from boardio.board_parser import build_board
from engine.game_engine import GameEngine
from model.position import Position


def make_engine(rows):
    grid = [row.split() for row in rows]
    return GameEngine(build_board(grid))


class TestSelection:

    def test_click_piece_selects_it(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.select(Position(0, 0))
        assert engine.state.selection == Position(0, 0)

    def test_click_empty_no_selection(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.select(Position(0, 1))
        assert engine.state.selection is None

    def test_click_enemy_piece_selects_it(self):
        engine = make_engine(["bK . .", ". . .", ". . ."])
        engine.select(Position(0, 0))
        assert engine.state.selection == Position(0, 0)

    def test_reclick_friendly_changes_selection(self):
        engine = make_engine(["wK . wR", ". . .", ". . ."])
        engine.select(Position(0, 0))
        engine.select(Position(0, 2))
        assert engine.state.selection == Position(0, 2)

    def test_illegal_move_keeps_selection(self):
        engine = make_engine(["wK . . .", ". . . .", ". . . ."])
        engine.select(Position(0, 0))
        engine.select(Position(0, 2))   # illegal: 2 squares right
        assert engine.state.selection == Position(0, 0)

    def test_legal_move_clears_selection(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.select(Position(0, 0))
        engine.select(Position(0, 1))
        assert engine.state.selection is None


class TestOutOfBoundsClick:

    def test_out_of_bounds_click_with_selection_clears_it(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.select(Position(0, 0))
        assert engine.state.selection == Position(0, 0)
        engine.select(None)
        assert engine.state.selection is None

    def test_out_of_bounds_click_with_no_selection_stays_none(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.select(None)
        assert engine.state.selection is None


class TestInFlight:

    def test_click_inflight_source_ignored(self):
        engine = make_engine(["wR . . .", ". . . .", ". . . ."])
        engine.select(Position(0, 0))
        engine.select(Position(0, 3))   # rook in flight
        engine.select(Position(0, 0))   # try to re-select in-flight source
        assert engine.state.selection is None
