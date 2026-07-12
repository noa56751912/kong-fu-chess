from model.board import Board
from model.piece import BLACK, WHITE
from model.position import Position
from rules.piece_rules import (
    MoveContext, _bishop_shape, _king_shape, _knight_shape, _pawn_capture,
    _pawn_promote, _pawn_shape, _queen_shape, _rook_shape,
)


def ctx(board=None, frm=None, to=None, start_row_offset=None):
    board = board or Board(8, 8)
    return MoveContext(frm=frm or Position(0, 0), to=to or Position(0, 0),
                        board=board, start_row_offset=start_row_offset)


class TestKingShape:

    def test_one_square_any_direction_is_legal(self):
        assert _king_shape(1, 0, WHITE, ctx()) is True
        assert _king_shape(-1, 1, WHITE, ctx()) is True

    def test_two_squares_is_illegal(self):
        assert _king_shape(2, 0, WHITE, ctx()) is False


class TestKnightShape:

    def test_l_shape_is_legal(self):
        assert _knight_shape(2, 1, WHITE, ctx()) is True
        assert _knight_shape(-1, 2, WHITE, ctx()) is True

    def test_straight_is_illegal(self):
        assert _knight_shape(2, 0, WHITE, ctx()) is False


class TestRookShape:

    def test_straight_line_is_legal(self):
        assert _rook_shape(0, 3, WHITE, ctx()) is True
        assert _rook_shape(3, 0, WHITE, ctx()) is True

    def test_diagonal_is_illegal(self):
        assert _rook_shape(1, 1, WHITE, ctx()) is False


class TestBishopShape:

    def test_diagonal_is_legal(self):
        assert _bishop_shape(2, 2, WHITE, ctx()) is True

    def test_straight_is_illegal(self):
        assert _bishop_shape(0, 2, WHITE, ctx()) is False

    def test_zero_distance_is_illegal(self):
        assert _bishop_shape(0, 0, WHITE, ctx()) is False


class TestQueenShape:

    def test_straight_is_legal(self):
        assert _queen_shape(0, 3, WHITE, ctx()) is True

    def test_diagonal_is_legal(self):
        assert _queen_shape(3, 3, WHITE, ctx()) is True

    def test_knight_shape_is_illegal(self):
        assert _queen_shape(2, 1, WHITE, ctx()) is False


class TestPawnCapture:

    def test_white_captures_diagonally_forward(self):
        assert _pawn_capture(-1, 1, WHITE, ctx()) is True
        assert _pawn_capture(-1, -1, WHITE, ctx()) is True

    def test_black_captures_diagonally_forward(self):
        assert _pawn_capture(1, 1, BLACK, ctx()) is True

    def test_forward_without_side_step_is_illegal(self):
        assert _pawn_capture(-1, 0, WHITE, ctx()) is False

    def test_wrong_direction_is_illegal(self):
        assert _pawn_capture(1, 1, WHITE, ctx()) is False


class TestPawnShape:

    def test_white_single_square_forward_is_legal(self):
        assert _pawn_shape(-1, 0, WHITE, ctx()) is True

    def test_black_single_square_forward_is_legal(self):
        assert _pawn_shape(1, 0, BLACK, ctx()) is True

    def test_sideways_is_illegal(self):
        assert _pawn_shape(-1, 1, WHITE, ctx()) is False

    def test_two_square_without_start_row_offset_is_illegal(self):
        assert _pawn_shape(-2, 0, WHITE, ctx(start_row_offset=None)) is False

    def test_two_square_from_start_row_is_legal(self):
        board = Board(4, 1)
        c = ctx(board=board, frm=Position(3, 0), start_row_offset=0)
        assert _pawn_shape(-2, 0, WHITE, c) is True

    def test_two_square_not_from_start_row_is_illegal(self):
        board = Board(4, 1)
        c = ctx(board=board, frm=Position(2, 0), start_row_offset=0)
        assert _pawn_shape(-2, 0, WHITE, c) is False

    def test_two_square_blocked_path_is_illegal(self):
        board = Board(4, 1)
        board.spawn_piece(BLACK, 'R', Position(2, 0))
        c = ctx(board=board, frm=Position(3, 0), start_row_offset=0)
        assert _pawn_shape(-2, 0, WHITE, c) is False

    def test_three_squares_is_illegal(self):
        assert _pawn_shape(-3, 0, WHITE, ctx(start_row_offset=0)) is False


class TestPawnPromote:

    def test_white_pawn_on_top_row_promotes(self):
        board = Board(4, 1)
        piece = board.spawn_piece(WHITE, 'P', Position(0, 0))
        _pawn_promote(piece, board)
        assert piece.kind == 'Q'

    def test_black_pawn_on_bottom_row_promotes(self):
        board = Board(4, 1)
        piece = board.spawn_piece(BLACK, 'P', Position(3, 0))
        _pawn_promote(piece, board)
        assert piece.kind == 'Q'

    def test_pawn_not_on_last_row_unaffected(self):
        board = Board(4, 1)
        piece = board.spawn_piece(WHITE, 'P', Position(1, 0))
        _pawn_promote(piece, board)
        assert piece.kind == 'P'
