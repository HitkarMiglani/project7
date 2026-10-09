# KnapResume — Project Journey & Decision Log

> **Tracking Document:** `Journey.md`  
> **Purpose:** Serves as the continuous, reflective engineering log for the KnapResume project. After **every iteration or completed stage**, either the Human or Agent must log the reasoning, architectural decisions, file changes, trade-offs, and outcomes.  
> **Paired Document:** `progress.md` (maintains the phase/stage checklist and completion status).

---

## 📝 Rules for Updating `Journey.md`

1. **Mandatory Logging:** Every time a stage or significant iteration is executed, append a new journal entry using the **Standard Iteration Template** below.
2. **Explain "Why" over "What":** Focus heavily on engineering rationale, why alternative approaches were rejected, and how edge cases were addressed.
3. **Keep Accurate Chronology:** Add new entries to the top or sequentially in the **Chronological Iteration Entries** section.
4. **Synchronize with `progress.md`:** Ensure status updates in `progress.md` correspond directly with the completed entry here.

---

## 📋 Standard Iteration Entry Template

```markdown
### [YYYY-MM-DD] Iteration Entry: Phase X — Stage X.X (<Stage Title>)
- **Author:** [Agent / Human / Collaborative]
- **Status:** [Completed / In Progress / Blocked]

#### 1. Objective & Scope
<What specific problem or task was addressed in this iteration?>

#### 2. Key Decisions & Technical Reasoning
- **Decision:** <Choice made>
  - **Reasoning:** <Why this choice was made>
  - **Alternatives Considered & Rejected:** <Why not the alternatives?>

#### 3. Code & Configuration Changes
- `<file_path>`: <Concise description of changes made>

#### 4. Edge Cases, Failures & Mitigations
- <Any hurdles encountered, unexpected model behavior, concurrency or dependency issues, and how they were solved>

#### 5. Verification & Test Results
- <Test commands executed, output checks, benchmark numbers, or pass/fail results>

#### 6. Next Steps
- <Immediate task to be picked up next>
```

---

## 🏛️ Architectural Decision Log Summary (ADR Reference)

| ADR ID | Topic | Decision | Core Rationale |
|---|---|---|---|
| **ADR-001** | Database Choice | SQLite with WAL mode (`PRAGMA journal_mode=WAL`) | Zero setup, single-user footprint (<100s rows), strong ACID consistency, prevents locking across threads. |
| **ADR-002** | Web Framework | Retain Flask + `threading.Thread` | Existing 132-line server is minimal and working. FastAPI adds async complexity without need (no WebSocket required). |
| **ADR-003** | NLP Pipeline | KeyBERT only (drop spaCy) | KeyBERT handles keyword extraction cleanly; `sentence-transformers` handles role classification. Saves ~15MB. |
| **ADR-004** | Verification Model | Hybrid Cosine Pre-screen + Small NLI (`nli-MiniLM2-L6-H768`) | High throughput via fast cosine; only borderline claims ($0.60 < s < 0.85$) invoke 90MB NLI model. |
| **ADR-005** | PDF Generation | Retain ReportLab flowables | 392 lines of working flowable layout. Avoids WeasyPrint C-dependencies (Cairo/Pango). |
| **ADR-006** | Vector Storage | Binary float32 buffer (`tobytes()` / `frombuffer()`) | Safer, faster, and more portable than Python `pickle` objects in SQLite BLOBs. |
| **ADR-007** | External Logging | Drop Notion MCP in favor of pure SQLite | Eliminates external Node.js server dependency (`@notionhq/notion-mcp-server`), removes third-party token setup, keeps all run logs local & private. |
| **ADR-008** | Quality Assurance | Phase-level test & build gate | Execute full test suite (`pytest -v`) and resolve all regressions at the conclusion of each full phase before transitioning to the next phase. |

---

## 📖 Chronological Iteration Entries

---

### [2026-10-04] Iteration Entry: Version v1.1 Planning (P0+P1+P2 — Single-Doc Ingestion & Fact Quality)
- **Author:** Agent + Human
- **Status:** Planned (build not started)

#### 1. Objective & Scope
User reported: ingestion pulls irrelevant content; fact add/modify is tedious; claimed facts badly formatted. Prior research confirmed root causes (ALL-CAPS/`|` over-match, append-only ingest, free-text sections, `instruct.md` humanizer misused as resume prompt, legacy `/api/tailor` bypass). User chose Google Doc (Docs API) as single user source-of-truth + keep full P2 bulk tools. Plan v1.1 as P0 (prompt/format) + P1 (GDoc sync) + P2 (bulk curation).

#### 2. Key Decisions & Technical Reasoning
- **Decision:** v1.1 (not v2) — P0+P1+P2 as patch-track; v2 LaTeX roadmap untouched.
  - **Reasoning:** Fixes correctness/UX of current pipeline without schema or renderer change.
  - **Alternatives Considered & Rejected:** GCS-bucket PDF/DOCX (keeps pdfplumber noise) / Drive export TXT (loses headings) — rejected; Docs API structuralElements preferred. Doc-only editing without P2 — rejected per user (keep P2 for cleanup/offline).
- **Decision:** P0 first (no GCP dependency), then P1 SA readonly + share-to-SA, then P2 additive bulk APIs.
  - **Reasoning:** P0 unblocks formatting even if GCP setup stalls; P1 makes editing lazy; P2 pays off in one 50-fact cleanup.
- **Decision:** No DB migration; `gdoc_rev` cached in `profiles.sections`; last-write-wins + diff preview on Doc/UI divergence.
  - **Reasoning:** Keeps rollback to route-disable + prompt-loader revert.

#### 3. Code & Configuration Changes
- `progress.md`: dashboard → v1.1 active track; new `## 🚀 Version v1.1 Roadmap` (v1.1.0/v1.1.1/v1.1.2 stages + gates); milestone row.
- `VERSIONS.md`: new `## Version 1.1 (Planned)` scope + file inventory + gates.
- `Journey.md`: this entry.
- No runtime code changed.

#### 4. Edge Cases, Failures & Mitigations
- *SA 403 permission:* setup doc must stress share-to-SA email; preview endpoint surfaces error pre-sync.
- *Offline Doc:* `gdoc_rev` cache fallback; UI read-only when unreachable.
- *Doc/UI divergence:* hash diff preview + last-write-wins.

#### 5. Verification & Test Results
- Planning only. Gates defined: P0 claims roundtrip, P1 live-Doc sync, P2 50-fact bulk — all `pytest -q` green + `py_compile` clean before closing each stage.

#### 6. Next Steps
- Start **v1.1.0a**: `resume_format.md` + `tailor.py` prompt swap + allocation routing fix.

---

### [2026-09-29] Iteration Entry: Phase 7 Complete (7.1 ATS Checklist, 7.2 Verify, 7.3 Smoke + Docs)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Execute all of Phase 7: lightweight ATS checklist in API + UI (7.1), PDF/persistence verification (7.2), offline end-to-end smoke test + README docs with phase gate (7.3).

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Checklist builder lives in `src/feedback.py` (stored on `RunLog.feedback` at creation), re-exported from `src/evaluation.py`.
  - **Reasoning:** Chat timelines render from stored feedback, so persisting the checklist once makes it appear everywhere with no extra queries. `evaluation.py` importing it keeps one source of truth (feedback already owns the sections shape; lazy imports avoid cycles).
- **Decision:** UI `scorecardHTML` is checklist-first (grade + global ✓/✕ chips + per-section bars), section-average fallback otherwise.
  - **Reasoning:** Server grade uses the required-skill union; the old client grade averaged section coverages (same required set counted per section). Also fixed a latent crash where the old code called `.map` on the numeric `matched` count.
- **Decision:** 7.2 verified with zero code changes (prior PDF overhaul + tailor-run persistence already cover it); 7.3 smoke runs fully offline with cosine-only verification.
  - **Reasoning:** Re-running 27 targeted tests proves the DoD without churning stable code; the smoke test skips only live LLM calls (the one non-deterministic step).

#### 3. Code & Configuration Changes
- `src/feedback.py`: Added `ats_grade`/`build_ats_checklist`; `create_feedback_run` persists `ats_checklist` in stored feedback.
- `src/evaluation.py`: Re-exports checklist builder; `get_ats_checklist()` unchanged in behavior.
- `app.py`: `POST /api/runs`, `POST /api/runs/<id>/rerun`, `GET /api/runs/<id>` return `ats_checklist`.
- `docs/index.html`: Checklist-first `scorecardHTML` + crash fix.
- `tests/test_feedback.py`: +3 checklist tests; `tests/test_e2e_smoke.py`: created (full offline path).
- `README.md`: ATS checklist, eval outputs, `phase6-batch`/`phase6-eval` commands, status.
- `progress.md`: Phase 7 all `[x]`, dashboard → 95%.

#### 4. Edge Cases, Failures & Mitigations
- *Checklist/grade duplication risk between `feedback.py` and `evaluation.py`:*
  - *Mitigation:* Single implementation in `feedback.py`, imported by `evaluation.py`.
- *GET run for tailor-kind rows lacking profile/JD links:*
  - *Mitigation:* Checklist attached best-effort (try/except ValueError), payload always returns.

#### 5. Verification & Test Results
- `pytest tests/test_feedback.py tests/test_evaluation.py`: **20 passed**.
- Targeted 7.2 re-run (pdf + tailor-runs + pipeline-api + chats): **27 passed**.
- `pytest tests/test_e2e_smoke.py`: **1 passed**.
- Phase 7 gate — `pytest -q` full suite: **204 passed**; `py_compile` clean on `app.py`, `main.py`, `src/evaluation.py`, `src/feedback.py`.

#### 6. Next Steps
- Remaining backlog: **Stage 6.1** fixture dataset + live benchmark run → root `Evaluation_Report.md` from real data (needs LLM cost decision).
- Optional v2 roadmap (LaTeX engine, ATS valuator, improver loop) per `progress.md`.

---

### [2026-09-29] Iteration Entry: Phase 6 Stages 6.2–6.4 (Metrics, Benchmark, Report)
- **Author:** Agent
- **Status:** Completed (code; live benchmark run pending)

#### 1. Objective & Scope
Build the remaining Phase 6 harness code (6.2 metric pipeline, 6.3 baseline-vs-knap comparison, 6.4 tables/charts/report) as user requested, offline-testable with no LLM calls. Leave 6.1 fixtures + live run + root `Evaluation_Report.md` for next steps.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** New `src/evaluation.py` with four deterministic 0–1 metrics (keyword union match, ATS mentions/100w saturated at 10, fabrication unsupported/total, utilization weight/capacity; baseline utilization = 0 by construction).
  - **Reasoning:** Metrics must be computable from existing artifacts (feedback sections, tailored text, claim states, allocation weights) with no new models. Union-match avoids double-counting the same required skill across sections.
- **Decision:** Pure `evaluate_texts()` + injectable `evaluate_profile_jd()` (tailor/verify callables) instead of hardwiring LLM calls.
  - **Reasoning:** Keeps the 7 new tests offline and fast; the CLI injects real `tailor_resume`/`tailor_resume_with_allocation`/`verify_claims` for live runs.
- **Decision:** `save_report()` (pandas CSV + matplotlib Agg grouped bars + markdown) + new `main.py phase6-eval` CLI for one profile+JD live comparison.
  - **Reasoning:** Closes the whole pipeline in CLI as requested; Agg backend works headless on Windows.

#### 3. Code & Configuration Changes
- `src/evaluation.py`: Created (metrics, compare, DB/LLM wiring, reporting).
- `tests/test_evaluation.py`: Created (7 tests: metric units, fabrication win, direction flags, report artifacts).
- `main.py`: Added `phase6-eval` command (live both-arms + `save_report`).
- `progress.md`: Stages 6.2–6.4 `[x]`; dashboard → 90%, 3/4; milestone row added.

