"""End-to-end coverage over a real localhost socket: two real websocket
connections talking to the real asyncio server (net/ws_server.py,
net/game_session.py), not just the in-process bus wiring the unit tests
exercise. No pytest-asyncio dependency - each test is a plain sync function
that drives one asyncio.run() over an async scenario.
"""
import asyncio

import websockets

from net.game_session import GameSession
from net.protocol import ERROR, EVENT, MOVE, SYNC_STATE, decode, encode
from net.ws_server import STARTING_POSITION, handle_connection

RECV_TIMEOUT = 5


async def _recv(ws):
    return decode(await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT))


async def _start_test_server():
    session = GameSession(STARTING_POSITION)

    async def handler(connection):
        await handle_connection(connection, session)

    server = await websockets.serve(handler, "localhost", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port, session


async def _stop_test_server(server, session):
    if session._tick_task is not None:
        session._tick_task.cancel()
    server.close()
    await server.wait_closed()


class TestTwoClientsOverRealSockets:

    async def _run(self):
        server, port, session = await _start_test_server()
        try:
            uri = f"ws://localhost:{port}"
            async with websockets.connect(uri) as ws_a, websockets.connect(uri) as ws_b:
                sync_a = await _recv(ws_a)
                sync_b = await _recv(ws_b)
                assert sync_a["type"] == SYNC_STATE
                assert sync_a["color"] == "w"   # first connection is White
                assert sync_b["color"] == "b"   # second is Black

                # A third connection is rejected outright (rooms/spectating arrive in Phase E).
                async with websockets.connect(uri) as ws_c:
                    rejection = await _recv(ws_c)
                    assert rejection["type"] == ERROR
                    assert rejection["code"] == "SESSION_FULL"

                # A real move, over the real socket, broadcast to both real connections.
                await ws_a.send(encode({"type": MOVE, "from": "e2", "to": "e4"}))
                event_a = await _recv(ws_a)
                event_b = await _recv(ws_b)
                assert event_a["type"] == EVENT
                assert event_a["topic"] == "move.started"
                assert event_a["payload"]["from"] == "e2"
                assert event_a["payload"]["to"] == "e4"
                assert event_a == event_b   # identical broadcast to both players

                # Security: White's own connection cannot move a Black piece,
                # even though it addresses a real square with a real piece on it.
                await ws_a.send(encode({"type": MOVE, "from": "e7", "to": "e5"}))
                error = await _recv(ws_a)
                assert error["type"] == ERROR
                assert error["code"] == "NOT_YOUR_PIECE"

                # Security: a hacked client resending a command for the same
                # piece before it has finished its first move is rejected -
                # only one move.started for d2 goes out, never two.
                await ws_a.send(encode({"type": MOVE, "from": "d2", "to": "d4"}))
                await _recv(ws_a)   # its own move.started broadcast
                await _recv(ws_b)
                await ws_a.send(encode({"type": MOVE, "from": "d2", "to": "d3"}))
                error2 = await _recv(ws_a)
                assert error2["type"] == ERROR
                assert error2["code"] in ("NOT_YOUR_PIECE", "MOTION_IN_PROGRESS")
        finally:
            await _stop_test_server(server, session)

    def test_color_assignment_move_propagation_and_server_authority(self):
        asyncio.run(self._run())
