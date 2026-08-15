# Book Illustration Studio

Web app that turns book text into character portraits and a chapter illustration via the Gemini API (Gradion intern take-home). Spec: [`docs/plan.md`](docs/plan.md).

## Prerequisites

- Python 3.11+ (`python3`)
- Node.js 20+ and npm
- An OpenRouter API key (not needed for the harness smoke tests)

## Setup

```bash
cp .env.example .env
# fill in OPENROUTER_API_KEY and model IDs when you run real generation
```

`./start.sh` and `./test.sh` create the Python venv and install dependencies on first run.

## Commands

| Command | What it does |
|---------|----------------|
| `./start.sh` | Starts FastAPI (`--workers 1`) and the Vite dev server |
| `./test.sh` | Runs pytest, then vitest; fails if either fails |

npm equivalents from the repo root: `npm start`, `npm test`, `npm run dev:backend`, `npm run dev:frontend`, `npm run test:backend`, `npm run test:frontend`.

After `./start.sh`:

- Frontend: http://127.0.0.1:5173
- Backend health: http://127.0.0.1:8000/api/health

Vite proxies `/api` to the backend. No Docker — state will live as JSON files under `data/` (gitignored).

## Env vars

See `.env.example`. Required later for generation: `OPENROUTER_API_KEY`, `GEMINI_TEXT_MODEL`, `GEMINI_IMAGE_MODEL`. Optional: `BACKEND_HOST`, `BACKEND_PORT`, `FRONTEND_PORT`.

## Architecture (short)

React (Vite) talks to FastAPI. Pipeline state is JSON on disk with a per-project file lock. Identity is email + name (`X-User-Email`); no password. Details and invariants are in `docs/plan.md`.

## Docs

- `docs/plan.md` — implementation spec
- `DECISIONS.md` — trade-offs
- `TESTING.md` — what we test and a real run report
