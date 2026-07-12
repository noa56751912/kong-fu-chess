from dataclasses import dataclass
from typing import Callable, Optional

from model.board import Board
from model.piece import BISHOP, KING, KNIGHT, PAWN, QUEEN, ROOK, WHITE, BLACK, Piece
from model.position import Position

TOP_ROW = 0
ONE_SQUARE = 1
TWO_SQUARES = 2
KING_REACH = ONE_SQUARE
KNIGHT_SHAPE = sorted([ONE_SQUARE, TWO_SQUARES])
PAWN_CAPTURE_SPAN = ONE_SQUARE

WHITE_FORWARD = -ONE_SQUARE
BLACK_FORWARD = ONE_SQUARE
FORWARD_BY_COLOR = {WHITE: WHITE_FORWARD, BLACK: BLACK_FORWARD}


@dataclass(frozen=True)
class MoveContext:
    frm: Position
    to: Position
    board: Board
    start_row_offset: Optional[int]


ShapePredicate = Callable[[int, int, str, MoveContext], bool]


def _king_shape(dr, dc, color, ctx):
    return max(abs(dr), abs(dc)) == KING_REACH


def _knight_shape(dr, dc, color, ctx):
    return sorted([abs(dr), abs(dc)]) == KNIGHT_SHAPE


def _rook_shape(dr, dc, color, ctx):
    return dr == 0 or dc == 0


def _bishop_shape(dr, dc, color, ctx):
    return abs(dr) == abs(dc) and dr != 0


def _queen_shape(dr, dc, color, ctx):
    return _rook_shape(dr, dc, color, ctx) or _bishop_shape(dr, dc, color, ctx)


def _pawn_capture(dr, dc, color, ctx):
    return abs(dc) == PAWN_CAPTURE_SPAN and dr == FORWARD_BY_COLOR[color]


def _pawn_shape(dr, dc, color, ctx):
    if dc != 0:
        return False
    direction = FORWARD_BY_COLOR[color]
    if dr == direction * ONE_SQUARE:
        return True
    if dr != direction * TWO_SQUARES:
        return False
    if ctx.start_row_offset is None:
        return False
    start_row = (ctx.board.rows - ONE_SQUARE - ctx.start_row_offset) if color == WHITE else ctx.start_row_offset
    if ctx.frm.row != start_row:
        return False
    return ctx.board.path_clear(ctx.frm, ctx.frm.offset(dr, 0))


def _pawn_promote(piece: Piece, board: Board) -> None:
    """Promote a pawn that arrived on the last row - mutates kind in place."""
    last_row = TOP_ROW if piece.color == WHITE else board.rows - ONE_SQUARE
    if piece.cell.row == last_row:
        piece.kind = QUEEN


@dataclass(frozen=True)
class MoveRule:
    shape_ok: ShapePredicate
    sliding: bool
    capture_ok: Optional[ShapePredicate] = None
    start_row_offset: Optional[int] = None
    on_arrive: Optional[Callable[[Piece, Board], None]] = None


MOVE_RULES: dict[str, MoveRule] = {
    KING: MoveRule(shape_ok=_king_shape, sliding=False),
    KNIGHT: MoveRule(shape_ok=_knight_shape, sliding=False),
    ROOK: MoveRule(shape_ok=_rook_shape, sliding=True),
    BISHOP: MoveRule(shape_ok=_bishop_shape, sliding=True),
    QUEEN: MoveRule(shape_ok=_queen_shape, sliding=True),
    PAWN: MoveRule(shape_ok=_pawn_shape, sliding=False, capture_ok=_pawn_capture,
                   start_row_offset=ONE_SQUARE, on_arrive=_pawn_promote),
}
