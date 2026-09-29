# KnapResume — Agent Onboarding & Operating Guide (`Agent.md`)

> **Target Audience:** AI CLI agents, automated sessions, and engineers picking up work on KnapResume.  
> **Mission:** Build a deterministic, ATS-optimized resume tailoring system combining **0/1 Knapsack Dynamic Programming content allocation**, **LLM rewriting**, and **3-State NLI hallucination verification** in a lightweight, local-first Python stack.

---

## 1. Executive Summary & Core Philosophy

KnapResume solves the problem of manual, time-consuming resume customization for competitive tech roles. Unlike naive prompt-only wrappers that hallucinate experience or select facts stochastically:
1. **Facts Persist**: Candidate experience is stored once as structured facts in a local SQLite database (`knapresume.db`).
2. **Deterministic Selection**: Facts are scored semantically against extracted job requirements and selected via a **0/1 Knapsack Dynamic Programming algorithm** constrained by section capacity.
3. **Strict Verification**: LLM-generated bullet claims are verified against cited facts using a hybrid **Cosine Pre-Screen + Small NLI Cross-Encoder** pipeline (`Verified` / `Inferred` / `Unsupported`). Unsupported claims are deterministically blocked from final PDFs.
4. **Zero Overhead**: Fully self-contained local Python application (SQLite WAL mode, Flask, ReportLab, MiniLM models). No external database servers, no Node.js processes, no paid SaaS dependencies.

---

## 2. Codebase Architecture & File Map

```
proj/
├── app.py                     # Flask web server (serves web UI + REST API endpoints)
├── main.py                    # Interactive Typer + Rich CLI tool
├── requirements.txt           # Curated Python dependencies
├── alembic.ini                # Alembic database migration config
├── .env.example               # Template for API keys (ANTHROPIC_API_KEY, GEMINI_API_KEY, BRAVE_API_KEY)
│
├── progress.md                # 🚨 MASTER ROADMAP: Phase & Stage checklist, completion tracker
├── Journey.md                 # 🚨 DECISION LOG: Iteration journal, ADRs, engineering rationale
├── Agent.md                   # 🚨 ONBOARDING GUIDE: This file
├── instruct.md                # Prompt style guide loaded by src/tailor.py (stays at root — code dependency)
│
├── src/                       # Core Application Modules
│   ├── __init__.py
│   ├── database.py            # SQLite engine, connection WAL pragma listeners, SessionLocal, Base
│   ├── models.py              # ORM models (Profile, ProfileFact, JD, JDRequirement, RunLog, Claim, ChatThread)
│   ├── logger.py              # Centralized logging (console + rotating file, never logs keys)
│   ├── parser.py              # Text extraction for PDF (pdfplumber/pypdf), DOCX (python-docx), and TXT
│   ├── resume_parser.py       # (Phase 1) Structured resume → discrete facts lowering
│   ├── web_context.py         # Company context enrichment via Brave Search API
│   ├── tailor.py              # Multi-provider LLM assembly + score→allocate orchestration (Claude/Gemini)
│   ├── pdf_generator.py       # ReportLab flowable PDF generation for resumes and cover letters
│   ├── profile_service.py     # (Phase 1) Profile and ProfileFact CRUD service layer
│   ├── jd_structuring.py      # (Phase 2) Cleaning, KeyBERT keywords, role classification, JD persistence
│   ├── scoring.py             # (Phase 3) MiniLM cosine similarity & RapidFuzz token scoring
│   ├── allocator.py           # (Phase 3) 0/1 Knapsack dynamic programming allocator
│   ├── claims.py              # (Phase 4) Claim extraction & [F<id>] citation parser
│   ├── verifier.py            # (Phase 4) Hybrid cosine pre-screen + MiniLM2 NLI cross-encoder verifier
│   └── feedback.py            # (Phase 5) Weakest-section gap analysis and reasoning engine
│   └── evaluation.py          # (Phase 6) Metric pipeline + baseline-vs-knap benchmark + report/charts
│
├── tests/                     # Automated Pytest Suite (in-memory SQLite `in_memory_db`)
│   ├── __init__.py
│   ├── conftest.py            # Pytest fixtures
│   ├── test_models.py         # DB models, constraints, embeddings
│   ├── test_profile_service.py  # Profile/fact CRUD service layer
│   ├── test_profile_persistence.py  # Flask profile/fact REST endpoints
│   ├── test_resume_parser.py  # Resume structure extraction & ingestion
│   ├── test_jd_structuring.py # JD cleaning, keywords, role classification, persistence
│   ├── test_scoring.py        # Semantic scoring engine
│   ├── test_allocator.py      # Knapsack optimality proofs & edge cases
│   ├── test_orchestration.py  # Score→allocate→prompt pipeline integration
│   ├── test_claims.py         # Claim extraction & citations
│   ├── test_verifier.py       # Hybrid verification + adversarial suite
│   ├── test_feedback.py       # Feedback loop, runs API, rerun diffs
│   ├── test_pipeline_api.py   # JD/allocation endpoints + served UI checks
│   ├── test_chats.py          # Chat threads (1:N profile→JD)
│   ├── test_tailor_runs.py    # Tailor→chat RunLog persistence + downloads
│   └── test_pdf_generator.py  # PDF round-trip formatting guards
│   └── test_phase6_batch_cli.py  # Phase 6 batch helpers (JD discovery, bottleneck)
│   └── test_evaluation.py     # Phase 6 metrics + benchmark + report artifacts
│   └── test_e2e_smoke.py      # Phase 7 offline full-path smoke (alloc→verify→PDF→persist)
│
├── alembic/                   # Database Migrations
│   ├── env.py                 # Alembic environment configured for src.database
│   └── versions/              # Migration revision scripts
│
├── docs/                      # Frontend + Design Docs
    ├── index.html             # Web UI interface (3-view SPA: profiles → facts → JD chats)
    ├── privacy.html           # Local privacy disclaimer
    └── design/                # System design & verification docs
        ├── SystemDesign.md            # Comprehensive System Design Document
        ├── SystemDesign_Template.md   # Design doc template
        ├── TechStack_Verification.md  # Architectural trade-off analysis
        └── KnapResume_Features_TechStack_BuildPlan.md  # Phase-wise feature spec
│
└── samples/                   # Sample resumes & outputs (regenerate stale PDFs post-fixes)
```

