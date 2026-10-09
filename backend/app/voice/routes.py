from fastapi import APIRouter

router = APIRouter(tags=["voice"])


@router.post("/family-message")
def family_message():
    return {"status": "not implemented yet"}