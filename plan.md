# Vela: voice and patient screen

One React app with two sides, backed by FastAPI and ElevenLabs.

| Side | URL | Who | Access |
|---|---|---|---|
| Patient | `/patient` | the person with dementia | open |
| Staff | `/care/...` | nurses, caregivers | staff PIN |

## Done

- **Talk to the companion.** The patient taps the orb, and a private ElevenLabs voice agent answers
  using what it's been told about their day.
- **Patient screen.** A calm, ElevenLabs-style kiosk: the date, the time in words, a living orb that
  moves and pulses with the voice, large captions, and the next confirmed plan.
- **Family messages.** Staff clone a consenting family member's voice, write a message, and it plays
  on the patient screen in that voice. The live companion always keeps its own neutral voice.
- **Staff PIN.** Protects every staff page and endpoint.
- **One look.** Staff pages share the patient screen's style (`frontend/src/theme.css`): light headlines, pill tabs and buttons, gray trays with white cards.
- **Calm conversations.** Replies are one or two sentences. The agent waits 20 seconds before
  checking in, then stays quiet, and the conversation ends by itself after 90 seconds of silence. It
  gets the real time every minute and never offers things it can't do (like playing music).

## How it works

```
Patient taps orb -> backend gives a one-time token + today's date -> ElevenLabs agent talks
Patient asks something -> agent calls get_memories -> answers only from what comes back
Staff writes message -> backend speaks it in the family voice (ElevenLabs) -> patient taps Play
```

## Moving to Tiger Data (for the memory teammate)

Every record the voice features save or read goes through one file: **`backend/app/store.py`**.
Today it writes JSON files in `backend/data/`. To switch, replace each function's body with the SQL
in its docstring. The endpoints, the agent, and the frontend don't change.

| In `store.py` | Today | Tiger Data |
|---|---|---|
| `current_memories`, `memories_by_id` | mock list in `memory/routes.py` | `memories` (`memories_by_id` should include superseded versions, for receipts) |
| `patient_name` | `"Rose"` | a patients table |
| `add_interaction`, `list_interactions` | `interactions.json` | `interactions` hypertable |
| `add_statement` | `statements.json` | `memories` rows with status `self_reported`, source `patient` |
| `add_alert`, `get_alert`, `list_alerts`, `resolve_alert` | `alerts.json` | `alerts` |
| `add_family_message`, `list_…`, `delete_…` | `family_messages.json` | `family_messages` (new) |
| `add_sent_reminder`, `recent_sent_reminders` | `reminders_now.json` | `reminders_sent` (new) |

- **Schema.** The new tables and two extra `interactions` columns are in
  `backend/app/memory/schema_voice.sql`, so `schema.sql` stays yours. `scripts/init_db.py` now runs
  both files.
- **Audio stays on disk.** Family message and reminder MP3s are a cache in `backend/data/`,
  regenerated from the text when missing, so they don't need a table.
- **IDs.** The mock memory ID `mock-1` isn't a UUID, so `interactions.memory_ids` (a `UUID[]`)
  accepts it only once real memories exist.
- **Snowflake life story.** Not wired yet. When `GET /life-story?q=` exists, the voice side adds a
  `search_life_story` tool to the agent (`app/voice/agent.py`) and its handler
  (`frontend/src/voice/agentTools.ts`).

## Next: trust features + first-language mode

Goal: every hard health question a judge asks has a feature we can show.

| Judge asks | Answer | Milestone |
|---|---|---|
| "Isn't a family voice deceptive?" | The companion is always a neutral AI voice. Cloned voices only read messages family wrote. | M1 |
| "How do you know it isn't making things up?" | It looks up confirmed memories live, and says "I'll ask Anna" when there's nothing. | M2 |
| "What if she says she fell?" | Calm reply plus an urgent staff alert, with a keyword backup that doesn't rely on the AI. | M3 |
| "Could it cause a double dose?" | It never confirms medication. What Rose says is logged as unverified. | M3 |
| "Can I see why it said that?" | Every answer links to the memory it came from, with the caregiver's exact words. | M4 |
| "What about patients who aren't English speakers?" | Rose can switch to her first language and the agent follows. | M5 |
| "How did you test it?" | 20 scripted safety checks with a pass/fail report. | M6 |

Order: M1 to M5 before the Saturday 6 PM freeze, M6 Saturday evening. Endpoints owned by the
memory teammate are marked *(Memory)*; until they exist, the tool handlers use mock data.

