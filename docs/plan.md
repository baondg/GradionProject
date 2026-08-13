# Book Illustration Studio — implementation spec

Source of truth for implementation. Do not invent architecture that is not in this file. Pipeline *mechanics* (models, structured output, `previous_interaction_id` / conversation chaining, portrait reuse) come from the Gradion notebook + current Gemini docs, not from guesswork.

**Assessment:** intern fullstack take-home (~16h). Required pipeline: notebook steps 1–5 only (Style → Characters → Portraits → Chapters → Illustrations). Out of scope: Veo, Lyria, TTS, mixing, public deploy.

---

## 1. Decisions (locked)

| # | Topic | Choice |
|---|--------|--------|
| 1 | Stack | **FastAPI (Python) + React (Vite)**. One language tax accepted: Pydantic and TypeScript both describe the wire JSON. Gemini work runs in a **thread pool** (`asyncio.to_thread` or equivalent); request handlers stay short. **Single uvicorn worker.** |
| 2 | Storage | **JSON on disk**, one file per project, small user index. Images and book text as files (required). Overlapping writes: **per-project `fcntl` flock**. Atomic rename is *not* the lock. |
| 3 | Progress | **Two axes on disk:** `completed_step` (cursor) + `run` (`idle` \| `running` \| `failed`). Next step is **implied** (cursor + 1). No stored `run_step`, no stored list pill. |
| 4 | Stranded `running` | **Boot id, derive-only (A1).** `run_boot_id` vs process `BOOT_ID`. GET never writes. No startup sweep. No wall-clock timeout retry. Hung thread in a live process is accepted and noted in `DECISIONS.md`. |
| 5 | API | **`X-User-Email` header**, named step POSTs, **202** then GET. Fat `to_view()`: pill, `action`, `steps[]`, `stuck`, `current_step`. React switches the primary button on **`action` only**. |
| 6 | Frontend | Four routes, small component set, Gradion CSS tokens. Detail **polls ~1s** while `action === "wait"`. No React Query, no SSE, no Redux. List is fetch-on-mount, not polled. |
| 7 | Tests | Function tests **plus** HTTP tests with temp `data/` and **fake Gemini**: 5-step happy path, concurrent duplicate POST, A1 stuck on list+detail, fail/retry. Frontend: a few RTL states. No Playwright, no coverage gate, no real Gemini in CI. |

Deliverable filename in the brief is **`DECISIONS.md`** (not `DECISION.md`). Use that.

---

## 2. Architecture

```
browser (Vite :5173)
  └─ proxy /api → FastAPI (:8000)
       ├─ routes (thin): identify, projects, steps, files
       ├─ to_view / can_claim / claim_and_start  (single brain)
       ├─ storage: flock + read/write project JSON
       ├─ pipeline: order, caps, persist session, call Gemini in thread
       └─ disk: data/users.json, data/projects/{id}.json, book.txt, images
```

**One command starts both processes** (`./start.sh`). **One command runs both test suites** (`./test.sh`). No Docker — JSON + local files do not need Compose.

### 2.1 FastAPI rules (non-negotiable)

- Gemini / SDK calls are **sync and slow**. Never run them on the event loop. Use a thread pool.
- Persist **`run: running` + `run_boot_id` + `run_started_at` under the file lock**, then **release the lock**, then start Gemini. Polling GET must succeed during the 10–30s+ call.
- `GET` is read-only (A1). No repair-on-read.
- Inject a Gemini client: real in process, fake in tests.

### 2.2 Layout (lean — do not grow extra layers)

```
backend/          FastAPI app + pytest
frontend/         Vite React + Vitest
data/             gitignored runtime files
start.sh
test.sh
.env.example
docs/plan.md      this file
DECISIONS.md
TESTING.md
README.md
```

No repository/service/domain pyramid. No shared npm package for types. Freeze the wire JSON here; duplicate it in Pydantic and TypeScript.

### 2.3 Identity

Email + name. Email exists → load that user (update name if changed). Missing → create. No password, no JWT, no OAuth.

After identify, every request sends **`X-User-Email`**. Name lives in `users.json`. Sign out is **client-only** (drop persisted identity). Impersonation is in-scope (assignment).

Persist `{ email, name }` in the browser so **refresh keeps identity**. Clear it on sign out. (`localStorage` vs `sessionStorage` — open question.)

---

## 3. Data model

