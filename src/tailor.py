"""
src/tailor.py
Multi-provider AI tailoring engine.
Supports:
  - Anthropic Claude  (any model string, e.g. claude-opus-4-5, claude-sonnet-4-6)
  - Google Gemini     (gemini-2.5-flash, gemini-2.5-flash-lite, gemini-2.5-pro)

Provider + model + API key are passed in at call time so the web UI can
accept them from the user. Falls back to environment variables for local/CLI use.
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from src.logger import get_logger

logger = get_logger("tailor")

PROVIDER = Literal["claude", "gemini"]


# ── Formatting instructions ───────────────────────────────────────────────────

def _load_instructions() -> str:
    instruct_path = Path(__file__).parent.parent / "instruct.md"
    if instruct_path.exists():
        return instruct_path.read_text(encoding="utf-8")
    return "Follow standard ATS-friendly resume and cover letter formatting."


# ── Prompt builders (shared across providers) ────────────────────────────────

def _resume_system_prompt(instructions: str) -> str:
    return f"""You are an expert resume writer and ATS optimization specialist.

FORMATTING INSTRUCTIONS (follow exactly):
{instructions}

ABSOLUTE RULES — NEVER VIOLATE:
1. You may ONLY use information that exists in the candidate's original resume.
2. Do NOT invent, embellish, or assume any experience, skills, metrics, or facts.
3. You MAY reorder, reword, and emphasize existing content to better match the job.
4. You MAY mirror keywords and phrases from the job description IF they accurately
   describe the candidate's existing experience.
5. If the candidate lacks a required skill, do NOT add it. Leave it absent.
6. Output ONLY the tailored resume text — no commentary, no preamble, no markdown fences."""


def _resume_user_prompt(resume_text: str, job_description: str, web_context: str,
                        source_note: str = "") -> str:
    note = f"\n{source_note}\n" if source_note else ""
    return f"""Tailor the following resume for the job description below.
{note}
=== ORIGINAL RESUME ===
{resume_text}

=== JOB DESCRIPTION ===
{job_description}

=== ADDITIONAL COMPANY/ROLE CONTEXT (for reference only) ===
{web_context or 'None available.'}

Instructions:
- Rewrite the resume to highlight the most relevant experience for this specific role.
- Use keywords from the job description where they truthfully apply to the candidate.
- Optimise for ATS parsing.
- Do NOT add any experience, skills, or achievements not present in the original resume.
- Output the full tailored resume text only."""


def _cover_system_prompt(instructions: str) -> str:
    return f"""You are an expert cover letter writer.

FORMATTING INSTRUCTIONS (follow exactly):
{instructions}

ABSOLUTE RULES — NEVER VIOLATE:
1. Only reference experience, achievements, and skills present in the candidate's resume.
2. Do NOT invent stories, metrics, or experiences.
3. Use the web context ONLY to reference the company's mission/values — do not fabricate
   insider knowledge.
4. Output ONLY the cover letter text — no commentary, no preamble, no markdown fences."""


def _cover_user_prompt(
    resume_text: str, job_description: str, tailored_resume: str, web_context: str
) -> str:
    return f"""Write a tailored cover letter for the following job using only the
candidate's actual experience from their resume.

=== ORIGINAL RESUME ===
{resume_text}

=== TAILORED RESUME (highlights to emphasise) ===
{tailored_resume}

=== JOB DESCRIPTION ===
{job_description}

=== COMPANY/ROLE CONTEXT (use for company references only) ===
{web_context or 'None available.'}

