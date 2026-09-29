# KnapResume — Project Progress Tracker

> **Tracking Document:** `progress.md`  
> **Purpose:** Dictates the phase-wise and stage-wise build plan, tracks real-time completion status, and defines the immediate next task to be picked up.  
> **Paired Document:** `Journey.md` (captures iterative reasoning, technical decisions, architectural choices, and change history).

---

## 📊 Project Status Dashboard

- **Current Phase:** Phase 7 — Export, Integration & Final Polish
- **Current Stage:** Phase 7 complete (only Phase 6.1 fixtures + live report remain)
- **Overall Completion:** 95%
- **Status:** 🟢 Phase 7 complete

| Phase | Description | Target Timeline | Status | Stages Total | Stages Completed |
|---|---|---|---|---|---|
| **Phase 0** | Fork & Orient | 1 day | ✅ Completed | 4 | 4 |
| **Phase 1** | Profile Persistence Layer | 4 days | ✅ Completed | 4 | 4 |
| **Phase 2** | JD Structuring Engine | 3 days | ✅ Completed | 3 | 3 |
| **Phase 3** | Scoring & Knapsack Allocation | 4 days | ✅ Completed | 4 | 4 |
| **Phase 4** | Verification Layer (3-State) | 5 days | ✅ Completed | 5 | 5 |
| **Phase 5** | Weakest-Section Feedback Loop | 2 days | ✅ Completed | 3 | 3 |
| **Phase 6** | Evaluation Harness & Benchmarking | 4 days | 🔄 In Progress (6.2–6.4 done, 6.1 pending) | 4 | 3 |
| **Phase 7** | Export, Integration & Final Polish | 3 days | ✅ Completed | 3 | 3 |

---

## 🎯 What is Next to be Picked Up (Immediate Action Item)

1. **Phase 6 — Stage 6.1 — Fixture Dataset Construction**
    - Create 10–15 realistic profile/JD fixture pairs across specializations (backend, frontend, data, devops, mobile, ML) as importable fixtures.
    - Then 6.2 metric pipeline (keyword match, ATS density, fabrication rate, knapsack utilization); 6.3 needs live-LLM decision (baseline vs KnapResume burns API calls).

2. **Phase 1 Gate — DONE (2026-09-24)**
    - Full suite `pytest -q`: 57 passed (12 models + 17 service + 16 parser + 12 persistence).
    - Restart persistence verified via temp `DATABASE_PATH` (count survives new process).
    - `python -m py_compile` clean on `app.py` + touched modules.

---

## 🏗️ Detailed Phase-Wise & Stage-Wise Breakdown

```
Legend:
[x] Completed
[/] In Progress
[ ] Pending
[!] Blocked
```

---

### Phase 0: Fork & Orient (Estimated: 1 Day) — ✅ COMPLETED
*Objective: Understand existing codebase, prune unnecessary legacy artifacts (Notion MCP server, etc.), verify baseline execution, and finalize architecture integration boundaries.*

- [x] **Stage 0.1 — System Architecture & Design Review**
  - Review `SystemDesign.md`, `TechStack_Verification.md`, and `KnapResume_Features_TechStack_BuildPlan.md`.
  - Validate core architectural trade-offs (SQLite WAL mode, ReportLab retention, small NLI model).
  - Initialize project tracking (`progress.md`, `Journey.md`).
- [x] **Stage 0.2 — Codebase Pruning & Legacy Artifact Removal**
  - Delete obsolete Notion MCP integration files (`src/notion_integration.py`, `src/mcp_notion_client.py`, `scripts/setup_notion_databases.py`, `.mcp.json`).
  - Prune unused dependencies from `requirements.txt` (`mcp`, `notion-client`) and clean `.env.example`.
  - Refactor `app.py` and `main.py` to remove external Notion calls and update CLI/UI branding to KnapResume.
  - Clean up footer and title in `docs/index.html`.
- [x] **Stage 0.3 — Baseline Execution Verification**
  - Verify local execution paths for `main.py` (CLI) and `app.py` (Flask server).
  - Verify ReportLab PDF generation with sample inputs (`pdf_generator.py`).
  - Test parser capabilities for PDF/DOCX/TXT (`parser.py`).
- [x] **Stage 0.4 — Dependency & Structure Preparation**
  - Update `requirements.txt` with SQLAlchemy, Alembic, NumPy, Pytest, Sentence-Transformers, KeyBERT, RapidFuzz.
  - Establish `src/database.py` with WAL pragma event listeners, engine factory, and session management.
  - Initialize `tests/` directory with `tests/conftest.py` in-memory SQLite fixtures.

---

### Phase 1: Profile Persistence Layer (Estimated: 4 Days)
*Objective: Build persistent, SQLite-backed profile store so user facts survive across sessions instead of being re-entered.*

