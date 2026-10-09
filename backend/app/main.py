from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.memory.routes import router as memory_router
from app.voice.routes import router as voice_router

app = FastAPI(title="CareEcho API")

# Lets the React dev server (port 5173) call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memory_router)
app.include_router(voice_router)


@app.get("/health")
def health():
    return {"status": "ok"}