---

## 3. Ground Rules & Mandatory Agent Protocols

When working in this repository in any session, you **must adhere strictly to these rules**:

### 🚨 Protocol 1: The `progress.md` & `Journey.md` Dual-Sync Rule
- **Before starting work:** Inspect `progress.md` to identify the **Current Phase**, **Active Stage**, and **Immediate Action Item**.
- **While implementing:** Build modular code, write unit/integration tests under `tests/`.
- **After finishing a stage:**
  1. Update **`progress.md`**: Mark the stage `[x]`, advance the dashboard % and active stage pointer, and add an entry to the *Completed Milestones Log*.
  2. Append to **`Journey.md`**: Write a complete iteration entry using the standardized template (*Objective, Key Decisions & Reasoning, File Changes, Edge Cases Handled, Test Results, Next Steps*).

### 🚨 Protocol 2: Phase-Level Test & Build Gate (End-of-Phase Verification)
- **Sub-Stage Execution:** During individual stages within a phase (e.g. Stage 1.1, Stage 1.2, Stage 1.3), focus on implementing the stage deliverables and authoring corresponding unit tests.
- **Phase Gate Trigger:** When all sub-stages of a phase are completed (e.g. Stage 1.x is done before moving to Phase 2):
  1. **Run Full Test Suite:** Execute `pytest -v` across the entire project.
  2. **Fix & Refactor:** Resolve any regressions, assertion failures, or broken integrations across the entire codebase.
  3. **Build Check:** Ensure all application modules compile cleanly with zero errors (`python -m py_compile ...`).
  4. **Phase Sign-off:** Only transition to the next Phase once 100% of tests pass and the Phase exit criteria (DoD) are fully verified.

