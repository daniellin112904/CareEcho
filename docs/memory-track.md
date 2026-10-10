# Memory track: decisions log

What changed on the memory side, every decision behind it, and what each one means for the rest
of the code. Read this before touching `backend/app/store.py`, `backend/app/db.py`,
`backend/app/memory/`, or the database.

**Status (Saturday, October 10, 2026):** steps 1 to 4 are done and pushed on the `TrackB_Memory`
branch; `main` is untouched. The agent, the patient screen, and the reminders read memories from Tiger Data,
and `POST /sessions/transcript` turns what a caregiver says into **pending** memories with Gemini.
Confirming and rejecting them (step 5) is next: until then, nothing extracted is ever spoken.

| Step | What | State |
|---|---|---|
| 1 | Setup, schema changes, apply to Tiger Cloud | done |
| 2 | Database connection, demo data, seed script | done |
| 3 | The store reads memories from Tiger Data | done |
| 4 | `POST /sessions/transcript`: Gemini extraction into pending memories | done |
| 5 | Confirm and reject endpoints, plus minimal staff cards | next |

## Quick start

From `backend/`, on Linux or WSL (the README has the PowerShell version):

```bash
uv venv .venv                                   # or: python3 -m venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python scripts/init_db.py             # safe to run again: changes nothing if up to date
.venv/bin/python scripts/seed_demo.py           # before every demo: resets Rose's memories
.venv/bin/python scripts/extraction_tests.py --offline   # free checks of the extraction code
.venv/bin/python -m uvicorn app.main:app --reload
```

`backend/.env` also needs:
- **`STAFF_PIN`**: the team's shared PIN, **digits only** (the PIN screen strips anything else).
  Without it, every staff page and endpoint refuses on purpose, extraction included. Never commit it.
- **`ELEVENLABS_AGENT_ID=agent_3901m4hzstsne44r6p7ddfmspgm1`**: the Vela agent on the team's
  ElevenLabs account. It's an ID, not a secret: sessions still need the API key. **Don't run
  `scripts/create_agent.py` without it set** (that creates a second agent). With it set, the script
  re-applies `app/voice/agent.py` to the live agent everyone tests against, so check with the voice
  owner first.

To run without the database (for example, if the venue Wi-Fi fails), set `DATABASE_URL=` (empty)
in `backend/.env` and restart. See decision 16.

## What changed

| File | Change |
|---|---|
| `backend/app/memory/schema.sql` | New `patients` table, plus a section of changes made after the first run (decisions 6 to 13) |
| `backend/app/db.py` | **New.** The connection pool (decision 15) |
| `backend/app/memory/demo.py` | **New.** The demo patient and memories, timed relative to now (decision 22) |
| `backend/scripts/seed_demo.py` | **New.** Resets the demo patient in Tiger Data (decision 23) |
| `backend/app/store.py` | Patient and memory reads now use Tiger Data, with the demo fallback (decisions 16 to 20) |
| `backend/app/memory/routes.py` | `GET /memories/current` reads through the store; the mock list is gone (decision 21) |
| `backend/app/memory/context.py` | New `facts_from(memories, now)`; `build_facts` calls it (decision 24) |
| `backend/scripts/safety_tests.py` | The dentist facts are built by the real code; one new check (decision 24) |
| `backend/requirements.txt` | `psycopg[binary]` became `psycopg[binary,pool]` (decision 4) |
| `backend/app/memory/extraction.py` | **New (step 4).** The Gemini prompt, the call, and the checks done in code (decisions 28 to 36) |
| `backend/app/memory/routes.py` | **Step 4:** staff-only `POST /sessions/transcript` (decisions 26, 27) |
| `backend/app/main.py`, `backend/.env.example` | **Step 4:** the new staff router; optional `GEMINI_MODEL` |
| `backend/app/store.py` | **Step 4:** `add_session`, `finish_session`; `all_day` and `session_id` in memory rows |
| `backend/app/memory/schema.sql`, `context.py`, `demo.py`, `seed_demo.py` | **Step 4:** all-day plans (decision 25) |
| `backend/app/voice/reminders.py` | **Step 4:** one guard so all-day plans get no timed reminder (decision 25; voice-owned file) |
| `frontend/src/api.ts`, `pages/patient/PatientPage.tsx`, `pages/care/MemoriesPage.tsx` | **Step 4:** all-day plans show a day without a time (decision 25; interface-owned files) |
| `backend/scripts/extraction_tests.py` | **New (step 4).** Offline and live extraction tests (decision 37) |

