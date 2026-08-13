"""Reference expectimax bot — single-file JSON-lines wire protocol server.

Speaks the bot protocol on stdin/stdout (one JSON message per line):
  new_game_from_setup  start/reset state from a serialized ResolveGameSetup
  search               run iterative-deepening expectimax, return chosen step
  advance              apply a step to the tracked state (or roll back on
                       illegal — used by `ActionFails` correctness tests)
  legal_actions        list the currently enumerable steps as JSON
  get_state            dump the full state for assertion-based tests
  quit                 graceful shutdown

This is the only bot the harness needs. Correctness tests drive the engine
through prescribed steps (the search code is unreached for those); the bench
drives the search.
"""

from __future__ import annotations

import copy
import json
import sys
import time
import traceback
from collections.abc import Sequence
from dataclasses import dataclass, field

from reference.engine.action_types import PlayerId
from reference.engine.actions import Action
from reference.engine.available_actions import (
    AvailableAction,
    AvailableActionResolveDrawReveal,
    AvailableActionResolveMonumentDraw,
    AvailableActionResolveMonumentReveal,
    AvailableActionResolveScryReveal,
)
from reference.engine.canonical_expand import expand_action, get_available_actions
from reference.engine.card_location import CardLocation
from reference.engine.entity_data import Entity
from reference.engine.game_engine import GameEngine
from reference.engine.game_phase import GamePhase
from reference.engine.game_state import GameState, create_game
from reference.engine.player_state import PlayerState
from reference.engine.pool import Pool
from reference.engine.state_dump import dump_state
from reference.engine.step_conversion import action_to_step, setup_step_to_action, step_to_action
from reference.engine.step_serialization import JsonValue, deserialize_step, serialize_step
from reference.engine.steps import ResolveGameSetup


# ===========================================================================
# Search: iterative-deepening expectimax with alpha-beta
# ===========================================================================

WIN_VALUE = 10000.0
LOSS_VALUE = -10000.0
HAND_WEIGHT = 0.25
GOLD_WEIGHT = 0.24
OTHER_ESSENCE_WEIGHT = 0.12

_CHANCE_ACTION_TYPES = (
    AvailableActionResolveDrawReveal,
    AvailableActionResolveMonumentDraw,
    AvailableActionResolveMonumentReveal,
    AvailableActionResolveScryReveal,
)

_DEADLINE_CHECK_INTERVAL = 256

_engine: GameEngine | None = None


def _get_engine() -> GameEngine:
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = GameEngine()
    return _engine


def clone_state(state: GameState) -> GameState:
    new = GameState.__new__(GameState)
    new.num_players = state.num_players
    new.artifact_range = state.artifact_range
    new.mage_range = state.mage_range
    new.magic_item_range = state.magic_item_range
    new.monument_range = state.monument_range
    new.pop_range = state.pop_range
    new.phase = state.phase
    new.round_number = state.round_number
    new.current_player_index = state.current_player_index
    new.first_player_index = state.first_player_index
    new.pending_turn_advance = state.pending_turn_advance
    new.winner_mask = state.winner_mask
    new.expansions = state.expansions
    new.is_mid_round_victory_check = state.is_mid_round_victory_check
    new.temp_vp = state.temp_vp.copy()

    entities: list[Entity] = []
    for e in state.entities:
        ne = Entity.__new__(Entity)
        ne.kind = e.kind
        ne.data = e.data
        ne.location = e.location
        ne.owner_id = e.owner_id
        ne.is_turned = e.is_turned
        ne.order_index = e.order_index
        ne.essences_on_card = Pool(values=list(e.essences_on_card)) if e.essences_on_card is not None else None
        entities.append(ne)
    new.entities = entities

    players: list[PlayerState] = []
    for p in state.players:
        np = PlayerState.__new__(PlayerState)
        np.pid = p.pid
        np.pool = Pool(values=list(p.pool))
        np.has_passed = p.has_passed
        np.has_first_player_token = p.has_first_player_token
        np.is_active = p.is_active
        players.append(np)
    new.players = players

    new.pending_stack = copy.deepcopy(state.pending_stack)
    return new


def apply_action(state: GameState, action: Action) -> None:
    _get_engine().execute_action(state, action)


