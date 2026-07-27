# Scaling Plan: Kong Fu Chess to 100M Registered / 10M Concurrent Users

This is an implementation plan, not a comparison document — it states what to build and
why, and is meant to guide the actual work when this is picked up. It merges my original
draft with a reviewed reference plan and a reviewed architecture diagram of the same
system; where they differed, the merged choice and its reason is noted inline.

Baseline this plan builds on: today's `net/ws_server.py` runs one asyncio process holding
all `GameSession`s in memory, backed by SQLite (`persistence/`), with in-memory
`MatchmakingQueue` and `RoomManager`. Every step below is about generalizing that same
in-process design across many machines, not replacing its ideas.

**Non-negotiable invariant, unchanged from today's code:** neither the client nor any
Gateway ever decides game rules. The `GameEngine` inside a Game Server Shard is the sole
source of truth for move legality, cooldowns, and piece ownership. Gateways only ever
move bytes between the client and the shard that owns its room.

---

## Merge notes (where the two plans differed)

- **Split the Gateway in two: API Gateway (login, room listing, history) + WebSocket
  Gateway (live connections, state push).** My original draft had one "Gateway" doing both
  WS termination and the login handshake. Splitting them is better because they scale on
  different axes — API Gateway is stateless request/response and scales on request rate;
  WebSocket Gateway holds one long-lived connection per player and scales on concurrent
  connection count. Keeping them separate lets each autoscale on its own correct metric.
- **Added Game Allocator as its own role, separate from Matchmaker.** My draft had the
  Matchmaker both pair players *and* pick a Game Server Shard for them. Separating
  placement (Game Allocator) from pairing (Matchmaker) is better because manually created
  rooms also need a shard chosen for them without going through ELO pairing at all — one
  Game Allocator serves both paths instead of duplicating placement logic in two places.
- **Added Observability as an explicit role.** Health probes and autoscaling metrics were
  implicit in my draft's "orchestrator" step; naming Observability as its own component
  makes clear it's the thing that *feeds* the orchestrator's scaling/restart decisions
  (connection counts, shard load, error rates), not an afterthought.
- **NATS / Redis Pub-Sub for inter-service messaging, layered on top of Redis-as-store.**
  My draft used Redis only for data structures (queue, directory). Adding a pub/sub layer
  is the right way for the Game Allocator to *push* placement results to the WebSocket
  Gateway and for shards to announce room lifecycle events, instead of every component
  polling Redis for changes.
- **Docker Compose for a small local deployment, Kubernetes/K3s for production.** My draft
  jumped straight to Kubernetes. Keeping a Compose file for local runs is worth adding as
  its own build step — it's the cheapest way to validate the multi-service design before
  paying for a real cluster.

## Merge notes v2 (workflow refinements from the reviewed diagram)

- **NATS is the transport for room commands and state updates themselves, not just a
  side-channel for placement notices.** Instead of the WebSocket Gateway looking up a
  shard's address in the Redis directory and proxying the connection directly to it, the
  gateway publishes a client's move onto a subject keyed by `room_id`; the shard that owns
  that room consumes it and publishes state updates back onto NATS for the gateway to
  forward to the client. This is the better choice: the gateway never needs to track a
  shard's network address at all, only the `room_id` — NATS's subject-based routing
  handles delivery even if the shard restarts or gets rescheduled. The Redis directory is
  kept, but narrowed to what NATS doesn't cover — reconnect lookup (which room a
  disconnected user belongs to) and matchmaking-queue state.
- **Consolidated the durable game-end write buffer onto NATS's persistent-stream mode,
  dropping Redis Streams as a separate technology.** Once NATS is already the backbone for
  live traffic, using it for the game-end write buffer too avoids running two different
  queue technologies for the same kind of job (durable, at-least-once delivery from a
  shard to a consumer). Redis keeps its role for ephemeral key/value state (directory,
  matchmaking queue) where a full stream isn't needed.