### 🚨 Protocol 3: Strict Architectural Boundaries (ADR Compliance)
1. **Database:** Always use SQLite with WAL mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`). Never introduce PostgreSQL, MySQL, or server processes.
2. **Vector Storage:** Store 384-dimensional embeddings as raw binary float32 byte buffers (`np.ndarray.tobytes()` and `np.frombuffer(blob, dtype=np.float32)`). Never use `pickle` (security and version risks).
3. **PDF Generation:** Use ReportLab flowables (`src/pdf_generator.py`). Do not introduce WeasyPrint (avoids heavy C-libraries like Cairo/Pango).
4. **NLP & Scoring:** Use `KeyBERT` for keyword extraction and `sentence-transformers/all-MiniLM-L6-v2` for embeddings. Avoid heavy spaCy pipelines.
5. **Verification Engine:** Use the hybrid approach — Fast Cosine pre-screen ($\ge 0.85 \implies \text{Verified}$, $\le 0.60 \implies \text{Unsupported}$) and small NLI cross-encoder (`cross-encoder/nli-MiniLM2-L6-H768`, ~90MB) on borderline cases ($0.60 < s < 0.85$).
6. **No External MCP / Notion Server:** All run history and telemetry reside strictly in local SQLite tables (`run_logs`, `claims`).

---

## 4. Key Data Entities (`src/models.py`)

| Model | Table | Responsibility | Key Fields |
|---|---|---|---|
| **`Profile`** | `profiles` | Persistent user profile container | `id`, `name`, `sections` (JSON), `created_at`, `updated_at` |
| **`ProfileFact`** | `profile_facts` | Discrete verifiable fact | `id`, `profile_id` (FK), `section`, `content`, `is_mandatory` (bool), `embedding` (BLOB bytes) |
| **`JD`** | `jds` | Ingested job description | `id`, `raw_text`, `structured` (JSON), `role_type`, `company`, `job_title` |
| **`JDRequirement`**| `jd_requirements`| Extracted skill requirement | `id`, `jd_id` (FK), `skill`, `category` (required/nice_to_have), `importance` (float) |
| **`RunLog`** | `run_logs` | Execution run telemetry | `id`, `profile_id` (FK), `jd_id` (FK), `feedback` (JSON), `status`, `duration_ms` |
| **`Claim`** | `claims` | 3-state verified claim | `id`, `run_log_id` (FK), `text`, `state` (verified/inferred/unsupported), `score`, `cited_fact_id` (FK) |

---

## 5. Development & Verification Workflow

### Running Tests (Phase Gate Requirement)
At the conclusion of each full Phase (e.g., when all Stage 1.x tasks are completed before Phase 2):
```powershell
pytest -v
```
*Rule: All tests across previous and current phases must pass (100% green) before advancing to the next Phase.*

### Applying Database Migrations
When modifying models in `src/models.py`:
```powershell
alembic revision --autogenerate -m "describe_change"
alembic upgrade head
```

### Running the Application
- **Flask Web Server:**
  ```powershell
  python app.py
  # Access at http://localhost:5000
  ```
- **CLI Wizard:**
  ```powershell
  python main.py tailor --help
  ```

---

## 6. Phase Roadmap Quick Reference

- **Phase 0:** Fork & Orient (Cleaned Notion MCP, scaffolded DB, pytest harness) — **✅ COMPLETED**
- **Phase 1:** Profile Persistence Layer (Models, CRUD service, DOCX ingestion, REST API) — **🔄 IN PROGRESS**
- **Phase 2:** JD Structuring Engine (KeyBERT extraction, role classification taxonomy)
- **Phase 3:** Scoring & Knapsack Allocation (Semantic cosine scoring, 0/1 Knapsack DP allocator)
- **Phase 4:** Verification Layer (Hybrid cosine + MiniLM2 NLI verifier, hallucination blocker)
- **Phase 5:** Weakest-Section Feedback Loop (Keyword gap reasoning, re-run differential reporting)
- **Phase 6:** Evaluation Harness & Benchmarking (Fixture benchmark set, Before vs. After metrics)
- **Phase 7:** Export, Integration & Final Polish (ATS keyword checklist, ReportLab export styling)

---

*When starting a new session, inspect `progress.md`, find the active stage, implement the code and unit tests, and record the rationale in `Journey.md`.*
