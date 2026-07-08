import pytest
from game import ChessGame, CELL_SIZE, MS_PER_SQUARE, EMPTY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_game(rows, win_conditions=None):
    """Build a ChessGame from a list of space-separated row strings."""
    return ChessGame([r.split() for r in rows], win_conditions=win_conditions)


def cell_center(row, col):
    """Pixel coordinate of the centre of a cell."""
    return col * CELL_SIZE + CELL_SIZE // 2, row * CELL_SIZE + CELL_SIZE // 2


def click(game, row, col):
    x, y = cell_center(row, col)
    game.click(x, y)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

class TestSelection:

    def test_click_piece_selects_it(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        click(game, 0, 0)
        assert game.selection == (0, 0)

    def test_click_empty_no_selection(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        click(game, 0, 1)
        assert game.selection is None

    def test_click_outside_board_ignored(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        game.click(9999, 9999)
        assert game.selection is None

    def test_click_enemy_piece_selects_it(self):
        game = make_game(["bK . .", ". . .", ". . ."])
        click(game, 0, 0)
        assert game.selection == (0, 0)

    def test_reclick_friendly_changes_selection(self):
        game = make_game(["wK . wR", ". . .", ". . ."])
        click(game, 0, 0)   # select wK
        click(game, 0, 2)   # re-select wR (same color)
        assert game.selection == (0, 2)

    def test_illegal_move_keeps_selection(self):
        # King cannot move 2 squares — selection must remain
        game = make_game(["wK . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 0, 2)   # illegal: 2 squares right
        assert game.selection == (0, 0)

    def test_legal_move_clears_selection(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 0, 1)   # legal king move
        assert game.selection is None


# ---------------------------------------------------------------------------
# Time-based movement — piece stays at source until arrival
# ---------------------------------------------------------------------------

class TestTimedMovement:

    def test_piece_still_at_source_before_arrival(self):
        game = make_game(["wR . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 0, 3)           # rook moves 3 squares → 3000 ms travel
        game.wait(1000)             # only 1000 ms passed
        assert game.grid[0][0] == 'wR'   # still at source
        assert game.grid[0][3] == EMPTY  # not yet at dest

    def test_piece_arrives_after_enough_wait(self):
        game = make_game(["wR . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 0, 3)
        game.wait(3000)             # exactly 3000 ms — should arrive
        game.print_board           # trigger settle (call _settle_moves via print)
        # settle is triggered by next click or print_board; call directly via wait chain
        click(game, 0, 3)          # triggers _settle_moves at start of click
        assert game.grid[0][3] == 'wR'
        assert game.grid[0][0] == EMPTY

    def test_travel_time_one_square(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 0, 1)
        assert len(game.pending) == 1
        assert game.pending[0].arrive_time == MS_PER_SQUARE

    def test_travel_time_rook_three_squares(self):
        game = make_game(["wR . . . .", ". . . . .", ". . . . ."])
        click(game, 0, 0)
        click(game, 0, 3)
        assert game.pending[0].arrive_time == 3 * MS_PER_SQUARE

    def test_travel_time_bishop_diagonal(self):
        game = make_game(["wB . . .", ". . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 2, 2)           # 2-square diagonal
        assert game.pending[0].arrive_time == 2 * MS_PER_SQUARE

    def test_travel_time_knight_l_shape(self):
        game = make_game(["wN . . .", ". . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 2, 1)           # Chebyshev distance = max(2,1) = 2
        assert game.pending[0].arrive_time == 2 * MS_PER_SQUARE

    def test_pending_stores_correct_from_and_to(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 1, 1)
        m = game.pending[0]
        assert (m.from_r, m.from_c) == (0, 0)
        assert (m.to_r, m.to_c) == (1, 1)
        assert m.piece == 'wK'


# ---------------------------------------------------------------------------
# In-flight piece protection
# ---------------------------------------------------------------------------

class TestInFlight:

    def test_click_inflight_source_ignored(self):
        game = make_game(["wR . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 0, 3)           # rook in flight
        click(game, 0, 0)           # try to re-select in-flight source
        assert game.selection is None  # click was ignored


# ---------------------------------------------------------------------------
# Piece movement rules — legal moves
# ---------------------------------------------------------------------------

class TestLegalMoves:

    def test_king_moves_one_square(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 1, 1)
        assert len(game.pending) == 1

    def test_rook_moves_along_rank(self):
        game = make_game(["wR . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 0, 3)
        assert len(game.pending) == 1

    def test_rook_moves_along_file(self):
        game = make_game(["wR . .", ". . .", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 3, 0)
        assert len(game.pending) == 1

    def test_bishop_moves_diagonally(self):
        game = make_game(["wB . . .", ". . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 3, 3)
        assert len(game.pending) == 1

    def test_queen_moves_straight(self):
        game = make_game(["wQ . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 0, 3)
        assert len(game.pending) == 1

    def test_queen_moves_diagonal(self):
        game = make_game(["wQ . . .", ". . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 3, 3)
        assert len(game.pending) == 1

    def test_knight_l_shape(self):
        game = make_game(["wN . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 2, 1)
        assert len(game.pending) == 1

    def test_white_pawn_moves_up(self):
        game = make_game([". . .", "wP . .", ". . ."])
        click(game, 1, 0)
        click(game, 0, 0)
        assert len(game.pending) == 1

    def test_black_pawn_moves_down(self):
        game = make_game([". . .", "bP . .", ". . ."])
        click(game, 1, 0)
        click(game, 2, 0)
        assert len(game.pending) == 1

    def test_white_pawn_captures_diagonally(self):
        game = make_game(["bK . .", "wP . .", ". . ."])
        click(game, 1, 0)
        click(game, 0, 1)           # not a piece there, but let's use one
        # reset with actual enemy on diagonal
        game2 = make_game([". bR .", "wP . .", ". . ."])
        click(game2, 1, 0)
        click(game2, 0, 1)
        assert len(game2.pending) == 1


# ---------------------------------------------------------------------------
# Piece movement rules — illegal moves (nothing scheduled)
# ---------------------------------------------------------------------------

class TestIllegalMoves:

    def test_king_cannot_move_two_squares(self):
        game = make_game(["wK . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 0, 2)
        assert len(game.pending) == 0

    def test_rook_cannot_move_diagonally(self):
        game = make_game(["wR . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 1, 1)
        assert len(game.pending) == 0

    def test_bishop_cannot_move_straight(self):
        game = make_game(["wB . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 0, 2)
        assert len(game.pending) == 0

    def test_rook_blocked_by_piece(self):
        game = make_game(["wR wN . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 0, 3)           # wN blocks the path
        assert len(game.pending) == 0

    def test_bishop_blocked_by_piece(self):
        game = make_game(["wB . . .", ". wN . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 2, 2)           # wN at (1,1) blocks diagonal
        assert len(game.pending) == 0

    def test_knight_cannot_move_straight(self):
        game = make_game(["wN . . .", ". . . .", ". . . ."])
        click(game, 0, 0)
        click(game, 0, 2)
        assert len(game.pending) == 0

    def test_white_pawn_cannot_move_down(self):
        game = make_game([". . .", ". wP .", ". . ."])
        click(game, 1, 1)
        click(game, 2, 1)
        assert len(game.pending) == 0

    def test_black_pawn_cannot_move_up(self):
        game = make_game([". . .", ". bP .", ". . ."])
        click(game, 1, 1)
        click(game, 0, 1)
        assert len(game.pending) == 0

    def test_white_pawn_cannot_move_forward_to_occupied(self):
        game = make_game(["bR . .", "wP . .", ". . ."])
        click(game, 1, 0)
        click(game, 0, 0)           # forward blocked by enemy piece
        assert len(game.pending) == 0

    def test_pawn_cannot_capture_on_empty_diagonal(self):
        game = make_game([". . .", "wP . .", ". . ."])
        click(game, 1, 0)
        click(game, 0, 1)           # diagonal but empty — not a capture
        assert len(game.pending) == 0

    def test_empty_cell_unknown_piece_not_scheduled(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        click(game, 0, 1)           # click empty — no selection
        click(game, 0, 2)           # still no selection
        assert len(game.pending) == 0

    def test_piece_with_no_rule_cannot_move(self):
        # 'wX' has no entry in MOVE_RULES — rule is None branch in _is_legal_move
        game = make_game(["wX . .", ". . .", ". . ."])
        click(game, 0, 0)           # select wX
        click(game, 0, 1)           # try to move — no rule exists
        assert len(game.pending) == 0


# ---------------------------------------------------------------------------
# Wait advances clock
# ---------------------------------------------------------------------------

class TestWait:

    def test_wait_advances_clock(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        game.wait(500)
        assert game.clock_ms == 500

    def test_multiple_waits_accumulate(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        game.wait(300)
        game.wait(700)
        assert game.clock_ms == 1000

    def test_piece_arrives_after_accumulated_wait(self):
        game = make_game(["wK . .", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 0, 1)           # 1 square → 1000 ms
        game.wait(500)
        game.wait(500)              # total 1000 ms
        click(game, 0, 1)           # triggers _settle_moves
        assert game.grid[0][1] == 'wK'
        assert game.grid[0][0] == EMPTY


# ---------------------------------------------------------------------------
# Game over — capturing the king
# ---------------------------------------------------------------------------

class TestGameOver:

    def test_game_not_over_initially(self):
        game = make_game(["wK bK .", ". . .", ". . ."])
        assert game.game_over is False

    def test_capturing_king_sets_game_over(self):
        # wR at (0,0), bK at (0,1) — rook captures king in 1000 ms
        game = make_game(["wR bK .", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 0, 1)
        game.wait(1000)             # rook arrives and captures bK
        assert game.game_over is True

    def test_non_king_capture_does_not_end_game(self):
        game = make_game(["wR bQ .", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 0, 1)
        game.wait(1000)
        assert game.game_over is False

    def test_click_after_game_over_is_ignored(self):
        game = make_game(["wR bK .", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 0, 1)
        game.wait(1000)             # game over
        click(game, 0, 2)           # should be completely ignored
        assert game.selection is None
        assert len(game.pending) == 0

    def test_no_new_moves_scheduled_after_game_over(self):
        game = make_game(["wR bK wK", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 0, 1)
        game.wait(1000)             # rook captures bK → game over
        click(game, 0, 2)           # try to move wK
        click(game, 0, 1)
        assert len(game.pending) == 0

    def test_pending_moves_cancelled_on_king_capture(self):
        # Two pieces moving: rook toward king, and another piece already pending
        # King is captured first → the other pending move must be cancelled
        game = make_game(["wR bK wQ . .", ". . . . .", ". . . . ."])
        # Schedule wR → col1 (captures bK in 1000ms)
        click(game, 0, 0)
        click(game, 0, 1)
        # Now manually add a second pending move (wQ → col4, arrives at 3000ms)
        # by temporarily bypassing the single-move guard via direct pending append
        from game import PendingMove, MS_PER_SQUARE
        game.pending.append(PendingMove('wQ', 0, 2, 0, 4, 3000))
        assert len(game.pending) == 2
        game.wait(1000)             # rook arrives, captures king
        assert game.game_over is True
        assert len(game.pending) == 0   # wQ's pending move cancelled

    def test_board_state_frozen_after_game_over(self):
        game = make_game(["wR bK .", ". . .", ". . ."])
        click(game, 0, 0)
        click(game, 0, 1)
        game.wait(1000)
        board_snapshot = [row[:] for row in game.grid]
        game.wait(5000)             # more time passes — nothing should change
        assert game.grid == board_snapshot

    def test_custom_win_condition_queen_capture(self):
        # Custom rule: capturing a queen ends the game
        game = make_game(["wR bQ .", ". . .", ". . ."],
                         win_conditions=[lambda t: t == 'bQ'])
        click(game, 0, 0)
        click(game, 0, 1)
        game.wait(1000)
        assert game.game_over is True

    def test_empty_win_conditions_never_ends_game(self):
        # No win conditions → game never ends even if king captured
        game = make_game(["wR bK .", ". . .", ". . ."],
                         win_conditions=[])
        click(game, 0, 0)
        click(game, 0, 1)
        game.wait(1000)
        assert game.game_over is False
