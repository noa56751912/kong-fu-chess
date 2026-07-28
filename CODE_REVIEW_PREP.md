# Kong Fu Chess — Code Review Prep (Q&A)

Goal: be able to defend every design decision in this codebase as if you wrote it, with
extra depth on the client/server architecture. Organized in steps — go through them in
order, or jump to the layer you're least confident on.

---

## STEP 1 — Core Model & Rules (`model/`, `rules/`)

**Q1. Why is `Board` backed by `dict[Position, Piece]` instead of a 2D array?**
A: Only occupied squares need an entry, and `Position` is a frozen, hashable dataclass
so it works directly as a dict key. Lookup (`piece_at`), removal, and "is this square
empty" are all O(1) either way, but the dict avoids pre-allocating/filling a full
rows×cols grid with `None`s and makes `Board.__iter__` naturally yield only real pieces.

**Q2. What's the difference between `Board.vacate()`, `_release()`, and `move_piece()`?**
A: `vacate(pos)` removes whatever is at `pos` *by position* — called the instant a move
is *scheduled* (not when it lands), so the origin square is immediately contestable by
anyone else. `_release(piece)` is the private helper that clears a piece's *old* cell
when it finally lands; it uses an identity check (`self._pieces.get(piece.cell) is
piece`) rather than a naive `del`, because `piece.cell` can be stale — the square may
already have been vacated at schedule-time, or even legitimately reoccupied by a
*different* piece since. `move_piece(piece, to)` is the public "the piece has arrived"
call: it releases the old cell, evicts/returns whatever occupied `to` (the capture), and
places the piece at `to`, updating `piece.cell`.

**Q3. Why doesn't `Board.move_piece` check that the destination is a different color?**
A: Deliberate separation of concerns. `RuleEngine.evaluate_move` is the only gate that
blocks moving onto a same-color piece, and it runs *before* anything is ever scheduled.
`Board` trusts its caller completely — it's a dumb data structure, not a rules engine.

**Q4. How does `Board.path_clear` avoid divide-by-zero for straight moves?**
A: It computes the unit step with `(dr > 0) - (dr < 0)` (sign function) instead of
`dr // abs(dr)`, so a purely horizontal or vertical move (where one of `dr`/`dc` is 0)
never divides by zero.

**Q5. What does `Board.snapshot()` do and why?**
A: A shallow copy of the `_pieces` dict (same `Piece` objects, new dict). It lets a
caller release a lock and do something slow (like rendering) with the copy without
holding the lock the whole time — the calling code, not `Board` itself, owns any
threading/locking concerns.

