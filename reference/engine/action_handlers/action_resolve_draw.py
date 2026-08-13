from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..card_location import CardLocation
from ..entity_data import UNKNOWN_ORDER
from ..game_phase import GamePhase
from ..pending_choices import PendingDrawRevealChoice
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionResolveDrawReveal:

    pid: PlayerId
    revealed_eids: tuple[EntityId, ...]
    known_eids: tuple[EntityId, ...] = ()

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        allowed_phases = {
            GamePhase.ACTIONS,
            GamePhase.SETUP_CHOOSE_MAGES,
            GamePhase.SETUP_CHOOSE_ITEMS,
        }
        assert state.phase in allowed_phases, state.phase

        pending = state.pending_stack.pop()
        assert isinstance(pending, PendingDrawRevealChoice)
        assert pending.pid == self.pid

        assert len(self.revealed_eids) == pending.reveal_count, (
            len(self.revealed_eids),
            pending.reveal_count,
        )

        known_orders = sorted(
            (state.entities[eid].order_index for eid in pending.known_eids),
            reverse=True,
        )

        for eid in pending.known_eids:
            entity = state.entities[eid]
            assert entity.location == CardLocation.DECK, (eid, entity.location)
            assert entity.owner_id == self.pid, (eid, entity.owner_id)
            assert entity.order_index != UNKNOWN_ORDER, eid
            entity.location = CardLocation.HAND
            entity.order_index = UNKNOWN_ORDER

        for _, art in state.iter_artifacts():
            if art.location == CardLocation.DECK and art.owner_id == self.pid and art.order_index != UNKNOWN_ORDER:
                adjustment = sum(1 for o in known_orders if art.order_index > o)
                if adjustment > 0:
                    art.order_index -= adjustment

        for eid in self.revealed_eids:
            entity = state.entities[eid]
            assert entity.location == CardLocation.DECK, (eid, entity.location)
            assert entity.owner_id == self.pid, (eid, entity.owner_id)
            assert entity.order_index == UNKNOWN_ORDER, (eid, entity.order_index)
            entity.location = CardLocation.HAND
