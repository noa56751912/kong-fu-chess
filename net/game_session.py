import asyncio
import logging
from typing import Optional

from boardio.board_parser import build_board
from engine.game_engine import GameEngine
from model.piece import BLACK, WHITE
from net.bus_bridge import BusBridge
from net.protocol import SYNC_STATE, encode, position_to_square, serialize_board

logger = logging.getLogger(__name__)

# 20 ticks/sec: fine enough granularity for settle() to resolve arrivals/jumps/
# rests promptly without flooding the event loop with wakeups.
TICK_MS = 50


class GameSession:
    """One authoritative GameEngine plus the asyncio machinery to run it and
    talk to its connected players over websockets.

    Everything here is single-process/single-event-loop: the tick loop only
    ever awaits asyncio.sleep, and a connection's own message loop only ever
    awaits socket I/O - neither may block, since one session's server-side
    lag would otherwise stall every other session and connection sharing the
    same process.
    """

    def __init__(self, starting_grid: list[list[str]]):
        self.engine = GameEngine(build_board(starting_grid))
        self.connections: dict[str, object] = {}   # color -> websocket connection
        self.bridge = BusBridge(self.engine.bus, self.engine.state.board.rows, self.broadcast_nowait)
        self._tick_task: Optional[asyncio.Task] = None

    def assign_color(self) -> Optional[str]:
        """The first connection is White, the second Black; anyone after that
        gets None here and is routed to spectate instead (see rooms/, Phase E)."""
        if WHITE not in self.connections:
            return WHITE
        if BLACK not in self.connections:
            return BLACK
        return None

    def add_player(self, color: str, connection) -> None:
        self.connections[color] = connection

    def broadcast_nowait(self, message: str) -> None:
        """Fire-and-forget send to every connected player - called from
        synchronous bus-handler code, so it schedules the actual (async)
        socket writes as tasks rather than awaiting them itself."""
        for connection in self.connections.values():
            asyncio.create_task(self._safe_send(connection, message))

    @staticmethod
    async def _safe_send(connection, message: str) -> None:
        try:
            await connection.send(message)
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