Instructions:
- Write a compelling, professional cover letter for this specific role.
- Reference real experience from the resume that matches the job requirements.
- Keep to 1 page / 4 paragraphs as per formatting instructions.
- Do NOT fabricate any experience, metrics, or claims.
- Output the cover letter text only."""


# ── Claude caller ─────────────────────────────────────────────────────────────

def _call_claude(
    system: str,
    user: str,
    api_key: str,
    model: str,
    max_tokens: int = 4096,
) -> str:
    start = time.time()
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    result = message.content[0].text.strip()
    logger.info("Claude call complete: model=%s chars_out=%d %.1fs",
                model, len(result), time.time() - start)
    return result


# ── Gemini caller ─────────────────────────────────────────────────────────────

def _call_gemini(
    system: str,
    user: str,
    api_key: str,
    model: str,
    max_tokens: int = 4096,
) -> str:
    """
    Calls Gemini via the google-generativeai SDK.
    System prompt is prepended to the user message since Gemini's
    generateContent supports system_instruction natively in newer SDK versions.
    """
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError(
            "google-generativeai is not installed. "
            "Run: pip install google-generativeai"
        )

    genai.configure(api_key=api_key)

    generation_config = genai.GenerationConfig(max_output_tokens=max_tokens)

    gemini_model = genai.GenerativeModel(
        model_name=model,
        system_instruction=system,
        generation_config=generation_config,
    )

    start = time.time()
    response = gemini_model.generate_content(user)
    result = response.text.strip()
    logger.info("Gemini call complete: model=%s chars_out=%d %.1fs",
                model, len(result), time.time() - start)
    return result


# ── Unified dispatcher ────────────────────────────────────────────────────────

def _call_ai(
    system: str,
    user: str,
    provider: str,
    model: str,
    api_key: str,
    max_tokens: int = 4096,
) -> str:
    if provider == "claude":
        return _call_claude(system, user, api_key, model, max_tokens)
    elif provider == "gemini":
        return _call_gemini(system, user, api_key, model, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider!r}. Use 'claude' or 'gemini'.")


# ── Public API ────────────────────────────────────────────────────────────────

def tailor_resume(
    resume_text: str,
    job_description: str,
    web_context: str = "",
    provider: str = "claude",
    model: str = "claude-opus-4-5",
    api_key: str = "",
    source_note: str = "",
) -> str:
    """
    Tailor the resume to the job description.
    Returns the tailored resume as plain text.

    provider: "claude" or "gemini"
    model:    e.g. "claude-opus-4-5", "claude-sonnet-4-6",
                   "gemini-2.5-flash", "gemini-2.5-flash-lite"
    api_key:  if blank, falls back to ANTHROPIC_API_KEY / GEMINI_API_KEY env vars
    source_note: optional preface describing the resume source (Stage 3.3
                 passes an allocation note; "" keeps legacy prompts byte-identical).
    """
    if not api_key:
        api_key = (
            os.environ.get("ANTHROPIC_API_KEY", "")
            if provider == "claude"
            else os.environ.get("GEMINI_API_KEY", "")
        )
    if not api_key:
        raise ValueError(
            f"No API key provided for {provider}. "
            "Pass api_key= or set the environment variable."
        )

    instructions = _load_instructions()
    system = _resume_system_prompt(instructions)
    user = _resume_user_prompt(resume_text, job_description, web_context,
                               source_note=source_note)
    logger.info("Tailoring resume: provider=%s model=%s resume_chars=%d jd_chars=%d",
                provider, model, len(resume_text), len(job_description))
    return _call_ai(system, user, provider, model, api_key, max_tokens=4096)


def generate_cover_letter(
    resume_text: str,
    job_description: str,
    tailored_resume: str,
    web_context: str = "",
    provider: str = "claude",
    model: str = "claude-opus-4-5",
    api_key: str = "",
) -> str:
    """
    Generate a tailored cover letter.
    Returns the cover letter as plain text.
    """
    if not api_key:
        api_key = (
            os.environ.get("ANTHROPIC_API_KEY", "")
            if provider == "claude"
            else os.environ.get("GEMINI_API_KEY", "")
        )
    if not api_key:
        raise ValueError(
            f"No API key provided for {provider}. "
            "Pass api_key= or set the environment variable."
        )

    instructions = _load_instructions()
    system = _cover_system_prompt(instructions)
    user = _cover_user_prompt(resume_text, job_description, tailored_resume, web_context)
    logger.info("Generating cover letter: provider=%s model=%s", provider, model)
    return _call_ai(system, user, provider, model, api_key, max_tokens=2048)


# ── Stage 3.3 — Orchestration: score → allocate → LLM ─────────────────────────
# The LLM never sees the full profile. build_allocation_context() scores every
# fact against the JD requirements and knapsack-selects the optimal subset per
# section; tailor_resume_with_allocation() feeds ONLY that subset to the LLM
# (physical constraint) plus an explicit allocation note (prompt constraint).

ALLOCATION_SOURCE_NOTE = (
    "SOURCE NOTE: the resume below is a mathematically pre-selected optimal "
    "subset of the candidate's profile (0/1 knapsack allocation over semantic "
    "relevance scores). Rewrite ONLY these facts — do not restore omitted "
    "content and do not introduce anything not listed here. "
    "Each input fact carries an ID like [F3]: end EVERY output bullet with "
    "the ID(s) supporting it (e.g. '- Led migration [F7]'). A bullet with no "
    "supporting fact ID is a fabrication — never emit one."
)


def build_allocation_context(
    profile_id: int,
    jd_id: int,
    session=None,
    capacities: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Score a profile's facts against a JD's requirements and allocate the
    optimal subset per section.

    Returns {profile_id, jd_id, company, job_title, role_type,
    sections: {section: allocate_section(...)}, selected_facts: [...],
    dropped_facts: [...], total_utility}. Each selected/dropped fact dict
    carries id/section/content/is_mandatory/utility/best_match.
    Raises ProfileNotFoundError (profile) or ValueError (JD) when missing.
    """
    from src.allocator import allocate_facts
    from src.database import get_db_session
    from src.models import JD as JDModel, JDRequirement, ProfileFact
    from src.profile_service import ProfileNotFoundError, _validate_profile_id
    from src.scoring import score_facts

    def _build(s):
        _validate_profile_id(s, profile_id)
        jd = s.query(JDModel).filter(JDModel.id == jd_id).first()
        if jd is None:
            raise ValueError(f"JD {jd_id} not found.")
        fact_rows = (
            s.query(ProfileFact)
            .filter(ProfileFact.profile_id == profile_id)
            .order_by(ProfileFact.id)
            .all()
        )
        req_rows = (
            s.query(JDRequirement)
            .filter(JDRequirement.jd_id == jd_id)
            .order_by(JDRequirement.id)
            .all()
        )
        facts = [{
            "id": f.id, "section": f.section, "content": f.content,
            "is_mandatory": f.is_mandatory,
            "embedding": f.get_embedding(),
        } for f in fact_rows]
        requirements = [{
            "skill": r.skill, "category": r.category,
            "importance": r.importance, "embedding": r.get_embedding(),
        } for r in req_rows]
        scored = score_facts(facts, requirements)
        for fact_dict, s_ in zip(facts, scored):
            fact_dict["utility"] = s_["utility"]
            fact_dict["best_match"] = s_["best_match"]
            fact_dict["cosine"] = s_["cosine"]
            fact_dict["fuzzy"] = s_["fuzzy"]
        sections = allocate_facts(facts, capacities=capacities)
        selected = [f for sec in sections.values() for f in sec["selected"]]
        dropped = [f for sec in sections.values() for f in sec["dropped"]]
        total_utility = sum(sec["total_utility"] for sec in sections.values())
        logger.info("Allocation context: profile=%d jd=%d selected=%d dropped=%d "
                    "utility=%.3f", profile_id, jd_id,
                    len(selected), len(dropped), total_utility)
        return {
            "profile_id": profile_id, "jd_id": jd_id,
            "company": jd.company, "job_title": jd.job_title,
            "role_type": jd.role_type,
            "sections": sections,
            "selected_facts": selected,
            "dropped_facts": dropped,
            "total_utility": total_utility,
        }

    if session is not None:
        return _build(session)
    with get_db_session() as s:
        return _build(s)


