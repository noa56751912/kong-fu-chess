from model.board import Board
from model.game_state import GameState
from model.piece import BLACK, KING, QUEEN, ROOK, WHITE
from model.position import Position
from realtime.motion import MS_PER_SQUARE, PendingMove
from realtime.real_time_arbiter import RealTimeArbiter


class TestWinConditions:

    def test_custom_win_condition_queen_capture(self):
        board = Board(3, 3)
        state = GameState(board, win_conditions=[lambda captured: captured.kind == QUEEN])
        arbiter = RealTimeArbiter()
        rook = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(BLACK, QUEEN, Position(0, 1))
        arbiter.schedule_move(rook, Position(0, 0), Position(0, 1), state.clock_ms)
        state.clock_ms = MS_PER_SQUARE
        arbiter.settle(state)
        assert state.game_over is True

    def test_empty_win_conditions_never_ends_game(self):
        board = Board(3, 3)
        state = GameState(board, win_conditions=[])
        arbiter = RealTimeArbiter()
        rook = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(BLACK, KING, Position(0, 1))
        arbiter.schedule_move(rook, Position(0, 0), Position(0, 1), state.clock_ms)
        state.clock_ms = MS_PER_SQUARE
        arbiter.settle(state)
        assert state.game_over is False

    def test_pending_moves_cancelled_on_king_capture(self):
        # Two pieces moving: rook toward king, and another piece already pending.
        # King is captured first -> the other pending move must be cancelled.
        board = Board(3, 5)
        state = GameState(board)
        arbiter = RealTimeArbiter()
        rook = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(BLACK, KING, Position(0, 1))
        queen = board.spawn_piece(WHITE, QUEEN, Position(0, 2))
        arbiter.schedule_move(rook, Position(0, 0), Position(0, 1), state.clock_ms)  # captures king at t=1000
        arbiter.pending.append(PendingMove(queen, Position(0, 2), Position(0, 4), 3000))
        assert len(arbiter.pending) == 2
        state.clock_ms = 1000
        arbiter.settle(state)
        assert state.game_over is True
        assert len(arbiter.pending) == 0   # queen's pending move cancelled