#### 4. Edge Cases, Failures & Mitigations
- *Chart helper used `means["baseline"]` (column lookup) instead of row lookup:*
  - *Mitigation:* Switched to `means.loc["baseline", k]`; all 7 eval tests green.
- *No fixtures (6.1) to benchmark against:*
  - *Mitigation:* Harness operates on any persisted profile+JD; no synthetic fixtures invented.

#### 5. Verification & Test Results
- `pytest tests/test_evaluation.py tests/test_phase6_batch_cli.py -q`: **14 passed**.
- `pytest -q` (full suite): **200 passed**, 0 failures.
- `py_compile` clean on `main.py`, `src/evaluation.py`, `tests/test_evaluation.py`.

#### 6. Next Steps
- Build **Stage 6.1** fixture dataset (10–15 profile/JD pairs).
- Run live `phase6-eval` / `phase6-batch` (needs LLM cost decision) and publish root `Evaluation_Report.md` from real data.

---

### [2026-09-29] Iteration Entry: Phase 6 CLI Output Decision (PDF Kept, No Text)
- **Author:** Agent & Human Collaborative
- **Status:** Completed

#### 1. Objective & Scope
Lock the `phase6-batch` output contract per user direction: keep PDF outputs, no tailored-text files. Revert the interim text-only draft (`.md` saves, `text_root/`, `resume_text_path`) back to the PDF pipeline so the CLI designs the whole pipeline end-to-end with PDFs.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** `phase6-batch` outputs `run_root/pdf/*.pdf` + `run_root/reports/` only; `RunLog.resume_pdf_path`/`cover_pdf_path` populated, no text paths.
  - **Reasoning:** User explicitly chose "keep the pdf no text". PDFs are the Phase 7-facing contract and the existing `RunLog` schema already carries PDF paths (nullable but populated in practice).
  - **Alternatives Considered & Rejected:** Text-only `.md` outputs (implemented as a draft per earlier Q&A, then reverted — avoids a second output contract and keeps verification on the shipped artifact).

#### 3. Code & Configuration Changes
- `main.py`: Restored `pdf` stage (`generate_resume_pdf`/`generate_cover_letter_pdf`, `resume_pdf_ms`/`cover_pdf_ms` timings), `pdf_failed` bottleneck path (`pdf_generation`/`pdf_generation_slow`), PDF report outputs; removed `text_root`/`save_text` draft.
- `progress.md`: Dashboard → Phase 6 🔄 In Progress / 87%; Stages 6.2 + 6.3 marked `[/]` (CLI foundation), 6.1 + 6.4 still `[ ]`; added decision milestone row.
- `Journey.md`: This entry.

#### 4. Edge Cases, Failures & Mitigations
- *Interim text-only edit broke the `pdf_failed` test contract (`test_diagnose_pdf_generation_failure_priority`):*
  - *Mitigation:* Restored `pdf_failed` param and PDF bottleneck branches; all 7 CLI helper tests green again.

#### 5. Verification & Test Results
- `python -m py_compile main.py`: clean.
- `pytest tests/test_phase6_batch_cli.py -q`: **7 passed**.
- `pytest -q` (full suite): **193 passed**, 0 failures.

#### 6. Next Steps
- Proceed with **Phase 6 — Stage 6.1** fixture dataset (10–15 profile/JD pairs).
- Then formalize Stage 6.2 four-metric definitions and Stage 6.3 baseline arm before Stage 6.4 `Evaluation_Report.md`.

---

### [2026-09-29] Iteration Entry: Phase 6 CLI Batch Pipeline (Folder JD PDFs)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Start Phase 6 execution from the CLI by adding a real batch pipeline that accepts a folder containing one or many JD PDFs, runs the full generation flow against an existing profile, and emits per-run bottleneck diagnostics and reports. Explicitly avoid synthetic/dummy profile creation by requiring an existing profile id and enforcing a minimum profile fact threshold.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Add a new command (`phase6-batch`) instead of overloading single-run `tailor`.
  - **Reasoning:** Keeps backward compatibility for existing single-run usage while introducing a benchmark-style path with its own controls (batch sizing, sleep policies, report outputs).
  - **Alternatives Considered & Rejected:** Replacing `tailor` directly (too risky for existing workflows and manual use cases).
- **Decision:** Wire the command to full pipeline modules: `persist_jd` → `tailor_resume_with_allocation` → `extract_claims` + `verify_claims` + `sanitize_text` → `build_feedback` → PDF generation.
  - **Reasoning:** Phase 6 needs instrumentation of allocation/verification quality, not prompt-only output.
- **Decision:** Add deterministic bottleneck categorization (`profile_facts_low`, `scoring_alignment`, `verification_risk`, `pdf_generation`, plus latency classes) and persist this in run feedback/report artifacts.
  - **Reasoning:** User asked for clear root-cause diagnosis per run, not just pass/fail.
- **Decision:** Implement batch + linear sleep controls (`--batch-size`, `--linear-sleep-base`, `--linear-sleep-step`, `--batch-sleep`).
  - **Reasoning:** Gives explicit throttle knobs for provider limits/cost pacing while preserving sequential determinism.

#### 3. Code & Configuration Changes
- `main.py`: Added `phase6-batch` command, helper diagnostics/report writers, profile validation gate, and RunLog/Claim persistence for each run.
- `tests/test_phase6_batch_cli.py`: Added helper tests for PDF discovery, linear sleep calculation, and bottleneck classification priority.
- `progress.md`: Added milestone entry for this Phase 6 CLI pipeline implementation.

#### 4. Edge Cases, Failures & Mitigations
- *Accidental patch markers in rewritten file (`+` at line starts):*
  - *Mitigation:* stripped markers and revalidated syntax/tests.
- *ORM typing ambiguity for run ids in static analysis:*
  - *Mitigation:* resolved ids via `to_dict()` payload before passing to `record_claims`.
- *Low-signal or non-JD PDFs could produce junk runs:*
  - *Mitigation:* enforce minimum extracted JD text length and hard-stop sparse profile usage via `--min-profile-facts`.

#### 5. Verification & Test Results
- `python -m py_compile main.py tests/test_phase6_batch_cli.py`: clean.
- `pytest tests/test_phase6_batch_cli.py -q`: **7 passed**.
- Editor diagnostics: no errors in `main.py` and new test module.

#### 6. Next Steps
- Proceed with **Phase 6 — Stage 6.1** fixture dataset curation using real user-supplied profile/JD PDFs.
- Use `phase6-batch` runs to collect Stage 6.2 metrics and identify dominant bottleneck classes before Stage 6.3 comparative benchmark.

---

### [2026-09-29] Iteration Entry: Light ATS-Clean UI/UX Redesign + Privacy Policy Refresh
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Full UI/UX pass over the 3-view SPA (`docs/index.html`) in a user-chosen **Light ATS-clean** direction, plus a rewrite of the stale `docs/privacy.html`. Audit found: flat action hierarchy (5 equal composer buttons), the Verified/Inferred/Unsupported differentiator invisible in the UI, facts as one unfilterable list with delete-only curation, no ATS grade/checklist, error-banner-only feedback, and accessibility gaps (low-contrast dim text, icon-only deletes, no labels/focus rings/modals semantics).

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Keep the single-file SPA; restyle to light tokens (`--bg #f4f6f9`, ink `#16202e`, accent `#1a56db`, ok/warn/err triple) with Fraunces + Inter, instead of splitting into multiple pages.
  - **Reasoning:** `app.py` serves one template string with `__ANTHROPIC_KEY__` placeholder replacement; GitHub Pages needs a zero-build artifact (repo forbids Node); `test_pipeline_api.py` pins `/` serving the whole UI. Multi-page was explicitly evaluated and rejected for now — hash routing later if deep-linking is wanted.
  - **Alternatives Considered & Rejected:** Multi-page split (duplicates placeholder logic, breaks served-UI test, adds reload state loss); dark-theme evolution (user chose light ATS-clean).
- **Decision:** One primary action per surface — `▶ Run analysis` becomes `.btn-primary`, the rest secondary; ATS scorecard (A–D grade + avg coverage + per-section ✓ matched / ✕ missing chips) rendered inside analysis bubbles.
  - **Reasoning:** Scorecard reuses existing `feedback.sections` JSON — zero backend change for a Phase 7.1-shaped ATS checklist preview.
- **Decision:** Facts gain section filter chips with counts, inline edit/save/cancel, and ☆→★ mandatory toggle (not just ★ display + delete).
  - **Reasoning:** Mandatory pinning is the knapsack's most user-visible guarantee; making it toggleable in-place closes the curate→allocate→verify loop without leaving the view.
- **Decision:** Privacy policy rewritten to actual data flows: local SQLite/`outputs/`/`.env` table, Claude/Gemini-only providers, Brave Search optional context, no Notion/mobile/ads/OpenAI.
  - **Reasoning:** Old page predated the Stage 0.2 Notion prune and described builds that don't exist; inaccurate privacy text is worse than none.

#### 3. Code & Configuration Changes
- `docs/index.html`: Rebuilt (light design system, how-it-works strip, verification legend, stepper descriptions, labeled inputs, focus-visible rings, `role=dialog` modals with Esc close, `/` focuses chat search, toasts, labeled 5-step tailor progress, allocation inspector with utility + char-budget, scorecard bubbles, thread gap/✓ flags, keyboard-operable cards, `prefers-reduced-motion`).
- `docs/privacy.html`: Rebranded to KnapResume, light theme, accurate local-vs-sent data map, effective date 2026-09-29.
- `progress.md`: Logged milestones (phase boxes untouched).
- No backend changes; all API wiring and test-pin strings preserved (`Knapsack resume`, `/api/runs`, `/api/allocate`, `attach-veil`/`attach-jd-file`/`attach-jd-existing`, no `prompt(` substring, no `Notion`, server key placeholders).

#### 4. Edge Cases, Failures & Mitigations
- *Served-UI test bans the `prompt(` substring (not just the call):* any comment or copy containing it fails the suite.
  - *Mitigation:* Verified `prompt(` absent via byte check before running tests; used `confirm()` only where pre-existing.
- *`python -m py_compile src/*.py` fails on Windows (glob not expanded by the shell):*
  - *Mitigation:* Compiled `app.py`/`main.py` directly plus per-file loop over `src/*.py` — all clean.

#### 5. Verification & Test Results
- Byte-check pins: `prompt(` absent, `Notion` absent, all required markers present.
- `python -m pytest tests/test_pipeline_api.py tests/test_chats.py tests/test_tailor_runs.py -q`: **19 passed**.
- `python -m pytest -q` (full suite): **186 passed**, 0 failures.
- `py_compile` clean on `app.py`, `main.py`, all `src/*.py`.

#### 6. Next Steps
- Proceed to **Phase 6 — Stage 6.1**: fixture dataset (10–15 profile/JD pairs); Stage 6.3 live-LLM benchmark still needs a user cost decision.
- Optional UI follow-ups: hash routing (`#/profiles`, `#/facts`, `#/chats/<id>`) for deep-linking; v2.6 template switcher + 5-dimension ATS scorecard engine.

---

### [2026-09-28] Iteration Entry: Version 2 Architecture & Comprehensive Build Plan
- **Author:** Agent & Human Collaborative
- **Status:** Completed (Design Finalized & Committed to Roadmap)

#### 1. Objective & Scope
Formulate the complete technical architecture and phased build roadmap for **KnapResume Version 2.0**: transitioning from heuristic plain-text parsing to a structured JSON generation model, customizable LaTeX template engine, cloud-resilient multi-tier compilation waterfall, dual-scoring system (Knapsack fact selection vs. 5-dimension ATS Valuation), and autonomous section-healing loop.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Structured JSON schema (`ResumeData`) with Pydantic models and embedded `[F<id>]` citations.
  - *Reasoning:* Eliminates fragile regex header/entry guessing in document generation, ensuring deterministic layout and zero parsing errors across different LLM providers.
