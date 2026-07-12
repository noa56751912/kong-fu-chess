from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    row: int
    col: int

    def offset(self, dr: int, dc: int) -> "Position":
        return Position(self.row + dr, self.col + dc)
