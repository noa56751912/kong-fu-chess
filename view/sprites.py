import pathlib

from input.board_mapper import CELL_SIZE
from view.img import Img

ASSET_ROOT = pathlib.Path(__file__).resolve().parent.parent / "assets" / "pieces2"


def _folder_code(kind: str, color: str) -> str:
    return f"{kind}{color.upper()}"


def _sprite_path(kind: str, color: str, state: str, frame: int) -> pathlib.Path:
    return ASSET_ROOT / _folder_code(kind, color) / "states" / state / "sprites" / f"{frame}.png"


class SpriteCache:
    """Loads and caches one Img per (kind, color), scaled to a board cell."""

    def __init__(self, cell_size: int = CELL_SIZE):
        self.cell_size = cell_size
        self._idle: dict[tuple[str, str], Img] = {}

    def idle_sprite(self, kind: str, color: str) -> Img:
        key = (kind, color)
        sprite = self._idle.get(key)
        if sprite is None:
            path = _sprite_path(kind, color, "idle", 1)
            sprite = Img().read(path, size=(self.cell_size, self.cell_size), keep_aspect=True)
            self._idle[key] = sprite
        return sprite
