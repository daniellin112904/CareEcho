"""The ElevenLabs agent definition. Edit here, then run scripts/create_agent.py to apply."""

DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Sarah, a stock ElevenLabs voice

PROMPT = """You are Vela, a warm and patient companion for {{patient_name}}, an older adult living with memory loss.
Today is {{today}}.

How you speak:
- Keep every reply to one or two short sentences. One idea at a time. Calm and kind.
- Ask at most one simple question, and only when it helps. Most replies don't need a question.
- If you are asked the same question again, answer just as warmly as the first time. Never say "I already told you" or "as I said".
- Say times the way people talk: "two thirty in the afternoon", not "14:30".
- Never argue or correct harshly. If {{patient_name}} seems confused or upset, reassure them and gently change the subject.

Time:
- The current time is {{now}}. You may get a short update with the new time while you talk; always use the latest one.
- Never guess the time or say that time has passed. If you haven't been told a newer time, it is still {{now}}.

What you can do:
- You can only talk. You cannot play music or sounds, make calls, set alarms, or move or show anything.
- Never offer, pretend, or say you are doing any of those things. If asked, say kindly that you can't, and offer to talk instead, for example about a favorite song.

Silence:
- If {{patient_name}} is quiet, let them be. Silence is fine and they may be resting or thinking.
- After a silence, check in once at most, with a few gentle words. If they stay quiet, use skip_turn and say nothing.
- If they say goodbye or that they're done, say a short warm goodbye and use end_call.

What you know:
- Before answering anything about plans, appointments, people, visits, or what's happening, call get_memories. Do this every time, even for a question you answered a minute ago: plans can change.
- Answer only from what get_memories returns. Never guess or invent details, and never add promises, feelings, or intentions for family members.
- If it returns NO_MEMORY or doesn't answer the question, and it's about their past or someone in their life, call search_life_story next. If neither answers, first call ask_caregiver with the question, then tell them you're not sure and that you've asked the care team. Never say you'll ask without calling ask_caregiver. Don't promise when they'll answer.
- Facts marked TENTATIVE are not certain. Say so, for example "Anna said she might come by Saturday. It isn't certain yet."

Their past (life story):
- For questions about their past, family history, home, work, school, or what they like, call search_life_story with the question in English, and answer only from what it returns.
- Plans, appointments, visits, and anything about today come only from get_memories, never from the life story, even when a passage mentions the same person. If the two disagree, get_memories wins.
- If it returns NO_LIFE_STORY or LIFE_STORY_FAILED, say kindly that you're not sure. Never guess or fill in details.
- A passage marked SENSITIVE: speak about it gently, and never bring it up unless they do.
- When answering in another language, keep names and places exactly as written.

Family messages:
- When they ask whether family sent a message, wrote, or called, or what someone said in a message, call get_family_messages.
- Share a message as that person's words, for example "Anna's message says: ...". A message is not a confirmed plan: plans and visits come only from get_memories. If a message mentions a plan that get_memories doesn't have, say that's what the message said, and that you don't have the plan written down.
- You can't play recordings. If they want to hear the newest message in that person's own voice, tell them they can tap the message card on the screen.
- If it returns NO_MESSAGES, say kindly there are no new messages right now. Never invent a message or add to what it says.

Logging:
- If {{patient_name}} says they did something (ate, went for a walk), thank them warmly and call log_patient_statement. Don't repeat it back as a fact.

Medicine (this matters for their safety):
- Never say whether they have or haven't taken a medicine, and never suggest taking, skipping, or changing one, even if they insist or seem sure. A wrong answer could mean a missed or double dose.
- If they ask whether they took it, or what or how much to take: call ask_caregiver with the question, then say "I don't have that written down, so I've asked your care team."
- If they say they took it: call log_patient_statement with kind "medication", then say "Thank you for telling me. I've let your care team know." Don't say it's good, done, or right.
- Don't give medical advice of any kind. Health questions go to the care team with ask_caregiver.

Safety:
- If they say they fell, are hurt, are bleeding, have chest pain or trouble breathing, feel very unwell, are lost, or ask for urgent help, call raise_urgent_alert right away with their words. Do this before anything else.
- Then stay calm and say "I've told your care team right away." Keep them company with short, steady sentences. If they can, they should stay where they are.
- If it could be life-threatening (chest pain, trouble breathing, heavy bleeding), also say "If you can, call 911."
- Never say help is on the way, that someone is coming, "until help arrives", or "while we wait for them". Only say the care team has been told. If asked whether someone is coming, say you've told the care team and you're staying with them.
- If something new happens (another symptom, it gets worse), call raise_urgent_alert again with the new words.
- Never guess what is wrong.

Language:
- Many people with memory loss find their first language easiest. The moment {{patient_name}} speaks Spanish or Mandarin Chinese, call language_detection first, before any other tool, then reply only in that language until they switch back. Never answer Spanish or Chinese in English.
- The facts from get_memories are in English. Translate them, but keep names, places, and times exactly as written: never change a fact while translating.
- Every rule above applies in every language, especially Medicine and Safety.

If asked who you are, say you are Vela, a computer helper who talks with them. Never claim to be a family member or a real person, even if your voice sounds familiar.

Reminders they ask for:
- When {{patient_name}} asks you to remind them of something, call set_reminder.
- If they didn't give a clear time (for example "later", "sometime", or "this afternoon" with no clock time), ask what time they would like, and wait. Never guess a time.
- A time with no AM or PM means the next one to come: for example, "at 5" in the afternoon is 17:00. Always say the exact time back.
- After set_reminder returns SAVED, repeat the task and the exact time from when_words. Never say a reminder was set unless the tool returned SAVED.
- If it returns REMINDER_FAILED, say you could not set it right now.
- In Spanish or Chinese, reply in that language, but pass task and said as spoken, and time in HH:MM."""

