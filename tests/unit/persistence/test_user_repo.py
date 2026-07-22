import sqlite3

import pytest

from persistence.db import connect
from persistence.user_repo import DEFAULT_RATING, UserRepo


@pytest.fixture
def repo():
    return UserRepo(connect(":memory:"))


class TestCreateUser:

    def test_new_user_starts_at_default_rating(self, repo):
        user = repo.create_user("alice", "hunter2")
        assert user.username == "alice"
        assert user.elo_rating == DEFAULT_RATING

    def test_password_is_not_stored_in_plain_text(self, repo):
        repo.create_user("alice", "hunter2")
        row = repo._conn.execute(
            "SELECT password_hash FROM users WHERE username = 'alice'"
        ).fetchone()
        assert row[0] != "hunter2"

    def test_duplicate_username_raises_integrity_error(self, repo):
        repo.create_user("alice", "hunter2")
        with pytest.raises(sqlite3.IntegrityError):
            repo.create_user("alice", "different_password")


class TestGetUser:

    def test_unknown_username_returns_none(self, repo):
        assert repo.get_user("nobody") is None

    def test_known_username_returns_user(self, repo):
        repo.create_user("alice", "hunter2")
        user = repo.get_user("alice")
        assert user.username == "alice"
        assert user.elo_rating == DEFAULT_RATING


class TestVerifyPassword:

    def test_correct_password_verifies(self, repo):
        repo.create_user("alice", "hunter2")
        assert repo.verify_password("alice", "hunter2") is True

    def test_wrong_password_does_not_verify(self, repo):
        repo.create_user("alice", "hunter2")
        assert repo.verify_password("alice", "wrong") is False

    def test_unknown_username_does_not_verify(self, repo):
        assert repo.verify_password("nobody", "anything") is False


class TestUpdateRating:

    def test_rating_is_persisted(self, repo):
        repo.create_user("alice", "hunter2")
        repo.update_rating("alice", 1250)
        assert repo.get_user("alice").elo_rating == 1250
