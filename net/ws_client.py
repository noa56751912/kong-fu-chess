import logging
import threading
from typing import Optional

import websockets

from model.board import Board
from model.move_record import MoveRecord
from model.position import Position
from net.protocol import (
    CANCEL_SEARCH, CREATE_ROOM, ERROR, EVENT, GAME_OVER, JOIN_ROOM, JUMP,
    LOGIN, LOGIN_OK, MATCH_FOUND, MOVE, NO_MATCH_FOUND, PLAY,
    PLAYER_DISCONNECTED, PLAYER_RECONNECTED, ROOM_CREATED, SYNC_STATE, decode,
    deserialize_board, encode, position_to_square, square_to_position,
)
from realtime.motion import PendingJump, PendingMove
from rules.piece_config import JUMP as JUMP_STATE, MOVE as MOVE_STATE

logger = logging.getLogger(__name__)


class NetworkGameClient:
    """Passive renderer-side mirror of the server's authoritative GameEngine.

    Holds a real model.Board, mutated with the exact same primitives
    RealTimeArbiter uses server-side, plus a locally reconstructed in-flight
    list shaped like the engine's own PendingMove/PendingJump - so the
    existing ImageView.render() call can be fed from this mirror almost
    exactly as it's fed from a local GameEngine, without running any rules or
    timing logic of its own. It is built entirely from SYNC_STATE/EVENT
    messages; a full SYNC_STATE only ever arrives on join or reconnect.
    """

    def __init__(self):
        self.board: Optional[Board] = None
        self.color: Optional[str] = None
        self.score: dict[str, int] = {}
        self.moves: list[MoveRecord] = []
        self.clock_ms: int = 0
        self.game_over: bool = False
        self.winner: Optional[str] = None
        self.pending_moves: list[PendingMove] = []
        self.pending_jumps: list[PendingJump] = []
        # (ready_at_clock_ms, apply_fn) pairs - board mutations (arrivals,
        # captures) held back until tick() sees the caller's own render
        # clock reach ready_at, so a move never visually snaps to its
        # destination ahead of this client's own interpolation of it.
        self._pending_arrivals: list[tuple[float, object]] = []
        self.last_error: Optional[dict] = None
        self.username: Optional[str] = None
        self.rating: Optional[int] = None
        # color -> username for whichever seats are filled so far - not just
        # this connection's own, so ImageView can show real names instead of
        # "White"/"Black" for both sides. Backfilled by SYNC_STATE for seats
        # already filled at the time this client joined, and kept current
        # afterward by the player.joined event for anyone who joins later.
        self.usernames: dict[str, str] = {}
        self.room_id: Optional[str] = None
        self.searching: bool = False
        self.no_match_found: bool = False
        # Set while the opponent is disconnected and their auto-resign grace
        # period is counting down; cleared on reconnect or once the game ends.
        self.opponent_disconnect_username: Optional[str] = None
        self.opponent_disconnect_countdown_s: Optional[int] = None
        # Bumped on every SYNC_STATE, so a caller tracking its own wall-clock-
        # derived render clock (client_main.py) can tell "a fresh clock_ms
        # just arrived, re-anchor to it" apart from "nothing changed".
        self.sync_version: int = 0
        # Guards every mutation of the attributes above, all of which are
        # written here on the background network thread (see
        # client_main.py's _start_network_thread) and read on the main
        # thread by the render loop. self.board specifically holds a plain
        # dict mutated in place (vacate/move_piece/remove_piece) - iterating
        # it in ImageView.render() while this thread deletes/inserts a key
        # raises "dictionary changed size during iteration" without this
        # lock held across both the mutation and the render call.
        self.lock = threading.Lock()
        self._pieces_by_id: dict[int, object] = {}
        self._connection = None

    async def connect(self, uri: str) -> None:
        self._connection = await websockets.connect(uri)

    async def _send(self, message: dict) -> None:
        raw = encode(message)
        await self._connection.send(raw)
        logger.debug("sent: %s", raw)

    async def login(self, username: str, password: str) -> bool:
        """The required first exchange on a fresh connection: a plain
        request/response, read directly (not via run()'s general dispatch
        loop, which isn't running yet). An unknown username auto-registers
        server-side; a known one must match its stored password."""
        await self._send({"type": LOGIN, "username": username, "password": password})
        raw = await self._connection.recv()
        logger.debug("recv: %s", raw)
        reply = decode(raw)
        if reply.get("type") == LOGIN_OK:
            self.username = username
            self.rating = reply.get("rating")
            return True
        self.last_error = reply
        return False

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def send_play(self) -> None:
        self.no_match_found = False
        self.searching = True
        await self._send({"type": PLAY})

    async def send_cancel_search(self) -> None:
        self.searching = False
        await self._send({"type": CANCEL_SEARCH})

    async def send_create_room(self) -> None:
        await self._send({"type": CREATE_ROOM})

    async def send_join_room(self, room_id: str) -> None:
        await self._send({"type": JOIN_ROOM, "room_id": room_id})

    async def send_move(self, frm: Position, to: Position) -> None:
        rows = self.board.rows
        await self._send({
            "type": MOVE, "from": position_to_square(frm, rows), "to": position_to_square(to, rows),
        })

    async def send_jump(self, pos: Position) -> None:
        rows = self.board.rows
        await self._send({"type": JUMP, "square": position_to_square(pos, rows)})

    async def run(self) -> None:
        """Consume incoming messages, applying each to the local mirror, until
        the connection closes."""
        async for raw in self._connection:
            logger.debug("recv: %s", raw)
            with self.lock:
                self.handle_message(decode(raw))

    def tick(self, local_clock_ms: float) -> None:
        """Applies any buffered arrival/capture (see _pending_arrivals)
        whose target time has been reached by the caller's own render
        clock. Must be called once per frame from client_main.py's render
        loop, under self.lock - the buffering only prevents a visual jump
        if something is actually driving the clock forward and periodically
        checking it."""
        if not self._pending_arrivals:
            return
        ready = [item for item in self._pending_arrivals if local_clock_ms >= item[0]]
        if not ready:
            return
        self._pending_arrivals = [item for item in self._pending_arrivals if local_clock_ms < item[0]]
        for _, apply in sorted(ready, key=lambda item: item[0]):
            apply()

    def handle_message(self, message: dict) -> None:
        msg_type = message.get("type")
        if msg_type == SYNC_STATE:
            self._apply_sync_state(message)
        elif msg_type == EVENT:
            self._apply_event(message["topic"], message["payload"])
        elif msg_type == GAME_OVER:
            self.game_over = True
            self.winner = message.get("winner")
        elif msg_type == PLAYER_DISCONNECTED:
            self.opponent_disconnect_username = message.get("username")
            self.opponent_disconnect_countdown_s = message.get("countdown_s")
        elif msg_type == PLAYER_RECONNECTED:
            self.opponent_disconnect_username = None
            self.opponent_disconnect_countdown_s = None
        elif msg_type == MATCH_FOUND:
            self.searching = False
            self.room_id = message.get("room_id")
            # color/board arrive moments later on the SYNC_STATE that always
            # follows a MATCH_FOUND - nothing further to do with this one.
        elif msg_type == NO_MATCH_FOUND:
            self.searching = False
            self.no_match_found = True
        elif msg_type == ROOM_CREATED:
            self.room_id = message.get("room_id")
            # color/board follow on the SYNC_STATE the server sends right
            # after, same as MATCH_FOUND - nothing further to do with this one.
        elif msg_type == ERROR:
            self.last_error = message

    def _apply_sync_state(self, message: dict) -> None:
        self.color = message.get("color")
        self.board = deserialize_board(message["board"])
        self._pieces_by_id = {piece.id: piece for _, piece in self.board}
        self.score = message["score"]
        self.usernames = dict(message.get("usernames", {}))
        self.clock_ms = message["clock_ms"]
        self.game_over = message["game_over"]
        self.winner = message["winner"]
        rows = self.board.rows
        self.moves = [
            MoveRecord(m["color"], m["kind"], square_to_position(m["frm"], rows),
                       square_to_position(m["to"], rows), m["time_ms"])
            for m in message["moves"]
        ]
        # Any in-flight motion is implicit in the board (an in-flight piece's
        # origin is already vacated there, same as server-side) - the moves/
        # jumps themselves aren't replayed, so there's nothing to interpolate
        # until the next move.started/jump.started event arrives.
        self.pending_moves.clear()
        self.pending_jumps.clear()
        self._pending_arrivals.clear()
        # A resync (join, or a reconnect landing here) means any stale
        # opponent-disconnect countdown from before is no longer meaningful.
        self.opponent_disconnect_username = None
        self.opponent_disconnect_countdown_s = None
        self.sync_version += 1

    def _apply_event(self, topic: str, payload: dict) -> None:
        rows = self.board.rows
        handler = self._EVENT_HANDLERS.get(topic)
        if handler is not None:
            handler(self, payload, rows)

    def _on_move_started(self, payload: dict, rows: int) -> None:
        piece = self._pieces_by_id[payload["piece_id"]]
        frm = square_to_position(payload["from"], rows)
        to = square_to_position(payload["to"], rows)
        self.board.vacate(frm)
        piece.state = MOVE_STATE
        self.pending_moves.append(PendingMove(piece, frm, to, payload["start_time"], payload["arrive_time"]))

    def _on_move_arrived(self, payload: dict, rows: int) -> None:
        piece = self._pieces_by_id[payload["piece_id"]]
        to = square_to_position(payload["to"], rows)

        def apply() -> None:
            captured = self.board.move_piece(piece, to)
            if captured is not None:
                captured.captured = True
            self.pending_moves = [m for m in self.pending_moves if m.piece.id != piece.id]

        # The network event fires the instant the *server* resolves the
        # arrival, which is typically a little ahead of this client's own
        # local_clock_ms (see client_main.py - it lags the server's clock by
        # network/processing latency). Applying the board mutation
        # immediately would yank the piece to its destination before this
        # client's own interpolation of it had visually finished, i.e. a
        # jump instead of a smooth slide. Buffering it until tick() sees
        # local_clock_ms catch up to this move's own arrive_time means the
        # piece is always already fully interpolated there by the time the
        # "official" arrival happens - nothing to visually snap.
        pending = next((m for m in self.pending_moves if m.piece.id == piece.id), None)
        ready_at = pending.arrive_time if pending is not None else self.clock_ms
        self._pending_arrivals.append((ready_at, apply))

    def _on_jump_started(self, payload: dict, rows: int) -> None:
        piece = self._pieces_by_id[payload["piece_id"]]
        pos = square_to_position(payload["pos"], rows)
        piece.state = JUMP_STATE
        self.pending_jumps.append(PendingJump(piece, pos, payload["end_time"]))

    def _on_jump_landed(self, payload: dict, rows: int) -> None:
        piece = self._pieces_by_id[payload["piece_id"]]
        self.pending_jumps = [j for j in self.pending_jumps if j.piece.id != piece.id]

    def _on_piece_captured(self, payload: dict, rows: int) -> None:
        # move.arrived's buffered apply() already detaches a captured piece
        # from the board (via board.move_piece, exactly like the server);
        # the airborne-defense case has no accompanying move.arrived (the
        # arriving piece dies mid-air, never resolving as a normal arrival),
        # so this still needs to handle removal itself there.
        piece = self._pieces_by_id.get(payload["piece_id"])
        if piece is None or piece.captured:
            return

        # If some other piece is mid-flight *toward* this one's square, it's
        # the attacker - align this piece's removal with that same
        # move's buffered arrival so the victim doesn't vanish before the
        # attacker has visually arrived. Otherwise (airborne-defense, or no
        # matching pending move for any other reason) there's no slide to
        # wait for, so it's removed immediately, same as before.
        incoming = next((m for m in self.pending_moves if m.to == piece.cell and m.piece.id != piece.id), None)
        if incoming is not None:
            self._pending_arrivals.append((incoming.arrive_time, lambda p=piece: self._remove_captured_piece(p)))
        else:
            self._remove_captured_piece(piece)

        # A "ghost" in-flight entry for the captured piece itself (relevant
        # to the airborne case, where the captured piece was the one
        # mid-flight) must not linger regardless of which branch above ran -
        # otherwise ImageView would keep trying to interpolate it forever.
        self.pending_moves = [m for m in self.pending_moves if m.piece.id != piece.id]
        self.pending_jumps = [j for j in self.pending_jumps if j.piece.id != piece.id]

    def _remove_captured_piece(self, piece) -> None:
        if not piece.captured:
            piece.captured = True
            self.board.remove_piece(piece)

    def _on_piece_state_changed(self, payload: dict, rows: int) -> None:
        piece = self._pieces_by_id.get(payload["piece_id"])
        if piece is not None:
            piece.state = payload["state"]

    def _on_score_changed(self, payload: dict, rows: int) -> None:
        self.score[payload["color"]] = payload["score"]

    def _on_game_over(self, payload: dict, rows: int) -> None:
        self.game_over = True
        self.winner = payload.get("winner")
        self.opponent_disconnect_username = None
        self.opponent_disconnect_countdown_s = None

    def _on_player_joined(self, payload: dict, rows: int) -> None:
        self.usernames[payload["color"]] = payload["username"]

    _EVENT_HANDLERS = {
        "move.started": _on_move_started,
        "move.arrived": _on_move_arrived,
        "jump.started": _on_jump_started,
        "jump.landed": _on_jump_landed,
        "piece.captured": _on_piece_captured,
        "piece.state_changed": _on_piece_state_changed,
        "score.changed": _on_score_changed,
        "game.over": _on_game_over,
        "player.joined": _on_player_joined,
    }
