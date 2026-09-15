# Tech Stack Verification Report

### Build Plan: KnapResume Features, Tech Stack & Build Plan
### Verified against: Existing codebase (`rotsl/resume-tailor` fork)

---

## 1. What Already Exists

The forked codebase already provides a working foundation. Before adding anything new, understand what's in place.

### 1.1 Current Architecture

```mermaid
flowchart TB
    subgraph CLI["CLI (main.py)"]
        T[typer + rich]
    end

    subgraph Web["Web Server (app.py)"]
        F[Flask]
        T --> F
    end

    subgraph Core["Core Engine (src/)"]
        P[parser.py<br/>pdfplumber + python-docx]
        W[web_context.py<br/>httpx + Brave Search]
        TN[tailor.py<br/>Claude + Gemini dispatch]
        PDF[pdf_generator.py<br/>ReportLab]
        N[notion_integration.py<br/>MCP client]
    end

    subgraph LLM["LLM Providers"]
        C[Anthropic SDK]
        G[Google Gemini SDK]
    end

    F --> P
    F --> W
    F --> TN
    F --> PDF
    F --> N
    TN --> C
    TN --> G
```

### 1.2 Existing Dependencies (requirements.txt)

| Package | Purpose | Already Working |
|---|---|---|
| `anthropic>=0.25.0` | Claude API calls | Yes — `src/tailor.py` |
| `google-generativeai>=0.8.0` | Gemini API calls | Yes — `src/tailor.py` |
| `pdfplumber>=0.10.0` | PDF text extraction | Yes — `src/parser.py` |
| `reportlab>=4.0.0` | PDF generation | Yes — `src/pdf_generator.py` |
| `python-docx>=1.1.0` | DOCX text extraction | Yes — `src/parser.py` |
| `flask>=3.0.0` | Web server | Yes — `app.py` |
| `httpx>=0.27.0` | HTTP client (URL fetch) | Yes — `src/web_context.py` |
| `mcp>=1.0.0` | Notion MCP protocol | Yes — `src/mcp_notion_client.py` |
| `notion-client>=2.2.0` | Notion SDK | Yes — `src/notion_integration.py` |
| `typer>=0.12.0` | CLI framework | Yes — `main.py` |
| `rich>=13.7.0` | CLI formatting | Yes — `main.py` |
| `python-dotenv>=1.0.0` | Env var loading | Yes |

### 1.3 Existing LLM Abstraction

```mermaid
flowchart LR
    A[caller] --> D{provider?}
    D -->|claude| C[_call_claude<br/>anthropic SDK]
    D -->|gemini| G[_call_gemini<br/>google-generativeai SDK]
    C --> R[response text]
    G --> R
```

**Key finding:** The codebase already has a clean provider dispatcher at `src/tailor.py:164-177`. The `_call_ai()` function routes based on `provider` string, accepts `model` and `api_key` at call time, and returns plain text. This is a lightweight abstraction layer.

---

## 2. Proposed vs. Recommended Tech Stack

### 2.1 Component-by-Component Verdict

| Component | Plan Proposes | Recommended | Verdict |
|---|---|---|---|
| API framework | FastAPI | Flask (keep existing) | **DROP** |
| Database | PostgreSQL + SQLAlchemy + Alembic | SQLite + SQLAlchemy + Alembic | **DOWNGRADE** |
| NLP pipeline | spaCy (`en_core_web_sm`) + KeyBERT | KeyBERT only | **DROP spaCy** |
| Semantic scoring | sentence-transformers (`all-MiniLM-L6-v2`) | sentence-transformers | **KEEP** |
| Fuzzy matching | rapidfuzz | rapidfuzz | **KEEP** |
| Verification engine | Embedding cosine similarity + full NLI cross-encoder (`nli-deberta-v3-base`, ~500MB) | Embedding cosine similarity + small NLI cross-encoder (`nli-MiniLM2-L6-H768`, ~90MB) | **SHRINK NLI** |
| LLM abstraction | litellm | Existing dispatcher OR litellm | **DEPENDS** |
| PDF export | WeasyPrint (+ keep ReportLab) | ReportLab only | **DROP WeasyPrint** |
| Eval reporting | pandas + matplotlib | pandas + matplotlib | **KEEP** |
| Testing | pytest | pytest | **KEEP** |

---

## 3. Analysis of Each Decision

### 3.1 API Framework: FastAPI vs. Flask

