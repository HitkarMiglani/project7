# KnapResume — Project Progress Tracker

> **Tracking Document:** `progress.md`  
> **Purpose:** Dictates the phase-wise and stage-wise build plan, tracks real-time completion status, and defines the immediate next task to be picked up.  
> **Paired Document:** `Journey.md` (captures iterative reasoning, technical decisions, architectural choices, and change history).

---

## 📊 Project Status Dashboard

- **Current Phase:** Phase 0 — Fork & Orient
- **Current Stage:** Stage 0.3 — Baseline Execution Verification
- **Overall Completion:** 10%
- **Status:** 🟢 Ready for Execution

| Phase | Description | Target Timeline | Status | Stages Total | Stages Completed |
|---|---|---|---|---|---|
| **Phase 0** | Fork & Orient | 1 day | 🔄 In Progress | 4 | 2 |
| **Phase 1** | Profile Persistence Layer | 4 days | ⏳ Pending | 4 | 0 |
| **Phase 2** | JD Structuring Engine | 3 days | ⏳ Pending | 3 | 0 |
| **Phase 3** | Scoring & Knapsack Allocation | 4 days | ⏳ Pending | 4 | 0 |
| **Phase 4** | Verification Layer (3-State) | 5 days | ⏳ Pending | 5 | 0 |
| **Phase 5** | Weakest-Section Feedback Loop | 2 days | ⏳ Pending | 3 | 0 |
| **Phase 6** | Evaluation Harness & Benchmarking | 4 days | ⏳ Pending | 4 | 0 |
| **Phase 7** | Export, Integration & Final Polish | 3 days | ⏳ Pending | 3 | 0 |

---

## 🎯 What is Next to be Picked Up (Immediate Action Item)

1. **Phase 0 — Stage 0.3**: Verify existing CLI (`main.py`) and local Flask server (`app.py`) workflow end-to-end with sample inputs.
2. **Phase 0 — Stage 0.4**: Audit dependencies and prepare modular layout in `src/` for Phase 1.

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

### Phase 0: Fork & Orient (Estimated: 1 Day)
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
- [/] **Stage 0.3 — Baseline Execution Verification**
  - Verify local execution paths for `main.py` (CLI) and `app.py` (Flask server).
  - Verify ReportLab PDF generation with sample inputs (`pdf_generator.py`).
  - Test parser capabilities for PDF/DOCX/TXT (`parser.py`).
- [ ] **Stage 0.4 — Dependency & Structure Preparation**
  - Audit `requirements.txt` and map out new packages (`sqlalchemy`, `alembic`, `sentence-transformers`, `keybert`, `rapidfuzz`).
  - Establish `src/` modular layout for upcoming engines (`storage`, `structuring`, `scoring`, `allocator`, `verifier`, `feedback`).

---

### Phase 1: Profile Persistence Layer (Estimated: 4 Days)
*Objective: Build persistent, SQLite-backed profile store so user facts survive across sessions instead of being re-entered.*

