from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..card_location import CardLocation
from ..component_type import ComponentType
from ..essence import Essence
from ..pending_choices import PendingMonumentRevealChoice
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionClaimMonument:
    pid: PlayerId
    eid: EntityId

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        player = state.players[self.pid]

        assert player.pool.gold >= 4

        monument_eid = self.eid

        assert 0 <= monument_eid < len(state.entities), monument_eid

        mon = state.entities[monument_eid]
        assert mon.kind == ComponentType.MONUMENT, mon.kind

        assert mon.location == CardLocation.AVAILABLE, mon.location

        player.pool.subtract(Essence.GOLD, 4)

        state.claim_monument(self.pid, monument_eid)

        deck = state.get_monument_deck()
        if deck:
            state.pending_stack.append(PendingMonumentRevealChoice(pid=self.pid))

        ctx.engine.trigger_monument_bought(state, self.pid, monument_eid)
