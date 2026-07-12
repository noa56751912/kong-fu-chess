from model.board import EMPTY, Board
from model.position import Position

VALID_CHARS = set(
    'KQRBNPkqrbnp'      # chess pieces
    'wbWB'              # color prefixes (white/black)
    '.'                 # empty square
    ' \t'               # whitespace
    '|+-'               # border separators
    '0123456789'        # rank numbers
    'abcdefghABCDEFGH'  # file letters
)


def parse_board(input_text: str) -> list[str]:
    lines = input_text.splitlines()
    board_lines = []
    in_board = False
    for line in lines:
        if line.strip() == 'Board:':
            in_board = True
            continue
        if line.strip() == 'Commands:':
            break
        if in_board:
            board_lines.append(line)
    return board_lines


def validate_board(board_lines: list[str]) -> None:
    non_empty = [line for line in board_lines if line.strip()]

    if len(set(len(line.split()) for line in non_empty)) > 1:
        raise ValueError("ERROR ROW_WIDTH_MISMATCH")

    for line in non_empty:
        for ch in line:
            if ch not in VALID_CHARS:
                raise ValueError("ERROR UNKNOWN_TOKEN")


def board_lines_to_grid(board_lines: list[str]) -> list[list[str]]:
    return [line.split() for line in board_lines if line.strip()]


def build_board(grid: list[list[str]]) -> Board:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    board = Board(rows, cols)
    for r, row in enumerate(grid):
        for c, token in enumerate(row):
            if token != EMPTY:
                color, kind = token[0], token[1]
                board.spawn_piece(color, kind, Position(r, c))
    return board
