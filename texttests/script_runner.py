from boardio import board_parser, board_printer
from engine.game_engine import GameEngine
from input.controller import Controller
from texttests import script_parser


def run(input_text: str) -> None:
    lines = board_parser.parse_board(input_text)
    board_parser.validate_board(lines)
    board = board_parser.build_board(board_parser.board_lines_to_grid(lines))
    engine = GameEngine(board)
    controller = Controller(engine)

    for cmd in script_parser.parse_commands(input_text):
        kind, *args = cmd
        if kind == 'print_board':
            board_printer.print_board(engine.snapshot())
        elif kind == 'wait':
            engine.wait(*args)
        elif kind == 'click':
            controller.click(*args)
        elif kind == 'jump':
            controller.jump(*args)