## Decisions

Each decision gives what was decided, why, and what it means for other code or other people.

### Setup

**1. Memory work happens on `TrackB_Memory`; `main` is untouched.**
- *Why:* agreed with the team lead, so `main` stays a working demo while memory changes land.
- *How:* the branch had no commits of its own and was 11 commits behind `main`. A normal switch
  failed because the uncommitted `.gitignore` edit conflicted, so the branch pointer was
  fast-forwarded with `git fetch . main:TrackB_Memory` (refuses anything but a fast-forward), then
  switched to.
- *Implications:* the uncommitted `.gitignore` change and the `plan.md` deletion from `main`'s
  working tree came along. They went into their own commit (`chore: hide planning docs until
  submission`), separate from the memory work.

**2. The docs are hidden until the project is done, except this decision log** (team lead's
decision).
- *How:* `.gitignore` ignores `docs/*` and un-ignores `!docs/memory-track.md`. It has to be
  `docs/*`, not `docs/`: git can't un-ignore a file inside a folder that's ignored as a whole.
- *Why this file is shared:* it's written so teammates can follow the memory work, and it lists what
  they must do after pulling. The planning docs (`Overview.md`, `Plan.md`, `Responsibility.md`) and
  the generated `extraction-report.md` stay local.
- *Implications:*
  - To share another doc later, add another `!docs/<name>` line.
  - `docs/safety-report.md` is still tracked: ignoring only affects files git doesn't track yet.
    To hide it, run `git rm --cached docs/safety-report.md`.
  - The old root `plan.md` (identical to `docs/Overview.md`) is already in `origin/main`'s history,
    so deleting it only removes it from now on.

**3. The backend environment is `backend/.venv`, made with `uv`, on Python 3.14.**
- *Why:* `uv` was installed and chose 3.14. The system Python is 3.10.
- *Implications:*
  - The code has only been run on 3.14. It needs at least 3.10 (it uses `str | None`).
  - On 3.10, `datetime.fromisoformat` rejects a trailing `Z`. Extraction (step 4) should normalize
    Gemini's timestamps anyway, so this doesn't matter which version runs it.

**4. Added the `pool` extra: `psycopg[binary,pool]`.**
- *Why:* the API handles requests on several threads, so a shared pool beats one connection per
  request.
- *Implications:* everyone needs to reinstall from `requirements.txt` once.

**5. Fixed `backend/.env` line 8:** a comment was missing its `#`.
- *Why:* `python-dotenv` printed a parse warning on every start. No values changed.
- *Implications:* if your own `.env` came from the same copy, fix the same line.

### Schema (`backend/app/memory/schema.sql`)

**State found before any change:** `schema.sql` had been applied on Friday and every table was
empty. `schema_voice.sql` had **never** been applied, so there was no `family_messages`, no
`reminders_sent`, and no `interactions.id` or `interactions.conversation_id`.

**6. New `patients` table, holding only `id`, `name`, `created_at`.**
- *Why:* the patient's name was hard-coded in two places. A table makes `patient_id` a real
  reference (decision 8).
- *Not added:* a timezone column. `TIMEZONE` in `.env` stays the only source, so two settings
  can't disagree.
- *Implications:* the Rose row is created by `seed_demo.py`, not by the schema file.

**7. New `memories.certainty` column: `definite` or `tentative`.**
- *Why:* extraction outputs a certainty, but a pending row only stores `status = 'pending'`.
  Without this column a pending memory loses whether it was tentative.
- *Implications:*
  - Confirming (step 5) sets `status` from `certainty`, unless the caregiver changes it.
  - `NULL` is allowed, for rows that never went through extraction, like patient self-reports.

