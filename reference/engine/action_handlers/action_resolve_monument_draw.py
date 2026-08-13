from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..card_location import CardLocation
from ..entity_data import UNKNOWN_ORDER
from ..game_phase import GamePhase
from ..pending_choices import PendingMonumentDrawChoice
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionResolveMonumentDraw:

    pid: PlayerId
    eid: EntityId

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.ACTIONS, state.phase

        assert state.pending_stack
        top = state.pending_stack[-1]
        assert isinstance(top, PendingMonumentDrawChoice), type(top)
        assert top.pid == self.pid, top.pid

        target = state.entities[self.eid]

        assert target.location == CardLocation.MONUMENT_DECK, (
            self.eid,
            target.location,
        )

        known = state.get_known_monument_deck()
        drawn_order = target.order_index
        if known:
            assert self.eid == known[0], (self.eid, known[0])
            for other_eid in known[1:]:
                other = state.entities[other_eid]
                if other.order_index > drawn_order:
                    other.order_index -= 1
        else:
            assert drawn_order == UNKNOWN_ORDER, (self.eid, drawn_order)

        state.claim_monument(self.pid, self.eid)
        target.order_index = UNKNOWN_ORDER

        assert state.pending_stack.pop() is top

        ctx.engine.trigger_monument_bought(state, self.pid, self.eid)
