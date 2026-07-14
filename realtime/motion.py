from typing import NamedTuple, Optional

from model.piece import Piece
from model.position import Position
from rules.piece_config import JUMP, MOVE, PIECE_CONFIG

# Calibrated, not arbitrary: every piece in the current asset pack has a
# uniform 1.5 m/s move speed and (bar one outlier) a uniform 3.0 m/s jump
# speed, so these conversion factors reproduce the project's original fixed
# MS_PER_SQUARE/JUMP_DURATION_MS timing exactly for that common case, while
# still deriving genuinely different durations for a piece whose own config
# actually differs (e.g. a slower jumper really does jump slower).
METERS_PER_CELL = 1.5
JUMP_REFERENCE_DISTANCE_M = 3.0

REST_DURATIONS = {
    "short_rest": 1000,
    "long_rest": 4000,
}

# Kept for readability/back-compat: equal to move_duration_ms(<any kind>, <any
# color>, 1) / jump_duration_ms(<any kind>, <any color>) for every piece in
# the current asset pack.
MS_PER_SQUARE = 1000
JUMP_DURATION_MS = 1000

ARRIVAL = 'arrival'     # a moving piece reaches its destination cell
LANDING = 'landing'     # a jumping piece's airborne window ends
REST_DONE = 'rest_done'  # a piece's post-action cooldown (short/long rest) elapses

# The airborne window is inclusive: an arrival on the very tick a jump ends
# is still met in the air, so ARRIVAL resolves before LANDING on the same tick.
EVENT_ORDER = {ARRIVAL: 0, LANDING: 1, REST_DONE: 2}


def move_duration_ms(kind: str, color: str, distance: int) -> int:
    speed = PIECE_CONFIG.get(kind, color, MOVE).speed_m_per_sec
    return round(distance * METERS_PER_CELL / speed * 1000)


def jump_duration_ms(kind: str, color: str) -> int:
    speed = PIECE_CONFIG.get(kind, color, JUMP).speed_m_per_sec
    return round(JUMP_REFERENCE_DISTANCE_M / speed * 1000)


def rest_duration_ms(state: str) -> int:
    return REST_DURATIONS[state]


class PendingMove(NamedTuple):
    piece: Piece
    frm: Position
    to: Position
    start_time: int
    arrive_time: int

    def interval_in(self, pos: Position) -> Optional[tuple[int, Optional[int]]]:
        """When does this move's piece physically occupy `pos`?

        Returns (enter_ms, leave_ms) - leave_ms is None for the destination,
        where the piece stays - or None if the cell is never crossed.
        """
        if pos == self.to:
            return self.arrive_time, None
        dr, dc = self.to.row - self.frm.row, self.to.col - self.frm.col
        distance = max(abs(dr), abs(dc))
        step_ms = (self.arrive_time - self.start_time) / distance
        start = self.start_time
        if pos == self.frm:
            return start, start + step_ms
        if dr != 0 and dc != 0 and abs(dr) != abs(dc):
            return None
        step_r = (dr > 0) - (dr < 0)
        step_c = (dc > 0) - (dc < 0)
        rr, cc = pos.row - self.frm.row, pos.col - self.frm.col
        k = max(abs(rr), abs(cc))
        if 0 < k < distance and (rr, cc) == (k * step_r, k * step_c):
            return start + k * step_ms, start + (k + 1) * step_ms
        return None


class PendingJump(NamedTuple):
    piece: Piece
    pos: Position
    end_time: int


class PendingRest(NamedTuple):
    piece: Piece
    state: str    # the rest state (e.g. "long_rest") that is ending
    end_time: int


class Idle:
    """A piece with no scheduled action. Implicit default (absence from the status dict)."""


class Moving:
    """A piece travelling toward a destination; stays on its origin cell until arrival."""

    def __init__(self, move: PendingMove):
        self.move = move


class Jumping:
    """A piece hopping in place; it stays on its cell and defends it until it lands."""

    def __init__(self, jump: PendingJump):
        self.jump = jump


class Event(NamedTuple):
    time: int
    kind: str
    activity: object   # the PendingMove / PendingJump / PendingRest that produced the event
