import time

import cv2

from boardio.board_parser import build_board
from engine.game_engine import GameEngine
from input.controller import Controller
from view.image_view import (
    BOTTOM_MARGIN, LEFT_PANEL_WIDTH, RIGHT_PANEL_WIDTH, TOP_MARGIN, WINDOW_NAME, ImageView,
)

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
RESTART_KEY = ord('r')


def _mouse_callback(event, x, y, flags, param):
    # param[0] is a mutable holder so a restart can swap in a fresh Controller
    # without having to re-register the callback.
    controller_holder: list[Controller]
    view: ImageView
    controller_holder, view = param
    if event not in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN):
        return
    bx, by = view.to_board_coords(x, y)
    if event == cv2.EVENT_LBUTTONDOWN:
        controller_holder[0].click(bx, by)
    elif event == cv2.EVENT_RBUTTONDOWN:
        controller_holder[0].jump(bx, by)


def _new_game() -> tuple[GameEngine, Controller]:
    engine = GameEngine(build_board(STARTING_POSITION))
    return engine, Controller(engine)


def main() -> None:
    engine, controller = _new_game()
    view = ImageView()
    controller_holder = [controller]

    board = engine.state.board
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, LEFT_PANEL_WIDTH + board.cols * view.cell_size + RIGHT_PANEL_WIDTH,
                      TOP_MARGIN + board.rows * view.cell_size + BOTTOM_MARGIN)
    cv2.setMouseCallback(WINDOW_NAME, _mouse_callback, (controller_holder, view))

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
                    window_size, engine.state.score, engine.state.moves,
                    engine.game_over, engine.state.winner, engine.selection_targets())

        key = cv2.waitKey(1) & 0xFF
        if key in QUIT_KEYS:
            break
        if key == RESTART_KEY and engine.game_over:
            engine, controller = _new_game()
            controller_holder[0] = controller
        if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