**8. Foreign keys from `memories.patient_id` and `sessions.patient_id` to `patients(id)`.**
- *Why:* the tables were empty, so it was free to add. It guarantees no memory belongs to an
  unknown patient.
- *Not added:* the same keys on `alerts` and `interactions`. They still live in JSON files, and
  can get keys when they move to SQL.
- *Implications:* inserting a memory or session fails with `ForeignKeyViolation` until the patient
  row exists. Run `seed_demo.py` on any new database.

**9. Check: a `confirmed` or `tentative` memory must have `confirmed_at`.**
- *Why:* "nothing is spoken without a caregiver confirming it" becomes a database rule, not just
  a code convention.
- *Implications:* the confirm endpoint must set `confirmed_at`. Otherwise the database rejects
  the write with `CheckViolation`.

**10. A partial unique index on `memories(supersedes_id)` for confirmed, tentative, and superseded
rows.**
- *Why:* a version chain can't fork. A memory is replaced by at most one confirmed version, so
  there's always exactly one current version. Several pending proposals for the same memory are
  still allowed, since a caregiver may say two different updates.
- *Implications for step 5:*
  - Confirming an update must mark the old version `superseded` and insert or confirm the new one
    in the same transaction.
  - Confirming a second competing proposal fails with `UniqueViolation`. The endpoint should
    catch it and return 409 ("this memory was already updated").

**11. New `sessions.extraction` column (JSONB): Gemini's raw output for each session.**
- *Why:* when Gemini gets a date wrong, you can see exactly what it returned. It's also the
  starting material for the 20-sentence extraction test set.
- *Implications:* step 4 should save the response here even when validation rejects it.

**12. Deliberately not done yet:**
- **No `CHECK` on `memories.kind`.** Extraction kinds (appointment, plan, routine, person…) and
  self-report kinds (medication, meal, feeling…) share the column. Validate in Pydantic instead.
- **`expires_at` stays unused.** `build_facts` keeps its rule of hiding events more than 2 hours
  after they start. Revisit if a memory needs its own end time (a week-long visit, for example).

**13. How changes are written:** an append-only section at the end of `schema.sql`.
- *Why:*
  - `CREATE TABLE IF NOT EXISTS` never changes an existing table, so new columns use
    `ALTER TABLE … ADD COLUMN IF NOT EXISTS`.
  - Postgres has no `ADD CONSTRAINT IF NOT EXISTS`, so constraints are dropped and re-added.
    That's cheap on small tables.
  - A `DO $$…$$` block isn't possible: `scripts/init_db.py` splits the file on every `;`.
- *Implications:*
  - Never put a `;` inside a string, comment, or function body in `schema.sql` or
    `schema_voice.sql`.
  - Every statement must work on both a new and an existing database.
  - Add new changes at the end.

**14. How it was applied:**
- A dry run first: every statement ran in one transaction that was always rolled back. The
  continuous-aggregate `CREATE` was skipped because TimescaleDB refuses it inside a transaction,
  and it already existed.
- Then `init_db.py` against Tiger Cloud, then `init_db.py` again to prove it's safe to repeat.
- *Implications:* the `schema_voice.sql` tables and columns now exist but are empty. The app still
  writes family messages, reminders, interactions, and alerts to JSON until each moves to SQL.

### Code

**15. `backend/app/db.py`: one shared, lazily opened connection pool.**
- *Why lazy:* importing the app or a script never connects by itself.
- *Settings:*
  - 1 to 5 connections.
  - Rows come back as dicts.
  - 3-second timeouts for getting and opening a connection. That's under the agent's 5-second tool
    timeout, so a slow database becomes "not sure" rather than a hung call.
  - Each connection is tested before use, because cloud databases drop idle ones.
  - The pool is closed at exit. Without that, scripts ended with a thread-shutdown traceback.
- *Implications:* use `with db.pool().connection() as conn:`. Each block is one transaction: it
  commits at the end, or rolls back if anything inside raises.