### 3.1 On disk (Python only — never sent to React)

**`data/users.json`** (own flock for create-user / append `project_ids`):

```json
{
  "users": {
    "mira@example.com": {
      "email": "mira@example.com",
      "name": "Mira Hassan",
      "project_ids": ["uuid-1"]
    }
  }
}
```

**`data/projects/{id}/`**

| Path | Role |
|------|------|
| `project.json` | Pipeline state (flock this file) |
| `book.txt` | Full book text |
| `portraits/{n}.png` | Character portraits |
| `illustrations/{n}.png` | Chapter illustrations |

**`project.json` shape:**

```json
{
  "id": "uuid",
  "user_email": "mira@example.com",
  "title": "The Wind in the Willows",
  "created_at": "2026-08-13T12:00:00+00:00",
  "completed_step": "none",
  "run": "idle",
  "run_started_at": null,
  "run_boot_id": null,
  "error": null,
  "style": null,
  "style_source": null,
  "characters": [],
  "chapters": [],
  "gemini": {
    "file_id": null,
    "interaction_id": null
  }
}
```

Field meanings:

| Field | Values / notes |
|-------|----------------|
| `completed_step` | `none` \| `style` \| `characters` \| `portraits` \| `chapters` \| `illustrations` — last **successful** step |
| `run` | `idle` \| `running` \| `failed` only. **Never** store `stuck` |
| `run_boot_id` | Process `BOOT_ID` written when a step is claimed. Compared on read |
| `error` | `{ "code": string, "message": string }` or `null` |
| `style_source` | `user` \| `generated` \| `null` |
| `characters` | Max **2**. `{ name, prompt, portrait_path }` (`portrait_path` null until that image lands) |
| `chapters` | Max **1**. `{ name, prompt, illustration_path }` |
| `gemini` | Whatever the notebook/SDK needs to **not re-send** the book (file upload id / uri, conversation / `interaction_id`). Exact keys: map from the notebook at implementation time. **Never on the wire.** |

`BOOT_ID`: uuid minted once at process start (module or FastAPI lifespan). New process (crash, `./start.sh`, uvicorn reload) → new id.

**On-disk `running` means:** a process *claimed* this step. It does **not** mean a thread is alive. Interpret only via `to_view()`.

### 3.2 Step order

```
none → style → characters → portraits → chapters → illustrations
```

`next(completed_step)` is the only runnable step. When `completed_step === illustrations` and `run === idle`, the project is done.

### 3.3 Invariants (enforced under the project flock)

1. At most one claimed run per project.
2. A step cannot start unless it is `next(completed_step)`.
3. Success: set `completed_step` to that step **and** `run=idle`, clear `error`, clear `run_boot_id` / `run_started_at`, in **one write**.
4. Failure: cursor **unchanged**, `run=failed`, set `error`. Do not delete earlier results.
5. While `run=running`, portrait/illustration paths may fill in one at a time (same lock, short writes). Cursor does not advance until the step fully succeeds.
6. After Gemini structured output: **truncate** to 2 characters and 1 chapter. Do not fail the step for extra items.
7. Book bytes are uploaded / sent to Gemini **once**; later steps use `gemini` session fields.

### 3.4 Claim / recover (`can_claim`)

Allowed to start (or restart) `next(completed_step)` when **all** are true:

- The requested step **is** `next(completed_step)` (named URL must match).
- `completed_step !== illustrations`.
- **`can_claim(doc)`:**
  - `run == idle`, or
  - `run == failed`, or
  - `run == running` **and** `run_boot_id != current BOOT_ID` (stale — crash recovery).

**Reject (409 `in_flight`)** when `run == running` **and** `run_boot_id == current BOOT_ID`.

**Reject (409 `wrong_step`)** when the URL step is not `next(completed_step)`.

`can_claim` is the **only** admission gate. Do not scatter a second “if failed” path.

### 3.5 `to_view(doc)` — single serializer

Used by **list and detail**. No second “summary” DTO that only reads `run`.

**Stuck (derived, not stored):**  
`stuck = (run == running && run_boot_id != current BOOT_ID)`

**`current_step` (derived):**  
`next(completed_step)`, or `null` if completed is `illustrations`.

**`status` (list pill, derived):**

| Condition | `status` |
|-----------|----------|
| `completed_step == none` and `run == idle` | `draft` |
| `completed_step == illustrations` and `run == idle` | `done` |
| otherwise | `in_progress` |

