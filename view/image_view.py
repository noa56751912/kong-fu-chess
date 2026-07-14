import cv2
import numpy as np

from input.board_mapper import CELL_SIZE, cell_to_pixel
from model.board import Board
from view.img import Img
from view.renderer import Renderer
from view.sprites import SpriteCache

LIGHT_SQUARE = (210, 238, 238)  # BGR
DARK_SQUARE = (86, 150, 118)  # BGR

WINDOW_NAME = "Image"  # matches Img.show()'s hardcoded title


class ImageView(Renderer):

    def __init__(self, cell_size: int = CELL_SIZE, sprite_cache: SpriteCache | None = None):
        self.cell_size = cell_size
        self.sprites = sprite_cache or SpriteCache(cell_size)
        self._background: Img | None = None

    def _build_background(self, rows: int, cols: int) -> Img:
        # BGRA (not BGR): Img.draw_on() only alpha-blends a sprite when the
        # destination already has 4 channels: against a 3-channel canvas it
        # silently drops the sprite's alpha and pastes it opaquely instead.
        canvas = np.empty((rows * self.cell_size, cols * self.cell_size, 4), dtype=np.uint8)
        canvas[..., 3] = 255
        for row in range(rows):
            for col in range(cols):
                color = LIGHT_SQUARE if (row + col) % 2 == 0 else DARK_SQUARE
                x, y = col * self.cell_size, row * self.cell_size
                canvas[y:y + self.cell_size, x:x + self.cell_size, :3] = color
        background = Img()
        background.img = canvas
        return background

    def _ensure_background(self, board: Board) -> Img:
        if self._background is None:
            self._background = self._build_background(board.rows, board.cols)
        return self._background

    def render(self, board: Board) -> None:
        background = self._ensure_background(board)
        frame = Img()
        frame.img = background.img.copy()
        for pos, piece in board:
            sprite = self.sprites.idle_sprite(piece.kind, piece.color)
            x, y = cell_to_pixel(pos, self.cell_size)
            sprite.draw_on(frame, x, y)
        cv2.imshow(WINDOW_NAME, cv2.cvtColor(frame.img, cv2.COLOR_BGRA2BGR))