```mermaid
flowchart TB
    subgraph FastAPI["FastAPI (proposed)"]
        FA1[Native async/await]
        FA2[WebSocket streaming]
        FA3[Auto OpenAPI docs]
        FA4[New framework to learn]
        FA5[Dual web framework in one app]
    end

    subgraph Flask["Flask (existing)"]
        FL1[Threading.Thread for background jobs]
        FL2[Working /api/tailor endpoint]
        FL3[Working /api/status polling]
        FL4[Zero new dependencies]
        FL5[Already in app.py — 132 lines]
    end

    FL1 -.->|"sufficient for 3 endpoints"| DEC{{"Decision"}}
    FA2 -.->|"only if streaming needed"| DEC

    DEC -->|"No streaming requirement"| USE_FLASK[Keep Flask]
    DEC -->|"Need real-time progress"| USE_FASTAPI[Add FastAPI]
```

**Why drop FastAPI:**
- The existing Flask server at `app.py:59-64` already handles background jobs via `threading.Thread`
- Status polling via `/api/status/<job_id>` (line 115-119) gives clients progress updates
- FastAPI only wins if you need WebSocket streaming — which a resume tailoring tool doesn't need
- Running two web frameworks in one project adds complexity with zero benefit at this scale

**When to reconsider:** If you add a frontend that needs real-time step-by-step progress (not just polling), FastAPI + WebSocket becomes justified.

---

### 3.2 Database: PostgreSQL vs. SQLite

```mermaid
flowchart TB
    subgraph PlanDB["Plan: PostgreSQL"]
        PG1[Server process required]
        PG2[Connection pooling needed]
        PG3[Deployment config]
        PG4[Handles millions of rows]
        PG5[Full-text search built-in]
    end

    subgraph AltDB["Recommended: SQLite"]
        S1[File-based, zero config]
        S2[No server process]
        S3[Same SQLAlchemy ORM]
        S4[Same Alembic migrations]
        S5[WAL mode: PRAGMA journal_mode=WAL]
        S6[Handles tens of thousands of rows]
    end

    subgraph Shared["Shared (both)"]
        SH1[SQLAlchemy models]
        SH2[Alembic migrations]
        SH3[Same Python code]
    end

    PlanDB -.-> Shared
    AltDB -.-> Shared

    subgraph WAL["Concurrency: WAL Mode"]
        W1[PRAGMA journal_mode=WAL]
        W2[One line at engine setup]
        W3[Readers don't block writers]
        W4[Concurrent reads + single write]
    end

    AltDB -.->|"run once"| WAL
```

**Data volume estimate for this tool:**
- Profile facts: ~10-50 per user
- JD records: ~5-20 per user per month
- Run logs: ~20-50 per user per month
- Total: **hundreds of rows, not thousands**

**Why SQLite:**
- Zero deployment overhead — no Postgres server to provision, configure, or maintain
- SQLAlchemy models and Alembic migrations work identically with SQLite
- The `sqlite3` module is in Python's standard library
- Single-file database (`knapresume.db`) is trivially backup-able
- The only SQLAlchemy caveat: no `ARRAY` or `JSONB` columns — use `JSON` type instead (which SQLite supports)

**WAL mode — explicit setup step (do not leave implicit):**

```python
# in the SQLAlchemy engine setup (e.g. db.py, before model imports)
engine = create_engine("sqlite:///knapresume.db", connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")   # readers don't block writers
    cursor.execute("PRAGMA busy_timeout=5000")   # wait up to 5s on locked DB
    cursor.close()
```

This is a one-line statement (`PRAGMA journal_mode=WAL`) executed once at connection setup. It's required because the app uses Flask worker threads (one job per `threading.Thread`, see `app.py:59-64`) — WAL lets those background threads read the profile while a write is in progress, instead of erroring with `database is locked`. The default `journal_mode=DELETE` rolls back to a hard lock on every write, which will surface as intermittent `sqlite3.OperationalError: database is locked` under concurrent runs.

**When to reconsider:** If you add multi-user support, concurrent writes from multiple processes, or need full-text search beyond what LIKE queries provide.

---

### 3.3 NLP Pipeline: spaCy + KeyBERT vs. KeyBERT Only