**`action` (primary button, derived):**

| Condition | `action` |
|-----------|----------|
| `stuck` | `recover` |
| `run == running` (live boot id) | `wait` |
| `run == failed` | `retry` |
| `completed_step == illustrations` and `run == idle` | `none` |
| else (`idle`, not done) | `run` |

React **must** switch the primary control on `action` only. Do not re-derive this matrix on the client.

**`steps[]` (stepper, derived):** for each key in order: `done` if that step is ≤ cursor; `current` if it is `current_step`; else `pending`. When done, all five are `done`.

---

## 4. Running a step (sequence)

```
POST /api/projects/:id/steps/{step}
  1. flock project.json
  2. load doc; 404 / 403 if missing or wrong user
  3. if not can_claim or wrong step → unlock, 409
  4. write run=running, run_boot_id=BOOT_ID, run_started_at=now, error=null
  5. unlock
  6. schedule Gemini in thread pool; return 202 + to_view(doc)
```

Worker (thread):

```
  7. call Gemini (no auto-retry; one attempt)
  8. flock
  9. reload doc
 10. if run_boot_id != the id this worker claimed → discard results, unlock, stop
      (late finish after user recovered; crash-only we still keep this fence)
 11. on success: write artifacts + images, advance cursor, run=idle
     on failure: run=failed, error={code, message}; keep cursor and prior artifacts
 12. unlock
```

Image steps: after **each** portrait/illustration file is written, take the lock, set that item’s path, unlock (cursor still not advanced). GET polls will show items landing one by one.

Retries are **user-triggered only** (button → same POST). Never loop Gemini on failure or timeout.

Recover (`action === recover`): **same POST** as run for `current_step`. `can_claim` allows stale boot; that request claims and calls Gemini. One click. (The HTML mock only clears stuck then waits for a second Generate — do not copy that.)

---

## 5. API contract

Base path `/api`. Vite proxies `/api` to FastAPI.

### 5.1 Endpoints

| Method | Path | Notes |
|--------|------|--------|
| `POST` | `/api/identify` | Body `{ "name", "email" }`. Upsert user. **No** `X-User-Email` required. Returns `{ email, name }`. |
| `GET` | `/api/me` | Header required. Current user. |
| `GET` | `/api/projects` | Header required. Array of **list** views (no `book_text`, no image blobs). Must include `stuck` / `action` via `to_view`. |
| `POST` | `/api/projects` | JSON `{ "title", "text" }` **or** multipart `title` + `.txt` file. Creates project, writes `book.txt`, `completed_step=none`, `run=idle`. **Does not** call Gemini. 201 + detail view. |
| `GET` | `/api/projects/:id` | Detail view including `book_text`. |
| `POST` | `/api/projects/:id/steps/style` | Optional `{ "style": string }`. Empty/omit → Gemini chooses. |
| `POST` | `/api/projects/:id/steps/characters` | |
| `POST` | `/api/projects/:id/steps/portraits` | |
| `POST` | `/api/projects/:id/steps/chapters` | |
| `POST` | `/api/projects/:id/steps/illustrations` | |
| `GET` | `/api/projects/:id/files/...` | Serve portrait/illustration bytes. 403 if not owner. |

No `POST /logout`. No `/advance`. No JWT.

Step POSTs: **202** + full **detail** `to_view`. Work continues in a thread.

### 5.2 Headers

`X-User-Email: mira@example.com` on all routes except `POST /api/identify`.

Missing/unknown email → 401. Project not owned by email → 403. Unknown id → 404.

### 5.3 Error bodies

```json
{ "error": { "code": "in_flight", "message": "..." } }
```

| HTTP | `code` | When |
|------|--------|------|
| 409 | `in_flight` | Live claim (this `BOOT_ID`) |
| 409 | `wrong_step` | URL step ≠ `next(completed_step)` |
| 400 | `validation` | Empty title/text, bad email, not `.txt` |
| 401 | `unauthenticated` | Missing/unknown email header |
| 403 | `forbidden` | Not the owner |
| 404 | `not_found` | |

### 5.4 Wire types (duplicated in Pydantic + TypeScript)

`StepKey` = `"style" | "characters" | "portraits" | "chapters" | "illustrations"`

**List item** — also the prefix of detail:

```ts
type ProjectListItem = {
  id: string
  title: string
  created_at: string // ISO-8601
  status: "draft" | "in_progress" | "done"
  completed_step: "none" | StepKey
  current_step: StepKey | null
  run: "idle" | "running" | "failed"
  stuck: boolean
  action: "run" | "wait" | "retry" | "recover" | "none"
  steps: { key: StepKey; view: "done" | "current" | "pending" }[]
  error: { code: string; message: string } | null
}
```

When `stuck`: `run` is `"running"`, `stuck` is `true`, `action` is `"recover"`.

**Detail** = list item plus:

```ts
type ProjectDetail = ProjectListItem & {
  book_text: string
  style: string | null
  style_source: "user" | "generated" | null
  characters: { name: string; prompt: string; portrait_url: string | null }[]
  chapters: { name: string; prompt: string; illustration_url: string | null }[]
}
```

`portrait_url` / `illustration_url` are API file URLs, not disk paths. `null` = not yet generated. Polling sees them fill in.

**Never on the wire:** `run_boot_id`, `gemini.*`, raw filesystem paths, other users’ data.

### 5.5 Caps

Enforce **server-side**: persist at most 2 characters and 1 chapter (truncate Gemini output). Do not rely on the UI.

---

## 6. Frontend

### 6.1 Screens (match `app-demo.html` scope)

| Route | Screen |
|-------|--------|
| `/` | Identity — name + email, validation |
| `/projects` | List — empty state; else title, created date, 5-seg progress, pill Draft / In progress / Done |
| `/projects/new` | Title, `.txt` upload **and** paste, validation |
| `/projects/:id` | Detail — title, date, full book text (readable anytime; modal or equivalent), stepper, style once set, character cards, chapter cards, one primary action, optional style input on step 1 |

Nav: logo, Projects, user name, **Sign out**. Keyboard-usable list rows (demo uses Enter). Responsive; no layout jump on poll. Visual bar is the demo (Gradion tokens) as the floor.

Detail extras the mock lacks and we **must** have:

- **Error:** `action === retry` — message + retry button for **that** step.
- **Stuck:** `action === recover` — interrupted copy + recover (POST current step).
- **In progress:** `action === wait` — **names the running step** (from `current_step`), not a bare spinner.
- **Per-item:** while portraits/illustrations wait, each card shows pending vs image as URLs appear.

Do not port demo timings (2s steps, 8s stuck) or its `localStorage` project store.

### 6.2 Components (do not explode)

`IdentityPage`, `ProjectListPage`, `NewProjectPage`, `ProjectDetailPage`, `Stepper`, `StepPanel`, `CharacterCard`, `ChapterCard`, `BookText` (or modal), `AuthContext`.

`AuthContext` holds `{ email, name }`, sets `X-User-Email`, persists across refresh, clears on sign out.

### 6.3 Polling

On Detail only:

- If `action === "wait"`: `GET /api/projects/:id` about **every 1s**.
- Stop on unmount, route change, and when `action !== "wait"`.
- After POST 202, apply the response body immediately, then poll.
- Disable the primary button when `action` is `wait` (and while the POST is in flight). **409 `in_flight` is the real duplicate guard** — do not rely on the client alone.
- Do **not** poll when `action` is `recover` or `retry`.
- Do **not** poll the list. Remount/focus refetch is enough.

### 6.4 Routing

React Router (browser history). Unknown project id → list (or a small not-found). Unauthenticated → Identity.

---

## 7. Gemini

- Key from env (`GEMINI_API_KEY`). Never commit it. Ship `.env.example`.
- Current **text** model + current **image** model (Nano Banana family). IDs change — pick current ones at implementation time and record them in `DECISIONS.md`.
- Follow the notebook for steps 1–5: style (user optional vs generated), adult characters only, structured JSON, conversation chaining, portraits then chapter illustration **reusing portraits**.
- Send book content **once**; reuse `gemini` session on disk.
- One attempt per user click. User retries on failure.
- Check free-tier **image** rate limits before burning quota in manual UAT.
- Python **SDK** is preferred on this stack (conversation API wrapped). REST is acceptable if the SDK lags; not a downgrade.

---

## 8. Testing

`./test.sh` runs **pytest and vitest**; either failure fails the script. Paste a **real** run into `TESTING.md`.

### 8.1 Backend

**Pure functions:** step order; `can_claim` (live boot → no, stale boot → yes, failed → yes, idle → yes); success vs fail cursor; truncate 2/1; `to_view` action/stuck/pill.

