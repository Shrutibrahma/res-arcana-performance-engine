from __future__ import annotations

from dataclasses import dataclass

from ..card_location import CardLocation
from ..card_type import CardType
from ..entity_data import EntityData
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class CostDestroyCardType:
    card_type_mask: int = 0

    def matches_type(self, data: EntityData) -> bool:
        if (self.card_type_mask & (1 << CardType.DRAGON)) and data.is_dragon:
            return True
        if (self.card_type_mask & (1 << CardType.CREATURE)) and data.is_creature:
            return True
        return False

    def pay(self, ctx: PowerContext) -> None:
        target_id = ctx.target_eid
        assert target_id is not None

        in_play = ctx.state.get_player_artifacts_in_play(ctx.pid)
        assert target_id in in_play, target_id

        entity = ctx.state.entities[target_id]
        assert entity.data
        assert self.matches_type(entity.data), target_id

        entity.location = CardLocation.DISCARD
        entity.essences_on_card = None
