from typing import Callable, NamedTuple

from engine import ARRIVAL, LANDING, Event, resolve_events
from statuses import Moving

CELL_SIZE = 100
MS_PER_SQUARE = 1000
EMPTY = '.'
WHITE = 'w'
BLACK = 'b'
KING  = 'K'

WIN_CONDITIONS = [
    lambda captured: _piece_type(captured) == KING,
]


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
    start_row_offset: int = None  # rows from the piece's starting edge (e.g. 1 = second row); None = not applicable
    on_arrive: Callable = None    # (piece, to_r, board_rows) -> final token to place; None = no transformation


def _king_shape(dr, dc, color, **ctx):   return max(abs(dr), abs(dc)) == 1
def _knight_shape(dr, dc, color, **ctx): return sorted([abs(dr), abs(dc)]) == [1, 2]
def _rook_shape(dr, dc, color, **ctx):   return dr == 0 or dc == 0
def _bishop_shape(dr, dc, color, **ctx): return abs(dr) == abs(dc) and dr != 0
def _queen_shape(dr, dc, color, **ctx):  return _rook_shape(dr, dc, color) or _bishop_shape(dr, dc, color)
def _pawn_capture(dr, dc, color, **ctx): return abs(dc) == 1 and dr == (-1 if color == WHITE else 1)


def _pawn_shape(dr, dc, color, **ctx):
    if dc != 0:
        return False
    direction = -1 if color == WHITE else 1
    if dr == direction:
        return True
    if dr != 2 * direction:
        return False
    start_row_offset = ctx.get('start_row_offset')
    if start_row_offset is None:
        return False
    board_rows = ctx.get('board_rows')
    from_r = ctx.get('from_r')
    from_c = ctx.get('from_c')
    grid = ctx.get('grid')
    start_row = (board_rows - 1 - start_row_offset) if color == WHITE else start_row_offset
    if from_r != start_row:
        return False
    return _is_path_clear(grid, from_r, from_c, from_r + dr, from_c)


def _pawn_promote(piece, to_r, board_rows):
    """Return the queen token if the pawn reached the last row, otherwise piece unchanged."""
    color = _color(piece)
    last_row = 0 if color == WHITE else board_rows - 1
    return color + 'Q' if to_r == last_row else piece


MOVE_RULES = {
    'K': MoveRule(shape_ok=_king_shape,   sliding=False),
    'N': MoveRule(shape_ok=_knight_shape, sliding=False),
    'R': MoveRule(shape_ok=_rook_shape,   sliding=True),
    'B': MoveRule(shape_ok=_bishop_shape, sliding=True),
    'Q': MoveRule(shape_ok=_queen_shape,  sliding=True),
    'P': MoveRule(shape_ok=_pawn_shape,   sliding=False, capture_ok=_pawn_capture,
                  start_row_offset=0, on_arrive=_pawn_promote),
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
    ctx = {
        'from_r': r1,
        'from_c': c1,
        'board_rows': len(grid),
        'grid': grid,
        'start_row_offset': rule.start_row_offset,
    }
    if not check(dr, dc, color, **ctx):
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


def _resolve_move_arrival(game, event):
    """Default arrival: the piece lands on its destination, capturing any occupant."""
    move = event.activity
    captured = game.grid[move.to_r][move.to_c]
    rule = MOVE_RULES.get(_piece_type(move.piece))
    final_piece = rule.on_arrive(move.piece, move.to_r, game.rows) if rule and rule.on_arrive else move.piece
    game.pending.remove(move)
    game.status.pop((move.from_r, move.from_c), None)
    game._cancel_activity_at(move.to_r, move.to_c)
    game.grid[move.from_r][move.from_c] = EMPTY
    game.grid[move.to_r][move.to_c] = final_piece
    game._apply_capture(captured)
    return True


EVENT_RESOLVERS = {
    ARRIVAL: [_resolve_move_arrival],
    LANDING: [],
}


class ChessGame:
    def __init__(self, grid, win_conditions=None):
        self.grid = [row[:] for row in grid]
        self.rows = len(grid)
        self.cols = len(grid[0]) if self.rows > 0 else 0
        self.selection = None  # (row, col) of selected piece
        self.clock_ms = 0
        self.pending: list = []
        self.status: dict = {}  # (row, col) -> status object; absence means idle
        self.game_over = False
        self.win_conditions = win_conditions if win_conditions is not None else WIN_CONDITIONS

    def _due_events(self):
        return [Event(m.arrive_time, ARRIVAL, m) for m in self.pending if m.arrive_time <= self.clock_ms]

    def _is_live(self, event):
        return event.activity in self.pending

    def _settle_events(self):
        if self.game_over:
            return
        resolve_events(self, self._due_events(), EVENT_RESOLVERS, self._is_live)

    def _apply_capture(self, captured):
        """Single funnel for every capture: checks the win conditions."""
        if any(cond(captured) for cond in self.win_conditions):
            self.game_over = True
            self.pending.clear()
            self.status.clear()

    def _cancel_activity_at(self, row, col):
        """Invalidate whatever the piece at (row, col) had scheduled — a captured
        piece must not act later, so its still-queued events die with it."""
        status = self.status.pop((row, col), None)
        if isinstance(status, Moving) and status.move in self.pending:
            self.pending.remove(status.move)

    def _pixel_to_cell(self, x, y):
        col = x // CELL_SIZE
        row = y // CELL_SIZE
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return row, col
        return None

    def _is_in_flight(self, row, col):
        return isinstance(self.status.get((row, col)), Moving)

    def _try_schedule_move(self, from_r, from_c, to_r, to_c):
        if self.game_over:
            return
        if _is_legal_move(self.grid, from_r, from_c, to_r, to_c):
            piece = self.grid[from_r][from_c]
            distance = max(abs(to_r - from_r), abs(to_c - from_c))
            arrive_time = self.clock_ms + distance * MS_PER_SQUARE
            move = PendingMove(piece, from_r, from_c, to_r, to_c, arrive_time)
            self.pending.append(move)
            self.status[(from_r, from_c)] = Moving(move)
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
        self._settle_events()
        if self.game_over:
            return
        cell = self._pixel_to_cell(x, y)
        if cell is None:
            return
        row, col = cell
        if self._is_in_flight(row, col):
            return
        self._handle_cell_click(row, col)

    def wait(self, ms):
        self.clock_ms += ms
        self._settle_events()

    def print_board(self):
        self._settle_events()
        for row in self.grid:
            print(' '.join(row))