**16. No database means demo data, and only when chosen.** With `DATABASE_URL` empty, the store
serves `demo_memories()` instead of querying.
- *Why:* it's a safety net for a demo without internet. It is **never automatic**: switching data
  sources silently mid-demo could change what the agent says without anyone noticing.
- *Implications:*
  - If the database is configured but unreachable, the agent's lookup fails and it says it isn't
    sure. That's the existing `LOOKUP_FAILED` path in `frontend/src/voice/agentTools.ts`.
  - The patient screen shows nothing in that case.
  - To switch, empty `DATABASE_URL` and restart the backend.

**17. The store always returns plain strings.** `_plain()` turns UUIDs into strings and times into
ISO 8601 strings with a timezone.
- *Why:* `build_facts`, the reminders, and the receipts call `fromisoformat()` on these values, and
  the frontend expects JSON-safe strings. psycopg returns `UUID` and `datetime` objects.
- *Implications:* new code must return rows through the store, never raw psycopg rows. IDs are
  dashed UUID strings, like `3b67c76f-3612-…`.

**18. `current_memories` filters to confirmed and tentative in SQL.**
- *Ordering:* by `event_at`, with untimed memories last.
- *Why:* `GET /memories/current` has no login (the patient screen uses it), so pending, rejected,
  and superseded memories must never appear there. `build_facts` checks the status again; two
  checks are deliberate.
- *Implications:* staff views that need pending memories (step 5) need their own staff-only
  endpoint and store function. Don't widen this one.

**19. `memories_by_id` includes superseded versions and skips IDs that aren't UUIDs.**
- *Why:* a receipt should show the version that was true when the answer was given. Answers
  logged before the database contain `mock-1`, and Postgres would reject the whole query over it.
- *Implications:* receipts for those old answers show "checked N, none named".

**20. `patient_name` falls back to "Rose"** if the patient row is missing.
- *Why:* starting a conversation shouldn't fail because the seed wasn't run.
- *Implications:* a missing seed shows up as no memories, not as a crash.

**21. Removed the circular import between the store and the memory routes.**
- *Before:* `store.py` imported its data from the mock in `memory/routes.py`.
- *Now:* the route calls the store. `topic` is still accepted and ignored, matching `build_facts`,
  which returns every current memory so a bad topic guess can't hide the answer.

**22. `backend/app/memory/demo.py` is the single source of demo data.** It's used by the seed
script, the no-database fallback, and the safety tests.

What it contains:

| Memory | Status | Rule it demonstrates |
|---|---|---|
| Dentist appointment, 3 PM, Anna picks up at 2:30 | confirmed | the main demo question |
| Its earlier version, pickup at 2:00 | superseded | never spoken; history and receipts can show it |
| Lunch with Joan, the next day at 12:30 | tentative | said as not certain |
| Mark is your son and lives in Boston | confirmed, no time | never expires |
| Haircut, two days later at 10 | pending | never spoken |

- *The 3 PM rule:* the dentist is today at 3 PM if that's at least 90 minutes away, otherwise
  tomorrow at 3 PM. The pickup is always "two thirty", matching the pitch script and the existing
  safety tests.
- *No shared names between memories:* answer receipts match memories by their words (`receipt()`
  in `backend/app/memory/events.py`), so two memories naming Anna would both claim every Anna
  answer.
- *Fresh random IDs on each seed:* the patient screen remembers played reminders by memory ID in
  the browser, so new IDs mean a reseeded day gets its reminders again.
- *Fallback timing:* in fallback mode the memories are timed once per server start, so the plan
  can't jump from today to tomorrow during a demo.
- *Implications:*
  - Change the demo story here, and only here.
  - Keep each memory covering a rule, and avoid shared names until receipts improve.

**23. `scripts/seed_demo.py` resets only the demo patient's memory data.**
- *What it deletes:* Rose's memories, sessions, and "Remind now" records, then it inserts Rose and
  the demo memories. It all happens in one transaction, so it either fully happens or not at all.
- *What it leaves:* interactions, alerts, and family messages. They're still JSON files in
  `backend/data/`.
- *Implications:*
  - Run it before every demo.
  - It wipes anything a caregiver confirmed for the demo patient, so don't use it on data you
    want to keep.
  - It's the starting point for the planned `POST /demo/reset`.