def render_allocated_resume_text(
    selected_facts: List[Dict[str, Any]],
    sections_order: Optional[List[str]] = None,
    with_ids: bool = True,
) -> str:
    """
    Render allocated facts grouped by section as prompt-ready resume text.
    With with_ids (default), each bullet is prefixed `[F<id>]` so the LLM
    can cite supporting fact IDs per bullet (Stage 4.1); facts without an
    id render as plain bullets.
    """
    groups: Dict[str, List[str]] = {}
    for f in selected_facts:
        section = str(f.get("section") or "other")
        content = str(f.get("content", ""))
        fid = f.get("id")
        bullet = f"[F{fid}] {content}" if with_ids and fid is not None else content
        groups.setdefault(section, []).append(bullet)
    order = sections_order or sorted(groups.keys())
    ordered = order + [s for s in groups if s not in order]
    blocks = []
    for section in ordered:
        lines = groups.get(section, [])
        if lines:
            blocks.append(f"{section.upper()}\n" + "\n".join(f"- {ln}" for ln in lines))
    return "\n\n".join(blocks)


def tailor_resume_with_allocation(
    profile_id: int,
    jd_id: int,
    web_context: str = "",
    provider: str = "claude",
    model: str = "claude-opus-4-5",
    api_key: str = "",
    session=None,
    capacities: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Full Stage 3.3 pipeline: allocate the optimal fact subset, then tailor
    with the LLM constrained to that subset. Returns
    {tailored_text, allocation} where allocation is the
    build_allocation_context() dict (selected/dropped facts, utilities).
    """
    from src.models import JD as JDModel

    context = build_allocation_context(
        profile_id, jd_id, session=session, capacities=capacities)
    if not context["selected_facts"]:
        raise ValueError(
            f"No facts selected for profile {profile_id} (empty profile?).")

    def _run(s):
        jd = s.query(JDModel).filter(JDModel.id == jd_id).first()
        jd_text = jd.raw_text if jd is not None else ""
        allocated_text = render_allocated_resume_text(context["selected_facts"])
        tailored = tailor_resume(
            allocated_text, jd_text, web_context,
            provider=provider, model=model, api_key=api_key,
            source_note=ALLOCATION_SOURCE_NOTE,
        )
        return {"tailored_text": tailored, "allocation": context}

    if session is not None:
        return _run(session)
    from src.database import get_db_session
    with get_db_session() as s:
        return _run(s)
