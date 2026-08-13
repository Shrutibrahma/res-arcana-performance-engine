from __future__ import annotations

from dataclasses import dataclass

from ..card_location import CardLocation
from ..entity_data import EntityData
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class CostDiscardCard:

    card_type_mask: int = 0
    exclude_entity_flags: int = 0

    def matches_type(self, data: EntityData) -> bool:
        if self.card_type_mask == 0:
            return True
        return bool(self.card_type_mask & data.card_type_mask)

    def pay(self, ctx: PowerContext) -> None:
        target_id = ctx.target_eid
        assert target_id is not None

        hand = ctx.state.get_player_hand(ctx.pid)
        assert target_id in hand, target_id

        entity = ctx.state.entities[target_id]
        assert not (self.exclude_entity_flags and (entity.data.entity_flags & self.exclude_entity_flags))
        assert not entity.data or self.matches_type(entity.data), target_id
        ctx.state.entities[target_id].location = CardLocation.DISCARD
