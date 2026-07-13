from engine.game_engine import GameEngine
from input.board_mapper import pixel_to_cell


class Controller:
    """Pixel-facing façade over GameEngine: translates pixels to cells and relays them."""

    def __init__(self, engine: GameEngine):
        self.engine = engine

    def click(self, x: int, y: int) -> None:
        pos = pixel_to_cell(x, y, self.engine.state.board)
        self.engine.select(pos)

    def jump(self, x: int, y: int) -> None:
        pos = pixel_to_cell(x, y, self.engine.state.board)
        self.engine.jump(pos)
