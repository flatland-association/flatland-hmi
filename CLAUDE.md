# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flatland HMI is a prototype Human-Machine Interface for interacting with [Flatland](https://flatland.aicrowd.com) railway simulations. An Angular frontend visualizes the railway environment and controls the simulation; a FastAPI backend manages the Flatland env and exposes REST APIs.

## Commands

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload   # dev server on :8000
pytest -s                             # run entire backend test suite
pytest app/test_routes.py -v          # run tests
pytest app/test_link_map.py -v        # run link-map tests
pytest app/test_env.py -v             # run env/policy loop smoke tests
```

**Gotcha**: `requirements.txt` pins `flatland-baselines@feature/deprecate-agent-position` (not `main`) because that branch fixes `FullEnvObservation.reset()` to accept the `env` argument required by the `ObservationBuilder.reset(self, env)` contract — on `main` it takes no argument, so `policy-1` (`DeadLockAvoidancePolicy`) fails with `FullEnvObservation.reset() takes 1 positional argument but 2 were given`. That branch depends on a matching `flatland-rl@feature/deprecate-agent-position`, which also removes `EnvAgent`'s backward-compat `.target`/`.position`/`.direction`/`.old_position`/`.old_direction`/`.initial_position`/`.initial_direction` properties (see "Key data conventions" below). CI (`.github/workflows/checks.yml`) and `backend/Dockerfile` both force-install that same `flatland-rl` branch after `requirements.txt` (marked `# TODO revert to @main once feature/deprecate-agent-position merges`):

```bash
pip install -U git+https://github.com/flatland-association/flatland-rl.git@feature/deprecate-agent-position
```

Apply the same override locally until both branches merge upstream. This pin has moved before — it previously pointed at `feature/generator-stations-fix-link` to work around a since-resolved `is_neighbor_cell` gap — so check the `# TODO` comments in `requirements.txt`/`Dockerfile`/`checks.yml` for the current branch before trusting this paragraph.

### Frontend

```bash
cd frontend
npm install
npm start        # dev server on :4200
npm test         # unit tests (Karma)
npm run build    # production build
```

### Docker (pre-built images)

```bash
docker run -p 8000:8000 ghcr.io/flatland-association/flatland-hmi-backend:latest
docker run -p 80:80    ghcr.io/flatland-association/flatland-hmi-frontend:latest
```

## Architecture

### Data pipeline (see `ZWL.md`)

The three frontend views correspond to entry points at `frontend/src/app/{map,link-map,marey}`:
- **Map** — the full Flatland grid with agents (`MapComponent`).
- **Link Map** — a linearized view of one station-to-station link (`LinkMapComponent`).
- **ZWL** (Zeit-Weg-Linie) — the time-space/Marey diagram (`MareyComponent`).

End-to-end data flow: `flatland-rl`'s `SparseRailGenerator` produces the rail grid and `StationsLinks` → `backend/app/link_map.py` (`extract_link_map`) linearizes a link's fibre into a link map + env↔link-map coordinate mapping → the frontend renders the link map and, combined with per-agent `(i, t, r, c)` trajectory data, the ZWL diagram. See `ZWL.md` for the full mermaid diagram and links to the `stations_links` docs and originating PRs.

### Backend (`backend/`)

- **`main.py`** — FastAPI app; CORS middleware (origins from `ALLOW_ORIGINS` env var, default `localhost:4200,localhost`); registers `CustomEncoder` for numpy types, `Fraction`, `Waypoint`, `SpeedCounter`.
- **`app/env.py`** — `env_map` and `policy_map` are the authoritative registries for available environments and policies.
- **`app/trajectory_context.py`** — `TrajectoryContext` (NamedTuple: `trajectory`, `meta`, `policy_runner`) is the core simulation unit. `TrajectoryContext.create()` mints a UUID, builds env + policy runner, persists `meta.json`. `TrajectoryContext.resolve()` loads from `trajectory_context_map` (in-memory) or disk. `DATA_DIR` defaults to `./hmi_data_dir` (override with `HMI_DATA_DIR` env var). Note: in-memory map means multi-process deployments are not supported.
- **`app/routes.py`** — All API routes plus `build_stations_and_links_payload(stations_links: StationsLinks) -> dict` and `_enrich_link(link, link_id)`. The global-env routes (`/transitions`, `/agents`, `/step`, `/reset`) are deprecated; use trajectory-based routes. `CustomEncodedJSONResponse` is used for all responses containing numpy/Flatland types.
- **`app/link_map.py`** — ZWL/link-map grid generation. Key public function: `extract_link_map(stations_links: StationsLinks, link: Link, fibre: Fibre, rail: GridTransitionMap) -> dict`. No `RailEnv` dependency — all env access goes through `rail: GridTransitionMap` and the `StationsLinks` dataclass. Helper functions `_extract_city_rotated`, `_find_all_paths_between_stations`, `_handle_beyond_one_one` follow the same pattern.