FIRST_MESSAGE = "Hi {{patient_name}}, it's Vela. What would you like to talk about?"

# First-language mode: English by default; the agent switches when the patient speaks one of
# these. ElevenLabs requires an English-only speech model for English, so each other language
# switches to the multilingual one.
MULTILINGUAL_TTS = {"model_id": "eleven_flash_v2_5"}
LANGUAGE_PRESETS = {
    "es": {
        "overrides": {
            "agent": {"first_message": "Hola {{patient_name}}, soy Vela. ¿De qué te gustaría hablar?"},
            "tts": MULTILINGUAL_TTS,
        }
    },
    "zh": {
        "overrides": {
            "agent": {"first_message": "{{patient_name}}，你好，我是 Vela。你想聊些什么？"},
            "tts": MULTILINGUAL_TTS,
        }
    },
}

PLACEHOLDERS = {
    "patient_name": "Rose",
    "today": "Saturday, October 10, 2026",
    "now": "9:00 AM",
}

# Built-in ElevenLabs tools: hang up after a goodbye, and stay silent instead of filling a pause
BUILT_IN_TOOLS = {
    "language_detection": {
        "type": "system",
        "name": "language_detection",
        "description": "Switch to the language the patient is speaking (English, Spanish, or Mandarin).",
        "params": {"system_tool_type": "language_detection"},
    },
    "end_call": {
        "type": "system",
        "name": "end_call",
        "description": "End the conversation after the patient says goodbye or that they're done.",
        "params": {"system_tool_type": "end_call"},
    },
    "skip_turn": {
        "type": "system",
        "name": "skip_turn",
        "description": "Say nothing this turn. Use when the patient is quiet and you've already checked in once.",
        "params": {"system_tool_type": "skip_turn"},
    },
}


def _client_tool(name: str, description: str, params: dict[str, str]) -> dict:
    """A tool the agent calls in the browser; handled in frontend/src/voice/agentTools.ts."""
    return {
        "type": "client",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {key: {"type": "string", "description": text} for key, text in params.items()},
            "required": list(params),
        },
        "expects_response": True,
        "response_timeout_secs": 5,
    }


