from __future__ import annotations

from dataclasses import dataclass

from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectTempVP:
    amount: int

    def execute(self, ctx: PowerContext) -> None:
        ctx.state.temp_vp[ctx.pid] += self.amount
