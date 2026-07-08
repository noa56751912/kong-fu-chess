import sys

from board_parser import parse_board, validate_board, board_lines_to_grid
from command_parser import parse_commands
from game import ChessGame


def run(input_text):
    board_lines = parse_board(input_text)
    validate_board(board_lines)
    grid = board_lines_to_grid(board_lines)
    commands = parse_commands(input_text)
    game = ChessGame(grid)
    for cmd in commands:
        if cmd[0] == 'print_board':
            game.print_board()
        elif cmd[0] == 'wait':
            game.wait(cmd[1])
        elif cmd[0] == 'click':
            game.click(cmd[1], cmd[2])


if __name__ == '__main__':# pragma: no cover
    try:
        run(sys.stdin.read())
    except ValueError as e:
        print(e)
