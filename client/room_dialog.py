import asyncio
import subprocess

import cv2
import numpy as np

from client.widgets import Button, TextInputBox
from net.ws_client import NetworkGameClient

WINDOW_NAME = "Kong Fu Chess - Room"
WINDOW_WIDTH = 380
WINDOW_HEIGHT = 230
BG_COLOR = (35, 35, 35)          # BGR
TEXT_COLOR = (255, 255, 255)
ERROR_COLOR = (80, 80, 220)
CODE_BG = (60, 60, 60)
CODE_BORDER = (0, 215, 255)      # gold, matches ImageView's selection color
CODE_TEXT = (0, 215, 255)

QUIT_KEYS = {27, ord('q')}   # ESC, q


def _copy_to_clipboard(text: str) -> None:
    """Best-effort only, via the stock Windows `clip` utility - no new
    dependency, and never worth crashing the dialog over if it fails."""
    try:
        subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass


def _draw_room_code(canvas, room_id: str) -> None:
    """A visually separated, large room-code box - not sharing a line with
    any other text/control, so it reads clearly at a glance."""
    x, y, w, h = 20, 30, 220, 55
    cv2.rectangle(canvas, (x, y), (x + w, y + h), CODE_BG, -1)
    cv2.rectangle(canvas, (x, y), (x + w, y + h), CODE_BORDER, 2)
    (text_w, text_h), _ = cv2.getTextSize(room_id, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
    cv2.putText(canvas, room_id, (x + (w - text_w) // 2, y + (h + text_h) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, CODE_TEXT, 2, cv2.LINE_AA)


def run_room_dialog(client: NetworkGameClient, loop: asyncio.AbstractEventLoop) -> bool:
    """An OpenCV window with a room-id textbox and Create/Join/Cancel
    buttons - the spec's screenshot shows a native-looking Windows popup for
    this, but per the project's no-other-GUI-library constraint this is
    built entirely on plain cv2 primitives, same as home_screen.py.

    Three views, chosen purely from client state (never a local step
    counter, so a stray extra SYNC_STATE etc. can't desync the UI from
    reality):
      - setup: no room_id yet - textbox + Create/Join/Cancel.
      - waiting: room_id known, client.board still None - the room exists
        but has one player (this one). Shows the code big and alone, plus a
        Copy button and Cancel - nothing here transitions on its own.
      - ready: client.board is populated (an opponent is seated too). Shows
        an explicit Enter Room button - the player decides when to leave
        this screen, never an automatic cutover the instant a sync arrives.

    Returns True once the player clicks Enter Room (ready for client_main.py
    to open the game window), False if cancelled/quit.
    """
    input_box = TextInputBox(20, 60, WINDOW_WIDTH - 40, 34, max_length=12)
    create_button = Button(20, 110, 100, 40, "Create")
    join_button = Button(140, 110, 100, 40, "Join")
    cancel_button_setup = Button(260, 110, 100, 40, "Cancel")

    copy_button = Button(250, 30, 110, 55, "Copy")
    cancel_button_waiting = Button(140, 140, 100, 40, "Cancel")

    enter_button = Button(90, 140, 110, 42, "Enter Room")
    cancel_button_ready = Button(210, 140, 100, 42, "Cancel")

    action = [None]   # "create" | "join" | "cancel" | "copy" | "enter"
    # Remembered locally the moment *this* client asks to join a room - the
    # server never echoes a joiner's own room_id back, so without this the
    # "waiting"/"ready" views would have nothing to display for a joiner.
    joined_room_id = [None]

    def mouse_callback(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if client.board is not None:
            if enter_button.contains(x, y):
                action[0] = "enter"
            elif cancel_button_ready.contains(x, y):
                action[0] = "cancel"
            return
        if client.room_id is not None or joined_room_id[0] is not None:
            if copy_button.contains(x, y):
                action[0] = "copy"
            elif cancel_button_waiting.contains(x, y):
                action[0] = "cancel"
            return
        if input_box.contains(x, y):
            input_box.focused = True
            return
        input_box.focused = False
        if create_button.contains(x, y):
            action[0] = "create"
        elif join_button.contains(x, y):
            action[0] = "join"
        elif cancel_button_setup.contains(x, y):
            action[0] = "cancel"

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, WINDOW_WIDTH, WINDOW_HEIGHT)
    cv2.setMouseCallback(WINDOW_NAME, mouse_callback)

    try:
        while True:
            if action[0] == "cancel":
                # Reset so a later re-entry into this dialog starts fresh at
                # the setup view, instead of immediately showing a stale
                # room code from this abandoned attempt.
                client.room_id = None
                return False
            if action[0] == "enter":
                return True   # client.board is already populated
            if action[0] == "copy":
                action[0] = None
                _copy_to_clipboard(client.room_id or joined_room_id[0] or "")
            elif action[0] == "create":
                action[0] = None
                asyncio.run_coroutine_threadsafe(client.send_create_room(), loop)
            elif action[0] == "join":
                action[0] = None
                if input_box.text:
                    joined_room_id[0] = input_box.text
                    asyncio.run_coroutine_threadsafe(client.send_join_room(input_box.text), loop)

            room_id = client.room_id or joined_room_id[0]
            canvas = np.full((WINDOW_HEIGHT, WINDOW_WIDTH, 3), BG_COLOR, dtype=np.uint8)

            if client.board is not None:
                if room_id is not None:
                    _draw_room_code(canvas, room_id)
                cv2.putText(canvas, "Opponent is here - enter when ready.", (20, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT_COLOR, 1, cv2.LINE_AA)
                enter_button.draw(canvas)
                cancel_button_ready.draw(canvas)
            elif room_id is not None:
                _draw_room_code(canvas, room_id)
                copy_button.draw(canvas)
                cv2.putText(canvas, "Waiting for opponent to join...", (20, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT_COLOR, 1, cv2.LINE_AA)
                cancel_button_waiting.draw(canvas)
            else:
                cv2.putText(canvas, "Enter a room code to join, or create one:", (20, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT_COLOR, 1, cv2.LINE_AA)
                input_box.draw(canvas)
                create_button.draw(canvas)
                join_button.draw(canvas)
                cancel_button_setup.draw(canvas)
                if client.last_error is not None and client.last_error.get("code") == "ROOM_NOT_FOUND":
                    cv2.putText(canvas, "Room not found.", (20, 185),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, ERROR_COLOR, 1, cv2.LINE_AA)

            cv2.imshow(WINDOW_NAME, canvas)
            key = cv2.waitKey(30) & 0xFF
            input_box.handle_key(key)
            if key in QUIT_KEYS:
                return False
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                return False
    finally:
        cv2.destroyWindow(WINDOW_NAME)
