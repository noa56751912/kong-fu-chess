from typing import Optional

from model.board import Board
from model.position import Position

CELL_SIZE = 100


def pixel_to_cell(x: int, y: int, board: Board, cell_size: int = CELL_SIZE) -> Optional[Position]:
    row, col = y // cell_size, x // cell_size
    pos = Position(row, col)
    return pos if board.in_bounds(pos) else None
