from typing import Callable, NamedTuple

CELL_SIZE = 100
MS_PER_SQUARE = 1000
EMPTY = '.'
WHITE = 'w'
BLACK = 'b'


class PendingMove(NamedTuple):
    piece: str
    from_r: int
    from_c: int
    to_r: int
    to_c: int
    arrive_time: int


class MoveRule(NamedTuple):
    shape_ok: Callable[[int, int, str], bool]
    sliding: bool
    capture_ok: Callable[[int, int, str], bool] = None  # None = same as shape_ok


def _king_shape(dr, dc, color):   return max(abs(dr), abs(dc)) == 1
def _knight_shape(dr, dc, color): return sorted([abs(dr), abs(dc)]) == [1, 2]
def _rook_shape(dr, dc, color):   return dr == 0 or dc == 0
def _bishop_shape(dr, dc, color): return abs(dr) == abs(dc) and dr != 0
def _queen_shape(dr, dc, color):  return _rook_shape(dr, dc, color) or _bishop_shape(dr, dc, color)
def _pawn_shape(dr, dc, color):   return dc == 0 and dr == (-1 if color == WHITE else 1)
def _pawn_capture(dr, dc, color): return abs(dc) == 1 and dr == (-1 if color == WHITE else 1)


MOVE_RULES = {
    'K': MoveRule(shape_ok=_king_shape,   sliding=False),
    'N': MoveRule(shape_ok=_knight_shape, sliding=False),
    'R': MoveRule(shape_ok=_rook_shape,   sliding=True),
    'B': MoveRule(shape_ok=_bishop_shape, sliding=True),
    'Q': MoveRule(shape_ok=_queen_shape,  sliding=True),
    'P': MoveRule(shape_ok=_pawn_shape,   sliding=False, capture_ok=_pawn_capture),
}


def _piece_type(token):
    """Return the piece-type letter ('K','Q','R','B','N','P') or None for empty."""
    return token[-1].upper() if token != EMPTY else None


def _is_path_clear(grid, r1, c1, r2, c2):
    """Return True if every cell strictly between (r1,c1) and (r2,c2) is empty."""
    dr = r2 - r1
    dc = c2 - c1
    step_r = (dr > 0) - (dr < 0)   # sign: -1, 0, or 1
    step_c = (dc > 0) - (dc < 0)
    r, c = r1 + step_r, c1 + step_c
    while (r, c) != (r2, c2):
        if grid[r][c] != EMPTY:
            return False
        r += step_r
        c += step_c
    return True


def _is_legal_move(grid, r1, c1, r2, c2):
    """Return True if the piece at (r1,c1) can legally move to (r2,c2)."""
    token = grid[r1][c1]
    piece = _piece_type(token)
    rule = MOVE_RULES.get(piece)
    if rule is None:
        return False
    color = token[0] if len(token) == 2 else None
    dr, dc = r2 - r1, c2 - c1
    is_capture = grid[r2][c2] != EMPTY
    check = rule.capture_ok if (is_capture and rule.capture_ok is not None) else rule.shape_ok
    if not check(dr, dc, color):
        return False
    if rule.sliding and not _is_path_clear(grid, r1, c1, r2, c2):
        return False
    return True


def _color(token):
    """Return the color prefix of a piece token, or None for empty squares."""
    if token.startswith(WHITE):
        return WHITE
    if token.startswith(BLACK):
        return BLACK
    return None


class ChessGame:
    def __init__(self, grid):
        self.grid = [row[:] for row in grid]
        self.rows = len(grid)
        self.cols = len(grid[0]) if self.rows > 0 else 0
        self.selection = None  # (row, col) of selected piece
        self.clock_ms = 0
        self.pending: list = []

    def _settle_moves(self):
        arrived = [m for m in self.pending if m.arrive_time <= self.clock_ms]
        self.pending = [m for m in self.pending if m.arrive_time > self.clock_ms]
        for m in arrived:
            self.grid[m.from_r][m.from_c] = EMPTY
            self.grid[m.to_r][m.to_c] = m.piece

    def _pixel_to_cell(self, x, y):
        col = x // CELL_SIZE
        row = y // CELL_SIZE
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return row, col
        return None

    def _is_in_flight(self, row, col):
        return any(m.from_r == row and m.from_c == col for m in self.pending)

    def _try_schedule_move(self, from_r, from_c, to_r, to_c):
        if _is_legal_move(self.grid, from_r, from_c, to_r, to_c):
            piece = self.grid[from_r][from_c]
            distance = max(abs(to_r - from_r), abs(to_c - from_c))
            arrive_time = self.clock_ms + distance * MS_PER_SQUARE
            self.pending.append(PendingMove(piece, from_r, from_c, to_r, to_c, arrive_time))
            self.selection = None

    def _handle_cell_click(self, row, col):
        color = _color(self.grid[row][col])
        if self.selection is None:
            if color is not None:
                self.selection = (row, col)
        else:
            sel_row, sel_col = self.selection
            if color == _color(self.grid[sel_row][sel_col]):
                self.selection = (row, col)
            else:
                self._try_schedule_move(sel_row, sel_col, row, col)

    def click(self, x, y):
        self._settle_moves()
        cell = self._pixel_to_cell(x, y)
        if cell is None:
            return
        row, col = cell
        if self._is_in_flight(row, col):
            return
        self._handle_cell_click(row, col)

    def wait(self, ms):
        self.clock_ms += ms
        self._settle_moves()

    def print_board(self):
        self._settle_moves()
        for row in self.grid:
            print(' '.join(row))
