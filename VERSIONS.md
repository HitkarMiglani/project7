# KnapResume Version History

## Version 1.0 (Current - Baseline)
**Status**: Implemented and working

### Core Architecture
- **Entry Points**: CLI (`main.py`), Flask Web (`app.py`), GitHub Pages (`docs/index.html`)
- **Profile Persistence**: SQLite (WAL mode) with `Profile` + `ProfileFact` models
- **JD Structuring**: KeyBERT + sentence-transformers → `required_skills`, `nice_to_have`, `role_type`
- **Scoring Engine**: Cosine similarity (all-MiniLM-L6-v2) + fuzzy matching → fact utilities
- **Knapsack Allocation**: 0/1 DP per section, mandatory facts pinned, capacity-constrained
- **LLM Generation**: Multi-provider (Claude/Gemini), anti-fabrication prompts with `[F<id>]` citations
- **Verification Pipeline**: 3-state (Verified/Inferred/Unsupported) via cosine + NLI cross-encoder
- **Feedback Loop**: Weakest-section detection with keyword-gap reasoning, rerun with diffs
- **PDF Generation**: ReportLab, ATS-friendly parsing (headers, bullets, job entries, contact)
- **Notion Logging**: Optional via MCP (Model Context Protocol)

### Key Files (v1)
```
src/
├── models.py              # SQLAlchemy ORM models
├── database.py            # SQLite engine, sessions, WAL config
├── parser.py              # PDF/DOCX/TXT text extraction
├── resume_parser.py       # Structured resume → discrete facts
├── profile_service.py     # Profile/Fact CRUD, ingestion, embeddings
├── jd_structuring.py      # JD cleaning, KeyBERT, role classification, persistence
├── scoring.py             # Semantic scoring (cosine + fuzzy)
├── allocator.py           # 0/1 Knapsack DP allocator
├── tailor.py              # LLM prompts, multi-provider dispatch, allocation orchestration
├── claims.py              # Claim extraction with [F<id>] citation parsing
├── verifier.py            # 3-state verification + sanitization
├── feedback.py            # Weakest-section analysis, rerun diffs
├── web_context.py         # Brave Search company context
├── pdf_generator.py       # ReportLab PDF rendering
└── logger.py              # Structured logging

app.py                     # Flask server, API routes, background jobs
main.py                    # CLI entry point (typer)
instruct.md                # Anti-AI-writing prompt instructions
```

### v1 Capabilities
- ✅ Persistent profile facts across runs
- ✅ JD → structured requirements + role type
- ✅ Optimal fact selection via knapsack DP
- ✅ Anti-fabrication: 3-state verification blocks unsupported claims
- ✅ Weakest-section feedback with concrete missing skills
- ✅ Rerun after profile edits shows coverage diffs
- ✅ PDF output (resume + cover letter)
- ✅ Free-tier LLM support (Claude + Gemini)

---

## Version 2.0 (Planned — LaTeX Template Engine, Structured Generation & ATS Valuation)
**Status**: Architecture & Design Finalized, Ready for Execution

### Core Architectural Pillars (v2)

#### 1. Structured JSON Generation Schema (`src/schemas.py`)
- LLM emits a strictly validated `ResumeData` JSON schema with `[F<id>]` fact citations inside bullet strings.
- Pydantic models for `ContactInfo`, `CategorizedSkills` (Languages, Frameworks, Tools, Databases), `ExperienceItem`, `EducationItem`, `ProjectItem`, and `CoverLetterData`.
- Eliminates brittle regex parsing across the pipeline.

