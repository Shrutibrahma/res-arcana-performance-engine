from __future__ import annotations

from dataclasses import dataclass, field

from ..pool import Pool
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectRivalsGain:

    essences: Pool = field(default_factory=Pool)

    def execute(self, ctx: PowerContext) -> None:
        if self.essences.is_empty():
            return
        for pid in range(ctx.state.num_players):
            if pid != ctx.pid:
                ctx.state.players[pid].pool.add_pool(self.essences)