def evaluate(state: GameState, pid: PlayerId) -> float:
    vp = float(_get_engine().calculate_victory_points(state, pid))
    pool = state.players[pid].pool
    gold = float(pool.gold)
    other = float(pool.elan + pool.life + pool.calm + pool.death)
    cards_in_hand = sum(1 for e in state.entities if e.owner_id == pid and e.location == CardLocation.HAND)
    return vp + GOLD_WEIGHT * gold + OTHER_ESSENCE_WEIGHT * other + HAND_WEIGHT * cards_in_hand


def evaluate_relative(state: GameState, pid: PlayerId) -> float:
    if state.phase == GamePhase.GAME_OVER:
        if pid in state.winner_ids:
            return WIN_VALUE
        return LOSS_VALUE

    my_score = evaluate(state, pid)
    if state.num_players == 1:
        return my_score

    best_opponent = max(evaluate(state, PlayerId(i)) for i in range(state.num_players) if i != pid)
    return my_score - best_opponent


def _is_chance_node(available: Sequence[AvailableAction]) -> bool:
    return len(available) > 1 and isinstance(available[0], _CHANCE_ACTION_TYPES)


@dataclass
class _Stats:
    nodes: int = 0
    max_depth: int = 0
    interrupted: bool = False
    deadline: float | None = None


def _expectimax(
    state: GameState,
    depth: int,
    maximizing_pid: PlayerId,
    alpha: float,
    beta: float,
    stats: _Stats,
) -> float:
    stats.nodes += 1

    if stats.deadline is not None and stats.nodes % _DEADLINE_CHECK_INTERVAL == 0:
        if time.monotonic() >= stats.deadline:
            stats.interrupted = True
            return evaluate_relative(state, maximizing_pid)

    if depth == 0 or state.phase == GamePhase.GAME_OVER:
        stats.max_depth = max(stats.max_depth, depth)
        return evaluate_relative(state, maximizing_pid)

    current_player = state.acting_player()
    available = get_available_actions(state, current_player)

    if not available:
        return evaluate_relative(state, maximizing_pid)

    if _is_chance_node(available):
        return _expectimax_chance(
            state, depth, maximizing_pid, available, current_player, alpha, beta, stats,
        )

    is_max = current_player == maximizing_pid
    best_value = float("-inf") if is_max else float("inf")

    for avail in available:
        for action in expand_action(state, avail, current_player):
            child = clone_state(state)
            apply_action(child, action)

            value = _expectimax(child, depth - 1, maximizing_pid, alpha, beta, stats)

            if stats.interrupted:
                return evaluate_relative(state, maximizing_pid)

            if is_max:
                if value > best_value:
                    best_value = value
                alpha = max(alpha, best_value)
            else:
                if value < best_value:
                    best_value = value
                beta = min(beta, best_value)

            if beta <= alpha:
                break

    return best_value


def _expectimax_chance(
    state: GameState,
    depth: int,
    maximizing_pid: PlayerId,
    available: Sequence[AvailableAction],
    current_player: PlayerId,
    alpha: float,
    beta: float,
    stats: _Stats,
) -> float:
    prob = 1.0 / len(available)
    expected = 0.0
    outcomes = 0

    for avail in available:
        for action in expand_action(state, avail, current_player):
            child = clone_state(state)
            apply_action(child, action)

            value = _expectimax(child, depth - 1, maximizing_pid, alpha, beta, stats)
            outcomes += 1

            if stats.interrupted:
                return expected / (outcomes * prob) if outcomes > 0 else evaluate_relative(state, maximizing_pid)

            expected += prob * value

    if outcomes == 0:
        return evaluate_relative(state, maximizing_pid)

    return expected


@dataclass
class SearchResult:
    value: float
    best_action: Action | None
    nodes: int = 0
    depth_completed: int = 0


def iterative_deepening(
    state: GameState,
    pid: PlayerId,
    max_depth: int = 30,
    deadline: float | None = None,
) -> SearchResult:
    best_action: Action | None = None
    best_value = LOSS_VALUE
    total_nodes = 0
    depth_completed = 0

    available = get_available_actions(state, pid)
    root_actions: list[Action] = []
    for avail in available:
        root_actions.extend(expand_action(state, avail, pid))

    assert root_actions, "No actions available at root"

    for depth in range(1, max_depth + 1):
        if deadline is not None and time.monotonic() >= deadline:
            break

        stats = _Stats(deadline=deadline)
        depth_best_value = float("-inf")
        depth_best_action: Action | None = None

        for action in root_actions:
            child = clone_state(state)
            apply_action(child, action)

            value = _expectimax(child, depth - 1, pid, float("-inf"), float("inf"), stats)

            if stats.interrupted:
                break

            if value > depth_best_value:
                depth_best_value = value
                depth_best_action = action

        total_nodes += stats.nodes

        if not stats.interrupted:
            depth_completed = depth
            best_value = depth_best_value
            best_action = depth_best_action

            if best_value >= WIN_VALUE - 1000.0:
                break
        else:
            break

    assert best_action is not None, "Iterative deepening must complete at least depth 1"

    return SearchResult(
        value=best_value,
        best_action=best_action,
        nodes=total_nodes,
        depth_completed=depth_completed,
    )


