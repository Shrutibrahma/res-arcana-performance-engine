from __future__ import annotations

from dataclasses import dataclass

from ..essence import Essence
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class CostPayIdentical:

    base_cost: int = 0
    min_amount: int = 0
    essence_type: Essence | None = None

    def pay(self, ctx: PowerContext) -> None:
        choice = ctx.pay
        assert choice is not None

        total = choice.total()
        x = total - self.base_cost

        assert x >= self.min_amount, (x, self.min_amount)

        if self.essence_type is not None:
            assert choice[self.essence_type] >= x, (
                self.essence_type,
                choice[self.essence_type],
                x,
            )
        else:
            identical_type = None
            for ess in Essence:
                if choice[ess] >= x:
                    identical_type = ess
                    break

            assert identical_type is not None, (x, choice)

        assert ctx.player.pool.can_afford(choice)
        ctx.player.pool.pay(choice)
        ctx.identical_amount = x
