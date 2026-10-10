import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

schema_dir = Path(__file__).parent.parent / "app" / "memory"
# schema.sql first: schema_voice.sql (the voice features' tables) adds to its tables
lines = [line for name in ("schema.sql", "schema_voice.sql") for line in (schema_dir / name).read_text().splitlines()]
schema = "\n".join(line for line in lines if not line.strip().startswith("--"))
statements = [s.strip() for s in schema.split(";") if s.strip()]

# autocommit is required: TimescaleDB can't create a continuous aggregate inside a transaction
with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
    for stmt in statements:
        conn.execute(stmt)
        print("ok:", stmt.splitlines()[0][:70])

    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name"
    ).fetchall()
    print("Tables:", [r[0] for r in rows])