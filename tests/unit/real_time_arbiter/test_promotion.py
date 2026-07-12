from model.board import Board
from model.game_state import GameState
from model.piece import BLACK, KING, PAWN, QUEEN, WHITE
from model.position import Position
from realtime.motion import MS_PER_SQUARE
from realtime.real_time_arbiter import RealTimeArbiter


class TestPromotionCombinedWithCapture:

    def test_promotion_combined_with_king_capture(self):
        # Diagonal capture landing on the last row: the captured token is
        # snapshotted before promotion, but by the time game_over is set the
        # board must already show the promoted queen, not the pawn.
        board = Board(2, 3)
        state = GameState(board)
        arbiter = RealTimeArbiter()
        king = board.spawn_piece(BLACK, KING, Position(0, 0))
        pawn = board.spawn_piece(WHITE, PAWN, Position(1, 1))
        arbiter.schedule_move(pawn, Position(1, 1), Position(0, 0), state.clock_ms)
        state.clock_ms = MS_PER_SQUARE
        arbiter.settle(state)
        assert state.game_over is True
        assert board.piece_at(Position(0, 0)) is pawn
        assert pawn.kind == QUEEN
        assert board.is_empty(Position(1, 1))