- [ ] **Stage 1.1 — Database Architecture & ORM Schema**
  - Configure SQLite engine with WAL mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`).
  - Implement SQLAlchemy models in `src/models.py`:
    - `Profile` (id, name, sections JSON, timestamps).
    - `ProfileFact` (id, profile_id, section, content, embedding BLOB/bytes, created_at).
    - `JD` and `JDRequirement` (id, raw_text, structured JSON, role_type, category, importance).
    - `RunLog` and `Claim` (id, run feedback, claim text, 3-state enum, similarity scores).
  - Initialize Alembic migration scripts and create initial schema migration.
- [ ] **Stage 1.2 — Profile & Fact CRUD Service Layer**
  - Create `src/profile_service.py` to handle creation, retrieval, updates, and deletion of profile facts.
  - Implement binary vector serialization (`np.ndarray.tobytes()` and `np.frombuffer()`) for embeddings storage.
  - Implement base metadata vs optional achievement fact tagging.
- [ ] **Stage 1.3 — Document Ingestion (DOCX / Resume Parser Integration)**
  - Integrate `python-docx` parsing in `src/parser.py` to extract structured profile sections.
  - Auto-populate `Profile` and `ProfileFact` records on document upload.
- [ ] **Stage 1.4 — REST Endpoints & Persistence Testing**
  - Add Flask routes in `app.py`:
    - `POST /api/profile` (Create/Update profile)
    - `GET /api/profile/<id>/facts` (List facts)
    - `POST /api/profile/<id>/facts` (Add fact)
    - `PUT /api/fact/<id>` (Update fact)
    - `DELETE /api/fact/<id>` (Delete fact)
  - Write pytest suite in `tests/test_profile_persistence.py` verifying facts persist across server restarts.

---

### Phase 2: JD Structuring Engine (Estimated: 3 Days)
*Objective: Transform messy, unstructured Job Descriptions into normalized, categorized requirement objects.*

- [ ] **Stage 2.1 — Text Cleaning & Boilerplate Filtering**
  - Implement `src/jd_structuring.py` to strip standard EEO boilerplate, legal disclaimers, and company promo text.
  - Extract company name, role title, and core requirement sections using regex and heuristic parsing.
- [ ] **Stage 2.2 — KeyBERT Keyword & Skill Extraction**
  - Integrate `KeyBERT` to extract unigram and bigram candidate technical skills and requirements.
  - Separate requirements into `required_skills` vs `nice_to_have` using linguistic cues and section headers.
- [ ] **Stage 2.3 — Role-Type Classification & Persistence**
  - Classify role type (Backend, Frontend, Fullstack, Data, DevOps, Mobile, ML) using embedding cosine similarity against a fixed role taxonomy.
  - Store structured JD output into `JD` and `JDRequirement` tables.
  - Write unit tests in `tests/test_jd_structuring.py` against standard tech job postings.

---

### Phase 3: Scoring & Knapsack Allocation (Estimated: 4 Days)
*Objective: Implement deterministic, mathematical content selection using 0/1 Knapsack dynamic programming per resume section.*

- [ ] **Stage 3.1 — Semantic Scoring Engine**
  - Implement `src/scoring.py` using `sentence-transformers/all-MiniLM-L6-v2`.
  - Compute cosine similarity matrix between candidate profile facts and structured JD requirements.
  - Combine semantic similarity with exact/fuzzy token matching (`rapidfuzz`) to compute net fact utility $v_i$.
- [ ] **Stage 3.2 — 0/1 Knapsack Dynamic Programming Allocator**
  - Implement `src/allocator.py` with pure Python 0/1 Knapsack DP algorithm:
    $$\text{Maximize } \sum v_i x_i \quad \text{subject to} \quad \sum w_i x_i \le W$$
  - Define integer weights $w_i$ (character/bullet length) and section capacity $W$.
  - Ensure mandatory structural facts (company name, role title, dates, education institution) are preserved while optimizing optional achievement bullets.
- [ ] **Stage 3.3 — Orchestration Pipeline Integration**
  - Wire allocator output into `src/tailor.py` before the LLM prompt is assembled.
  - Constrain LLM rewriting strictly to the mathematically selected subset of facts.
- [ ] **Stage 3.4 — Optimality & Edge-Case Verification**
  - Write unit tests in `tests/test_allocator.py` proving provable global optimality on synthetic small test cases.
  - Test edge cases: empty sections, zero capacity, facts exceeding section capacity.

---

### Phase 4: Verification Layer (Highest Priority) (Estimated: 5 Days)
*Objective: Build an enforced 3-state verification system (Verified / Inferred / Unsupported) and deterministically block hallucinations.*

- [ ] **Stage 4.1 — Claim Extraction & Citation Parser**
  - Update prompt templates in `src/tailor.py` to produce structured bullet claims linked to cited fact IDs.
  - Implement claim extractor to parse generated resume output into discrete, testable claim statements.
- [ ] **Stage 4.2 — Hybrid Verification Pipeline**
  - Implement `src/verifier.py`:
    - Fast embedding cosine pre-screen against cited facts:
      - Score $\ge 0.85 \implies \text{\textbf{Verified}}$
      - Score $\le 0.60 \implies \text{\textbf{Unsupported}}$
    - Borderline claims ($0.60 < \text{Score} < 0.85$) evaluated via small NLI cross-encoder (`cross-encoder/nli-MiniLM2-L6-H768`).
      - Entailment $\implies \text{\textbf{Verified}}$
      - Neutral $\implies \text{\textbf{Inferred}}$
      - Contradiction $\implies \text{\textbf{Unsupported}}$
- [ ] **Stage 4.3 — Hallucination Blocking & Output Sanitization**
  - Filter out or flag any `Unsupported` claims before passing text to PDF generation.
  - Record claim states and similarity scores in `claims` table.
- [ ] **Stage 4.4 — Adversarial Test Suite**
  - Create adversarial test cases in `tests/test_verifier.py` injecting fabricated metrics, unearned titles, and absent skills.
  - Ensure 100% detection and blocking rate on unsupported claims.
- [ ] **Stage 4.5 — Multi-Provider Abstraction (Optional LiteLLM)**
  - Validate `_call_ai()` dispatcher across Claude / Gemini / OpenAI; evaluate if LiteLLM package is needed.

---

### Phase 5: Weakest-Section Feedback Loop (Estimated: 2 Days)
*Objective: Provide actionable, explainable feedback on resume gaps and enable iterative profile editing.*

- [ ] **Stage 5.1 — Gap Analysis & Weakest-Section Detector**
  - Implement `src/feedback.py` to identify sections with the lowest requirement coverage or keyword overlap.
  - Generate precise explanation strings (e.g., *"Matched 2/5 required skills in Experience; missing: Docker, Kubernetes"*).
- [ ] **Stage 5.2 — Re-Run & Differential Reporting Endpoint**
  - Add API support for rapid re-runs after fact edits (`POST /api/rerun/<job_id>`).
  - Store iteration feedback in `run_logs` table.
- [ ] **Stage 5.3 — Feedback Verification & Tests**
  - Write test in `tests/test_feedback.py` verifying that editing profile facts directly updates feedback metrics on the subsequent run.

---

### Phase 6: Evaluation Harness & Benchmarking (Estimated: 4 Days)
*Objective: Rigorously benchmark KnapResume against the baseline prompt-only approach on realistic test fixtures.*

- [ ] **Stage 6.1 — Fixture Dataset Construction**
  - Create 10–15 realistic test pairs of user profiles and job descriptions across various CSE/SE specializations.
- [ ] **Stage 6.2 — Metric Collection Pipeline**
  - Collect metrics: Keyword match rate, ATS density, fabrication rate (% unsupported), knapsack capacity utilization.
- [ ] **Stage 6.3 — Comparative Benchmark Execution**
  - Execute comparative runs: *Baseline (rotsl prompt-only)* vs. *KnapResume (Knapsack + Verifier)*.
- [ ] **Stage 6.4 — Results Visualizations & Documentation**
  - Generate comparison tables and charts (via `pandas` and `matplotlib`).
  - Publish benchmark findings in `Evaluation_Report.md`.

---

### Phase 7: Export, Integration & Final Polish (Estimated: 3 Days)
*Objective: Complete end-to-end integration, ATS keyword checklist, ReportLab export formatting, and final documentation.*

- [ ] **Stage 7.1 — ATS Keyword Checklist & UI Integration**
  - Add lightweight ATS checklist data to the API response and web UI (`docs/index.html`).
- [ ] **Stage 7.2 — PDF Generator Alignment & Final Polish**
  - Verify ReportLab flowable styling for verified tailored resumes and cover letters in `src/pdf_generator.py`.
  - Finalize SQLite run persistence integration (`run_logs` and `claims` tables).
- [ ] **Stage 7.3 — Full End-to-End Smoke Test & Documentation**
  - Run comprehensive E2E smoke tests from profile ingestion $\to$ JD parsing $\to$ Knapsack allocation $\to$ LLM generation $\to$ Verification $\to$ PDF export.
  - Finalize `README.md` and user guide.

---

## 📈 Completed Milestones Log

| Date | Phase / Stage | Summary of Completion |
|---|---|---|
| **2026-09-16** | Stage 0.1 | System design review completed; architecture constraints validated; `progress.md` and `Journey.md` established. |
| **2026-09-16** | Stage 0.2 | Codebase pruned: removed Notion MCP server/client modules, setup scripts, pruned requirements.txt, and updated app/CLI branding. |
