from __future__ import annotations

from dataclasses import dataclass

from ..essence import Essence
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectGainGoldFromCost:
    divisor: int = 1

    def execute(self, ctx: PowerContext) -> None:
        amount = ctx.identical_amount
        gold_gained = amount // self.divisor

        expected = ctx.gain[Essence.GOLD]
        assert expected == gold_gained, (expected, gold_gained)

        if gold_gained > 0:
            ctx.player.pool.add(Essence.GOLD, gold_gained)
