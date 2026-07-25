import secrets
from typing import Optional

from net.game_session import STARTING_POSITION, GameSession
from persistence.user_repo import UserRepo


class RoomManager:
    """Server-side room lifecycle: create_room mints a fresh GameSession
    (the creator seats as White separately, via the same _seat_player helper
    matchmaking uses); get_room looks one up by id for a joiner. A room_id
    and a matchmaking match_id are the same concept - both just keys into
    ServerState.sessions - so rooms share that one registry rather than
    keeping a second, parallel one."""

    def __init__(self, sessions: dict[str, GameSession], user_repo: Optional[UserRepo]):
        self._sessions = sessions
        self._user_repo = user_repo

    def create_room(self) -> tuple[str, GameSession]:
        room_id = secrets.token_hex(3)
        session = GameSession(STARTING_POSITION, self._user_repo, label=room_id)
        self._sessions[room_id] = session
        return room_id, session

    def get_room(self, room_id: str) -> Optional[GameSession]:
        return self._sessions.get(room_id)
