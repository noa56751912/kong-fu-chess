from bus.event_bus import EventBus


class TestPublishSubscribe:

    def test_subscriber_receives_published_payload(self):
        bus = EventBus()
        received = []
        bus.subscribe("move.arrived", received.append)
        bus.publish("move.arrived", {"piece_id": 1})
        assert received == [{"piece_id": 1}]

    def test_multiple_subscribers_all_receive_the_event(self):
        bus = EventBus()
        first, second = [], []
        bus.subscribe("score.changed", first.append)
        bus.subscribe("score.changed", second.append)
        bus.publish("score.changed", {"color": "w", "score": 3})
        assert first == [{"color": "w", "score": 3}]
        assert second == [{"color": "w", "score": 3}]

    def test_subscriber_only_receives_its_own_topic(self):
        bus = EventBus()
        received = []
        bus.subscribe("move.arrived", received.append)
        bus.publish("jump.landed", {"piece_id": 2})
        assert received == []

    def test_publish_with_no_subscribers_does_not_raise(self):
        bus = EventBus()
        bus.publish("game.over", {"winner": "w"})