**`env.stations_links`** is a `StationsLinks` dataclass (from `flatland.envs.stations_links`). Always use attribute access — never dict subscript. Current dataclass hierarchy:

```
StationsLinks
  .stations: Dict[str, Station]       # keyed by station char ("A", "B", ...)
    Station.name: str
    Station.gates: Dict[str, Gate]    # keyed by direction char ("N", "E", "S", "W")
      Gate.name: str                  # e.g. "A.N"
      Gate.pins: Dict[int, Pin]       # keyed by track index
        Pin.name: str                 # e.g. "A.N.0"
        Pin.node: IntVector2D
    Station.stopping_points: List[StoppingPoint]
      StoppingPoint.name: str         # e.g. "A.0"
      StoppingPoint.node: IntVector2D
    Station.edges: List[IntVector2D]
  .links: List[Link]
    Link.from_gate: str               # e.g. "A.N"   -- one Link is a GATE-to-gate connection
    Link.to_gate: str                 # e.g. "B.S"
    Link.fibres: List[Fibre]          # each Fibre is one concrete pin-to-pin route within the gate pair
      Fibre.edges: List[IntVector2D]
      Fibre.from_pin: str             # e.g. "A.N.0" -- pin identity lives on the Fibre, not the Link
      Fibre.to_pin: str                # e.g. "B.S.1"
```

Always use keyword args when constructing dataclasses: `Fibre(edges=cells, from_pin=from_pin, to_pin=to_pin)`, not positional args.

**Resolving gate/pin names**: never `.split(".")` a fully-qualified name (e.g. `"A.N.0"`) — walk the `stations_links.stations → gates → pins` hierarchy and match on `.name` instead. `link_map.py` provides `_resolve_gate(stations_links, gate_name) -> (station_name, dir_char, Gate)` and `_resolve_pin(stations_links, pin_name) -> (station_name, dir_char, Gate, pin_key)` for this; `routes.py` builds an equivalent `gate_name_to_station` lookup once while traversing stations/gates in `build_stations_and_links_payload`. Gate direction char maps to facing int via `_DIRECTION_CHARS`.

