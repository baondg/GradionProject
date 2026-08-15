# Decisions

Decisions only — not a worklog. Each one below explains what I chose, what the AI suggested instead, and what it cost me.

## FastAPI + React, not TypeScript everywhere

Cursor's first offer was TypeScript end to end — Express on the backend, the JS Gemini SDK — so we would not have to keep two type systems in sync. I pushed back. The reference notebook's conversation API is wrapped in the Python SDK, and Gemini calls are slow (10–30+ seconds) and synchronous. I wanted the event loop free to keep answering GET requests while a worker thread sat inside a Gemini call. FastAPI, one uvicorn worker, and a thread pool for the Gemini calls was the smaller lie to tell myself.

The cost is real: Pydantic models on the backend and TypeScript types on the frontend now describe the same JSON twice, by hand. I made `to_view()` the single place that shapes that JSON, so at least there's one seam instead of many, and `./test.sh` fails the whole build if either pytest or vitest fails.

## JSON files on disk, not a database

This was my call, not the AI's. The brief said JSON is fine if you handle concurrent writes correctly, and at this scope — one project per user, five pipeline steps — a database felt like weight the project didn't need. One JSON file per project, one `users.json`. No migrations, no ORM, no schema to keep in sync with Pydantic.

I underestimated the "concurrent writes correctly" part at first. Cursor pushed back when I treated "one file per project" as automatically safe: refresh the page, open a second tab, double-click a button, and two POSTs can both read `idle`, both decide the project is free, and both call Gemini. That pushback was right, and it's why the storage layer needed its own decision below.

## A file lock, not atomic rename, not a database transaction

The fix for the concurrent-write problem is a per-project `fcntl` flock around the read-check-write cycle. `users.json` gets its own separate lock. One worker process only, so I never had to invent a distributed lock — flock is enough when there's exactly one process touching the files.

Cursor's own snippets treated atomic rename (write to a temp file, then rename over the real one) as if that were the concurrency fix. I overrode that. Atomic rename stops you from reading a half-written file; it does nothing to stop two requests from both deciding it's safe to start a Gemini call. The flock is the actual lock — it serializes the read-check-write, not just the write. The cost is that a hung thread inside a live process holds that lock's "running" state open until the process itself dies. I accepted that trade instead of building anything more sophisticated.

## Two fields for progress, not one status enum

Cursor's first instinct, and the brief's own example, was a single `status` field: `idle`, `running`, `done`, `failed`. That can't express "style is finished, characters is running" — which is exactly the state a page refresh in the middle of a step needs to read correctly. So I split it into two things stored on disk: `completed_step` (a cursor — how far the project has actually gotten) and `run` (`idle`, `running`, or `failed` — what the current step is doing right now). The next step to run is just implied by `completed_step` plus one. There's no `stuck` value stored anywhere; `stuck` is a fact I derive, not a fact I write.

## `boot_id` recovery, not a timeout or a startup sweep

A crash can leave a project's `run` field stuck at `running` forever, since nothing else will ever flip it back. Cursor's answer was the demo's own answer: an 8-second wall-clock timeout, plus a startup sweep that rewrites every project to `failed` when the server boots. I overrode both. An 8-second timer next to a 30-second image call will call a perfectly live run "stuck" and invite a second Gemini call on top of the first one — and the brief explicitly forbids duplicate calls. A boot-time sweep also means the server writes to disk before it's served a single GET, and I wanted GET to stay read-only, always.

What I landed on: each process mints a `BOOT_ID` when it starts, writes it into the project as `run_boot_id` the moment it claims a step, and a project only counts as `stuck` when `run == running` and the stored boot id no longer matches the current process's boot id. Recovering a stuck run is just the same POST you'd send to run any step — not the demo's two-click "clear stuck, then Generate." The cost: if the *same* process wedges on a step (no crash, no restart), that project looks like `wait` forever, with no automatic way out. I wrote that limitation down instead of hiding it.

## FakeGeminiClient by default; OpenRouter tried and dropped

I first looked at OpenRouter as a way to reach Gemini without dealing with an AI Studio key directly. That didn't survive contact with the actual pipeline: the notebook's chaining (`previous_interaction_id`, uploaded file references) depends on Google's stateful Interactions and Files APIs, which only the `google-genai` SDK wraps — a generic proxy like OpenRouter doesn't expose that shape, and I burned through free credits confirming it before giving up on the idea. I switched to calling `google-genai` directly and built the app so real calls are optional, not required.