**Q6. Explain `MoveRule` and how pawn's two-square start and promotion are wired in.**
A: `MoveRule` is a frozen dataclass bundling `shape_ok` (the shape predicate),
`sliding` (whether path-blocking applies), an optional `capture_ok` (a different shape
predicate used only when the destination is enemy-occupied — this is how "pawn moves
straight, captures diagonally" is expressed generically), an optional
`start_row_offset` (only set for PAWN, enabling the two-square-from-start case), and an
optional `on_arrive` hook (only set for PAWN, calling `_pawn_promote`).

**Q7. Why isn't the pawn's two-square move just marked `sliding=True` like a rook?**
A: `sliding` is a single flag for the *whole* rule, but the pawn's one-square move and
its capture move must NOT be path-blocked the same way the two-square move is. So the
"can't jump over a piece" check for the two-square case is hand-rolled inside
`_pawn_shape` itself (`ctx.board.path_clear(...)`), rather than reusing the generic
sliding mechanism which would apply too broadly.

**Q8. When exactly does a pawn become a queen?**
A: On *arrival*, not on scheduling. `_pawn_promote` is wired as `MoveRule.on_arrive` and
is only invoked from the real-time arbiter after `board.move_piece` has already placed
the piece on its destination. A pawn that's still mid-flight toward the last row is
still governed by pawn movement rules the entire time it's in the air.

**Q9. How does `RuleEngine.evaluate_move` treat a square occupied by a piece that's
mid-jump?**
A: It's treated as *not occupied* for legality purposes (`airborne_enemy = dest is not
None and dest.state == JUMP`). An enemy can legally schedule a non-capturing-shape move
onto that square. This is a deliberate two-phase design: legality is decided now, but
*who actually wins the square* is resolved later by the real-time arbiter
(`_resolve_airborne_defense` — see Step 2). If asked "isn't that a bug," the answer is
no — it's the intentional mechanism for how a jumping piece can still be captured out
of the air.

---

## STEP 2 — Realtime Engine & Orchestration (`realtime/`, `engine/`)

This is the layer that makes the game "real-time chess" instead of turn-based chess —
expect this to be a major focus of questions.

**Q1. What's the one thing that makes this "not turn-based"?**
A: `RealTimeArbiter.schedule_move` calls `board.vacate(frm)` **immediately**, the
instant a move is scheduled — before any time has passed. The origin square is open to
anyone the moment a piece sets off, not when it arrives. Only the *destination* square's
occupancy at arrival time is ever contested.

**Q2. Where do the move/jump duration numbers come from — why not just hardcode
1000ms per square?**
A: `move_duration_ms`/`jump_duration_ms` derive timing from each piece's
`speed_m_per_sec` (loaded from `assets/.../config.json` via `PieceConfigLoader`), scaled
by constants (`METERS_PER_CELL=1.1`, `JUMP_REFERENCE_DISTANCE_M=3.0`,
`TIME_SCALE=1.5`). These constants were reverse-engineered so that, for the asset pack's
default uniform speeds, the formula reproduces the project's original fixed
`MS_PER_SQUARE=1000`/`JUMP_DURATION_MS=1000` — but a piece with a genuinely different
speed in its config now actually takes proportionately longer. Single source of truth,
not a hardcoded constant, so animation and physics can never drift apart.

**Q3. Why does `TIME_SCALE` not affect `REST_DURATIONS`?**
A: `REST_DURATIONS` (`short_rest: 1000`, `long_rest: 4000`) are flat cooldown constants
independent of any piece's config — `TIME_SCALE` is a pacing knob for movement/jump
*travel* time only, deliberately not for cooldowns.

**Q4. Walk me through what happens, tick by tick, when two events land at the exact
same millisecond.**
A: `settle()` collects all due events (`ARRIVAL`, `LANDING`, `REST_DONE`) and sorts them
by `(time, EVENT_ORDER[kind])` where `EVENT_ORDER = {ARRIVAL: 0, LANDING: 1,
REST_DONE: 2}`. So on a tie, arrivals resolve first, then landings, then rest
completions. The comment in the code calls this "the airborne window is inclusive": a
jump that ends on the exact tick a mover arrives at that square is still considered "in
the air" when the arrival resolves, so the mover is captured by the still-airborne
defender (see Q6) before the jumper's own landing is processed later in the same batch.

**Q5. What happens if a piece scheduled to arrive was already captured earlier in the
same `settle()` batch?**
A: `_is_live` checks whether the event's piece is already flagged `captured`; if so,
`_discard` drops the event instead of resolving it. This matters because a single
`settle()` call can process many events in order, and an earlier one (e.g. an airborne
defense capture) can invalidate a later one for the same piece.

**Q6. Explain the airborne-defense mechanic concretely.**
A: `RuleEngine` allowed a move onto a square where the occupant was mid-jump (treating
it as "not really there"). If that jumper is *still* airborne when the mover's arrival
event actually fires, `_resolve_airborne_defense` captures the **mover** instead — the
jumper "defends" its square just by still being there when the mover shows up. The
jumper itself is untouched; it keeps jumping and lands normally afterward. Same-color
jumpers are exempt (no friendly fire).

**Q7. Why does a normal move's `on_arrive` hook run *after* the capture is applied?**
A: `_resolve_move_arrival` calls `board.move_piece` (which returns/evicts any captured
occupant) before running `on_arrive` (pawn promotion). The comment flags this ordering
as deliberate: the captured piece reference is snapshotted while the mover is still
nominally its pre-promotion kind. In practice nothing currently breaks if this were
reversed (promotion and capture touch different pieces), but the ordering is documented
intentionally rather than left to chance.

**Q8. What happens to all other in-flight moves/jumps/rests when the game ends?**
A: `_apply_capture`, on a win-condition hit (default: king captured), does
`arbiter.pending.clear()`, `arbiter.rests.clear()`, `arbiter.status.clear()` — *every*
in-flight motion anywhere on the board is silently dropped, not just the piece involved
in the winning capture. This is by design: `game_state.game_over` short-circuits
`settle()` on the next call, and `GameEngine.select/move/jump` all early-return once the
game is over, so nothing further can act on those cleared structures anyway.

**Q9. `GameEngine` exposes both `select()` and `move()` — why two APIs?**
A: `select(pos)` is the two-click local UX (click a piece, click a destination).
`move(frm, to, requesting_color=None)` is the one-shot "as a network client sends it"
API. The `requesting_color` parameter is the single place server-side ownership is
enforced: if given and it doesn't match the piece's actual color, the request is
silently rejected. `jump()` gets the identical treatment. This is deliberately the
*only* authority check needed anywhere in the engine for networked play, because a
network client can only ever request a move through this one entry point — it never
gets a reference to `GameState`/`Board` to mutate directly itself.

**Q10. What guards against two friendly pieces racing for the same square?**
A: `_is_destination_reserved` checks if a same-color piece is already scheduled toward
`to`; if so, the new move is rejected as `DESTINATION_RESERVED`. Note this is
same-color-only — an *enemy* racing for the same square is allowed, and resolving that
race (whoever's arrival event fires first, or the airborne-defense mechanic) is exactly
the arbiter's job.

**Q11. What's the only thing that advances the game clock?**
A: `GameEngine.wait(ms)`. Time is entirely externally/pull-driven — there's no internal
thread or timer in the engine itself. The GUI main loop calls it with a frame delta; the
text-script harness calls it with an explicit `wait N` command; the networked server's
tick loop calls it with real elapsed wall-clock time (see Step 5).

---

## STEP 3 — I/O Adapters (`boardio/`, `input/`, `view/`, `texttests/`)

**Q1. What are the two exact error strings `board_parser.validate_board` can raise, and
why do they matter so much?**
A: `ERROR ROW_WIDTH_MISMATCH` (rows split into differing token counts) and
`ERROR UNKNOWN_TOKEN` (a character outside the allowed set). These exact strings are
part of an **exact-stdout-diff contract**: the integration tests and `app.py`'s
`except ValueError as e: print(e)` print them verbatim, and the grading/test harness
diffs stdout byte-for-byte. Changing the wording breaks the contract, not just the
error message.

**Q2. Why is `board_printer.print_board` deliberately so minimal (no header/border)?**
A: Its exact, minimal, deterministic output (space-joined tokens per row, nothing else)
is diffed byte-for-byte against each `.kfc` test file's `Expected:` section. Any
formatting change here breaks every integration test relying on that format.

**Q3. How does `input/board_mapper.pixel_to_cell` handle out-of-bounds clicks?**
A: Plain floor division (`y // cell_size`, `x // cell_size`), then returns `None` if
`board.in_bounds` rejects the resulting cell. Python's `//` floors toward negative
infinity, so negative pixel coordinates naturally produce negative cells, which
`in_bounds` correctly rejects — no special-casing needed.

**Q4. Why is the background board pre-rendered once and cached as BGRA (4-channel),
not BGR (3-channel)?**
A: `Img.draw_on()` only alpha-blends when the destination canvas has 4 channels;
against a 3-channel canvas it would paste piece sprites opaquely, destroying
transparency at their edges.

**Q5. Why is `_state_entry` (piece id → state-entry timestamp) explicitly cleared for
every in-flight piece on every frame?**
A: A piece mid-flight is drawn through a different code path (position interpolated
from its `PendingMove`) and never has its state-entry timestamp refreshed while
in-flight. Without clearing it, a piece that lands back into a rest state it was
previously in (e.g. `long_rest` again) would reuse a stale old timestamp, making its
cooldown-fill bar look almost drained from frame one instead of full. Popping the entry
on every in-flight frame guarantees the next non-in-flight sighting is always "fresh."

**Q6. Where is view rendering event-driven rather than purely polled per-frame?**
A: Only for capture flashes — `ImageView` subscribes to the `piece.captured` bus event
and drives a fading highlight + a Windows `winsound` beep from it. Everything else
(sprites, cooldown bars, board layout) is recomputed fresh every frame from the current
snapshot/clock, not from events.

**Q7. What exactly does the `.kfc` test-script format look like, and what four commands
does `texttests/script_parser.py` recognize?**
A: `Board:` section (whitespace-separated two-char tokens or `.`), `Commands:` section,
`Expected:` section (split via a literal `"\nExpected:\n"` marker — exact spacing
matters). The four recognized commands are `print board`, `wait <int>`,
`click <int> <int>`, `jump <int> <int>` (click/jump accept negative ints, to test
out-of-bounds clicks deliberately) — anything else raises `ERROR UNKNOWN_TOKEN`.

**Q8. Concretely, what happens if a script clicks-and-moves a piece that's still
resting?**
A: Nothing observable in stdout. `GameEngine._try_schedule_move` would reject it as
`MOTION_IN_PROGRESS` internally (piece not `is_selectable`), but `script_runner.run`
only ever prints board state on `print board` — it never prints move-result reasons —
so a rejected move looks identical to a silent no-op from the script's output
perspective.

---

## STEP 4 — Cross-Cutting Infra: Event Bus & Wire Protocol (`bus/`, `net/protocol.py`)

**Q1. Why is `EventBus` synchronous with no queueing or locks?**
A: Both consumers that ever publish — the single-threaded-per-tick `GameEngine` and the
single-threaded-per-event-loop-iteration asyncio server — only ever publish from one
place at a time. There's no concurrent publish to guard against, so a plain
`dict[str, list[handler]]` with immediate synchronous dispatch is sufficient; adding
locking would be solving a problem that doesn't exist here.

**Q2. What does `bus/logging_subscriber.py` do, and why does it import
`BRIDGED_TOPICS` from `net/bus_bridge.py` instead of defining its own topic list?**
A: `attach_logging` subscribes a structured log line to every topic in
`net.bus_bridge.BRIDGED_TOPICS`. Reusing that exact list (instead of a second,
independently-maintained one) guarantees the logging layer and the network layer never
silently drift apart about what "every game-relevant topic" means.

**Q3. Why is `serialize_board`/`deserialize_board` a completely different format from
`boardio`'s plain grid tokens?**
A: The plain "wK" token grid has no piece id and no `piece.state`. If SYNC_STATE reused
it, every resync would hand out fresh, server-mismatched piece ids (breaking every
subsequent EVENT's `piece_id` lookup client-side) and lose mid-cooldown/mid-rest state.
`serialize_board` carries each piece's real id, color, kind, position, and state
explicitly so a resync is a faithful, fully resumable snapshot.

**Q4. Why does `positions_to_squares` exist, and where is it used?**
A: Bus event payloads carry `Position` objects internally (not JSON-serializable
directly). `positions_to_squares` shallow-converts any `Position`-valued field (e.g.
`from`/`to`/`pos`) into its algebraic-square string, leaving every other field
untouched. `BusBridge` calls it on every payload before encoding an EVENT message.

**Q5. What's the row/rank convention, and where does it live?**
A: Row 0 is the *top* of the board's internal grid. `square_to_position`/
`position_to_square` convert between that and standard algebraic notation
(`row = rows - rank`), matching `model/position.py`'s convention and the
`STARTING_POSITION` grid layout (black pieces on row 0/1, white on the bottom rows).

---

## STEP 5 — Server Architecture (`net/ws_server.py`, `net/game_session.py`,
`net/bus_bridge.py`, `rooms/`, `matchmaking/`)

This is a focus area — expect deep questions here.

**Q1. Describe the high-level shape: what's a `ConnectionContext`, a `ServerState`,
and a `GameSession`?**
A: `ConnectionContext` is per-connection state that outlives any single message: the
logged-in username, and — once matched/seated — which `GameSession`, `color`, and
whether it's a spectator. `ServerState` is process-wide: the `UserRepo`, the
`MatchmakingQueue`, the `sessions` dict (`room_id`/`match_id` → `GameSession`), the
`RoomManager` (sharing that same `sessions` dict), and `active_players`
(`username` → `(session, color)`, used to recognize reconnects). `GameSession` is one
authoritative `GameEngine` plus the asyncio machinery (tick loop, connections dict,
disconnect timers) to run it and talk to its players over websockets.

**Q2. Why is a room and a matchmaking match "the same underlying concept"?**
A: Both are just a fresh `GameSession` keyed by a random id in `server_state.sessions`.
`_start_matched_game` reuses `RoomManager.create_room()` rather than duplicating a
second random-id/session-bookkeeping scheme for matched games — one registry, one
creation path, for both entry points into a game.

**Q3. Walk me through exactly what happens on a new websocket connection, from raw
socket to gameplay.**
A: `handle_connection` calls `_await_login` first — the *required* first message must
be `LOGIN`; anything else gets an error and the connection is closed. Login does a
lookup-or-create against `UserRepo` (auto-registering unknown usernames, verifying
password hashes for known ones via PBKDF2 + constant-time compare), then checks
`active_players` for a matching in-progress session (a reconnect) before falling
through to a normal lobby entry. From there the main loop dispatches every subsequent
message to either `_dispatch_lobby` (if `context.session is None`: PLAY, CANCEL_SEARCH,
CREATE_ROOM, JOIN_ROOM) or `_dispatch_in_game` (MOVE, JUMP, rejected outright for
spectators).

**Q4. Why does the server never trust a client-declared color or piece for a MOVE?**
A: `_dispatch_in_game` calls `session.engine.move(frm, to,
requesting_color=context.color)` — the engine itself resolves whose piece `frm`
actually holds and checks that against the *connection's own assigned* color (set once,
server-side, at seating time), never anything the client claims in the message. This is
the entire server-authoritative security model for move requests.