```mermaid
flowchart TB
    subgraph spaCy["spaCy (proposed to drop)"]
        SC1[15MB model download]
        SC2[Full NER pipeline]
        SC3[Dependency parsing]
        SC4[POS tagging]
        SC5[Overkill for JD keyword extraction]
    end

    subgraph KeyBERT["KeyBERT (keep)"]
        KB1[Lightweight]
        KB2[Keyword extraction from JD]
        KB3[Uses sentence-transformers under the hood]
        KB4[Sufficient for required/nice-to-have classification]
    end

    subgraph RoleClass["Role Classification"]
        RC1[sentence-transformers embeddings]
        RC2[Cosine similarity vs. role taxonomy]
        RC3[Already planned for scoring engine]
    end

    spaCy -.->|"not needed"| DROP{{"Drop spaCy"}}
    KeyBERT --> JD["JD Structuring"]
    RoleClass --> JD
    JD --> |"{required_skills,<br/>nice_to_have,<br/>role_type}"| OUT[Structured JD]
```

**Why drop spaCy:**
- spaCy's value is NER and dependency parsing — neither is needed for JD structuring
- KeyBERT handles keyword extraction without spaCy's full pipeline
- Role classification can use sentence-transformers embeddings (already in the stack)
- Saves ~15MB download + faster install + fewer version conflicts

