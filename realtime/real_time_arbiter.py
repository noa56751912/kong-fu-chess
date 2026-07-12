from model.board import Board
from model.game_state import GameState
from model.piece import Piece, PieceState
from model.position import Position
from realtime.motion import (
    ARRIVAL, EVENT_ORDER, Event, JUMP_DURATION_MS, Jumping, LANDING,
    MS_PER_SQUARE, Moving, PendingJump, PendingMove,
)
from rules.piece_rules import MOVE_RULES


def _run_on_arrive(piece: Piece, board: Board) -> None:
    rule = MOVE_RULES.get(piece.kind)
    if rule and rule.on_arrive:
        rule.on_arrive(piece, board)


def _apply_capture(captured: Piece, game_state: GameState, arbiter: "RealTimeArbiter") -> None:
    """Single funnel for every capture: checks the win conditions."""
    if any(cond(captured) for cond in game_state.win_conditions):
        game_state.game_over = True
        arbiter.pending.clear()
        arbiter.status.clear()


def _resolve_airborne_defense(arbiter: "RealTimeArbiter", game_state: GameState, event: Event) -> bool:
    """An enemy arriving on an airborne piece's cell is captured mid-air:
    the jumper does not move and keeps its cell."""
    move: PendingMove = event.activity
    defender_status = arbiter.status.get(move.to)
    if not isinstance(defender_status, Jumping):
        return False
    if defender_status.jump.piece.color == move.piece.color:
        return False
    arbiter.pending.remove(move)
    arbiter.status.pop(move.frm, None)
    game_state.board.remove_piece(move.piece)
    move.piece.state = PieceState.CAPTURED
    _apply_capture(move.piece, game_state, arbiter)
    return True


def _resolve_move_arrival(arbiter: "RealTimeArbiter", game_state: GameState, event: Event) -> bool:
    """Default arrival: the piece lands on its destination, capturing any occupant."""
    move: PendingMove = event.activity
    board = game_state.board
    captured = board.move_piece(move.piece, move.to)
    arbiter.pending.remove(move)
    arbiter.status.pop(move.frm, None)
    move.piece.state = PieceState.IDLE
    if captured is not None:
        captured.state = PieceState.CAPTURED
    _run_on_arrive(move.piece, board)   # promotion runs after the captured snapshot is taken
    if captured is not None:
        _apply_capture(captured, game_state, arbiter)
    return True


def _resolve_jump_landing(arbiter: "RealTimeArbiter", game_state: GameState, event: Event) -> bool:
    """Default landing: the jump ends and the piece is idle again on its cell."""
    jump: PendingJump = event.activity
    jump.piece.state = PieceState.IDLE
    arbiter.status.pop(jump.pos, None)
    return True


RESOLVERS = {
    ARRIVAL: [_resolve_airborne_defense, _resolve_move_arrival],
    LANDING: [_resolve_jump_landing],
}


class RealTimeArbiter:

    def __init__(self):
        self.pending: list[PendingMove] = []
        self.status: dict[Position, object] = {}

    def is_busy(self, pos: Position) -> bool:
        return pos in self.status

    def schedule_move(self, piece: Piece, frm: Position, to: Position, now_ms: int) -> PendingMove:
        distance = max(abs(to.row - frm.row), abs(to.col - frm.col))
        move = PendingMove(piece, frm, to, now_ms + distance * MS_PER_SQUARE)
        self.pending.append(move)
        self.status[frm] = Moving(move)
        piece.state = PieceState.MOVING
        return move

    def schedule_jump(self, piece: Piece, pos: Position, now_ms: int) -> PendingJump:
        jump = PendingJump(piece, pos, now_ms + JUMP_DURATION_MS)
        self.status[pos] = Jumping(jump)
        piece.state = PieceState.MOVING
        return jump

    def settle(self, game_state: GameState) -> None:
        if game_state.game_over:
            return
        events = self._due_events(game_state.clock_ms)
        for event in sorted(events, key=self._sort_key):
            if game_state.game_over:
                return
            if not self._is_live(event):
                self._discard(event)
                continue
            for resolver in RESOLVERS[event.kind]:
                if resolver(self, game_state, event):
                    break

    def _due_events(self, clock_ms: int) -> list[Event]:
        due_moves = [Event(m.arrive_time, ARRIVAL, m)
                     for m in self.pending if m.arrive_time <= clock_ms]
        due_jumps = [Event(s.jump.end_time, LANDING, s.jump)
                     for s in self.status.values()
                     if isinstance(s, Jumping) and s.jump.end_time <= clock_ms]
        return due_moves + due_jumps

    def _is_live(self, event: Event) -> bool:
        return event.activity.piece.state is not PieceState.CAPTURED

    def _discard(self, event: Event) -> None:
        if event.kind == ARRIVAL and event.activity in self.pending:
            self.pending.remove(event.activity)

    @staticmethod
    def _sort_key(event: Event):
        return event.time, EVENT_ORDER[event.kind]
