from boardio.board_printer import print_board
from model.board import Board
from model.piece import BLACK, KING, WHITE
from model.position import Position


class TestPrintBoard:

    def test_prints_grid_as_space_separated_rows(self, capsys):
        board = Board(3, 3)
        board.spawn_piece(WHITE, KING, Position(0, 0))
        board.spawn_piece(BLACK, KING, Position(1, 1))
        print_board(board)
        out = capsys.readouterr().out
        assert out == "wK . .\n. bK .\n. . .\n"

    def test_empty_board_prints_dots(self, capsys):
        board = Board(2, 2)
        print_board(board)
        assert capsys.readouterr().out == ". .\n. .\n"
