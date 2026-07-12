from model.board import Board


def print_board(board: Board) -> None:
    for row in board.to_grid():
        print(' '.join(row))
