import logging

from bus.event_bus import EventBus
from bus.logging_subscriber import attach_logging


class TestAttachLogging:

    def test_bridged_topic_is_logged(self, caplog):
        bus = EventBus()
        with caplog.at_level(logging.INFO, logger="bus"):
            attach_logging(bus)
            bus.publish("move.started", {"piece_id": 1})
        assert "move.started" in caplog.text

    def test_unrelated_topic_is_not_logged(self, caplog):
        bus = EventBus()
        with caplog.at_level(logging.INFO, logger="bus"):
            attach_logging(bus)
            bus.publish("not.a.bridged.topic", {})
        assert caplog.text == ""

    def test_label_is_included_when_given(self, caplog):
        bus = EventBus()
        with caplog.at_level(logging.INFO, logger="bus"):
            attach_logging(bus, label="room-abc123")
            bus.publish("game.over", {"winner": "w"})
        assert "room-abc123" in caplog.text
