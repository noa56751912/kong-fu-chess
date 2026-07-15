import time

import cv2

from boardio.board_parser import build_board
from engine.game_engine import GameEngine
from input.controller import Controller
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

QUIT_KEYS = {27, ord('q')}  # ESC, q


def _mouse_callback(event, x, y, flags, param):
    controller: Controller
    view: ImageView
    controller, view = param
    if event not in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN):
        return
    bx, by = view.to_board_coords(x, y)
    if event == cv2.EVENT_LBUTTONDOWN:
        controller.click(bx, by)
    elif event == cv2.EVENT_RBUTTONDOWN:
        controller.jump(bx, by)


def main() -> None:
    board = build_board(STARTING_POSITION)
    engine = GameEngine(board)
    controller = Controller(engine)
    view = ImageView()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, board.cols * view.cell_size, board.rows * view.cell_size)
    cv2.setMouseCallback(WINDOW_NAME, _mouse_callback, (controller, view))

    last = time.perf_counter()
    while True:
        now = time.perf_counter()
        dt_ms = (now - last) * 1000
        last = now

        if not engine.game_over:
            engine.wait(dt_ms)

        board = engine.snapshot()
        _, _, win_w, win_h = cv2.getWindowImageRect(WINDOW_NAME)
        window_size = (win_w, win_h) if win_w > 0 and win_h > 0 else None
        view.render(board, engine.now_ms(), engine.in_flight_moves(), engine.state.selection,
                    window_size)

        key = cv2.waitKey(1) & 0xFF
        if key in QUIT_KEYS:
            break
        if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
