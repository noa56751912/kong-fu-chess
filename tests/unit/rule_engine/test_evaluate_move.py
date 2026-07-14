from model.board import Board
from model.piece import BISHOP, BLACK, KING, KNIGHT, PAWN, QUEEN, ROOK, WHITE
from rules.piece_config import MOVE
from model.position import Position
from rules.rule_engine import OK, MoveValidation, RuleEngine


def make_engine():
    return RuleEngine()


class TestOutOfBounds:

    def test_source_out_of_bounds(self):
        board = Board(3, 3)
        assert make_engine().evaluate_move(board, Position(-1, 0), Position(0, 0)) == MoveValidation.OUT_OF_BOUNDS

    def test_destination_out_of_bounds(self):
        board = Board(3, 3)
        board.spawn_piece(WHITE, KING, Position(0, 0))
        assert make_engine().evaluate_move(board, Position(0, 0), Position(3, 3)) == MoveValidation.OUT_OF_BOUNDS


class TestNoPiece:

    def test_empty_source_cell(self):
        board = Board(3, 3)
        assert make_engine().evaluate_move(board, Position(0, 0), Position(1, 1)) == MoveValidation.NO_PIECE


class TestUnknownKind:

    def test_piece_with_no_rule(self):
        board = Board(3, 3)
        board.spawn_piece(WHITE, 'X', Position(0, 0))
        assert make_engine().evaluate_move(board, Position(0, 0), Position(0, 1)) == MoveValidation.UNKNOWN_KIND


class TestSameColorDestination:

    def test_blocks_move_onto_friendly_piece(self):
        board = Board(3, 3)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(WHITE, KING, Position(0, 1))
        result = make_engine().evaluate_move(board, Position(0, 0), Position(0, 1))
        assert result == MoveValidation.SAME_COLOR_DESTINATION


class TestInvalidShape:

    def test_king_two_squares_is_invalid_shape(self):
        board = Board(3, 3)
        board.spawn_piece(WHITE, KING, Position(0, 0))
        assert make_engine().evaluate_move(board, Position(0, 0), Position(0, 2)) == MoveValidation.INVALID_SHAPE

    def test_bishop_straight_is_invalid_shape(self):
        board = Board(3, 3)
        board.spawn_piece(WHITE, BISHOP, Position(0, 0))
        assert make_engine().evaluate_move(board, Position(0, 0), Position(0, 2)) == MoveValidation.INVALID_SHAPE


class TestPathBlocked:

    def test_rook_blocked_by_piece(self):
        board = Board(1, 4)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(WHITE, KNIGHT, Position(0, 1))
        result = make_engine().evaluate_move(board, Position(0, 0), Position(0, 3))
        assert result == MoveValidation.PATH_BLOCKED


class TestBusyPieceIsNoLongerRuleEngineConcern:

    def test_moving_piece_is_still_shape_legal_at_rule_level(self):
        # Busy/motion-in-progress is an application-level concern (GameEngine),
        # not something RuleEngine.evaluate_move rejects on its own.
        board = Board(3, 3)
        piece = board.spawn_piece(WHITE, KING, Position(0, 0))
        piece.state = MOVE
        assert make_engine().evaluate_move(board, Position(0, 0), Position(0, 1)) == OK


class TestAccepted:

    def test_legal_move_returns_ok(self):
        board = Board(3, 3)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        assert make_engine().evaluate_move(board, Position(0, 0), Position(0, 2)) == OK

    def test_capture_of_enemy_piece_is_ok(self):
        board = Board(3, 3)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        board.spawn_piece(BLACK, QUEEN, Position(0, 2))
        assert make_engine().evaluate_move(board, Position(0, 0), Position(0, 2)) == OK

    def test_is_legal_move_wraps_bool(self):
        board = Board(3, 3)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        engine = make_engine()
        assert engine.is_legal_move(board, Position(0, 0), Position(0, 2)) is True
        assert engine.is_legal_move(board, Position(0, 0), Position(1, 1)) is False


class TestOnArrive:

    def test_promotes_pawn_via_rule_hook(self):
        from model.piece import PAWN
        board = Board(2, 1)
        piece = board.spawn_piece(WHITE, PAWN, Position(0, 0))
        make_engine().on_arrive(piece, board)
        assert piece.kind == QUEEN

    def test_non_pawn_unaffected(self):
        board = Board(2, 1)
        piece = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        make_engine().on_arrive(piece, board)
        assert piece.kind == ROOK


class TestPawnDoubleFromStartRow:
    """On a 5-row board, pawns start one row in from the back rank (row 3
    for white, row 1 for black), not on the back rank itself."""

    def test_white_pawn_double_from_start_valid(self):
        board = Board(5, 1)
        board.spawn_piece(WHITE, PAWN, Position(3, 0))
        assert make_engine().is_legal_move(board, Position(3, 0), Position(1, 0)) is True

    def test_black_pawn_double_from_start_valid(self):
        board = Board(5, 1)
        board.spawn_piece(BLACK, PAWN, Position(1, 0))
        assert make_engine().is_legal_move(board, Position(1, 0), Position(3, 0)) is True

    def test_white_pawn_double_from_non_start_invalid(self):
        board = Board(5, 1)
        board.spawn_piece(WHITE, PAWN, Position(4, 0))
        assert make_engine().is_legal_move(board, Position(4, 0), Position(2, 0)) is False