### M1. Lock the companion voice ✅ done
- [x] Companion always uses the stock voice: "Use this voice" and `PUT /voice/active` are gone
- [x] Staff page is now "Family messages": cloned voices are for messages only
- [x] `POST /family-messages`: staff write a message and pick a voice, the backend runs text to speech and caches the MP3
- [x] Patient screen: a "Recorded message from Anna" card with a warm orb and a big Play button

**How it works**
- **The lock.** No endpoint can change the companion's voice anymore. As a safety net, the first
  conversation after the backend starts checks the agent on ElevenLabs and resets it to the stock
  voice if anyone changed it in the dashboard. `scripts/create_agent.py` also re-applies the stock voice.
- **Making a message.** Staff pick a family voice and type the text. The backend turns it into speech
  once with ElevenLabs text to speech and saves the MP3 in `backend/data/` (not committed). Replays
  cost nothing and work without internet.
- **Only consented voices.** Clones made on the staff page get a `vela` label. Only labeled
  voices can read messages, so other voices on the ElevenLabs account can't be used.
- **Deleting.** Deleting a voice also deletes every message in that voice, so no audio outlives the
  consent behind it.
- **On the patient screen.** The newest message shows next to "Coming up" (checked every 15 seconds).
  While it plays, the small orb swirls and Anna's words show as a caption. Only one voice plays at a
  time: Play ends a conversation, and starting a conversation stops the message.
- **Code:** `backend/app/voice/routes.py`, `backend/app/voice/messages.py`,
  `frontend/src/pages/care/VoicesPage.tsx`, `FamilyMessageCard` in `PatientPage.tsx`

### M2. Live memory tools ✅ done
- [x] Client tools on the agent: `get_memories(topic)`, `ask_caregiver(question)`, `log_patient_statement(text, kind)`
- [x] Handled in `frontend/src/voice/agentTools.ts`, passed as `clientTools` in `startSession`
- [x] `get_memories` returns short spoken sentences, or `NO_MEMORY` so the agent says it isn't sure
- [x] Prompt: always look up before answering; ask the care team instead of guessing
- [x] Placeholder endpoints: `POST /alerts`, `POST /interactions`, `POST /patient/statements`, staff `GET /alerts`
- [x] Staff Alerts page lists open alerts (refreshes every 5 seconds) with "Mark resolved"
- [x] Alert notifications on every staff page: a toast, a soft chime, a red count on the Alerts tab,
      the count in the browser tab title, and desktop notifications when the tab is in the background

**How it works**
- **Live lookups, nothing baked in.** Facts are no longer pasted into the prompt at the start. On
  every question about plans or people, the agent calls `get_memories`, the browser asks
  `GET /voice/facts`, and the agent answers only from that. A plan confirmed mid-conversation is
  picked up on the next question. Only confirmed or tentative memories that haven't ended are
  returned; tentative ones are marked so the agent says they aren't certain.
- **Not sure means ask.** When the facts don't cover a question, the agent calls `ask_caregiver`,
  which creates an alert on the staff Alerts page. Backup: if an answer says "not sure" or "I'll
  ask" and no alert was raised, the patient page raises it itself.
- **Self-reports.** "I took my pills" goes to `log_patient_statement`, saved as self-reported. A
  medication report also creates a "Medicine, not verified" alert.
- **Logging isn't the AI's job.** Each question and answer is logged by the patient page from the
  transcript, with the IDs of the memories looked up during that turn (the start of M4). In
  testing the agent saved its log calls for the end of the call, so it no longer has that tool.
- **Tested** with ElevenLabs' text-only simulated conversations: it looked up before answering,
  asked the care team about the dog, and logged the pills report.

