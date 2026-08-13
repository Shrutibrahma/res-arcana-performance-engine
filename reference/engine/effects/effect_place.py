from __future__ import annotations

from dataclasses import dataclass, field

from ..pending_choices import PendingPlacementChoice
from ..power_context import PowerContext
from ..select_card_filter import SelectCardFilter


@dataclass(frozen=True, slots=True)
class EffectPlace:
    filter: SelectCardFilter = field(default_factory=SelectCardFilter)
    discount: int = 0
    free: bool = False
    can_discount_gold: bool = False

    def execute(self, ctx: PowerContext) -> None:
        assert ctx.eid is not None
        ctx.state.pending_stack.append(
            PendingPlacementChoice(
                pid=ctx.pid,
                source_eid=ctx.eid,
                filter=self.filter,
                discount=self.discount,
                free=self.free,
                can_discount_gold=self.can_discount_gold,
            )
        )
