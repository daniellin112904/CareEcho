# Vela

A voice health companion that keeps watch. It answers questions calmly and correctly, using only what a caregiver has confirmed. The first use case is people living with dementia, who ask the same questions many times a day.

The name comes from the Spanish *velar*: to keep watch over someone, especially through the night.

Built at Hack Knight Fall 2026.

## Structure

- `backend/`: FastAPI API (memories, extraction, alerts, family messages)
- `frontend/`: React app with the patient screen (`/patient`) and the PIN-protected staff pages (`/care`)
- `docs/`: pitch, architecture, Devpost drafts

## Running locally

First-time setup (copy `backend/.env.example` to `backend/.env` and fill it in first):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python scripts\create_agent.py   # first time only, then add ELEVENLABS_AGENT_ID to .env
cd ..
npm run install:all
```

Then start both servers from the repo root:

```powershell
npm run dev
```

Open http://localhost:5173/patient for the patient screen and http://localhost:5173/care for staff
(PIN is `STAFF_PIN` in `backend/.env`). Backend API is on http://localhost:8000.

To run only one side: `npm run dev:frontend` or `npm run dev:backend`.