**What spaCy would be useful for (but isn't needed here):**
- Extracting company names from free-form text (regex handles this — see `app.py:92-95`)
- Named entity recognition for skills (KeyBERT keyword extraction is more relevant)

---

### 3.4 Verification Engine: Full NLI Cross-Encoder vs. Small NLI Cross-Encoder

```mermaid
flowchart TB
    subgraph Plan["Plan: Full NLI"]
        DBT["cross-encoder/nli-deberta-v3-base<br/>~500MB model"]
        DBT --> TAG["Verified / Inferred / Unsupported"]
    end

    subgraph Rec["Recommended: Small NLI"]
        MINI["cross-encoder/nli-MiniLM2-L6-H768<br/>~90MB model"]
        COS2["Cosine Similarity<br/>all-MiniLM-L6-v2<br/>(already needed for scoring)"]
        THRESH["Threshold 0.75-0.85<br/>fast pre-screen"]
        ENTAIL["Entailment check<br/>on borderline claims"]
    end

    COS2 --> THRESH --> ENTAIL
    MINI --> ENTAIL
    ENTAIL --> TAG2["Verified / Inferred / Unsupported"]

    Plan -->|"~500MB model<br/>for marginal gain<br/>over 90MB"| SHRINK_NLI{{"Shrink NLI"}}
    Rec -->|"~90MB model<br/>one pip download"| USE_SMALL_NLI["Use nli-MiniLM2-L6-H768"]
```

**Why shrink the NLI cross-encoder (instead of dropping it):**
- The full model (`cross-encoder/nli-deberta-v3-base`) is ~500MB and adds minutes to the first-run download
- `cross-encoder/nli-MiniLM2-L6-H768` is ~90MB — a **5.5x smaller** entailment model with the same architecture, built on MiniLM instead of DeBERTa
- Entailment scoring is still available for the third state (**Inferred**), so you don't lose the Verified/Inferred/Unsupported three-state design from the plan
- `all-MiniLM-L6-v2` cosine similarity (already needed for fact-JD scoring) stays as the fast pre-screen — only borderline claims go through the entailment model, keeping runtime low

**Recommended hybrid flow:**

```mermaid
flowchart LR
    CLAIM[Generated claim] --> COS{"Cosine vs. cited fact<br/>(all-MiniLM-L6-v2)"}
    COS -->|"score >= 0.85"| V[Verified]
    COS -->|"score <= 0.60"| U[Unsupported<br/>blocked]
    COS -->|"0.60 < score < 0.85<br/>(borderline)"| NLI{"Entailment<br/>(nli-MiniLM2-L6-H768)"}
    NLI -->|"entails fact"| V
    NLI -->|"neutral"| I[Inferred<br/>soft-fail]
    NLI -->|"contradicts fact"| U
```

**Why cosine alone is not enough:**
- A paraphrased but fabricated claim can score high cosine similarity to a nearby fact while still being a hallucination
- The 0.75 threshold touted in the plan is heuristic — the small entailment model gives a principled second opinion at the cost of ~90MB, not ~500MB
- Keeping a small NLI model preserves the three-state **Inferred** tag that "cosine only" necessarily collapses away

**When to revisit:** If even the ~90MB model is too heavy for your target runtime, drop entailment entirely and gate on cosine only — then the three-state design collapses to two. But at ~90MB this is unlikely to matter.

---

### 3.5 LLM Abstraction: litellm vs. Existing Dispatcher

```mermaid
flowchart TB
    subgraph Existing["Existing: tailor.py _call_ai()"]
        EA[provider string] --> ED{match}
        ED -->|claude| EC[_call_claude]
        ED -->|gemini| EG[_call_gemini]
        EC --> ER[response]
        EG --> ER
    end

    subgraph LiteLLM["litellm (proposed)"]
        LL[Unified API] --> LC[cost tracking]
        LL --> LR[retry logic]
        LL --> LM[model fallback]
        LL --> LP[provider routing]
    end

    Existing -->|"works for 2 providers"| Q1{{"Need OpenAI?"}}
    LiteLLM -->|"adds OpenAI + retry + cost"| Q1

    Q1 -->|Yes| USE_LITELLM[Add litellm]
    Q1 -->|No| KEEP_EXISTING[Keep existing dispatcher]
```

**Decision tree:**
- If Claude + Gemini cover your needs: **keep existing `_call_ai()` dispatcher** — it's 15 lines, clear, and zero dependencies
- If you want OpenAI as a third provider: **add litellm** — it handles the routing, retry, and cost tracking across all three
- If you want retry/rate-limit logic: litellm adds this for free, otherwise implement it manually

**Recommendation:** Add litellm only if you plan to support OpenAI. Otherwise the existing dispatcher is simpler and already working.

---

### 3.6 PDF Export: WeasyPrint vs. ReportLab Only

```mermaid
flowchart TB
    subgraph Current["Current: ReportLab"]
        RL[ReportLab] --> RLF["Flowable-based layout"]
        RLF --> RLP["Resume PDF"]
        RLF --> RLC["Cover Letter PDF"]
    end

    subgraph Proposed["Proposed: WeasyPrint"]
        WP[WeasyPrint] --> WPH["HTML/CSS templates"]
        WPH --> WPP["PDF output"]
        WP -.->|"requires C libs:<br/>cairo, pango, gdk-pixbuf"| DEP[Heavy install]
    end

    CURRENT["392 working lines<br/>in pdf_generator.py"] -->|"already handles<br/>section parsing,<br/>bullet points,<br/>contact blocks"| KEEP_RL{{"Keep ReportLab"}}

    Proposed -.->|"add only if complex<br/>layout needed"| COND["Conditional addition"]

    COND -->|"Need pixel-perfect<br/>templates?"| ADD_WP[Add WeasyPrint]
    COND -->|"Current layout<br/>is sufficient"| SKIP_WP[Skip WeasyPrint]
```

**Why keep ReportLab:**
- Already working — `src/pdf_generator.py` has 392 lines of tested code
- Handles all resume parsing: section headers, bullets, job entries, contact blocks
- Pure Python install — no C library dependencies (cairo, pango)
- WeasyPrint only wins for complex HTML/CSS layouts — resume templates don't need this

**When to reconsider:** If you need pixel-perfect resume templates with complex multi-column layouts that ReportLab's flowable system can't express.

---

## 4. Recommended Architecture (Post-Verification)

```mermaid
flowchart TB
    subgraph Input["User Input"]
        U[User] -->|profile + JD| API
    end

    subgraph API["Flask API (existing)"]
        API[app.py]
    end

    subgraph DB["SQLite + SQLAlchemy"]
        PROF[(Profile + Facts)]
        JDDB[(JD + Requirements)]
        RUNS[(Run Logs)]
    end

    subgraph Engine["Core Engine"]
        JD_STRUCT["JD Structuring<br/>(KeyBERT + sentence-transformers)"]
        SCORE["Scoring Engine<br/>(sentence-transformers cosine)"]
        KNAP["Knapsack Allocator<br/>(pure Python DP)"]
        LLM["LLM Generation<br/>(existing tailor.py)"]
        VERIFY["Verification Engine<br/>(cosine pre-screen +<br/>nli-MiniLM2-L6-H768 entailment)"]
        FEED["Feedback Engine<br/>(weakest section detection)"]
    end

    subgraph Output["Output"]
        PDF_OUT["PDF Export<br/>(existing ReportLab)"]
        NOTION["Notion Logging<br/>(existing MCP client)"]
    end

    subgraph Eval["Evaluation"]
        HARNESS["Eval Harness<br/>(pandas + matplotlib)"]
    end

    API --> DB
    API --> JD_STRUCT
    JD_STRUCT --> SCORE
    SCORE --> KNAP
    KNAP --> LLM
    LLM --> VERIFY
    VERIFY --> PDF_OUT
    VERIFY --> FEED
    FEED -->|edit profile| PROF
    DB --> API
    RUNS --> HARNESS
    NOTION -.->|"optional"| API
```

---

## 5. Updated requirements.txt (Recommended)

```txt
# ── Existing (keep) ──────────────────────────────────────────────────────────
anthropic>=0.25.0
google-generativeai>=0.8.0
pypdf>=4.0.0
pdfplumber>=0.10.0
reportlab>=4.0.0
python-docx>=1.1.0
mcp>=1.0.0
notion-client>=2.2.0
requests>=2.31.0
python-dotenv>=1.0.0
rich>=13.7.0
typer>=0.12.0
httpx>=0.27.0
flask>=3.0.0

# ── New (add) ────────────────────────────────────────────────────────────────
SQLAlchemy>=2.0.0
alembic>=1.13.0
keybert>=0.8.0
sentence-transformers>=2.2.0
rapidfuzz>=3.6.0
litellm>=1.30.0          # only if OpenAI support needed; else skip
pandas>=2.1.0
matplotlib>=3.8.0
pytest>=7.4.0
cross-encoder/nli-MiniLM2-L6-H768   # sentence-transformers model (auto-downloaded, ~90MB)
```

**Removed vs. plan:**
- `spacy` + `en_core_web_sm` — not needed; KeyBERT + sentence-transformers covers JD structuring
- `cross-encoder/nli-deberta-v3-base` — replaced with the smaller `cross-encoder/nli-MiniLM2-L6-H768` (~90MB vs ~500MB); you keep the full three-state verification
- `WeasyPrint` — not needed; ReportLab already handles PDF export
- `FastAPI` — not needed; Flask handles existing endpoints
- `psycopg2` / `asyncpg` — not needed; SQLite doesn't require a database driver (and WAL mode is set via one `PRAGMA` line)

**Net install size reduction:** ~615MB (spaCy model: ~15MB, full NLI model: ~500MB replaced by ~90MB small NLI, WeasyPrint C deps: ~200MB)

---

## 6. Migration Path: Existing → Recommended

```mermaid
flowchart LR
    subgraph Phase1["Phase 0-1: Orient + Profile"]
        P0["Fork + run existing app"]
        P1["Add SQLAlchemy models<br/>(Profile, ProfileFact)"]
        P2["Add Alembic migrations"]
        P3["Build CRUD endpoints<br/>(keep Flask)"]
    end

    subgraph Phase2["Phase 2: JD Structuring"]
        P4["Add KeyBERT extraction"]
        P5["Add role classification<br/>(sentence-transformers)"]
        P6["Store JD + Requirements<br/>(SQLite via SQLAlchemy)"]
    end

    subgraph Phase3["Phase 3: Scoring + Allocation"]
        P7["Embedding-based scoring<br/>(sentence-transformers)"]
        P8["Knapsack DP allocator<br/>(pure Python)"]
        P9["Wire before LLM call"]
    end

    subgraph Phase4["Phase 4: Verification"]
        P10["Cosine similarity pre-screen<br/>(reuse scoring embeddings)"]
        P11["Small NLI entailment on borderline<br/>(nli-MiniLM2-L6-H768)"]
        P12["Tag claims Verified/Inferred/Unsupported"]
        P13["Block Unsupported claims"]
        P14["Optionally add litellm"]
    end

    subgraph Phase5["Phase 5-6: Feedback + Eval"]
        P14["Weakest section detection"]
        P15["Re-run endpoint"]
        P16["Eval harness<br/>(pandas + matplotlib)"]
    end

    Phase1 --> Phase2 --> Phase3 --> Phase4 --> Phase5
```

---

## 7. Summary

| Question | Answer |
|---|---|
| Does the plan add unnecessary complexity? | Yes — FastAPI, PostgreSQL, spaCy, the ~500MB full NLI model, and WeasyPrint are overkill for a personal tool |
| Does the plan add unnecessary cost? | Yes — spaCy model (~15MB), full NLI model (~500MB), and WeasyPrint C deps (~200MB) inflate the install by ~700MB; a ~90MB NLI model gets the same verification behavior |
| Is there a better alternative for each dropped item? | Yes — see Section 2.1 table |
| Does the recommended stack still deliver all features? | Yes — profile persistence (SQLite + WAL), JD structuring, scoring, knapsack allocation, three-state verification (small NLI), feedback, and eval are all achievable with the lighter stack |
| When should you revisit dropped items? | If adding multi-user support (Postgres or SQLite connection pooling), complex layouts (WeasyPrint), OpenAI provider (litellm), or if the small NLI model underperforms on paraphrase edge cases (then upgrade to a larger cross-encoder) |
