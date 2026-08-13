from __future__ import annotations

from dataclasses import dataclass

from ..essence import Essence
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectGainSameTypeAsSpent:
    def execute(self, ctx: PowerContext) -> None:
        if not ctx.pay or ctx.pay.total() == 0:
            return

        non_zero_types = [ess for ess in Essence if ctx.pay[ess] > 0]
        assert len(non_zero_types) == 1, non_zero_types

        assert ctx.player.pool.can_afford(ctx.pay)

        spent_count = ctx.pay.total()

        gain_choice = ctx.gain
        assert gain_choice
        assert gain_choice.total() == spent_count, (gain_choice.total(), spent_count)
        gain_types = [ess for ess in Essence if gain_choice[ess] > 0]
        assert len(gain_types) == 1, gain_types
        assert gain_types[0] != Essence.GOLD, gain_types[0]

        ctx.player.pool.pay(ctx.pay)
        ctx.player.pool.add_pool(gain_choice)
