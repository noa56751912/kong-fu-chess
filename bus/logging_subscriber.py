import logging

from bus.event_bus import EventBus
from net.bus_bridge import BRIDGED_TOPICS

logger = logging.getLogger("bus")


def attach_logging(bus: EventBus, label: str = "") -> None:
    """Subscribes a structured log line to every bus topic a GameSession
    forwards over the network (net/bus_bridge.py's BRIDGED_TOPICS - the same
    list, so this and the network layer never drift out of sync about what
    "every bus topic" means)."""
    for topic in BRIDGED_TOPICS:
        bus.subscribe(topic, _make_handler(topic, label))


def _make_handler(topic: str, label: str):
    def handler(payload: dict) -> None:
        if label:
            logger.info("[%s] %s %s", label, topic, payload)
        else:
            logger.info("%s %s", topic, payload)
    return handler
