import cv2

from boardio.board_parser import build_board
from engine.game_engine import GameEngine
from view.image_view import WINDOW_NAME, ImageView

STARTING_POSITION = [
    "bR bN bB bQ bK bB bN bR".split(),
    "bP bP bP bP bP bP bP bP".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    "wP wP wP wP wP wP wP wP".split(),
    "wR wN wB wQ wK wB wN wR".split(),
]


def main() -> None:
    board = build_board(STARTING_POSITION)
    engine = GameEngine(board)
    view = ImageView()

    view.render(engine.snapshot())
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
