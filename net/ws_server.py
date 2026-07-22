import argparse
import asyncio
import logging
import secrets
import sqlite3
from typing import Optional

import websockets

from matchmaking.queue import MatchmakingQueue, Waiting
from model.piece import BLACK, WHITE
from net.game_session import GameSession
from net.protocol import (
    CANCEL_SEARCH, ERROR, JUMP, LOGIN, LOGIN_FAIL, LOGIN_OK, MATCH_FOUND, MOVE,
    NO_MATCH_FOUND, PLAY, ProtocolError, decode, encode, square_to_position,
)
from persistence.db import connect as connect_db
from persistence.user_repo import DEFAULT_RATING, UserRepo

logger = logging.getLogger(__name__)

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

# How often the matchmaking loop checks for pairings/timeouts. A plain
# await asyncio.sleep() between passes - not a blocking wait - so it costs
# nothing else running on the server.
MATCHMAKING_INTERVAL_S = 1


class ConnectionContext:
    """Per-connection state that outlives any single incoming message: which
    username this connection logged in as, and - once matched or joined into
    a room - which GameSession and color it belongs to. A connection with
    session=None is still in the lobby (only PLAY/CANCEL_SEARCH/room commands
    are valid); once session is set, MOVE/JUMP are dispatched to it."""

    def __init__(self, connection, username: str):
        self.connection = connection
        self.username = username
        self.session: Optional[GameSession] = None
        self.color: Optional[str] = None


class ServerState:
    def __init__(self, user_repo: UserRepo):
        self.user_repo = user_repo
        self.queue = MatchmakingQueue()
        self.sessions: dict[str, GameSession] = {}
        # username -> (session, color) for every player currently in an
        # in-progress game, so a fresh LOGIN for that username can be
        # recognized as a reconnect instead of a normal lobby entry. Left in
        # place (not deleted) once a game ends - handle_connection checks
        # session.engine.state.game_over at lookup time, so a stale entry is
        # simply ignored rather than needing active cleanup.
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


async def _dispatch_lobby(msg_type: Optional[str], context: ConnectionContext, server_state: ServerState) -> None:
    if msg_type == PLAY:
        user = await asyncio.to_thread(server_state.user_repo.get_user, context.username)
        rating = user.elo_rating if user is not None else DEFAULT_RATING
        server_state.queue.add(context, rating)
    elif msg_type == CANCEL_SEARCH:
        server_state.queue.remove_connection(context.connection)
    else:
        await _send_error(context.connection, "UNKNOWN_MESSAGE_TYPE", str(msg_type))


async def _dispatch_in_game(message: dict, msg_type: Optional[str], context: ConnectionContext) -> None:
    session = context.session
    rows = session.engine.state.board.rows
    connection = context.connection

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
            try:
                message = decode(raw)
            except ProtocolError as exc:
                await _send_error(connection, "BAD_MESSAGE", str(exc))
                continue
            msg_type = message.get("type")
            if context.session is None:
                await _dispatch_lobby(msg_type, context, server_state)
            else:
                await _dispatch_in_game(message, msg_type, context)
    finally:
        server_state.queue.remove_connection(connection)
        if context.session is not None:
            context.session.on_disconnect(context.color)
        logger.info("%s disconnected", username)


async def _start_matched_game(pair: tuple[Waiting, Waiting], server_state: ServerState) -> None:
    waiting_a, waiting_b = pair
    session = GameSession(STARTING_POSITION, server_state.user_repo)
    match_id = secrets.token_hex(3)
    server_state.sessions[match_id] = session

    for color, waiting in ((WHITE, waiting_a), (BLACK, waiting_b)):
        waiting.context.session = session
        waiting.context.color = color
        session.add_player(color, waiting.context.connection, waiting.context.username)
        server_state.active_players[waiting.context.username] = (session, color)
    session.start_tick_loop()

    for color, waiting in ((WHITE, waiting_a), (BLACK, waiting_b)):
        try:
            await waiting.context.connection.send(encode({
                "type": MATCH_FOUND, "room_id": match_id, "color": color,
            }))
            await session.send_sync_state(waiting.context.connection, color)
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


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Kong Fu Chess WebSocket server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()
    asyncio.run(serve(args.host, args.port, args.db_path))


if __name__ == "__main__":
    main()
