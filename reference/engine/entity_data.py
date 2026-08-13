from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .action_types import UNOWNED, PlayerId
from .card_location import CardLocation
from .card_type import CardTypeMask, EntityFlag
from .component_type import ComponentType
from .discount import Discount
from .expansions import ExpansionCode
from .pool import Pool

if TYPE_CHECKING:
    from .collect_ability import CollectAbility
    from .power import Power

UNKNOWN_ORDER: int = -1


@dataclass(frozen=True, slots=True, kw_only=True)
class EntityData:

    name: str = ""
    powers: tuple[Power, ...] = ()
    collect_ability: CollectAbility | None = None
    expansion: ExpansionCode

    placement_cost: Pool | None = None
    placement_cost_any: int = 0

    card_type_mask: CardTypeMask = CardTypeMask.NONE
    entity_flags: EntityFlag = EntityFlag.NONE

    victory_points: int = 0
    victory_points_per_two_artifacts: int = 0

    discount: Discount = field(default_factory=Discount)

    points_per_essence: tuple[int, ...] = (0, 0, 0, 0, 0)

    base_points: int = 0
    vp_per_dragon: int = 0
    vp_per_creature: int = 0
    vp_per_artifact_count_num: int = 0
    vp_per_artifact_count_denom: int = 1

    @property
    def is_dragon(self) -> bool:
        return bool(self.card_type_mask & CardTypeMask.DRAGON)

    @property
    def is_creature(self) -> bool:
        return bool(self.card_type_mask & CardTypeMask.CREATURE)

    @property
    def cannot_be_free_placed(self) -> bool:
        return bool(self.entity_flags & EntityFlag.CANNOT_BE_FREE_PLACED)

    def total_placement_cost(self) -> int:
        if self.placement_cost is None:
            return self.placement_cost_any
        return self.placement_cost.total() + self.placement_cost_any


@dataclass
class Entity:

    kind: ComponentType
    data: EntityData
    location: CardLocation = CardLocation.OUT_OF_GAME
    owner_id: PlayerId = UNOWNED
    is_turned: bool = False

    essences_on_card: Pool | None = None

    order_index: int = UNKNOWN_ORDER
