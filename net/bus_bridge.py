from typing import Callable

from bus.event_bus import EventBus
from net.protocol import EVENT, encode, positions_to_squares

# Every bus topic a network client needs to know about to keep its local
# board mirror in sync - see bus/event_bus.py's publish call sites in
# realtime/real_time_arbiter.py. Deliberately NOT a periodic full-board
# push: each of these fires once, the instant it happens server-side.
BRIDGED_TOPICS = [
    'move.started', 'move.arrived',
    'jump.started', 'jump.landed',
    'piece.captured', 'piece.state_changed',
    'score.changed', 'game.over',
    'player.joined',
]


class BusBridge:
    """Subscribes to every game-relevant bus topic and forwards each as a
    small EVENT message to a session's connected clients, the instant it's
    published."""

    def __init__(self, bus: EventBus, rows: int, broadcast_nowait: Callable[[str], None]):
        self._rows = rows
        self._broadcast_nowait = broadcast_nowait
        for topic in BRIDGED_TOPICS:
            bus.subscribe(topic, self._make_handler(topic))

    def _make_handler(self, topic: str) -> Callable[[dict], None]:
        def handler(payload: dict) -> None:
            safe_payload = positions_to_squares(payload, self._rows)
            self._broadcast_nowait(encode({"type": EVENT, "topic": topic, "payload": safe_payload}))
        return handler
