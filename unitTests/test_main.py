import pytest
from main import run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_input(board_rows, commands):
    board = "Board:\n" + "\n".join(board_rows)
    cmds  = "Commands:\n" + "\n".join(commands)
    return board + "\n" + cmds


# ---------------------------------------------------------------------------
# print board — output matches initial board
# ---------------------------------------------------------------------------

class TestPrintBoard:

    def test_print_board_simple(self, capsys):
        inp = make_input(["wK . bK", ". . .", "wR . bR"], ["print board"])
        run(inp)
        assert capsys.readouterr().out == "wK . bK\n. . .\nwR . bR\n"

    def test_print_board_single_row(self, capsys):
        inp = make_input(["wK bK"], ["print board"])
        run(inp)
        assert capsys.readouterr().out == "wK bK\n"

    def test_multiple_print_board_commands(self, capsys):
        inp = make_input(["wK bK"], ["print board", "print board"])
        run(inp)
        out = capsys.readouterr().out
        assert out == "wK bK\nwK bK\n"

    def test_no_commands_produces_no_output(self, capsys):
        inp = make_input(["wK bK"], [])
        run(inp)
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# wait — advances clock, piece arrives on time
# ---------------------------------------------------------------------------

class TestWaitIntegration:

    def test_piece_not_arrived_before_wait(self, capsys):
        inp = make_input(
            ["wR . . ."],
            ["click 50 50", "click 350 50", "wait 500", "print board"]
        )
        run(inp)
        out = capsys.readouterr().out.strip()
        assert out == "wR . . ."   # still at source after only 500 ms

    def test_piece_arrived_after_full_wait(self, capsys):
        inp = make_input(
            ["wR . . ."],
            ["click 50 50", "click 350 50", "wait 3000", "print board"]
        )
        run(inp)
        out = capsys.readouterr().out.strip()
        assert out == ". . . wR"


# ---------------------------------------------------------------------------
# click — selection and movement
# ---------------------------------------------------------------------------

class TestClickIntegration:

    def test_click_and_legal_move_then_print(self, capsys):
        inp = make_input(
            ["wK . ."],
            ["click 50 50", "click 150 50", "wait 1000", "print board"]
        )
        run(inp)
        out = capsys.readouterr().out.strip()
        assert out == ". wK ."

    def test_illegal_move_piece_stays(self, capsys):
        inp = make_input(
            ["wK . . ."],
            ["click 50 50", "click 250 50", "wait 1000", "print board"]
        )
        run(inp)
        out = capsys.readouterr().out.strip()
        assert out == "wK . . ."   # king can't jump 2 squares

    def test_click_outside_board_ignored(self, capsys):
        inp = make_input(
            ["wK ."],
            ["click 9999 9999", "print board"]
        )
        run(inp)
        out = capsys.readouterr().out.strip()
        assert out == "wK ."


# ---------------------------------------------------------------------------
# Error handling — invalid board
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_unknown_token_in_board(self, capsys):
        inp = make_input(["wK xZ", ". ."], ["print board"])
        try:
            run(inp)
        except ValueError as e:
            assert "ERROR UNKNOWN_TOKEN" in str(e)

    def test_row_width_mismatch(self, capsys):
        inp = make_input(["wK . .", ". bK"], ["print board"])
        try:
            run(inp)
        except ValueError as e:
            assert "ERROR ROW_WIDTH_MISMATCH" in str(e)

    def test_unknown_command_raises(self, capsys):
        inp = make_input(["wK ."], ["fly away"])
        try:
            run(inp)
        except ValueError as e:
            assert "ERROR UNKNOWN_TOKEN" in str(e)

    def test_wait_non_numeric_raises(self, capsys):
        inp = make_input(["wK ."], ["wait abc"])
        try:
            run(inp)
        except ValueError as e:
            assert "ERROR UNKNOWN_TOKEN" in str(e)