**HTTP (temp data dir, fake Gemini):**

1. Happy path: create → five named POSTs → 202s → GET until `status=done`. Fake records **one book send** and **one call per step**.
2. Duplicate: two concurrent POSTs on the same step → one 202, one 409, fake called **once**.
3. Restart: leave `running` with a **foreign** `run_boot_id` → **GET list and GET detail** both `stuck: true` and `action: recover` → POST current step → 202 and a **new** fake call.
4. Failure: fake raises → `run=failed`, cursor unchanged, retry POST allowed and calls fake again.

Fake Gemini is injected; **no network**.

### 8.2 Frontend

Vitest + Testing Library, mocked `fetch`:

- Identity: invalid vs valid.
- List: empty vs a row with a pill.
- StepPanel (or Detail): `action` `run` \| `wait` \| `retry` \| `recover` \| `none` — copy and button.

Skip: CSS, CharacterCard layout, Playwright, coverage %, real Gemini, load tests.

Optional only if it stays short: fake timers prove polling starts when `action === wait` and stops otherwise.

### 8.3 Deliberately untested

E2E browser, Gemini prompt quality, `fcntl` in isolation (covered by concurrent POST), list polling, SSE.

---

## 9. Scripts and env

**`./start.sh`:** create venv if needed, install backend + frontend deps if needed, run uvicorn **`--workers 1`** and Vite. Print URLs. Trap signals so both die together.

**`./test.sh`:** pytest (backend) then vitest run (frontend), non-zero if either fails.

**`.env.example`:** `GEMINI_API_KEY=`, `GEMINI_TEXT_MODEL=`, `GEMINI_IMAGE_MODEL=`, backend bind host/port as needed.

`data/` gitignored. No Compose.

---

## 10. UI / copy notes

- In-progress names the step (`current_step`), not “Loading…”.
- Stuck copy: interrupted (server restarted); prior steps kept; recover is safe.
- Error copy: that step failed; retry that step only.
- Done: no auto-regenerate.
- Demo recover is two-step (clear stuck, then Generate). **Ours is one POST.** Say so in `DECISIONS.md` if asked.

Match or beat `app-demo.html` visually (tokens already in the mock). Empty / loading / error / stuck all designed, not leftover spinners.

---

## 11. Non-goals

- Auto-retry loops, rate-limit infrastructure, S3/CDN, public hosting.
- Auth beyond email header.
- Postgres/SQLite, Docker, Next.js, SSE/WebSocket, TanStack Query, Redux.
- Generic step engine, attempt history, sample-book picker, extra notebook sections (unless time left **after** the required product).
- Type generation from OpenAPI.
- Multiple uvicorn workers.

---

## 12. Open questions

Resolve at implementation time; record in `DECISIONS.md` if the answer is a real trade-off.

1. **Exact Gemini model IDs** and SDK field names for file upload + conversation chaining (from notebook + current docs).
2. **Identity persistence:** `localStorage` vs `sessionStorage`.
3. **Poll interval:** 1000ms is the default; change only if UAT feels noisy or laggy.
4. **Book size cap** (e.g. 1 MB) — not in the brief; pick a sane limit so one file cannot stall the process.
5. **Project id format** — UUID is the default.
6. **SPA in production-like start:** Vite dev + proxy is enough for reviewers; serving `frontend/dist` from FastAPI is optional.
7. **`GET /me` on boot:** client has persisted email; still call `/me` to refresh name, or trust local persistence.
8. **Worker fence (`run_id` vs `run_boot_id` only):** boot id is enough for crash-only. A per-claim uuid is extra safety for late writes; add only if the worker can outlive a recover in the same process (it should not, given A1).
9. **Rename `DECISION.md` → `DECISIONS.md`** to match the brief.

---

## 13. Implementation order (suggested)

1. Backend storage + flock + `to_view` / `can_claim` + tests (no Gemini).
2. HTTP identify/projects/steps with fake Gemini; tests 8.1.
3. Real Gemini adapter behind the same interface; one manual notebook-equivalent UAT.
4. Frontend screens + poll; RTL tests 8.2.
5. `start.sh` / `test.sh` / README / TESTING.md (real report) / DECISIONS.md.
6. Polish UI against the demo; manual two-tab + refresh + restart UAT.

Let tests lead each backend slice so the copilot cannot silently drop the lock or `to_view` on the list path.
