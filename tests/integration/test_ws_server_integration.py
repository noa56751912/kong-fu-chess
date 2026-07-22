"""End-to-end coverage over a real localhost socket: two real websocket
connections talking to the real asyncio server (net/ws_server.py,
net/game_session.py), not just the in-process bus wiring the unit tests
exercise. No pytest-asyncio dependency - each test is a plain sync function
that drives one asyncio.run() over an async scenario.
"""
import asyncio

import websockets

from net.game_session import GameSession
from net.protocol import ERROR, EVENT, LOGIN, LOGIN_FAIL, LOGIN_OK, MOVE, SYNC_STATE, decode, encode
from net.ws_client import NetworkGameClient
from net.ws_server import STARTING_POSITION, handle_connection
from persistence.db import connect as connect_db
from persistence.user_repo import UserRepo

RECV_TIMEOUT = 5


async def _recv(ws):
    return decode(await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT))


async def _login(ws, username: str, password: str = "hunter2") -> dict:
    await ws.send(encode({"type": LOGIN, "username": username, "password": password}))
    reply = await _recv(ws)
    assert reply["type"] == LOGIN_OK, reply
    return reply


async def _start_test_server():
    user_repo = UserRepo(connect_db(":memory:"))
    session = GameSession(STARTING_POSITION, user_repo)

    async def handler(connection):
        await handle_connection(connection, session, user_repo)

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
                login_a = await _login(ws_a, "alice")
                login_b = await _login(ws_b, "bob")
                assert login_a["new_account"] is True   # first time either username is seen
                assert login_b["new_account"] is True

                sync_a = await _recv(ws_a)
                sync_b = await _recv(ws_b)
                assert sync_a["type"] == SYNC_STATE
                assert sync_a["color"] == "w"   # first connection is White
                assert sync_b["color"] == "b"   # second is Black

                # A third connection still has to log in first, then is
                # rejected (rooms/spectating arrive in Phase E).
                async with websockets.connect(uri) as ws_c:
                    await _login(ws_c, "carol")
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


class TestLoginOverRealSockets:

    async def _run(self):
        server, port, session = await _start_test_server()
        try:
            uri = f"ws://localhost:{port}"
            async with websockets.connect(uri) as ws_a:
                login = await _login(ws_a, "dave", "correct-password")
                assert login["rating"] == 1200   # new accounts start at 1200 ELO

            # A second connection with the same username but the wrong
            # password is rejected and the connection is closed - it never
            # gets far enough to be assigned a color.
            async with websockets.connect(uri) as ws_b:
                await ws_b.send(encode({"type": LOGIN, "username": "dave", "password": "wrong-password"}))
                reply = await _recv(ws_b)
                assert reply["type"] == LOGIN_FAIL

            # The correct password for that same (now-registered) username
            # succeeds and is treated as an existing account, not a new one.
            async with websockets.connect(uri) as ws_c:
                login2 = await _login(ws_c, "dave", "correct-password")
                assert login2["new_account"] is False
                assert login2["rating"] == 1200
        finally:
            await _stop_test_server(server, session)

    def test_wrong_password_is_rejected_and_correct_password_succeeds(self):
        asyncio.run(self._run())


class TestNetworkGameClientLoginAndPlayOverRealSockets:
    """The other tests in this file drive raw protocol messages; this one
    exercises the actual NetworkGameClient class client_main.py uses -
    login(), then the general run() dispatch loop applying a real SYNC_STATE
    and a real EVENT from a genuine second player."""

    async def _run(self):
        server, port, session = await _start_test_server()
        try:
            uri = f"ws://localhost:{port}"
            client = NetworkGameClient()
            await client.connect(uri)
            assert await client.login("erin", "s3cret") is True
            assert client.username == "erin"
            assert client.rating == 1200

            run_task = asyncio.ensure_future(client.run())
            deadline = asyncio.get_event_loop().time() + 5
            while client.board is None and asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(0.02)
            assert client.board is not None
            assert client.color == "w"

            async with websockets.connect(uri) as ws_b:
                await _login(ws_b, "frank")
                await _recv(ws_b)   # frank's own initial SYNC_STATE

                await ws_b.send(encode({"type": MOVE, "from": "e7", "to": "e5"}))
                while not client.pending_moves and asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(0.02)
                # erin's client mirror picked up frank's move.started via the
                # normal EVENT stream, entirely through NetworkGameClient.run().
                assert len(client.pending_moves) == 1
                assert client.pending_moves[0].piece.color == "b"

            run_task.cancel()
            await client.close()
        finally:
            await _stop_test_server(server, session)

    def test_login_then_receive_a_real_opponent_event(self):
        asyncio.run(self._run())
