from model.piece import BISHOP, KNIGHT, ROOK, WHITE, Piece
from model.position import Position
from realtime.motion import PendingMove


def make_piece(kind):
    return Piece(id=1, color=WHITE, kind=kind, cell=Position(0, 0))


class TestMoveTrajectory:

    def test_origin_interval(self):
        m = PendingMove(make_piece(ROOK), Position(0, 0), Position(0, 3), 3000)
        assert m.interval_in(Position(0, 0)) == (0, 1000)

    def test_intermediate_cell_interval(self):
        m = PendingMove(make_piece(ROOK), Position(0, 0), Position(0, 3), 3000)
        assert m.interval_in(Position(0, 2)) == (2000, 3000)

    def test_destination_is_open_ended(self):
        m = PendingMove(make_piece(ROOK), Position(0, 0), Position(0, 3), 3000)
        assert m.interval_in(Position(0, 3)) == (3000, None)

    def test_cell_off_path_returns_none(self):
        m = PendingMove(make_piece(ROOK), Position(0, 0), Position(0, 3), 3000)
        assert m.interval_in(Position(1, 1)) is None

    def test_cell_behind_origin_returns_none(self):
        m = PendingMove(make_piece(ROOK), Position(0, 1), Position(0, 3), 3000)
        assert m.interval_in(Position(0, 0)) is None

    def test_knight_crosses_no_intermediate_cells(self):
        m = PendingMove(make_piece(KNIGHT), Position(0, 0), Position(2, 1), 2000)
        assert m.interval_in(Position(1, 0)) is None
        assert m.interval_in(Position(1, 1)) is None

    def test_diagonal_intermediate_cell(self):
        m = PendingMove(make_piece(BISHOP), Position(0, 0), Position(2, 2), 2000)
        assert m.interval_in(Position(1, 1)) == (1000, 2000)

    def test_start_offset_by_schedule_time(self):
        # Scheduled at t=5000, 2 squares -> departs origin during [5000, 6000)
        m = PendingMove(make_piece(ROOK), Position(0, 0), Position(0, 2), 7000)
        assert m.interval_in(Position(0, 0)) == (5000, 6000)
        assert m.interval_in(Position(0, 1)) == (6000, 7000)
