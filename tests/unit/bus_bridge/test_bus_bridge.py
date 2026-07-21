import json

from model.board import Board
from model.piece import BLACK, ROOK, KING, WHITE
from model.position import Position
from engine.game_engine import GameEngine
from net.bus_bridge import BusBridge
from net.protocol import EVENT


def make_engine_with_bridge():
    board = Board(3, 3)
    engine = GameEngine(board)
    sent = []
    BusBridge(engine.bus, board.rows, sent.append)
    return engine, board, sent


class TestBusBridge:

    def test_move_started_is_forwarded_as_an_event_message_with_algebraic_squares(self):
        engine, board, sent = make_engine_with_bridge()
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)

        messages = [json.loads(m) for m in sent]
        started = next(m for m in messages if m["payload"].get("piece_id") is not None
                        and m["topic"] == "move.started")
        assert started["type"] == EVENT
        assert started["payload"]["from"] == "a3"
        assert started["payload"]["to"] == "c3"
        assert started["payload"]["color"] == WHITE
        assert started["payload"]["kind"] == ROOK

    def test_no_full_board_snapshot_is_ever_sent_through_the_bridge(self):
        # The bridge only ever forwards small per-event payloads - never a
        # grid/board dump - which is the whole point of the event-driven
        # protocol over a periodic full-state push.
        engine, board, sent = make_engine_with_bridge()
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        engine.wait(5000)

        for raw in sent:
            payload = json.loads(raw)["payload"]
            assert "grid" not in payload
            assert "board" not in payload

    def test_capture_and_game_over_events_are_forwarded(self):
        engine, board, sent = make_engine_with_bridge()
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(BLACK, KING, Position(0, 2))
        engine.move(Position(0, 0), Position(0, 2), requesting_color=WHITE)
        engine.wait(5000)

        topics = [json.loads(m)["topic"] for m in sent]
        assert "piece.captured" in topics
        assert "score.changed" in topics
        assert "game.over" in topics
