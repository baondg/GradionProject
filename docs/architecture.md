# Architecture

Book Illustration Studio is two local processes and a `data/` directory. No Docker, no database, no SSE.

```
browser (Vite :5173)
  └─ proxy /api → FastAPI (:8000, --workers 1)
       ├─ routes (thin): identify, me, projects, steps, files
       ├─ to_view / can_claim / claim_and_start
       ├─ storage: fcntl flock + read/write project JSON
       ├─ pipeline worker (thread pool): one Gemini attempt, then persist
       └─ gemini client (injected)
            ├─ FakeGeminiClient     USE_FAKE_GEMINI=1  or tests
            └─ RealGeminiClient     google-genai Files + Interactions, when the flag is unset
```

**On disk** (`data/`, gitignored):

```
data/
  users.json
  projects/{id}/
    project.json          flock this file
    book.txt
    portraits/{n}.png
    illustrations/{n}.png
```

**Progress (two axes only):** `completed_step` is the last successful step. `run` is `idle` | `running` | `failed`. `stuck` is derived: `running` and `run_boot_id !=` this process’s `BOOT_ID`. GET never writes.

**Claim:** flock → load → `can_claim` → write `running` + this `BOOT_ID` → unlock → schedule worker → 202. Live boot + `running` → 409 `in_flight`. Wrong URL step → 409 `wrong_step`.

**Caps:** persist at most 2 characters and 1 chapter. Truncate Gemini output; do not fail the step for extras.

**One book send:** `send_book` once; later steps reuse `doc.gemini` session fields. Never on the wire.

**Frontend:** four routes (`/`, `/projects`, `/projects/new`, `/projects/:id`). React switches the primary button on `action` only. Detail polls ~1s while `action === "wait"`.
