from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..pending_choices import PendingLifeLossScan
from ..power_context import PowerContext

if TYPE_CHECKING:
    from ..costs import Cost


@dataclass(frozen=True, slots=True)
class EffectDamage:
    amount: int
    defense_options: list[Cost] = field(default_factory=lambda: [])
    all_players: bool = False
    include_self: bool = False

    def execute(self, ctx: PowerContext) -> None:
        assert self.amount > 0
        source = ctx.eid if ctx.eid is not None else ctx.entity_name
        ctx.state.pending_stack.append(
            PendingLifeLossScan(
                source=source,
                amount=self.amount,
                next_offset=0 if self.include_self else 1,
                pid=ctx.pid,
                include_self=self.include_self,
                all_players=self.all_players,
            )
        )
