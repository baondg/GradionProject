# Testing

## Strategy

`./test.sh` runs pytest, then vitest. Either failure fails the script. GitHub Actions (`.github/workflows/test.yml`) runs the same pair on push/PR; no live Gemini. HTTP tests inject `FakeGeminiClient`. The same fake is what `USE_FAKE_GEMINI=1` selects at process start; tests do not rely on that env var, they pass the client into `create_app`.

### Backend (pytest)

**Pure functions** (`backend/tests/unit/test_state.py`): step order; `can_claim` (idle / failed / stale boot → yes, live boot → no); `to_view` pills and `action` (`draft`/`run`, live `wait`, stale `recover`, `retry`, `done`/`none`); disk-only fields stay off the view (`attempts` included — list serializer does not emit them). Missing `attempts` → `[]`.

**Storage** (`backend/tests/unit/test_storage.py`): project and user JSON roundtrips; concurrent `save_project` leaves valid JSON; concurrent `update_project` / `update_users` do not drop increments (the flock).

**Gemini helpers** (`backend/tests/unit/test_gemini.py`): mocked SDK only (no network). Missing/invalid key → `GeminiConfigError`; `send_book` uploads a file then starts an interaction with the document URI; structured lists use a JSON array schema and truncate to 2; portraits start a separate image chain; illustrations continue that chain and pass portrait bytes as `{type: image}` parts. Fake portraits are a valid 1×1 PNG.

**HTTP** (`backend/tests/integration/test_api.py`), temp `data/` dir, injected fake:

1. Happy path — create (no Gemini) → five named POSTs → 202s → GET until `status=done`. Fake records **one** `send_book` and **one** call per step. Detail `attempts` is five `success` rows. List items do not include `attempts`.
2. Duplicate — two concurrent POSTs on the same step → one 202, one 409 `in_flight`, fake called **once**.
3. Restart — leave `running` with a foreign `run_boot_id` → GET list **and** GET detail both `stuck: true` / `action: recover` → POST current step → 202 and a new fake call.
4. Failure — fake raises → `run=failed`, cursor unchanged, one `failed` attempt → retry POST allowed, cursor advances, attempts are `[failed, success]`.

### Frontend (Vitest + Testing Library)

Mocked `fetch`. The states a reviewer actually sees:

- **Identity** — invalid name/email does not POST; valid identify stores `biStudio.identity` and navigates.
- **List** — empty state; a row with a Draft pill and subtitle; in-progress/done subtitles; loading skeleton (`aria-busy`); fetch error (no empty-state copy); Space opens a row; window `focus` refetches.
- **New project** — empty title/text does not fetch; non-`.txt` upload; API error on create.
- **Detail** — GET 500 shows `loadError`; 404 navigates to list; attempt history from the payload.
- **StepPanel** — `action` `run` | `wait` | `retry` | `recover` | `none`: copy, enabled/disabled button, step name on wait.
- **AttemptHistory** — mixed success/failed grouped by step; empty hidden.

### Deliberately not tested

Playwright / E2E, CSS, CharacterCard layout, coverage gates, live Gemini, list polling, SSE, `fcntl` in isolation (covered by the concurrent storage and duplicate-POST tests), Gemini prompt quality.

## Test report

Real run of `./test.sh` on 2026-08-15.

```
==> backend (pytest)
...................................................                      [100%]
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /home/gia-bao/Desktop/GradionProject/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
51 passed, 1 warning in 0.93s
==> frontend (vitest)

> frontend@0.0.0 test
> vitest run


 RUN  v4.1.10 /home/gia-bao/Desktop/GradionProject/frontend


 Test Files  6 passed (6)
      Tests  23 passed (23)
   Start at  22:00:38
   Duration  1.63s (transform 676ms, setup 1.27s, import 1.08s, tests 1.06s, environment 3.87s)
```

The Starlette/`httpx` deprecation is from FastAPI’s TestClient, not our code.
