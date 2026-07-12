from pathlib import Path

import pytest

import app

SCRIPTS_DIR = Path(__file__).parent / "scripts"


def _load_kfc(path: Path) -> tuple[str, str]:
    text = path.read_text()
    script_text, _, expected_output = text.partition("\nExpected:\n")
    return script_text, expected_output


@pytest.mark.parametrize("kfc_path", sorted(SCRIPTS_DIR.glob("*.kfc")), ids=lambda p: p.stem)
def test_kfc_script_matches_expected_output(kfc_path, capsys):
    script_text, expected_output = _load_kfc(kfc_path)
    app.run(script_text)
    assert capsys.readouterr().out == expected_output


class TestErrorPropagation:

    def test_unknown_token_in_board(self):
        text = "Board:\nwK xZ\n. .\nCommands:\nprint board"
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            app.run(text)

    def test_row_width_mismatch(self):
        text = "Board:\nwK . .\n. bK\nCommands:\nprint board"
        with pytest.raises(ValueError, match="ERROR ROW_WIDTH_MISMATCH"):
            app.run(text)

    def test_unknown_command_raises(self):
        text = "Board:\nwK .\nCommands:\nfly away"
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            app.run(text)

    def test_wait_non_numeric_raises(self):
        text = "Board:\nwK .\nCommands:\nwait abc"
        with pytest.raises(ValueError, match="ERROR UNKNOWN_TOKEN"):
            app.run(text)
