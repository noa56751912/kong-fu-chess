from boardio.board_parser import build_board
from engine.game_engine import GameEngine
from model.position import Position


def make_engine(rows):
    grid = [row.split() for row in rows]
    return GameEngine(build_board(grid))


class TestWait:

    def test_wait_advances_clock(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.wait(500)
        assert engine.state.clock_ms == 500

    def test_multiple_waits_accumulate(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.wait(300)
        engine.wait(700)
        assert engine.state.clock_ms == 1000

    def test_piece_arrives_after_accumulated_wait(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.select(Position(0, 0))
        engine.select(Position(0, 1))   # 1 square -> 1000 ms
        engine.wait(500)
        engine.wait(500)               # total 1000 ms
        board = engine.snapshot()
        assert board.piece_at(Position(0, 1)) is not None
        assert board.is_empty(Position(0, 0))