- [x] **Stage 1.1 — Database Architecture & ORM Schema**
  - Configure SQLite engine with WAL mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`).
  - Implement SQLAlchemy models in `src/models.py`:
    - `Profile` (id, name, sections JSON, timestamps).
    - `ProfileFact` (id, profile_id, section, content, is_mandatory, embedding binary float32, created_at).
    - `JD` and `JDRequirement` (id, raw_text, structured JSON, role_type, category, importance).
    - `RunLog` and `Claim` (id, run feedback, claim text, 3-state enum, similarity scores).
  - Initialize Alembic migration scripts and create initial schema migration (`55641e2e17b1_initial_schema.py`).
  - Write unit tests in `tests/test_models.py` verifying constraints, foreign keys, cascades, and vector serialization.
- [x] **Stage 1.2 — Profile & Fact CRUD Service Layer**
  - Created `src/profile_service.py` with full CRUD for profiles and facts.
  - Implemented binary vector embedding (de)serialization via `set_embedding`/`get_embedding`.
  - Implemented `is_mandatory` metadata tagging (`infer_is_mandatory`) with structural-section and date/contact-content heuristics.
  - Added `tests/test_profile_service.py` (17 tests); full suite 29 passed.
- [x] **Stage 1.3 — Document Ingestion (DOCX / Resume Parser Integration)**
  - Created `src/resume_parser.py` — `parse_resume(text)` lowers raw resume text into a normalized structure (name, contact block, summary, sections incl. `experience`/`education`/`projects` entry parsing), `to_facts(structure)` flattens entries+bullets into discrete facts with `is_mandatory` metadata tagging.
  - Added `ingest_resume()` and `ingest_document()` to `src/profile_service.py` to auto-populate `Profile`/`ProfileFact` records on document upload (Stage 1.3 objective). `ingest_document()` bridges `src/parser.py:extract_text()` for path/bytes/plain-text sources.
  - Wrote `tests/test_resume_parser.py` (16 tests); full suite 45 passed.
- [x] **Stage 1.4 — REST Endpoints & Persistence Testing**
  - Add Flask routes in `app.py`:
    - `POST /api/profile` (Create profile; with `id` also updates)
    - `GET /api/profiles` (List profiles)
    - `GET /api/profile/<id>` (Get single profile)
    - `DELETE /api/profile/<id>` (Delete profile + cascade facts)
    - `GET /api/profile/<id>/facts` (List facts, `?section=` filter)
    - `POST /api/profile/<id>/facts` (Add fact)
    - `PUT /api/fact/<id>` (Update fact)
    - `DELETE /api/fact/<id>` (Delete fact)
    - `POST /api/profile/<id>/ingest` (Auto-populate from uploaded DOCX/PDF/TXT or `resume_text`)
  - Write test suite in `tests/test_profile_persistence.py`.
- [x] **Phase 1 Test & Verification Gate (Required before Phase 2)**
  - Full suite `pytest -q`: 57 passed (12 models + 17 service + 16 parser + 12 persistence), 0 failures.
  - `python -m py_compile` clean on `app.py` + touched modules.
  - Server restart persistence verified (DoD): profile created in one process visible in a fresh process against the same SQLite file.

---

### Phase 2: JD Structuring Engine (Estimated: 3 Days)
*Objective: Transform messy, unstructured Job Descriptions into normalized, categorized requirement objects.*

- [x] **Stage 2.1 — Text Cleaning & Boilerplate Filtering**
  - Implemented `src/jd_structuring.py` (stdlib-only, no models): `clean_jd_text()` strips EEO/legal/promo boilerplate at line level, `extract_company()` / `extract_job_title()` via regex + heuristics, `extract_sections()` groups lines under canonical headers (`requirements`/`responsibilities`/`qualifications`/`nice_to_have`/`about`/`benefits`/`other`), `structure_jd()` orchestrates to `{raw_text, cleaned_text, company, job_title, sections}`.
  - Wrote `tests/test_jd_structuring.py` (16 tests); full suite 73 passed.
- [x] **Stage 2.2 — KeyBERT Keyword & Skill Extraction**
  - Added `extract_keywords()` (KeyBERT uni+bigram, MMR, lazy singleton on shared `all-MiniLM-L6-v2`) and `extract_requirements()` (per-line taxonomy scan over ~70-skill `SKILL_TAXONOMY` + KeyBERT discovery mapped onto it; `nice_to_have` by section origin + cue regex `preferred|bonus|plus|familiarity|exposure|...`; required wins on conflict; importance-weighted + sorted).
  - `tests/test_jd_structuring.py` extended; full suite 84 passed.
- [x] **Stage 2.3 — Role-Type Classification & Persistence**
  - Added `classify_role_type()` (deterministic title override → embedding cosine vs 7 role anchors → keyword-overlap fallback; returns `backend|frontend|fullstack|data|devops|mobile|ml`) and `persist_jd()` (full pipeline → `JD` + `JDRequirement` rows with skill embeddings for Stage 3; optional-session pattern like `profile_service`).
  - Phase 2 gate: full suite 84 passed, `py_compile` clean.

---

### Phase 3: Scoring & Knapsack Allocation (Estimated: 4 Days)
*Objective: Implement deterministic, mathematical content selection using 0/1 Knapsack dynamic programming per resume section.*

- [x] **Stage 3.1 — Semantic Scoring Engine**
  - Implemented `src/scoring.py` on shared `all-MiniLM-L6-v2` singleton: `cosine_similarity_matrix()` (clip [0,1], precomputed-embedding reuse, defensive renormalize), `fuzzy_match_matrix()` (max(token_set, partial)/100), `score_facts()` → `v_i = max_j((alpha*cos + (1-alpha)*fuzz) * importance * category_weight)` with `required=1.0`/`nice_to_have=0.5`, best-match attribution, deterministic, empty-safe.
  - Wrote `tests/test_scoring.py` (13 tests); full suite 97 passed.
- [x] **Stage 3.2 — 0/1 Knapsack Dynamic Programming Allocator**
  - Implemented `src/allocator.py` (pure Python, no new deps): `allocate_section()` pins mandatory facts (always kept, even over capacity) and runs classic 1D 0/1 DP over optional bullets under remaining budget; `allocate_facts()` groups by section with per-section capacities (`DEFAULT_SECTION_CAPACITY` + override). Weights = `len(content)` chars, explicit `weight` override supported.
  - Wrote `tests/test_allocator.py` (12 tests: textbook greedy-failure optimality + 30-case brute-force fuzz, mandatory pinning, empty/zero/oversize/negative edges, determinism, grouping); full suite 109 passed.
- [x] **Stage 3.3 — Orchestration Pipeline Integration**
  - Wired score→allocate into `src/tailor.py`: `build_allocation_context(profile_id, jd_id)` (loads facts + JD requirements with stored embeddings → `score_facts()` → `allocate_facts()`), `render_allocated_resume_text()` (section-grouped prompt text), `tailor_resume_with_allocation()` (LLM sees ONLY the allocated subset — physical constraint — plus `ALLOCATION_SOURCE_NOTE` prompt constraint). `tailor_resume()` gained backward-compatible `source_note=""` (legacy prompts byte-identical).
  - Wrote `tests/test_orchestration.py` (6 tests: relevant-selected/filler-dropped, missing profile/JD errors, mocked-LLM prompt constraint, empty-profile error, render grouping).
- [x] **Stage 3.4 — Optimality & Edge-Case Verification**
  - Extended `tests/test_allocator.py` to 17 tests (greedy-failure + 30-seed brute-force proofs, all-mandatory/exact-capacity/multi-oversize/absent-capacity/mandatory-weight edges).
  - Phase 3 gate: full suite 120 passed, `py_compile` clean.

---

### Phase 4: Verification Layer (Highest Priority) (Estimated: 5 Days)
*Objective: Build an enforced 3-state verification system (Verified / Inferred / Unsupported) and deterministically block hallucinations.*

- [x] **Stage 4.1 — Claim Extraction & Citation Parser**
  - Allocation prompts now emit cited facts: `render_allocated_resume_text()` prefixes `[F<id>]` bullets (backward-compatible `with_ids=False`), `ALLOCATION_SOURCE_NOTE` requires per-bullet citations and bans uncited bullets as fabrication.
  - Created `src/claims.py`: `extract_claims()` parses bullets (`-/*/•/1.`) into `{text, cited_fact_ids, raw}` with continuation joining, header/blank handling, malformed-marker (`[F]/[Fx]/[12]`) tolerance, marker-only-bullet dropping.
  - Wrote `tests/test_claims.py` (12 tests, fixture outputs only, incl. mocked prompt→claims roundtrip); full suite 132 passed.
- [x] **Stage 4.2 — Hybrid Verification Pipeline**
  - Implemented `src/verifier.py`: `cosine_to_facts()` (shared MiniLM singleton, precomputed-embedding reuse) → `verify_claim()` fast path (≥0.85 Verified, ≤0.60 Unsupported) → borderline NLI via `cross-encoder/nli-MiniLM2-L6-H768` (entail→Verified, neutral→Inferred, contradict→Unsupported; softmax probs as scores). Cited facts checked first, uncited screened against all facts; NLI failure falls back to cosine midpoint (≥0.72 Inferred else Unsupported).
  - Wrote `tests/test_verifier.py` (14 tests: live identical/unrelated/paraphrase behavior, stubbed NLI label mapping, fallback paths, degenerate inputs); full suite 146 passed.
- [x] **Stage 4.3 — Hallucination Blocking & Output Sanitization**
  - `sanitize_text()` drops Unsupported bullets + continuations from generated text (headers/blanks/kept bullets verbatim) → `{sanitized_text, blocked, kept_count}`; `record_claims()` persists `{text, state, score, cited_fact_id}` rows to `claims` table (optional-session pattern, `ValueError` on missing run).
- [x] **Stage 4.4 — Adversarial Test Suite**
  - Extended `tests/test_verifier.py` to 17 tests: 6 live adversarials (fabricated metrics cited + uncited, unearned titles, absent skills) — 100% Unsupported; end-to-end blocking-rate test (2 legit verified + 6 fabricated → all 6 blocked, legit kept); citation-non-rescue test (exaggerated metric never Verifies).
  - Phase 4 gate: full suite 149 passed, `py_compile` clean.
- [x] **Stage 4.5 — Multi-Provider Abstraction (⏭️ SKIPPED)**
  - Decision: skip LiteLLM. Existing `_call_ai()` dispatcher covers Claude/Gemini with zero deps; LiteLLM adds value only with OpenAI support or managed retry/cost tracking — neither required. Revisit if OpenAI provider is requested.

---

### Phase 5: Weakest-Section Feedback Loop (Estimated: 2 Days)
*Objective: Provide actionable, explainable feedback on resume gaps and enable iterative profile editing.*

- [x] **Stage 5.1 — Gap Analysis & Weakest-Section Detector**
  - Implemented `src/feedback.py`: `analyze_gaps()` per-section required-skill coverage (matched = best_match + fuzzy ≥ 0.8 exact-mention rule or blended cosine/fuzzy ≥ 0.5; utility-only fallback), weakest = lowest coverage (utility tie-break, clean-sheet → None), precise reasoning strings ("Matched 1/2 required skills in Experience; missing: Docker").
  - `build_feedback()` orchestrates allocation context + requirements; `diff_feedback()` per-section deltas (newly_matched/newly_missing).
- [x] **Stage 5.2 — Re-Run & Differential Reporting Endpoint**
  - `create_feedback_run()` persists completed RunLogs with feedback JSON; `rerun_feedback(run_id)` rebuilds post-edit + persists new run + coverage diff. `app.py`: `POST /api/runs`, `POST /api/runs/<id>/rerun`, `GET /api/runs/<id>` (404/400/422 mapping).
- [x] **Stage 5.3 — Feedback Verification & Tests**
  - Wrote `tests/test_feedback.py` (10 tests: gap units, missing-skill naming, edit→rerun improvement with `newly_matched == [Kubernetes]`, API flow + validation errors); full suite 159 passed. Phase 5 gate: `py_compile` clean.

---

### Phase 6: Evaluation Harness & Benchmarking (Estimated: 4 Days)
*Objective: Rigorously benchmark KnapResume against the baseline prompt-only approach on realistic test fixtures.*
*CLI foundation (DONE 2026-09-29): `main.py phase6-batch` runs the whole pipeline in CLI only — folder JD PDFs in → allocation → LLM tailor → claim verify/sanitize → feedback → cover letter → PDF export (+ `RunLog`/`Claim` persist, per-run + summary bottleneck reports). PDF outputs KEPT, no text-file outputs (user decision).*

- [ ] **Stage 6.1 — Fixture Dataset Construction**
  - Create 10–15 realistic test pairs of user profiles and job descriptions across various CSE/SE specializations.
- [x] **Stage 6.2 — Metric Collection Pipeline (`src/evaluation.py`)**
  - Collect metrics: Keyword match rate, ATS density, fabrication rate (% unsupported), knapsack capacity utilization.
  - DONE: four deterministic functions (`compute_keyword_match_rate` = matched-anywhere required union, `compute_ats_density` = mentions/100w saturated at 10, `compute_fabrication_rate` = unsupported/total, `compute_knapsack_utilization` = weight/capacity) + `compute_metrics()` per arm. Offline-tested in `tests/test_evaluation.py`.
- [x] **Stage 6.3 — Comparative Benchmark Execution (`evaluate_texts` + `evaluate_profile_jd` + `phase6-eval` CLI)**
  - Execute comparative runs: *Baseline (rotsl prompt-only)* vs. *KnapResume (Knapsack + Verifier)*.
  - DONE: pure `evaluate_texts()` (baseline utilization = 0, no allocator) + DB/LLM `evaluate_profile_jd()` with injectable tailor/verify fns (tests stay offline) + `main.py phase6-eval` (live LLM both arms). Live benchmark run pending API-cost decision.
- [x] **Stage 6.4 — Results Visualizations & Documentation (`save_report`)**
  - Generate comparison tables and charts (via `pandas` and `matplotlib`).
  - DONE: `save_report()` emits `report.md` + `results.csv` + `chart.png` (grouped baseline-vs-knap bars) + `summary.json`; covered by artifact-existence test. Root `Evaluation_Report.md` from live data pending the 6.3 live run.

---

### Phase 7: Export, Integration & Final Polish (Estimated: 3 Days)
*Objective: Complete end-to-end integration, ATS keyword checklist, ReportLab export formatting, and final documentation.*

- [x] **Stage 7.1 — ATS Keyword Checklist & UI Integration**
  - Lightweight checklist (`grade` A–D, `coverage`, `matched`/`missing`, per-skill `items`) built in `src/feedback.py:build_ats_checklist`, re-exported via `src/evaluation.py`; returned by `POST /api/runs`, `POST /api/runs/<id>/rerun`, `GET /api/runs/<id>`; persisted on `RunLog.feedback`; rendered in `docs/index.html:scorecardHTML` (checklist-first, section bars fallback; also fixed a latent `(count).map` crash in the old matched-chips path). Tests: 3 new in `tests/test_feedback.py`.
- [x] **Stage 7.2 — PDF Generator Alignment & Final Polish**
  - Verified, no code changes: ReportLab flowables (`_P` escape choke point, ASCII normalization, header guards, KeepTogether) covered by `tests/test_pdf_generator.py` (8); SQLite run persistence (`run_logs` + `claims`, restart-safe downloads) covered by `tests/test_tailor_runs.py` (4); served UI pins in `tests/test_pipeline_api.py`. Re-ran 27/27 green.
- [x] **Stage 7.3 — Full End-to-End Smoke Test & Documentation**
  - New offline `tests/test_e2e_smoke.py`: profile → facts → JD → allocation (budget respected) → feedback + checklist → cited-claims extract/verify/sanitize → PDF export → `RunLog` + `Claim` persistence. `README.md` refreshed (ATS checklist, eval outputs, `phase6-batch`/`phase6-eval` commands, status).
  - Phase 7 gate: full suite 204 passed, `py_compile` clean.

---

## 🚀 Version 2.0 Roadmap: LaTeX Template Engine, Structured Generation & ATS Valuation

```
Legend:
[x] Completed
[/] In Progress
[ ] Pending
[!] Blocked
```

### Phase v2.1: Schema Definition & LaTeX Engine Foundation (Estimated: 2 Days)
*Objective: Build type-safe Pydantic models for structured resume output and implement a LaTeX-safe Jinja2 rendering engine with standard templates.*

- [ ] **Stage v2.1.1 — Structured JSON Schemas (`src/schemas.py`)**
  - Implement Pydantic models: `ContactInfo`, `CategorizedSkills`, `ExperienceItem`, `EducationItem`, `ProjectItem`, `ResumeData`, and `CoverLetterData`.
  - Add validator hooks ensuring bullet points carry `[F<id>]` fact citations.
- [ ] **Stage v2.1.2 — LaTeX Template Engine (`src/latex_engine.py`)**
  - Setup Jinja2 environment with LaTeX-safe delimiters (`\BLOCK{...}`, `\VAR{...}`, `\#{...}`).
  - Implement comprehensive LaTeX character escaping (`_`, `&`, `%`, `$`, `#`, `{`, `}`, `~`, `^`, `\`, `<`, `>`).
- [ ] **Stage v2.1.3 — Built-in Templates Scaffolding (`templates/latex/`)**
  - Create default templates: `classic_ats.tex` (standard single-column), `modern_tech.tex` (skill chips/navy headers), `compact_single_page.tex` (0.4in margins), `academic_entry.tex`.
  - Write test suite (`tests/test_latex_engine.py`) verifying escaping, delimiters, and sample generation.

---

### Phase v2.2: Structured LLM Generation & Verification Integration (Estimated: 3 Days)
*Objective: Update the LLM prompting and claim verification pipeline to operate directly on JSON structures rather than plain markdown.*

- [ ] **Stage v2.2.1 — Structured Prompt Dispatcher (`src/tailor.py`)**
  - Implement `tailor_resume_structured()` instructing the LLM to output conforming `ResumeData` JSON with `[F<id>]` citations inside bullets.
  - Implement defensive JSON extractor handling potential markdown code-block wrapping.
- [ ] **Stage v2.2.2 — Direct JSON Claim Verification & Sanitization (`src/verifier.py`)**
  - Update `claims.py` and `verifier.py` to traverse `ResumeData.experience` and `projects` bullet arrays directly.
  - Automatically strip unsupported bullets directly from the JSON structure prior to template compilation.
- [ ] **Stage v2.2.3 — Deterministic ReportLab JSON Fallback (`src/pdf_generator.py`)**
  - Implement `render_resume_data(resume_data: ResumeData)` in ReportLab providing a zero-regex, guaranteed-success direct PDF builder.

---

### Phase v2.3: Multi-Tier Compilation Waterfall & API Endpoints (Estimated: 2 Days)
*Objective: Implement a resilient compilation strategy that works locally, in Docker, or on cloud platforms without failing.*

- [ ] **Stage v2.3.1 — Compilation Waterfall Manager (`src/latex_compiler.py`)**
  - Tier 1: Local / Container Binary (`tectonic` on-demand package fetching or `pdflatex`).
  - Tier 2: Remote Microservice API (`LATEX_API_URL` calling self-hosted Gotenberg or latexonline.cc).
  - Tier 3: Zero-dependency ReportLab JSON builder fallback.
  - Tier 4: Direct export ("Open in Overleaf" URL generation + `.tex`/`.zip` bundle creation).
- [ ] **Stage v2.3.2 — Web API Integration (`app.py`)**
  - Expose `/api/templates` (list available templates and metadata).
  - Add `/api/runs/<id>/tex`, `/api/runs/<id>/zip`, and `/api/runs/<id>/recompile` (re-render with different template/margins).

---

### Phase v2.4: 5-Dimension ATS Valuation & Scorecard Engine (Estimated: 2 Days)
*Objective: Implement an objective, comprehensive ATS scoring and audit engine evaluating the completed resume.*

- [ ] **Stage v2.4.1 — ATS Evaluator Core (`src/ats_evaluator.py`)**
  - Dimension 1: Keyword & Hard Skill Matching (35% weight, contextual placement bonus in bullets).
  - Dimension 2: Parseability & Structural Compliance (20% weight, contact info, standard headers, clean ASCII).
  - Dimension 3: Google XYZ Formula Impact & Action Verb Density (20% weight, metrics check).
  - Dimension 4: Section Organization & Relevance Hierarchy (15% weight).
  - Dimension 5: Spatial Length & Page Fit (10% weight, single-page budget compliance).
- [ ] **Stage v2.4.2 — Valuation API & Scorecard Generation**
  - Return detailed audit scorecard with grade (A/B/C/D), numerical score (0-100), breakdown bars, and actionable gap recommendations.

---

### Phase v2.5: Section-Healing Improver Loop (Estimated: 2 Days)
*Objective: Autonomously optimize weak sections through targeted multi-pass rewrites guided by the ATS Scorecard.*

- [ ] **Stage v2.5.1 — Surgical Section Improver (`src/improver.py`)**
  - Trigger rewrite loop if composite ATS score $< 85$ or weakest section coverage $< 80\%$.
  - Prompt LLM to rewrite ONLY the targeted section JSON using specific missing facts.
  - Re-verify citations and track composite iteration quality scores.

---

### Phase v2.6: SPA UI Integration & Multi-Format Exporter (Estimated: 2 Days)
*Objective: Polish user experience with template controls, live ATS scorecard, and one-click export actions.*

- [ ] **Stage v2.6.1 — Multi-Format Exporter (`src/export_engine.py`)**
  - Implement Word `.docx` exporter via `python-docx` using `ResumeData`.
  - Implement JSON Resume standard (`jsonresume.org`) schema exporter.
- [ ] **Stage v2.6.2 — Frontend Scorecard & Template Switcher (`docs/index.html`)**
  - Add template selector dropdown (Classic ATS, Modern Tech, Compact Single-Page).
  - Add interactive ATS Valuation Scorecard with progress meters, matched skill badges, and Overleaf launch button.

---

## 📈 Completed Milestones Log

| Date | Phase / Stage | Summary of Completion |
|---|---|---|
| **2026-09-16** | Stage 0.1 | System design review completed; architecture constraints validated; `progress.md` and `Journey.md` established. |
| **2026-09-16** | Stage 0.2 | Codebase pruned: removed Notion MCP server/client modules, setup scripts, pruned requirements.txt, and updated app/CLI branding. |
| **2026-09-16** | Stage 0.3 | Baseline CLI (`main.py`) & Flask (`app.py`) execution, parser extraction, and ReportLab PDF generation verified. |
| **2026-09-16** | Stage 0.4 | Dependencies added to `requirements.txt`, `src/database.py` scaffolded with SQLite WAL pragma listeners, and `tests/conftest.py` in-memory SQLite fixtures created. Phase 0 complete. |
| **2026-09-16** | Stage 1.1 | SQLAlchemy ORM models implemented in `src/models.py`, Alembic migrations configured & executed, binary float32 vector serialization verified, pytest suite passing 100%. |
| **2026-09-21** | Cross-cutting | Centralized logging added via `src/logger.py` (console + optional rotating file, `KNAP_LOG_LEVEL`/`KNAP_LOG_FILE`); wired into `app.py` (job lifecycle + request logging), `main.py` CLI, `tailor.py` (provider/model/latency), `parser.py`, `pdf_generator.py`, `web_context.py`, and `database.py`. API keys never logged. 6/6 tests passing. |
| **2026-09-21** | Stage 1.2 | Profile & Fact service layer implemented in `src/profile_service.py`: full CRUD, binary float32 embedding serialization, `is_mandatory` metadata tagging via `infer_is_mandatory`. Added `tests/test_profile_service.py` (17 tests). Full suite: 29 passed. |
| **2026-09-24** | Stage 1.3 | Document ingestion implemented: `src/resume_parser.py` (`parse_resume`/`to_facts`) + `ingest_resume()`/`ingest_document()` in `src/profile_service.py`. Added `tests/test_resume_parser.py` (16 tests). Full suite: 45 passed. Tracker synced (dashboard → Stage 1.4, fixed `parse_document()` naming error). |
| **2026-09-24** | Stage 1.4 + Phase 1 Gate | REST endpoints wired in `app.py` (`POST /api/profile`, `GET /api/profiles`, `GET/DELETE /api/profile/<id>`, `GET/POST /api/profile/<id>/facts`, `PUT/DELETE /api/fact/<id>`, `POST /api/profile/<id>/ingest`) with 404/400/422 mapping + `init_db()` at startup. Added `tests/test_profile_persistence.py` (12 tests). Full suite: 57 passed. Restart persistence verified. Phase 1 complete → Phase 2. |
| **2026-09-24** | Stage 2.1 | Text cleaning & boilerplate filtering implemented in `src/jd_structuring.py` (stdlib-only: `clean_jd_text`, `extract_company`, `extract_job_title`, `extract_sections`, `structure_jd`). Added `tests/test_jd_structuring.py` (16 tests). Full suite: 73 passed (venv python; system python lacks reportlab). |
| **2026-09-24** | Stage 2.2 + 2.3, Phase 2 Gate | Keyword extraction (`extract_keywords` KeyBERT MMR + `extract_requirements` taxonomy-mapped, cue-split) and role classification (`classify_role_type` title→embedding→keyword-fallback) + `persist_jd()` (`JD`/`JDRequirement` rows with embeddings). Extended `tests/test_jd_structuring.py` to 27 tests. Full suite: 84 passed. Phase 2 complete → Phase 3. |
| **2026-09-24** | Stage 3.1 | Semantic scoring engine in `src/scoring.py` (cosine matrix + max(token_set,partial) fuzzy blend, importance × category weights, precomputed-embedding reuse). Added `tests/test_scoring.py` (13 tests). Full suite: 97 passed. |
| **2026-09-24** | Stage 3.2 | 0/1 knapsack DP allocator in `src/allocator.py` (mandatory pinned, char weights, per-section capacities). Added `tests/test_allocator.py` (12 tests incl. brute-force optimality proofs). Full suite: 109 passed. |
| **2026-09-24** | Stage 3.3 + 3.4, Phase 3 Gate | Orchestration wired into `src/tailor.py` (`build_allocation_context`, `render_allocated_resume_text`, `tailor_resume_with_allocation` with physical + prompt subset constraints; backward-compatible `source_note`). Added `tests/test_orchestration.py` (6 tests) and extended `test_allocator.py` to 17. Full suite: 120 passed. Phase 3 complete → Phase 4. |
| **2026-09-24** | Stage 4.1 | Cited-fact prompts (`[F<id>]` bullets + citation mandate in allocation note) and `src/claims.py` extractor (`extract_claims` → `{text, cited_fact_ids, raw}`). Added `tests/test_claims.py` (12 tests). Full suite: 132 passed. |
| **2026-09-24** | Stage 4.2 + 4.3 | Hybrid verifier in `src/verifier.py` (cosine fast path + MiniLM2 NLI borderline judging, cited-first/uncited-screens-all, cosine-midpoint NLI fallback) plus `sanitize_text()` blocker and `record_claims()` persistence. Added `tests/test_verifier.py` (14 tests). Full suite: 146 passed. |
| **2026-09-24** | Stage 4.4 + 4.5, Phase 4 Gate | Adversarial suite: 6 live fabrications at 100% Unsupported + end-to-end 100% blocking with legit preserved (`test_verifier.py` → 17 tests). Stage 4.5 LiteLLM SKIPPED (dispatcher sufficient; revisit for OpenAI). Full suite: 149 passed. Phase 4 complete → Phase 5. |
| **2026-09-24** | Stage 5.1 + 5.2 + 5.3, Phase 5 Gate | Feedback loop in `src/feedback.py` (gap analysis, run/rerun with RunLog persistence, diffs) + `/api/runs` endpoints in `app.py`. Added `tests/test_feedback.py` (10 tests incl. edit→rerun improvement). Full suite: 159 passed. Phase 5 complete → Phase 6. |
| **2026-09-24** | Pre-Phase-6 UI integration | Connected frontend to the implemented flow: new `POST/GET /api/jds` (+ `raw_text` on single-JD) and `POST /api/allocate` (embedding-stripped, JSON-safe) routes; rebuilt `docs/index.html` around profile → ingest/curate facts → structure JD → run/rerun feedback with diffs → backend tailor + PDF downloads (fixed stale Notion badge/branding). Added `tests/test_pipeline_api.py` (7 tests). Full suite: 166 passed. |
| **2026-09-24** | Multi-view SPA + JD chats (1:N) | Split UI into 3 views (1 Profile build/select → 2 Facts ingest/curate → 3 WhatsApp-like chats, one thread per JD under a profile). New `ChatThread` model + Alembic migration (`1480e95b0f1c`) with chat CRUD/attach endpoints (thread cards carry JD summary + latest run; detail carries JD + runs timeline; runs survive thread deletion). Added `tests/test_chats.py` (8 tests). Full suite: 174 passed. |
| **2026-09-24** | Tailor→chat integration | Tailor completions now post into chat timelines: `/api/tailor` accepts `profile_id`/`jd_id`, `_run()` persists a `kind=tailor` RunLog with PDF paths (also fixed a latent `started_at` KeyError that failed EVERY tailor job), new restart-safe `GET /api/runs/<id>/download/<doc>`, chat bubbles with persistent download links. Added `tests/test_tailor_runs.py` (4 tests). Full suite: 178 passed. |
| **2026-09-24** | Attach-JD file drop | Replaced the `prompt()`-based chat JD attach with a 3-tab modal (paste text / drop PDF-DOCX-TXT-MD file / pick existing structured job); file path reuses server-side `extract_text` via `POST /api/jds`. Served-page test now pins the modal + no-`prompt()` rule. Full suite: 178 passed. |
| **2026-09-24** | PDF formatting overhaul | Fixed `src/pdf_generator.py`: XML-escape choke point (`_P()` — `<products>`/`R&D` no longer eaten or mangled), Unicode→ASCII normalization (`•/·/–/—` rendered as `(cid:127)`/`?` in Helvetica — now `-`), header guards (date lines / `A \| B` caps lines no longer misread as sections), fence stripping, identifier-safe markdown (no more single-`*`/`_` stripping), KeepTogether section headers, pre-build flowable count. Added `tests/test_pdf_generator.py` (8 round-trip tests). Full suite: 186 passed. |
| **2026-09-24** | Repo tidy: docs/design + samples | Sorted the root: 4 design docs → `docs/design/` (relative cross-links intact), 3 sample PDFs → `samples/`; kept `instruct.md` at root (code dependency of `tailor.py`), agent ops files + entry points untouched. Refreshed the `Agent.md` file map (incl. new modules/tests). Full suite: 186 passed. |
| **2026-09-29** | UI/UX redesign: Light ATS-clean SPA | Rebuilt `docs/index.html` (light design system, one primary action per surface, ATS scorecard A–D with matched/missing chips in analysis bubbles, fact filter chips + inline edit + ☆/★ mandatory toggle, toasts, labeled 5-step tailor progress, allocation inspector with utility + char-budget, thread gap/✓ flags, labeled inputs, focus rings, dialog semantics, Esc/`/` shortcuts, reduced-motion support). Single-file kept (multi-page evaluated and rejected: Flask placeholder serving, zero-build Pages demo, served-UI test pins). No backend changes. Full suite: 186 passed. |
| **2026-09-29** | Privacy policy refresh | Rewrote `docs/privacy.html` (KnapResume branding, light theme, accurate local-vs-sent data map: SQLite/`outputs/`/`.env` stays local; Claude/Gemini + optional Brave Search on user trigger; removed Notion/mobile/ads/OpenAI fiction). Effective date 2026-09-29. Pipeline UI tests: 7 passed. |
| **2026-09-29** | Phase 6 CLI batch pipeline (folder JD PDFs) | Added `main.py` command `phase6-batch` to process one/many JD PDFs from a folder against an existing profile id (no dummy profile generation), run full allocation→tailor→claim verify→sanitize→feedback→PDF flow, persist `RunLog` + `Claim` rows, classify bottlenecks (`profile_facts_low`, `scoring_alignment`, `verification_risk`, `pdf_generation`, latency classes), and emit per-run + summary reports (`summary.md`/`summary.json`) with batch/linear sleeps. Added `tests/test_phase6_batch_cli.py` (7 tests), all passing. |
| **2026-09-29** | Phase 6 CLI decision: PDF kept, no text | User decision locked: `phase6-batch` keeps PDF outputs (`run_root/pdf/*.pdf`, `resume_pdf_path`/`cover_pdf_path` on `RunLog`), no tailored-text (`.md`/`.txt`) outputs. Reverted interim text-only draft back to PDF stage (`pdf` + `pdf_failed` bottleneck paths). Stages 6.2/6.3 marked `[/]` In Progress (CLI foundation), 6.1/6.4 still `[ ]`. Full suite: 193 passed. |
| **2026-09-29** | Stages 6.2–6.4 code-complete | Built `src/evaluation.py` (4 deterministic metrics, `evaluate_texts`/`evaluate_profile_jd` with injectable LLM/verify fns, `save_report` with pandas CSV + matplotlib chart) + `main.py phase6-eval` CLI (live baseline-vs-knap on one profile+JD). Added `tests/test_evaluation.py` (7 tests, offline). Full suite: 200 passed. Remaining: 6.1 fixtures + live benchmark run + root `Evaluation_Report.md` from live data. |
| **2026-09-29** | Phase 7 complete (7.1 + 7.2 + 7.3) | 7.1 ATS checklist (`build_ats_checklist` in `feedback.py`, API + stored + UI scorecard, 3 tests). 7.2 PDF/persistence verified (27/27, no code changes). 7.3 offline E2E smoke (`tests/test_e2e_smoke.py`) + README refresh. Phase 7 gate: 204 passed, `py_compile` clean. |
