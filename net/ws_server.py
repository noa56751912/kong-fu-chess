import argparse
import asyncio
import logging
import sqlite3
from logging.handlers import RotatingFileHandler
from typing import Optional

import websockets

from matchmaking.queue import MatchmakingQueue, Waiting
from model.piece import BLACK, WHITE
from net.game_session import GameSession
from net.protocol import (
    CANCEL_SEARCH, CREATE_ROOM, ERROR, JOIN_ROOM, JUMP, LOGIN, LOGIN_FAIL,
    LOGIN_OK, MATCH_FOUND, MOVE, NO_MATCH_FOUND, PLAY, ROOM_CREATED,
    ProtocolError, decode, encode, square_to_position,
)
from persistence.db import connect as connect_db
from persistence.user_repo import DEFAULT_RATING, UserRepo
from rooms.room_manager import RoomManager

logger = logging.getLogger(__name__)

# How often the matchmaking loop checks for pairings/timeouts. A plain
# await asyncio.sleep() between passes - not a blocking wait - so it costs
# nothing else running on the server.
MATCHMAKING_INTERVAL_S = 1


class ConnectionContext:
    """Per-connection state that outlives any single incoming message: which
    username this connection logged in as, and - once matched or joined into
    a room - which GameSession/color/spectator status it belongs to. A
    connection with session=None is still in the lobby (only PLAY/
    CANCEL_SEARCH/CREATE_ROOM/JOIN_ROOM are valid); once session is set,
    MOVE/JUMP are dispatched to it (rejected outright if is_spectator)."""

    def __init__(self, connection, username: str):
        self.connection = connection
        self.username = username
        self.session: Optional[GameSession] = None
        self.color: Optional[str] = None
        self.is_spectator: bool = False


class ServerState:
    def __init__(self, user_repo: UserRepo):
        self.user_repo = user_repo
        self.queue = MatchmakingQueue()
        self.sessions: dict[str, GameSession] = {}
        self.rooms = RoomManager(self.sessions, user_repo)
        # username -> (session, color) for every player currently in an
        # in-progress game, so a fresh LOGIN for that username can be
        # recognized as a reconnect instead of a normal lobby entry. Left in
        # place (not deleted) once a game ends - handle_connection checks
        # session.engine.state.game_over at lookup time, so a stale entry is
        # simply ignored rather than needing active cleanup. Spectators are
        # deliberately never registered here - a disconnected spectator just
        # re-enters the lobby on reconnect rather than resuming as a spectator.
        self.active_players: dict[str, tuple[GameSession, str]] = {}


async def _send_error(connection, code: str, message: str = "") -> None:
    await connection.send(encode({"type": ERROR, "code": code, "message": message}))


async def _await_login(connection, user_repo: UserRepo) -> Optional[str]:
    """The required first message on every connection. Returns the logged-in
    username, or None if login failed/never happened (the connection is
    already closed in that case - the caller has nothing further to do)."""
    try:
        raw = await connection.recv()
    except websockets.ConnectionClosed:
        return None

    try:
        message = decode(raw)
    except ProtocolError as exc:
        await _send_error(connection, "BAD_MESSAGE", str(exc))
        await connection.close()
        return None

    if message.get("type") != LOGIN:
        await _send_error(connection, "LOGIN_REQUIRED", "the first message on a connection must be LOGIN")
        await connection.close()
        return None

    username = message.get("username")
    password = message.get("password")
    if not username or not password:
        await _send_error(connection, "BAD_MESSAGE", "username and password are required")
        await connection.close()
        return None

    user = await asyncio.to_thread(user_repo.get_user, username)
    is_new_account = False
    if user is None:
        try:
            user = await asyncio.to_thread(user_repo.create_user, username, password)
            is_new_account = True
        except sqlite3.IntegrityError:
            # Another connection registered this exact username in the
            # instant between our get_user and create_user calls - fall
            # back to treating it as an existing-user login.
            user = await asyncio.to_thread(user_repo.get_user, username)
    if not is_new_account:
        if not await asyncio.to_thread(user_repo.verify_password, username, password):
            await connection.send(encode({"type": LOGIN_FAIL, "reason": "bad_password"}))
            await connection.close()
            return None

    await connection.send(encode({
        "type": LOGIN_OK, "rating": user.elo_rating, "new_account": is_new_account,
    }))
    logger.info("%s logged in%s", username, " (new account)" if is_new_account else "")
    return username


