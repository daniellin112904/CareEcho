import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

schema_path = Path(__file__).parent.parent / "app" / "memory" / "schema.sql"
lines = schema_path.read_text().splitlines()
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