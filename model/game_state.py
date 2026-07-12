from dataclasses import dataclass, field
from typing import Callable

from model.board import Board
from model.piece import KING, Piece
from model.position import Position

DEFAULT_WIN_CONDITIONS: list[Callable[[Piece], bool]] = [
    lambda captured: captured.kind == KING,
]


@dataclass
class GameState:
    board: Board
    selection: Position | None = None
    clock_ms: int = 0
    game_over: bool = False
    win_conditions: list[Callable[[Piece], bool]] = field(
        default_factory=lambda: list(DEFAULT_WIN_CONDITIONS)
    )
