import argparse
import asyncio
import threading
import time
from typing import Optional

import cv2

from auth.login_cli import Credentials, prompt_credentials
from client.home_screen import run_home_screen
from input.board_mapper import pixel_to_cell
from model.position import Position
from net.ws_client import NetworkGameClient
from view.image_view import (
    BOTTOM_MARGIN, LEFT_PANEL_WIDTH, RIGHT_PANEL_WIDTH, TOP_MARGIN, WINDOW_NAME, ImageView,
)

QUIT_KEYS = {27, ord('q')}  # ESC, q
MAX_LOGIN_ATTEMPTS = 3

# Known simplification for this phase: capture flash/beep (wired in Phase 0
# via ImageView.subscribe_to(engine.bus)) isn't hooked up here. That effect's
# timing comes from the *same* clock passed to render() each frame; the local
# offline path (gui_main.py) has one authoritative clock for both, but here
# render() is driven by a wall-clock-derived local_clock_ms owned by this
# loop, while capture events arrive on the network thread - wiring the two
# together correctly is more machinery than the cosmetic payoff is worth
# right now. The move/score/game-over sync itself is unaffected.


class LocalSelection:
    """Purely client-side "which square did I click first" state, for
    highlighting only - never sent to or read from the server. Networked
    play always sends a complete from->to MOVE in one message (see
    net/protocol.py), so this just turns two clicks into that one message,
    the same way GameEngine._handle_selection turns two clicks into one
    scheduled move locally."""

    def __init__(self):
        self.pos: Optional[Position] = None


def _start_network_thread(uri: str, client: NetworkGameClient,
                           credentials: Credentials) -> tuple[asyncio.AbstractEventLoop, threading.Thread, bool]:
    """Runs the asyncio websocket connection - including the LOGIN handshake,
    which must happen before run()'s general dispatch loop starts consuming
    messages - on a dedicated background thread, so the main thread stays
    free for OpenCV's synchronous render/event loop. The two never share the
    event loop, only NetworkGameClient's plain-data attributes (safe under
    the GIL for the simple reads/writes both sides do). Returns once login
    has succeeded or failed (not once the whole session ends)."""
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    failure: list[BaseException] = []
    login_result: list[bool] = []

    async def runner():
        try:
            await client.connect(uri)
            login_result.append(await client.login(credentials.username, credentials.password))
        except Exception as exc:
            failure.append(exc)
            return
        finally:
            ready.set()
        if login_result and login_result[0]:
            await client.run()

    def thread_main():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner())

    thread = threading.Thread(target=thread_main, daemon=True)
    thread.start()
    ready.wait(timeout=15)
    if failure:
        raise failure[0]
    return loop, thread, bool(login_result and login_result[0])


def _handle_click(client: NetworkGameClient, selection: LocalSelection, pos: Position,
                   loop: asyncio.AbstractEventLoop) -> None:
    board = client.board
    piece_at_target = board.piece_at(pos)

    if selection.pos is None:
        if piece_at_target is not None and piece_at_target.color == client.color and piece_at_target.is_selectable:
            selection.pos = pos
        return

    if pos == selection.pos:
        selection.pos = None   # clicking the same square again deselects
        return

    if piece_at_target is not None and piece_at_target.color == client.color:
        selection.pos = pos if piece_at_target.is_selectable else None
        return

    frm = selection.pos
    selection.pos = None
    # This is a request, not a write: the server independently re-resolves
    # frm's actual color and cooldown state before ever scheduling anything.
    asyncio.run_coroutine_threadsafe(client.send_move(frm, pos), loop)


def _mouse_callback(event, x, y, flags, param):
    client, selection, view, loop = param
    if event not in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN):
        return
    if client.board is None:
        return
    bx, by = view.to_board_coords(x, y)
    pos = pixel_to_cell(bx, by, client.board)
    if pos is None:
        return
    if event == cv2.EVENT_LBUTTONDOWN:
        _handle_click(client, selection, pos, loop)
    elif event == cv2.EVENT_RBUTTONDOWN:
        asyncio.run_coroutine_threadsafe(client.send_jump(pos), loop)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kong Fu Chess networked client")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    uri = f"ws://{args.host}:{args.port}"
    client = loop = thread = None
    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        credentials = prompt_credentials()
        client = NetworkGameClient()
        loop, thread, logged_in = _start_network_thread(uri, client, credentials)
        if logged_in:
            break
        reason = client.last_error.get("reason") if client.last_error else None
        print(f"Login failed{f' ({reason})' if reason else ''}.")
    else:
        print("Too many failed login attempts.")
        return

    print(f"Logged in as {client.username} (rating {client.rating})")

    if not run_home_screen(client, loop):
        asyncio.run_coroutine_threadsafe(client.close(), loop)
        return
    if client.board is None:
        print("Matched, but did not receive the initial game state.")
        return

    view = ImageView()
    selection = LocalSelection()

    board = client.board
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, LEFT_PANEL_WIDTH + board.cols * view.cell_size + RIGHT_PANEL_WIDTH,
                      TOP_MARGIN + board.rows * view.cell_size + BOTTOM_MARGIN)
    cv2.setMouseCallback(WINDOW_NAME, _mouse_callback, (client, selection, view, loop))

    # A wall-clock-derived render clock, re-anchored to the server's own
    # clock_ms every time a fresh SYNC_STATE arrives (sync_version changes) -
    # bounding drift without needing a clock reading on every single event.
    local_clock_ms = float(client.clock_ms)
    last_sync_version = client.sync_version
    last = time.perf_counter()

    while True:
        now = time.perf_counter()
        dt_ms = (now - last) * 1000
        last = now

        if client.sync_version != last_sync_version:
            local_clock_ms = float(client.clock_ms)
            last_sync_version = client.sync_version
        else:
            local_clock_ms += dt_ms

        _, _, win_w, win_h = cv2.getWindowImageRect(WINDOW_NAME)
        window_size = (win_w, win_h) if win_w > 0 and win_h > 0 else None
        disconnect_notice = None
        if client.opponent_disconnect_username is not None:
            disconnect_notice = (client.opponent_disconnect_username, client.opponent_disconnect_countdown_s)
        # selection_targets is deliberately omitted (None): the server is the
        # sole authority on legal destinations, and duplicating RuleEngine
        # client-side just to highlight them isn't worth it for this phase.
        view.render(client.board, local_clock_ms, client.pending_moves, selection.pos,
                    window_size, client.score, client.moves, client.game_over, client.winner, None,
                    disconnect_notice)

        key = cv2.waitKey(1) & 0xFF
        if key in QUIT_KEYS:
            break
        if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            break
        if not thread.is_alive():
            break

    asyncio.run_coroutine_threadsafe(client.close(), loop)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
