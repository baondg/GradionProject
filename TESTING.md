# Testing

## Strategy

Tests run with **`./test.sh`** (pytest, then vitest). Either failure fails the script. Gemini is never called in tests — a fake client will be injected when the pipeline exists.

**Backend (now):** HTTP health check so the FastAPI app actually boots in pytest.

**Backend (next, per `docs/plan.md`):** step order, `can_claim` (live vs stale boot id), success/fail cursor, 2/1 caps, `to_view` action/stuck/pill; HTTP tests with a temp `data/` dir — 5-step happy path, concurrent duplicate POST → one 409, restart stuck on list **and** detail, fail/retry.

**Frontend (now):** the harness hello-world screen renders.

**Frontend (next):** Identity validation; list empty vs row; StepPanel `action` `run` | `wait` | `retry` | `recover` | `none`.

**Deliberately not tested:** Playwright/E2E, CSS, Gemini prompt quality, coverage gates, real Gemini, list polling, SSE.

## Harness smoke report

Real run of `./test.sh` (2026-08-14). One pytest, one vitest, both passed.

```
==> backend (pytest)
.                                                                        [100%]
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  .../fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with
  `starlette.testclient` is deprecated; install `httpx2` instead.

1 passed, 1 warning in 0.17s
==> frontend (vitest)

 RUN  v4.1.10

 Test Files  1 passed (1)
      Tests  1 passed (1)
   Duration  731ms
```

The Starlette/`httpx` deprecation is from FastAPI's TestClient, not our code. Leave it until the pipeline tests exist; do not add `httpx2` just to silence a warning.
