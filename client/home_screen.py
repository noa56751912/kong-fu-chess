import asyncio

import cv2
import numpy as np

from client.widgets import Button
from net.ws_client import NetworkGameClient

WINDOW_NAME = "Kong Fu Chess - Home"
WINDOW_WIDTH = 420
WINDOW_HEIGHT = 260
BG_COLOR = (35, 35, 35)   # BGR
TEXT_COLOR = (255, 255, 255)
NO_MATCH_COLOR = (80, 80, 220)

QUIT_KEYS = {27, ord('q')}   # ESC, q


def _mouse_callback(event, x, y, flags, param):
    button, click_holder = param
    if event == cv2.EVENT_LBUTTONDOWN and button.enabled and button.contains(x, y):
        click_holder[0] = True


def run_home_screen(client: NetworkGameClient, loop: asyncio.AbstractEventLoop) -> bool:
    """Blocks on the main thread (via cv2.waitKey, same pattern gui_main.py's
    render loop uses) until the player is matched or quits. An ordinary
    OpenCV window with a hand-drawn button - per the project's no-other-GUI-
    library constraint, this is not tkinter or a native dialog.

    Returns True once matched (client.board is populated, ready for
    client_main.py to open the game window) or False if the player quit.
    """
    play_button = Button(WINDOW_WIDTH // 2 - 60, 140, 120, 40, "Play")
    click_holder = [False]

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, WINDOW_WIDTH, WINDOW_HEIGHT)
    cv2.setMouseCallback(WINDOW_NAME, _mouse_callback, (play_button, click_holder))

    try:
        while True:
            if client.board is not None:
                return True

            if click_holder[0]:
                click_holder[0] = False
                if not client.searching:
                    asyncio.run_coroutine_threadsafe(client.send_play(), loop)

            canvas = np.full((WINDOW_HEIGHT, WINDOW_WIDTH, 3), BG_COLOR, dtype=np.uint8)
            cv2.putText(canvas, f"Logged in as {client.username}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEXT_COLOR, 1, cv2.LINE_AA)
            cv2.putText(canvas, f"Rating: {client.rating}", (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEXT_COLOR, 1, cv2.LINE_AA)

            play_button.enabled = not client.searching
            play_button.label = "Searching..." if client.searching else "Play"
            play_button.draw(canvas)

            if client.no_match_found:
                cv2.putText(canvas, "Could not find a match. Try again.", (20, 210),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, NO_MATCH_COLOR, 1, cv2.LINE_AA)

            cv2.imshow(WINDOW_NAME, canvas)
            key = cv2.waitKey(30) & 0xFF
            if key in QUIT_KEYS:
                return False
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                return False
    finally:
        cv2.destroyWindow(WINDOW_NAME)
