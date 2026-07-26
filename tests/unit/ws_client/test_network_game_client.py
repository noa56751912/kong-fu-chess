import sys
import threading

from engine.game_engine import GameEngine
from model.board import Board
from model.piece import BLACK, KING, KNIGHT, ROOK, WHITE
from model.position import Position
from net.bus_bridge import BusBridge
from net.protocol import SYNC_STATE, decode, encode, serialize_board
from net.ws_client import NetworkGameClient
from realtime.motion import jump_duration_ms, move_duration_ms


def make_server(rows, cols):
    board = Board(rows, cols)
    engine = GameEngine(board)
    sent = []
    BusBridge(engine.bus, rows, sent.append)
    return board, engine, sent


def make_client_synced(board, color=None):
    client = NetworkGameClient()
    initial = encode({
        "type": SYNC_STATE, "color": color, "board": serialize_board(board),
        "score": {"w": 0, "b": 0}, "moves": [], "clock_ms": 0,
        "game_over": False, "winner": None,
    })
    client.handle_message(decode(initial))
    return client


def deliver(client, sent):
    for raw in sent:
        client.handle_message(decode(raw))


def deliver_and_settle(client, sent):
    """Like deliver(), but also flushes every buffered arrival/capture (see
    NetworkGameClient.tick) - use this whenever a test wants the board to
    reflect a move that has actually finished, not just been announced."""
    deliver(client, sent)
    client.tick(float("inf"))


class TestNetworkGameClientMirrorsSimpleMove:

    def test_board_position_matches_server_after_arrival(self):
        board, engine, sent = make_server(3, 3)
        rook = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        client = make_client_synced(board, color=WHITE)

        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        engine.wait(move_duration_ms(ROOK, WHITE, 2))
        deliver_and_settle(client, sent)

        assert client.color == WHITE
        assert client.board.piece_at(Position(0, 2)).id == rook.id
        assert client.board.is_empty(Position(0, 0))
        assert client.pending_moves == []

    def test_in_flight_position_is_interpolatable_mid_move(self):
        board, engine, sent = make_server(3, 3)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        client = make_client_synced(board)

        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        deliver(client, sent)

        assert len(client.pending_moves) == 1
        pm = client.pending_moves[0]
        assert pm.frm == Position(0, 0)
        assert pm.to == Position(0, 2)
        assert client.board.is_empty(Position(0, 0))   # vacated immediately, same as server

    def test_arrival_does_not_jump_ahead_of_this_clients_own_animation(self):
        # The whole point of buffering: move.arrived is delivered (the
        # server has already resolved it) but this client's own render
        # clock hasn't reached the move's arrive_time yet - the piece must
        # still be reported as in flight (still interpolating, not yet
        # snapped to its destination) until tick() catches up.
        board, engine, sent = make_server(3, 3)
        rook = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        client = make_client_synced(board, color=WHITE)

        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        arrive_time = move_duration_ms(ROOK, WHITE, 2)
        engine.wait(arrive_time)
        deliver(client, sent)   # move.arrived has been delivered...

        # ...but this client's own clock is still short of arrive_time, so
        # nothing should have snapped yet.
        client.tick(arrive_time - 1)
        assert len(client.pending_moves) == 1
        assert client.board.piece_at(Position(0, 2)) is None

        # Only once the local clock actually reaches arrive_time does the
        # buffered arrival apply.
        client.tick(arrive_time)
        assert client.pending_moves == []
        assert client.board.piece_at(Position(0, 2)).id == rook.id