**Q5. What's the race being guarded against in `_await_login` when creating a new
account?**
A: Two connections could both call `get_user` (find nothing), then both call
`create_user` for the same brand-new username. The second `create_user` raises
`sqlite3.IntegrityError` (the `username` primary key already exists); that's caught and
the code falls back to re-fetching the now-existing user and treating this connection's
attempt as a login instead of a fresh registration.

**Q6. Why does the room creator get `SYNC_STATE` immediately, instead of waiting for
an opponent to join?**
A: The protocol doesn't gate this — it's a deliberate choice (see the commit history:
"don't sync the room creator until an opponent actually joins" was actually the
*opposite*, older behavior that was changed). Today, whether/when to leave the room
dialog for the game window is entirely a client-side UX decision
(`client/room_dialog.py`'s "Enter Room" button), not something the protocol should be
timing.

**Q7. Explain the disconnect/reconnect/auto-resign flow in `GameSession` in detail.**
A: `on_disconnect(color)` starts a `DISCONNECT_GRACE_S` (20s) countdown task unless the
game's already over or a timer's already running for that color. Every second, it
notifies the *opponent* (not the disconnected player) of the remaining countdown via a
`PLAYER_DISCONNECTED` message. If the timer runs out, `_resign(color)` fires: it sets
`game_over=True`, `winner=<opponent>`, and publishes the *same* `game.over` bus event
any other win condition uses (with `reason: 'opponent_disconnected'`) — so the existing
ELO-update subscriber and network broadcast both just work, with no second code path.
If the same username logs back in before the timer expires, `handle_connection` detects
it via `active_players`, calls `on_reconnect`, which cancels the pending timer, notifies
the opponent (`PLAYER_RECONNECTED`), rebinds the connection, and sends a full
`SYNC_STATE` (the *only* other time a full snapshot is sent besides initial join) since
the reconnecting client has no idea what it missed.

**Q8. Why is `_resign`/`on_disconnect` idempotent against a game that already ended?**
A: `on_disconnect` no-ops if `game_over` or a timer's already running for that color, so
a normal disconnect right after a win/loss doesn't spuriously start a resign countdown.
`_resign` itself also re-checks `game_over` before acting, since the grace-period task
could fire after the game ended for an unrelated reason (the opponent won some other
way in the meantime).

**Q9. Why does `broadcast_nowait`/`_safe_send` schedule sends as tasks instead of
awaiting them directly, and why does `_safe_send` swallow exceptions?**
A: `broadcast_nowait` is called from *synchronous* bus-handler code (a bus publish call
inside the arbiter, which is not itself async) — it can't `await` anything, so it fires
off `asyncio.create_task` for each send instead. `_safe_send` wraps each individual send
in a try/except and just logs failures, because one dead/slow connection (e.g. a
spectator who silently closed their tab) must never crash the entire broadcast loop or
block delivery to everyone else.

**Q10. Why does the tick loop credit the engine with *actual elapsed* wall-clock time
instead of a flat `TICK_MS`?**
A: `asyncio.sleep(TICK_MS/1000)` only guarantees *at least* that long; under event-loop
load (other sessions' I/O, a blocking-via-`to_thread` DB write, GC) a nominal 50ms tick
can easily take 70-100ms of real time. If the engine were credited a fixed 50ms
regardless, `clock_ms` (and therefore every move's server-computed
`start_time`/`arrive_time`) would permanently drift behind real time relative to a
client's own wall-clock-derived render clock — eventually a client's local clock would
race past a move's `arrive_time` before the slide animation visually finished,
producing a "snap then wobble" artifact. Crediting real elapsed time means a slow tick
only costs itself once, and never compounds into later ticks.

**Q11. Why is ELO update scheduled as a separate task (`asyncio.create_task`) instead
of run inline from the `game.over` bus handler?**
A: Bus handlers are synchronous, but updating ELO means a blocking SQLite write
(offloaded via `asyncio.to_thread`), which needs `await`. `_on_game_over` can't await
directly (it's a sync callback), so it schedules `_update_ratings` as a background task
— the same fire-and-forget pattern `broadcast_nowait` uses for socket sends.

**Q12. How does `MatchmakingQueue.find_match` pick pairs, and what's the tradeoff?**
A: It's an O(n²) scan over the waiting list, returning the *first* pair found within
`RATING_RANGE` (100) of each other — FIFO order, not the closest possible pairing
overall. Simple and correct for a course-scale queue; would need a smarter data
structure (e.g. a sorted structure with a sliding window) to scale, but that's an
explicit non-goal here.

**Q13. Why is `MatchmakingQueue` framework-agnostic (no asyncio/websockets imports)?**
A: So it's trivial to unit-test in isolation with plain synchronous calls
(`tests/unit/matchmaking/test_queue.py`). The async server (`_matchmaking_loop`) is a
thin wrapper that periodically calls `find_match()`/`expire()` and performs the actual
I/O (sending `MATCH_FOUND`/`NO_MATCH_FOUND`) — the queue itself never touches a
connection except as an opaque field on `Waiting.context`.

**Q14. What determines whether the second connection into a room is seated as Black
or made a spectator?**
A: `GameSession.assign_color()` — White if the White seat is empty, Black if only Black
is empty, `None` (→ spectator) otherwise. This is the same method used for both a
`JOIN_ROOM` request and (implicitly, since matched players are seated directly by color)
matchmaking.

---

## STEP 6 — Persistence & Auth (`persistence/`, `auth/`)

**Q1. Why PBKDF2 via stdlib `hashlib` instead of bcrypt/argon2?**
A: Deliberately stdlib-only — avoids a new dependency for a course-scale user base,
while still being a real salted (`secrets.token_bytes(16)`), iterated (200,000
rounds) hash rather than a plain or reversible one. Password comparison uses
`secrets.compare_digest` (constant-time) to avoid timing attacks on the hash comparison.

**Q2. Why does `UserRepo` have its own `threading.Lock` in addition to
`check_same_thread=False` on the SQLite connection?**
A: The async server offloads every DB call via `asyncio.to_thread`, which can run
different calls on different worker threads. `check_same_thread=False` merely lets
SQLite *accept* calls from multiple threads; it doesn't serialize them. `UserRepo`'s own
lock provides the actual real thread-safety, rather than depending on whatever
threading guarantees (or lack thereof) the underlying SQLite build happens to have.

**Q3. Why does `connect()` special-case the literal string `":memory:"`?**
A: So `Path(path).parent.mkdir(...)` isn't called for it — `:memory:` is SQLite's
in-memory-database sentinel, not a real filesystem path, and tests use it to get a
fresh, isolated DB with no file created.

**Q4. Walk through the ELO math in `persistence/elo.py`.**
A: Standard ELO: `expected_a = 1 / (1 + 10^((rating_b - rating_a)/400))`,
`expected_b = 1 - expected_a`. `result_a` is the actual outcome (1.0/0.0/0.5);
`result_b` is always its complement — there's no separate parameter for it since a
single game has exactly one outcome. New ratings are
`rating + K * (result - expected)`, rounded to the nearest int, with `K_FACTOR = 32`.

**Q5. Why is login a blocking terminal prompt (`auth/login_cli.py`) instead of a GUI
dialog?**
A: Explicit project requirement ("do it in a shell" for login). It runs on the main
thread *before* any OpenCV window opens. An unknown username auto-registers
server-side, so there's deliberately no separate "sign up" flow to build client-side.

---

## STEP 7 — Client Architecture (`net/ws_client.py`, `client_main.py`,
`client/home_screen.py`, `client/room_dialog.py`, `client/widgets.py`)

Also a focus area.

**Q1. What is `NetworkGameClient` conceptually, and why does it reuse
`model.Board`/`PendingMove`/`PendingJump` instead of its own data structures?**
A: It's a "passive renderer-side mirror" of the server's authoritative `GameEngine` —
holding a real `model.Board` mutated with the *exact same primitives*
(`vacate`/`move_piece`/`remove_piece`) the server's `RealTimeArbiter` uses, plus a
locally reconstructed in-flight list shaped like the engine's own `PendingMove`/
`PendingJump`. This means the existing `ImageView.render()` can be fed from this mirror
almost exactly as it's fed from a local `GameEngine`, without this client running any
rules or timing logic of its own — it only ever applies what the server tells it
happened.

**Q2. Why does `NetworkGameClient` need a `threading.Lock`, and what specifically is
it protecting?**
A: Network messages are received and applied on a background asyncio thread (see
`client_main.py`'s `_start_network_thread`), while the render loop reads/mutates the
same state on the main thread. `self.board` holds a plain dict mutated in place
(insert/delete keys); iterating it in `ImageView.render()` on one thread while the
network thread deletes/inserts a key mid-iteration raises "dictionary changed size
during iteration." The lock is held across both a message's application and any render
read of the shared state (`tick()`, `snapshot()`, and copying out score/moves/etc.).

**Q3. Why is a full `SYNC_STATE` never sent on a timer, only at join/reconnect?**
A: Every other state change is instead pushed incrementally as a small `EVENT` the
instant it happens server-side (`BusBridge`'s `BRIDGED_TOPICS`), which is both cheaper
and lower-latency than periodic full snapshots. A full snapshot is only needed when a
client has *no* prior state to incrementally build on — i.e., exactly at join and at
reconnect.

**Q4. Explain the arrival-buffering mechanism (`_pending_arrivals`/`tick()`) in detail
— why not just apply a `move.arrived` event's board mutation immediately?**
A: The network event fires the instant the *server* resolves the arrival, which is
typically a bit ahead of this client's own `local_clock_ms` (lagging by network/
processing latency). Applying the mutation immediately would yank the piece to its
destination before this client's own slide interpolation of it had visually finished —
a jump instead of a smooth animation. Instead, `_on_move_arrived` buffers an `apply()`
closure keyed by the move's own `arrive_time`; `tick(local_clock_ms)` (called once per
frame under the lock) only runs buffered applies whose time has been reached by this
client's own render clock. By the time the "official" arrival applies, the piece is
already fully interpolated there visually — nothing to snap.

**Q5. Why does `_on_piece_captured` sometimes defer removal and sometimes remove
immediately?**
A: A normal capture is already handled by the buffered `move.arrived` apply (which
detaches the captured piece via `board.move_piece`). But the airborne-defense capture
(the mover dies mid-air) has **no** accompanying `move.arrived` for the *mover* — it
never resolves as a normal arrival. So `_on_piece_captured` checks whether some other
pending move's destination matches the captured piece's current square: if so, it
aligns the removal with *that* move's buffered arrival (so the victim doesn't vanish
before the attacker visually arrives); otherwise (airborne-defense, or no matching
pending move at all) it removes the piece immediately.

**Q6. Why does the render loop re-anchor `local_clock_ms` to `clock_ms` on every
`sync_version` bump instead of just letting it free-run from wall-clock deltas?**
A: `sync_version` is bumped on every `SYNC_STATE`. A fresh sync means the client's
previous locally-accumulated clock estimate is meaningless (a join or reconnect can
jump the actual game clock arbitrarily). Re-anchoring exactly when a new `SYNC_STATE`
arrives, and free-running via `dt_ms` accumulation otherwise, bounds drift without
needing a fresh clock reading on every single event.

**Q7. In `client_main.py`'s render loop, why is `client.lock` released *before*
calling `view.render()`?**
A: `view.render()` (drawing the entire board + panels) is the expensive part of the
frame; `cv2.waitKey(1)` is the only other thing in the loop and returns almost
instantly. If the lock were held through the render call too, it would be held almost
continuously, starving the network thread of any real chance to apply an incoming
message — moves could take seconds to visually show up under load. So the lock is only
held long enough to `tick()` and copy out exactly what `render()` needs (via
`Board.snapshot()` and shallow copies of score/moves/etc.), then released before the
actual drawing happens.

**Q8. What security assumption does `_handle_click`/`send_move` rely on, given the
client never validates legality itself?**
A: "This is a request, not a write" — the client only turns two clicks into a
`from`→`to` MOVE message; it never checks whose turn it is, whether the piece is
selectable, or whether the shape is legal. The server independently re-resolves
`frm`'s actual color and cooldown state (`GameEngine.move`'s `requesting_color` check
plus `RuleEngine`) before ever scheduling anything, so a compromised or buggy client
can only ever get its illegal request rejected, never executed.

