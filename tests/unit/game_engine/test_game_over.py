from boardio.board_parser import build_board
from engine.game_engine import GameEngine
from model.position import Position


def make_engine(rows, win_conditions=None):
    grid = [row.split() for row in rows]
    return GameEngine(build_board(grid), win_conditions=win_conditions)


class TestGameOver:

    def test_game_not_over_initially(self):
        engine = make_engine(["wK bK .", ". . .", ". . ."])
        assert engine.game_over is False

    def test_capturing_king_sets_game_over(self):
        engine = make_engine(["wR bK .", ". . .", ". . ."])
        engine.click(Position(0, 0))
        engine.click(Position(0, 1))
        engine.wait(1000)
        assert engine.game_over is True

    def test_non_king_capture_does_not_end_game(self):
        engine = make_engine(["wR bQ .", ". . .", ". . ."])
        engine.click(Position(0, 0))
        engine.click(Position(0, 1))
        engine.wait(1000)
        assert engine.game_over is False

    def test_click_after_game_over_is_ignored(self):
        engine = make_engine(["wR bK .", ". . .", ". . ."])
        engine.click(Position(0, 0))
        engine.click(Position(0, 1))
        engine.wait(1000)
        engine.click(Position(0, 2))
        assert engine.state.selection is None
        assert len(engine.arbiter.pending) == 0

    def test_no_new_moves_scheduled_after_game_over(self):
        engine = make_engine(["wR bK wK", ". . .", ". . ."])
        engine.click(Position(0, 0))
        engine.click(Position(0, 1))
        engine.wait(1000)   # rook captures bK -> game over
        engine.click(Position(0, 2))
        engine.click(Position(0, 1))
        assert len(engine.arbiter.pending) == 0

    def test_board_state_frozen_after_game_over(self):
        engine = make_engine(["wR bK .", ". . .", ". . ."])
        engine.click(Position(0, 0))
        engine.click(Position(0, 1))
        engine.wait(1000)
        snapshot = engine.snapshot().to_grid()
        engine.wait(5000)
        assert engine.snapshot().to_grid() == snapshot

    def test_custom_win_condition_queen_capture(self):
        engine = make_engine(["wR bQ .", ". . .", ". . ."],
                              win_conditions=[lambda captured: captured.kind == 'Q'])
        engine.click(Position(0, 0))
        engine.click(Position(0, 1))
        engine.wait(1000)
        assert engine.game_over is True

    def test_empty_win_conditions_never_ends_game(self):
        engine = make_engine(["wR bK .", ". . .", ". . ."], win_conditions=[])
        engine.click(Position(0, 0))
        engine.click(Position(0, 1))
        engine.wait(1000)
        assert engine.game_over is False