class TestNetworkGameClientMirrorsCapture:

    def test_score_and_board_updated_on_capture(self):
        board, engine, sent = make_server(3, 3)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        target = board.spawn_piece(BLACK, KING, Position(0, 2))
        client = make_client_synced(board)

        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        engine.wait(move_duration_ms(ROOK, WHITE, 2))
        deliver_and_settle(client, sent)

        assert client.game_over is True
        assert client.winner == WHITE
        assert client.score[WHITE] == engine.state.score[WHITE]
        client_target = client._pieces_by_id[target.id]
        assert client_target.captured is True

    def test_captured_piece_stays_until_attackers_animation_catches_up(self):
        # A non-king victim, so the game doesn't end and there's something
        # left to assert about mid-flight state.
        board, engine, sent = make_server(3, 3)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        target = board.spawn_piece(BLACK, KNIGHT, Position(0, 2))
        client = make_client_synced(board)

        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        arrive_time = move_duration_ms(ROOK, WHITE, 2)
        engine.wait(arrive_time)
        deliver(client, sent)   # server has already resolved the capture...

        # ...but this client's own clock hasn't caught up yet, so the
        # victim must still be there - not vanish before the attacker has
        # visually arrived.
        client.tick(arrive_time - 1)
        client_target = client._pieces_by_id[target.id]
        assert client_target.captured is False
        assert client.board.piece_at(Position(0, 2)).id == target.id

        client.tick(arrive_time)
        assert client_target.captured is True
        attacker = client.board.piece_at(Position(0, 2))
        assert attacker is not None and attacker.kind == ROOK


class TestNetworkGameClientMirrorsAirborneDefense:
    """Mirrors tests/unit/real_time_arbiter/test_airborne_defense.py: the
    arriving piece is captured mid-air, so its move.arrived never fires -
    only move.started (earlier) and piece.captured do. The client must not
    be left interpolating a 'ghost' in-flight piece forever."""

    def test_no_ghost_pending_move_left_behind(self):
        board, engine, sent = make_server(3, 3)
        mover = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        target = board.spawn_piece(BLACK, KNIGHT, Position(0, 2))
        client = make_client_synced(board)

        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        move_time = move_duration_ms(ROOK, WHITE, 2)
        wait_before_jump = move_time - 1   # jump scheduled just before arrival...
        engine.wait(wait_before_jump)
        engine.jump(Position(0, 2), requesting_color=BLACK)
        assert jump_duration_ms(KNIGHT, BLACK) > 1   # ...so its airborne window still covers it
        engine.wait(move_time - wait_before_jump)     # advance clock to exactly move_time
        deliver(client, sent)

        assert engine.state.board.piece_at(Position(0, 2)) is target   # sanity: server-side outcome
        assert mover.captured is True

        assert client.board.piece_at(Position(0, 2)).id == target.id
        assert client._pieces_by_id[mover.id].captured is True
        assert client.pending_moves == []


class TestThreadSafety:
    """client.board is a dict-of-Position mutated in place by the background
    network thread (see NetworkGameClient.run()); client_main.py's render
    loop iterates it on the main thread. Without client.lock held across
    both, this reliably raises "dictionary changed size during iteration"
    within milliseconds - this reproduces exactly that concurrency pattern
    (one thread mutating in a tight loop, another iterating in a tight loop)
    and asserts neither thread ever fails."""

    def test_concurrent_mutation_and_iteration_under_the_lock_never_raises(self):
        board = Board(3, 3)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        client = make_client_synced(board, color=WHITE)

        errors: list[Exception] = []
        stop = threading.Event()

        def render_loop():
            try:
                while not stop.is_set():
                    with client.lock:
                        list(client.board)   # same access pattern as ImageView.render's `for pos, piece in board:`
            except Exception as exc:   # noqa: BLE001 - capturing for the assertion below
                errors.append(exc)

        # A short switch interval forces the interpreter to hand control
        # between threads far more often than the 5ms default - without
        # this, a race that would eventually bite in a real, longer-running
        # session doesn't reliably reproduce in a short test run either way
        # (confirmed: the *unlocked* version of this exact test only failed
        # consistently once the interval was lowered like this).
        original_interval = sys.getswitchinterval()
        sys.setswitchinterval(0.00001)
        renderer = threading.Thread(target=render_loop, daemon=True)
        renderer.start()

        try:
            pos_a, pos_b = Position(0, 0), Position(0, 2)
            for _ in range(20000):
                with client.lock:
                    frm = pos_a if client.board.piece_at(pos_a) is not None else pos_b
                    to = pos_b if frm == pos_a else pos_a
                    client.board.move_piece(client.board.piece_at(frm), to)
        except Exception as exc:
            errors.append(exc)
        finally:
            stop.set()
            renderer.join(timeout=2)
            sys.setswitchinterval(original_interval)

        assert errors == []
