from input.board_mapper import CELL_SIZE
from rules.piece_config import IDLE, PIECE_CONFIG
from view.img import Img


class SpriteCache:
    """Loads and caches one Img per (kind, color, state, frame index), scaled to a board cell."""

    def __init__(self, cell_size: int = CELL_SIZE):
        self.cell_size = cell_size
        self._cache: dict[tuple[str, str, str, int], Img] = {}

    def sprite(self, kind: str, color: str, state: str, frame_idx: int) -> Img:
        key = (kind, color, state, frame_idx)
        img = self._cache.get(key)
        if img is None:
            path = PIECE_CONFIG.get(kind, color, state).frame_paths[frame_idx]
            img = Img().read(path, size=(self.cell_size, self.cell_size), keep_aspect=True)
            self._cache[key] = img
        return img

    def idle_sprite(self, kind: str, color: str) -> Img:
        return self.sprite(kind, color, IDLE, 0)