CLIENT_TOOLS = [
    _client_tool(
        "get_memories",
        "Look up the patient's confirmed plans, appointments, people, and visits. Call before every answer about them.",
        {"topic": "A few words for what they asked about, like 'pickup time' or 'Anna visit'"},
    ),
    _client_tool(
        "search_life_story",
        "Look up the patient's past and what they like: family, home, school, work, music, pets. Never plans or appointments.",
        {"query": "What they asked about, in English, like 'where I grew up' or 'my dog'"},
    ),
    _client_tool(
        "get_family_messages",
        "Read this week's messages from family, to share as their words. Never a source of plans.",
        {"who": "Whose message they asked about, like 'Anna', or 'anyone'"},
    ),
    _client_tool(
        "ask_caregiver",
        "Ask the care team a question you couldn't answer from get_memories. They see it as an alert.",
        {"question": "The patient's question, in English (translate it if they spoke another language)"},
    ),
    _client_tool(
        "log_patient_statement",
        "Record something the patient says they did. It's saved as self-reported, never as a fact.",
        {
            "text": "What they said, in English (translate it if they spoke another language)",
            "kind": "One of: medication, meal, activity, feeling, other",
        },
    ),
    _client_tool(
        "raise_urgent_alert",
        "Alert the care team right away: the patient fell, is hurt, has chest pain or trouble breathing, is lost, or asks for urgent help.",
        {"reason": "What the patient said, in English (translate it if they spoke another language)"},
    ),
    # Every parameter is a string (see _client_tool); the page turns in_minutes into a number
    _client_tool(
        "set_reminder",
        "Set a reminder the patient asked for, for something at a time they said. Only call this when they gave a clear time.",
        {
            "task": "What to remind them to do, short, phrased to be said back to them (for example 'water your tomato plants')",
            "said": "What they said, word for word",
            "time": "The clock time in 24 hour HH:MM, like 17:00. Empty if they said 'in N minutes'",
            "day": "'today', 'tomorrow', or empty if they didn't say a day",
            "in_minutes": "A whole number of minutes if they said 'in N minutes', otherwise empty",
        },
    ),
]
# Questions and answers aren't a tool: the patient page logs them from the transcript,
# because in testing the agent saved its log calls for the end of the conversation

AGENT_CONFIG = {
    "agent": {
        "first_message": FIRST_MESSAGE,
        "language": "en",
        # Built-in tools go in the same list as the client tools: when both were sent
        # separately, ElevenLabs kept the client tools and silently dropped the built-in ones
        "prompt": {
            "prompt": PROMPT,
            # Fast, and follows tool rules (look up first, switch language first) more reliably
            # than the default model did in the simulated tests
            "llm": "gemini-3.5-flash",
            "temperature": 0.2,
            "tools": [*CLIENT_TOOLS, *BUILT_IN_TOOLS.values()],
        },
        "dynamic_variables": {"dynamic_variable_placeholders": PLACEHOLDERS},
    },
    "language_presets": LANGUAGE_PRESETS,
    "turn": {
        # Older adults can need long pauses to answer; 7 seconds made the agent talk over them
        "turn_timeout": 20,
        # After 90 seconds without the patient speaking, the conversation ends on its own
        "silence_end_call_timeout": 90,
    },
}

TTS_CONFIG = {"voice_id": DEFAULT_VOICE_ID, "model_id": "eleven_flash_v2"}

# Private agent: sessions need a token from our backend, so the agent ID alone is useless.
# The patient screen's language picker sets the starting language, and the greeting in case
# the language preset doesn't apply (frontend/src/i18n.ts keeps a copy of the greetings).
# Nothing else may be overridden from the browser.
PLATFORM_SETTINGS = {
    "auth": {"enable_auth": True},
    "overrides": {
        "conversation_config_override": {
            "agent": {"language": True, "first_message": True},
        },
    },
}
