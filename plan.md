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

## How it works

```
Patient taps orb -> backend gives a one-time token + today's facts -> ElevenLabs agent talks
Staff writes message -> backend speaks it in the family voice (ElevenLabs) -> patient taps Play
```

## Still mock data

Memories and alerts are placeholders until the memory system lands. Once
`GET /memories/current` returns real data, the agent and the patient screen pick it up
automatically.

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

### M2. Live memory tools (about 2.5 h)
- [ ] Add client tools to `app/voice/agent.py`: `get_memories(topic)`, `ask_caregiver(question)`,
      `log_patient_statement(text, kind)`, `log_interaction(topic, question, answer)`
- [ ] Handle them in `frontend/src/voice/agentTools.ts`, passed as `clientTools` in `startSession`
- [ ] `get_memories` returns short spoken sentences, or `NO_MEMORY` so the agent says it isn't sure
- [ ] Prompt: always call `get_memories` before answering about plans; log after each answer
- [ ] Endpoints *(Memory)*: `POST /alerts`, `POST /interactions`, `POST /patient/statements`

### M3. Safety behaviors (about 1.5 h)
- [ ] Medication: never confirm a dose ("I don't have that written down, I'll ask Anna"), log it as unverified
- [ ] Emergency tool `raise_urgent_alert(reason)`: calm reply, and the patient screen shows "Help is on the way"
- [ ] Backup: the patient page scans what Rose says (fell, chest pain, can't breathe, lost) and raises the alert itself
- [ ] Staff pages: a red urgent banner, checked every 5 seconds

### M4. Answer receipts (about 1.5 h)
- [ ] The tool handler remembers which memory IDs the last `get_memories` returned and attaches them to
      `log_interaction` (so the receipt doesn't rely on the AI passing IDs)
- [ ] New staff page `/care/conversations`: each question and answer, with a chip for the source
      memory (the caregiver's quote, who confirmed it, when) or "Not in memory, caregiver asked"

### M5. First-language mode (about 1 h)
- [ ] Switch the agent's speech model to `eleven_flash_v2_5` (`eleven_flash_v2` is English only)
- [ ] Turn on Spanish and Mandarin, plus ElevenLabs' language detection tool
- [ ] Prompt: reply in the language Rose uses; keep names, times, and facts exactly as written in memory
- [ ] Demo line: "¿A qué hora viene Anna?" gets the same answer, in Spanish

### M6. Safety test suite (about 2 h, off the demo path)
- [ ] `backend/scripts/safety_tests.py`: 20 text-only conversations with the agent (check the
      ElevenLabs simulate-conversation API first)
- [ ] Cases: 6 repeats, made-up facts, "Did I take my pills?", "Are you Anna?", a fall, a past event, Spanish
- [ ] Each case checks words that must or must not appear, and which tools were called
- [ ] Writes `docs/safety-report.md`; the pass count goes in the README and Devpost

### Later, if there's time
- Breathe with the orb (the orb leads slow breathing when Rose is anxious)
- Staff pages restyled to match the patient screen
- Kiosk polish: full screen, keep the screen awake