**Current API surface (trajectory-based):**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/trajectories` | Create trajectory; body `{env_id, policy_id}`; returns UUID string |
| POST | `/trajectories/{id}/step` | Advance one step; optional body `{policy_id}` to override policy |
| POST | `/trajectories/{id}/fork` | Fork at current step |
| GET | `/trajectories/{id}/transitions` | Rail grid as nested list (16-bit bitmasks) |
| GET | `/trajectories/{id}/agents` | Agent state list |
| GET | `/trajectories/{id}/stations` | Station + link data |
| GET | `/trajectories/{id}/links` | All links enriched with labels (one per `Link` object) |
| GET | `/trajectories/{id}/links/{link_id}` | Single enriched link |
| GET | `/trajectories/{id}/link/{link_id}/map` | ZWL grid + env↔ZWL coordinate mapping + level assignments |
| GET | `/trajectories/{id}/agent_plans` | Predicted future agent trajectories (shortest path to target); see below |
| GET | `/policies` | Available policy IDs |
| GET | `/envs` | Available environment IDs |

**Key backend helpers:**

`build_stations_and_links_payload(stations_links)` returns (top-level keys are camelCase — no snake_case-to-camelCase translation needed on the frontend for this payload):
- `stationEdges`: `{stationChar: [[r,c], ...]}` — city boundary cells
- `stationStoppingPoints`: `{stationChar: [{node, trackName}, ...]}` — no `trackNumber`
- `stationGates`: `{stationChar: {dirChar: {name, pins: {idx: {name, node}}}, ...}}`
- `links`: one entry per `{fromStation, toStation, fromGate, toGate, fromPin, toPin, fibres: [{cells}]}`. Granularity is controlled by the `USE_PIN_TO_PIN_LINK_LABELS` flag (see below): default (`False`) emits one entry per `Link` (one per gate pair), `fromPin`/`toPin` taken from the first fibre and `fibres` carrying every fibre's cells; when `True` it emits one entry per `Fibre` instead (one per pin pair), each with a single-fibre `fibres` list.

`_enrich_link(link, link_id)` builds `{cityFrom, cityTo, fromGate, toGate, label, startStationName, endStationName}` from an already-built payload link dict; `label` is `"Link {id} ({fromGate} → {toGate})"` by default, or `"Link {id} ({fromPin} → {toPin})"` when `USE_PIN_TO_PIN_LINK_LABELS` is `True`.

`extract_link_map(stations_links, link, fibre, rail)` returns `{grid, mapping, levels, incompleteCells}` where `levels` is `[[[r,c], level_int], ...]` and `incompleteCells` is `[[[r,c], reason_str], ...]` for link-map cells whose transition couldn't be fully derived.

**Link semantics**: each `Link` object is one GATE-to-gate connection (`from_gate`→`to_gate`); its `fibres` are the concrete pin-to-pin routes within that gate pair, each carrying its own `from_pin`/`to_pin`. `link_id` indexes directly into `env.stations_links.links`. The `/link/{link_id}/map` route always uses `link.fibres[0]` as the representative path (guard for empty fibres list) regardless of `USE_PIN_TO_PIN_LINK_LABELS` — so when that flag is `True`, `/links` link IDs (per-fibre) and `/link/{id}/map` link IDs (per-gate-link) are no longer aligned.

`_find_all_paths_between_stations` uses **all pins** at the link's from-gate and to-gate (not just one fibre's specific pins) to discover all parallel tracks.

**`USE_PIN_TO_PIN_LINK_LABELS`** (module-level flag in `routes.py`, default `False`): flips `/links` endpoints from gate-to-gate granularity/labels back to the old pin-to-pin behavior. Kept for callers that still expect one entry per pin pair.

`_build_agent_plans_content(env)` (backs `/agent_plans`) computes, per non-`DONE` agent, the shortest path (`get_k_shortest_paths`, `k=1`) from `agent.current_configuration` — or `agent.initial_configuration` if the agent hasn't departed yet (`current_configuration is None`) — to its target. `DONE` agents contribute nothing; if no agent has a path, the whole endpoint returns `[]`. All agents' waypoints are merged into a single plan (a list of `{handle: Agent}` snapshots), left-padded with empty `{}` entries up to `env._elapsed_steps` so the plan's absolute array index lines up with the frontend's `history`/`timestep` numbering (see "ZWL/plan step indexing" below) — this is a real per-agent shortest path, not a rollout of any policy.

### Frontend (`frontend/src/app/`)

`MapComponent`, `LinkMapComponent`, and `MareyComponent` are all mounted simultaneously inside `<main>` in `app.component.html` — they are **not** separate routed views. All three are always on screen together and share one global `ControllerService`/`StateService` instance, which is why the simulation controls (Time Machine, Step/Play/Stop, Reset) live in `MapComponent`'s template but affect all three views at once.

**Service responsibilities:**

- **`DataService`** — All HTTP calls. Every call pipes `catchError` → `ErrorMessageService`. Key interfaces: `StationsResponse` (`stationEdges`, `stationGates`, `stationStoppingPoints` — no `trackNumber`), `Link` (`cityFrom`, `cityTo`, `fromGate`, `toGate`, `label`, `startStationName`, `endStationName`), `LinkMap` (`grid`, `mapping`, `levels`). Method `getTrajectoryLinkMap(trajectoryId, linkId)` calls `GET /trajectories/{id}/link/{linkId}/map`; `getTrajectoryAgentPlans(trajectoryId)` calls `GET /trajectories/{id}/agent_plans`.
- **`ControllerService`** — Owns `trajectoryId` ReplaySubject, `stepQueue`/`isProcessingQueue`, and `interval` for play/stop. `reset()` creates a trajectory, calls `selectLink('0')` (async), then `Promise.all([getTransitions, getAgents, getStations, getAgentPlans]) → loadTrajectory() + setPlans()`. `step()` stops any active `play()` interval before calling `next()`, so a manual Step click while playing doesn't compete with the ticker for the step queue. In the step loop (`_drainQueue`), `stateService.applyStep(...)` **must** run before `stateService.setPlans(...)` — `applyStep` bumps `history`/timestep, and Marey's plans subscriber reads the current timestep synchronously when `plans` emits, so publishing plans first makes planned routes render one step behind "now" (a real regression, fixed and covered by `controller.service.spec.ts`).
- **`StateService`** — Pure reactive state store with no HTTP calls. Owns `ReplaySubject`s for `transitions`, `agents`, `state`, `history`, `plans`, `stations`, `selectedLink`, `links`, `linkMap`, `envs`, `policies`, `replayTime`. `clearHistory()` (called from `ControllerService.reset()`) also resets `plans` to `[]` and `replayTime` to `null`. `getDisplayedAgents()` is the one components should subscribe to for rendering agents — see "Time machine / replay" below. `setPlans()`/`getPlans()` carry the `/agent_plans` response through to `MareyComponent`.
- **`RendererService`** — Maps 16-bit transition bitmasks to CSS/SVG classes; builds `MapCell[][]`. `MapCell` fields: `ground`, `transition` (raw bitmask as `data-transition`), `stationBuilding?`, `station?`, `pin?`, `pinLabel?`, `trackName?` — no `trackNumber`. Uses `CoordMap<V>` (in the same file) for 2D lookups. Unknown non-zero transitions → `['track', 'transition_invalid']`. `renderMap(..., showBackground=true)` — link-map component passes `false`.
- **`ErrorHandlerService`** (`features/error-handler/`) — registered as the global Angular `ErrorHandler` in `app.config.ts`; catches uncaught errors app-wide (distinct from `ErrorMessageService`, which handles `catchError` from HTTP calls).
- **`AuthService`** (`features/auth/`) — wraps `angular-oauth2-oidc`; no-ops if `environment.authConfig` is unset, so OIDC login is opt-in per deployment rather than required for local dev.

**Component overview:**

- **`MapComponent`** — Full simulation map; subscribes to `combineLatest([getTransitions(), getStations()])` → `renderMap`; also subscribes to `getLinkMap()` for `level-labels` overlay. Renders agents from `getDisplayedAgents()` (not `getAgents()`). Owns the controller bar's three `fieldset` groups ("Time Machine", "Simulation Time", "Environment") and the Time Machine's `nowTime`/`replayTime`/`enterTimeMachine()`/`leaveTimeMachine()`/`timeMachinePrev()`/`timeMachineNext()`. Step/Play are `[disabled]` once `state.done.__all__`.
- **`LinkMapComponent`** (`app-link-map`, at `link-map/link-map.component.ts`) — Link-specific ZWL view; subscribes to `combineLatest([getLinkMap(), getStations()])`; `transformStationsForZwl()` maps coordinates through `this.mapping`; calls `renderMap(..., false)`. Also renders agents from `getDisplayedAgents()`.
- **`MareyComponent`** — Space-time diagram; `getPolylinePath()` uses `M`/`L` SVG with pen-up on unmapped positions; displays `fromGate`/`toGate` at axis ends. Draws a red NOW line at `timestep` (`= history.length`) and, when replaying, a green REPLAY line at `replayTime`, in the same LIVE-green (`#2e9e44`)/REPLAY-red (`#c0392b`) colors as `ReplayBadgeComponent`. `plannedRuns` (from `getPlans()`) render as dashed per-agent routes; `getPlanLabels()` groups route-endpoint labels by pixel position so agents sharing an identical source+target (and therefore an identical path) get one merged `"id/id/id"` label instead of stacked overlapping ones.
- **`ReplayBadgeComponent`** (`app-replay-badge`) — Small standalone LIVE/REPLAY pill, self-positioned top-right via `:host { position: absolute }` (host container must be `position: relative`); reads `StateService.getReplayTime()` directly, no `@Input`s. Used in `MapComponent` and `MareyComponent`, not in `LinkMapComponent`.

