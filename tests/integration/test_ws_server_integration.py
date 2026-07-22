"""End-to-end coverage over a real localhost socket: real websocket
connections talking to the real asyncio server (net/ws_server.py,
net/game_session.py, matchmaking/queue.py), not just the in-process bus
wiring the unit tests exercise. No pytest-asyncio dependency - each test is
a plain sync function that drives one asyncio.run() over an async scenario.
"""
import asyncio
from unittest.mock import patch

import pytest
import websockets

import net.ws_server as ws_server
import matchmaking.queue as matchmaking_queue
from net.protocol import (
    ERROR, EVENT, LOGIN, LOGIN_FAIL, LOGIN_OK, MATCH_FOUND, MOVE,
    NO_MATCH_FOUND, PLAY, SYNC_STATE, decode, encode,
)
from net.ws_client import NetworkGameClient
from net.ws_server import ServerState, handle_connection
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


async def _login_and_play(ws, username: str, password: str = "hunter2") -> None:
    await _login(ws, username, password)
    await ws.send(encode({"type": PLAY}))


async def _start_test_server():
    user_repo = UserRepo(connect_db(":memory:"))
    server_state = ServerState(user_repo)

    async def handler(connection):
        await handle_connection(connection, server_state)

    server = await websockets.serve(handler, "localhost", 0)
    port = server.sockets[0].getsockname()[1]
    matchmaking_task = asyncio.create_task(ws_server._matchmaking_loop(server_state))
    return server, port, server_state, matchmaking_task


async def _stop_test_server(server, server_state, matchmaking_task):
    matchmaking_task.cancel()
    for session in server_state.sessions.values():
        if session._tick_task is not None:
            session._tick_task.cancel()
    server.close()
    await server.wait_closed()


class TestLoginOverRealSockets:

    async def _run(self):
        server, port, server_state, matchmaking_task = await _start_test_server()
        try:
            uri = f"ws://localhost:{port}"
            async with websockets.connect(uri) as ws_a:
                login = await _login(ws_a, "dave", "correct-password")
                assert login["rating"] == 1200   # new accounts start at 1200 ELO
                assert login["new_account"] is True

            # A second connection with the same username but the wrong
            # password is rejected and the connection is closed.
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
            await _stop_test_server(server, server_state, matchmaking_task)

    def test_wrong_password_is_rejected_and_correct_password_succeeds(self):
        asyncio.run(self._run())


class TestMatchmakingAndGameplayOverRealSockets:

    async def _run(self):
        server, port, server_state, matchmaking_task = await _start_test_server()
        try:
            uri = f"ws://localhost:{port}"
            async with websockets.connect(uri) as ws_a, websockets.connect(uri) as ws_b:
                await _login_and_play(ws_a, "alice")   # first to PLAY
                await _login_and_play(ws_b, "bob")     # second to PLAY

                match_a = await _recv(ws_a)
                match_b = await _recv(ws_b)
                assert match_a["type"] == MATCH_FOUND
                assert match_b["type"] == MATCH_FOUND
                assert match_a["room_id"] == match_b["room_id"]
                assert match_a["color"] == "w"   # first PLAY -> White
                assert match_b["color"] == "b"   # second PLAY -> Black

                sync_a = await _recv(ws_a)
                sync_b = await _recv(ws_b)
                assert sync_a["type"] == SYNC_STATE
                assert sync_a["color"] == "w"
                assert sync_b["color"] == "b"

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
            await _stop_test_server(server, server_state, matchmaking_task)

    def test_matchmaking_color_assignment_move_propagation_and_server_authority(self):
        asyncio.run(self._run())


class TestOutOfRangeRatingsAreNotMatchedOverRealSockets:

    async def _run(self):
        server, port, server_state, matchmaking_task = await _start_test_server()
        try:
            uri = f"ws://localhost:{port}"
            async with websockets.connect(uri) as ws_a, websockets.connect(uri) as ws_b:
                await _login(ws_a, "low_rated")
                await _login(ws_b, "high_rated")
                # Push them more than +-100 apart before either searches.
                await asyncio.to_thread(server_state.user_repo.update_rating, "low_rated", 1000)
                await asyncio.to_thread(server_state.user_repo.update_rating, "high_rated", 1300)

                await ws_a.send(encode({"type": PLAY}))
                await ws_b.send(encode({"type": PLAY}))

                # Give the matchmaking loop several passes' worth of time -
                # nowhere near the 60s timeout - to prove they're genuinely
                # never paired, not just not-yet-paired: no message ever
                # arrives, so waiting for one must time out.
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(ws_a.recv(), timeout=1.5)
        finally:
            await _stop_test_server(server, server_state, matchmaking_task)

    def test_players_far_apart_in_rating_are_never_matched(self):
        asyncio.run(self._run())


class TestMatchmakingTimeoutOverRealSockets:
    """Uses a shrunk timeout/poll interval so this doesn't take 60 real
    seconds - the timing logic itself is already covered precisely (with
    injected clock values) by tests/unit/matchmaking/test_queue.py; this
    only proves the wiring that turns an expired wait into a real NO_MATCH_
    FOUND message actually fires."""

    async def _run(self):
        server, port, server_state, matchmaking_task = await _start_test_server()
        try:
            uri = f"ws://localhost:{port}"
            async with websockets.connect(uri) as ws_a:
                await _login_and_play(ws_a, "lonely")
                reply = await _recv(ws_a)
                assert reply["type"] == NO_MATCH_FOUND
        finally:
            await _stop_test_server(server, server_state, matchmaking_task)

    def test_a_lone_searcher_is_told_no_match_was_found(self):
        with patch.object(matchmaking_queue, "TIMEOUT_S", 0.2), \
             patch.object(ws_server, "MATCHMAKING_INTERVAL_S", 0.1):
            asyncio.run(self._run())


class TestNetworkGameClientLoginPlayAndOpponentEventOverRealSockets:
    """The other tests in this file drive raw protocol messages; this one
    exercises the actual NetworkGameClient class client_main.py uses -
    login(), send_play(), then the general run() dispatch loop applying a
    real MATCH_FOUND/SYNC_STATE/EVENT from a genuine second player."""

    async def _run(self):
        server, port, server_state, matchmaking_task = await _start_test_server()
        try:
            uri = f"ws://localhost:{port}"
            client = NetworkGameClient()
            await client.connect(uri)
            assert await client.login("erin", "s3cret") is True
            assert client.username == "erin"
            assert client.rating == 1200

            run_task = asyncio.ensure_future(client.run())
            await client.send_play()

            async with websockets.connect(uri) as ws_b:
                await _login_and_play(ws_b, "frank")

                loop = asyncio.get_event_loop()
                deadline = loop.time() + 5
                while client.board is None and loop.time() < deadline:
                    await asyncio.sleep(0.02)
                assert client.board is not None
                assert client.room_id is not None

                # Consume frank's own MATCH_FOUND + SYNC_STATE so the socket
                # isn't left holding unread frames before the assertions below.
                await _recv(ws_b)
                await _recv(ws_b)

                await ws_b.send(encode({"type": MOVE, "from": "e7", "to": "e5"}))
                while not client.pending_moves and loop.time() < deadline:
                    await asyncio.sleep(0.02)
                # erin's client mirror picked up frank's move.started via the
                # normal EVENT stream, entirely through NetworkGameClient.run().
                assert len(client.pending_moves) == 1
                assert client.pending_moves[0].piece.color == "b"

            run_task.cancel()
            await client.close()
        finally:
            await _stop_test_server(server, server_state, matchmaking_task)

    def test_login_then_play_then_receive_a_real_opponent_event(self):
        asyncio.run(self._run())
