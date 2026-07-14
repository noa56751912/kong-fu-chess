from dataclasses import dataclass

from model.position import Position
from rules.piece_config import IDLE

WHITE = 'w'
BLACK = 'b'

KING = 'K'
QUEEN = 'Q'
ROOK = 'R'
BISHOP = 'B'
KNIGHT = 'N'
PAWN = 'P'


@dataclass
class Piece:
    id: int
    color: str
    kind: str
    cell: Position
    state: str = IDLE
    captured: bool = False

    @property
    def is_selectable(self) -> bool:
        """A piece can be selected only while idle: not mid-move, mid-jump,
        resting through a post-action cooldown, or already captured."""
        return not self.captured and self.state == IDLE