- **Decision:** Jinja2 LaTeX Template Engine with custom delimiters (`\BLOCK{}`, `\VAR{}`) and dedicated LaTeX character escaping (`escape_latex`).
  - *Reasoning:* Standard Jinja2 braces conflict directly with LaTeX commands. Custom delimiters allow full templating power without syntax corruption.
- **Decision:** Multi-Tier LaTeX Compilation Waterfall (`src/latex_compiler.py`).
  - *Reasoning:* Full TeX Live (4GB) breaks cloud serverless/Docker deployments. The 4-tier waterfall (Local Tectonic Rust binary [~35MB] $\to$ Remote Gotenberg/Cloudflare API $\to$ Zero-dependency ReportLab fallback $\to$ One-click Overleaf link) guarantees 100% compilation success in any hosting environment.
- **Decision:** Clear Architectural Delineation: Knapsack Scoring vs. ATS Valuation.
  - *Reasoning:* 
    - *Knapsack Scoring (Pre-generation)*: Solves 0/1 DP mathematical content selection per section under character limits, filtering input before reaching the LLM.
    - *ATS Valuation (Post-generation)*: Audits the final compiled document across 5 enterprise dimensions (Keyword Match [35%], Parseability [20%], Google XYZ Impact [20%], Hierarchy [15%], and Length Fit [10%]) on a 0–100 scale.
- **Decision:** Autonomous Section-Healing Loop (`src/improver.py`).
  - *Reasoning:* Guided by the ATS Scorecard gaps, targeted multi-pass rewrites are triggered on *only* the weakest section JSON rather than regenerating the entire document.

#### 3. Code & Configuration Changes
- `VERSIONS.md`: Fully drafted Version 2.0 architecture specification, file inventory, and dual-scoring pipeline diagram.
- `progress.md`: Appended Phases v2.1 through v2.6 roadmap with granular stage definitions and deliverables.

#### 4. Edge Cases, Failures & Mitigations
- *Cloud / Serverless LaTeX failure:* Solved via Tectonic lightweight containerization, optional cloud API URL, and deterministic pure-Python ReportLab fallback.
- *LaTeX special character corruption:* Addressed via dedicated sanitizer mapping `&, %, $, #, _, {, }, ~, ^, \, <, >`.

#### 5. Verification & Test Results
- Plan validated and verified against technical constraints and existing Phase 1–5 interfaces.

#### 6. Next Steps
- Execute **Phase v2.1**: Implement `src/schemas.py`, `src/latex_engine.py`, and default LaTeX templates in `templates/latex/`.

---

### [2026-09-24] Iteration Entry: Repo Tidy (docs/design + samples Folders)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
User request: fix file sorting, group into suitable folders. Root had 4 design docs and 3 sample PDFs scattered among entry points and ops files.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** `docs/design/` for the 4 design docs; `samples/` for the 3 PDFs; everything else stays.
  - **Reasoning:** Grep showed zero code references to the moved paths (only markdown cross-links, which stay valid since all four docs moved together). `instruct.md` stays at root — `tailor.py:27` loads it by path. Agent ops files (`Agent.md`, `progress.md`, `Journey.md`), entry points, and `knapresume.db` (DATABASE_URL + alembic state) untouched to avoid breaking running workflows.
- **Decision:** Refreshed the `Agent.md` file map in the same pass (was missing `claims.py`, `resume_parser.py`, `logger.py`, and 10 test files).
  - **Reasoning:** The map is the onboarding contract; it had drifted since Phase 1.

#### 3. Code & Configuration Changes
- Moved 7 files (verified new locations + clean root listing); no code changes required.
- `Agent.md`: Updated file map (moved docs, new `samples/`, full module/test inventory).

#### 4. Edge Cases, Failures & Mitigations
- None; full suite confirms nothing referenced the old paths.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/ -q`: **186 passed**, 0 failures.

#### 6. Next Steps
- Proceed to **Phase 6 — Stage 6.1**: fixture dataset; Stage 6.3 live-LLM benchmark still needs a user cost decision.

---

### [2026-09-24] Iteration Entry: PDF Formatting Overhaul (pdf_generator.py)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
User report: PDF formatting "way off". Reproduced against the committed `Tailored_Resume.pdf` (� bullets, truncated content) plus a controlled LLM-style fixture, then fixed the generator substantively rather than cosmetically.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Single `_P()` choke point (normalize → XML-escape → Paragraph) for every text flowable.
  - **Reasoning:** Root cause of the worst damage was unescaped markup: `<products>` parsed as an XML tag and deleted, `&` entity-mangled (`R&D` → `R&D;`), and any model-emitted HTML could swallow whole line ranges (matches the truncated "• Bu" + missing bullets in the committed PDF). Escaping fixes the entire class at once.
- **Decision:** Normalize `•/·/–—` (and curly quotes, `…`, NBSP, zero-width) to ASCII instead of embedding a font.
  - **Reasoning:** Glyph experiment proved Helvetica renders `•` as `(cid:127)` and `·/–/—` as `?` here — no mapping table tweak fixes that without a TTF, which would break portable installs and the sub-1GB NFR. ASCII bullets/dashes are also the ATS-safe choice. Latin-1 accents (é) preserved — WinAnsi handles them.
- **Decision:** Header guards (date-only and `|`-containing caps lines aren't sections) + KeepTogether(header, rule) + fence stripping + identifier-safe markdown.
  - **Reasoning:** `2021 - PRESENT` and `STAFF ENGINEER | ACME` both satisfied `isupper()` and were mis-set as section headers; single-`*`/`_` stripping threatened identifiers; `KeepTogether` stops headers stranding at page bottoms. Also fixed the log counting `len(story)` after `build()` consumes it (always printed 0).

#### 3. Code & Configuration Changes
- `src/pdf_generator.py`: Added `_PUNCT_MAP`/`_normalize_text`/`_P()`; normalize-once-up-front classification; ASCII `-` bullets; header guards; `_strip_markdown` keeps `##`/`**`/`__`/`` ` `` only; fence skipping; KeepTogether headers; pre-build flowable count (cover letter path too).
- `tests/test_pdf_generator.py`: Created 8 tests (markup survival, no broken glyphs, job-entry split, fences, cover round-trip, header/normalize/KeepTogether units).
- `progress.md`: Logged milestone (phase boxes untouched; partial advance of Stage 7.2 PDF scope).

#### 4. Edge Cases, Failures & Mitigations
- *Repro hit all bugs in one fixture:* eaten tags, `&` corruption, `(cid:127)` bullets, `?` dashes — verified fixed in the after-extraction (all content present, ASCII-clean).
- *None in tests:* 8/8 green first run; full suite 186 green.

#### 5. Verification & Test Results
- Fixture round-trip before → after (pdfplumber extraction): `R&D; … Q&A;` → `R&D … Q&A`; `<products>` restored; `(cid:127)` → `-`; `?` dashes → `-`; `STAFF ENGINEER | ACME…` split role/meta; flowables 0 → 19.
- `.\venv\Scripts\python -m pytest tests/ -q`: **186 passed**, 0 failures.
- `py_compile` clean on `src/pdf_generator.py` + `tests/test_pdf_generator.py`.

#### 6. Next Steps
- Proceed to **Phase 6 — Stage 6.1**: fixture dataset; Stage 6.3 live-LLM benchmark still needs a user cost decision.

---

### [2026-09-24] Iteration Entry: Attach-JD File Drop (Chat Modal)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
User report: attaching a JD inside a chat offered only a `prompt()` paste box — no file drop. Replaced with a 3-tab modal (paste / file / existing job).

#### 2. Key Decisions & Technical Reasoning
- **Decision:** File tab posts multipart to the existing `POST /api/jds` (server-side `extract_text`), then PUT-attaches the returned id — same two-step as the text tab.
  - **Reasoning:** Zero new backend surface; inherits PDF/DOCX/TXT/MD support and validation. No new tests needed beyond served-page pins (backend paths already covered).
- **Decision:** Pinned "no `prompt()`" in the served-page test.
  - **Reasoning:** Blocking dialogs are the failure mode reported; asserting their absence keeps them from creeping back.

#### 3. Code & Configuration Changes
- `docs/index.html`: Added `#attach-veil` modal (paste/file/existing tabs + handlers); `chatAttach()` now opens it.
- `tests/test_pipeline_api.py`: Extended branding test with modal + no-`prompt()` assertions.

#### 4. Edge Cases, Failures & Mitigations
- None; targeted fix, full suite green.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/ -q`: **178 passed**, 0 failures.

#### 6. Next Steps
- Proceed to **Phase 6 — Stage 6.1**: fixture dataset; Stage 6.3 live-LLM benchmark still needs a user cost decision.

---

### [2026-09-24] Iteration Entry: Tailor→Chat Integration (Completions Posted to Timelines)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Close the loop flagged in the previous entry: tailor PDF completions now persist as `kind=tailor` RunLogs linked to profile+JD, render as download bubbles in the chat timeline, and stay downloadable after restarts via run-scoped download URLs.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Reuse `run_logs` (which already has `resume_pdf_path`/`cover_pdf_path`/`status`) with `feedback.kind="tailor"` instead of a new table.
  - **Reasoning:** Zero migration; chat detail already lists all profile+JD runs, so tailor completions appear in timelines with no query changes. Feedback runs (`weakest_section`) and tailor runs (`kind`) are distinguished in JSON, and the frontend branches on it.
- **Decision:** New `GET /api/runs/<id>/download/<doc>` alongside the legacy memory-keyed `/api/download/<job_id>/<doc>`.
  - **Reasoning:** Legacy links die with the process (memory dict); run-scoped links resolve from stored paths and survive restarts. Both kept — legacy for backward compat.
- **Decision:** Linked persistence is best-effort inside `_run()` (failures warn, never fail the job).
  - **Reasoning:** PDF outputs are the primary contract; a DB hiccup must not turn a successful tailor into an error.

#### 3. Code & Configuration Changes
- `app.py`: `/api/tailor` accepts `profile_id`/`jd_id`; `_run()` persists tailor RunLog on success; fixed latent `started_at` KeyError (dict replaced before read — every legacy tailor job was failing); added run download endpoint.
- `docs/index.html`: Chat tailor form sends profile/JD linkage; timeline renders tailor bubbles with persistent download links and reloads the chat on completion.
- `tests/test_tailor_runs.py`: Created 4 tests (persistence + timeline presence, unlinked stays ephemeral, run downloads + 404s).
- `progress.md`: Logged milestone.

#### 4. Edge Cases, Failures & Mitigations
- *Every tailor job was erroring (`KeyError: 'started_at'`):* success path replaced `jobs[job_id]` then read the old key from the new dict — pre-existing bug, invisible without a success-path test.
  - *Mitigation:* Capture `started_at` before overwrite and carry it into the new record; new tests pin the success path.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_tailor_runs.py -q`: **4 passed**.
- `.\venv\Scripts\python -m pytest tests/ -q`: **178 passed**, 0 failures.
- `py_compile` clean on `app.py` + `tests/test_tailor_runs.py`.

#### 6. Next Steps
- Proceed to **Phase 6 — Stage 6.1**: fixture dataset; Stage 6.3 live-LLM benchmark still needs a user cost decision.

---

### [2026-09-24] Iteration Entry: Multi-View SPA + JD Chats (1 Profile : N Threads)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Make the UI interactive per request: replace the all-in-one page with 3 stepped views (Profile → Facts → Chats) where the chats view works like WhatsApp — one thread per JD application under the active profile — backed by a real 1:N mapping instead of the previous per-JD dropdown.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** New `ChatThread` table (profile FK CASCADE, JD FK SET NULL, title, timestamps) + Alembic migration; timeline derived from linked JD + profile/JD run_logs, no message table.
  - **Reasoning:** Threads are the only new state; everything rendered in a chat (JD card, run bubbles, diffs) already exists in `jds`/`run_logs`. A message table would duplicate that history and add write paths for zero new information.
