from __future__ import annotations

from dataclasses import dataclass

from ..essence import Essence
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectGainAny:
    amount: int
    exclude: tuple[Essence, ...] = ()

    def execute(self, ctx: PowerContext) -> None:
        # All cards using this effect have amount >= 1
        assert self.amount > 0
        gain_choice = ctx.gain
        assert gain_choice
        assert gain_choice.total() == self.amount, (gain_choice.total(), self.amount)
        assert gain_choice.gold == 0
        for excl in self.exclude:
            assert gain_choice[excl] == 0, excl
        ctx.player.pool.add_pool(gain_choice)
