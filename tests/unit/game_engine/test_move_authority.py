from boardio.board_parser import build_board
from engine.game_engine import GAME_OVER, MOTION_IN_PROGRESS, NOT_YOUR_PIECE, GameEngine
from model.piece import BLACK, ROOK, WHITE
from model.position import Position
from realtime.motion import move_duration_ms
from rules.rule_engine import OK


def make_engine(rows):
    grid = [row.split() for row in rows]
    return GameEngine(build_board(grid))


class TestMoveWithoutRequestingColor:
    """requesting_color=None preserves today's local/hotseat behavior."""

    def test_legal_move_is_accepted(self):
        engine = make_engine(["wR . . .", ". . . .", ". . . ."])
        result = engine.move(Position(0, 0), Position(0, 3))
        assert result.is_accepted is True
        assert result.reason == OK


class TestServerSideOwnershipCheck:
    """A networked client can only ever *request* a move - the server always
    resolves whose piece it actually is and rejects a mismatched color, which
    is what stops a hacked client from moving its opponent's pieces."""

    def test_moving_own_color_piece_is_accepted(self):
        engine = make_engine(["wR . . .", ". . . .", ". . . ."])
        result = engine.move(Position(0, 0), Position(0, 3), requesting_color=WHITE)
        assert result.is_accepted is True

    def test_moving_opponents_piece_is_rejected(self):
        engine = make_engine(["bR . . .", ". . . .", ". . . ."])
        result = engine.move(Position(0, 0), Position(0, 3), requesting_color=WHITE)
        assert result.is_accepted is False
        assert result.reason == NOT_YOUR_PIECE

    def test_moving_an_empty_square_is_rejected_as_not_your_piece(self):
        engine = make_engine([". . . .", ". . . .", ". . . ."])
        result = engine.move(Position(0, 0), Position(0, 3), requesting_color=WHITE)
        assert result.is_accepted is False
        assert result.reason == NOT_YOUR_PIECE

    def test_game_over_takes_precedence_over_ownership_check(self):
        engine = make_engine(["wR bK wQ", ". . .", ". . ."])
        engine.move(Position(0, 0), Position(0, 1))
        engine.wait(2000)   # rook captures king -> game over
        result = engine.move(Position(0, 2), Position(1, 2), requesting_color=WHITE)
        assert result.is_accepted is False
        assert result.reason == GAME_OVER


class TestServerSideCooldownCheck:
    """A hacked client that tries to move a piece again the instant it lands -
    skipping its post-move rest/cooldown - must have the second move rejected.
    (A move *in flight* vacates its origin square immediately, so a second
    command targeting the departed square finds no piece there at all - see
    test_move_scheduling.py - so the realistic "skip the cooldown" attack is
    against a piece that has just landed and is resting, not one still
    travelling.) This falls out of the existing is_selectable check in
    _try_schedule_move, exercised here through the network-facing move()
    entry point."""

    def test_moving_again_immediately_after_landing_is_rejected(self):
        engine = make_engine(["wR . . .", ". . . .", ". . . ."])
        duration = move_duration_ms(ROOK, WHITE, 3)
        first = engine.move(Position(0, 0), Position(0, 3), requesting_color=WHITE)
        assert first.is_accepted is True
        engine.wait(duration)   # rook lands and enters its post-move rest
        second = engine.move(Position(0, 3), Position(0, 2), requesting_color=WHITE)
        assert second.is_accepted is False
        assert second.reason == MOTION_IN_PROGRESS


class TestJumpWithRequestingColor:

    def test_jump_own_piece_is_scheduled(self):
        engine = make_engine(["wN . . .", ". . . .", ". . . ."])
        engine.jump(Position(0, 0), requesting_color=WHITE)
        assert len(engine.in_flight_moves()) == 0   # jumps aren't tracked as in_flight_moves
        assert engine.state.board.piece_at(Position(0, 0)).state != "idle"

    def test_jump_opponents_piece_is_ignored(self):
        engine = make_engine(["bN . . .", ". . . .", ". . . ."])
        engine.jump(Position(0, 0), requesting_color=WHITE)
        piece = engine.state.board.piece_at(Position(0, 0))
        assert piece.state == "idle"