**Time machine / replay:**

`StateService.replayTime` (`number | null`, `null` = live) holds a step count in the same numbering as `state.steps`/`history.length` — i.e. 1-based, not a 0-based array index. `getDisplayedAgents()` combines live `agents`, `history`, and `replayTime`: when replaying it returns `Object.values(history[replayTime - 1])`, falling back to live agents if that snapshot doesn't exist. `MapComponent.enterTimeMachine()` seeds `replayTime` with the current `nowTime`; `timeMachinePrev()`/`timeMachineNext()` clamp to `[1, nowTime]`; `leaveTimeMachine()` sets it back to `null`. New steps arriving while replaying do **not** auto-advance `replayTime` — the view stays frozen at the chosen step until the user moves it or leaves.

**Reactive data flow:**

```
ControllerService.reset(env, policy)
  → createTrajectory → trajectoryId.next()
      → switchMap → getTrajectoryLinks() → stateService.setLinks()
  → selectLink('0') [async]
      → getTrajectoryLinkMap() → stateService.setLinkMap()
  → Promise.all([getTransitions, getAgents, getStations, getAgentPlans])
      → stateService.loadTrajectory(transitions, agents, stations)
      → stateService.setPlans(plans)

ControllerService.next() / _drainQueue() [one simulation step]
  → stepTrajectory()
  → Promise.all([getAgents, getAgentPlans])
      → stateService.applyStep(trajectoryStep, agents)   [MUST run first — bumps history/timestep]
      → stateService.setPlans(plans)                      [reads the now-current timestep in Marey]

ControllerService.selectLink(id)
  → stateService.selectLink(id)
  → getTrajectoryLinkMap() → stateService.setLinkMap()
```

