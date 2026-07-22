"""JSON wire messages + the algebraic-square <-> Position conversion used to
build them and to format the WQe2e5-style move strings used for display/logs.

Message shape on the wire is always {"type": <one of the constants below>, ...fields}.
"""
import json

from model.board import Board
from model.position import Position

# Client -> server
LOGIN = "LOGIN"
MOVE = "MOVE"
JUMP = "JUMP"
PLAY = "PLAY"
CANCEL_SEARCH = "CANCEL_SEARCH"
CREATE_ROOM = "CREATE_ROOM"
JOIN_ROOM = "JOIN_ROOM"

# Server -> client
LOGIN_OK = "LOGIN_OK"
LOGIN_FAIL = "LOGIN_FAIL"
SYNC_STATE = "SYNC_STATE"
EVENT = "EVENT"
MATCH_FOUND = "MATCH_FOUND"
NO_MATCH_FOUND = "NO_MATCH_FOUND"
ROOM_CREATED = "ROOM_CREATED"
PLAYER_DISCONNECTED = "PLAYER_DISCONNECTED"
PLAYER_RECONNECTED = "PLAYER_RECONNECTED"
GAME_OVER = "GAME_OVER"
ERROR = "ERROR"


class ProtocolError(ValueError):
    """Raised for a malformed wire message (bad JSON, missing/invalid fields)."""


def encode(message: dict) -> str:
    return json.dumps(message)


def decode(data: str) -> dict:
    try:
        message = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc
    if not isinstance(message, dict) or "type" not in message:
        raise ProtocolError("message must be a JSON object with a 'type' field")
    return message


def square_to_position(square: str, rows: int) -> Position:
    """'e2' -> Position(row, col); row 0 is the top of the board (rank `rows`),
    matching model/position.py and the STARTING_POSITION grid convention."""
    if len(square) < 2 or not square[0].isalpha() or not square[1:].isdigit():
        raise ProtocolError(f"not a valid square: {square!r}")
    col = ord(square[0].lower()) - ord('a')
    rank = int(square[1:])
    row = rows - rank
    return Position(row, col)


def position_to_square(pos: Position, rows: int) -> str:
    """Inverse of square_to_position."""
    return f"{chr(ord('a') + pos.col)}{rows - pos.row}"


def format_move_string(color: str, kind: str, frm: Position, to: Position, rows: int) -> str:
    """'WQe2e5'-style human-readable move label, per the spec's example."""
    return f"{color.upper()}{kind}{position_to_square(frm, rows)}{position_to_square(to, rows)}"


def serialize_board(board: Board) -> dict:
    """Full board state for a SYNC_STATE message - deliberately not the plain
    "wK"-token grid boardio/board_parser.py uses for the old text-script
    protocol: that format has no piece id or piece.state, so rebuilding from
    it would (a) hand out fresh, server-mismatched ids on every resync,
    silently breaking every subsequent EVENT's piece_id lookup, and (b) lose
    mid-rest/mid-cooldown state. Every piece's real id and state are carried
    explicitly so a resync is actually a faithful, resumable snapshot."""
    return {
        "rows": board.rows,
        "cols": board.cols,
        "pieces": [
            {"id": piece.id, "color": piece.color, "kind": piece.kind,
             "pos": position_to_square(pos, board.rows), "state": piece.state}
            for pos, piece in board
        ],
    }


def deserialize_board(data: dict) -> Board:
    """Inverse of serialize_board - the client-side mirror's only source of a
    full board, at initial join and at reconnect."""
    board = Board(data["rows"], data["cols"])
    for entry in data["pieces"]:
        pos = square_to_position(entry["pos"], data["rows"])
        # spawn_piece has no way to take an explicit id, so it's patched in
        # right after: every EVENT that follows addresses pieces by the
        # server's real id, so the client absolutely must reuse it rather
        # than whatever spawn_piece's own counter would have assigned.
        piece = board.spawn_piece(entry["color"], entry["kind"], pos)
        piece.id = entry["id"]
        piece.state = entry["state"]
    return board


def positions_to_squares(payload: dict, rows: int) -> dict:
    """Shallow-converts any Position-valued field of a bus-event payload (e.g.
    'from'/'to'/'pos') into its algebraic square string, so the payload is
    plain-JSON-serializable. Every other field is passed through unchanged."""
    return {
        key: (position_to_square(value, rows) if isinstance(value, Position) else value)
        for key, value in payload.items()
    }
