from abc import ABC, abstractmethod

from model.board import Board


class Renderer(ABC):

    @abstractmethod
    def render(self, board: Board) -> None:
        ...
