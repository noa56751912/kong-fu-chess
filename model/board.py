import itertools
from typing import Iterator

from model.piece import Piece
from model.position import Position

EMPTY = '.'


class Board:
    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self._pieces: dict[Position, Piece] = {}
        self._next_id = itertools.count(1)

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.row < self.rows and 0 <= pos.col < self.cols

    def spawn_piece(self, color: str, kind: str, cell: Position) -> Piece:
        piece = Piece(id=next(self._next_id), color=color, kind=kind, cell=cell)
        self._pieces[cell] = piece
        return piece

    def piece_at(self, pos: Position) -> Piece | None:
        return self._pieces.get(pos)

    def is_empty(self, pos: Position) -> bool:
        return pos not in self._pieces

    def move_piece(self, piece: Piece, to: Position) -> Piece | None:
        """Places `piece` at `to`, capturing (and returning) any occupant.

        No color check here - RuleEngine.is_legal_move is what blocks a move
        onto a same-color piece before it's ever scheduled.
        """
        captured = self._pieces.pop(to, None)
        del self._pieces[piece.cell]
        piece.cell = to
        self._pieces[to] = piece
        return captured

    def remove_piece(self, piece: Piece) -> None:
        """Removes `piece` from the board entirely (e.g. captured mid-air, never lands)."""
        del self._pieces[piece.cell]

    def path_clear(self, frm: Position, to: Position) -> bool:
        dr = to.row - frm.row
        dc = to.col - frm.col
        step_r = (dr > 0) - (dr < 0)
        step_c = (dc > 0) - (dc < 0)
        pos = frm.offset(step_r, step_c)
        while pos != to:
            if not self.is_empty(pos):
                return False
            pos = pos.offset(step_r, step_c)
        return True

    def to_grid(self) -> list[list[str]]:
        grid = [[EMPTY] * self.cols for _ in range(self.rows)]
        for pos, piece in self._pieces.items():
            grid[pos.row][pos.col] = piece.color + piece.kind
        return grid

    def __iter__(self) -> Iterator[tuple[Position, Piece]]:
        return iter(self._pieces.items())