async def _seat_player(session: GameSession, color: str, context: ConnectionContext,
                        server_state: ServerState) -> None:
    """Shared by matchmaking and rooms: registers a connection as one of a
    session's two actual players (as opposed to add_spectator) and sends it
    the session's current full state."""
    context.session = session
    context.color = color
    session.add_player(color, context.connection, context.username)
    server_state.active_players[context.username] = (session, color)
    await session.send_sync_state(context.connection, color)


async def _dispatch_lobby(message: dict, msg_type: Optional[str], context: ConnectionContext,
                           server_state: ServerState) -> None:
    if msg_type == PLAY:
        user = await asyncio.to_thread(server_state.user_repo.get_user, context.username)
        rating = user.elo_rating if user is not None else DEFAULT_RATING
        server_state.queue.add(context, rating)

    elif msg_type == CANCEL_SEARCH:
        server_state.queue.remove_connection(context.connection)

    elif msg_type == CREATE_ROOM:
        room_id, session = server_state.rooms.create_room()
        session.start_tick_loop()
        await context.connection.send(encode({"type": ROOM_CREATED, "room_id": room_id}))
        await _seat_player(session, WHITE, context, server_state)
        logger.info("%s created room %s", context.username, room_id)

    elif msg_type == JOIN_ROOM:
        room_id = message.get("room_id")
        session = server_state.rooms.get_room(room_id) if room_id else None
        if session is None:
            await _send_error(context.connection, "ROOM_NOT_FOUND", str(room_id))
            return
        color = session.assign_color()
        if color is not None:
            await _seat_player(session, color, context, server_state)
            logger.info("%s joined room %s as %s", context.username, room_id, color)
        else:
            context.session = session
            context.is_spectator = True
            session.add_spectator(context.connection)
            await session.send_sync_state(context.connection, None)
            logger.info("%s joined room %s as a spectator", context.username, room_id)

    else:
        await _send_error(context.connection, "UNKNOWN_MESSAGE_TYPE", str(msg_type))


async def _dispatch_in_game(message: dict, msg_type: Optional[str], context: ConnectionContext) -> None:
    connection = context.connection

    if context.is_spectator:
        if msg_type in (MOVE, JUMP):
            await _send_error(connection, "SPECTATOR_CANNOT_MOVE", "spectators cannot move pieces")
        else:
            await _send_error(connection, "UNKNOWN_MESSAGE_TYPE", str(msg_type))
        return

    session = context.session
    rows = session.engine.state.board.rows

    if msg_type == MOVE:
        try:
            frm = square_to_position(message["from"], rows)
            to = square_to_position(message["to"], rows)
        except (KeyError, ProtocolError) as exc:
            await _send_error(connection, "BAD_MESSAGE", str(exc))
            return
        # The server never trusts a client-declared color or piece - it
        # always resolves whose piece frm actually holds and checks that
        # against the connection's own assigned color.
        result = session.engine.move(frm, to, requesting_color=context.color)
        if not result.is_accepted:
            await _send_error(connection, result.reason.upper())

    elif msg_type == JUMP:
        try:
            pos = square_to_position(message["square"], rows)
        except (KeyError, ProtocolError) as exc:
            await _send_error(connection, "BAD_MESSAGE", str(exc))
            return
        session.engine.jump(pos, requesting_color=context.color)

    else:
        await _send_error(connection, "UNKNOWN_MESSAGE_TYPE", str(msg_type))


