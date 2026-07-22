import sqlite3
from pathlib import Path
from typing import Optional, Union

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "kong_fu_chess.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    elo_rating INTEGER NOT NULL DEFAULT 1200,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Opens (creating if needed) the SQLite database and ensures the schema
    exists. `:memory:` is accepted for tests - a fresh in-memory database per
    connection, no file created."""
    path = db_path if db_path is not None else DEFAULT_DB_PATH
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: the async server accesses this connection via
    # asyncio.to_thread, which can run different calls on different worker
    # threads. UserRepo pairs this with its own lock for real serialization,
    # rather than relying on the sqlite3 build's threading mode to save us.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