**24. The safety tests use the real fact format.**
- *What changed:* `facts_from(memories, now)` is a new pure function in
  `backend/app/memory/context.py`; `build_facts` calls it. The tests' `DENTIST` facts are now
  built by it from the demo memory at a fixed time (Saturday 1:20 PM, the simulated "now"),
  instead of a hand-written string.
- *Why:* before, the agent was tested on text nobody had checked against what the app sends. The
  new string was confirmed to be **identical** to the old one, so earlier live results still hold
  and no paid re-run was needed.
- *New check:* `demo-seed-safe` checks that the demo's pending and superseded memories never reach
  the agent.
- *Implications:*
  - The suite is now 31 checks. `docs/safety-report.md` still says 30/30 until the next full run.
  - If `build_facts`' wording ever changes, the agent tests automatically get the new wording.
    Re-run the suite then.

### Step 4: extraction (`POST /sessions/transcript`)

Decided with the team lead before building: medication is never extracted, the full test set
(offline and live) is part of this step, and plans with a day but no time get proper all-day
support.

**25. All-day plans: a new `memories.all_day` column** (`BOOLEAN NOT NULL DEFAULT false`).
- *Why:* caregivers often give a day with no time ("Anna might visit Saturday" is the example in
  Plan.md). With only `event_at`, such a plan would get an invented time ("12:00 AM"), or expire at
  2 AM that day, since timed events stop being told 2 hours after they start.
- *How:*
  - `event_at` is local midnight of that day.
  - `build_facts` says the day without a time ("Anna visit, Saturday, October 17"), and stops
    telling it once that day is over.
  - Reminders skip it unless it has a pickup time, because there's no clock time to remind at.
  - The patient screen shows "Coming up: Anna visit, on Saturday" until the day ends.
  - The staff Memories page shows the date only.
- *Implications for other owners:*
  - **Voice:** one guard at the top of `_plan()` in `backend/app/voice/reminders.py`. "Remind now"
    on an all-day plan returns the existing 400 message.
  - **Interface:** `Memory.all_day` in `api.ts`, and `hasPassed()` / `whenWords()` in
    `PatientPage.tsx`.
  - Anything new that shows `event_at` must check `all_day` first.

**26. Extraction is a staff-only endpoint, and needs the database.**
- *Request:* `POST /sessions/transcript` with the `X-Staff-Pin` header and body
  `{"transcript": "...", "source": "caregiver_typed"}`. The transcript is 1 to 4000 characters.
  `source` may be `caregiver_session` once speech to text (Scribe) sends audio transcripts.
- *Reply:* 201 with
  `{"session_id", "candidates": [pending memory + "warnings"], "dropped": [{"summary", "reason"}]}`.
- *Errors:*

  | Code | When |
  |---|---|
  | 401 | wrong or missing PIN |
  | 422 | empty transcript |
  | 503 | no `DATABASE_URL`; the patient row is missing (run the seed); or Gemini's rate limit, with a `Retry-After` header |
  | 502 | any other Gemini failure |

- *Why staff-only:* only a caregiver may put something on the path to being spoken. The demo
  fallback (decision 16) covers the patient side only; extraction without a database answers 503.
- *Implications:* the step 5 UI calls this, then shows the candidates and their warnings as cards.

**27. Transaction boundaries: the words are saved first, and no connection is held while Gemini
works.**
- *Order:*
  1. `store.add_session()` saves the transcript in its own transaction.
  2. Gemini is called with no database connection open.
  3. `store.finish_session()` saves Gemini's record in `sessions.extraction` and inserts the
     pending memories, in one transaction.
- *On failure:* the session still records `{"error", "raw"}`, and the caregiver is told the words
  were saved.
- *Why:*
  - A caregiver's words are never lost to a Gemini failure.
  - The pool has 5 connections, and Gemini takes several seconds, so holding one during the call
    could starve the patient side.
- *Implications:* a session can exist with no memories. That's normal: nothing to save, an error,
  or everything left out.

