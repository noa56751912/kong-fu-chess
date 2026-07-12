from input.board_mapper import CELL_SIZE, pixel_to_cell
from model.board import Board
from model.position import Position


class TestPixelToCell:

    def test_x_maps_to_column_y_maps_to_row(self):
        board = Board(5, 5)
        assert pixel_to_cell(350, 50, board) == Position(0, 3)

    def test_top_left_cell(self):
        board = Board(3, 3)
        assert pixel_to_cell(0, 0, board) == Position(0, 0)

    def test_center_of_cell_resolves_to_that_cell(self):
        board = Board(3, 3)
        assert pixel_to_cell(150, 250, board) == Position(2, 1)

    def test_out_of_bounds_returns_none(self):
        board = Board(3, 3)
        assert pixel_to_cell(9999, 9999, board) is None

    def test_negative_coordinates_return_none(self):
        board = Board(3, 3)
        assert pixel_to_cell(-1, 0, board) is None

    def test_custom_cell_size(self):
        board = Board(3, 3)
        assert pixel_to_cell(40, 0, board, cell_size=20) == Position(0, 2)

    def test_default_cell_size_constant(self):
        assert CELL_SIZE == 100