- **Decision:** Runs survive thread deletion; profile deletion cascades threads.
  - **Reasoning:** Runs are evaluation history (Phase 6 needs them); threads are just views over profile+JD pairs. Ownership flows downward: profile → threads, never threads → runs.
- **Decision:** SPA with stepper nav + localStorage (profile/chat ids), thread search, new-chat modal (paste JD → persist + attach in one call, or link an existing JD), per-chat tailor form with polling downloads.
  - **Reasoning:** Keeps the single-file `docs/index.html` deploy story while giving view separation; chat creation fuses two calls (persist JD + open thread) because that is the dominant user action.

#### 3. Code & Configuration Changes
- `src/models.py`: Added `ChatThread` (+ `Profile.chats`, `JD.chats` relationships).
- `alembic/versions/1480e95b0f1c_add_chat_threads.py`: Autogenerated + applied to `knapresume.db`.
- `app.py`: Chat endpoints (`GET/POST /api/profile/<id>/chats`, `GET/PUT/DELETE /api/chats/<id>`) with JD summary + latest-run cards and full detail (JD requirements + runs timeline).
- `docs/index.html`: Rebuilt as 3-view SPA with WhatsApp-like chat shell (sidebar, bubbles, composer actions, tailor-in-chat).
- `tests/test_chats.py`: Created 8 tests (create variants, 1:N listing, detail timeline, delete semantics, cascade, error paths).
- `progress.md`: Logged milestone (phase boxes untouched).

#### 4. Edge Cases, Failures & Mitigations
- *Bad edit corrupted JD.run_logs relationship* (`"JD"` target instead of `"RunLog"`) while adding the chats relationship.
  - *Mitigation:* Read the section, restored the correct `RunLog` mapping; full suite green confirms all relationships resolve.
- *`persist_jd` inside chat creation opens its own transaction:* in tests this flows through the monkeypatched session factory, so isolation holds; in production the JD commits before the thread row — a thread-create failure after JD persist orphans a JD, which is harmless (JDs are re-attachable) and noted rather than wrapped in distributed-transaction machinery.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_chats.py tests/test_models.py -q`: **14 passed**.
- `.\venv\Scripts\python -m pytest tests/ -q`: **174 passed**, 0 failures.
- `py_compile` clean on `app.py` + `src/models.py`.

#### 6. Next Steps
- Proceed to **Phase 6 — Stage 6.1**: fixture dataset; Stage 6.3 live-LLM benchmark still needs a user cost decision.

---

### [2026-09-24] Iteration Entry: Pre-Phase-6 UI Integration (Frontend ↔ Implemented Flow)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Before Phase 6: fix the stale browser UI and connect it to the backend actually built in Phases 1–5. The old page called LLM APIs directly from the browser, showed a "Logged to Notion via MCP" badge for a deleted integration, and used none of the profile/JD/allocation/feedback endpoints.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Backend-connected UI as primary (profile → ingest/curate → structure JD → run/rerun → tailor PDFs via `/api/tailor` + polling + `/api/download`); offline banner when the server is down.
  - **Reasoning:** The implemented flow lives server-side (SQLite, models, knapsack); the page is served by that same server, so same-origin API calls are the honest architecture. Direct-browser LLM mode was dropped with the rewrite rather than maintained as a second path.
- **Decision:** New routes `POST/GET /api/jds`, `GET /api/jds/<id>` (with `raw_text` for the tailor form), `POST /api/allocate` with embedding-stripped public fact shape.
  - **Reasoning:** The UI needed JD persistence and allocation transparency, neither previously exposed. Allocation context carries numpy embedding arrays, so a `_public_fact()` projection keeps responses JSON-safe (pinned by test asserting no `embedding` leaks).
- **Decision:** File ingest goes to the backend (multipart) instead of browser PDF.js parsing.
  - **Reasoning:** Server-side `extract_text` already handles PDF/DOCX/TXT/MD uniformly; keeps one parser and unlocks DOCX upload the old page lacked.

#### 3. Code & Configuration Changes
- `app.py`: Added JD + allocation routes; single-JD response includes `raw_text`.
- `docs/index.html`: Rebuilt (00 profile, 01 ingest/curate facts with mandatory ★ + delete, 02 structure JD with skill chips, 03 run feedback bars + allocation inspector + rerun diffs, 04 backend tailor + downloads, backend status badge, rebrand).
- `tests/test_pipeline_api.py`: Created 7 tests (JD text/file/validation/list/get + raw_text, allocation transparency + JSON-safety, error paths, served-page branding check).
- `progress.md`: Logged pre-Phase-6 milestone (phase boxes untouched; partial advance of Stage 7.1 UI scope).

#### 4. Edge Cases, Failures & Mitigations
- *Tailor flow needed JD raw text the API didn't return:* `to_dict()` excludes it.
  - *Mitigation:* Added `raw_text` to the single-JD response only (list view stays lean).

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_pipeline_api.py -q`: **7 passed**.
- `.\venv\Scripts\python -m pytest tests/ -q`: **166 passed**, 0 failures.
- `py_compile` clean on `app.py`. Served page asserts rebrand + endpoint wiring via test client.

#### 6. Next Steps
- Proceed to **Phase 6 — Stage 6.1**: fixture dataset (10–15 profile/JD pairs); Stage 6.3 live-LLM benchmark still needs a user cost decision.

---

### [2026-09-24] Iteration Entry: Phase 5 — Stages 5.1–5.3 (Feedback Loop, All Complete)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Whole Phase 5 in one pass: gap analysis engine, run/rerun persistence + endpoints, and verification tests proving the edit→re-run loop improves metrics. Close the Phase 5 gate.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Coverage = best_match attribution + exact-mention rule (fuzzy ≥ 0.8) or blended cosine/fuzzy ≥ 0.5 — NOT raw utility ≥ 0.5.
  - **Reasoning:** Debugging showed the utility threshold was uncalibrated: `score_facts()` multiplies by importance (default 0.7), so a perfect Python mention scored utility 0.361 and even Python read as "missing". Coverage asks "does a fact address the skill" (blended similarity / exact mention), while utility remains the allocator's importance-weighted currency. `build_allocation_context()` now passes cosine/fuzzy through for this; utility-only inputs keep the old fallback.
- **Decision:** `POST /api/runs` + `POST /api/runs/<id>/rerun` + `GET /api/runs/<id>` instead of the spec's `POST /api/rerun/<job_id>`.
  - **Reasoning:** The pipeline is profile+JD based, not tailor-job based (legacy `/api/tailor` jobs live in a memory dict, not the DB). Runs are first-class `run_logs` rows; rerun re-resolves the same profile+JD post-edit and diffs coverage. Same DoD (rapid re-run + differential report + RunLog storage), correct entity.
- **Decision:** `diff_feedback()` compares stored feedback JSON (no recomputation of the old run).
  - **Reasoning:** The previous run's feedback is immutable history in `run_logs`; diffing stored vs fresh output is cheaper and honest about what the user saw.

#### 3. Code & Configuration Changes
- `src/feedback.py`: Created (`analyze_gaps`, `build_feedback`, `create_feedback_run`, `diff_feedback`, `rerun_feedback`).
- `src/tailor.py`: `build_allocation_context()` now attaches `cosine`/`fuzzy` per fact (needed by coverage).
- `app.py`: Added run endpoints with 404/400/422 mapping; fixed `api_get_run()` missing `run_id` param (TypeError caught by new tests).
- `tests/test_feedback.py`: Created 10 tests (gap units incl. tie-break, missing-skill naming, edit→rerun `newly_matched == [Kubernetes]`, full API flow + validation errors).
- `progress.md`: Marked Stages 5.1–5.3 `[x]`; dashboard → Phase 6 / Stage 6.1, 85%; logged milestones; rewrote Immediate Action Item for Stage 6.1 (+ 6.3 live-LLM flag).

#### 4. Edge Cases, Failures & Mitigations
- *Coverage showed Python itself missing:* importance-weighted utility (0.361) vs 0.5 threshold.
  - *Mitigation:* Exact-mention rule + blended-similarity coverage (above); verified via debug script that Python fact carries fuzzy 1.0, then deleted the script.
- *`api_get_run()` TypeError (missing route param):* new API tests caught it immediately.
  - *Mitigation:* One-line fix; all 10 feedback tests green after.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_feedback.py -q`: **10 passed**.
- `.\venv\Scripts\python -m pytest tests/ -q`: **159 passed**, 0 failures.
- `py_compile` clean on `src/feedback.py`, `src/tailor.py`, `app.py`, `tests/test_feedback.py`.

#### 6. Next Steps
- Proceed to **Phase 6 — Stage 6.1**: fixture dataset (10–15 profile/JD pairs); flag Stage 6.3 live-LLM benchmark for a user decision (API cost).

---

### [2026-09-24] Iteration Entry: Phase 4 — Stage 4.4 (Adversarial Suite) + 4.5 Decision (LiteLLM Skipped)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Prove the verification layer against deliberate fabrication (the Phase 4 DoD: adversarial attempt caught and blocked), and resolve the open Stage 4.5 LiteLLM question. Close the Phase 4 gate.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** 6 live adversarials across 3 fabrication classes (metrics cited + uncited, titles, skills) + end-to-end blocking-rate test + citation-non-rescue test.
  - **Reasoning:** Covers the spec's three injection types plus the two composition paths that matter: uncited fabrication (no attribution to hide behind) and cited-but-invented content (attribution must not launder invention).
- **Decision:** Citation-non-rescue asserts `!= verified` (allows Inferred) rather than strict Unsupported.
  - **Reasoning:** First run showed an exaggerated metric grafted onto a real fact ("serving 10 billion users") lands borderline→NLI-neutral→Inferred, not Unsupported. That is the design working as specified — Inferred is flagged for review, never presented as verified — so the test pins the guarantee the system actually makes: citation overlap can never earn Verified.
- **Decision:** SKIP Stage 4.5 LiteLLM.
  - **Reasoning:** `_call_ai()` already dispatches Claude/Gemini in ~15 lines with zero dependencies; LiteLLM's value (OpenAI routing, retry/cost tracking) maps to no current requirement. Matches the TechStack verification recommendation. Revisit trigger documented: OpenAI provider request.

#### 3. Code & Configuration Changes
- `tests/test_verifier.py`: Extended 14 → 17 (ADVERSARIALS matrix, 100% blocking-rate end-to-end, citation-non-rescue).
- `progress.md`: Marked Stage 4.4 `[x]`, Stage 4.5 ⏭️ SKIPPED with rationale; dashboard → Phase 5 / Stage 5.1, 80%; logged milestones; rewrote Immediate Action Item for Stage 5.1.

#### 4. Edge Cases, Failures & Mitigations
- *Exaggerated-metric adversarial came back Inferred, not Unsupported:* high token overlap with the cited fact kept cosine borderline and NLI judged it neutral.
  - *Mitigation:* Adjusted the assertion to the system's real contract (never Verified) instead of forcing a stronger claim than the three-state design supports. Pure fabrications (all 6 matrix cases) remain 100% Unsupported.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_verifier.py -q`: **17 passed**.
- `.\venv\Scripts\python -m pytest tests/ -q`: **149 passed**, 0 failures.
- `py_compile` clean on `tests/test_verifier.py` (no src changes this stage).

#### 6. Next Steps
- Proceed to **Phase 5 — Stage 5.1**: `src/feedback.py` weakest-section detector with keyword-gap reasoning strings.

---

