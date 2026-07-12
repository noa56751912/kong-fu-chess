from model.board import Board
from view.renderer import Renderer


class ImageView(Renderer):
    """Not implemented yet - no rendering library or piece/board assets exist in this project."""

    def render(self, board: Board) -> None:
        raise NotImplementedError("image rendering not yet implemented")
