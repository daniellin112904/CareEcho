from dotenv import load_dotenv

load_dotenv()

from elevenlabs.core import ApiError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import router as staff_router
from app.memory.routes import router as memory_router
from app.voice.routes import router as voice_router
from app.voice.routes import staff_router as voice_staff_router

app = FastAPI(title="Vela API")

# Lets the React dev server (port 5173) call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(staff_router)
app.include_router(memory_router)
app.include_router(voice_router)
app.include_router(voice_staff_router)


@app.exception_handler(ApiError)
def elevenlabs_error(request: Request, exc: ApiError):
    body = exc.body if isinstance(exc.body, dict) else {}
    detail = body.get("detail")
    message = detail.get("message") if isinstance(detail, dict) else detail
    return JSONResponse(status_code=502, content={"detail": f"ElevenLabs: {message or exc.body}"})


@app.get("/health")
def health():
    return {"status": "ok"}