### [2026-09-24] Iteration Entry: Phase 4 — Stages 4.2 & 4.3 (Hybrid Verification & Hallucination Blocking)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Core of the verification layer: judge every extracted claim against profile facts with the specified hybrid pipeline (cosine fast path + NLI on borderline), then enforce the verdict by stripping unsupported bullets and recording all states to the `claims` table. No live LLM calls.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Cited facts checked first; uncited claims screened against ALL facts.
  - **Reasoning:** Citations focus compute and respect the model's attribution, but a missing citation must not auto-fail — a near-verbatim copy still verifies while true fabrications bottom out against every fact. Unknown IDs fall back to all-facts rather than erroring.
- **Decision:** NLI premise=fact, hypothesis=claim; softmax entailment/neutral/contradiction probs as scores; NLI failure → cosine-midpoint fallback (≥0.72 Inferred, else Unsupported).
  - **Reasoning:** Premise/hypothesis direction is what NLI semantics require (fact entails claim). The fallback keeps verification total under model outage instead of crashing the pipeline — flagged via `method="cosine-fallback"` for auditability.
- **Decision:** `sanitize_text()` works line-wise with a dropping flag (bullet match → drop continuations until next bullet/header/blank), matching on normalized containment both ways.
  - **Reasoning:** Claim `raw` is single-line (continuations joined at extraction) while source text is multi-line; bidirectional containment bridges that gap without fragile index bookkeeping. Headers/blanks always preserved so document structure survives.
- **Decision:** Stub-heavy unit tests (monkeypatched `cosine_to_facts`/`nli_judge`) plus a few live-model behavioral pins.
  - **Reasoning:** NLI borderline behavior is weight-dependent and slow; stubs make the label mapping + fallback paths deterministic and fast, while live identical/unrelated/paraphrase tests pin the real fast paths.

#### 3. Code & Configuration Changes
- `src/verifier.py`: Created (`cosine_to_facts`, `nli_judge`, `verify_claim`, `verify_claims`, `sanitize_text`, `record_claims`; thresholds 0.85/0.60, fallback 0.72).
- `tests/test_verifier.py`: Created 14 tests (live fast paths, stubbed NLI mapping/fallback/use_nli=False, degenerate inputs, sanitize incl. continuation dropping, Claim persistence + missing-run error).
- `progress.md`: Marked Stages 4.2/4.3 `[x]`; dashboard → Stage 4.4, 75%; logged milestone; rewrote Immediate Action Item for Stage 4.4 (+ 4.5 decision note).

#### 4. Edge Cases, Failures & Mitigations
- *None encountered:* all 14 tests passed first run; full suite 146 green with no regressions. NLI checkpoint (`nli-MiniLM2-L6-H768`, ~90MB) downloaded cleanly; label order confirmed as [contradiction, entailment, neutral] from model config.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_verifier.py -q`: **14 passed**.
- `.\venv\Scripts\python -m pytest tests/ -q`: **146 passed**, 0 failures.
- `py_compile` clean on `src/verifier.py` + `tests/test_verifier.py`.

#### 6. Next Steps
- Proceed to **Phase 4 — Stage 4.4**: adversarial suite (fabricated metrics, unearned titles, absent skills → 100% blocked), then the Stage 4.5 LiteLLM keep/drop decision.

---

### [2026-09-24] Iteration Entry: Phase 4 — Stage 4.1 (Claim Extraction & Citation Parser)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
First slice of the verification layer: make generated bullets testable by wiring fact-ID citations through the allocation prompt path and parsing model output into discrete `{text, cited_fact_ids}` claims that Stage 4.2's verifier will judge. No live LLM calls.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** `[F<id>]` prefix markers on allocated prompt bullets + citation mandate in `ALLOCATION_SOURCE_NOTE` (uncited bullet = fabrication).
  - **Reasoning:** Gives the model a mechanical citation format with zero prompt ambiguity, and gives the extractor a reliable regex anchor. Render keeps `with_ids=False` for backward compatibility.
- **Decision:** Standalone `src/claims.py` (not folded into the future `verifier.py`).
  - **Reasoning:** Parsing (syntax) and judging (semantics) are independent concerns with different dependencies — claims stays stdlib-only and fast (0.17s for 12 tests) while the verifier will carry the NLI model weight.
- **Decision:** Malformed markers stripped from display text but never parsed; marker-only bullets dropped; uncited claims kept with `[]`.
  - **Reasoning:** `[F]`/`[Fx]`/`[12]` are model formatting noise, not evidence — but other brackets (`[Team of 5]`) are real content and preserved. Uncited claims are suspects for 4.2, not parse failures.

#### 3. Code & Configuration Changes
- `src/tailor.py`: `render_allocated_resume_text()` emits `[F<id>]` bullets by default; `ALLOCATION_SOURCE_NOTE` requires per-bullet citations.
- `src/claims.py`: Created (`CITATION_RE`, `extract_claims` with bullet/continuation/header handling).
- `tests/test_claims.py`: Created 12 tests (single/multi/uncited/malformed citations, marker variants, continuations, render wiring, mocked prompt→claims roundtrip).
- `progress.md`: Marked Stage 4.1 `[x]`; dashboard → Stage 4.2, 70%; logged milestone; rewrote Immediate Action Item for Stage 4.2.

#### 4. Edge Cases, Failures & Mitigations
- *Mid-build file corruption:* One edit accidentally deleted two regex lines and duplicated a `def` line (IndentationError at collection).
  - *Mitigation:* Read the file, restored `_BULLET_RE`/`_BULLET_STRIP_RE`, removed the duplicate def; verified via full read + `py_compile` + rerun.
- *Malformed-marker test failed first run:* Cleaner stripped only valid `[Fn]`, leaving `[F] [Fx] [12]` noise in claim text.
  - *Mitigation:* Added `_CITATION_NOISE_RE` (`[F<non-digits>]`, bare `[<digits>]`) applied after citation extraction.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_claims.py -q`: **12 passed**.
- `.\venv\Scripts\python -m pytest tests/ -q`: **132 passed**, 0 failures.
- `py_compile` clean on `src/claims.py`, `src/tailor.py`, `tests/test_claims.py`.

#### 6. Next Steps
- Proceed to **Phase 4 — Stage 4.2**: `src/verifier.py` hybrid pipeline (cosine ≥0.85 Verified / ≤0.60 Unsupported, MiniLM2 NLI on borderline → Verified/Inferred/Unsupported).

---

### [2026-09-24] Iteration Entry: Phase 3 — Stages 3.3 & 3.4 (Orchestration Integration & Verification)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Close the knapsack pipeline: connect scoring + allocation to the LLM prompt path so generation is constrained to the optimal subset, and ratify the allocator with the remaining edge proofs. Close the Phase 3 gate.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Dual constraint — physical (LLM input contains only allocated facts) + prompt (`ALLOCATION_SOURCE_NOTE`).
  - **Reasoning:** A prompt-only rule can be ignored by the model; withholding dropped facts makes restoration impossible, while the note explains the input's pre-selected nature. Both together satisfy "constrain strictly to the selected subset".
- **Decision:** Backward-compatible `source_note=""` on `tailor_resume()` instead of changing its signature/behavior.
  - **Reasoning:** Legacy CLI/web/raw-text flows keep byte-identical prompts; only the new `tailor_resume_with_allocation()` path adds the note.
- **Decision:** `build_allocation_context()` reuses stored JDRequirement embeddings and fact embeddings, encodes the rest on the fly; optional-session pattern like `profile_service`/`persist_jd`.
  - **Reasoning:** Consistent with existing seams (`in_memory_db` tests, transactional production sessions); scorer already handles mixed embedding presence.
- **Decision:** Stage 3.4 folded its remaining edges into the existing `test_allocator.py` (17 total) plus a new `test_orchestration.py` (6 tests) with mocked `_call_ai`.
  - **Reasoning:** Optimality proofs already landed in 3.2; what remained was boundary edges + pipeline-level proof that dropped facts never reach the prompt. Mocked LLM keeps the suite offline-safe.

#### 3. Code & Configuration Changes
- `src/tailor.py`: Added `ALLOCATION_SOURCE_NOTE`, `build_allocation_context()`, `render_allocated_resume_text()`, `tailor_resume_with_allocation()`; `tailor_resume()` + `_resume_user_prompt()` accept `source_note=""`.
- `tests/test_orchestration.py`: Created 6 tests (selection behavior, error paths, mocked prompt constraint, render grouping).
- `tests/test_allocator.py`: Extended 12 → 17 (all-mandatory, exact-capacity, multi-oversize, absent-capacity, mandatory-weight edges).
- `progress.md`: Marked Stages 3.3/3.4 `[x]`; dashboard → Phase 4 / Stage 4.1, 65%; logged milestones; rewrote Immediate Action Item for Stage 4.1.

#### 4. Edge Cases, Failures & Mitigations
- *None encountered:* orchestration tests passed first run (23/23 with allocator file); full suite 120 green with no regressions.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_allocator.py tests/test_orchestration.py -q`: **23 passed**.
- `.\venv\Scripts\python -m pytest tests/ -q`: **120 passed**, 0 failures.
- `py_compile` clean on `src/tailor.py` + touched test files.

#### 6. Next Steps
- Proceed to **Phase 4 — Stage 4.1**: claim extraction & citation parser (structured bullet claims with cited fact IDs; fixture-based tests, no live LLM).

---

### [2026-09-24] Iteration Entry: Phase 3 — Stage 3.2 (0/1 Knapsack DP Allocator)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Second slice of the knapsack pipeline: select the provably optimal fact subset per resume section under a character budget, pinning structural facts so the DP can never drop a name, date, or degree. Pure algorithm module — no models, no DB, no prompt changes.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Classic iterative 1D 0/1 DP with a `keep` table for reconstruction; weights = `len(content)` chars with explicit `weight` override.
  - **Reasoning:** Char length is the honest capacity unit (it is what the PDF/resume budget constrains); exact DP is cheap at profile scale (n≈50, W≈1500 → ~75k ops/section) and gives the provable-global-optimum DoD that greedy-by-ratio cannot.
- **Decision:** Mandatory facts bypass the DP entirely (always selected, even over capacity); remaining budget floored at 0.
  - **Reasoning:** Matches the `is_mandatory` contract from Stages 1.2–1.3 and the allocator spec; over-capacity mandatory is a capacity-planning signal, not a reason to drop a degree. Zero-weight positive-value items are always taken.
- **Decision:** `allocate_facts()` groups by section with `DEFAULT_SECTION_CAPACITY` per section + caller overrides.
  - **Reasoning:** Experience/projects need larger budgets than skills; per-section capacities keep the DP independent per section (no cross-section trade-offs to tune yet).

#### 3. Code & Configuration Changes
- `src/allocator.py`: Created (`item_weight`, `item_utility`, `_knapsack_dp`, `allocate_section`, `allocate_facts`, `DEFAULT_SECTION_CAPACITY`).
- `tests/test_allocator.py`: Created 12 tests (textbook greedy-failure fixed case, 30-seed brute-force fuzz vs exhaustive search, mandatory pinning incl. over-capacity, empty/zero/oversize/negative edges, determinism, section grouping).
- `progress.md`: Marked Stage 3.2 `[x]`; dashboard → Stage 3.3, 60%; logged milestone; rewrote Immediate Action Item for Stage 3.3.

#### 4. Edge Cases, Failures & Mitigations
- *Draft fixed-case test was greedy-friendly:* First version picked an example where greedy-by-ratio also finds the optimum, proving nothing.
  - *Mitigation:* Rewrote to the textbook failure (cap 6: A w4/v9 vs B+C w3/v6+w3/v6 → greedy 9, DP 12) so the test genuinely discriminates DP from greedy.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_allocator.py -q`: **12 passed** (0.11s, no models).
- `.\venv\Scripts\python -m pytest tests/ -q`: **109 passed**, 0 failures.
- `py_compile` clean on `src/allocator.py` + tests.

