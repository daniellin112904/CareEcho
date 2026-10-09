import os

import httpx
from dotenv import load_dotenv

load_dotenv()


def check_gemini():
    from google import genai

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    reply = client.models.generate_content(
        model="gemini-flash-latest",
        contents="Reply with the single word: ready",
    )
    print("Gemini:", reply.text.strip())


def check_elevenlabs():
    res = httpx.get(
        "https://api.elevenlabs.io/v1/user",
        headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY", "")},
    )
    if res.status_code == 200:
        print("ElevenLabs: ok")
    else:
        print(f"ElevenLabs: failed ({res.status_code}) {res.text[:200]}")


for check in (check_gemini, check_elevenlabs):
    try:
        check()
    except Exception as e:
        print(f"{check.__name__} failed: {e}")