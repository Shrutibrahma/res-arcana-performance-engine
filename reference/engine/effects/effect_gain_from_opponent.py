from __future__ import annotations

from dataclasses import dataclass

from ..essence import Essence
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectGainFromOpponent:
    their_essence: int = -1
    your_essence: int = -1

    def execute(self, ctx: PowerContext) -> None:
        if self.their_essence < 0 or self.your_essence < 0:
            return

        target_pid = ctx.target_pid
        if target_pid is None or target_pid == ctx.pid:
            return

        their_ess = Essence(self.their_essence)
        your_ess = Essence(self.your_essence)

        count = ctx.state.players[target_pid].pool[their_ess]
        if count > 0:
            ctx.player.pool.add(your_ess, count)
