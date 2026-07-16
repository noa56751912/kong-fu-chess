from boardio.board_parser import build_board
from engine.game_engine import GameEngine
from model.position import Position
from realtime.motion import JUMP_DURATION_MS, Moving, rest_duration_ms


def make_engine(rows):
    grid = [row.split() for row in rows]
    return GameEngine(build_board(grid))


class TestJump:

    def test_board_unchanged_by_jump(self):
        engine = make_engine([". . .", ". wK .", ". . ."])
        engine.jump(Position(1, 1))
        engine.wait(JUMP_DURATION_MS)
        assert engine.snapshot().piece_at(Position(1, 1)).kind == 'K'

    def test_jumping_piece_cannot_be_selected(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.jump(Position(0, 0))
        engine.select(Position(0, 0))
        assert engine.state.selection is None

    def test_resting_piece_cannot_be_selected(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.jump(Position(0, 0))
        engine.wait(JUMP_DURATION_MS)   # lands into its post-jump rest
        engine.select(Position(0, 0))
        assert engine.state.selection is None

    def test_pawn_can_walk_into_a_jumping_enemys_square_and_gets_captured_on_landing(self):
        engine = make_engine(["bP", "wP"])
        engine.jump(Position(0, 0))                    # black pawn jumps in place
        engine.select(Position(1, 0))
        engine.select(Position(0, 0))                   # white pawn steps straight into it
        assert len(engine.arbiter.pending) == 1
        engine.wait(JUMP_DURATION_MS)                    # both the jump and the step land at once
        board = engine.snapshot()
        assert board.is_empty(Position(1, 0))            # the white pawn never made it down
        assert board.piece_at(Position(0, 0)).color == 'b'
        assert engine.state.score['b'] == 1

    def test_jumping_piece_cannot_move(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.select(Position(0, 0))     # select while still idle
        engine.jump(Position(0, 0))      # then it goes airborne
        engine.select(Position(0, 1))     # try to move it while airborne
        assert len(engine.arbiter.pending) == 0

    def test_moving_piece_cannot_jump(self):
        engine = make_engine(["wR . . .", ". . . .", ". . . ."])
        engine.select(Position(0, 0))
        engine.select(Position(0, 3))
        engine.jump(Position(0, 0))
        # jump() must have been a no-op: the origin cell still just shows the pending move
        assert isinstance(engine.arbiter.status.get(Position(0, 0)), Moving)

    def test_jump_on_empty_cell_ignored(self):
        engine = make_engine([". . .", ". . .", ". . ."])
        engine.jump(Position(1, 1))
        assert engine.arbiter.status == {}

    def test_jump_outside_board_ignored(self):
        engine = make_engine(["wK ."])
        engine.jump(None)
        assert engine.arbiter.status == {}

    def test_still_resting_immediately_after_landing(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.jump(Position(0, 0))
        engine.wait(JUMP_DURATION_MS)
        engine.select(Position(0, 0))
        engine.select(Position(0, 1))
        assert len(engine.arbiter.pending) == 0

    def test_piece_can_move_again_after_landing_and_resting(self):
        engine = make_engine(["wK . .", ". . .", ". . ."])
        engine.jump(Position(0, 0))
        engine.wait(JUMP_DURATION_MS)
        engine.wait(rest_duration_ms("short_rest"))
        engine.select(Position(0, 0))
        engine.select(Position(0, 1))
        assert len(engine.arbiter.pending) == 1

    def test_jump_ignored_after_game_over(self):
        engine = make_engine(["wR bK wQ", ". . .", ". . ."])
        engine.select(Position(0, 0))
        engine.select(Position(0, 1))
        engine.wait(1000)   # rook captures king -> game over
        engine.jump(Position(0, 2))
        assert engine.arbiter.status == {}
