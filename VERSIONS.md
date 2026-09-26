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

## Version 2.0 (Planned - Iterative Improvement Loop)
**Status**: Design complete, ready for implementation

### New Features
1. **Structured JSON Output** (instead of plain text)
   - LLM emits typed `ResumeData` JSON schema
   - Deterministic PDF renderer (no fragile regex parsing)
   - Categorized skills (Languages, Frameworks, Cloud/DevOps, Databases, Tools)
   - Section ordering by allocation utility score (highest first)

2. **Iterative Improvement Loop** (max 3 LLM calls)
   - Detect weakest section from feedback
   - Rewrite ONLY that section to cover missing skills
   - Re-verify after each iteration
   - Enforce 1-page constraint via intelligent trimming
   - Composite resume score tracking (verification rate + coverage + utility)

3. **Enhanced PDF Formatting**
   - Pure B&W, letter-style section separation (black rules)
   - Structured contact block with labels
   - Right-aligned dates in experience entries
   - Skills rendered as categorized chips
   - Business-letter format cover letter

### New Files (v2)
```
src/
├── schemas.py             # ResumeData, CoverLetterData, ExperienceEntry TypedDicts
├── improver.py            # Iterative improvement loop (max 3 calls, page constraint)
└── (modified existing)
```

### Modified Files (v1 → v2)
```
src/tailor.py              # + tailor_resume_structured(), tailor_resume_with_improvement_loop()
src/pdf_generator.py       # + render_resume_data(), count_pdf_pages(), structured renderers
src/app.py                 # Route allocation+improvement path in _run()
src/main.py                # CLI --structured/--improve flags
tests/
├── test_structured_output.py
├── test_improver.py
└── test_pdf_generator.py  # Extended
```

### v2 Capabilities (Incremental over v1)
- ✅ Deterministic structured output → reliable PDF rendering
- ✅ Section ordering by relevance score
- ✅ Categorized skills layout
- ✅ Max 3 LLM calls to fix weakest section
- ✅ Automatic 1-page enforcement (trim/rewrite by utility)
- ✅ Composite score tracking per iteration
- ✅ Backward compatible with v1 plain-text path

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