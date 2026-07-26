import asyncio

import cv2
import numpy as np

from client.widgets import Button, TextInputBox
from net.ws_client import NetworkGameClient

WINDOW_NAME = "Kong Fu Chess - Room"
WINDOW_WIDTH = 380
WINDOW_HEIGHT = 220
BG_COLOR = (35, 35, 35)   # BGR
TEXT_COLOR = (255, 255, 255)
ERROR_COLOR = (80, 80, 220)

QUIT_KEYS = {27, ord('q')}   # ESC, q


def run_room_dialog(client: NetworkGameClient, loop: asyncio.AbstractEventLoop) -> bool:
    """An OpenCV window with a room-id textbox and Create/Join/Cancel
    buttons - the spec's screenshot shows a native-looking Windows popup for
    this, but per the project's no-other-GUI-library constraint this is
    built entirely on plain cv2 primitives, same as home_screen.py.

    Returns True once matched into a room (client.board is populated, ready
    for client_main.py to open the game window), False if cancelled/quit.
    """
    input_box = TextInputBox(20, 60, WINDOW_WIDTH - 40, 34, max_length=12)
    create_button = Button(20, 120, 100, 36, "Create")
    join_button = Button(140, 120, 100, 36, "Join")
    cancel_button = Button(260, 120, 100, 36, "Cancel")
    action = [None]   # "create" | "join" | "cancel", set from the mouse callback

    def mouse_callback(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if input_box.contains(x, y):
            input_box.focused = True
            return
        input_box.focused = False
        if create_button.contains(x, y):
            action[0] = "create"
        elif join_button.contains(x, y):
            action[0] = "join"
        elif cancel_button.contains(x, y):
            action[0] = "cancel"

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, WINDOW_WIDTH, WINDOW_HEIGHT)
    cv2.setMouseCallback(WINDOW_NAME, mouse_callback)

    try:
        while True:
            if client.board is not None:
                return True

            if action[0] == "create":
                action[0] = None
                asyncio.run_coroutine_threadsafe(client.send_create_room(), loop)
            elif action[0] == "join":
                action[0] = None
                if input_box.text:
                    asyncio.run_coroutine_threadsafe(client.send_join_room(input_box.text), loop)
            elif action[0] == "cancel":
                return False

            canvas = np.full((WINDOW_HEIGHT, WINDOW_WIDTH, 3), BG_COLOR, dtype=np.uint8)
            if client.room_id is not None:
                # Per the spec: the generated room id is written at the top
                # of the screen once a room exists. The server doesn't send
                # this connection a SYNC_STATE (client.board stays None,
                # so this dialog doesn't move on to the game window) until
                # a second player actually joins - giving the creator time
                # to actually read and share this before the screen changes.
                cv2.putText(canvas, f"Room: {client.room_id}", (20, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, TEXT_COLOR, 2, cv2.LINE_AA)
                cv2.putText(canvas, "Waiting for opponent to join...", (20, 155),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT_COLOR, 1, cv2.LINE_AA)
            else:
                cv2.putText(canvas, "room name", (20, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, TEXT_COLOR, 1, cv2.LINE_AA)
            input_box.draw(canvas)
            create_button.draw(canvas)
            join_button.draw(canvas)
            cancel_button.draw(canvas)

            if client.last_error is not None and client.last_error.get("code") == "ROOM_NOT_FOUND":
                cv2.putText(canvas, "Room not found.", (20, 190),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, ERROR_COLOR, 1, cv2.LINE_AA)

            cv2.imshow(WINDOW_NAME, canvas)
            key = cv2.waitKey(30) & 0xFF
            input_box.handle_key(key)
            if key in QUIT_KEYS:
                return False
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                return False
    finally:
        cv2.destroyWindow(WINDOW_NAME)
