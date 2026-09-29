"""
src/evaluation.py
Phase 6 — Stages 6.2/6.3/6.4: metric pipeline, comparative benchmark, reporting.

Stage 6.2 — four deterministic metrics (all in [0, 1] except utilization
which may exceed 1 on mandatory over-capacity, reported raw):

  - keyword_match_rate: distinct required skills matched in ANY feedback
    section / total required. Derived from feedback sections' `missing`
    lists (each section reports missing vs the full required set), so
    matched-anywhere = required - intersection(all missing).
  - ats_density: required-skill substring mentions per 100 words of the
    tailored text (case-insensitive), normalized to [0, 1] as
    min(1, mentions_per_100_words / 10). 10+ mentions/100w saturates.
  - fabrication_rate: unsupported claims / total claims (0.0 when no claims).
  - knapsack_utilization: total allocated weight / total capacity across
    allocation sections (sum total_weight / sum capacity).

Stage 6.3 — compare baseline (prompt-only: all facts -> LLM) vs KnapResume
(allocated subset -> LLM -> verify/sanitize) via evaluate_texts(), a pure
function over already-produced texts + verification states. DB/LLM wiring
lives in evaluate_profile_jd() with injectable callables so tests stay
offline.

Stage 6.4 — save_report() emits report.md + results.csv (pandas) +
chart.png (matplotlib Agg) into an output dir.

Stage 7.1 — build_ats_checklist(): lightweight ATS keyword checklist
(grade + matched/missing skills) for API responses and the web UI.
Further stages: see progress.md Phase 7.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.logger import get_logger

logger = get_logger("evaluation")

METRIC_KEYS = (
    "keyword_match_rate",
    "ats_density",
    "fabrication_rate",
    "knapsack_utilization",
)


# ── Stage 6.2 — metric primitives ────────────────────────────────────────────

def compute_keyword_match_rate(
    feedback: Dict[str, Any],
    requirements: Optional[List[Dict[str, Any]]] = None,
) -> float:
    """Distinct required skills matched in any section / total required."""
    sections = (feedback or {}).get("sections", {}) or {}
    # Required universe: prefer explicit requirements list, else reconstruct
    # from section matched+missing counts.
    if requirements is not None:
        required = [
            str(r.get("skill", ""))
            for r in requirements
            if str(r.get("category", "required")) == "required"
        ]
    else:
        required = []
        for sec in sections.values():
            for s in (sec.get("missing") or []):
                if s not in required:
                    required.append(str(s))
            # matched names are not stored, only counts — missing union is
            # the best reconstruction without requirements.
    if not required:
        # Fall back: mean coverage across sections with total > 0.
        covs = [
            float(s.get("coverage", 0.0))
            for s in sections.values()
            if int(s.get("total", 0) or 0) > 0
        ]
        return sum(covs) / len(covs) if covs else 1.0
    still_missing = set(required)
    for sec in sections.values():
        still_missing -= set(sections and (set(required) - set(sec.get("missing", []))) or set())
        # Equivalent: still_missing &= set(sec missing)
        still_missing &= set(str(m) for m in (sec.get("missing", []) or []))
        if not still_missing:
            break
    matched = len(required) - len(still_missing)
    return matched / len(required)


def compute_ats_density(
    tailored_text: str,
    requirements: List[Dict[str, Any]],
) -> float:
    """Skill mentions per 100 words, saturated at 10/100w -> 1.0."""
    text = (tailored_text or "").lower()
    words = len(text.split())
    if not words or not requirements:
        return 0.0
    required = [
        str(r.get("skill", "")).lower()
        for r in requirements
        if str(r.get("category", "required")) == "required" and str(r.get("skill", "")).strip()
    ]
    if not required:
        return 0.0
    mentions = sum(1 for s in required if s and s in text)
    per_100 = mentions / words * 100.0
    return min(1.0, per_100 / 10.0)


def _state_counts(
    verified: Optional[List[Dict[str, Any]]] = None,
    claim_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, int]:
    if claim_counts is not None:
        return {
            "verified": int(claim_counts.get("verified", 0) or 0),
            "inferred": int(claim_counts.get("inferred", 0) or 0),
            "unsupported": int(claim_counts.get("unsupported", 0) or 0),
        }
    counts = {"verified": 0, "inferred": 0, "unsupported": 0}
    for row in verified or []:
        st = str((row or {}).get("state", "")).lower()
        if st in counts:
            counts[st] += 1
    return counts


def compute_fabrication_rate(
    verified: Optional[List[Dict[str, Any]]] = None,
    claim_counts: Optional[Dict[str, int]] = None,
) -> float:
    """Unsupported / total claims (0.0 when there are no claims)."""
    counts = _state_counts(verified, claim_counts)
    total = counts["verified"] + counts["inferred"] + counts["unsupported"]
    if total <= 0:
        return 0.0
    return counts["unsupported"] / total


def compute_knapsack_utilization(allocation: Dict[str, Any]) -> float:
    """Sum total_weight / sum capacity over allocation sections."""
    sections = (allocation or {}).get("sections", {}) or {}
    total_w = sum(float(s.get("total_weight", 0.0) or 0.0) for s in sections.values())
    total_c = sum(float(s.get("capacity", 0.0) or 0.0) for s in sections.values())
    if total_c <= 0:
        return 0.0
    return total_w / total_c


def compute_metrics(
    tailored_text: str,
    allocation: Dict[str, Any],
    feedback: Dict[str, Any],
    requirements: List[Dict[str, Any]],
    verified: Optional[List[Dict[str, Any]]] = None,
    claim_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, float]:
    """All four Stage 6.2 metrics for one arm (baseline or KnapResume)."""
    return {
        "keyword_match_rate": compute_keyword_match_rate(feedback, requirements),
        "ats_density": compute_ats_density(tailored_text, requirements),
        "fabrication_rate": compute_fabrication_rate(verified, claim_counts),
        "knapsack_utilization": compute_knapsack_utilization(allocation),
    }


# ── Stage 6.3 — comparative benchmark (pure) ─────────────────────────────────

def compare_metrics(
    baseline: Dict[str, float],
    knapresume: Dict[str, float],
) -> Dict[str, Any]:
    """Per-metric deltas (knap - baseline) + win flags.

    Higher is better for keyword_match_rate / ats_density /
    knapsack_utilization; lower is better for fabrication_rate.
    """
    lower_is_better = {"fabrication_rate"}
    deltas: Dict[str, float] = {}
    wins: Dict[str, bool] = {}
    for key in METRIC_KEYS:
        b = float(baseline.get(key, 0.0) or 0.0)
        k = float(knapresume.get(key, 0.0) or 0.0)
        d = k - b
        deltas[key] = d
        wins[key] = (d < 0) if key in lower_is_better else (d > 0)
    return {"deltas": deltas, "wins": wins, "knap_wins": sum(1 for v in wins.values() if v)}


def evaluate_texts(
    baseline_text: str,
    knap_text: str,
    allocation: Dict[str, Any],
    feedback: Dict[str, Any],
    requirements: List[Dict[str, Any]],
    baseline_verified: Optional[List[Dict[str, Any]]] = None,
    knap_verified: Optional[List[Dict[str, Any]]] = None,
    baseline_claim_counts: Optional[Dict[str, int]] = None,
    knap_claim_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Compare two already-produced texts. No models, no DB, no LLM."""
    baseline_m = compute_metrics(
        baseline_text, {"sections": {}}, feedback, requirements,
        baseline_verified, baseline_claim_counts,
    )
    # Baseline prompt-only has no knapsack allocation: utilization n/a -> 0.
    baseline_m["knapsack_utilization"] = 0.0
    knap_m = compute_metrics(
        knap_text, allocation, feedback, requirements,
        knap_verified, knap_claim_counts,
    )
    comparison = compare_metrics(baseline_m, knap_m)
    return {
        "baseline": baseline_m,
        "knapresume": knap_m,
        **comparison,
    }


