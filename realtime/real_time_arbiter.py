from typing import Optional

from bus.event_bus import EventBus
from model.board import Board
from model.game_state import GameState
from model.piece import Piece, POINT_VALUES
from model.position import Position
from rules.piece_config import IDLE, JUMP, MOVE, PIECE_CONFIG
from realtime.motion import (
    ARRIVAL, EVENT_ORDER, Event, Jumping, LANDING, Moving, PendingJump,
    PendingMove, PendingRest, REST_DONE, jump_duration_ms, move_duration_ms,
    rest_duration_ms,
)
from rules.piece_rules import MOVE_RULES


def _run_on_arrive(piece: Piece, board: Board) -> None:
    """Run the piece kind's on-arrive rule, if it has one (e.g. pawn promotion)."""
    rule = MOVE_RULES.get(piece.kind)
    if rule and rule.on_arrive:
        rule.on_arrive(piece, board)


def _apply_capture(captured: Piece, capturer_color: str, game_state: GameState, arbiter: "RealTimeArbiter") -> None:
    """Single funnel for every capture: scores it, then checks the win conditions."""
    arbiter.bus.publish('piece.captured', {
        'piece_id': captured.id, 'capturer_color': capturer_color,
        'pos': captured.cell, 'clock_ms': game_state.clock_ms,
    })
    game_state.score[capturer_color] += POINT_VALUES[captured.kind]
    arbiter.bus.publish('score.changed', {'color': capturer_color, 'score': game_state.score[capturer_color]})
    if any(cond(captured) for cond in game_state.win_conditions):
        game_state.game_over = True
        game_state.winner = capturer_color
        arbiter.pending.clear()
        arbiter.rests.clear()
        arbiter.status.clear()
        arbiter.bus.publish('game.over', {'winner': capturer_color, 'reason': 'capture'})


def _advance_state(arbiter: "RealTimeArbiter", game_state: GameState, piece: Piece, finished_state: str) -> None:
    """A piece just finished `finished_state` - consult its config for what
    comes next. If the next state is itself timed (a rest), schedule its
    expiry; if it's idle, the piece just waits for player input."""
    next_state = PIECE_CONFIG.get(piece.kind, piece.color, finished_state).next_state
    piece.state = next_state
    # A single generic event regardless of which transition caused it (move
    # finishing, jump finishing, or a rest expiring) - a network client just
    # needs to know "this piece is now in state X" to keep its local mirror's
    # sprite/cooldown-bar rendering in sync, not why.
    arbiter.bus.publish('piece.state_changed', {'piece_id': piece.id, 'state': next_state})
    if next_state == IDLE:
        return
    end_time = game_state.clock_ms + rest_duration_ms(next_state)
    arbiter.rests.append(PendingRest(piece, next_state, end_time))


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
    move.piece.captured = True
    _apply_capture(move.piece, defender_status.jump.piece.color, game_state, arbiter)
    return True


def _resolve_move_arrival(arbiter: "RealTimeArbiter", game_state: GameState, event: Event) -> bool:
    """Default arrival: the piece lands on its destination, capturing any occupant."""
    move: PendingMove = event.activity
    board = game_state.board
    captured = board.move_piece(move.piece, move.to)
    arbiter.pending.remove(move)
    arbiter.status.pop(move.frm, None)
    _advance_state(arbiter, game_state, move.piece, MOVE)
    if captured is not None:
        captured.captured = True
    _run_on_arrive(move.piece, board)   # promotion runs after the captured snapshot is taken
    arbiter.bus.publish('move.arrived', {
        'piece_id': move.piece.id, 'to': move.to,
        'captured_piece_id': captured.id if captured is not None else None,
    })
    if captured is not None:
        _apply_capture(captured, move.piece.color, game_state, arbiter)
    return True


def _resolve_jump_landing(arbiter: "RealTimeArbiter", game_state: GameState, event: Event) -> bool:
    """Default landing: the jump ends and the piece moves on to its next state."""
    jump: PendingJump = event.activity
    arbiter.status.pop(jump.pos, None)
    _advance_state(arbiter, game_state, jump.piece, JUMP)
    arbiter.bus.publish('jump.landed', {'piece_id': jump.piece.id})
    return True


