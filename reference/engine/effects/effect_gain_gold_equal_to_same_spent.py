from __future__ import annotations

from dataclasses import dataclass

from ..essence import Essence
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectGainGoldEqualToSameSpent:
    def execute(self, ctx: PowerContext) -> None:
        if not ctx.pay or ctx.pay.total() == 0:
            return

        non_zero_types = [ess for ess in Essence if ctx.pay[ess] > 0]
        assert len(non_zero_types) == 1, non_zero_types
        assert ctx.player.pool.can_afford(ctx.pay)

        same_count = ctx.pay.total()
        ctx.player.pool.pay(ctx.pay)
        ctx.player.pool.add(Essence.GOLD, same_count)