# ── DB/LLM wiring (injectable for offline tests) ─────────────────────────────

def evaluate_profile_jd(
    profile_id: int,
    jd_id: int,
    session=None,
    baseline_tailor_fn: Optional[Callable[[str, str], str]] = None,
    knap_bundle_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    verify_fn: Optional[Callable[[List[Dict[str, Any]], List[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
    use_nli: bool = True,
) -> Dict[str, Any]:
    """Full 6.3 comparison for one profile+JD.

    Injectables keep tests offline:
      - baseline_tailor_fn(resume_text, jd_text) -> tailored text.
      - knap_bundle_fn() -> {"tailored_text", "allocation"}.
      - verify_fn(claims, facts) -> verified states.
    Defaults call the real pipeline (require LLM + embedding models).
    """
    from src.claims import extract_claims
    from src.database import get_db_session
    from src.feedback import build_feedback
    from src.verifier import verify_claims

    def _run(s):
        from src.models import JD as JDModel
        from src.models import JDRequirement
        from src.tailor import (
            build_allocation_context,
            render_allocated_resume_text,
            tailor_resume,
            tailor_resume_with_allocation,
        )

        jd = s.query(JDModel).filter(JDModel.id == jd_id).first()
        if jd is None:
            raise ValueError(f"JD {jd_id} not found.")
        req_rows = (
            s.query(JDRequirement)
            .filter(JDRequirement.jd_id == jd_id)
            .order_by(JDRequirement.id)
            .all()
        )
        requirements = [
            {"skill": r.skill, "category": r.category, "importance": r.importance}
            for r in req_rows
        ]
        context = build_allocation_context(profile_id, jd_id, session=s)
        feedback = build_feedback(profile_id, jd_id, session=s)
        all_facts = [*context["selected_facts"], *context["dropped_facts"]]

        # KnapResume arm.
        if knap_bundle_fn is not None:
            bundle = knap_bundle_fn()
        else:
            bundle = tailor_resume_with_allocation(profile_id, jd_id, session=s)
        knap_text = bundle["tailored_text"]
        allocation = bundle["allocation"]

        # Baseline arm: full-fact resume text -> prompt-only LLM call.
        full_text = render_allocated_resume_text(all_facts, with_ids=False)
        if baseline_tailor_fn is not None:
            baseline_text = baseline_tailor_fn(full_text, jd.raw_text)
        else:
            baseline_text = tailor_resume(full_text, jd.raw_text or "")

        verify = verify_fn or (lambda claims, facts: verify_claims(claims, facts, use_nli=use_nli))
        knap_verified = verify(extract_claims(knap_text), all_facts)
        baseline_verified = verify(extract_claims(baseline_text), all_facts)

        result = evaluate_texts(
            baseline_text, knap_text, allocation, feedback, requirements,
            baseline_verified=baseline_verified, knap_verified=knap_verified,
        )
        logger.info(
            "Eval profile=%d jd=%d knap_wins=%d/4 fab_base=%.2f fab_knap=%.2f",
            profile_id, jd_id, result["knap_wins"],
            result["baseline"]["fabrication_rate"],
            result["knapresume"]["fabrication_rate"],
        )
        return {
            "profile_id": profile_id, "jd_id": jd_id,
            "baseline_text": baseline_text, "knap_text": knap_text,
            **result,
        }

    if session is not None:
        return _run(session)
    with get_db_session() as s:
        return _run(s)


# ── Stage 7.1 — ATS keyword checklist ────────────────────────────────────────
# Single source lives in src.feedback (stored on RunLog rows); re-exported
# here for the runs API and report code.

from src.feedback import ats_grade, build_ats_checklist  # noqa: E402,F401


def get_ats_checklist(
    profile_id: int,
    jd_id: int,
    session=None,
) -> Dict[str, Any]:
    """Checklist for a profile+JD (optional-session pattern)."""
    from src.database import get_db_session
    from src.feedback import build_feedback
    from src.models import JDRequirement

    def _build(s):
        feedback = build_feedback(profile_id, jd_id, session=s)
        req_rows = (
            s.query(JDRequirement)
            .filter(JDRequirement.jd_id == jd_id)
            .order_by(JDRequirement.id)
            .all()
        )
        requirements = [
            {"skill": r.skill, "category": r.category} for r in req_rows
        ]
        return build_ats_checklist(feedback, requirements)

    if session is not None:
        return _build(session)
    with get_db_session() as s:
        return _build(s)


# ── Stage 6.4 — reporting (tables + charts) ──────────────────────────────────

def results_frame(results: List[Dict[str, Any]]):
    """pandas DataFrame with one row per evaluated pair (baseline + knap)."""
    import pandas as pd

    rows = []
    for r in results or []:
        label = str(r.get("label") or f"profile={r.get('profile_id')} jd={r.get('jd_id')}")
        for arm in ("baseline", "knapresume"):
            m = (r.get(arm) or {})
            rows.append({
                "pair": label,
                "arm": arm,
                **{k: float(m.get(k, 0.0) or 0.0) for k in METRIC_KEYS},
            })
    return pd.DataFrame(rows, columns=["pair", "arm", *METRIC_KEYS])


def save_report(
    results: List[Dict[str, Any]],
    out_dir: str | Path,
    title: str = "KnapResume Evaluation Report (Phase 6)",
) -> Dict[str, str]:
    """Write report.md + results.csv + chart.png. Returns paths."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame = results_frame(results)
    csv_path = out / "results.csv"
    frame.to_csv(str(csv_path), index=False)

    # Grouped bars: mean per arm across pairs (all metrics 0..1 scale;
    # fabrication lower-is-better is still plotted raw with a note).
    chart_path = out / "chart.png"
    if frame.empty:
        plt.figure(figsize=(8, 4))
        plt.text(0.5, 0.5, "No evaluation results", ha="center")
        plt.savefig(str(chart_path), bbox_inches="tight")
        plt.close()
    else:
        means = frame.groupby("arm")[list(METRIC_KEYS)].mean().reindex(["baseline", "knapresume"])
        x = range(len(METRIC_KEYS))
        width = 0.35
        plt.figure(figsize=(9, 4.5))
        b_vals = [float(means.loc["baseline", k]) if "baseline" in means.index else 0.0 for k in METRIC_KEYS]
        k_vals = [float(means.loc["knapresume", k]) if "knapresume" in means.index else 0.0 for k in METRIC_KEYS]
        plt.bar([i - width / 2 for i in x], b_vals, width, label="Baseline (prompt-only)")
        plt.bar([i + width / 2 for i in x], k_vals, width, label="KnapResume (knapsack+verifier)")
        plt.xticks(list(x), [k.replace("_", "\n") for k in METRIC_KEYS])
        plt.ylim(0, 1.05)
        plt.ylabel("Score (0-1; fabrication lower is better)")
        plt.title("Phase 6 — Baseline vs KnapResume (mean across pairs)")
        plt.legend()
        plt.tight_layout()
        plt.savefig(str(chart_path), bbox_inches="tight")
        plt.close()

    # Markdown report with per-pair table + means.
    md_path = out / "report.md"
    lines = [f"# {title}", ""]
    if frame.empty:
        lines.append("No evaluation results.")
    else:
        with pd.option_context("display.float_format", "{:.3f}".format):
            lines += ["## Per-pair results", "", frame.to_string(index=False), ""]
            lines += ["## Mean by arm", "", frame.groupby("arm")[list(METRIC_KEYS)].mean().to_string(), ""]
        wins = sum(int(r.get("knap_wins", 0) or 0) for r in results)
        lines += [f"KnapResume arm wins: {wins} metric-wins across {len(results)} pair(s).", "",
                  "![comparison chart](chart.png)", ""]
        lines += ["### Metric definitions",
                  "- keyword_match_rate: distinct required skills matched in any section / total required.",
                  "- ats_density: required-skill mentions per 100 words, saturated at 10/100w.",
                  "- fabrication_rate: unsupported claims / total claims (lower is better).",
                  "- knapsack_utilization: allocated chars / section capacity (baseline = 0, no allocator).", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    payload = {
        "report_md": str(md_path),
        "results_csv": str(csv_path),
        "chart_png": str(chart_path),
    }
    (out / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Evaluation report written to %s", str(out))
    return payload
