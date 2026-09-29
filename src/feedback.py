"""
src/feedback.py
Phase 5 — Weakest-Section Feedback Loop.

Turns scoring/allocation output into actionable gap feedback:

  - analyze_gaps(scored_facts, requirements): per-section required-skill
    coverage from score_facts() output ({section, utility, best_match}).
    A skill counts as matched in a section when some section fact claims it
    as best_match with utility >= MATCH_THRESHOLD. Weakest section = lowest
    coverage (tie-break: lowest summed utility).
  - build_feedback(profile_id, jd_id): allocation context + requirements ->
    {weakest_section, reasoning, sections, ...}.
  - create_feedback_run(profile_id, jd_id): persists a RunLog with the
    feedback JSON; rerun_feedback(run_id): rebuilds post-edit, persists a
    new RunLog, and diffs per-section coverage vs the previous run.

Pure (analyze/diff) + service (optional-session pattern) layers.
"""

from typing import Any, Dict, List, Optional

from src.logger import get_logger

logger = get_logger("feedback")

MATCH_THRESHOLD = 0.5
# Exact skill mentions (fuzzy) always count as covering the skill, even when
# the importance-weighted utility is small. score_facts() multiplies by
# importance (default 0.7), so thresholding raw utility would make
# default-importance skills nearly uncoverable.
FUZZY_MATCH_COVER = 0.8


def _covers(fact: Dict[str, Any], skill: str,
            match_threshold: float, alpha: float) -> bool:
    if str(fact.get("best_match", "")) != skill:
        return False
    if float(fact.get("fuzzy", 0.0)) >= FUZZY_MATCH_COVER:
        return True
    if "cosine" in fact and "fuzzy" in fact:
        blended = (alpha * float(fact["cosine"])
                   + (1.0 - alpha) * float(fact["fuzzy"]))
        return blended >= match_threshold
    return float(fact.get("utility", 0.0)) >= match_threshold


def analyze_gaps(
    scored_facts: List[Dict[str, Any]],
    requirements: List[Dict[str, Any]],
    match_threshold: float = MATCH_THRESHOLD,
    alpha: float = 0.7,
) -> Dict[str, Any]:
    """
    Per-section coverage of required skills. Returns {weakest_section,
    reasoning, sections: {section: {matched, total, missing, coverage,
    reasoning}}}. Sections with no required skills (or no requirements at
    all) report coverage 1.0 and never win "weakest" over a real gap.
    """
    required = [str(r.get("skill", "")) for r in (requirements or [])
                if str(r.get("category", "required")) == "required"]
    by_section: Dict[str, List[Dict[str, Any]]] = {}
    for f in scored_facts or []:
        section = str(f.get("section") or "other").strip() or "other"
        by_section.setdefault(section, []).append(f)
    sections: Dict[str, Any] = {}
    for section, facts in by_section.items():
        matched = [s for s in required
                   if any(_covers(g, s, match_threshold, alpha) for g in facts)]
        missing = [s for s in required if s not in matched]
        total = len(required)
        coverage = (len(matched) / total) if total else 1.0
        label = section.capitalize()
        if missing:
            reasoning = (f"Matched {len(matched)}/{total} required skills "
                         f"in {label}; missing: {', '.join(missing)}")
        elif total:
            reasoning = (f"Matched {total}/{total} required skills in {label}; "
                         f"no gaps")
        else:
            reasoning = f"No required skills to cover in {label}"
        sections[section] = {
            "matched": len(matched), "total": total, "missing": missing,
            "coverage": coverage, "reasoning": reasoning,
            "utility": sum(float(g.get("utility", 0.0)) for g in facts),
        }
    weakest: Optional[str] = None
    if sections:
        weakest = min(sections,
                      key=lambda s: (sections[s]["coverage"],
                                     sections[s]["utility"],
                                     s))
        # A clean sheet (every section fully covered) has no weakest.
        if all(v["coverage"] >= 1.0 for v in sections.values()):
            weakest = None
    reasoning = sections[weakest]["reasoning"] if weakest else "No gaps found"
    return {"weakest_section": weakest, "reasoning": reasoning,
            "sections": sections}


def build_feedback(
    profile_id: int,
    jd_id: int,
    session=None,
    capacities: Optional[Dict[str, int]] = None,
    match_threshold: float = MATCH_THRESHOLD,
) -> Dict[str, Any]:
    """
    Full gap analysis for a profile + JD. Returns the analyze_gaps() dict
    plus {profile_id, jd_id, role_type, total_utility, selected_count,
    dropped_count}. Raises ProfileNotFoundError / ValueError(JD) when missing.
    """
    from src.database import get_db_session
    from src.models import JDRequirement
    from src.tailor import build_allocation_context

    def _build(s):
        context = build_allocation_context(
            profile_id, jd_id, session=s, capacities=capacities)
        req_rows = (
            s.query(JDRequirement)
            .filter(JDRequirement.jd_id == jd_id)
            .order_by(JDRequirement.id)
            .all()
        )
        requirements = [{"skill": r.skill, "category": r.category,
                         "importance": r.importance} for r in req_rows]
        scored = ([{**f} for sec in context["sections"].values()
                   for f in sec["selected"]]
                  + [{**f} for sec in context["sections"].values()
                     for f in sec["dropped"]])
        gaps = analyze_gaps(scored, requirements,
                            match_threshold=match_threshold)
        logger.info("Feedback: profile=%d jd=%d weakest=%s",
                    profile_id, jd_id, gaps["weakest_section"])
        return {**gaps, "profile_id": profile_id, "jd_id": jd_id,
                "role_type": context["role_type"],
                "total_utility": context["total_utility"],
                "selected_count": len(context["selected_facts"]),
                "dropped_count": len(context["dropped_facts"])}

    if session is not None:
        return _build(session)
    with get_db_session() as s:
        return _build(s)


