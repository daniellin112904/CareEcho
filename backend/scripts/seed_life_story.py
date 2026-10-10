"""Loads the demo patient's life story into Snowflake from backend/app/memory/life_story_demo.json.

Run from backend/:  python scripts/seed_life_story.py            (the demo file)
                    python scripts/seed_life_story.py other.json (another file, same format)

The file is a list of passages, written following "How to write the life story" in
docs/memory-track.md:

    [{"section": "Career", "topic": "work", "passage": "Rose taught third grade in Flushing for 31 years.",
      "people": "", "said_by": "Anna, daughter", "sensitive": false}, ...]

("section" is optional and only for people reading the file: it isn't loaded.)

Every passage is checked first; if any is wrong, nothing is loaded. Then the demo patient's
passages become exactly these (the old ones are removed). They're searchable by the agent within
about a minute. This isn't part of POST /demo/reset, so a reset never depends on Snowflake.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from pydantic import ValidationError

from app.memory import life_story
from app.store import PATIENT_ID

DEMO_FILE = Path(__file__).parent.parent / "app" / "memory" / "life_story_demo.json"

path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEMO_FILE
if not path.exists():
    sys.exit(f"{path} doesn't exist yet. Write it following \"How to write the life story\" in docs/memory-track.md.")
if not life_story.enabled():
    sys.exit("Snowflake isn't set up: fill the SNOWFLAKE_* settings in backend/.env (see scripts/snowflake_setup.sql).")

try:
    entries = json.loads(path.read_text(encoding="utf-8"))
except json.JSONDecodeError as err:
    sys.exit(f"{path.name} isn't valid JSON: {err}")
if not isinstance(entries, list):
    sys.exit(f"{path.name} must be a list of passages.")

passages, problems = [], []
for number, entry in enumerate(entries, start=1):
    try:
        passages.append(life_story.Passage.model_validate(entry))
    except ValidationError as err:
        problems += [f"  passage {number}, {'.'.join(map(str, e['loc'])) or 'entry'}: {e['msg']}" for e in err.errors()]
if problems:
    sys.exit("Nothing was loaded. Fix these first:\n" + "\n".join(problems))

try:
    count = life_story.replace_passages(PATIENT_ID, passages)
except life_story.LifeStoryError as err:
    sys.exit(f"Snowflake: {err}")
print(f"Loaded {count} passages for the demo patient ({PATIENT_ID}) from {path.name}.")
print("They're searchable by the agent within about a minute.")
