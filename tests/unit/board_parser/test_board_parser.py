import pytest

from boardio.board_parser import board_lines_to_grid, build_board, parse_board, validate_board
from model.piece import BLACK, KING, ROOK, WHITE
from model.position import Position


class TestParseBoard:

    def test_happy_path_returns_board_lines(self):
        input_text = "Board:\nwK . bK\n. . .\nwR . bR\nCommands:\nprint board"
        result = parse_board(input_text)
        assert result == ["wK . bK", ". . .", "wR . bR"]

    def test_no_board_section_returns_empty_list(self):
        input_text = "Commands:\nprint board"
        assert parse_board(input_text) == []

    def test_empty_string_returns_empty_list(self):
        assert parse_board("") == []

    def test_board_section_only_no_commands(self):
        input_text = "Board:\nwK bK"
        assert parse_board(input_text) == ["wK bK"]

    def test_ignores_lines_before_board(self):
        input_text = "some header\nBoard:\nwK .\nCommands:"
        assert parse_board(input_text) == ["wK ."]

    def test_stops_at_commands_line(self):
        input_text = "Board:\nwK .\nCommands:\nextra line"
        result = parse_board(input_text)
        assert "extra line" not in result
        assert result == ["wK ."]


class TestValidateBoard:

    def test_valid_board_does_not_raise(self):
        board_lines = ["wK . bQ", ". wN .", "bP . wR"]
        validate_board(board_lines)

    def test_valid_board_with_all_piece_types(self):
        board_lines = ["wK wQ wR", "wB wN wP", ". . ."]
        validate_board(board_lines)

    def test_invalid_character_raises_unknown_token(self):
        board_lines = ["wK xZ", ". ."]
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            validate_board(board_lines)

    def test_at_symbol_raises_unknown_token(self):
        board_lines = ["wK @", ". ."]
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            validate_board(board_lines)

    def test_row_width_mismatch_raises(self):
        board_lines = ["wK . .", ". bK"]
        with pytest.raises(ValueError, match="ERROR ROW_WIDTH_MISMATCH"):
            validate_board(board_lines)

    def test_empty_board_lines_does_not_raise(self):
        validate_board([])

    def test_blank_lines_ignored_in_width_check(self):
        board_lines = ["wK . bK", "", ". . .", "wR . bR"]
        validate_board(board_lines)


class TestBoardLinesToGrid:

    def test_converts_lines_to_token_lists(self):
        board_lines = ["wK . bK", ". . .", "wR . bR"]
        grid = board_lines_to_grid(board_lines)
        assert grid == [
            ["wK", ".", "bK"],
            [".", ".", "."],
            ["wR", ".", "bR"],
        ]

    def test_skips_blank_lines(self):
        board_lines = ["wK bK", "", "wR bR"]
        grid = board_lines_to_grid(board_lines)
        assert len(grid) == 2


class TestBuildBoard:

    def test_spawns_pieces_at_correct_positions(self):
        grid = [["wK", ".", "bK"], [".", ".", "."]]
        board = build_board(grid)
        king = board.piece_at(Position(0, 0))
        assert king.color == WHITE
        assert king.kind == KING
        assert board.piece_at(Position(0, 2)).color == BLACK

    def test_dots_are_empty(self):
        grid = [[".", "."]]
        board = build_board(grid)
        assert board.is_empty(Position(0, 0))
        assert board.is_empty(Position(0, 1))

    def test_board_dimensions_match_grid(self):
        grid = [["wR", ".", "."], [".", ".", "."]]
        board = build_board(grid)
        assert board.rows == 2
        assert board.cols == 3

    def test_round_trip_matches_original_grid(self):
        grid = [["wK", ".", "bK"], [".", "wR", "."]]
        board = build_board(grid)
        assert board.to_grid() == grid
