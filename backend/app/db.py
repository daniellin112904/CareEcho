"""The Tiger Data (Postgres) connection pool, shared by the app and the scripts.

Without DATABASE_URL there's no pool, and app/store.py serves the demo memories from
app/memory/demo.py instead: a demo that still runs when the database can't be reached.
The switch is only this setting, never automatic, so the agent can't quietly change
from real memories to sample ones in the middle of a demo.
"""

import atexit
import os
import threading

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def enabled() -> bool:
    return bool(os.getenv("DATABASE_URL"))


def pool() -> ConnectionPool:
    """Opened on first use, so importing the app (or a script) never connects by itself.

    Use as `with db.pool().connection() as conn:`. The block is one transaction: it commits
    at the end, or rolls back if anything inside raises.
    """
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                _pool = ConnectionPool(
                    os.environ["DATABASE_URL"],
                    min_size=1,
                    max_size=5,
                    # Under the agent's 5 second tool timeout, so a slow database turns into
                    # "not sure" (LOOKUP_FAILED in agentTools.ts) rather than a hung tool call
                    timeout=3,
                    kwargs={"row_factory": dict_row, "connect_timeout": 3},
                    # Cloud databases drop idle connections; test each one before handing it out
                    check=ConnectionPool.check_connection,
                    open=True,
                )
                # Close before the interpreter shuts down: the pool's worker threads can't be
                # joined later than that, and a script would end with a traceback
                atexit.register(_pool.close)
    return _pool