def _resolve_rest_done(arbiter: "RealTimeArbiter", game_state: GameState, event: Event) -> bool:
    """A cooldown (short/long rest) elapses - advance to whatever its config says is next."""
    rest: PendingRest = event.activity
    arbiter.rests.remove(rest)
    _advance_state(arbiter, game_state, rest.piece, rest.state)
    return True


RESOLVERS = {
    ARRIVAL: [_resolve_airborne_defense, _resolve_move_arrival],
    LANDING: [_resolve_jump_landing],
    REST_DONE: [_resolve_rest_done],
}


class RealTimeArbiter:

    def __init__(self, bus: Optional[EventBus] = None):
        self.pending: list[PendingMove] = []
        self.rests: list[PendingRest] = []
        self.status: dict[Position, object] = {}
        self.bus = bus if bus is not None else EventBus()

    def is_busy(self, pos: Position) -> bool:
        """Return whether a square is currently occupied by an in-progress move or jump."""
        return pos in self.status

    def schedule_move(self, board: Board, piece: Piece, frm: Position, to: Position, now_ms: int) -> PendingMove:
        """Queue a timed move from frm to to, marking the origin square as moving.

        The origin is vacated immediately (not on arrival): once a piece has
        set off, its old square is open to everyone else, and nothing can
        capture it there anymore - only a live occupant of the destination
        can still be captured, resolved fresh when this move actually lands.
        """
        distance = max(abs(to.row - frm.row), abs(to.col - frm.col))
        duration = move_duration_ms(piece.kind, piece.color, distance)
        move = PendingMove(piece, frm, to, now_ms, now_ms + duration)
        self.pending.append(move)
        self.status[frm] = Moving(move)
        piece.state = MOVE
        board.vacate(frm)
        self.bus.publish('move.started', {
            'piece_id': piece.id, 'color': piece.color, 'kind': piece.kind,
            'from': frm, 'to': to, 'start_time': now_ms, 'arrive_time': move.arrive_time,
        })
        return move

    def schedule_jump(self, piece: Piece, pos: Position, now_ms: int) -> PendingJump:
        """Queue a timed in-place jump, marking the square as airborne."""
        duration = jump_duration_ms(piece.kind, piece.color)
        jump = PendingJump(piece, pos, now_ms + duration)
        self.status[pos] = Jumping(jump)
        piece.state = JUMP
        self.bus.publish('jump.started', {
            'piece_id': piece.id, 'pos': pos, 'end_time': jump.end_time,
        })
        return jump

    def settle(self, game_state: GameState) -> None:
        """Resolve every move/jump/rest event that has come due at the game clock's current time."""
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
        """Collect all pending moves, jumps, and rests whose time has come."""
        due_moves = [Event(m.arrive_time, ARRIVAL, m)
                     for m in self.pending if m.arrive_time <= clock_ms]
        due_jumps = [Event(s.jump.end_time, LANDING, s.jump)
                     for s in self.status.values()
                     if isinstance(s, Jumping) and s.jump.end_time <= clock_ms]
        due_rests = [Event(r.end_time, REST_DONE, r)
                     for r in self.rests if r.end_time <= clock_ms]
        return due_moves + due_jumps + due_rests

    def _is_live(self, event: Event) -> bool:
        """Return whether the event's piece is still in play (not captured beforehand)."""
        return not event.activity.piece.captured

    def _discard(self, event: Event) -> None:
        """Drop a stale event whose piece was captured before the event could resolve."""
        if event.kind == ARRIVAL and event.activity in self.pending:
            self.pending.remove(event.activity)
        elif event.kind == REST_DONE and event.activity in self.rests:
            self.rests.remove(event.activity)

    @staticmethod
    def _sort_key(event: Event):
        """Order due events by time, then arrivals before landings before rests on the same tick."""
        return event.time, EVENT_ORDER[event.kind]