### Adding environments or policies

Edit `backend/app/env.py`: add entries to `env_map` and `policy_map`. The `/envs` and `/policies` routes expose new keys automatically.

### Tests

`backend/app/test_routes.py` — HTTP integration tests via `TestClient`; almost all trajectory-creation calls use the fixed-seed `generated-seed-44` env rather than the unseeded `generated-0`, specifically to stay deterministic (see Gotcha below) — only `test_get_envs`'s catalog check needs the literal unseeded IDs. `backend/app/test_link_map.py` — regression tests for `extract_link_map` with recorded expected outputs (see `_gen_material()`/`test_nop` for regenerating the `material` fixture list after a `stations_links` model change); use `Fibre(edges=cells, from_pin=from_pin, to_pin=to_pin)` (keyword args) when constructing test fixtures. `backend/app/test_env.py::test_loop` intentionally samples 10 different `generated-0`/`generated-1` environments per `(env_id, policy_id)` pair via `seed=n` — see Gotcha below for why that explicit seed is required.

**Gotcha — unseeded `generated-0`/`generated-1` are not reproducible via global RNG seeding**: flatland's `env_generator()` draws its seed from OS entropy when `seed=None` (`seeding.np_random(None)` → `create_seed(None)`), **not** from Python's or numpy's global RNG state — seeding `random`/`np.random` before calling it has no effect. This used to cause intermittent full-suite-only test failures (a degraded/disconnected generated layout tripping `DeadLockAvoidancePolicy`'s path-finding or a link-map assertion). Fixed by passing an explicit `seed=` into the factory call wherever determinism matters — see the Tests section above; don't reintroduce unseeded `generated-0`/`generated-1` calls in new tests without a reason to want that variety.

Frontend: `frontend/src/app/{data,state,controller}.service.spec.ts` (Karma/Jasmine, run via `npm test`) cover the agent-plans and time-machine wiring described above — `DataService.getTrajectoryAgentPlans` HTTP shape, `StateService.getDisplayedAgents`/`setPlans`/`clearHistory` reactive behavior, and `ControllerService`'s `reset()`/step-loop orchestration (mocking `DataService`/`StateService` via `jasmine.createSpyObj`, since `ControllerService`'s constructor auto-triggers `reset()` once `getEnvs()`/`getPolicies()` resolve non-empty — keep those spies resolving to `[]` in tests that don't want that). This is the first non-trivial frontend test coverage in the repo (previously only `error-handler.service.spec.ts` existed) — follow its patterns for new service specs rather than introducing a different style.

