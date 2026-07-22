import argparse
import asyncio
import logging
import sqlite3
from typing import Optional

import websockets

from net.game_session import GameSession
from net.protocol import (
    ERROR, JUMP, LOGIN, LOGIN_FAIL, LOGIN_OK, MOVE, ProtocolError, decode, encode,
    square_to_position,
)
from persistence.db import connect as connect_db
from persistence.user_repo import UserRepo

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


async def _dispatch(message: dict, color: str, session: GameSession, connection) -> None:
    rows = session.engine.state.board.rows
    msg_type = message.get("type")

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
        result = session.engine.move(frm, to, requesting_color=color)
        if not result.is_accepted:
            await _send_error(connection, result.reason.upper())

    elif msg_type == JUMP:
        try:
            pos = square_to_position(message["square"], rows)
        except (KeyError, ProtocolError) as exc:
            await _send_error(connection, "BAD_MESSAGE", str(exc))
            return
        session.engine.jump(pos, requesting_color=color)

    else:
        await _send_error(connection, "UNKNOWN_MESSAGE_TYPE", str(msg_type))


async def handle_connection(connection, session: GameSession, user_repo: UserRepo) -> None:
    username = await _await_login(connection, user_repo)
    if username is None:
        return

    color = session.assign_color()
    if color is None:
        await _send_error(connection, "SESSION_FULL", "the game already has two players")
        await connection.close()
        return

    session.add_player(color, connection, username)
    await session.send_sync_state(connection, color)
    session.start_tick_loop()
    logger.info("%s connected as %s", username, color)

    try:
        async for raw in connection:
            try:
                message = decode(raw)
            except ProtocolError as exc:
                await _send_error(connection, "BAD_MESSAGE", str(exc))
                continue
            await _dispatch(message, color, session, connection)
    finally:
        logger.info("%s (%s) disconnected", username, color)


async def serve(host: str = "0.0.0.0", port: int = 8765, db_path: Optional[str] = None) -> None:
    user_repo = UserRepo(await asyncio.to_thread(connect_db, db_path))
    session = GameSession(STARTING_POSITION, user_repo)

    async def handler(connection):
        await handle_connection(connection, session, user_repo)

    async with websockets.serve(handler, host, port):
        logger.info("server listening on %s:%d", host, port)
        await asyncio.Future()  # run forever


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
