import pytest
from command_parser import parse_commands


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestParseCommandsHappyPath:

    def test_print_board(self):
        result = parse_commands("Commands:\nprint board")
        assert result == [('print_board',)]

    def test_wait(self):
        result = parse_commands("Commands:\nwait 500")
        assert result == [('wait', 500)]

    def test_click(self):
        result = parse_commands("Commands:\nclick 50 150")
        assert result == [('click', 50, 150)]

    def test_all_three_commands_in_sequence(self):
        input_text = "Commands:\nclick 50 50\nwait 1000\nprint board"
        result = parse_commands(input_text)
        assert result == [
            ('click', 50, 50),
            ('wait', 1000),
            ('print_board',),
        ]

    def test_ignores_lines_before_commands_section(self):
        input_text = "Board:\nwK .\nCommands:\nprint board"
        result = parse_commands(input_text)
        assert result == [('print_board',)]

    def test_blank_lines_between_commands_ignored(self):
        input_text = "Commands:\nwait 100\n\nprint board"
        result = parse_commands(input_text)
        assert result == [('wait', 100), ('print_board',)]

    def test_click_with_zero_coordinates(self):
        result = parse_commands("Commands:\nclick 0 0")
        assert result == [('click', 0, 0)]

    def test_wait_zero_ms(self):
        result = parse_commands("Commands:\nwait 0")
        assert result == [('wait', 0)]

    def test_multiple_print_board_commands(self):
        input_text = "Commands:\nprint board\nprint board"
        result = parse_commands(input_text)
        assert result == [('print_board',), ('print_board',)]


# ---------------------------------------------------------------------------
# Edge cases — no Commands section
# ---------------------------------------------------------------------------

class TestParseCommandsNoSection:

    def test_no_commands_section_returns_empty(self):
        assert parse_commands("Board:\nwK .") == []

    def test_empty_string_returns_empty(self):
        assert parse_commands("") == []

    def test_commands_section_with_no_commands(self):
        assert parse_commands("Commands:\n") == []

    def test_commands_section_only_blank_lines(self):
        assert parse_commands("Commands:\n\n\n") == []


# ---------------------------------------------------------------------------
# Invalid commands — must raise ERROR UNKNOWN_TOKEN
# ---------------------------------------------------------------------------

class TestParseCommandsInvalidToken:

    def test_unknown_command_word(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\nmove a2 a4")

    def test_garbage_string(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\n@@@")

    def test_wait_missing_value(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\nwait")

    def test_wait_non_numeric(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\nwait abc")

    def test_wait_float(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\nwait 1.5")

    def test_wait_too_many_parts(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\nwait 100 200")

    def test_click_missing_y(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\nclick 50")

    def test_click_non_numeric_x(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\nclick abc 50")

    def test_click_non_numeric_y(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\nclick 50 abc")

    def test_click_too_many_parts(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\nclick 50 50 50")

    def test_click_float_coordinates(self):
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            parse_commands("Commands:\nclick 1.5 2.5")