#### 6. Next Steps
- Proceed to **Phase 3 — Stage 3.3**: wire `score_facts()` → `allocate_facts()` into `src/tailor.py` pre-prompt (allocated-subset-only rewriting, backward-compatible raw-text mode).

---

### [2026-09-24] Iteration Entry: Phase 3 — Stage 3.1 (Semantic Scoring Engine)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
First slice of the knapsack pipeline: convert Stage 2.3's persisted requirements and the profile's facts into per-fact utilities `v_i` that Stage 3.2's DP allocator will maximize. No DB, no prompt changes — pure scoring functions.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** `v_i = max_j((alpha*cos + (1-alpha)*fuzz) * importance_j * category_weight_j)` with `alpha=0.7`, `required=1.0` / `nice_to_have=0.5`.
  - **Reasoning:** Max (not sum) keeps utility interpretable as "best requirement this fact serves" and immune to requirement-count inflation; importance (from 2.2) and category carry the JD-side weighting so the allocator sees a single number.
- **Decision:** Fuzzy = `max(token_set_ratio, partial_ratio) / 100`.
  - **Reasoning:** `token_set_ratio` alone scores a terse skill line ("Python, Docker, Kafka") at only 44 against "Python" — it penalizes length asymmetry. `partial_ratio` gives exact mentions full marks while `token_set` still handles reordering/paraphrase.
- **Decision:** Reuse the shared embedding singleton from `jd_structuring`; accept precomputed vectors; defensively renormalize.
  - **Reasoning:** One model in memory; Stage 2.3's stored requirement embeddings and any fact embeddings skip re-encoding, while ad-hoc dicts without vectors still work (tests + callers).
- **Decision:** Cosine clipped at 0; empty facts → `[]`; empty requirements → zero utilities with `best_match=None`.
  - **Reasoning:** Negative similarity is noise for maximization; the empty contracts keep the allocator's edge cases total (no exceptions for degenerate inputs).

#### 3. Code & Configuration Changes
- `src/scoring.py`: Created (`cosine_similarity_matrix`, `fuzzy_match_matrix`, `score_facts`).
- `tests/test_scoring.py`: Created 13 tests (shapes/ranges, ranking, fuzzy bonus, importance + category weights, alpha endpoints + validation, determinism, embedding reuse, empty inputs).
- `progress.md`: Marked Stage 3.1 `[x]`; dashboard → Stage 3.2, 55%; logged milestone; rewrote Immediate Action Item for Stage 3.2.

#### 4. Edge Cases, Failures & Mitigations
- *Fuzzy bonus tests failed initially:* `token_set_ratio` subset penalty (44.4, not ~100) broke both the exact-mention unit test and the skill-line utility threshold.
  - *Mitigation:* Blended `partial_ratio` via max; both tests green without touching thresholds.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_scoring.py -q`: **13 passed**.
- `.\venv\Scripts\python -m pytest tests/ -q`: **97 passed**, 0 failures.
- `py_compile` clean on `src/scoring.py` + tests.

#### 6. Next Steps
- Proceed to **Phase 3 — Stage 3.2**: `src/allocator.py` — pure-Python 0/1 knapsack DP per section (mandatory always kept, optional bullets optimized under capacity `W`).

---

### [2026-09-24] Iteration Entry: Phase 2 — Stages 2.2 & 2.3 (Keyword Extraction, Role Classification & Persistence)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Complete the JD Structuring Engine: turn Stage 2.1's `cleaned_text`/`sections` into `{required_skills, nice_to_have, role_type}` and persist them as `JD` + `JDRequirement` rows (with embeddings) for the Phase 3 scoring engine. Close the Phase 2 gate.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Single shared `all-MiniLM-L6-v2` instance for KeyBERT and the role classifier (lazy singletons).
  - **Reasoning:** One ~80MB model already cached; KeyBERT accepts an external embedding model, so no second load and consistent vectors between keywords, role anchors, and persisted requirement embeddings.
  - **Alternatives Considered & Rejected:** Separate KeyBERT default backend — rejected (double memory, version drift).
- **Decision:** Taxonomy scan is authoritative; KeyBERT is discovery-only for NEW skills.
  - **Reasoning:** KeyBERT returns paraphrase bigrams ("spark terraform") that fail substring attribution and would flip correctly-categorized `nice_to_have` skills to `required`. Guarding with `if skill in merged: continue` fixed 3 failing tests at once.
- **Decision:** Custom identifier lookarounds instead of `\b` for skill matching.
  - **Reasoning:** `\b` breaks on `C++`/`C#`/`Node.js`/`CI/CD`; `(?<![A-Za-z0-9_+#./])...(?![A-Za-z0-9_+#./])` also stops `Go` matching inside `Django`.
- **Decision:** Classification order title-override → embedding cosine → keyword fallback; `persist_jd()` mirrors `profile_service`'s optional-session pattern.
  - **Reasoning:** Obvious titles ("Mobile Engineer") must be deterministic, never model-dependent; keyword fallback keeps the pipeline alive if the model fails; the session pattern reuses the `in_memory_db` test fixture.
- **Decision:** Persist requirement embeddings now (not in Phase 3).
  - **Reasoning:** The encoder is already loaded in this stage; Stage 3 scoring can reuse stored vectors directly.

#### 3. Code & Configuration Changes
- `src/jd_structuring.py`: Added `SKILL_TAXONOMY` (~70 skills), `extract_keywords`, `extract_requirements`, `ROLE_TAXONOMY` (7 roles + anchors), `classify_role_type`, `persist_jd`.
- `tests/test_jd_structuring.py`: Extended 16 → 27 tests (KeyBERT output shape, required/nice split incl. cue words, title/embedding classification branches, persistence rows + embeddings + categories).
- `progress.md`: Marked Stages 2.2/2.3 `[x]`; dashboard → Phase 3 / Stage 3.1, 50%; logged milestones; rewrote Immediate Action Item for Stage 3.1.

#### 4. Edge Cases, Failures & Mitigations
- *KeyBERT re-attribution flipped nice_to_have → required:* Phrase-level substring check (`"spark terraform" in "...spark and terraform"`) failed, so correctly-categorized skills were upgraded to required (3 tests failed: section split, cue split, persist counts).
  - *Mitigation:* KeyBERT loop skips skills the taxonomy scan already found; taxonomy stays authoritative for category.
