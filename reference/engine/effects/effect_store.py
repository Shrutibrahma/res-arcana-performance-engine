from __future__ import annotations

from dataclasses import dataclass, field

from ..essence import Essence
from ..pool import Pool
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectStore:

    essences: Pool = field(default_factory=Pool)
    any_amount: int = 0
    exclude: tuple[Essence, ...] = ()
    what_spent: bool = False
    on_target: bool = False

    def execute(self, ctx: PowerContext) -> None:
        assert not self.on_target or ctx.target_eid is not None

        if self.on_target and ctx.target_eid is not None:
            target_entity = ctx.state.entities[ctx.target_eid]
        else:
            target_entity = ctx.entity

        if not self.essences.is_empty():
            if target_entity.essences_on_card is None:
                target_entity.essences_on_card = Pool()
            target_entity.essences_on_card.add_pool(self.essences)

        if self.any_amount > 0 and ctx.gain:
            assert ctx.gain.total() == self.any_amount, (
                ctx.gain.total(),
                self.any_amount,
            )
            for excl in self.exclude:
                assert ctx.gain[excl] == 0, excl
            if target_entity.essences_on_card is None:
                target_entity.essences_on_card = Pool()
            target_entity.essences_on_card.add_pool(ctx.gain)

        if self.what_spent:
            essence_cost = ctx.pay_essence_cost if ctx.pay_essence_cost else Pool()
            spent = ctx.pay if ctx.pay else essence_cost
            if not spent.is_empty():
                if ctx.pay_essence_cost is None and ctx.pay:
                    ctx.player.pool.pay(ctx.pay)
                if target_entity.essences_on_card is None:
                    target_entity.essences_on_card = Pool()
                target_entity.essences_on_card.add_pool(spent)
