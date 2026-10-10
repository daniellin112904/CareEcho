"""Creates the Vela agent on ElevenLabs, or re-applies app/voice/agent.py to it.

Run from backend/:  python scripts/create_agent.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

from app.voice.agent import AGENT_CONFIG, PLATFORM_SETTINGS, TTS_CONFIG

AGENT_NAME = "Vela"

load_dotenv()
client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
agent_id = os.getenv("ELEVENLABS_AGENT_ID")

if agent_id:
    # Re-applies the stock voice too: the live companion never uses a cloned voice
    client.conversational_ai.agents.update(
        agent_id,
        name=AGENT_NAME,
        conversation_config={**AGENT_CONFIG, "tts": TTS_CONFIG},
        platform_settings=PLATFORM_SETTINGS,
    )
    print(f"Updated agent {agent_id}")
else:
    agent = client.conversational_ai.agents.create(
        name=AGENT_NAME,
        conversation_config={**AGENT_CONFIG, "tts": TTS_CONFIG},
        platform_settings=PLATFORM_SETTINGS,
    )
    print(f"Created agent. Add this line to backend/.env:\nELEVENLABS_AGENT_ID={agent.agent_id}")