#### 2. Customizable LaTeX Template Engine (`src/latex_engine.py` + `templates/latex/`)
- Jinja2 environment configured with custom LaTeX-safe delimiters (`\BLOCK{...}`, `\VAR{...}`, `\#{...}`).
- Dedicated LaTeX character escaping pipeline (`&`, `%`, `$`, `#`, `_`, `{`, `}`, `~`, `^`, `\`, `<`, `>`).
- **Default built-in templates**:
  - `classic_ats.tex`: Standard single-column, horizontal rules, maximum ATS parseability.
  - `modern_tech.tex`: Categorized skills chips, subtle navy/slate section headers.
  - `compact_single_page.tex`: 0.4in margins, tight vertical spacing for dense profiles.
  - `academic_entry.tex`: Focused on Education, Research, Publications, and Projects.
- **Customization Parameters**: Margins (compact/standard/wide), font sizes (10–12pt), accent colors, date formatting, and dynamic section reordering.

#### 3. Multi-Tier LaTeX Compilation Waterfall (`src/latex_compiler.py`)
- **Tier 1 (Local / Container Binary)**: Executes `tectonic` (~35MB Rust binary, dynamic package fetching, zero 4GB TeX Live dependency) or `pdflatex`/`xelatex` in `PATH`.
- **Tier 2 (Cloud / Remote Microservice)**: Optional HTTP call to `LATEX_API_URL` (self-hosted Gotenberg, latexonline.cc, or AWS Lambda).
- **Tier 3 (Zero-Dependency ReportLab Fallback)**: Deterministic direct PDF builder rendering `ResumeData` directly to PDF without TeX dependencies.
- **Tier 4 (User Direct Action)**: One-click "Open in Overleaf" button and downloadable `.tex` source / `.zip` bundle.

#### 4. Dual-Scoring Model: Knapsack Content Selection vs. ATS Valuation

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                            Dual-Scoring Pipeline Architecture                               │
├──────────────────────────────────────────────┬──────────────────────────────────────────────┤
│ 🎒 Pre-Generation: Knapsack Scoring          │ 📊 Post-Generation: ATS Valuation Scorecard │
│ (src/scoring.py & src/allocator.py)          │ (src/ats_evaluator.py)                       │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ • Evaluates individual atomic profile facts  │ • Evaluates the entire generated resume      │
│ • Blends Cosine Sim + Fuzzy String Match     │ • 5-Dimension Composite Audit (0–100 scale): │
│ • 0/1 Knapsack DP (O(n · W)) selects optimal │   1. Keyword & Skill Match (35%)             │
│   fact subset per section under budget       │   2. Parseability & Structure (20%)          │
│ • Filters out noise BEFORE reaching LLM      │   3. Google XYZ Impact & Metrics (20%)       │
│                                              │   4. Section Hierarchy & Ordering (15%)      │
│                                              │   5. Spatial Length & 1-Page Fit (10%)       │
│ • Goal: Optimal Content Selection            │ • Goal: Compliance, Quality & Recruiter Rank│
└──────────────────────────────────────────────┴──────────────────────────────────────────────┘
```

#### 5. Autonomous Section-Healing Loop (`src/improver.py`)
- Analyzes ATS Scorecard gaps post-generation.
- If composite ATS score $< 85$ or required skill coverage $< 80\%$, executes targeted surgical rewrites on ONLY the weakest section JSON.
- Re-verifies citations and halts within max 2–3 LLM passes.

#### 6. Multi-Format Exporter & SPA UI Integration
- Multi-format download endpoints: Compiled PDF, LaTeX `.tex`, Overleaf `.zip`, Word `.docx`, and JSON Resume.
- Interactive ATS Scorecard bar in `docs/index.html` displaying matched/missing skill chips, XYZ verb statistics, and template customization controls.

---

### New & Modified File Inventory (v2)

```
src/
├── schemas.py             # (NEW) Pydantic models (ResumeData, CategorizedSkills, etc.)
├── latex_engine.py        # (NEW) Jinja2 LaTeX template renderer & escaping
├── latex_compiler.py      # (NEW) Multi-tier compilation waterfall (Tectonic/API/Overleaf)
├── ats_evaluator.py       # (NEW) 5-dimension ATS scoring & audit scorecard
├── improver.py            # (NEW) Iterative section-healing loop
├── export_engine.py       # (NEW) Multi-format export (DOCX, ZIP, JSON Resume)
├── pdf_generator.py       # (MODIFIED) Add deterministic ReportLab JSON builder fallback
├── tailor.py              # (MODIFIED) Structured JSON prompting with [F<id>] citations
├── verifier.py            # (MODIFIED) Direct JSON claim extraction & sanitization
└── app.py                 # (MODIFIED) Template endpoints, recompile, & ATS audit routes

templates/latex/
├── classic_ats.tex        # (NEW) Standard single-column ATS template
├── modern_tech.tex        # (NEW) Technical template with skill chips
├── compact_single_page.tex# (NEW) High-density 1-page template
└── academic_entry.tex     # (NEW) Education & project-centric template
```

---

### v2 Phased Implementation Roadmap

| Phase | Title | Scope & Deliverables |
|---|---|---|
| **v2.1** | Schema & LaTeX Engine | `schemas.py`, `latex_engine.py`, default `.tex` templates, Jinja2 escape tests |
| **v2.2** | Structured LLM Pipeline | Prompt JSON schema in `tailor.py`, update `claims.py` & `verifier.py` for JSON |
| **v2.3** | Compilation Waterfall | `latex_compiler.py` (Tectonic, Gotenberg/API, Overleaf, ReportLab JSON fallback) |
| **v2.4** | ATS Valuation Engine | `ats_evaluator.py` (5 dimensions: Keywords, Parseability, XYZ Verbs, Hierarchy, Length) |
| **v2.5** | Section-Healing Loop | `improver.py` multi-pass loop guided by ATS audit score |
| **v2.6** | Multi-Format Export & UI | `export_engine.py` (DOCX, ZIP), template selector & ATS scorecard in `docs/index.html` |

---

## Migration Strategy
| Phase | Action | Version |
|-------|--------|---------|
| 1 | Implement `schemas.py` + structured prompts | v2.1 |
| 2 | Build deterministic PDF renderer | v2.2 |
| 3 | Implement `improver.py` loop | v2.3 |
| 4 | Integrate into `tailor.py` + `app.py` | v2.4 |
| 5 | CLI/Web hooks + tests | v2.5 |
| 6 | Default to v2 path for profile+JD runs | v2.0 |

---

## Version Identification
```python
# In src/__init__.py or similar
__version__ = "1.0.0"  # Current
# __version__ = "2.0.0"  # After v2 implementation
```

### How to Check Current Version
```bash
# From codebase
git log --oneline -1

# From running app
python -c "import src; print(src.__version__)"
```

---

## Rollback Plan
If v2 introduces regressions:
1. `git checkout v1.0-tag` (to be created before v2 work begins)
2. Or disable via feature flag: `use_structured=False`, `use_improvement_loop=False`