from dataclasses import dataclass
from enum import Enum

from model.position import Position

WHITE = 'w'
BLACK = 'b'

KING = 'K'
QUEEN = 'Q'
ROOK = 'R'
BISHOP = 'B'
KNIGHT = 'N'
PAWN = 'P'


class PieceState(Enum):
    IDLE = 'idle'
    MOVING = 'moving'
    CAPTURED = 'captured'


@dataclass
class Piece:
    id: int
    color: str
    kind: str
    cell: Position
    state: PieceState = PieceState.IDLE
