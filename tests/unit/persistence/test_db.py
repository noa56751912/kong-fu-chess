from persistence.db import connect


class TestConnect:

    def test_creates_users_table(self):
        conn = connect(":memory:")
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        assert row is not None

    def test_calling_connect_twice_on_the_same_file_does_not_error(self, tmp_path):
        db_path = tmp_path / "test.db"
        connect(db_path).close()
        conn2 = connect(db_path)   # schema already exists - must be idempotent
        row = conn2.execute("SELECT count(*) FROM users").fetchone()
        assert row[0] == 0
