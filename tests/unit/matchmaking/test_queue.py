from dataclasses import dataclass

from matchmaking.queue import MatchmakingQueue


@dataclass
class FakeConnection:
    name: str


@dataclass
class FakeContext:
    connection: FakeConnection


def ctx(name):
    return FakeContext(FakeConnection(name))


class TestFindMatch:

    def test_no_match_when_queue_has_fewer_than_two(self):
        q = MatchmakingQueue()
        q.add(ctx("alice"), 1200)
        assert q.find_match() is None

    def test_matches_two_players_within_range(self):
        q = MatchmakingQueue()
        q.add(ctx("alice"), 1200)
        q.add(ctx("bob"), 1250)
        pair = q.find_match()
        assert pair is not None
        a, b = pair
        assert {a.context.connection.name, b.context.connection.name} == {"alice", "bob"}

    def test_matched_pair_is_removed_from_the_queue(self):
        q = MatchmakingQueue()
        q.add(ctx("alice"), 1200)
        q.add(ctx("bob"), 1250)
        q.find_match()
        assert len(q) == 0

    def test_no_match_outside_rating_range(self):
        q = MatchmakingQueue()
        q.add(ctx("alice"), 1200)
        q.add(ctx("bob"), 1301)   # 101 points away, just outside +-100
        assert q.find_match() is None
        assert len(q) == 2

    def test_boundary_of_exactly_100_points_matches(self):
        q = MatchmakingQueue()
        q.add(ctx("alice"), 1200)
        q.add(ctx("bob"), 1300)
        assert q.find_match() is not None

    def test_third_player_is_matched_against_the_closest_available_when_pairs_overlap(self):
        q = MatchmakingQueue()
        q.add(ctx("alice"), 1200)
        q.add(ctx("bob"), 1250)
        q.add(ctx("carol"), 1500)   # nobody in range for carol
        pair = q.find_match()
        names = {pair[0].context.connection.name, pair[1].context.connection.name}
        assert names == {"alice", "bob"}
        assert len(q) == 1   # carol is still waiting


class TestExpire:

    def test_entries_younger_than_timeout_are_not_expired(self):
        q = MatchmakingQueue()
        q.add(ctx("alice"), 1200, now=100.0)
        assert q.expire(now=100.0 + 59) == []
        assert len(q) == 1

    def test_entries_at_or_past_timeout_are_expired_and_removed(self):
        q = MatchmakingQueue()
        q.add(ctx("alice"), 1200, now=100.0)
        expired = q.expire(now=100.0 + 60)
        assert len(expired) == 1
        assert expired[0].context.connection.name == "alice"
        assert len(q) == 0

    def test_only_the_stale_entry_expires(self):
        q = MatchmakingQueue()
        q.add(ctx("alice"), 1200, now=0.0)
        q.add(ctx("bob"), 1200, now=50.0)
        expired = q.expire(now=60.0)
        assert [w.context.connection.name for w in expired] == ["alice"]
        assert len(q) == 1


class TestRemoveConnection:

    def test_removes_only_the_matching_connection(self):
        q = MatchmakingQueue()
        alice, bob = ctx("alice"), ctx("bob")
        q.add(alice, 1200)
        q.add(bob, 1200)
        q.remove_connection(alice.connection)
        assert len(q) == 1
        assert q.find_match() is None   # only bob left, no partner