**Q9. Why is `selection_targets` always passed as `None` in the networked client's call
to `view.render()`?**
A: The server is the sole authority on legal destinations; duplicating `RuleEngine`
client-side just to compute and highlight them wasn't judged worth it for this phase —
an explicitly named simplification, not an oversight.

**Q10. Why does the room dialog remember `joined_room_id` locally instead of relying
entirely on `client.room_id`?**
A: The server never echoes a *joiner's* own room_id back to them (only the creator gets
`ROOM_CREATED`/`room_id`; a joiner just gets seated and synced). Without a client-side
copy captured the moment the join is requested, the "in_room" view would have nothing to
display for a joiner — `client.room_id` alone only ever gets populated for the creator.

**Q11. Why does `run_room_dialog` never auto-transition to the game window the instant
`client.board` becomes populated?**
A: Deliberate UX choice — the two views (`setup` vs `in_room`) are chosen purely from
client state, and entering the game window happens only when the *player* clicks
"Enter Room," never as an automatic cutover the instant a sync arrives. This also means
a stray/duplicate message can't desync the UI by yanking the window away unexpectedly.

**Q12. Why are clipboard copy/paste "best-effort," swallowing all exceptions?**
A: They shell out to platform tools (`clip`, PowerShell's `Get-Clipboard`) with no new
dependency — if that fails for any reason (missing tool, permissions, non-Windows dev
environment), the dialog should degrade gracefully (manual typing still works) rather
than crash.

**Q13. Why does the capture-flash/beep effect explicitly not work in the networked
client, per the comment in `client_main.py`?**
A: That effect's timing is driven by the *same* clock passed into `render()` each
frame. In the offline/local path there's one authoritative clock shared by both the
engine and the renderer. In the networked client, `render()` is driven by a wall-clock-
derived `local_clock_ms` owned by the render loop, while capture events arrive
asynchronously on the network thread — correctly wiring the two together was judged to
be more machinery than the purely cosmetic payoff justified for this phase. Move/score/
game-over sync itself is unaffected.

---

## STEP 8 — End-to-End Scenarios (span client + server — likely review questions)

**Q1. Trace a full move from a mouse click to every client's screen updating.**
A: `_mouse_callback` (client_main.py) maps pixels→cell under `client.lock`,
`_handle_click` builds a `LocalSelection` (purely client-side, never sent), and on the
second click schedules `client.send_move(frm, pos)` on the network thread's event loop.
`NetworkGameClient._send` encodes and sends a `MOVE` message. Server-side,
`_dispatch_in_game` decodes `frm`/`to`, calls `session.engine.move(frm, to,
requesting_color=context.color)`. If legal, `GameEngine._try_schedule_move` schedules it
via `RealTimeArbiter.schedule_move`, which immediately `board.vacate(frm)`s and publishes
`move.started` on the engine's `EventBus`. `BusBridge` (subscribed to that topic)
converts the payload's positions to algebraic squares and calls `broadcast_nowait`,
which fires an async send task to every connected player and spectator. Each
`NetworkGameClient.run()` loop receives the `EVENT` message and calls
`_on_move_started`, vacating its own mirrored board and adding a `PendingMove` for
interpolation. When the server's tick loop later advances the clock past the move's
`arrive_time`, `settle()` resolves the `ARRIVAL` event, `board.move_piece` actually
lands it, and `move.arrived` is published/bridged/broadcast the same way — each client
buffers the arrival via `_pending_arrivals` until its own local render clock catches up,
then applies it.

**Q2. Trace what happens when a player closes their laptop mid-game and reopens it 10
seconds later.**
A: The websocket connection drops; `handle_connection`'s `finally` block calls
`session.on_disconnect(color)`, starting a 20s grace-period task that notifies the
opponent every second via `PLAYER_DISCONNECTED`. The disconnected player's client
(`NetworkGameClient.run()`'s `async for` loop) exits when the socket closes; nothing in
the client automatically reconnects — `client_main.py` has no retry logic shown, so in
practice the user would need to relaunch. On relaunch, `_await_login` succeeds again for
the same username, `handle_connection` finds the still-in-progress session in
`active_players`, and calls `session.on_reconnect` — cancelling the pending timer,
notifying the opponent (`PLAYER_RECONNECTED`), rebinding the connection, and sending a
fresh full `SYNC_STATE`.

**Q3. What happens if that same player instead waits 25 seconds before reopening?**
A: The grace timer (20s) expires first: `_resign(color)` sets `game_over=True`, the
opponent as `winner`, and publishes `game.over` with `reason: 'opponent_disconnected'`.
This is bridged/broadcast like any other game-over, and separately triggers
`_on_game_over`'s ELO update. When the disconnected player does reconnect afterward,
`active_players` still has a stale entry, but `handle_connection`'s check
(`not reconnect_info[0].engine.state.game_over`) sees the game is already over and
routes them into the lobby instead of `on_reconnect`.

**Q4. Why can a spectator watch a room but never move a piece, and what happens if
they try?**
A: `assign_color()` returns `None` once both seats are filled; `JOIN_ROOM`'s handler
then sets `context.is_spectator = True` and calls `session.add_spectator` instead of
`_seat_player`. `_dispatch_in_game` explicitly checks `context.is_spectator` first and
rejects `MOVE`/`JUMP` with `SPECTATOR_CANNOT_MOVE` before ever reaching the engine.

**Q5. Two clients on the same slow network both click to move different pieces to the
same empty square at nearly the same time. What determines the outcome?**
A: Both requests independently pass `RuleEngine.evaluate_move` (the square is empty at
the time each is evaluated) and get scheduled — `_is_destination_reserved` only blocks a
*same-color* second racer, so two enemy pieces racing for one square is allowed. The
server processes each incoming MOVE message sequentially as it's received (single
event-loop, no true parallelism), so whichever message the server's socket layer
delivers/decodes first schedules first; when both eventually reach their `ARRIVAL`
events, `settle()`'s event ordering resolves them in the order their `arrive_time`s
(and therefore likely their scheduling times/travel durations) actually land — the
piece that arrives second lands via ordinary `_resolve_move_arrival`, which captures
whatever ended up on that square first via `board.move_piece`.

---

## STEP 9 — Testing Strategy

**Q1. What are the two fundamentally different kinds of automated tests in this
project, and why?**
A: (1) The **text-script integration harness** (`tests/integration/test_text_script.py`
+ `.kfc` fixture files) — pipes a `Board:`/`Commands:` text script through
`texttests/script_runner.run` and diffs stdout byte-for-byte against an `Expected:`
section. This exercises the model/rules/realtime/engine stack end-to-end through a
deterministic, timing-controlled (`wait N`) text protocol with zero networking/
rendering involved. (2) **Unit tests per module** (`tests/unit/...`, one directory per
package: `board`, `rule_engine`, `real_time_arbiter`, `game_engine`, `game_session`,
`matchmaking`, `persistence`, `ws_client`, `rooms`, `bus_bridge`, etc.) — isolate a
single class/function's behavior, including timing edge cases like
`test_airborne_defense.py`, `test_promotion.py`, `test_win_conditions.py`.

**Q2. Why is there a separate `tests/integration/test_ws_server_integration.py` on top
of the `.kfc` harness and the unit tests?**
A: The `.kfc` harness never touches networking; unit tests isolate individual classes
(often with fakes/mocks for their collaborators). The websocket server integration test
is the one place that exercises real asyncio + real `websockets` connections end-to-end
(login, matchmaking or room join, moves, disconnects) against an actual running
`serve()` coroutine — the only test layer that would catch a bug purely in the
async wiring (e.g. a message dispatched to the wrong handler, a race in connection
setup) that per-module unit tests can't see.

**Q3. Why is `MatchmakingQueue` so easy to unit test, and what would be harder to test
if it weren't structured that way?**
A: It's plain synchronous Python with no asyncio/websockets dependency — `add`,
`find_match`, `expire` all take an optional explicit `now` parameter instead of calling
`time.monotonic()` internally by default when testing, so tests can control time
precisely without real sleeps. If matching logic were embedded directly in
`_matchmaking_loop`'s async code, testing pairing/timeout edge cases would require
spinning up real event loops and either sleeping in real time or mocking asyncio
internals — much heavier and flakier.

**Q4. What's the significance of the exact string `"\nExpected:\n"` in
`test_text_script.py`'s fixture loader?**
A: It's the literal delimiter `_load_kfc` splits each `.kfc` file on
(`text.partition(...)`) to separate the script's input from its expected stdout. Any
`.kfc` fixture must have that exact substring, with that exact spacing/casing/newlines,
or the split silently fails to find the expected section.
