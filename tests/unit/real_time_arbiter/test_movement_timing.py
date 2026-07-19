from model.board import Board
from model.game_state import GameState
from model.piece import BISHOP, KING, KNIGHT, ROOK, WHITE
from model.position import Position
from realtime.motion import MS_PER_SQUARE
from realtime.real_time_arbiter import RealTimeArbiter


def make(rows, cols):
    board = Board(rows, cols)
    state = GameState(board)
    arbiter = RealTimeArbiter()
    return board, state, arbiter


class TestTimedMovement:

    def test_source_vacated_the_instant_the_move_is_scheduled(self):
        board, state, arbiter = make(1, 4)
        piece = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        arbiter.schedule_move(board, piece, Position(0, 0), Position(0, 3), state.clock_ms)
        assert board.is_empty(Position(0, 0))
        assert board.is_empty(Position(0, 3))   # not there yet either - still in flight

    def test_piece_not_yet_present_at_destination_before_arrival(self):
        board, state, arbiter = make(1, 4)
        piece = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        arbiter.schedule_move(board, piece, Position(0, 0), Position(0, 3), state.clock_ms)
        state.clock_ms = 1000
        arbiter.settle(state)
        assert board.is_empty(Position(0, 3))

    def test_piece_arrives_after_enough_wait(self):
        board, state, arbiter = make(1, 4)
        piece = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        arbiter.schedule_move(board, piece, Position(0, 0), Position(0, 3), state.clock_ms)
        state.clock_ms = 3000
        arbiter.settle(state)
        assert board.piece_at(Position(0, 3)) is piece
        assert board.is_empty(Position(0, 0))

    def test_travel_time_one_square(self):
        board, state, arbiter = make(3, 3)
        piece = board.spawn_piece(WHITE, KING, Position(0, 0))
        move = arbiter.schedule_move(board, piece, Position(0, 0), Position(0, 1), state.clock_ms)
        assert len(arbiter.pending) == 1
        assert move.arrive_time == MS_PER_SQUARE

    def test_travel_time_rook_three_squares(self):
        board, state, arbiter = make(3, 5)
        piece = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        move = arbiter.schedule_move(board, piece, Position(0, 0), Position(0, 3), state.clock_ms)
        assert move.arrive_time == 3 * MS_PER_SQUARE

    def test_travel_time_bishop_diagonal(self):
        board, state, arbiter = make(4, 4)
        piece = board.spawn_piece(WHITE, BISHOP, Position(0, 0))
        move = arbiter.schedule_move(board, piece, Position(0, 0), Position(2, 2), state.clock_ms)
        assert move.arrive_time == 2 * MS_PER_SQUARE

    def test_travel_time_knight_l_shape(self):
        board, state, arbiter = make(4, 4)
        piece = board.spawn_piece(WHITE, KNIGHT, Position(0, 0))
        move = arbiter.schedule_move(board, piece, Position(0, 0), Position(2, 1), state.clock_ms)
        assert move.arrive_time == 2 * MS_PER_SQUARE

    def test_pending_stores_correct_from_and_to(self):
        board, state, arbiter = make(3, 3)
        piece = board.spawn_piece(WHITE, KING, Position(0, 0))
        move = arbiter.schedule_move(board, piece, Position(0, 0), Position(1, 1), state.clock_ms)
        assert move.frm == Position(0, 0)
        assert move.to == Position(1, 1)
        assert move.piece is piece