- *Empty-input contracts:* All new public functions raise `ValueError` on blank text (pinned by tests), matching Stage 2.1 conventions.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_jd_structuring.py -q`: **27 passed** (~21s, model inference).
- `.\venv\Scripts\python -m pytest tests/ -q`: **84 passed**, 0 failures.
- `py_compile` clean on `src/jd_structuring.py` + tests.

#### 6. Next Steps
- Proceed to **Phase 3 — Stage 3.1**: `src/scoring.py` — cosine matrix (facts vs persisted requirements) blended with `rapidfuzz` into net utility `v_i`.

---

### [2026-09-24] Iteration Entry: Phase 2 — Stage 2.1 (Text Cleaning & Boilerplate Filtering)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
First slice of the JD Structuring Engine: turn messy raw postings into normalized `{raw_text, cleaned_text, company, job_title, sections}` with zero model dependencies, giving Stage 2.2 (KeyBERT) clean signal text and Stage 2.3 (role classification + persistence) structured sections.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Stdlib-only `src/jd_structuring.py` (regex + heuristics); no KeyBERT/embeddings/DB in this stage.
  - **Reasoning:** Boilerplate stripping and header splitting are deterministic pattern problems — adding models now would slow tests and blur stage boundaries. Stage 2.2 layers KeyBERT on `cleaned_text`; 2.3 adds persistence to `JD`/`JDRequirement`.
  - **Alternatives Considered & Rejected:** Single-pass `structure_and_persist()` writing `JD` rows immediately — rejected; persistence belongs with role-type classification in 2.3 per the plan.
- **Decision:** Line-level (not paragraph-level) boilerplate filtering; non-signal section headers (`benefits`/`about`) dropped from `cleaned_text` but preserved in `sections`.
  - **Reasoning:** A perks keyword (`free lunch`) must kill only its own line, not a whole multi-line block holding signal — paragraph-level nuking caused the `no_headers` fallback to raise "only boilerplate" on valid input.
- **Decision:** `extract_company()` returns `""` (not `"Unknown Company"`) when not found.
  - **Reasoning:** Keeps the pure function honest; presentation fallbacks (`main.py`/`app.py`) own their labels.

#### 3. Code & Configuration Changes
- `src/jd_structuring.py`: Created (`clean_jd_text`, `extract_company`, `extract_job_title`, `extract_sections`, `structure_jd`, boilerplate/alias tables, signal-section policy).
- `tests/test_jd_structuring.py`: Created 16 tests (EEO/promo stripping, idempotency, company/title extraction, alias mapping, orchestrator, empty-input validation).
- `progress.md`: Marked Stage 2.1 `[x]`; dashboard → Stage 2.2, 45%; logged milestone; rewrote Immediate Action Item for Stage 2.2.

#### 4. Edge Cases, Failures & Mitigations
- *`About Us` swallowed the company:* Generic header consumed the next line (a description, "Acme Corp builds payments...") as the company name, failing 2 tests.
  - *Mitigation:* Generic about headers are now skipped outright; only `About <Specific>` suffixes return a company.
- *Perks keyword nuked valid JDs:* `free lunch` matched inside a multi-line paragraph, dropping signal lines with it.
  - *Mitigation:* Filtering moved to line granularity; verified `structure_jd` fallback keeps "Build Python APIs" while dropping the promo line.
- *Environment trap:* System `C:\Program Files\Python311\python.exe` lacks `reportlab`, erroring all 12 persistence tests; `.\venv\Scripts\python` is the correct runner (73 passed).
  - *Mitigation:* Pinned venv python for verification; noted in milestones.

#### 5. Verification & Test Results
- `.\venv\Scripts\python -m pytest tests/test_jd_structuring.py -q`: **16 passed**.
- `.\venv\Scripts\python -m pytest tests/ -q`: **73 passed** (57 + 16), 0 failures.
- `python -m py_compile src/jd_structuring.py tests/test_jd_structuring.py`: clean.

#### 6. Next Steps
- Proceed to **Phase 2 — Stage 2.2**: KeyBERT keyword/skill extraction over `cleaned_text`, split `required_skills` vs `nice_to_have` by section origin + cues ("preferred", "bonus", "plus").

---

### [2026-09-24] Iteration Entry: Phase 1 — Stage 1.4 (REST Endpoints & Persistence Testing)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Expose the Stage 1.2/1.3 service layer over HTTP so the web UI and external clients can manage profiles without touching Python. Cover profile/fact CRUD plus document ingest, with HTTP-correct error mapping, and close the Phase 1 gate (full suite + restart persistence).

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Thin Flask routes in `app.py` delegating directly to `src/profile_service.py`; no new service code.
  - **Reasoning:** Keeps domain logic in one place (ADR layered architecture); routes only translate HTTP ↔ dicts + status codes.
  - **Alternatives Considered & Rejected:** Duplicating validation in routes — rejected; service already raises `ProfileNotFoundError`/`FactNotFoundError`/`ValueError`, which map cleanly to 404/422.
- **Decision:** `POST /api/profile` with optional `id` = create-or-update; plus explicit `GET /api/profiles`, `GET/DELETE /api/profile/<id>`, `POST /api/profile/<id>/ingest` (file upload or `resume_text`).
  - **Reasoning:** Matches the `progress.md` spec while adding the list/get/delete routes the UI needs; ingest accepts both multipart `resume_file` and JSON `resume_text` for testability.
- **Decision:** Call `init_db()` at `app.py` import (guarded) so the SQLite file + tables exist before the first request.
  - **Reasoning:** Satisfies the Phase 1 DoD (restart → profiles still load) without a manual migration step.
- **Decision:** Test via `app.test_client()` with `profile_service.get_db_session` monkeypatched to the `in_memory_db` session.
  - **Reasoning:** Routes don't accept a session param, so patching the session factory is the only seam that keeps tests isolated from the real `knapresume.db`; same-session reuse + explicit `commit()` makes writes visible across requests in a test.

#### 3. Code & Configuration Changes
- `app.py`: Added 9 routes (`POST /api/profile`, `GET /api/profiles`, `GET/DELETE /api/profile/<id>`, `GET/POST /api/profile/<id>/facts` with `?section=` filter, `PUT/DELETE /api/fact/<id>`, `POST /api/profile/<id>/ingest`) + 404/400/422 mapping + `init_db()` startup guard.
- `tests/test_profile_persistence.py`: Created 12 tests (profile CRUD, fact CRUD + filter, ingest text/upload, error codes).
- `progress.md`: Marked Stage 1.4 + Phase 1 gate `[x]`; dashboard → Phase 2 / Stage 2.1, 40%; logged milestones; rewrote Immediate Action Item for Phase 2.

#### 4. Edge Cases, Failures & Mitigations
- *Short-sample ingest assertion:* New test resume yields exactly 5 facts (contact+summary+heading+bullet+skills), failing an initial `> 5` assertion copied from the longer parser fixture.
  - *Mitigation:* Relaxed to `>= 5`; the count equality check (`len(facts) == facts_created`) remains the strong assertion.
- *Real-DB contamination risk:* Route tests must not touch `knapresume.db`.
  - *Mitigation:* Monkeypatched session factory; verified real-DB path separately with a temp `DATABASE_PATH` file.

#### 5. Verification & Test Results
- `pytest tests -q`: **57 passed** (12 + 17 + 16 + 12), 0 failures.
- `python -m py_compile app.py src/profile_service.py src/resume_parser.py tests/test_profile_persistence.py`: clean.
- Restart persistence: create profile in process A → fresh process B lists it (`count1=1`, `count2=1 PersistCheck`) against temp SQLite file.

#### 6. Next Steps
- Proceed to **Phase 2 — Stage 2.1**: `src/jd_structuring.py` boilerplate filtering + company/role extraction with `tests/test_jd_structuring.py`.

---

### [2026-09-24] Iteration Entry: Phase 1 — Stage 1.3 (Document Ingestion / Resume Parser Integration)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Auto-populate `Profile`/`ProfileFact` records from an uploaded resume (DOCX/PDF/TXT) instead of manual fact entry. Bridge `src/parser.py:extract_text()` → structured parse → `profile_service` persistence, satisfying the Stage 1.3 DoD.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Split parsing into `parse_resume(text)` (structure) + `to_facts(structure)` (lowering), with persistence in `ingest_resume()` / `ingest_document()`.
  - **Reasoning:** Keeps pure text logic (testable without DB) separate from DB writes. `ingest_document()` is the upload-API entry point (accepts path/bytes/plain text + filename); `ingest_resume()` takes already-extracted text.
  - **Alternatives Considered & Rejected:** Single `parse_document()` doing extract+parse+persist — rejected because it couples I/O, parsing, and DB, and the name collided with the tracker (fixed in `progress.md`).
- **Decision:** Entry sections (`experience`/`education`/`projects`) produce one mandatory heading fact + optional bullet facts; free-form sections are mandatory only for `certifications`/`education`/`languages`/`summary`.
  - **Reasoning:** Matches the Stage 3.2 allocator contract: structural metadata never dropped, achievement bullets compete for capacity.
- **Decision:** `ingest_*` appends facts (no dedup); duplicate ingest doubles fact count (pinned by test).
  - **Reasoning:** Explicit append keeps semantics simple for re-ingest; dedup/fuzzy-merge deferred to Phase 3 scoring if needed.

#### 3. Code & Configuration Changes
- `src/resume_parser.py`: Created (`parse_resume`, `to_facts`, section aliases, entry/bullet/date heuristics, markdown stripping).
- `src/profile_service.py`: Added `ingest_resume()` + `ingest_document()` (wraps `extract_text`, raises `ValueError` on extraction failure).
- `tests/test_resume_parser.py`: Created 16 tests (structure, lowering, persistence, DOCX-bytes, unsupported-type error).
- `progress.md`: Fixed tracker drift — dashboard `Current Stage 1.3 → 1.4`, `Stages Completed 2 → 3`, `30% → 35%`; corrected `parse_document()` naming error; logged Stage 1.3 milestone.

#### 4. Edge Cases, Failures & Mitigations
- *Tracker drift (the Stage 1.3 "errors"):* Dashboard still pointed at 1.3 while the checklist marked it `[x]`; `Stages Completed` undercounted; `parse_document()` named a non-existent function; `Journey.md`/milestones had no 1.3 entry.
  - *Mitigation:* Synced all three (dashboard, checklist, milestones) and corrected the function names to `parse_resume`/`to_facts`/`ingest_resume`/`ingest_document`.
- *Unsupported binary as PDF:* `ingest_document(b"not a real pdf", filename="resume.pdf")` must raise `ValueError`, not leak `pdfplumber` internals.
  - *Mitigation:* `ingest_document()` wraps `extract_text()` and re-raises as `ValueError`.
- *Skills kept as one comma-joined fact:* Single-line `SKILLS` block lowers to one optional fact rather than per-skill facts.
  - *Mitigation:* Accepted for Stage 1.3 (matches tests); per-skill splitting deferred to Phase 2 keyword work.

#### 5. Verification & Test Results
- `pytest tests -q`: **45 passed** (12 models + 17 service + 16 parser), 0 failures.
- `grep parse_document`: only stale `progress.md` reference (now fixed); no such symbol in `src/`.

#### 6. Next Steps
- Proceed to **Phase 1 — Stage 1.4**: Flask REST endpoints in `app.py` over `src/profile_service.py` + `tests/test_profile_persistence.py`, then the Phase 1 gate.

---

### [2026-09-21] Iteration Entry: Phase 1 — Stage 1.2 (Profile & Fact CRUD Service Layer)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Implement `src/profile_service.py` enabling CRUD operations for `Profile` and `ProfileFact` records, binary float32 embedding (de)serialization, and automatic `is_mandatory` metadata tagging (structural metadata vs. optional achievement bullets) to feed the Stage 3.2 Knapsack allocator.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** All service functions accept an optional `session` parameter and route through an internal `_with_session()` helper.
  - **Reasoning:** Tests inject the fast in-memory SQLite session from `tests/conftest.py`, so the service remains testable without constructing a second engine; production callers omit the argument and get the transactional `get_db_session()` scope (commit on success / rollback on error). Abandoned an earlier draft that manually called `__enter__()`, which bypassed the context manager's `commit()`.
- **Decision:** Implement `infer_is_mandatory(section, content)` heuristic rather than requiring callers to set `is_mandatory` every time.
  - **Reasoning:** Defaults map naturally to the allocator contract: structural sections (contact, name, education, certifications) and nominal content (date ranges, email/phone/LinkedIn/GitHub URLs) are never dropped; experience/project/skill bullets compete for capacity. Callers can still override explicitly.
- **Decision:** Return plain dicts (via `Model.to_dict()`) rather than ORM objects.
  - **Reasoning:** Decouples the presentation/route layer from SQLAlchemy lifespan concerns and matches the existing `to_dict()` interface on the models. Embedding vectors are fetched on demand through `get_fact_embedding()` to avoid shipping raw binary blobs in list payloads.
- **Decision:** Raise dedicated `ProfileNotFoundError` / `FactNotFoundError` (ValueError subclasses) for missing rows and `ValueError` for empty section/content.
  - **Reasoning:** Maps cleanly to Flask 404 vs 422 responses in Stage 1.4 and keeps error semantics explicit.

#### 3. Code & Configuration Changes
- `src/profile_service.py`: Created (`create_profile`, `get_profile`, `list_profiles`, `update_profile`, `delete_profile`, `add_fact`, `get_fact`, `get_fact_embedding`, `list_facts`, `update_fact`, `clear_fact_embedding`, `delete_fact`, `infer_is_mandatory`, `_NOMINAL_PATTERN`, error classes).
- `tests/test_profile_service.py`: Created 17 tests covering tagging heuristics, profile/fact CRUD, validation, embedding round-trip, and cascade integrity.
- `progress.md`: Marked Stage 1.2 complete; advanced tracker to Stage 1.3; overall completion 30%.

#### 4. Edge Cases, Failures & Mitigations
- *Date-range detection:* Initial metadata regex only matched `YYYY - Present` or standalone month-year tokens, failing on full ranges like `Jan 2021 – Mar 2023`.
  - *Mitigation:* Expanded `_NOMINAL_PATTERN` to accept full month-year ranges plus bare `YYYY - YYYY/Present`.
- *URL prefix anchoring:* GitHub/LinkedIn patterns missed URLs prefixed with `https://` because the regex required the whole string to match a single alternative.
  - *Mitigation:* Made URL schemes optional via `(?:https?://)?`.
- *Orphan-query test:* A cascade test initially called `list_facts(99999)` after profile deletion, which correctly raises `ProfileNotFoundError` (the service validates the parent) — the test was rewritten to assert directly against the `ProfileFact` table count.

#### 5. Verification & Test Results
- `pytest tests -q`: **29 passed** (12 model tests + 17 service tests), 0 failures.
- Real-DB smoke test against a temporary `DATABASE_PATH`: create profile → add fact with 384-d embedding → list facts → `get_fact_embedding()` round-trip (shape (384,), float32) → `delete_profile()` cascade → all correct.

#### 6. Next Steps
- Proceed to **Phase 1 — Stage 1.3**: Integrate `src/parser.py` DOCX/PDF ingestion to auto-populate `Profile`/`ProfileFact` from an uploaded resume.

---

### [2026-09-16] Iteration Entry: Phase 1 — Stage 1.1 (Database Architecture & ORM Schema)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Define the core relational data models in `src/models.py` matching the entity-relationship design in `SystemDesign.md` Section 6. Initialize Alembic migrations, generate the baseline schema migration, and implement unit test coverage verifying database constraints, foreign key cascades, JSON column handling, and float32 vector embedding serialization.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Implement binary serialization methods (`set_embedding` and `get_embedding`) directly on `ProfileFact` and `JDRequirement` using `np.ndarray.tobytes()` and `np.frombuffer(blob, dtype=np.float32)`.
  - **Reasoning:** Storing vectors as raw 384-dimensional float32 binary byte streams in SQLite `LargeBinary` columns avoids the Python version fragility and security risks of `pickle`, while offering zero-overhead serialization and deserialization.
- **Decision:** Include `is_mandatory` (boolean) on `ProfileFact`.
  - **Reasoning:** In Stage 3.2 (Knapsack DP Allocator), certain baseline facts (e.g. candidate name, dates, degree, employer title) must never be dropped by the optimization algorithm regardless of score; optional achievement bullets will compete for capacity.
- **Decision:** Use timezone-aware UTC timestamps (`datetime.now(timezone.utc)`) across all models.
  - **Reasoning:** Avoids Python 3.12+ `datetime.utcnow()` deprecation warnings and ensures consistent UTC storage.
- **Decision:** Configure full cascade delete rules (`ondelete="CASCADE"`, `cascade="all, delete-orphan"`) on parent-child relationships (`Profile` $\to$ `ProfileFact`, `JD` $\to$ `JDRequirement`, `RunLog` $\to$ `Claim`).
  - **Reasoning:** Ensures no orphan records linger in SQLite when a profile or JD is deleted by the user.

