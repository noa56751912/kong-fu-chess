from dataclasses import dataclass
from typing import Optional

from model.board import Board
from model.game_state import GameState
from model.position import Position
from realtime.real_time_arbiter import RealTimeArbiter
from rules.rule_engine import OK, RuleEngine

GAME_OVER = "game_over"
MOTION_IN_PROGRESS = "motion_in_progress"


@dataclass(frozen=True)
class MoveResult:
    is_accepted: bool
    reason: str


class GameEngine:
    """The sole entry point: every request into the game flows through here."""

    def __init__(self, board: Board, rule_engine: Optional[RuleEngine] = None,
                 arbiter: Optional[RealTimeArbiter] = None, win_conditions=None):
        if win_conditions is None:
            self.state = GameState(board)
        else:
            self.state = GameState(board, win_conditions=list(win_conditions))
        self.rule_engine = rule_engine or RuleEngine()
        self.arbiter = arbiter or RealTimeArbiter()

    @property
    def game_over(self) -> bool:
        return self.state.game_over

    def select(self, pos: Optional[Position]) -> None:
        """Act on a square being selected, regardless of the input device that chose it."""
        if self.state.game_over:
            return
        if pos is None:
            self.state.selection = None   # selecting off the board drops any active selection
            return
        self._handle_selection(pos)

    def jump(self, pos: Optional[Position]) -> None:
        if self.state.game_over or pos is None:
            return
        piece = self.state.board.piece_at(pos)
        if piece is None or not piece.is_selectable:
            return
        self.arbiter.schedule_jump(piece, pos, self.state.clock_ms)

    def wait(self, ms: int) -> None:
        self.state.clock_ms += ms
        self.arbiter.settle(self.state)

    def snapshot(self) -> Board:
        """Returns the board as of the last time-advancing settle - the read side of print_board."""
        return self.state.board

    def _handle_selection(self, pos: Position) -> None:
        piece = self.state.board.piece_at(pos)
        if self.state.selection is None:
            if piece is not None and piece.is_selectable:
                self.state.selection = pos
            return
        sel_piece = self.state.board.piece_at(self.state.selection)
        same_color = piece is not None and piece.color == sel_piece.color
        if same_color:
            if piece.is_selectable:
                self.state.selection = pos
        else:
            self._try_schedule_move(self.state.selection, pos)

    def _try_schedule_move(self, frm: Position, to: Position) -> MoveResult:
        if self.state.game_over:
            return MoveResult(False, GAME_OVER)
        piece = self.state.board.piece_at(frm)
        if piece is not None and not piece.is_selectable:
            return MoveResult(False, MOTION_IN_PROGRESS)
        reason = self.rule_engine.evaluate_move(self.state.board, frm, to)
        if reason != OK:
            return MoveResult(False, reason)
        self.arbiter.schedule_move(piece, frm, to, self.state.clock_ms)
        self.state.selection = None
        return MoveResult(True, OK)
