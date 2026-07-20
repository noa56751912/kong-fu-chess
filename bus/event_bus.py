from collections import defaultdict
from typing import Callable


class EventBus:
    """Synchronous pub/sub: publishing a topic calls every subscriber immediately.

    Both the engine (single-threaded per tick) and the asyncio server (single-threaded
    per event-loop iteration) only ever publish from one place at a time, so there is
    no need for queueing or thread-safety here.
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable[[dict], None]]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None:
        self._subscribers[topic].append(handler)

    def publish(self, topic: str, payload: dict) -> None:
        for handler in self._subscribers[topic]:
            handler(payload)