**28. Gemini fills in a form; code builds the times.**
- *How:* Gemini returns a fixed JSON shape (`Candidate` in `extraction.py`). Each candidate has a
  local `date` (YYYY-MM-DD) and clock `time` (HH:MM), never a timestamp. Code combines them with
  `TIMEZONE`.
- *Why:* offsets and daylight saving are exactly what language models get wrong. With this split,
  the test case on the night the clocks change is handled entirely by code (Sunday, November 1,
  2026 at 9 AM is saved as `-05:00`).
- *Detail keys:* the form's flat fields become `details = {who, pickup_at, place}`. Reminders
  depend on exactly `who` and `pickup_at`, so free-form keys could have silently broken them.
- *Implications:* add a new detail by adding a field to `Candidate` and to `validate()`. Never
  accept free-form keys from Gemini.

**29. Gemini gets a calendar, and fixed rules for days and times.**
- *The calendar:* the prompt lists the next 14 days with their weekdays, so "Tuesday" is a lookup,
  not arithmetic.
- *The rules:*
  - "this Tuesday", "next Tuesday", and "Tuesday" all mean the first Tuesday after today, never
    today. This is a deliberate convention, because "next Tuesday" is ambiguous in English and the
    caregiver sees the resolved date before confirming.
  - A clock time with no day is the next time it comes. Code applies the same rule as a backup,
    with a warning.
  - No time said means an all-day plan. Gemini must never guess a time.
- *Implications:* if users expect "next Tuesday" to mean the week after, change the rule in the
  prompt and its test case together.

**30. Medication is never extracted.**
- *How, in three layers:*
  - the prompt tells Gemini to leave medicine out;
  - `medication` isn't an allowed kind;
  - a word list in code (pills, meds, dose, prescription, insulin, vitamins…) drops any candidate
    whose summary or quote mentions medicine.
- *Why:* the agent's rules forbid ever suggesting taking, skipping, or changing a dose. A
  medication schedule it could read ("pill at 8 every morning") invites "it's time for your pill".
  The word list follows the project's "backup that doesn't rely on the AI" approach, like the
  emergency phrases.
- *Implications:*
  - The word list is deliberately strict, so a pharmacy errand ("pick up her prescription") is
    left out too.
  - Medication needs its own design if it's ever wanted, with new safety tests.

**31. What code drops, and what it only warns about.**
- *Dropped, with a reason in the reply:*
  - a candidate that can't be read (missing field, unknown kind, bad date or time);
  - medicine;
  - a plain repeat of a current memory;
  - an "update" that changes nothing;
  - anything beyond 10 per session.
- *Kept, with a warning for the caregiver:*
  - it already happened;
  - the pickup is at or after the start;
  - a pickup with no one named (no pickup reminder can be given);
  - no day was said, so the next occurrence was used;
  - the quote isn't the caregiver's exact words;
  - the summary was trimmed to 80 characters;
  - an update pointed at a memory that doesn't exist (saved as new);
  - an update left out a field the current version has.
- *Why:* each candidate is checked on its own, so one bad one never loses the others. Warnings
  mark what a human should look at before confirming, rather than silently changing it.
- *Implications:* the step 5 cards must show warnings next to the resolved time and the quote.

**32. Updates are complete new versions.**
- *How:* for a change ("Anna will pick her up at two instead"), Gemini returns the whole new
  version, with unchanged fields copied from the current memory, and the current memory's ID.
  Code sets `supersedes_id` only if that ID really is a current memory.
- *Why:* the version chain (decision 10) needs every version to be complete. The partial unique
  index only allows one confirmed successor.
- *Implications for step 5:* confirming marks the old version `superseded` in the same
  transaction, and a second competing proposal gets 409.
- *Not done yet:* a proposal isn't compared with other *pending* proposals, so saying the same
  change twice makes two cards.

**33. The model is `gemini-3.5-flash`, and can be changed with `GEMINI_MODEL`.**
- *Settings:* temperature 0, medium thinking (resolving "in two hours" is arithmetic, and a
  caregiver can wait a few seconds), a 30-second timeout.