async def handle_connection(connection, server_state: ServerState) -> None:
    username = await _await_login(connection, server_state.user_repo)
    if username is None:
        return

    context = ConnectionContext(connection, username)

    reconnect_info = server_state.active_players.get(username)
    if reconnect_info is not None and not reconnect_info[0].engine.state.game_over:
        session, color = reconnect_info
        context.session = session
        context.color = color
        await session.on_reconnect(color, connection)
        logger.info("%s reconnected as %s", username, color)
    else:
        logger.info("%s connected, entering lobby", username)

    try:
        async for raw in connection:
            logger.debug("recv from %s: %s", username, raw)
            try:
                message = decode(raw)
            except ProtocolError as exc:
                await _send_error(connection, "BAD_MESSAGE", str(exc))
                continue
            msg_type = message.get("type")
            if context.session is None:
                await _dispatch_lobby(message, msg_type, context, server_state)
            else:
                await _dispatch_in_game(message, msg_type, context)
    finally:
        server_state.queue.remove_connection(connection)
        if context.session is not None:
            if context.is_spectator:
                context.session.remove_spectator(connection)
            else:
                context.session.on_disconnect(context.color)
        logger.info("%s disconnected", username)


async def _start_matched_game(pair: tuple[Waiting, Waiting], server_state: ServerState) -> None:
    waiting_a, waiting_b = pair
    # A matched game and a manually-created room are the same underlying
    # concept (a fresh GameSession keyed by a random id in
    # server_state.sessions) - reuses RoomManager.create_room() rather than
    # duplicating that bookkeeping here with a second random-id scheme.
    match_id, session = server_state.rooms.create_room()
    session.start_tick_loop()

    for color, waiting in ((WHITE, waiting_a), (BLACK, waiting_b)):
        try:
            await waiting.context.connection.send(encode({
                "type": MATCH_FOUND, "room_id": match_id, "color": color,
            }))
            await _seat_player(session, color, waiting.context, server_state)
        except Exception:
            # The other player, if still connected, will see this one
            # time out via Phase D's disconnect handling once it's wired up.
            logger.exception("failed to notify a matched player")
    logger.info("matched %s (w) vs %s (b) as %s", waiting_a.context.username, waiting_b.context.username, match_id)


async def _expire_waiting(server_state: ServerState) -> None:
    for waiting in server_state.queue.expire():
        try:
            await waiting.context.connection.send(encode({"type": NO_MATCH_FOUND}))
        except Exception:
            logger.exception("failed to notify a timed-out matchmaking search")


async def _matchmaking_loop(server_state: ServerState) -> None:
    while True:
        await asyncio.sleep(MATCHMAKING_INTERVAL_S)
        while True:
            pair = server_state.queue.find_match()
            if pair is None:
                break
            await _start_matched_game(pair, server_state)
        await _expire_waiting(server_state)


async def serve(host: str = "0.0.0.0", port: int = 8765, db_path: Optional[str] = None) -> None:
    user_repo = UserRepo(await asyncio.to_thread(connect_db, db_path))
    server_state = ServerState(user_repo)

    async def handler(connection):
        await handle_connection(connection, server_state)

    matchmaking_task = asyncio.create_task(_matchmaking_loop(server_state))
    try:
        async with websockets.serve(handler, host, port):
            logger.info("server listening on %s:%d", host, port)
            await asyncio.Future()  # run forever
    finally:
        matchmaking_task.cancel()


def _configure_logging(log_path: str) -> None:
    """Console (INFO+) for interactive use, plus a rotating server.log (DEBUG+,
    so it also captures every websocket message logged at DEBUG level) for
    later troubleshooting - per-connection/session activity and every bus
    event, per the spec's server- and client-side logging requirement."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    root.addHandler(console)

    file_handler = RotatingFileHandler(log_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(file_handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kong Fu Chess WebSocket server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--log-path", default="server.log")
    args = parser.parse_args()
    _configure_logging(args.log_path)
    asyncio.run(serve(args.host, args.port, args.db_path))


if __name__ == "__main__":
    main()
