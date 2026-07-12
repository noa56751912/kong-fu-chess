from model.board import Board
from model.game_state import GameState
from model.piece import BLACK, QUEEN, ROOK, WHITE
from model.position import Position
from realtime.real_time_arbiter import RealTimeArbiter


def make(rows, cols):
    board = Board(rows, cols)
    state = GameState(board)
    arbiter = RealTimeArbiter()
    return board, state, arbiter


class TestCaptureCancelsMove:

    def test_capturing_a_departing_piece_cancels_its_move(self):
        # bR (2 squares away) is scheduled to capture wR at (0,0), arriving at
        # t=2000. wR then starts a 3-square move arriving at t=3000. When bR
        # captures it at t=2000, wR's still-pending move must die with it -
        # it must not "resurrect" at (0,3) and erase bR at t=3000.
        board, state, arbiter = make(3, 4)
        wR = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        bR = board.spawn_piece(BLACK, ROOK, Position(2, 0))
        arbiter.schedule_move(bR, Position(2, 0), Position(0, 0), state.clock_ms)
        arbiter.schedule_move(wR, Position(0, 0), Position(0, 3), state.clock_ms)
        state.clock_ms = 3000
        arbiter.settle(state)
        assert board.piece_at(Position(0, 0)) is bR   # captor holds the cell
        assert board.is_empty(Position(0, 3))          # cancelled move never landed
        assert len(arbiter.pending) == 0

    def test_capture_of_idle_piece_unaffected(self):
        board, state, arbiter = make(3, 3)
        wR = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(BLACK, QUEEN, Position(0, 1))
        arbiter.schedule_move(wR, Position(0, 0), Position(0, 1), state.clock_ms)
        state.clock_ms = 1000
        arbiter.settle(state)
        assert board.piece_at(Position(0, 1)) is wR
