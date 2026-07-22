import asyncio
import json
from unittest.mock import patch

import net.game_session as game_session_module
from model.piece import BLACK, ROOK, WHITE
from model.position import Position
from net.game_session import GameSession
from net.protocol import PLAYER_DISCONNECTED, PLAYER_RECONNECTED
from persistence.db import connect as connect_db
from persistence.user_repo import UserRepo
from realtime.motion import move_duration_ms


class FakeConnection:
    def __init__(self, name):
        self.name = name
        self.sent: list[dict] = []

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))


def make_session_with_users():
    user_repo = UserRepo(connect_db(":memory:"))
    user_repo.create_user("alice", "pw1")
    user_repo.create_user("bob", "pw2")
    grid = [
        "wR . bK".split(),
        ". . .".split(),
        ". . .".split(),
    ]
    session = GameSession(grid, user_repo)
    session.usernames[WHITE] = "alice"
    session.usernames[BLACK] = "bob"
    return session, user_repo


class TestRatingsUpdateOnGameOver:

    def test_winner_gains_and_loser_loses_rating_after_game_over(self):
        async def scenario():
            session, user_repo = make_session_with_users()
            result = session.engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
            assert result.is_accepted is True
            session.engine.wait(move_duration_ms(ROOK, WHITE, 2))   # rook captures king -> game over
            assert session.engine.game_over is True

            # The rating update is scheduled as an asyncio task (never done
            # inline from the synchronous bus handler) - give the loop a turn.
            await asyncio.sleep(0.05)

            alice = user_repo.get_user("alice")
            bob = user_repo.get_user("bob")
            assert alice.elo_rating == 1216   # equal-rated win/loss, K=32
            assert bob.elo_rating == 1184

        asyncio.run(scenario())

    def test_without_a_user_repo_game_over_does_not_touch_the_database(self):
        # No user_repo passed -> the bus subscription is never even
        # registered, so a local/offline-style session (no accounts
        # involved) doesn't need a database at all.
        grid = [
            "wR . bK".split(),
            ". . .".split(),
            ". . .".split(),
        ]
        session = GameSession(grid)
        session.usernames[WHITE] = "alice"
        session.usernames[BLACK] = "bob"
        result = session.engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        assert result.is_accepted is True
        session.engine.wait(move_duration_ms(ROOK, WHITE, 2))
        assert session.engine.game_over is True   # no exception, nothing to assert on a DB


class TestDisconnectAutoResign:

    def test_opponent_receives_a_disconnect_countdown(self):
        async def scenario():
            with patch.object(game_session_module, 'DISCONNECT_GRACE_S', 1):
                session, _ = make_session_with_users()
                white_conn, black_conn = FakeConnection("white"), FakeConnection("black")
                session.add_player(WHITE, white_conn, "alice")
                session.add_player(BLACK, black_conn, "bob")

                session.on_disconnect(WHITE)
                await asyncio.sleep(0.2)   # let the first countdown tick fire

                countdown_messages = [m for m in black_conn.sent if m["type"] == PLAYER_DISCONNECTED]
                assert len(countdown_messages) == 1
                assert countdown_messages[0]["username"] == "alice"
                assert countdown_messages[0]["countdown_s"] == 1

                await asyncio.sleep(1.5)   # let the grace period fully expire

        asyncio.run(scenario())

    def test_timeout_auto_resigns_and_updates_ratings(self):
        async def scenario():
            with patch.object(game_session_module, 'DISCONNECT_GRACE_S', 1):
                session, user_repo = make_session_with_users()
                white_conn, black_conn = FakeConnection("white"), FakeConnection("black")
                session.add_player(WHITE, white_conn, "alice")
                session.add_player(BLACK, black_conn, "bob")

                session.on_disconnect(WHITE)   # alice (White) disconnects
                await asyncio.sleep(1.3)       # past the 1s grace period

                assert session.engine.state.game_over is True
                assert session.engine.state.winner == BLACK   # bob wins by default

                alice = user_repo.get_user("alice")
                bob = user_repo.get_user("bob")
                assert alice.elo_rating == 1184   # lost by resignation
                assert bob.elo_rating == 1216

        asyncio.run(scenario())

    def test_reconnect_before_timeout_cancels_resignation_and_resyncs(self):
        async def scenario():
            with patch.object(game_session_module, 'DISCONNECT_GRACE_S', 2):
                session, _ = make_session_with_users()
                white_conn, black_conn = FakeConnection("white"), FakeConnection("black")
                session.add_player(WHITE, white_conn, "alice")
                session.add_player(BLACK, black_conn, "bob")

                session.on_disconnect(WHITE)
                await asyncio.sleep(0.1)

                new_white_conn = FakeConnection("white-reconnected")
                await session.on_reconnect(WHITE, new_white_conn)

                # Past where the original 2s grace period would have expired -
                # the game must still be in progress.
                await asyncio.sleep(2.2)
                assert session.engine.state.game_over is False
                assert session.connections[WHITE] is new_white_conn

                # The reconnecting connection got a full SYNC_STATE...
                assert any(m["type"] == "SYNC_STATE" for m in new_white_conn.sent)
                # ...and the opponent was told the disconnect is over.
                assert any(m["type"] == PLAYER_RECONNECTED and m["username"] == "alice"
                           for m in black_conn.sent)

        asyncio.run(scenario())

    def test_disconnect_after_game_already_over_is_a_no_op(self):
        async def scenario():
            session, _ = make_session_with_users()
            result = session.engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
            assert result.is_accepted is True
            session.engine.wait(move_duration_ms(ROOK, WHITE, 2))
            assert session.engine.game_over is True

            session.on_disconnect(WHITE)   # should not schedule anything
            assert session._disconnect_timers == {}

        asyncio.run(scenario())
