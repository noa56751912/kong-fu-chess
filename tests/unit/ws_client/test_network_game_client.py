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


class TestNetworkGameClientMirrorsSimpleMove:

    def test_board_position_matches_server_after_arrival(self):
        board, engine, sent = make_server(3, 3)
        rook = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        client = make_client_synced(board, color=WHITE)

        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        engine.wait(move_duration_ms(ROOK, WHITE, 2))
        deliver(client, sent)

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


class TestNetworkGameClientMirrorsCapture:

    def test_score_and_board_updated_on_capture(self):
        board, engine, sent = make_server(3, 3)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        target = board.spawn_piece(BLACK, KING, Position(0, 2))
        client = make_client_synced(board)

        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        engine.wait(move_duration_ms(ROOK, WHITE, 2))
        deliver(client, sent)

        assert client.game_over is True
        assert client.winner == WHITE
        assert client.score[WHITE] == engine.state.score[WHITE]
        client_target = client._pieces_by_id[target.id]
        assert client_target.captured is True


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
