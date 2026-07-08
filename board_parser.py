def parse_board(input_text):
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


def validate_board(board_lines):
    # Valid characters: pieces (both cases), empty square markers,
    # board border/separator chars, digits, column letters, and whitespace
    valid_chars = set(
        'KQRBNPkqrbnp'   # chess pieces
        'wbWB'           # color prefixes (white/black)
        '.'              # empty square
        ' \t'            # whitespace
        '|+-'            # border separators
        '0123456789'     # rank numbers
        'abcdefghABCDEFGH'  # file letters
    )

    non_empty = [line for line in board_lines if line.strip()]

    # All ranks must have the same number of tokens
    if len(set(len(line.split()) for line in non_empty)) > 1:
        raise ValueError("ERROR ROW_WIDTH_MISMATCH")

    for line in non_empty:
        for ch in line:
            if ch not in valid_chars:
                raise ValueError("ERROR UNKNOWN_TOKEN")


def board_lines_to_grid(board_lines):
    return [line.split() for line in board_lines if line.strip()]