- *Why this model:* it's the model the agent already runs on, and the key can reach it.
  `sessions.extraction` records both the model asked for and the exact version that answered.
- *Implications:* compare another model with `extraction_tests.py --model <id>` before changing
  the default.

**34. One shared Gemini client, created under a lock.**
- *Why:* the first live test run found it. The SDK closes its connection when a `Client` object
  is garbage collected, so when several request threads each made a client, the extra ones
  closed the connection under the others ("Cannot send a request, as the client has been closed").
- *Implications:* never create `genai.Client` per request; use `_client()` in `extraction.py`.

**35. Gemini's free tier allows 5 requests a minute and 20 a day per model.**
- *Found by:* the first live runs. Gemini's 429 names the quota it enforced:
  `GenerateRequestsPerMinutePerProjectPerModel-FreeTier` (5), then
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier` (20, with a `retryDelay` of about 3.5 hours).
- *Observed:* the daily cap isn't enforced as a clean counter. Requests sometimes went through
  minutes after a daily 429. Code must therefore read each 429 rather than predict it.
- *How a 429 is classified:* `_rate_limit()` in `extraction.py`.
  - A `quotaId` containing `PerDay` means the daily cap; its `quotaValue` is the size.
  - `retryDelay` is the wait.
  - Any wait over 10 minutes counts as daily.
  - Without details, the wait is a minute.
  - `wait_words()` turns seconds into "about 28 seconds", "about 25 minutes", or "about 3 hours".
- *What the caregiver sees:* 503 with a `Retry-After` header and the words saved:
  - **daily:** "Gemini's daily limit of 20 requests was reached. The words were saved; try again in
    about 3 hours."
  - **per minute:** "Gemini is busy right now. The words were saved; try again in about 28
    seconds."
  - **any other failure:** still 502.
  - `sessions.extraction` records `daily` and `retry_after` for a failed session.
- *What the test suite does:*
  - It waits out a per-minute limit, at most `MAX_WAIT` (120 seconds).
  - A daily limit, or any longer wait, **stops the run at once**: remaining cases are marked
    ⏸ "not run" without calling Gemini, never as failures. (Before this fix, the suite slept
    through Gemini's multi-hour delay and looked hung.)
  - Exit codes: **0** all passed, **1** something failed, **2** nothing failed but some cases
    didn't run.
  - `--only` takes comma-separated names (an exact name picks just that case, so `tomorrow` doesn't
    also pick `day-after-tomorrow`). That lets the 21 cases be split across days on the free tier.
- *Implications:*
  - 20 requests a day is tight for a demo: rehearsals and a test run can use it up before judges
    try it. **Enable billing on the Google AI project before judging** (the team lead's decision);
    a full live run then costs a few cents, and `--workers 4` makes it fast.
  - The voice agent isn't affected: its model runs through ElevenLabs.

**36. Things extraction deliberately doesn't do:**
- **Cancellations.** "The dentist is cancelled" produces nothing: staff remove plans themselves.
  Step 5 needs a way for staff to retire a confirmed memory.
- **Instructions inside the transcript.** They're never followed; a test checks this.
- **Feelings, past events, small talk.** Never memories.

**37. Tests: `backend/scripts/extraction_tests.py`.**
- *Offline (20 checks, free):* hand-written Gemini answers go through `validate()`, plus all-day
  facts and reminders. Covers both sides of the daylight saving change, bad candidates, medication,
  duplicates, every warning, and the 10-candidate limit.
- *Live (21 cases):* real Gemini calls at a fixed moment (Saturday, October 10, 2026, 3:30 PM),
  with the demo memories, so the expected dates never change. Nothing is written to the database.
- *Output:* writes `docs/extraction-report.md`, and exits 1 on any failure.
- *Safety suite:* `safety_tests.py` has one more free memory-rule check (an all-day plan is told
  with no clock time, and only on its day). The suite is now 32 checks; `docs/safety-report.md`
  updates on the next full run.
- *Implications:* run the offline checks after any change to `extraction.py`. Run the live set
  after changing the prompt or the model.

**38. The frontend's dependencies are installed locally** (`frontend/node_modules`, git-ignored),
so the frontend could be type-checked and linted.
- *Implications:* none for git. `npm run build` and `npm run lint` both pass. The chunk-size
  warning was already there.

## Live extraction results so far

On the free tier, the live set has been run in pieces (Saturday, October 10, 2026).
`gemini-3.5-flash` is answered by `gemini-3.6-flash`.

- **10 of 21 cases passed; none failed:** `tomorrow`, `this-weekday`, `next-weekday`,
  `tentative-all-day`, `update-pickup`, `update-moved`, `update-now-certain`,
  `day-after-tomorrow`, `tonight`, and `dst` (Sunday, November 1 at 9 AM saved as `-05:00`).
- **Not run yet (11):** `in-two-hours`, `time-no-day`, `absolute-date`, `routine`, `person`,
  `preference`, `medication`, `nothing-to-save`, `repeat`, `two-in-one`, `ignores-instructions`.
  Run them with:
  `python scripts/extraction_tests.py --only in-two-hours,time-no-day,absolute-date,routine,person,preference,medication,nothing-to-save,repeat,two-in-one,ignores-instructions`
- **Endpoint, one real Gemini call:** still to do, the success path of `POST /sessions/transcript`.
  Its failure paths (no PIN, no database, empty text, daily limit, per-minute limit, other errors)
  have been checked, the limits by simulating Gemini's errors.

## Checked

- **Schema:** the dry run and both `init_db.py` runs succeeded.
- **Constraints**, tested in rolled-back transactions:
  - an unknown patient is rejected;
  - a confirmed memory without `confirmed_at` is rejected;
  - a second confirmed successor is rejected;
  - a bad `certainty` is rejected;
  - a second *pending* proposal is allowed.
- **Endpoints**, both with Tiger Data and in fallback mode:
  - `/memories/current` returns only confirmed and tentative memories, with string IDs and times;
  - `/voice/facts` has the dentist with the pickup and hides the haircut;
  - `/reminders/upcoming` responds;
  - `memories_by_id` skips `mock-1` and finds the superseded version;
  - the patient name is right;
  - fallback data stays the same across calls.
- **Safety suite:** all 6 memory-rule checks pass. The agent conversations weren't re-run (they
  cost ElevenLabs credits, and their input text is unchanged).

## Known issues and follow-ups

- **"Remind now" grammar is now reachable in the demo** (voice code, `backend/app/voice/reminders.py`
  line 73). After 1:30 PM the dentist is tomorrow, and the button produces: *"Rose, a reminder: Anna
  is picking you up at tomorrow at 2:30 in the afternoon for your dentist appointment."* The
  template adds "at" in front of a phrase that can already start with "tomorrow at". It's a
  one-line fix; the voice owner should decide.
- **No scheduled reminders in an afternoon demo.** After 1:30 PM the plan is tomorrow, more than
  12 hours away. Seed before 1:30 PM, or use "Remind now" once its grammar is fixed.
- **The tentative test has an odd time.** Its hand-written facts put Anna's visit at 11 AM, but the
  simulated time is 1:20 PM. It's left as is so results stay comparable; fix it at the next paid
  run.
- **The staff Memories page** still says "Showing sample data". The data is real now, but seeded.
  That's for the Interface owner.
- **A harmless warning:** `StarletteDeprecationWarning` from FastAPI's test client.

## Next: step 5

Step 4 (extraction) is described in decisions 25 to 38 above.

**Step 5.** Confirm and reject endpoints (staff only):
- *Confirm* sets `status` from `certainty` and sets `confirmed_at`. For updates, it marks the old
  version `superseded` in the same transaction, and maps `UniqueViolation` to 409.
- *Reject* sets `rejected`.
- *UI:* minimal Confirm/Reject cards on the staff Memories page, showing the resolved time, the
  caregiver's exact words, and the warnings from extraction, plus a box to type what a caregiver
  said (it calls `POST /sessions/transcript`).
- *Also needed:* a staff-only list of pending memories (`GET /memories/pending`), and a way for
  staff to retire a confirmed memory, since extraction ignores cancellations (decision 36).
