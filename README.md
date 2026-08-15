# Book Illustration Studio

Web app that turns a book’s text into character portraits and one chapter illustration, following the Gradion intern take-home (notebook steps 1–5 only). Spec: [`docs/plan.md`](docs/plan.md).

## Prerequisites

- Python 3.11+ (`python3`)
- Node.js 20+ and npm
- A Gemini API key **only** if you want live generation (`USE_FAKE_GEMINI` unset)

No Docker. State is JSON and image files under `data/` (gitignored).

## Setup

```bash
cp .env.example .env
# Default: USE_FAKE_GEMINI=1 — walk the five steps without a live Gemini key.
# To use the notebook adapter: unset USE_FAKE_GEMINI and set GEMINI_API_KEY.
```

`./start.sh` and `./test.sh` create `backend/.venv` and install frontend npm deps on first run.

## Commands

| Command | What it does |
|---------|----------------|
| `./start.sh` | Starts FastAPI (`--workers 1`) and the Vite dev server; Ctrl+C stops both |
| `./test.sh` | Runs pytest, then vitest; fails if either fails. The same pair runs on GitHub Actions on push/PR to `main` |

npm equivalents from the repo root: `npm start`, `npm test`, `npm run dev:backend`, `npm run dev:frontend`, `npm run test:backend`, `npm run test:frontend`.

After `./start.sh`:

- Frontend: http://127.0.0.1:5173 — identity `/`, list `/projects`, new `/projects/new`, detail `/projects/:id`
- Backend health: http://127.0.0.1:8000/api/health

Vite proxies `/api` to FastAPI.

## Env vars

See [`.env.example`](.env.example).

| Variable | Role |
|----------|------|
| `USE_FAKE_GEMINI` | `1` (default in the example) injects `FakeGeminiClient`. Unset to use `RealGeminiClient` |
| `GEMINI_API_KEY` | Required for the real adapter. Never commit it |
| `GEMINI_TEXT_MODEL` | Default `gemini-3.7-flash` (notebook) |
| `GEMINI_IMAGE_MODEL` | Default `gemini-3.1-flash-lite-image` (notebook Nano Banana) |
| `BACKEND_HOST` / `BACKEND_PORT` | Default `127.0.0.1` / `8000` |
| `FRONTEND_PORT` | Default `5173` |

## Architecture

The browser is a small React (Vite) SPA: identity, project list, new project, and project detail. Detail polls `GET /api/projects/:id` about once a second only while the server-derived `action` is `wait`. Identity is email + name in `localStorage`; every API call except `POST /api/identify` sends `X-User-Email`. There is no password and no JWT.

FastAPI is the only backend. Routes stay thin. `to_view()` / `can_claim()` are the single brain for list pills, the primary button, and step admission. Pipeline state lives in `data/projects/{id}/project.json` under a per-file `fcntl` flock; book text and images are sibling files. A step POST claims under the lock (`run=running`, this process’s `BOOT_ID`), unlocks, returns **202**, and runs Gemini in a thread pool so GET can succeed during a long call. Caps are enforced server-side: at most two characters and one chapter (truncate, do not fail). Gemini is never auto-retried.

The Gemini client is injected into `create_app`. `FakeGeminiClient` and `RealGeminiClient` share the same methods (`send_book`, `style`, `characters`, `portraits`, `chapters`, `illustrations`, session dump). Tests always inject the fake. `./start.sh` follows `USE_FAKE_GEMINI` so a reviewer can finish the product without a live key; unsetting that flag and setting `GEMINI_API_KEY` is the switch to the notebook Files + Interactions path. Session fields (`file_id`, `file_uri`, `interaction_id`, `image_interaction_id`) stay on disk and off the wire.

## Docs

- [`docs/plan.md`](docs/plan.md) — implementation spec
- [`docs/architecture.md`](docs/architecture.md) — layout diagram
- [`DECISIONS.md`](DECISIONS.md) — trade-offs and AI overrides
- [`TESTING.md`](TESTING.md) — strategy and a real `./test.sh` report
