from model.board import Board
from model.game_state import GameState
from model.piece import BLACK, KING, KNIGHT, ROOK, WHITE
from model.position import Position
from realtime.real_time_arbiter import RealTimeArbiter


def make(rows, cols):
    board = Board(rows, cols)
    state = GameState(board)
    arbiter = RealTimeArbiter()
    return board, state, arbiter


class TestAirborneDefense:

    def _setup_attack(self):
        # wR at (0,0) is scheduled to capture bN at (0,2): arrives at t=2000.
        board, state, arbiter = make(3, 3)
        mover = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        target = board.spawn_piece(BLACK, KNIGHT, Position(0, 2))
        arbiter.schedule_move(mover, Position(0, 0), Position(0, 2), state.clock_ms)
        return board, state, arbiter, mover, target

    def test_airborne_piece_captures_arriving_enemy(self):
        board, state, arbiter, mover, target = self._setup_attack()
        state.clock_ms = 1500
        arbiter.settle(state)
        arbiter.schedule_jump(target, Position(0, 2), state.clock_ms)   # window [1500, 2500] covers t=2000
        state.clock_ms = 2500
        arbiter.settle(state)
        assert board.piece_at(Position(0, 2)) is target   # jumper kept its cell
        assert board.is_empty(Position(0, 0))              # arriver removed from play
        assert len(arbiter.pending) == 0
        assert mover.captured is True

    def test_arrival_after_landing_is_a_normal_capture(self):
        board, state, arbiter, mover, target = self._setup_attack()
        state.clock_ms = 500
        arbiter.settle(state)
        arbiter.schedule_jump(target, Position(0, 2), state.clock_ms)   # window [500, 1500] misses t=2000
        state.clock_ms = 2000
        arbiter.settle(state)
        assert board.piece_at(Position(0, 2)) is mover

    def test_arrival_on_landing_tick_still_met_in_air(self):
        board, state, arbiter, mover, target = self._setup_attack()
        state.clock_ms = 1000
        arbiter.settle(state)
        arbiter.schedule_jump(target, Position(0, 2), state.clock_ms)   # window [1000, 2000] - inclusive
        state.clock_ms = 2000
        arbiter.settle(state)
        assert board.piece_at(Position(0, 2)) is target

    def test_airborne_capture_of_king_ends_game(self):
        board, state, arbiter = make(3, 3)
        knight = board.spawn_piece(WHITE, KNIGHT, Position(0, 0))
        king = board.spawn_piece(BLACK, KING, Position(0, 1))
        arbiter.schedule_move(king, Position(0, 1), Position(0, 0), state.clock_ms)  # arrives t=1000
        state.clock_ms = 500
        arbiter.settle(state)
        arbiter.schedule_jump(knight, Position(0, 0), state.clock_ms)  # knight airborne [500, 1500]
        state.clock_ms = 1000                                          # t=1000: knight captures the arriving king
        arbiter.settle(state)
        assert state.game_over is True
        assert board.piece_at(Position(0, 0)) is knight
        assert board.is_empty(Position(0, 1))

    def test_jumper_is_idle_again_after_defending(self):
        board, state, arbiter, mover, target = self._setup_attack()
        state.clock_ms = 1500
        arbiter.settle(state)
        arbiter.schedule_jump(target, Position(0, 2), state.clock_ms)
        state.clock_ms = 2500   # defense at t=2000, landing at t=2500
        arbiter.settle(state)
        assert target.state == "short_rest"   # briefly resting after defending
        state.clock_ms = 3500                 # short_rest elapses
        arbiter.settle(state)
        assert target.is_selectable
