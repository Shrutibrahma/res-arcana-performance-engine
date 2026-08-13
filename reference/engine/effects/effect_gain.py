from __future__ import annotations

from dataclasses import dataclass, field

from ..pool import Pool
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectGain:

    essences: Pool = field(default_factory=Pool)

    def execute(self, ctx: PowerContext) -> None:
        if self.essences.is_empty():
            return
        ctx.player.pool.add_pool(self.essences)
