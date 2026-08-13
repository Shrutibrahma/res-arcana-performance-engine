from __future__ import annotations

from typing import Any

from .action_types import PlayerId
from .game_engine import GameEngine
from .game_phase import GamePhase
from .game_state import GameState


def dump_state(state: GameState, engine: GameEngine) -> dict[str, Any]:
    return {
        "phase": state.phase.name,
        "round": state.round_number,
        "current_player": state.acting_player(),
        "first_player": state.first_player_index,
        "winner_ids": list(state.winner_ids),
        "players": [
            {
                "pool": list(state.players[i].pool),
                "vp": engine.calculate_victory_points(state, PlayerId(i)),
                "has_passed": state.players[i].has_passed,
                "has_first_player_token": state.players[i].has_first_player_token,
            }
            for i in range(state.num_players)
        ],
        "entities": [
            {
                "name": e.data.name,
                "kind": e.kind.name,
                "location": e.location.name,
                "owner": int(e.owner_id),
                "is_turned": e.is_turned,
                "essences_on_card": list(e.essences_on_card) if e.essences_on_card is not None else None,
                "order_index": e.order_index,
            }
            for e in state.entities
        ],
    }


class StateView:

    def __init__(self, dump: dict[str, Any]):
        self.dump = dump

    @property
    def phase(self) -> GamePhase:
        return GamePhase[self.dump["phase"]]

    @property
    def current_player(self) -> int:
        return self.dump["current_player"]

    @property
    def winner_ids(self) -> list[int]:
        return list(self.dump["winner_ids"])

    def player_pool(self, pid: int) -> list[int]:
        return list(self.dump["players"][pid]["pool"])

    def player_vp(self, pid: int) -> int:
        return self.dump["players"][pid]["vp"]

    def player_passed(self, pid: int) -> bool:
        return self.dump["players"][pid]["has_passed"]

    def find_entity(self, name: str) -> dict[str, Any]:
        for e in self.dump["entities"]:
            if e["name"] == name:
                return e
        raise AssertionError(f"Entity {name!r} not found in state")
