from input.board_mapper import CELL_SIZE
from rules.piece_config import IDLE, PIECE_CONFIG
from view.img import Img


class SpriteCache:
    """Loads and caches one Img per (kind, color), scaled to a board cell."""

    def __init__(self, cell_size: int = CELL_SIZE):
        self.cell_size = cell_size
        self._idle: dict[tuple[str, str], Img] = {}

    def idle_sprite(self, kind: str, color: str) -> Img:
        key = (kind, color)
        sprite = self._idle.get(key)
        if sprite is None:
            path = PIECE_CONFIG.get(kind, color, IDLE).frame_paths[0]
            sprite = Img().read(path, size=(self.cell_size, self.cell_size), keep_aspect=True)
            self._idle[key] = sprite
        return sprite
