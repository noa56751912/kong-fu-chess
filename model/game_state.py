from dataclasses import dataclass, field
from typing import Callable

from model.board import Board
from model.move_record import MoveRecord
from model.piece import BLACK, KING, Piece, WHITE
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
    winner: str | None = None
    win_conditions: list[Callable[[Piece], bool]] = field(
        default_factory=lambda: list(DEFAULT_WIN_CONDITIONS)
    )
    score: dict[str, int] = field(default_factory=lambda: {WHITE: 0, BLACK: 0})
    moves: list[MoveRecord] = field(default_factory=list)
