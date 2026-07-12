from model.board import Board
from model.position import Position
from rules.piece_rules import MOVE_RULES, MoveContext, MoveRule

OK = "ok"


class MoveValidation:
    """Rule-level rejection reasons returned by RuleEngine.evaluate_move."""
    OUT_OF_BOUNDS = "out_of_bounds"
    NO_PIECE = "no_piece"
    UNKNOWN_KIND = "unknown_kind"
    SAME_COLOR_DESTINATION = "same_color_destination"
    INVALID_SHAPE = "invalid_shape"
    PATH_BLOCKED = "path_blocked"


class RuleEngine:

    def rule_for(self, kind: str) -> MoveRule | None:
        return MOVE_RULES.get(kind)

    def evaluate_move(self, board: Board, frm: Position, to: Position) -> str:
        """Returns OK, or one of the MoveValidation reason strings."""
        if not (board.in_bounds(frm) and board.in_bounds(to)):
            return MoveValidation.OUT_OF_BOUNDS
        piece = board.piece_at(frm)
        if piece is None:
            return MoveValidation.NO_PIECE
        rule = self.rule_for(piece.kind)
        if rule is None:
            return MoveValidation.UNKNOWN_KIND
        dest = board.piece_at(to)
        if dest is not None and dest.color == piece.color:
            return MoveValidation.SAME_COLOR_DESTINATION
        dr, dc = to.row - frm.row, to.col - frm.col
        predicate = rule.capture_ok if (dest is not None and rule.capture_ok is not None) else rule.shape_ok
        ctx = MoveContext(frm=frm, to=to, board=board, start_row_offset=rule.start_row_offset)
        if not predicate(dr, dc, piece.color, ctx):
            return MoveValidation.INVALID_SHAPE
        if rule.sliding and not board.path_clear(frm, to):
            return MoveValidation.PATH_BLOCKED
        return OK

    def is_legal_move(self, board: Board, frm: Position, to: Position) -> bool:
        return self.evaluate_move(board, frm, to) == OK

    def on_arrive(self, piece, board: Board) -> None:
        rule = self.rule_for(piece.kind)
        if rule and rule.on_arrive:
            rule.on_arrive(piece, board)
