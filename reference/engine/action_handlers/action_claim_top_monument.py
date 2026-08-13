from __future__ import annotations

from dataclasses import dataclass

from ..action_types import PlayerId
from ..essence import Essence
from ..pending_choices import PendingMonumentDrawChoice
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionClaimTopMonument:

    pid: PlayerId

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        player = state.players[self.pid]

        assert player.pool.gold >= 4
        assert state.get_top_monument_from_deck() is not None

        player.pool.subtract(Essence.GOLD, 4)

        state.pending_stack.append(PendingMonumentDrawChoice(pid=self.pid))
