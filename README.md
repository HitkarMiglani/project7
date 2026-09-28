# KnapResume

KnapResume

KnapResume tailors a resume and cover letter to a job description while keeping the user's resume as the source of truth. It uses semantic matching, deterministic section allocation, and claim verification to select relevant content and block unsupported claims.

## Features

- Flask web app with resume tailoring, PDF downloads, profile management, JD processing, allocation, feedback reruns, and chat-thread endpoints
- Typer CLI for tailoring resumes and generating cover letters
- PDF, DOCX, TXT, and Markdown resume or job-description input
- Claude and Gemini providers
- SQLite persistence through SQLAlchemy and Alembic
- JD cleaning, company/title extraction, skill requirements, and role classification
- Semantic and fuzzy scoring with per-section 0/1 knapsack allocation
- Three-state claim verification: `Verified`, `Inferred`, and `Unsupported`
- Feedback that identifies missing required skills and the weakest resume section
- Browser-only demo in [`docs/index.html`](docs/index.html)

## Requirements

- Python 3.11 or newer
- An Anthropic or Google Gemini API key
- Node.js is not required for the current application

## Setup

```bash
git clone https://github.com/HitkarMiglani/project7.git
cd project7

python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env  # Windows
# cp .env.example .env  # macOS/Linux
```

Set at least one provider key in `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
```

Only one key is required. The default SQLite database is `knapresume.db`; set `DATABASE_PATH` to use another location.

## Run the web app

```bash
python app.py
```

Open <http://localhost:5000> in a browser.

The main API endpoints include:

| Area | Endpoints |
|---|---|
| Tailoring | `POST /api/tailor`, `GET /api/status/<job_id>`, PDF download endpoints |
| Profiles and facts | `/api/profile`, `/api/profiles`, `/api/profile/<id>/facts`, `/api/profile/<id>/ingest` |
| Job descriptions | `/api/jds` and `/api/jds/<id>` |
| Allocation and feedback | `POST /api/allocate`, `/api/runs`, `/api/runs/<id>/rerun` |
| Chat threads | `/api/profile/<id>/chats` and `/api/chats/<id>` |

## Run the CLI

```bash
python main.py --help
python main.py tailor --resume my_resume.pdf --job-url https://jobs.example.com/role
python main.py tailor --resume my_resume.docx --job-file job_description.pdf
python main.py tailor
```

The CLI accepts resume files in `PDF`, `DOCX`, `TXT`, or `MD` format. Job descriptions can come from a file, URL, or pasted text. Use `--provider claude` or `--provider gemini` and `--model` to select the model.

Generated files are written to `outputs/`.

## Database migrations

Create or update the local schema with Alembic:

```bash
alembic upgrade head
```

The current schema stores profiles, normalized resume facts, job descriptions and requirements, tailoring runs, verification claims, and chat threads.

## Development

Run the test suite:

```bash
pytest -q
```

Compile the application modules without running the server:

```bash
python -m py_compile app.py main.py src/*.py
```

Important files:

- [`app.py`](app.py) - Flask application and API routes
- [`main.py`](main.py) - CLI entry point
- [`src/profile_service.py`](src/profile_service.py) - profile and resume-fact persistence
- [`src/jd_structuring.py`](src/jd_structuring.py) - job-description normalization
- [`src/scoring.py`](src/scoring.py) and [`src/allocator.py`](src/allocator.py) - matching and content selection
- [`src/verifier.py`](src/verifier.py) - claim verification and sanitization
- [`src/feedback.py`](src/feedback.py) - gap analysis and rerun feedback
- [`src/pdf_generator.py`](src/pdf_generator.py) - PDF export
- [`instruct.md`](instruct.md) - local and CLI prompt instructions

## Privacy

In local mode, resume and job-description content is sent from your machine to the provider configured in `.env`. API keys are read locally and are not committed to the repository. Review your provider's data-handling policy before sending sensitive material.

The browser demo sends content directly from the browser to the selected provider and does not use the Flask backend.

## Project status

Phases 1-5 are implemented and covered by tests. Phase 6 is focused on fixture-based evaluation and benchmarking; Phase 7 covers final export integration and polish. See [`progress.md`](progress.md) for the detailed tracker and [`Journey.md`](Journey.md) for implementation decisions.

## License

MIT.

<div align="center">
  <sub>Built for sharper application packets without letting the model invent a career.</sub>
</div>
