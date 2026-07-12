from typing import NamedTuple, Optional

from model.piece import Piece
from model.position import Position

MS_PER_SQUARE = 1000
JUMP_DURATION_MS = 1000

ARRIVAL = 'arrival'   # a moving piece reaches its destination cell
LANDING = 'landing'   # a jumping piece's airborne window ends

# The airborne window is inclusive: an arrival on the very tick a jump ends
# is still met in the air, so ARRIVAL resolves before LANDING on the same tick.
EVENT_ORDER = {ARRIVAL: 0, LANDING: 1}


class PendingMove(NamedTuple):
    piece: Piece
    frm: Position
    to: Position
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
        start = self.arrive_time - distance * MS_PER_SQUARE
        if pos == self.frm:
            return start, start + MS_PER_SQUARE
        if dr != 0 and dc != 0 and abs(dr) != abs(dc):
            return None
        step_r = (dr > 0) - (dr < 0)
        step_c = (dc > 0) - (dc < 0)
        rr, cc = pos.row - self.frm.row, pos.col - self.frm.col
        k = max(abs(rr), abs(cc))
        if 0 < k < distance and (rr, cc) == (k * step_r, k * step_c):
            return start + k * MS_PER_SQUARE, start + (k + 1) * MS_PER_SQUARE
        return None


class PendingJump(NamedTuple):
    piece: Piece
    pos: Position
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
    activity: object   # the PendingMove / PendingJump that produced the event
