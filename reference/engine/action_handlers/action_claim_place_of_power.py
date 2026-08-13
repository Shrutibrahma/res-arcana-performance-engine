from __future__ import annotations

from dataclasses import dataclass, field

from ..action_types import EntityId, PlayerId
from ..card_location import CardLocation
from ..component_type import ComponentType
from ..pool import Pool
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionClaimPlaceOfPower:
    pid: PlayerId
    eid: EntityId
    pay: Pool = field(default_factory=Pool)

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        player = state.players[self.pid]

        pop_eid = self.eid

        assert 0 <= pop_eid < len(state.entities), pop_eid

        pop = state.entities[pop_eid]
        assert pop.kind == ComponentType.PLACE_OF_POWER, pop.kind
        assert pop.location == CardLocation.AVAILABLE, pop.location

        pop_data = pop.data
        assert pop_data

        total_cost = pop_data.total_placement_cost()
        assert player.pool.total() >= total_cost

        fixed_cost = pop_data.placement_cost if pop_data.placement_cost else Pool()
        assert player.pool.can_afford(fixed_cost)

        player.pool.pay(fixed_cost)

        any_cost = pop_data.placement_cost_any
        if any_cost > 0:
            assert self.pay.total() == any_cost, (self.pay.total(), any_cost)
            player.pool.pay(self.pay)

        pop = state.entities[pop_eid]
        assert pop.location == CardLocation.AVAILABLE, pop.location
        pop.location = CardLocation.IN_PLAY
        pop.owner_id = self.pid