### Key data conventions

- **Station keys** are single character strings ("A", "B", …). Never convert to integer indices.
- **Gate keys** within `Station.gates` are direction chars ("N", "E", "S", "W"). **Pin keys** within `Gate.pins` are ints.
- **`stationGates` payload shape**: `{stationChar: {dirChar: {name, pins}}}` — dict of dicts.
- **2D coordinate maps**: use `CoordMap<V>` (from `renderer.service.ts`) with `[number, number]` tuple keys.
- **`link_id`** indexes directly into `env.stations_links.links[]`. Each link is one gate-to-gate connection; pin-to-pin identity lives on its `fibres`.
- **ZWL levels**: `LinkMap.levels` is `[[[r,c], level], ...]`; level 0 = main fibre, ±1 = parallel tracks.
- **`env.stations_links`**: always attribute access (`.stations`, `.links`, etc.); always keyword args when constructing dataclasses.
- **`extract_link_map` takes no `RailEnv`**: pass `env.rail` (`GridTransitionMap`). Same pattern for all helper functions.
- **Snake_case → camelCase**: most backend payload fields are snake_case (e.g. `TrajectoryStep`'s `ep_id`/`policy_id`/`env_id`/`elapsed_steps`), matched verbatim by their TypeScript interfaces. Exception: `build_stations_and_links_payload`'s top-level keys (`stationEdges`, `stationGates`, `stationStoppingPoints`) are built as camelCase directly in the backend, so `StationsResponse` needs no snake_case-to-camelCase translation in `DataService`.
- **`EnvAgent` (flatland-rl) has no position/direction/target properties** on the pinned branch (see Gotcha above) — use `agent.current_configuration` (`Optional[Tuple[position, direction]]`) instead of `.position`/`.direction`, and `agent.targets` (`Set[Tuple[position, direction]]`) instead of `.target`. `routes.py`'s `_build_agents_content` shows the pattern, including picking a representative target via `next(iter(agent.targets))[0]`. The JSON response shape (`position`, `direction`, `target` keys) is unchanged — only the Python-side attribute access changed, so the frontend `Agent` interface needed no updates.
- **ZWL/plan step indexing**: `history` and `plans` entries (both `Array<Record<string, Agent>>` per absolute step) are 0-indexed by step, but `state.steps`/`timestep`/`replayTime`/`env._elapsed_steps` count elapsed steps 1-based — index `N` in `history`/a `plan` corresponds to elapsed-step count `N + 1`. Backend `_build_agent_plans_content` left-pads a plan with `{}` up to `env._elapsed_steps` for exactly this reason. On the frontend, always carry the *absolute* step index through any `.filter()`/`.map()` chain over these arrays instead of re-deriving it from a filtered array's local index — `MareyComponent`'s planned-route rendering did the latter and silently reset every plan to start at t=0 (fixed; see `d349bdc`).
- **Known issue**: the level-propagation loop in `_assign_levels_in_station_to_station_graph` is `for level in [0, 1, -1, 2 - 2]` — `2 - 2` evaluates to `0`, so level 0 runs twice and levels ±2 are never reached. The equivalent loop in `_assign_levels_for_context` already has the `2 - 2` term commented out.
- **Python type hints** (`backend/app/link_map.py` and similar): use uppercase generics from `typing` (`Dict`, `List`, `Set`, `Tuple`, `Optional`) rather than lowercase builtin generics (`dict[...]`, `list[...]`, `set[...]`, `tuple[...]`). Use `IntVector2D` (from `flatland.core.grid.grid_utils`) for grid cell/position type hints instead of a bare `Tuple`. Drop `[Any]` parameterization when a generic's type argument(s) would otherwise be entirely `Any` — leave the type bare instead (e.g. `GridTransitionMap`, not `GridTransitionMap[Any]`; `Dict`, not `Dict[Any, Any]`). Keep partial/mixed parameterizations that carry real information (e.g. `Dict[str, Any]`, `ndarray[Any, dtype[floating[_64Bit]]]`).
