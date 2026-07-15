from dataclasses import dataclass

from model.position import Position


@dataclass(frozen=True)
class MoveRecord:
    color: str
    kind: str
    frm: Position
    to: Position
    time_ms: int
