import asyncio
import logging
from typing import Optional

from boardio.board_parser import build_board
from bus.logging_subscriber import attach_logging
from engine.game_engine import GameEngine
from model.piece import BLACK, WHITE
from net.bus_bridge import BusBridge
from net.protocol import (
    PLAYER_DISCONNECTED, PLAYER_RECONNECTED, SYNC_STATE, encode, position_to_square,
    serialize_board,
)
from persistence.elo import compute_new_ratings
from persistence.user_repo import UserRepo

logger = logging.getLogger(__name__)

# 20 ticks/sec: fine enough granularity for settle() to resolve arrivals/jumps/
# rests promptly without flooding the event loop with wakeups.
TICK_MS = 50

# How long a disconnected player has to reconnect before auto-resigning.
DISCONNECT_GRACE_S = 20

# Shared by matchmaking (net/ws_server.py) and rooms (rooms/room_manager.py) -
# lives here, not in ws_server.py, so room_manager.py can use it without a
# circular import back to ws_server.py.
STARTING_POSITION = [
    "bR bN bB bQ bK bB bN bR".split(),
    "bP bP bP bP bP bP bP bP".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    "wP wP wP wP wP wP wP wP".split(),
    "wR wN wB wQ wK wB wN wR".split(),
]


class GameSession:
    """One authoritative GameEngine plus the asyncio machinery to run it and
    talk to its connected players over websockets.

    Everything here is single-process/single-event-loop: the tick loop only
    ever awaits asyncio.sleep, and a connection's own message loop only ever
    awaits socket I/O - neither may block, since one session's server-side
    lag would otherwise stall every other session and connection sharing the
    same process.
    """

    def __init__(self, starting_grid: list[list[str]], user_repo: Optional[UserRepo] = None,
                 label: str = ""):
        self.engine = GameEngine(build_board(starting_grid))
        self.connections: dict[str, object] = {}   # color -> websocket connection
        self.usernames: dict[str, str] = {}         # color -> logged-in username
        self.spectators: list[object] = []           # read-only connections (rooms/, Phase E)
        self.bridge = BusBridge(self.engine.bus, self.engine.state.board.rows, self.broadcast_nowait)
        attach_logging(self.engine.bus, label)   # every session/room logs its own bus activity
        self._tick_task: Optional[asyncio.Task] = None
        self._disconnect_timers: dict[str, asyncio.Task] = {}   # color -> pending auto-resign timer
        self._user_repo = user_repo
        if user_repo is not None:
            self.engine.bus.subscribe('game.over', self._on_game_over)

    def assign_color(self) -> Optional[str]:
        """The first connection is White, the second Black; anyone after that
        gets None here and is routed to spectate instead (see rooms/, Phase E)."""
        if WHITE not in self.connections:
            return WHITE
        if BLACK not in self.connections:
            return BLACK
        return None

    def add_player(self, color: str, connection, username: str) -> None:
        self.connections[color] = connection
        self.usernames[color] = username
        # SYNC_STATE is only ever sent once per recipient (join/reconnect),
        # so a player already connected before their opponent joins would
        # otherwise never learn that name - this lets ImageView show real
        # usernames instead of "White"/"Black" for both sides, not just
        # whichever side happened to be seated first.
        self.engine.bus.publish('player.joined', {'color': color, 'username': username})

    def add_spectator(self, connection) -> None:
        self.spectators.append(connection)

    def remove_spectator(self, connection) -> None:
        if connection in self.spectators:
            self.spectators.remove(connection)

    def _on_game_over(self, payload: dict) -> None:
        """Bus handlers are synchronous, and an ELO update is a blocking
        SQLite write - so this only schedules the actual update as a task
        rather than performing it inline, the same pattern broadcast_nowait
        uses for socket sends."""
        winner_color = payload.get('winner')
        if winner_color is None:
            return
        loser_color = BLACK if winner_color == WHITE else WHITE
        winner_username = self.usernames.get(winner_color)
        loser_username = self.usernames.get(loser_color)
        if winner_username is None or loser_username is None:
            return
        asyncio.create_task(self._update_ratings(winner_username, loser_username))

    async def _update_ratings(self, winner_username: str, loser_username: str) -> None:
        winner = await asyncio.to_thread(self._user_repo.get_user, winner_username)
        loser = await asyncio.to_thread(self._user_repo.get_user, loser_username)
        if winner is None or loser is None:
            return
        new_winner_rating, new_loser_rating = compute_new_ratings(
            winner.elo_rating, loser.elo_rating, result_a=1.0)
        await asyncio.to_thread(self._user_repo.update_rating, winner_username, new_winner_rating)
        await asyncio.to_thread(self._user_repo.update_rating, loser_username, new_loser_rating)
        logger.info("ratings updated: %s %d->%d, %s %d->%d",
                    winner_username, winner.elo_rating, new_winner_rating,
                    loser_username, loser.elo_rating, new_loser_rating)

    def _opponent_color(self, color: str) -> str:
        return BLACK if color == WHITE else WHITE

    def on_disconnect(self, color: str) -> None:
        """Called once a connection's own message loop ends. Starts a grace-
        period timer rather than resigning immediately - the player may just
        be reloading a page, not gone for good - and does nothing at all if
        the game already ended by the time this fires (e.g. the disconnect
        is simply the player closing the client after a normal win/loss)."""
        if self.engine.state.game_over or color in self._disconnect_timers:
            return
        self._disconnect_timers[color] = asyncio.create_task(self._run_disconnect_timer(color))

    async def _run_disconnect_timer(self, color: str) -> None:
        try:
            for remaining in range(DISCONNECT_GRACE_S, 0, -1):
                self._notify_disconnect_countdown(color, remaining)
                await asyncio.sleep(1)
            self._resign(color)
        except asyncio.CancelledError:
            pass   # reconnected in time - on_reconnect cancels this task
        finally:
            self._disconnect_timers.pop(color, None)

    def _notify_disconnect_countdown(self, color: str, remaining: int) -> None:
        opponent_connection = self.connections.get(self._opponent_color(color))
        if opponent_connection is None:
            return
        message = encode({
            "type": PLAYER_DISCONNECTED, "username": self.usernames.get(color), "countdown_s": remaining,
        })
        asyncio.create_task(self._safe_send(opponent_connection, message))

    def _resign(self, color: str) -> None:
        """The disconnected player's grace period expired: a technical loss,
        same as any other game.over - it goes through the exact same bus
        event (with a distinguishing reason) so the existing ELO-update
        subscriber and the network broadcast to the opponent both just work,
        without a second code path duplicating either."""
        if self.engine.state.game_over:
            return
        winner_color = self._opponent_color(color)
        self.engine.state.game_over = True
        self.engine.state.winner = winner_color
        self.engine.bus.publish('game.over', {'winner': winner_color, 'reason': 'opponent_disconnected'})

    async def on_reconnect(self, color: str, new_connection) -> None:
        """Called when the same username logs back in while still attached
        to this in-progress session. Cancels the pending auto-resign timer,
        rebinds the connection, and sends the second (and only other) full
        SYNC_STATE this session ever emits - the reconnecting client has no
        idea what it missed, so a full snapshot is the correct resync."""
        timer = self._disconnect_timers.get(color)
        if timer is not None:
            timer.cancel()
            self._notify_reconnected(color)
        self.connections[color] = new_connection
        await self.send_sync_state(new_connection, color)

    def _notify_reconnected(self, color: str) -> None:
        opponent_connection = self.connections.get(self._opponent_color(color))
        if opponent_connection is None:
            return
        message = encode({"type": PLAYER_RECONNECTED, "username": self.usernames.get(color)})
        asyncio.create_task(self._safe_send(opponent_connection, message))

    def broadcast_nowait(self, message: str) -> None:
        """Fire-and-forget send to every connected player and spectator -
        called from synchronous bus-handler code, so it schedules the actual
        (async) socket writes as tasks rather than awaiting them itself."""
        for connection in self.connections.values():
            asyncio.create_task(self._safe_send(connection, message))
        for connection in self.spectators:
            asyncio.create_task(self._safe_send(connection, message))

    @staticmethod
    async def _safe_send(connection, message: str) -> None:
        try:
            await connection.send(message)
            logger.debug("sent: %s", message)
        except Exception:
            logger.exception("failed to deliver a message to a connection")

    def _sync_state_message(self, color: Optional[str]) -> str:
        state = self.engine.state
        rows = state.board.rows
        moves = [
            {
                "color": record.color,
                "kind": record.kind,
                "frm": position_to_square(record.frm, rows),
                "to": position_to_square(record.to, rows),
                "time_ms": record.time_ms,
            }
            for record in state.moves
        ]
        return encode({
            "type": SYNC_STATE,
            "color": color,   # which side (if any) this recipient is playing
            "board": serialize_board(state.board),
            "score": state.score,
            "usernames": dict(self.usernames),   # whichever seats are already filled
            "moves": moves,
            "clock_ms": state.clock_ms,
            "game_over": state.game_over,
            "winner": state.winner,
        })

    async def send_sync_state(self, connection, color: Optional[str] = None) -> None:
        """The only full-board message: sent once when a connection joins
        (here) and once more on reconnect (Phase D) - never on a timer."""
        await connection.send(self._sync_state_message(color))

    def start_tick_loop(self) -> None:
        if self._tick_task is None:
            self._tick_task = asyncio.create_task(self._run_tick_loop())

    async def _run_tick_loop(self) -> None:
        while not self.engine.game_over:
            await asyncio.sleep(TICK_MS / 1000)
            self.engine.wait(TICK_MS)
