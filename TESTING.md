# Testing

## Strategy

Tests run with **`./test.sh`** (pytest, then vitest). Either failure fails the script. Gemini is never called in tests — a fake client will be injected when the pipeline exists.

**Backend:** step order, `can_claim`, `to_view`, storage flock, Gemini helpers (mocked SDK), HTTP tests with a temp `data/` dir — 5-step happy path, concurrent duplicate POST → one 409, restart stuck on list **and** detail, fail/retry. Fake Gemini is injected; no network.

**Frontend (now):** the harness hello-world screen renders.

**Frontend (next):** Identity validation; list empty vs row; StepPanel `action` `run` | `wait` | `retry` | `recover` | `none`.

**Deliberately not tested:** Playwright/E2E, CSS, Gemini prompt quality, coverage gates, real Gemini, list polling, SSE.

## Harness smoke report

Real run of `./test.sh` (2026-08-15).

```
==> backend (pytest)
................................................                         [100%]
48 passed, 1 warning in 0.83s
==> frontend (vitest)
 Test Files  1 passed (1)
      Tests  1 passed (1)
```

The Starlette/`httpx` deprecation is from FastAPI's TestClient, not our code. Do not add `httpx2` just to silence it.