def ats_grade(coverage: float) -> str:
    """Letter grade from required-skill coverage: A >= .8, B >= .6, C >= .4."""
    if coverage >= 0.8:
        return "A"
    if coverage >= 0.6:
        return "B"
    if coverage >= 0.4:
        return "C"
    return "D"


def build_ats_checklist(
    feedback: Dict[str, Any],
    requirements: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Lightweight ATS checklist: grade + per-skill matched flags.

    Pure function over a feedback dict (sections with `missing` lists)
    and requirement rows. Required skills drive the grade; nice_to_have
    skills are listed for display only.
    """
    sections = (feedback or {}).get("sections", {}) or {}
    missing_union: set = set()
    for sec in sections.values():
        missing_union |= set(str(m) for m in (sec.get("missing", []) or []))
    items: List[Dict[str, Any]] = []
    matched_req = 0
    total_req = 0
    for r in requirements or []:
        skill = str(r.get("skill", ""))
        cat = str(r.get("category", "required"))
        matched = skill not in missing_union
        items.append({"skill": skill, "category": cat, "matched": matched})
        if cat == "required":
            total_req += 1
            matched_req += 1 if matched else 0
    coverage = (matched_req / total_req) if total_req else 1.0
    matched = [i["skill"] for i in items if i["category"] == "required" and i["matched"]]
    missing = [i["skill"] for i in items if i["category"] == "required" and not i["matched"]]
    return {
        "grade": ats_grade(coverage),
        "coverage": coverage,
        "matched": matched,
        "missing": missing,
        "items": items,
    }


def create_feedback_run(
    profile_id: int,
    jd_id: int,
    session=None,
    capacities: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Build feedback and persist it as a completed RunLog. Returns
    {run_id, feedback, role_type, total_utility}.
    """
    from src.database import get_db_session
    from src.models import RunLog

    def _save(s):
        from src.models import JDRequirement

        feedback = build_feedback(profile_id, jd_id, session=s,
                                  capacities=capacities)
        req_rows = (
            s.query(JDRequirement)
            .filter(JDRequirement.jd_id == jd_id)
            .order_by(JDRequirement.id)
            .all()
        )
        checklist = build_ats_checklist(
            feedback,
            [{"skill": r.skill, "category": r.category} for r in req_rows],
        )
        run = RunLog(profile_id=profile_id, jd_id=jd_id,
                     feedback={k: feedback[k] for k in
                               ("weakest_section", "reasoning", "sections")} | {"ats_checklist": checklist},
                     status="completed")
        s.add(run)
        s.flush()
        logger.info("Feedback run %d stored (weakest=%s)",
                    run.id, feedback["weakest_section"])
        return {"run_id": run.id, "feedback": feedback,
                "role_type": feedback["role_type"],
                "total_utility": feedback["total_utility"]}

    if session is not None:
        return _save(session)
    with get_db_session() as s:
        return _save(s)


def diff_feedback(
    previous: Dict[str, Any], current: Dict[str, Any]
) -> Dict[str, Any]:
    """Per-section coverage deltas between two feedback dicts."""
    prev_sections = (previous.get("feedback") or previous).get("sections", {})
    cur_sections = (current.get("feedback") or current).get("sections", {})
    diff: Dict[str, Any] = {}
    for section in sorted(set(prev_sections) | set(cur_sections)):
        prev = prev_sections.get(section, {})
        cur = cur_sections.get(section, {})
        prev_missing = set(prev.get("missing", []))
        cur_missing = set(cur.get("missing", []))
        diff[section] = {
            "prev_coverage": prev.get("coverage"),
            "new_coverage": cur.get("coverage"),
            "delta": ((cur.get("coverage") or 0.0)
                      - (prev.get("coverage") or 0.0)),
            "newly_matched": sorted(prev_missing - cur_missing),
            "newly_missing": sorted(cur_missing - prev_missing),
        }
    return diff


def rerun_feedback(run_id: int, session=None,
                   capacities: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """
    Rebuild feedback for a previous run's profile + JD (post-edit), persist
    a new RunLog, and diff coverage vs the previous run. Returns
    {run_id, prev_run_id, feedback, diff}. Raises ValueError on missing run.
    """
    from src.database import get_db_session
    from src.models import RunLog

    def _rerun(s):
        prev = s.query(RunLog).filter(RunLog.id == run_id).first()
        if prev is None:
            raise ValueError(f"RunLog {run_id} not found.")
        result = create_feedback_run(prev.profile_id, prev.jd_id,
                                     session=s, capacities=capacities)
        result["prev_run_id"] = run_id
        result["diff"] = diff_feedback(
            {"feedback": prev.feedback or {}}, result)
        return result

    if session is not None:
        return _rerun(session)
    with get_db_session() as s:
        return _rerun(s)
