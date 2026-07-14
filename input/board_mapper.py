from typing import Optional

from model.board import Board
from model.position import Position

CELL_SIZE = 100


def pixel_to_cell(x: int, y: int, board: Board, cell_size: int = CELL_SIZE) -> Optional[Position]:
    row, col = y // cell_size, x // cell_size
    pos = Position(row, col)
    return pos if board.in_bounds(pos) else None


def cell_to_pixel(pos: Position, cell_size: int = CELL_SIZE) -> tuple[int, int]:
    """Top-left pixel corner of `pos`'s square - the inverse of pixel_to_cell."""
    return pos.col * cell_size, pos.row * cell_size
