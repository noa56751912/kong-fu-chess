import asyncio

from model.piece import BLACK, ROOK, WHITE
from model.position import Position
from net.game_session import GameSession
from persistence.db import connect as connect_db
from persistence.user_repo import UserRepo
from realtime.motion import move_duration_ms


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
