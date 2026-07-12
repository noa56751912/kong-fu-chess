from model.board import Board
from model.piece import BLACK, KING, ROOK, WHITE
from model.position import Position


class TestInBounds:

    def test_position_inside_board_is_in_bounds(self):
        board = Board(3, 3)
        assert board.in_bounds(Position(0, 0)) is True
        assert board.in_bounds(Position(2, 2)) is True

    def test_position_outside_board_is_out_of_bounds(self):
        board = Board(3, 3)
        assert board.in_bounds(Position(3, 0)) is False
        assert board.in_bounds(Position(0, -1)) is False


class TestSpawnPiece:

    def test_spawned_piece_is_placed_on_its_cell(self):
        board = Board(3, 3)
        piece = board.spawn_piece(WHITE, KING, Position(0, 0))
        assert board.piece_at(Position(0, 0)) is piece

    def test_ids_are_unique_and_stable(self):
        board = Board(3, 3)
        p1 = board.spawn_piece(WHITE, KING, Position(0, 0))
        p2 = board.spawn_piece(BLACK, KING, Position(2, 2))
        assert p1.id != p2.id


class TestPieceAtAndIsEmpty:

    def test_piece_at_empty_cell_is_none(self):
        board = Board(3, 3)
        assert board.piece_at(Position(1, 1)) is None
        assert board.is_empty(Position(1, 1)) is True

    def test_piece_at_occupied_cell_is_not_empty(self):
        board = Board(3, 3)
        board.spawn_piece(WHITE, KING, Position(1, 1))
        assert board.is_empty(Position(1, 1)) is False


class TestMovePiece:

    def test_move_updates_piece_cell(self):
        board = Board(3, 3)
        piece = board.spawn_piece(WHITE, KING, Position(0, 0))
        board.move_piece(piece, Position(1, 1))
        assert piece.cell == Position(1, 1)

    def test_move_vacates_origin_and_occupies_destination(self):
        board = Board(3, 3)
        piece = board.spawn_piece(WHITE, KING, Position(0, 0))
        board.move_piece(piece, Position(1, 1))
        assert board.is_empty(Position(0, 0))
        assert board.piece_at(Position(1, 1)) is piece

    def test_move_onto_occupied_cell_returns_captured_piece(self):
        board = Board(3, 3)
        mover = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        victim = board.spawn_piece(BLACK, KING, Position(0, 2))
        captured = board.move_piece(mover, Position(0, 2))
        assert captured is victim

    def test_move_onto_empty_cell_returns_none(self):
        board = Board(3, 3)
        mover = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        assert board.move_piece(mover, Position(0, 2)) is None

    def test_captured_piece_detached_from_board(self):
        board = Board(3, 3)
        mover = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        victim = board.spawn_piece(BLACK, KING, Position(0, 2))
        board.move_piece(mover, Position(0, 2))
        assert board.piece_at(Position(0, 2)) is mover
        assert victim.cell == Position(0, 2)  # captured object's own cell is left untouched


class TestPathClear:

    def test_clear_straight_path(self):
        board = Board(1, 4)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        assert board.path_clear(Position(0, 0), Position(0, 3)) is True

    def test_blocked_straight_path(self):
        board = Board(1, 4)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(WHITE, KING, Position(0, 1))
        assert board.path_clear(Position(0, 0), Position(0, 3)) is False

    def test_clear_diagonal_path(self):
        board = Board(4, 4)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        assert board.path_clear(Position(0, 0), Position(3, 3)) is True

    def test_blocked_diagonal_path(self):
        board = Board(4, 4)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(WHITE, KING, Position(1, 1))
        assert board.path_clear(Position(0, 0), Position(3, 3)) is False

    def test_endpoints_excluded_from_check(self):
        board = Board(1, 2)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(BLACK, KING, Position(0, 1))
        assert board.path_clear(Position(0, 0), Position(0, 1)) is True

    def test_adjacent_cells_have_no_intermediate_squares(self):
        board = Board(2, 2)
        assert board.path_clear(Position(0, 0), Position(1, 1)) is True


class TestToGrid:

    def test_empty_board_is_all_dots(self):
        board = Board(2, 2)
        assert board.to_grid() == [['.', '.'], ['.', '.']]

    def test_pieces_rendered_as_color_kind_tokens(self):
        board = Board(2, 2)
        board.spawn_piece(WHITE, KING, Position(0, 0))
        board.spawn_piece(BLACK, ROOK, Position(1, 1))
        assert board.to_grid() == [['wK', '.'], ['.', 'bR']]


class TestIteration:

    def test_iterates_position_piece_pairs(self):
        board = Board(2, 2)
        piece = board.spawn_piece(WHITE, KING, Position(0, 0))
        assert list(board) == [(Position(0, 0), piece)]
