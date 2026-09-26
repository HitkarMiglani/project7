"""
main.py
CLI entry point for KnapResume.
Supports job URL, job description text, and file uploads for both
job description and resume.

Usage:
  python main.py                         # Interactive wizard / tailor
  python main.py --help                  # Show all options
"""

import os
import sys
import time
import typer
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.logger import get_logger
from src.parser import extract_text
from src.web_context import fetch_company_context
from src.tailor import tailor_resume, generate_cover_letter
from src.pdf_generator import generate_resume_pdf, generate_cover_letter_pdf

logger = get_logger("main")

app = typer.Typer(help="🎯 KnapResume — ATS-optimized resume tailoring with knapsack allocation & verification")
console = Console()

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validate_env():
    missing = []
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
        missing.append("ANTHROPIC_API_KEY or GEMINI_API_KEY")
    if missing:
        console.print(
            f"[bold red]❌ Missing environment variables: {', '.join(missing)}[/]\n"
            "Copy .env.example to .env and fill in your keys.",
            style="red",
        )
        raise typer.Exit(1)


def _get_job_description(
    job_url: str = "",
    job_file: str = "",
    job_text: str = "",
) -> tuple[str, str]:
    """Returns (job_description_text, job_url)."""
    if job_file:
        console.print(f"📄 Reading job description from file: {job_file}")
        return extract_text(job_file, Path(job_file).name), ""

    if job_url:
        import httpx, re
        console.print(f"🌐 Fetching job description from URL: {job_url}")
        try:
            resp = httpx.get(job_url, timeout=15, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()[:8000]
            return text, job_url
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not fetch URL: {e}. Please paste the JD manually.[/]")

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
        console.print(f"📄 Reading resume from file: {resume_file}")
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


def _extract_company_job_title(job_description: str) -> tuple[str, str]:
    """Best-effort extraction of company and job title from JD text."""
    import re
    lines = job_description.split("\n")[:10]

    company = "Unknown Company"
    job_title = "Role"

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # First substantial line is likely the job title
        if job_title == "Role" and len(line) > 3:
            job_title = line[:80]
        # Look for "at Company" pattern
        match = re.search(r"\bat\s+([A-Z][A-Za-z0-9\s&,.]+?)(?:\s*[|–—,.]|$)", line)
        if match:
            company = match.group(1).strip()[:60]
            break

    return company, job_title


# ── Main Command ──────────────────────────────────────────────────────────────

@app.command()
def tailor(
    resume_file: Optional[str] = typer.Option(None, "--resume", "-r", help="Path to resume PDF/DOCX/TXT"),
    job_file: Optional[str] = typer.Option(None, "--job-file", "-jf", help="Path to job description PDF/DOCX/TXT"),
    job_url: Optional[str] = typer.Option(None, "--job-url", "-u", help="URL of the job posting"),
    output_name: Optional[str] = typer.Option(None, "--output", "-o", help="Base name for output files (no extension)"),
    skip_web: bool = typer.Option(False, "--skip-web", help="Skip web context fetching"),
    provider: str = typer.Option("claude", "--provider", "-p", help="LLM Provider: claude or gemini"),
    model: str = typer.Option("", "--model", "-m", help="Specific model string (e.g. claude-opus-4-5, gemini-2.5-flash)"),
):
    """
    🎯 Tailor your resume and generate a cover letter for a specific job.

    Outputs two PDFs: tailored_resume.pdf and cover_letter.pdf
    """
    console.print(Panel.fit(
        "[bold cyan]KnapResume[/] — ATS Optimization with Knapsack Allocation & Verification",
        border_style="cyan"
    ))

    _validate_env()

    # ── Step 1: Collect inputs ────────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True) as progress:

        task = progress.add_task("Loading job description...", total=None)
        job_desc, detected_url = _get_job_description(
            job_url=job_url or "",
            job_file=job_file or "",
        )
        if not job_desc.strip():
            console.print("[red]❌ Job description is empty. Aborting.[/]")
            raise typer.Exit(1)
        progress.update(task, description="✅ Job description loaded")

        task2 = progress.add_task("Loading resume...", total=None)
        resume = _get_resume_text(resume_file=resume_file or "")
        if not resume.strip():
            console.print("[red]❌ Resume is empty. Aborting.[/]")
            raise typer.Exit(1)
        progress.update(task2, description="✅ Resume loaded")

    company, job_title = _extract_company_job_title(job_desc)
    console.print(f"\n[bold]Detected role:[/] {job_title}")
    console.print(f"[bold]Detected company:[/] {company}\n")
    logger.info("Run starting: company=%s role=%s provider=%s model=%s",
                company, job_title, provider, model or "claude-opus-4-5")
    _start = time.time()

    # ── Step 2: Web context ──────────────────────────────────────────────────
    web_context = ""
    if not skip_web:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      transient=True) as progress:
            task = progress.add_task("Fetching company context from web...", total=None)
            web_context = fetch_company_context(job_desc, detected_url or job_url or "")
            progress.update(task, description="✅ Web context fetched")
        logger.info("Web context fetched (%d chars)", len(web_context))

    # ── Step 3: Tailor resume ────────────────────────────────────────────────
    console.print(f"[bold cyan]Step 1/3:[/] Tailoring resume with {provider.title()} AI...")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True) as progress:
        task = progress.add_task("Analysing and tailoring...", total=None)
        tailored = tailor_resume(resume, job_desc, web_context, provider=provider, model=model or "claude-opus-4-5")
        progress.update(task, description="✅ Resume tailored")
    logger.info("Resume tailored (%d chars)", len(tailored))

    # ── Step 4: Generate cover letter ────────────────────────────────────────
    console.print(f"[bold cyan]Step 2/3:[/] Generating cover letter with {provider.title()} AI...")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True) as progress:
        task = progress.add_task("Writing cover letter...", total=None)
        cover = generate_cover_letter(resume, job_desc, tailored, web_context, provider=provider, model=model or "claude-opus-4-5")
        progress.update(task, description="✅ Cover letter generated")
    logger.info("Cover letter generated (%d chars)", len(cover))

    # ── Step 5: Generate PDFs ────────────────────────────────────────────────
    console.print("[bold cyan]Step 3/3:[/] Generating PDFs...")
    base = output_name or f"{company.replace(' ', '_')}_{job_title[:20].replace(' ', '_')}"
    resume_pdf_path = str(OUTPUT_DIR / f"{base}_resume.pdf")
    cover_pdf_path = str(OUTPUT_DIR / f"{base}_cover_letter.pdf")

    generate_resume_pdf(tailored, resume_pdf_path)
    generate_cover_letter_pdf(cover, cover_pdf_path)
    logger.info("PDFs written: %s, %s", resume_pdf_path, cover_pdf_path)

    # ── Done ─────────────────────────────────────────────────────────────────
    logger.info("Run completed in %.1fs", time.time() - _start)
    console.print(Panel(
        f"[bold green]✅ Done![/]\n\n"
        f"📄 Tailored Resume:  [cyan]{resume_pdf_path}[/]\n"
        f"✉️  Cover Letter:    [cyan]{cover_pdf_path}[/]",
        title="Output Files",
        border_style="green",
    ))


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
