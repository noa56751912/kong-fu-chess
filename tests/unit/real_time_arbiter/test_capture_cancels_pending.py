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


class TestCannotCaptureADepartedPiece:

    def test_arriving_on_a_square_its_occupant_already_left_is_not_a_capture(self):
        # bR (2 squares away) is scheduled to capture wR at (0,0). wR sets off
        # on its own 3-square move in the same tick - so by the time bR gets
        # to (0,0), wR is long gone. bR just moves in; wR's own move is
        # unaffected and lands normally.
        board, state, arbiter = make(3, 4)
        wR = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        bR = board.spawn_piece(BLACK, ROOK, Position(2, 0))
        move_b = arbiter.schedule_move(board, bR, Position(2, 0), Position(0, 0), state.clock_ms)
        move_w = arbiter.schedule_move(board, wR, Position(0, 0), Position(0, 3), state.clock_ms)
        state.clock_ms = max(move_b.arrive_time, move_w.arrive_time)
        arbiter.settle(state)
        assert board.piece_at(Position(0, 0)) is bR   # moved into the now-empty square
        assert board.piece_at(Position(0, 3)) is wR    # its own move landed untouched
        assert wR.captured is False
        assert len(arbiter.pending) == 0

    def test_capture_of_idle_piece_unaffected(self):
        board, state, arbiter = make(3, 3)
        wR = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(BLACK, QUEEN, Position(0, 1))
        move = arbiter.schedule_move(board, wR, Position(0, 0), Position(0, 1), state.clock_ms)
        state.clock_ms = move.arrive_time
        arbiter.settle(state)
        assert board.piece_at(Position(0, 1)) is wR


class TestCrossingPaths:

    def test_two_pieces_swapping_squares_neither_captures_the_other(self):
        # wR heads from (0,0) to (0,1) to capture bQ - but bQ flees the other
        # way, from (0,1) straight into wR's now-vacated (0,0). Whichever of
        # the two settles first must not treat the other as still standing
        # on the square it's only just arriving at: both should land safely,
        # crossing paths instead of one "eating" the other.
        board, state, arbiter = make(1, 2)
        wR = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        bQ = board.spawn_piece(BLACK, QUEEN, Position(0, 1))
        move_w = arbiter.schedule_move(board, wR, Position(0, 0), Position(0, 1), state.clock_ms)
        move_b = arbiter.schedule_move(board, bQ, Position(0, 1), Position(0, 0), state.clock_ms)
        state.clock_ms = max(move_w.arrive_time, move_b.arrive_time)
        arbiter.settle(state)
        assert board.piece_at(Position(0, 1)) is wR
        assert board.piece_at(Position(0, 0)) is bQ
        assert wR.captured is False
        assert bQ.captured is False
        assert len(arbiter.pending) == 0
