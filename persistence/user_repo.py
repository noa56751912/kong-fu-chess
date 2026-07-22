import hashlib
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from typing import Optional

# Deliberately stdlib-only (hashlib.pbkdf2_hmac), not bcrypt/argon2 - avoids a
# new dependency for a course-scale user base, while still being a real
# salted, iterated hash rather than a plain/reversible one.
PBKDF2_ITERATIONS = 200_000
DEFAULT_RATING = 1200


@dataclass(frozen=True)
class User:
    username: str
    elo_rating: int


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS).hex()


class UserRepo:
    """Plain synchronous SQLite access - callers on the asyncio server side
    are expected to offload calls via asyncio.to_thread so a (fast, but
    still blocking) disk write never stalls the event loop. Different
    to_thread calls can land on different worker threads, so this connection
    is opened with check_same_thread=False (see persistence/db.py) and every
    access here is serialized through its own lock - real thread-safety,
    not a reliance on the underlying SQLite build's threading mode."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = threading.Lock()

    def get_user(self, username: str) -> Optional[User]:
        with self._lock:
            row = self._conn.execute(
                "SELECT username, elo_rating FROM users WHERE username = ?", (username,)
            ).fetchone()
        return User(row[0], row[1]) if row is not None else None

    def create_user(self, username: str, password: str) -> User:
        """Raises sqlite3.IntegrityError if the username already exists -
        callers racing to register the same new username must handle that
        by falling back to verify_password instead."""
        salt = secrets.token_bytes(16)
        password_hash = _hash_password(password, salt)
        with self._lock:
            self._conn.execute(
                "INSERT INTO users (username, password_hash, password_salt, elo_rating) VALUES (?, ?, ?, ?)",
                (username, password_hash, salt.hex(), DEFAULT_RATING),
            )
            self._conn.commit()
        return User(username, DEFAULT_RATING)

    def verify_password(self, username: str, password: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT password_hash, password_salt FROM users WHERE username = ?", (username,)
            ).fetchone()
        if row is None:
            return False
        stored_hash, salt_hex = row
        candidate = _hash_password(password, bytes.fromhex(salt_hex))
        return secrets.compare_digest(candidate, stored_hash)

    def update_rating(self, username: str, new_rating: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET elo_rating = ? WHERE username = ?", (new_rating, username)
            )
            self._conn.commit()
