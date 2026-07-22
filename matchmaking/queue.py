import time
from dataclasses import dataclass
from typing import Optional

RATING_RANGE = 100
TIMEOUT_S = 60


@dataclass
class Waiting:
    context: object   # a ws_server.ConnectionContext - opaque to this module
    rating: int
    joined_at: float


class MatchmakingQueue:
    """Pure, synchronous, framework-agnostic matchmaking data structure - no
    asyncio/websockets here at all, so it's trivial to unit test. The async
    server periodically calls find_match()/expire() and acts on the result;
    this class only ever mutates its own waiting list."""

    def __init__(self):
        self._waiting: list[Waiting] = []

    def add(self, context, rating: int, now: Optional[float] = None) -> None:
        self._waiting.append(Waiting(context, rating, now if now is not None else time.monotonic()))

    def remove_connection(self, connection) -> None:
        self._waiting = [w for w in self._waiting if w.context.connection is not connection]

    def __len__(self) -> int:
        return len(self._waiting)

    def find_match(self) -> Optional[tuple[Waiting, Waiting]]:
        """Returns and removes the first pair within RATING_RANGE of each
        other (FIFO over the waiting list, not necessarily the closest
        possible pairing), or None if no such pair exists yet."""
        for i, a in enumerate(self._waiting):
            for b in self._waiting[i + 1:]:
                if abs(a.rating - b.rating) <= RATING_RANGE:
                    self._waiting.remove(a)
                    self._waiting.remove(b)
                    return a, b
        return None

    def expire(self, now: Optional[float] = None) -> list[Waiting]:
        """Returns and removes every entry that has waited >= TIMEOUT_S."""
        now = now if now is not None else time.monotonic()
        expired = [w for w in self._waiting if now - w.joined_at >= TIMEOUT_S]
        for w in expired:
            self._waiting.remove(w)
        return expired