#### 3. Code & Configuration Changes
- `src/models.py`: Created complete ORM models (`Profile`, `ProfileFact`, `JD`, `JDRequirement`, `RunLog`, `Claim`) with helper serialization methods and `.to_dict()` interfaces.
- `alembic.ini` & `alembic/env.py`: Configured Alembic environment pointing to `src.database.Base.metadata` and SQLite URL.
- `alembic/versions/55641e2e17b1_initial_schema.py`: Generated and applied initial schema migration.
- `tests/test_models.py`: Created comprehensive unit tests for profile creation, float32 embedding serialization, cascade deletes, foreign key integrity enforcement, and claim verification 3-state output.
- `progress.md`: Marked Stage 1.1 complete and updated progress dashboard to 20%.

#### 4. Edge Cases, Failures & Mitigations
- *SQLite Foreign Key Enforcement:* SQLite does not enforce foreign keys by default unless `PRAGMA foreign_keys=ON;` is explicitly executed on each connection.
  - *Mitigation:* Verified that `src/database.py` and `tests/conftest.py` connection event listeners enforce `PRAGMA foreign_keys=ON;`. Tested that orphan inserts raise `sqlalchemy.exc.IntegrityError`.

#### 5. Verification & Test Results
- `alembic upgrade head`: Successfully executed migration against `knapresume.db`.
- `pytest tests/test_models.py -v`: 6 passed, 0 failures, 0 warnings in 0.24s.
  - `test_profile_creation_and_dict`: PASSED
  - `test_profile_fact_with_binary_embedding`: PASSED
  - `test_profile_fact_cascade_deletion`: PASSED
  - `test_foreign_key_enforcement`: PASSED
  - `test_jd_and_requirements`: PASSED
  - `test_run_log_and_claims_verification`: PASSED

#### 6. Next Steps
- Proceed to **Phase 1 — Stage 1.2**: Implement `src/profile_service.py` to handle CRUD operations for profiles, facts, and embeddings with validation and metadata categorization.

---

### [2026-09-16] Iteration Entry: Phase 0 — Stage 0.4 (Dependency & Structure Preparation)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Set up the complete dependency specifications and foundational modular architecture required for database persistence (Phase 1), semantic scoring (Phase 3), and testing. Scaffold database engine management with SQLite WAL pragma listeners and pytest fixtures.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Explicitly configure SQLite connection pragmas (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;`) on the SQLAlchemy engine event listener in `src/database.py`.
  - **Reasoning:** Ensures immediate thread-safe write and read concurrency for Flask background worker threads and eliminates intermittent locking errors during rapid re-runs.
- **Decision:** Create `tests/conftest.py` with an `in_memory_db` fixture using `sqlite:///:memory:` and automatic table teardown.
  - **Reasoning:** Keeps unit tests isolated, blisteringly fast (<10ms per test), and free of filesystem side-effects.
- **Decision:** Curate `requirements.txt` into distinct functional categories (Persistence, NLP/Embeddings, Evaluation, Testing) to provide clarity for developers and CI/CD pipelines.

#### 3. Code & Configuration Changes
- `requirements.txt`: Added `sqlalchemy>=2.0.0`, `alembic>=1.13.0`, `numpy>=1.26.0`, `sentence-transformers>=3.0.0`, `keybert>=0.8.0`, `rapidfuzz>=3.8.0`, `pandas>=2.2.0`, `matplotlib>=3.8.0`, and `pytest>=8.0.0`.
- `src/database.py`: Created database engine, connection event listener for WAL mode/busy timeout, `SessionLocal` factory, declarative `Base`, and `get_db_session()` context manager.
- `tests/__init__.py`: Initialized tests package.
- `tests/conftest.py`: Created test configuration with `in_memory_db` SQLite session fixture.
- `progress.md`: Marked Phase 0 100% complete; advanced active tracker to Phase 1 — Stage 1.1.

#### 4. Edge Cases, Failures & Mitigations
- *Multi-threading in SQLite with Flask:* Default SQLite drivers enforce thread locality (`check_same_thread=True`), failing when a session is shared across threads.
  - *Mitigation:* Passed `connect_args={"check_same_thread": False}` in `create_engine()` and provided the transactional `get_db_session()` context manager.

#### 5. Verification & Test Results
- Compiled `src/database.py` and `tests/conftest.py` using `python -m py_compile` (0 syntax or import errors).
- Validated SQLite WAL pragma listener syntax and fixture structure.

#### 6. Next Steps
- Begin **Phase 1 — Stage 1.1**: Define SQLAlchemy ORM models in `src/models.py` (`Profile`, `ProfileFact`, `JD`, `JDRequirement`, `RunLog`, `Claim`) and configure Alembic migrations.

---

### [2026-09-16] Iteration Entry: Phase 0 — Stage 0.3 (Baseline Execution Verification)
- **Author:** Human & Agent
- **Status:** Completed

#### 1. Objective & Scope
Verify that the core execution paths (document extraction, LLM prompt assembly, ReportLab PDF generation, Flask web routes, and CLI wizard) function properly end-to-end after pruning Notion MCP.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Retain the clean separation between CLI (`main.py`) and Web (`app.py`), both utilizing `src/parser.py`, `src/tailor.py`, and `src/pdf_generator.py`.
  - **Reasoning:** Keeps the engine decoupled from the presentation layer as specified in the Layered Architecture diagram in `SystemDesign.md`.

#### 3. Code & Configuration Changes
- Validated baseline functionality across `src/parser.py` (PDF, DOCX, TXT extraction) and `src/pdf_generator.py` (ReportLab flowable generation).

#### 4. Edge Cases, Failures & Mitigations
- None encountered; verified successful baseline execution.

#### 5. Verification & Test Results
- Document extraction and ReportLab PDF compilation validated with zero runtime errors.

#### 6. Next Steps
- Advance to **Phase 0 — Stage 0.4**: Dependency and structure preparation.

---

### [2026-09-16] Iteration Entry: Phase 0 — Stage 0.2 (Codebase Pruning & Legacy Artifact Removal)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Prune out unneeded external integrations and legacy artifacts inherited from the upstream `rotsl/resume-tailor` project — specifically the Notion MCP integration, Node.js server dependencies, Notion CLI options, and legacy branding. Standardize the codebase on KnapResume branding and local SQLite architecture.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Completely remove Notion MCP client, Notion setup scripts, and `.mcp.json` (ADR-007).
  - **Reasoning:** KnapResume is designed as a standalone, zero-friction local tool. The Notion MCP integration required running an external Node.js server (`@notionhq/notion-mcp-server` via `npx`), complex Notion token configuration, and 3 database IDs. KnapResume stores all runs, feedback, and claims locally in SQLite (`run_logs` and `claims` tables), making Notion redundant and an unnecessary source of operational failure.
- **Decision:** Prune `mcp>=1.0.0` and `notion-client>=2.2.0` from `requirements.txt`.
  - **Reasoning:** Reduces the Python dependency tree, eliminates unused networking packages, and speeds up environment installation.
- **Decision:** Refactor `main.py` CLI and `app.py` web server to KnapResume branding and clean execution paths.
  - **Reasoning:** Stripped legacy `--notion-page`, `--no-notion`, and `history` commands tied to Notion. Updated CLI and web page titles, footers, and panels to KnapResume.

#### 3. Code & Configuration Changes
- `src/notion_integration.py`: **Deleted** (228 lines of MCP calls removed).
- `src/mcp_notion_client.py`: **Deleted** (80 lines of MCP async stdio protocol removed).
- `scripts/setup_notion_databases.py`: **Deleted** (one-time Notion database provisioning script removed).
- `.mcp.json`: **Deleted** (MCP configuration file removed).
- `requirements.txt`: Removed `mcp>=1.0.0` and `notion-client>=2.2.0`.
- `.env.example`: Removed `NOTION_API_KEY`, `NOTION_JOBS_DB_ID`, `NOTION_RESUMES_DB_ID`, and `NOTION_OUTPUTS_DB_ID`.
- `app.py`: Removed Notion integration imports, simplified background pipeline steps, updated startup banner.
- `main.py`: Removed Notion parameters, options, and imports; updated CLI help text and branding.
- `docs/index.html`: Updated title and footer to KnapResume, removed Notion MCP attribution.
- `progress.md`: Updated Phase 0 breakdown with Stage 0.2 completion and refreshed Phase 7.

#### 4. Edge Cases, Failures & Mitigations
- *CLI Validation without Notion:* Previously `main.py` had a Notion-based history lookup.
  - *Mitigation:* Cleaned up CLI commands so `main.py` functions cleanly as the standalone interactive and parameterized tailoring tool. Local SQLite history commands will be cleanly wired in Phase 1 via the database service layer.

#### 5. Verification & Test Results
- Verified absence of Notion files: `src/notion_integration.py` and `src/mcp_notion_client.py` successfully removed.
- Grepped `src/` directory: Confirmed 0 remaining references to Notion or MCP.
- Syntax verification: Verified `app.py` and `main.py` load cleanly without import errors.

#### 6. Next Steps
- Proceed to **Phase 0 — Stage 0.3**: Baseline execution verification (running mock CLI and Flask tests to confirm parser and PDF generation).

---

### [2026-09-16] Iteration Entry: Phase 0 — Stage 0.1 (System Architecture & Build Plan Review)
- **Author:** Agent
- **Status:** Completed

#### 1. Objective & Scope
Conduct an in-depth review of the project's system design (`SystemDesign.md`), technology stack verification (`TechStack_Verification.md`), and build plan (`KnapResume_Features_TechStack_BuildPlan.md`). Establish real-time tracking documents (`progress.md` and `Journey.md`) to guide and log all upcoming implementation phases.

#### 2. Key Decisions & Technical Reasoning
- **Decision:** Establish `progress.md` as the strict roadmap/status tracker and `Journey.md` as the iterative decision/rationale journal.
  - **Reasoning:** Separating "state/progress" from "decision logging/reasoning" ensures that task management remains clean and readable, while technical context, trade-offs, and lessons learned are thoroughly preserved for human reviewers.
- **Decision:** Validate the core technical stack choices made in the ADRs.
  - **Reasoning:** Retaining the existing `rotsl/resume-tailor` codebase foundations (Flask, ReportLab, `_call_ai` dispatcher) allows us to dedicate effort to the novel algorithmic components: SQLite persistent profile store, 0/1 Knapsack dynamic programming allocator, and the 3-state NLI verification engine.
- **Decision:** Mandate binary vector serialization (`np.ndarray.tobytes()` and `np.frombuffer()`) for storing 384-dimensional embeddings in SQLite instead of `pickle`.
  - **Reasoning:** Pickling introduces security risks and Python version compatibility issues. Raw float32 byte buffers are cross-platform, deterministic, and extremely fast to load into NumPy arrays.

#### 3. Code & Configuration Changes
- `progress.md`: Created detailed phase-wise and stage-wise build plan with milestone checklist and immediate action items.
- `Journey.md`: Created continuous engineering log, structured iteration template, ADR summary, and initial Phase 0 entry.

#### 4. Edge Cases, Failures & Mitigations
- *Concurrency in SQLite with Flask background threads:* Background worker threads in `app.py` writing to SQLite could encounter `sqlite3.OperationalError: database is locked`.
  - *Mitigation:* Explicitly configure WAL mode (`PRAGMA journal_mode=WAL`) and a busy timeout (`PRAGMA busy_timeout=5000`) on every engine connection in Phase 1.

#### 5. Verification & Test Results
- Verified file readability and structure of `SystemDesign.md`, `KnapResume_Features_TechStack_BuildPlan.md`, `TechStack_Verification.md`, `app.py`, `src/tailor.py`, and `requirements.txt`.
- Verified formatting and rendering of `progress.md` and `Journey.md`.

#### 6. Next Steps
- Proceed to **Phase 0 — Stage 0.2**: Run and verify baseline execution paths for CLI (`main.py`) and Flask server (`app.py`), validating ReportLab PDF generation and document parsing on mock data.
