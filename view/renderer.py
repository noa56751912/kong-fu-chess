from abc import ABC, abstractmethod
from typing import Iterable, Optional

from model.board import Board
from model.position import Position
from realtime.motion import PendingMove


class Renderer(ABC):

    @abstractmethod
    def render(self, board: Board, now_ms: int, in_flight_moves: Iterable[PendingMove],
               selection: Optional[Position] = None,
               window_size: Optional[tuple[int, int]] = None) -> None:
        ...
