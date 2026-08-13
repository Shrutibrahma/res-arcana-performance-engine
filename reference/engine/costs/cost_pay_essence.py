from __future__ import annotations

from dataclasses import dataclass, field

from ..essence import Essence
from ..pool import Pool
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class CostPayEssence:

    essences: Pool = field(default_factory=Pool)
    any_amount: int = 0
    exclude: tuple[Essence, ...] = ()

    def pay(self, ctx: PowerContext) -> None:
        choice = ctx.pay
        if choice.is_empty():
            assert self.any_amount == 0, self.any_amount
            if self.essences.total() > 0:
                ctx.player.pool.pay(self.essences)
            return

        if self.any_amount == 0:
            assert choice == self.essences, (choice, self.essences)
            ctx.player.pool.pay(choice)
            return

        for essence in Essence:
            assert choice[essence] >= self.essences[essence], (
                essence,
                choice[essence],
                self.essences[essence],
            )

        required_total = self.essences.total() + self.any_amount
        choice_total = choice.total()
        assert choice_total == required_total, (choice_total, required_total)

        for excl in self.exclude:
            assert choice[excl] <= self.essences[excl], (
                excl,
                choice[excl],
                self.essences[excl],
            )

        ctx.player.pool.pay(choice)