`create_app(gemini=...)` is the seam that makes that possible. Tests always inject a `FakeGeminiClient` — no network, no key needed. `./start.sh` can set `USE_FAKE_GEMINI=1` so anyone can walk all five pipeline steps without an AI Studio key at all; unset it and set `GEMINI_API_KEY` to hit the live notebook path instead. Fake portraits are a tiny real PNG, not a placeholder string, so the UI never has to render a broken `<img>`. The cost is that the fake path proves the *plumbing* — resume, no duplicate calls, correct chaining — but it can't prove real image quality. I say so plainly in the last section of this file.

## No auto-retry on Gemini calls

The reference notebook turns on the SDK's built-in retry (`HttpRetryOptions(attempts=5)`), and my first instinct was to keep it, since the notebook does. Cursor and my own plan both pushed back: never auto-retry a Gemini call. Each `interactions.create` is one user click; if it fails, the user sees that and clicks again themselves. Auto-retry on a call that's already partially succeeded, or that fails for a reason a retry won't fix (a bad model ID, a rate limit), risks a second image generation and a second bill for one click — silently. I dropped the SDK retry loop entirely. The cost is that a single 429 or 404 now becomes a visible `run: failed` instead of quietly succeeding on the third or fourth attempt. I'd rather the user see the failure than pay twice without knowing it.

## Polling over WebSockets or SSE

Cursor wanted TanStack Query or server-sent events so the frontend would "know" the instant a portrait landed. I kept it simpler: a fat `to_view()` response (`status`, `action`, `steps[]`, `stuck`, `current_step`) and a plain ~1-second GET poll on the Detail page, and only while `action === "wait"`. The list page just fetches once on mount — it doesn't poll at all. React switches its primary button off `action` alone; it never re-derives status from raw fields itself.

The actual guard against duplicate work isn't a disabled button in the UI — it's a `409 in_flight` response from the backend, under the same flock described above. A disabled button is just a UI nicety on top of a lock that exists either way. The cost of polling over a push-based approach is up to a second of lag before a finished portrait shows up. At this scope, that's a trade I was happy to make for not running a second transport (WebSocket/SSE infrastructure) alongside plain HTTP.

## Email header auth in `localStorage`, not JWT

The plan left `localStorage` versus `sessionStorage` open, and I picked `localStorage`: `{ email, name }` under `biStudio.identity`, so a refresh doesn't log anyone out. Sign-out is client-only — it just drops that key. There's no JWT, no session table, no expiry.

Cursor caught a real bug in my first pass at this: I had portraits rendering through a plain `<img src={portrait_url}>`. File bytes are actually served behind `GET /api/projects/:id/files/...`, gated on an `X-User-Email` header, and a bare `<img>` tag can't attach a custom header — every image would 401. I built `AuthImage` instead: it fetches the bytes with the header attached and hands the browser a blob URL. That costs an extra request and a blob-URL lifecycle to manage per image, but it's the only way the auth model I chose actually works for images. The security trade-off in the identity model itself is real and I'm naming it directly: an email header with no token and no session is trivially spoofable by anyone who can set their own headers. That's acceptable for a take-home review, not for anything that needs to hold up against a real adversary.

## Bonus: per-step attempt history

Append-only log on `project.json`: `attempts[]`, each entry `{step, at, outcome, message}`. Written in `_finish_ok` / `_finish_fail`, under the same flock, and only when `run_boot_id` still matches the boot that claimed the step — so a wedged old process can't write a stale attempt after a newer process has moved on. This log is purely informational: `can_claim`, the `action` matrix inside `to_view()`, and `completed_step` never read it. Detail includes the full list; the list page doesn't, to keep that response small. Cost is just more JSON on disk, nothing structural.

## Bonus: CI

GitHub Actions (`.github/workflows/test.yml`) runs the same pytest and vitest pair on every push and pull request against `main`/`master`, with no Gemini key configured — tests always inject `FakeGeminiClient`. The point was to make the CI harness the actual gate, not a reviewer's laptop. Cost is Ubuntu install time on every run, nothing more.

---

If I had one more day, I'd run the live notebook path through the real UI — generated style, two adult characters, two portraits, one chapter, one illustration that reuses the stored portrait bytes — on a key that can actually reach the current text and image models, and I'd add a distinct "model unavailable" error instead of a generic `gemini_error`. The fake path already proves resume and no-duplicate-calls; the piece it can't prove is real image quality.