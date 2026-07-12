from boardio.board_parser import build_board
from engine.game_engine import GAME_OVER, GameEngine, MOTION_IN_PROGRESS
from model.position import Position
from rules.rule_engine import OK, MoveValidation


def make_engine(rows, win_conditions=None):
    grid = [row.split() for row in rows]
    return GameEngine(build_board(grid), win_conditions=win_conditions)


class TestMoveResult:

    def test_legal_move_is_accepted(self):
        engine = make_engine(["wR . . .", ". . . .", ". . . ."])
        result = engine._try_schedule_move(Position(0, 0), Position(0, 3))
        assert result.is_accepted is True
        assert result.reason == OK

    def test_illegal_shape_is_rejected_with_rule_reason(self):
        engine = make_engine(["wK . . .", ". . . .", ". . . ."])
        result = engine._try_schedule_move(Position(0, 0), Position(0, 2))
        assert result.is_accepted is False
        assert result.reason == MoveValidation.INVALID_SHAPE

    def test_busy_piece_is_rejected_with_motion_in_progress(self):
        engine = make_engine(["wR . . .", ". . . .", ". . . ."])
        engine._try_schedule_move(Position(0, 0), Position(0, 3))   # now moving
        result = engine._try_schedule_move(Position(0, 0), Position(1, 0))
        assert result.is_accepted is False
        assert result.reason == MOTION_IN_PROGRESS

    def test_move_after_game_over_is_rejected_with_game_over_reason(self):
        engine = make_engine(["wR bK wQ", ". . .", ". . ."])
        engine._try_schedule_move(Position(0, 0), Position(0, 1))
        engine.wait(1000)   # rook captures king -> game over
        result = engine._try_schedule_move(Position(0, 2), Position(1, 2))
        assert result.is_accepted is False
        assert result.reason == GAME_OVER
