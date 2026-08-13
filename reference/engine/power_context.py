from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .action_types import EntityId, PlayerId
from .component_type import ComponentType
from .pool import Pool

if TYPE_CHECKING:
    from .entity_data import Entity
    from .game_engine import GameEngine
    from .game_state import GameState
    from .player_state import PlayerState


@dataclass
class PowerContext:

    engine: GameEngine
    state: GameState
    pid: PlayerId
    entity: Entity
    eid: EntityId | None = None

    pay_essence_cost: Pool | None = None

    target_eid: EntityId | None = None
    target_pid: PlayerId | None = None

    pay: Pool = field(default_factory=Pool)
    identical_amount: int = 0

    component_type: ComponentType | None = None
    gain: Pool = field(default_factory=Pool)

    @property
    def player(self) -> PlayerState:
        return self.state.players[self.pid]

    @property
    def entity_id(self) -> EntityId | None:
        return self.eid

    @property
    def entity_name(self) -> str:
        return self.entity.data.name
