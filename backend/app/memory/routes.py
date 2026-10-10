from fastapi import APIRouter

router = APIRouter(tags=["memory"])

# Mock data until the real Tiger Data queries replace it
MOCK_MEMORIES = [
    {
        "id": "mock-1",
        "kind": "appointment",
        "summary": "Dentist appointment",
        "details": {"who": "Anna", "pickup_at": "2026-10-10T14:30:00-04:00"},
        "event_at": "2026-10-10T15:00:00-04:00",
        "status": "confirmed",
        "source": "caregiver_session",
        "source_quote": "Your dentist appointment is tomorrow at three. Anna will pick you up at two thirty.",
        "confirmed_at": "2026-10-09T18:12:00-04:00",
    }
]


@router.get("/memories/current")
def current_memories(topic: str | None = None):
    return {"memories": MOCK_MEMORIES}