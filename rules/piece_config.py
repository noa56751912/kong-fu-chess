import json
import pathlib
from dataclasses import dataclass

ASSET_ROOT = pathlib.Path(__file__).resolve().parent.parent / "assets" / "pieces_classic"

IDLE = "idle"
MOVE = "move"
JUMP = "jump"


@dataclass(frozen=True)
class StateConfig:
    speed_m_per_sec: float
    next_state: str
    frames_per_sec: int
    is_loop: bool
    frame_paths: tuple[pathlib.Path, ...]


def _folder_code(kind: str, color: str) -> str:
    return f"{kind}{color.upper()}"


def _state_dir(kind: str, color: str, state: str) -> pathlib.Path:
    return ASSET_ROOT / _folder_code(kind, color) / "states" / state


def _load_state_config(kind: str, color: str, state: str) -> StateConfig:
    state_dir = _state_dir(kind, color, state)
    raw = json.loads((state_dir / "config.json").read_text())
    frame_paths = tuple(sorted(
        (state_dir / "sprites").glob("*.png"),
        key=lambda p: int(p.stem),
    ))
    return StateConfig(
        speed_m_per_sec=raw["physics"]["speed_m_per_sec"],
        next_state=raw["physics"]["next_state_when_finished"],
        frames_per_sec=raw["graphics"]["frames_per_sec"],
        is_loop=raw["graphics"]["is_loop"],
        frame_paths=frame_paths,
    )


class PieceConfigLoader:
    """Parses each (kind, color, state) config.json once and caches the result.

    This is the single source both the engine (physics/next-state, for real
    cooldown enforcement) and the view (graphics/sprite frames, for animation)
    read from, so the two can never drift apart.
    """

    def __init__(self):
        self._cache: dict[tuple[str, str, str], StateConfig] = {}

    def get(self, kind: str, color: str, state: str) -> StateConfig:
        key = (kind, color, state)
        cfg = self._cache.get(key)
        if cfg is None:
            cfg = _load_state_config(kind, color, state)
            self._cache[key] = cfg
        return cfg


PIECE_CONFIG = PieceConfigLoader()
