from net.game_session import GameSession
from rooms.room_manager import RoomManager


class TestCreateRoom:

    def test_creates_a_new_session_registered_by_room_id(self):
        sessions = {}
        manager = RoomManager(sessions, None)
        room_id, session = manager.create_room()
        assert sessions[room_id] is session
        assert isinstance(session, GameSession)

    def test_each_call_creates_a_distinct_room(self):
        sessions = {}
        manager = RoomManager(sessions, None)
        room_id_1, session_1 = manager.create_room()
        room_id_2, session_2 = manager.create_room()
        assert room_id_1 != room_id_2
        assert session_1 is not session_2


class TestGetRoom:

    def test_unknown_room_id_returns_none(self):
        manager = RoomManager({}, None)
        assert manager.get_room("nonexistent") is None

    def test_known_room_id_returns_its_session(self):
        sessions = {}
        manager = RoomManager(sessions, None)
        room_id, session = manager.create_room()
        assert manager.get_room(room_id) is session
