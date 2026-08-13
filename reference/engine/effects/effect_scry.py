from __future__ import annotations

from dataclasses import dataclass

from ..pending_choices import PendingScryDeckChoice
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectScry:
    amount: int

    def execute(self, ctx: PowerContext) -> None:
        assert self.amount > 0
        assert ctx.eid is not None
        ctx.state.pending_stack.append(
            PendingScryDeckChoice(
                pid=ctx.pid,
                scry_count=self.amount,
                source_eid=ctx.eid,
            )
        )