- **Added an optional fleet-manager layer under the Game Allocator, specifically for
  Game Server Shard lifecycle.** There's a purpose-built class of Kubernetes tooling for
  allocating and scaling short-lived dedicated game server instances — exactly the
  30-90s-session churn problem from Q4 (~83k games/sec starting and ending cluster-wide).
  Rather than hand-rolling shard allocation and lifecycle tracking entirely inside the
  Game Allocator, use that tooling underneath it for the low-level "give me a ready,
  healthy shard" mechanics, and keep the Game Allocator's own logic focused on business
  rules (same-region preference, load balancing across the fleet it's handed). Marked
  optional because a hand-rolled allocator over plain Kubernetes pods is a reasonable
  starting point; add the fleet manager once shard churn makes hand-rolled lifecycle
  tracking a maintenance burden.
- **Matchmaking requests (`PLAY`) move to the API Gateway over REST, not the live
  WebSocket connection.** Today's client sends `PLAY`/`CANCEL_SEARCH` on the same
  WebSocket used for gameplay. The refined workflow separates this: "find a match" becomes
  a request/response call to the API Gateway (which enqueues into the Redis matchmaking
  queue), and the match-found result is pushed to the client over its WebSocket connection
  once the Matchmaker/Game Allocator have placed it. This is a reasonable production
  target — it keeps the WebSocket Gateway focused purely on in-game traffic — but it's a
  real client-protocol change from today's single-connection flow, not just a backend
  refactor, so schedule client work for it explicitly rather than assuming it falls out of
  the backend split for free.
- **API Gateway explicitly hosts Auth Service and Rooms API as internal routes/modules.**
  This matches what v1 already described (login/registration/room-listing/history behind
  the API Gateway); naming the two internal modules explicitly is worth keeping as the
  convention going forward.

---

## System components

| Component | Responsibility |
|---|---|
| API Gateway | Login (Auth Service module), room listing/history (Rooms API module), matchmaking requests — stateless request/response |
| WebSocket Gateway | Holds the live connection to each client; publishes/consumes room traffic over NATS, never talks to a shard's address directly |
| Matchmaker | Pairs players from the ELO queue, hands pairs to the Game Allocator |
| Game Allocator | Decides which Game Server Shard runs a given room (matched or manually created); optionally backed by a fleet manager for shard lifecycle |
| Game Server Shards | Run the authoritative `GameEngine`/`RealTimeArbiter` for their assigned rooms |
| Observability | Logs, metrics, health checks, load tests — feeds the orchestrator's scaling/restart decisions |

## Technologies

| Technology | Used for |
|---|---|
| PostgreSQL (primary + replicas) | Durable data: users, ELO, finished games, move history |
| Redis | Ephemeral data: reconnect lookup, matchmaking queue |
| NATS (with persistent streams) | Backbone for room commands/state updates between WS Gateway and shards, and the durable buffer for game-end writes to Postgres |
| Fleet manager (optional, e.g. Agones) | Kubernetes-native allocation/scaling of short-lived Game Server Shards, used underneath the Game Allocator |
| Docker Compose | Small local version of the full stack, for development and design validation |
| Kubernetes / K3s | Managed multi-container deployment with autoscaling in production |

---

## 1. Data layer

1. Stand up Postgres (managed, or self-hosted with Patroni for failover) with one primary
   + at least one standby replica. Port `persistence/db.py`, `persistence/user_repo.py`,
   `persistence/elo.py` from `sqlite3` to `asyncpg`, keeping the same repo interfaces so
   callers don't change.
2. Add read replicas once read QPS (profile lookups, history, leaderboards) grows; route
   reads to replicas, writes to the primary.
3. Stand up Redis. Move `MatchmakingQueue` (`matchmaking/queue.py`) onto a Redis sorted
   set keyed by ELO. Move reconnect lookup (`ServerState.active_players`) onto a Redis
   hash: `username -> room_id`, with a heartbeat/TTL.
4. Stand up NATS with persistence enabled. Add a game-end stream: a shard publishes
   `{result, elo_delta, move_history}` on game end instead of writing Postgres directly; a
   small pool of consumer workers drains the stream and batch-writes to Postgres. Build
   this before load testing anything else — it's cheap now, expensive to retrofit later.
5. Only shard Postgres (e.g. Citus, or hash-by-`user_id`) once write QPS approaches one
   primary's ceiling — don't shard preemptively.

## 2. Services

1. Extract login/registration/ELO-read/room-listing/history endpoints out of
   `ws_server.py` into the API Gateway (Auth Service + Rooms API modules) — stateless,
   scales behind a plain load balancer. Move the `PLAY`/`CANCEL_SEARCH` matchmaking
   request here too, off the live WebSocket connection.
2. Containerize the remaining `ws_server.py` as the Game Server Shard image. Each instance
   subscribes to a NATS subject per room it's assigned (e.g. `room.<room_id>.commands`)
   and publishes state updates to a matching subject (`room.<room_id>.updates`); it
   unsubscribes on game end or clean shutdown.
3. Build the WebSocket Gateway as a thin bridge, not a direct proxy: for each connected
   client in a room, subscribe to that room's NATS update subject and publish incoming
   client messages to its command subject. The gateway only ever needs a `room_id` — never
   a shard's address — so a shard restarting or being rescheduled is invisible to it.
4. Build the Game Allocator as the single place that picks a shard for a new room —
   whether the room came from the Matchmaker or from a manually created room — using
   least-loaded selection over shard capacity reported through Observability (optionally
   delegating the low-level allocation mechanics to a fleet manager). Publish its
   placement decision over NATS so the WebSocket Gateway learns which `room_id` to
   subscribe to without polling.
5. Build the Matchmaker as a small worker pool reading the shared Redis ELO queue and
   handing pairs to the Game Allocator — it never talks to shards directly.
6. Wire up Observability from the start: structured logs, per-shard connection/CPU
   metrics, liveness/readiness endpoints on every service, and a basic load-test harness —
   this is what the orchestrator's autoscaler and health checks consume in step 3.

## 3. Deployment

1. Write a Docker Compose file that runs one instance of each service (API Gateway,
   WebSocket Gateway, Matchmaker, Game Allocator, one or two Game Server Shards, Redis,
   Postgres) locally, to validate the design end-to-end before touching a real cluster.
2. Move to Kubernetes/K3s: package each service as its own Docker image, add
   liveness/readiness probes wired to Observability, and put a `HorizontalPodAutoscaler`
   on the WebSocket Gateway and Game Server Shards, driven by a trailing average of
   concurrent connections (not instantaneous game count — 30-90s games churn too fast for
   that to be stable).
3. Deploy one full regional stack (API Gateway + WebSocket Gateway + Matchmaker + Game
   Allocator + shards) per region (US/EU/APAC), with a single Postgres primary and
   per-region read replicas; prefer same-region matchmaking for latency.

## 4. Wire protocol

Keep the existing event-driven delta model (`move.started`/`move.arrived` via the bus,
full `SYNC_STATE` only on start/reconnect) — never send full board state per move. Any new
message type in `net/protocol.py` should carry only the delta needed (piece id, from/to,
timestamp), following the existing `PendingMove`/`PendingJump` shape from
`realtime/motion.py`. This is what keeps aggregate bandwidth (~12 Gbps across the whole
fleet at 10M concurrent players moving every 2s) small enough per shard (~15-25 Mbps
each) to scale by just adding more Game Server Shard pods.

## 5. Process model

One process per Game Server Shard container hosts many concurrent `GameSession`s via
asyncio — never one OS process or thread per game or per player. Scale by adding shard
replicas through the `HorizontalPodAutoscaler`, not by adding concurrency primitives
inside one process.

## 6. Resilience

1. On every move (or a short timer), a shard writes its sessions' minimal recovery state —
   board position, seats, clocks — into Redis, keyed by `room_id`.
2. Extend the existing reconnect path (`active_players` lookup + `SYNC_STATE`-on-reconnect
   in `ws_server.py`) so a reconnecting client can be served by *any* shard that
   rehydrates from Redis, not only the one that crashed.
3. Kubernetes liveness probes detect a dead shard and reschedule a replacement; because
   the WebSocket Gateway only ever knows a `room_id` (never the dead shard's address), the
   replacement just resubscribes to the same NATS subjects and reconnects transparently
   once it rehydrates the session from Redis.
4. If a session's state wasn't recoverable, resolve it as an aborted game with no rating
   change — the fallback path in the reconnect handler.
5. A Postgres outage only delays the game-end write-stream drain (step 1.4) — it never
   drops a result and never affects in-progress gameplay, since per-move traffic never
   touches Postgres. Only the API Gateway (login) needs to fail over to a promoted standby.

---

## Build order

1. Swap SQLite → Postgres in `persistence/`, keeping the same repo interfaces.
2. Stand up Redis; move `MatchmakingQueue` and reconnect lookup onto it.
3. Stand up NATS; add the game-end write stream (persistent NATS + drain workers).
4. Extract the API Gateway from `ws_server.py`, including the `PLAY`/`CANCEL_SEARCH` move
   from WebSocket to REST.
5. Containerize the Game Server Shard to subscribe/publish over per-room NATS subjects;
   add the WebSocket Gateway as a bridge between client sockets and those subjects.
6. Add the Game Allocator and the Matchmaker worker pool, wired together over NATS.
7. Wire up Observability (metrics, health endpoints, logs, load-test harness).
8. Add session-state mirroring to Redis and the rehydrate-on-reconnect path.
9. Validate the whole stack locally with Docker Compose.
10. Deploy under Kubernetes/K3s with liveness probes and a connections-based
    `HorizontalPodAutoscaler`; layer in a fleet manager (e.g. Agones) once shard churn
    makes hand-rolled lifecycle tracking a burden.
11. Replicate the whole stack per region once a single region is stable.
