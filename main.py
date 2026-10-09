"""
main.py
CLI entry point for KnapResume.

Commands:
  - tailor: single-run resume + cover-letter generation (PDF export).
  - phase6-batch: batch pipeline over a folder of JD PDFs using an existing profile,
    with per-run bottleneck diagnostics and summary reports.
    Full pipeline in CLI only — allocation -> LLM tailor -> claim
    verify -> sanitize -> feedback -> cover letter -> PDF export.
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.claims import extract_claims
from src.database import get_db_session
from src.feedback import build_feedback
from src.jd_structuring import persist_jd
from src.logger import get_logger
from src.models import Profile, ProfileFact, RunLog
from src.parser import extract_text
from src.pdf_generator import generate_cover_letter_pdf, generate_resume_pdf
from src.tailor import (
    generate_cover_letter,
    render_allocated_resume_text,
    tailor_resume,
    tailor_resume_with_allocation,
)
from src.verifier import record_claims, sanitize_text, verify_claims
from src.web_context import fetch_company_context

logger = get_logger("main")

app = typer.Typer(help="KnapResume CLI")
console = Console()

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


# Helpers ---------------------------------------------------------------------

def _validate_env() -> None:
    missing = []
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
        missing.append("ANTHROPIC_API_KEY or GEMINI_API_KEY")
    if missing:
        console.print(
            f"[bold red]Missing environment variables: {', '.join(missing)}[/]\n"
            "Copy .env.example to .env and fill in your keys.",
            style="red",
        )
        raise typer.Exit(1)


def _resolve_model(provider: str, model: str) -> str:
    if model.strip():
        return model.strip()
    return "claude-opus-4-5" if provider == "claude" else "gemini-3.5-flash-lite"


def _slug(value: str) -> str:
    out = re.sub(r"[^A-Za-z0-9]+", "_", (value or "").strip())
    out = out.strip("_")
    return out or "run"


def _collect_jd_pdfs(folder: Path, recursive: bool) -> List[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(p for p in folder.glob(pattern) if p.is_file())


def _compute_linear_sleep(run_index_in_batch: int, base_seconds: float,
                          step_seconds: float) -> float:
    return max(0.0, float(base_seconds) + (max(0, run_index_in_batch) * float(step_seconds)))


def _summarize_claim_states(verified: List[Dict[str, Any]]) -> Dict[str, int]:
    states = {"verified": 0, "inferred": 0, "unsupported": 0}
    for row in verified:
        st = str(row.get("state", "")).lower()
        if st in states:
            states[st] += 1
    return states


def _weakest_coverage(feedback: Dict[str, Any]) -> Optional[float]:
    weakest = feedback.get("weakest_section")
    sections = feedback.get("sections", {}) or {}
    if not weakest or weakest not in sections:
        return None
    cov = sections[weakest].get("coverage")
    return float(cov) if cov is not None else None


def _diagnose_bottleneck(
    profile_fact_count: int,
    selected_count: int,
    required_skills_count: int,
    total_utility: float,
    weakest_coverage: Optional[float],
    unsupported_ratio: float,
    timings_ms: Dict[str, int],
    pdf_failed: bool,
) -> Dict[str, str]:
    if profile_fact_count < 8 or selected_count < 4:
        return {
            "category": "profile_facts_low",
            "detail": "Profile fact inventory is too small for strong allocation coverage.",
        }

    if pdf_failed:
        return {
            "category": "pdf_generation",
            "detail": "PDF generation failed for this run.",
        }

    if required_skills_count > 0:
        if weakest_coverage is not None and weakest_coverage < 0.45:
            return {
                "category": "scoring_alignment",
                "detail": "Low required-skill coverage in weakest section.",
            }
        if total_utility < 0.80:
            return {
                "category": "scoring_alignment",
                "detail": "Low total utility from score/allocation indicates weak match quality.",
            }

    if unsupported_ratio > 0.35:
        return {
            "category": "verification_risk",
            "detail": "High unsupported-claim ratio after verification.",
        }

    if not timings_ms:
        return {"category": "healthy", "detail": "No bottleneck detected."}

    slowest_stage = max(timings_ms.items(), key=lambda kv: kv[1])[0]
    if slowest_stage in {"resume_pdf_ms", "cover_pdf_ms"}:
        return {
            "category": "pdf_generation_slow",
            "detail": "PDF build is the slowest stage.",
        }
    if slowest_stage in {"tailor_ms", "cover_ms", "allocation_tailor_ms"}:
        return {
            "category": "llm_latency",
            "detail": "Model inference is the slowest stage.",
        }
    if slowest_stage in {"persist_jd_ms", "feedback_ms", "verify_ms"}:
        return {
            "category": "scoring_pipeline_latency",
            "detail": "JD structuring/scoring/feedback path is the slowest stage.",
        }

    return {
        "category": "healthy",
        "detail": f"No quality bottleneck; slowest stage was {slowest_stage}.",
    }


def _write_run_report(path: Path, run: Dict[str, Any]) -> None:
    lines = [
        "# Phase 6 Batch Run Report",
        "",
        f"- run_index: {run.get('run_index')}",
        f"- status: {run.get('status')}",
        f"- jd_file: {run.get('jd_file')}",
        f"- run_log_id: {run.get('run_log_id')}",
        f"- bottleneck: {run.get('bottleneck', {}).get('category')}",
        f"- bottleneck_detail: {run.get('bottleneck', {}).get('detail')}",
        "",
        "## Metrics",
        "",
        f"- profile_fact_count: {run.get('profile_fact_count')}",
        f"- selected_count: {run.get('selected_count')}",
        f"- dropped_count: {run.get('dropped_count')}",
        f"- required_skills_count: {run.get('required_skills_count')}",
        f"- total_utility: {run.get('total_utility')}",
        f"- weakest_section_coverage: {run.get('weakest_section_coverage')}",
        f"- claim_counts: {run.get('claim_counts')}",
        f"- unsupported_ratio: {run.get('unsupported_ratio')}",
        "",
        "## Timings (ms)",
        "",
    ]

    for key, value in sorted((run.get("timings_ms") or {}).items()):
        lines.append(f"- {key}: {value}")

    if run.get("status") == "completed":
        lines.extend([
            "",
            "## Outputs",
            "",
            f"- resume_pdf: {run.get('resume_pdf_path')}",
            f"- cover_pdf: {run.get('cover_pdf_path')}",
        ])

    if run.get("error"):
        lines.extend(["", "## Error", "", str(run["error"])])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary_report(path: Path, payload: Dict[str, Any]) -> None:
    bottlenecks = payload.get("bottleneck_counts", {})
    lines = [
        "# Phase 6 Batch Summary",
        "",
        f"- generated_at: {payload.get('generated_at')}",
        f"- profile_id: {payload.get('profile_id')}",
        f"- profile_name: {payload.get('profile_name')}",
        f"- jd_folder: {payload.get('jd_folder')}",
        f"- total_runs: {payload.get('total_runs')}",
        f"- completed: {payload.get('completed')}",
        f"- failed: {payload.get('failed')}",
        "",
        "## Bottleneck Counts",
        "",
    ]

    for key in sorted(bottlenecks):
        lines.append(f"- {key}: {bottlenecks[key]}")

    lines.extend([
        "",
        "## Run Artifacts",
        "",
    ])
    for run in payload.get("runs", []):
        lines.append(
            f"- run_{int(run['run_index']):03d}: status={run.get('status')} "
            f"bottleneck={run.get('bottleneck', {}).get('category')} "
            f"report={run.get('report_path')}"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_profile(profile_id: int) -> Tuple[str, int]:
    with get_db_session() as s:
        profile = s.query(Profile).filter(Profile.id == profile_id).first()
        if profile is None:
            raise ValueError(f"Profile {profile_id} not found.")
        fact_count = (
            s.query(ProfileFact).filter(ProfileFact.profile_id == profile_id).count()
        )
        return str(profile.name), int(fact_count)


def _get_job_description(
    job_url: str = "",
    job_file: str = "",
    job_text: str = "",
) -> Tuple[str, str]:
    """Returns (job_description_text, job_url)."""
    if job_file:
        console.print(f"Reading job description from file: {job_file}")
        return extract_text(job_file, Path(job_file).name), ""

    if job_url:
        import httpx

        console.print(f"Fetching job description from URL: {job_url}")
        try:
            resp = httpx.get(job_url, timeout=15, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()[:8000]
            return text, job_url
        except Exception as e:
            console.print(f"[yellow]Could not fetch URL: {e}. Please paste the JD manually.[/]")

    if job_text:
        return job_text, ""

    # Interactive fallback
    console.print("\n[bold cyan]Paste the job description below.[/]")
    console.print("[dim]Enter a blank line followed by 'END' when done.[/]\n")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines), ""


def _get_resume_text(resume_file: str = "", resume_text: str = "") -> str:
    if resume_file:
        console.print(f"Reading resume from file: {resume_file}")
        return extract_text(resume_file, Path(resume_file).name)

    if resume_text:
        return resume_text

    console.print("\n[bold cyan]Paste your resume below.[/]")
    console.print("[dim]Enter a blank line followed by 'END' when done.[/]\n")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def _extract_company_job_title(job_description: str) -> Tuple[str, str]:
    """Best-effort extraction of company and job title from JD text."""
    lines = job_description.split("\n")[:10]

    company = "Unknown Company"
    job_title = "Role"

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if job_title == "Role" and len(line) > 3:
            job_title = line[:80]
        match = re.search(r"\bat\s+([A-Z][A-Za-z0-9\s&,.]+?)(?:\s*[|â€“â€”,.]|$)", line)
        if match:
            company = match.group(1).strip()[:60]
            break

    return company, job_title


# Commands --------------------------------------------------------------------

@app.command()
def tailor(
    resume_file: Optional[str] = typer.Option(None, "--resume", "-r", help="Path to resume PDF/DOCX/TXT"),
    job_file: Optional[str] = typer.Option(None, "--job-file", "-jf", help="Path to job description PDF/DOCX/TXT"),
    job_url: Optional[str] = typer.Option(None, "--job-url", "-u", help="URL of the job posting"),
    output_name: Optional[str] = typer.Option(None, "--output", "-o", help="Base name for output files (no extension)"),
    skip_web: bool = typer.Option(False, "--skip-web", help="Skip web context fetching"),
    provider: str = typer.Option("claude", "--provider", "-p", help="LLM Provider: claude or gemini"),
    model: str = typer.Option("", "--model", "-m", help="Specific model string (e.g. claude-opus-4-5, gemini-3.5-flash-lite)"),
):
    """
    Tailor your resume and generate a cover letter for a specific job.

    Outputs two PDFs: tailored_resume.pdf and cover_letter.pdf
    """
    console.print(Panel.fit(
        "[bold cyan]KnapResume[/] - ATS Optimization",
        border_style="cyan"
    ))

    _validate_env()
    provider = provider.strip().lower()
    if provider not in {"claude", "gemini"}:
        console.print("[red]Provider must be 'claude' or 'gemini'.[/]")
        raise typer.Exit(1)
    resolved_model = _resolve_model(provider, model or "")

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True) as progress:

        task = progress.add_task("Loading job description...", total=None)
        job_desc, detected_url = _get_job_description(
            job_url=job_url or "",
            job_file=job_file or "",
        )
        if not job_desc.strip():
            console.print("[red]Job description is empty. Aborting.[/]")
            raise typer.Exit(1)
        progress.update(task, description="Job description loaded")

        task2 = progress.add_task("Loading resume...", total=None)
        resume = _get_resume_text(resume_file=resume_file or "")
        if not resume.strip():
            console.print("[red]Resume is empty. Aborting.[/]")
            raise typer.Exit(1)
        progress.update(task2, description="Resume loaded")

    company, job_title = _extract_company_job_title(job_desc)
    console.print(f"\n[bold]Detected role:[/] {job_title}")
    console.print(f"[bold]Detected company:[/] {company}\n")
    logger.info("Run starting: company=%s role=%s provider=%s model=%s",
                company, job_title, provider, resolved_model)
    started = time.time()

    web_context = ""
    if not skip_web:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      transient=True) as progress:
            task = progress.add_task("Fetching company context from web...", total=None)
            web_context = fetch_company_context(job_desc, detected_url or job_url or "")
            progress.update(task, description="Web context fetched")
        logger.info("Web context fetched (%d chars)", len(web_context))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True) as progress:
        task = progress.add_task("Tailoring resume...", total=None)
        tailored = tailor_resume(
            resume,
            job_desc,
            web_context,
            provider=provider,
            model=resolved_model,
        )
        progress.update(task, description="Resume tailored")
    logger.info("Resume tailored (%d chars)", len(tailored))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True) as progress:
        task = progress.add_task("Generating cover letter...", total=None)
        cover = generate_cover_letter(
            resume,
            job_desc,
            tailored,
            web_context,
            provider=provider,
            model=resolved_model,
        )
        progress.update(task, description="Cover letter generated")
    logger.info("Cover letter generated (%d chars)", len(cover))

    base = output_name or f"{company.replace(' ', '_')}_{job_title[:20].replace(' ', '_')}"
    resume_pdf_path = str(OUTPUT_DIR / f"{base}_resume.pdf")
    cover_pdf_path = str(OUTPUT_DIR / f"{base}_cover_letter.pdf")

    generate_resume_pdf(tailored, resume_pdf_path)
    generate_cover_letter_pdf(cover, cover_pdf_path)
    logger.info("PDFs written: %s, %s", resume_pdf_path, cover_pdf_path)

    logger.info("Run completed in %.1fs", time.time() - started)
    console.print(Panel(
        f"[bold green]Done[/]\n\n"
        f"Resume: [cyan]{resume_pdf_path}[/]\n"
        f"Cover:  [cyan]{cover_pdf_path}[/]",
        title="Output Files",
        border_style="green",
    ))


@app.command("phase6-batch")
def phase6_batch(
    profile_id: int = typer.Option(..., "--profile-id", "-pid", help="Existing profile id to use for all runs."),
    jd_folder: str = typer.Option(..., "--jd-folder", "-jf", help="Folder containing one or many JD PDFs."),
    provider: str = typer.Option("claude", "--provider", "-p", help="LLM Provider: claude or gemini"),
    model: str = typer.Option("", "--model", "-m", help="Model override. Defaults per provider."),
    skip_web: bool = typer.Option(False, "--skip-web", help="Skip web-context enrichment."),
    use_nli: bool = typer.Option(True, "--use-nli/--no-nli", help="Enable NLI for borderline claim verification."),
    output_root: str = typer.Option("outputs", "--output-root", "-o", help="Root output directory for PDFs and reports."),
    recursive: bool = typer.Option(False, "--recursive", help="Recursively find PDFs in subfolders."),
    batch_size: int = typer.Option(2, "--batch-size", min=1, help="Number of runs per batch block."),
    linear_sleep_base: float = typer.Option(1.0, "--linear-sleep-base", min=0.0, help="Base sleep in seconds between runs."),
    linear_sleep_step: float = typer.Option(0.25, "--linear-sleep-step", min=0.0, help="Added linear sleep per run inside a batch."),
    batch_sleep: float = typer.Option(2.0, "--batch-sleep", min=0.0, help="Sleep at each batch boundary."),
    min_profile_facts: int = typer.Option(8, "--min-profile-facts", min=1, help="Abort if profile has too few facts (prevents dummy runs)."),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop immediately on the first failed run."),
):
    """
    Phase 6 batch pipeline (CLI-only):
    - Reads one/many JD PDFs from a folder (JD inputs only).
    - Uses an existing profile (no dummy profile generation).
    - Runs full pipeline: extract JD -> persist JD -> web context ->
      allocation + LLM tailor -> claim verify + sanitize -> feedback ->
      cover letter -> PDF export.
    - Persists RunLog/Claim records and emits per-run + summary bottleneck reports.
    """
    console.print(Panel.fit(
        "[bold cyan]KnapResume Phase 6 Batch Pipeline[/]",
        border_style="cyan",
    ))

    _validate_env()

    provider = provider.strip().lower()
    if provider not in {"claude", "gemini"}:
        console.print("[red]Provider must be 'claude' or 'gemini'.[/]")
        raise typer.Exit(1)
    resolved_model = _resolve_model(provider, model)

    jd_dir = Path(jd_folder).expanduser().resolve()
    if not jd_dir.exists() or not jd_dir.is_dir():
        console.print(f"[red]JD folder does not exist: {jd_dir}[/]")
        raise typer.Exit(1)

    try:
        profile_name, profile_fact_count = _load_profile(profile_id)
    except Exception as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    if profile_fact_count < min_profile_facts:
        console.print(
            "[red]Aborting: profile does not have enough facts for Phase 6 benchmarking "
            f"({profile_fact_count} < {min_profile_facts}).[/]"
        )
        raise typer.Exit(1)

    jd_files = _collect_jd_pdfs(jd_dir, recursive=recursive)
    if not jd_files:
        console.print("[red]No PDF files found in the JD folder.[/]")
        raise typer.Exit(1)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_root = Path(output_root).expanduser().resolve() / f"phase6_batch_{ts}"
    pdf_root = run_root / "pdf"
    report_root = run_root / "reports"
    pdf_root.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Phase6 batch start profile_id=%d profile_name=%s fact_count=%d folder=%s files=%d provider=%s model=%s",
        profile_id,
        profile_name,
        profile_fact_count,
        str(jd_dir),
        len(jd_files),
        provider,
        resolved_model,
    )
    console.print(f"[bold]Profile:[/] {profile_name} (id={profile_id}, facts={profile_fact_count})")
    console.print(f"[bold]JD files:[/] {len(jd_files)}")
    console.print(f"[bold]Output:[/] {run_root}")

    runs: List[Dict[str, Any]] = []
    total = len(jd_files)

    for i, jd_path in enumerate(jd_files, start=1):
        run_started = time.perf_counter()
        timings_ms: Dict[str, int] = {}
        report: Dict[str, Any] = {
            "run_index": i,
            "jd_file": str(jd_path),
            "status": "failed",
            "profile_fact_count": profile_fact_count,
            "selected_count": 0,
            "dropped_count": 0,
            "required_skills_count": 0,
            "total_utility": 0.0,
            "weakest_section_coverage": None,
            "claim_counts": {"verified": 0, "inferred": 0, "unsupported": 0},
            "unsupported_ratio": 0.0,
            "timings_ms": timings_ms,
            "bottleneck": {"category": "unknown", "detail": "Run not completed."},
            "run_log_id": None,
            "resume_pdf_path": None,
            "cover_pdf_path": None,
            "error": None,
        }

        console.print(f"\n[bold cyan]Run {i}/{total}[/] Processing [cyan]{jd_path.name}[/]")
        stage = "setup"
        jd_id: Optional[int] = None
        pdf_failed = False

        try:
            stage = "extract_jd"
            t0 = time.perf_counter()
            jd_text = extract_text(str(jd_path), jd_path.name)
            timings_ms["extract_jd_ms"] = int((time.perf_counter() - t0) * 1000)
            if not jd_text.strip() or len(jd_text.strip()) < 100:
                raise ValueError("JD extraction produced too little text; supply a real JD PDF.")

            stage = "persist_jd"
            t0 = time.perf_counter()
            jd_info = persist_jd(jd_text)
            jd_id = int(jd_info["id"])
            timings_ms["persist_jd_ms"] = int((time.perf_counter() - t0) * 1000)
            required_skills_count = int(jd_info.get("requirements_count") or 0)
            report["required_skills_count"] = required_skills_count

            stage = "web_context"
            web_context = ""
            if not skip_web:
                t0 = time.perf_counter()
                web_context = fetch_company_context(jd_text, "")
                timings_ms["web_context_ms"] = int((time.perf_counter() - t0) * 1000)

            stage = "allocation_tailor"
            t0 = time.perf_counter()
            bundle = tailor_resume_with_allocation(
                profile_id=profile_id,
                jd_id=jd_id,
                web_context=web_context,
                provider=provider,
                model=resolved_model,
            )
            timings_ms["allocation_tailor_ms"] = int((time.perf_counter() - t0) * 1000)
            allocation = bundle["allocation"]
            tailored_text = bundle["tailored_text"]
            selected = allocation.get("selected_facts", [])
            dropped = allocation.get("dropped_facts", [])
            report["selected_count"] = len(selected)
            report["dropped_count"] = len(dropped)
            report["total_utility"] = float(allocation.get("total_utility") or 0.0)

            stage = "verify"
            t0 = time.perf_counter()
            claims = extract_claims(tailored_text)
            all_facts = [*selected, *dropped]
            verified = verify_claims(claims, all_facts, use_nli=use_nli)
            sanitized = sanitize_text(tailored_text, verified)
            safe_resume_text = sanitized["sanitized_text"]
            timings_ms["verify_ms"] = int((time.perf_counter() - t0) * 1000)
            claim_counts = _summarize_claim_states(verified)
            total_claims = max(1, sum(claim_counts.values()))
            unsupported_ratio = claim_counts["unsupported"] / total_claims
            report["claim_counts"] = claim_counts
            report["unsupported_ratio"] = unsupported_ratio

            stage = "feedback"
            t0 = time.perf_counter()
            feedback = build_feedback(profile_id, jd_id)
            timings_ms["feedback_ms"] = int((time.perf_counter() - t0) * 1000)
            report["weakest_section_coverage"] = _weakest_coverage(feedback)

            stage = "cover_letter"
            t0 = time.perf_counter()
            allocated_resume = render_allocated_resume_text(selected)
            cover_text = generate_cover_letter(
                allocated_resume,
                jd_text,
                safe_resume_text,
                web_context,
                provider=provider,
                model=resolved_model,
            )
            timings_ms["cover_ms"] = int((time.perf_counter() - t0) * 1000)

            stage = "pdf"
            company = str(jd_info.get("company") or "company")
            title = str(jd_info.get("job_title") or jd_path.stem)
            base = f"run{i:03d}_{_slug(company)}_{_slug(title)[:40]}"
            resume_pdf_path = pdf_root / f"{base}_resume.pdf"
            cover_pdf_path = pdf_root / f"{base}_cover_letter.pdf"
            t0 = time.perf_counter()
            generate_resume_pdf(safe_resume_text, str(resume_pdf_path))
            timings_ms["resume_pdf_ms"] = int((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            generate_cover_letter_pdf(cover_text, str(cover_pdf_path))
            timings_ms["cover_pdf_ms"] = int((time.perf_counter() - t0) * 1000)

            stage = "persist_run"
            total_ms = int((time.perf_counter() - run_started) * 1000)
            bottleneck = _diagnose_bottleneck(
                profile_fact_count=profile_fact_count,
                selected_count=int(report["selected_count"]),
                required_skills_count=required_skills_count,
                total_utility=float(report["total_utility"]),
                weakest_coverage=report["weakest_section_coverage"],
                unsupported_ratio=float(report["unsupported_ratio"]),
                timings_ms=timings_ms,
                pdf_failed=pdf_failed,
            )
            report["bottleneck"] = bottleneck

            with get_db_session() as s:
                row = RunLog(
                    profile_id=profile_id,
                    jd_id=jd_id,
                    status="completed",
                    duration_ms=total_ms,
                    resume_pdf_path=str(resume_pdf_path),
                    cover_pdf_path=str(cover_pdf_path),
                    feedback={
                        "kind": "phase6_batch_cli",
                        "weakest_section": feedback.get("weakest_section"),
                        "reasoning": feedback.get("reasoning"),
                        "sections": feedback.get("sections"),
                        "timings_ms": timings_ms,
                        "bottleneck": bottleneck,
                        "jd_file": str(jd_path),
                    },
                )
                s.add(row)
                s.flush()
                run_log_id = int(row.to_dict()["id"])
                record_claims(run_log_id, verified, session=s)
                report["run_log_id"] = run_log_id

            report["status"] = "completed"
            report["resume_pdf_path"] = str(resume_pdf_path)
            report["cover_pdf_path"] = str(cover_pdf_path)
            logger.info(
                "Phase6 run completed idx=%d jd=%s run_id=%s bottleneck=%s",
                i,
                jd_path.name,
                report.get("run_log_id"),
                bottleneck.get("category"),
            )
            console.print(
                "[green]Completed[/] "
                f"bottleneck=[bold]{bottleneck.get('category')}[/] "
                f"run_id={report.get('run_log_id')}"
            )

        except Exception as e:
            pdf_failed = (stage == "pdf")
            timings_ms["total_ms"] = int((time.perf_counter() - run_started) * 1000)
            bottleneck = _diagnose_bottleneck(
                profile_fact_count=profile_fact_count,
                selected_count=int(report.get("selected_count") or 0),
                required_skills_count=int(report.get("required_skills_count") or 0),
                total_utility=float(report.get("total_utility") or 0.0),
                weakest_coverage=report.get("weakest_section_coverage"),
                unsupported_ratio=float(report.get("unsupported_ratio") or 0.0),
                timings_ms=timings_ms,
                pdf_failed=pdf_failed,
            )
            report["bottleneck"] = bottleneck
            report["error"] = f"stage={stage}: {e}"
            logger.exception("Phase6 run failed idx=%d jd=%s stage=%s", i, jd_path.name, stage)

            with get_db_session() as s:
                fail_row = RunLog(
                    profile_id=profile_id,
                    jd_id=jd_id,
                    status="failed",
                    duration_ms=int((time.perf_counter() - run_started) * 1000),
                    error_message=str(e),
                    feedback={
                        "kind": "phase6_batch_cli",
                        "failed_stage": stage,
                        "bottleneck": bottleneck,
                        "jd_file": str(jd_path),
                    },
                )
                s.add(fail_row)
                s.flush()
                report["run_log_id"] = int(fail_row.to_dict()["id"])

            console.print(
                "[red]Failed[/] "
                f"stage={stage} bottleneck=[bold]{bottleneck.get('category')}[/]"
            )
            if fail_fast:
                runs.append(report)
                report_path = report_root / f"run_{i:03d}_{_slug(jd_path.stem)}.md"
                _write_run_report(report_path, report)
                report["report_path"] = str(report_path)
                break

        report.setdefault("timings_ms", timings_ms)
        if "total_ms" not in report["timings_ms"]:
            report["timings_ms"]["total_ms"] = int((time.perf_counter() - run_started) * 1000)

        report_path = report_root / f"run_{i:03d}_{_slug(jd_path.stem)}.md"
        _write_run_report(report_path, report)
        report["report_path"] = str(report_path)
        runs.append(report)

        if i < total:
            idx_in_batch = (i - 1) % batch_size
            if i % batch_size == 0:
                sleep_s = float(batch_sleep)
                reason = "batch boundary"
            else:
                sleep_s = _compute_linear_sleep(idx_in_batch, linear_sleep_base, linear_sleep_step)
                reason = "linear"
            if sleep_s > 0:
                console.print(f"[dim]Sleeping {sleep_s:.2f}s ({reason}) before next run...[/]")
                time.sleep(sleep_s)

    completed = sum(1 for r in runs if r.get("status") == "completed")
    failed = len(runs) - completed
    bottleneck_counts: Dict[str, int] = {}
    for r in runs:
        key = (r.get("bottleneck") or {}).get("category", "unknown")
        bottleneck_counts[key] = bottleneck_counts.get(key, 0) + 1

    summary_payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "profile_id": profile_id,
        "profile_name": profile_name,
        "jd_folder": str(jd_dir),
        "total_runs": len(runs),
        "completed": completed,
        "failed": failed,
        "bottleneck_counts": bottleneck_counts,
        "runs": runs,
    }
    summary_md = report_root / "summary.md"
    summary_json = report_root / "summary.json"
    _write_summary_report(summary_md, summary_payload)
    summary_json.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    console.print(Panel(
        f"[bold green]Phase 6 batch finished[/]\n\n"
        f"Completed: {completed}\n"
        f"Failed: {failed}\n"
        f"Summary: [cyan]{summary_md}[/]\n"
        f"JSON: [cyan]{summary_json}[/]",
        title="Batch Report",
        border_style="green" if failed == 0 else "yellow",
    ))


@app.command("phase6-eval")
def phase6_eval(
    profile_id: int = typer.Option(..., "--profile-id", "-pid", help="Existing profile id."),
    jd_id: int = typer.Option(..., "--jd-id", "-jid", help="Persisted JD id to compare against."),
    provider: str = typer.Option("claude", "--provider", "-p", help="LLM Provider: claude or gemini"),
    model: str = typer.Option("", "--model", "-m", help="Model override. Defaults per provider."),
    use_nli: bool = typer.Option(True, "--use-nli/--no-nli", help="Enable NLI for borderline claims."),
    output_root: str = typer.Option("outputs", "--output-root", "-o", help="Root output directory for eval report."),
):
    """Phase 6.3/6.4: baseline (prompt-only) vs KnapResume on one profile+JD.

    Runs both arms with live LLM calls, computes the four Stage 6.2 metrics,
    and writes report.md + results.csv + chart.png (Stage 6.4).
    """
    from src.evaluation import evaluate_profile_jd, save_report

    console.print(Panel.fit("[bold cyan]KnapResume Phase 6 Eval[/]", border_style="cyan"))
    _validate_env()
    provider = provider.strip().lower()
    if provider not in {"claude", "gemini"}:
        console.print("[red]Provider must be 'claude' or 'gemini'.[/]")
        raise typer.Exit(1)
    resolved_model = _resolve_model(provider, model)
    _load_profile(profile_id)  # validates existence / fact threshold messaging

    import functools

    from src.tailor import render_allocated_resume_text, tailor_resume

    def _baseline_fn(resume_text: str, jd_text: str) -> str:
        return tailor_resume(resume_text, jd_text, provider=provider, model=resolved_model)

    def _knap_fn() -> Dict[str, Any]:
        from src.tailor import tailor_resume_with_allocation

        return tailor_resume_with_allocation(
            profile_id, jd_id, provider=provider, model=resolved_model
        )

    result = evaluate_profile_jd(
        profile_id, jd_id,
        baseline_tailor_fn=_baseline_fn, knap_bundle_fn=_knap_fn,
        use_nli=use_nli,
    )
    result["label"] = f"profile={profile_id} jd={jd_id} {provider}/{resolved_model}"
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(output_root).expanduser().resolve() / f"phase6_eval_{ts}"
    paths = save_report([result], out_dir)
    console.print(Panel(
        f"[bold green]Eval finished[/] knap wins {result['knap_wins']}/4\n\n"
        f"Report: [cyan]{paths['report_md']}[/]\n"
        f"CSV: [cyan]{paths['results_csv']}[/]\n"
        f"Chart: [cyan]{paths['chart_png']}[/]",
        title="Eval Report", border_style="green",
    ))


if __name__ == "__main__":
    app()