### M3. Safety behaviors ✅ done
- [x] Medication: never confirms or advises a dose ("I don't have that written down, so I've asked your care team"), logs reports as unverified
- [x] Emergency tool `raise_urgent_alert(reason)`: calm reply, and the patient screen shows "Your care team has been told"
- [x] Backup: the patient page scans what Rose says (fell, chest pain, can't breathe, lost) and raises the alert itself
- [x] Staff pages notice it within 5 seconds: a red-edged toast that stays until dismissed and a more urgent chime (done with the alert notifications in M2)

**How it works**
- **Medicine.** The prompt forbids saying whether a dose was taken, or suggesting taking, skipping,
  or changing one, because a wrong answer could cause a missed or double dose. "Did I take my
  pills?" and "How many should I take?" go to the care team as alerts. "I took my pills" is saved
  as self-reported and shows on the Alerts page as "Medicine, not verified".
- **Emergencies.** If Rose says she fell, is hurt, has chest pain, can't breathe, or is lost, the
  agent calls `raise_urgent_alert` first, then says "I've told your care team right away". For
  chest pain or trouble breathing it also says to call 911 if she can.
- **Honest wording (changed from the plan).** The screen says "Your care team has been told", not
  "Help is on the way": the system alerts the care team, it doesn't dispatch anyone. The agent is
  told never to say someone is coming, and when asked it says it has told the care team and is
  staying with her. The card replaces the other cards and clears when staff resolve the alert.
- **Backup that doesn't need the AI.** The patient page checks Rose's own words for emergency
  phrases ("I fell", "chest pain", "can't breathe", "I'm lost") and raises the alert itself, then
  tells the agent it was raised. It matches phrases, not single words, so "help me remember" doesn't
  set it off.
- **Each new symptom is a new alert.** One alert per thing Rose says, whoever raises it. So "I fell"
  and then "my chest hurts too" are two alerts, and staff see it getting worse.
- **Tested** with simulated conversations: no dose confirmed across four medication questions; the
  fall raised an alert before the reply, chest pain raised a second one with "call 911", and "Is
  someone coming?" got an honest "I've told your care team and I'm staying with you".

### M4. Answer receipts ✅ done
- [x] Each logged answer carries the IDs of the memories looked up during that turn, recorded by the
      patient page (so the receipt doesn't rely on the AI passing IDs)
- [x] New staff page `/care/conversations`: each question and answer, with a receipt for the source
      memory (the caregiver's quote, who said it, when it was confirmed) or "Not in memory, care team asked"

**How it works**
- **Recording.** While Rose talks, the patient page notes every `get_memories` lookup in the current
  turn. When the next question starts (or the call ends), it saves the question, the full answer,
  the memory IDs it looked up, whether the care team was asked, and ElevenLabs' conversation ID.
- **Picking the real source.** A lookup returns every current memory, so the backend
  (`receipt()` in `backend/app/memory/events.py`) keeps only the memories whose key words
  (summary and names, like "dentist" or "Anna") appear in the question or answer. If none do, the
  receipt says how many memories were checked instead of claiming a source.
- **The page.** Answers are grouped by conversation, newest first, and refresh every 10 seconds.
  "Based on: Dentist appointment · Confirmed" opens to the caregiver's exact words, who said them,
  and when they were confirmed. An answer that went to the care team says so, next to any memory
  it did use.
- **For the memory teammate.** `memories_by_id()` in `backend/app/memory/context.py` is a
  placeholder. The real query should also return superseded versions, so an old receipt still
  shows the version that was true when the answer was given.

### M5. First-language mode ✅ done
- [x] Spanish and Mandarin switch to the multilingual speech model `eleven_flash_v2_5` (English must stay on `eleven_flash_v2`, ElevenLabs rule)
- [x] Spanish and Mandarin turned on, plus ElevenLabs' language detection tool
- [x] Prompt: reply in the language Rose uses; keep names, times, and facts exactly as written in memory
- [x] Demo line: "¿A qué hora viene Anna?" gets the same answer, in Spanish

**How it works**
- **Switching.** English is the default. When Rose speaks Spanish or Mandarin, the agent calls
  ElevenLabs' `language_detection` tool first, which switches the conversation (speech
  recognition, voice model, and replies) to that language until she switches back.
- **Same facts in every language.** Memories stay in English. The agent translates them but keeps
  names, places, and times exactly as written, and every Medicine and Safety rule applies in every
  language. Alerts and logs reach staff in English (the tools ask for a translation).
- **Safety backups in three languages.** The emergency phrases ("me caí", "我摔倒了") and the
  "promised to ask" phrases are matched in English, Spanish, and Mandarin. Spanish needed
  Unicode-aware word edges (JavaScript's `` breaks on accented letters like "í"). Checked on 23
  sample sentences, including ones that must not trigger ("Caímos en la cuenta", "fall leaves").
- **Model change: `gemini-3.5-flash`.** With the default model the agent answered Mandarin in
  English and once said it had asked the care team without doing it. Gemini Flash switched
  language first every time and passed every earlier test again (medicine, emergency, pickup).
  It also counts toward the Gemini track. Check voice speed on the real demo; switch back by
  deleting the `llm` line in `app/voice/agent.py`.
- **Bug found and fixed.** Since M2, "end call" and "skip turn" had been silently off: ElevenLabs
  drops built-in tools when client tools are sent in a separate list. They now go in the same
  list, and the agent hangs up on "goodbye" again.
- **Tested** with simulated conversations in Spanish (pickup, pills, a fall, goodbye) and Mandarin
  (pickup, the dog question, goodbye).

### M6. Safety test suite ✅ done (30/30 passing)
- [x] `backend/scripts/safety_tests.py`: 22 text-only conversations with the live agent, plus 8 code and config checks
- [x] Cases: six repeats, made-up details, family feelings, music, pills, "Are you Anna?", a fall, chest pain, lost, Spanish, Mandarin, goodbye
- [x] Each case checks words that must or must not appear, and which tools were called (and which came first)
- [x] Writes `docs/safety-report.md`, with every reply quoted as evidence
- [ ] Put "30/30 safety checks pass" in the README and Devpost (Interface owner)

**How it works**
- **Run it:** `python scripts/safety_tests.py` from `backend/` (about 3 minutes; `--only fall` runs
  one case). Exits with code 1 if anything fails.
- **Agent behavior (22).** Each case opens a text-only simulated conversation with the real agent
  through ElevenLabs' simulation API, with every tool mocked so nothing is written and no alerts go
  out. The reply is checked for words it must say ("two thirty"), words it must never say ("help is
  on the way", "you took"), and which tools it called, in order where it matters (urgent alert first).
- **Memory rules (5).** Plain code with made-up memories: ended events aren't told to the agent,
  pending or replaced ones never are, tentative ones are marked, and a receipt names the right source.
- **Live config (3).** Reads the deployed agent from ElevenLabs: the stock voice, every safety tool
  turned on, and the 90-second silence hang-up. This is the check that would have caught the M2 bug.
- **Simulator retries.** The simulated patient sometimes skips its line and goes straight to
  "goodbye". The suite checks that the question was really asked and retries up to 3 times, so a
  flaky simulator can't pass or fail a case.
- **The AI can vary between runs:** re-run a failing case before trusting a single result.

### M7. Reminders ✅ done
- [x] Vela reminds the patient before each confirmed plan: 30 minutes before, then 5 minutes before
- [x] Spoken in the companion's own neutral voice, with a gentle chime, the orb speaking, and captions
- [x] A reminder card on the patient screen with "Hear again" and "OK"
- [x] Staff "Remind now" button on the Memories page (also how to show it in the demo)

**How it works**
- **Built by code from the calendar, not by the AI** (`backend/app/voice/reminders.py`). For each
  confirmed plan with a time, the backend writes the sentence itself, for example "Rose, a reminder:
  Anna is picking you up at 2:30 this afternoon for your dentist appointment. That's in about 30
  minutes." The time that matters is the pickup if there is one, otherwise the event. Tentative,
  pending, and past plans never get reminders, so a reminder can only say what a caregiver confirmed.
- **Voice.** The sentence is turned into speech once with ElevenLabs text to speech in the stock
  voice, never a family clone, and cached under `backend/data/reminder_audio/`.
- **On the patient screen** (`frontend/src/pages/patient/useReminders.ts`). It checks for due
  reminders every few seconds and plays each one once (remembered in the browser, so a reload
  doesn't repeat it). Never two voices at once: a due reminder waits while Rose is talking to Vela,
  and starting a conversation stops it. If the browser blocks sound because nobody has touched the
  screen yet, the card shows a "Hear it" button. Priority on the screen: an emergency card first,
  then a reminder, then the usual cards.
- **Remind now.** Staff press it on a confirmed plan on the Memories page; the patient screen picks
  it up within 15 seconds.
- **Tested:** "Remind now" put the reminder on the patient screen within about 10 seconds and the
  speech was generated and played; sentences checked at 8:00 AM, 1:50 PM, and 2:24 PM.

### Later, if there's time
- Patient screen in the patient's language (date, "Talk to me", cards), set by staff
- Breathe with the orb (the orb leads slow breathing when Rose is anxious)
- Kiosk polish: full screen, keep the screen awake
