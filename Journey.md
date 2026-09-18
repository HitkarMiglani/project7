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
