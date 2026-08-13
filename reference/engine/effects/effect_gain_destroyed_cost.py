from __future__ import annotations

from dataclasses import dataclass

from ..essence import Essence
from ..pending_choices import PendingGain
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectGainDestroyedCost:

    as_any: bool = False
    as_gold: bool = False
    bonus: int = 0

    def execute(self, ctx: PowerContext) -> None:
        if ctx.target_eid is None:
            return

        art = ctx.state.entities[ctx.target_eid]
        base_value = art.data.total_placement_cost()

        if self.as_gold:
            gold_value = base_value
            ctx.player.pool.add(Essence.GOLD, gold_value)

        elif self.as_any:
            any_value = base_value + self.bonus
            if any_value > 0:
                gain_choice = ctx.gain
                if gain_choice and gain_choice.total() == any_value:
                    assert gain_choice.gold == 0, gain_choice
                    ctx.player.pool.add_pool(gain_choice)
                else:
                    ctx.state.pending_stack.append(
                        PendingGain(
                            pid=ctx.pid,
                            any_amount=any_value,
                            restriction_mask=(1 << Essence.GOLD),
                            source_eid=ctx.eid,
                        )
                    )
