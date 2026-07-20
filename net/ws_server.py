import argparse
import asyncio
import logging

import websockets

from net.game_session import GameSession
from net.protocol import ERROR, JUMP, MOVE, ProtocolError, decode, encode, square_to_position

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


async def handle_connection(connection, session: GameSession) -> None:
    color = session.assign_color()
    if color is None:
        await _send_error(connection, "SESSION_FULL", "the game already has two players")
        await connection.close()
        return

    session.add_player(color, connection)
    await session.send_sync_state(connection, color)
    session.start_tick_loop()
    logger.info("player connected as %s", color)

    try:
        async for raw in connection:
            try:
                message = decode(raw)
            except ProtocolError as exc:
                await _send_error(connection, "BAD_MESSAGE", str(exc))
                continue
            await _dispatch(message, color, session, connection)
    finally:
        logger.info("player %s disconnected", color)


async def serve(host: str = "0.0.0.0", port: int = 8765) -> None:
    session = GameSession(STARTING_POSITION)

    async def handler(connection):
        await handle_connection(connection, session)

    async with websockets.serve(handler, host, port):
        logger.info("server listening on %s:%d", host, port)
        await asyncio.Future()  # run forever


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Kong Fu Chess WebSocket server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(serve(args.host, args.port))


if __name__ == "__main__":
    main()