# ===========================================================================
# Wire-protocol server
# ===========================================================================

_COMMANDS = frozenset({
    "quit", "new_game_from_setup", "search", "advance",
    "get_state", "legal_actions",
})


@dataclass
class Session:
    state: GameState
    engine: GameEngine
    player_id: int
    cached_actions: list[Action] = field(default_factory=list)

    def refresh_actions(self) -> None:
        pid = PlayerId(self.state.acting_player())
        available = get_available_actions(self.state, pid)
        self.cached_actions = []
        for avail in available:
            self.cached_actions.extend(expand_action(self.state, avail, pid))


def _respond(msg: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _new_session(msg: dict[str, JsonValue], engine: GameEngine) -> Session:
    setup_json = msg["setup"]
    assert isinstance(setup_json, dict)
    setup_step = deserialize_step(setup_json)
    assert isinstance(setup_step, ResolveGameSetup)

    raw_pid = msg["player_id"]
    assert isinstance(raw_pid, int)
    raw_np = msg.get("num_players", 2)
    assert isinstance(raw_np, int)

    state = create_game(db=engine.db, num_players=raw_np)
    engine.execute_action(state, setup_step_to_action(setup_step))

    session = Session(state=state, engine=engine, player_id=raw_pid)
    session.refresh_actions()
    return session


def _handle_search(session: Session, msg: dict[str, JsonValue]) -> dict[str, object]:
    raw_depth = msg.get("depth", 3)
    assert isinstance(raw_depth, int)
    raw_max_pid = msg.get("maximizing_pid")
    pid = PlayerId(raw_max_pid) if isinstance(raw_max_pid, int) else PlayerId(session.player_id)

    result = iterative_deepening(session.state, pid, max_depth=raw_depth)
    assert result.best_action is not None, "expectimax returned best_action=None — search is incomplete"

    step = action_to_step(result.best_action, session.state)
    return {
        "step": serialize_step(step),
        "nodes": result.nodes,
        "depth": result.depth_completed,
    }


def main() -> None:
    engine = GameEngine()
    session: Session | None = None

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            msg: dict[str, JsonValue] = json.loads(line)
        except json.JSONDecodeError as e:
            _respond({"error": f"Invalid JSON: {e}"})
            continue

        cmd = msg.get("cmd")
        if not isinstance(cmd, str) or cmd not in _COMMANDS:
            _respond({"error": f"Unknown command: {cmd!r}"})
            continue

        try:
            if cmd == "quit":
                _respond({"status": "ok"})
                break

            elif cmd == "new_game_from_setup":
                session = _new_session(msg, engine)
                _respond({"status": "ok"})

            elif cmd == "search":
                assert session is not None, "No active session"
                _respond(_handle_search(session, msg))

            elif cmd == "advance":
                assert session is not None, "No active session"
                step_json = msg["step"]
                assert isinstance(step_json, dict)
                step = deserialize_step(step_json)

                snapshot = copy.deepcopy(session.state)
                try:
                    session.engine.execute_action(
                        session.state, step_to_action(session.state, step),
                    )
                    session.refresh_actions()
                    _respond({"status": "ok"})
                except (AssertionError, ValueError) as illegal:
                    # ActionFails tests rely on the bot rolling back on illegal steps.
                    session.state = snapshot
                    _respond({"status": "error", "msg": str(illegal)})

            elif cmd == "get_state":
                assert session is not None, "No active session"
                _respond({"state": dump_state(session.state, session.engine)})

            elif cmd == "legal_actions":
                assert session is not None, "No active session"
                steps = [
                    serialize_step(action_to_step(a, session.state))
                    for a in session.cached_actions
                ]
                _respond({"actions": steps})

        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            _respond({"error": f"{cmd} failed: {e}"})


if __name__ == "__main__":
    main()
