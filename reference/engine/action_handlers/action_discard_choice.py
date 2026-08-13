from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..card_location import CardLocation
from ..game_phase import GamePhase
from ..pending_choices import PendingDiscardChoice
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionDiscardChoice:
    pid: PlayerId
    eids: tuple[EntityId, ...]

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.ACTIONS, state.phase

        assert state.pending_stack
        top = state.pending_stack[-1]
        assert isinstance(top, PendingDiscardChoice), type(top)
        assert top.pid == self.pid, top.pid

        assert len(self.eids) == top.count, (len(self.eids), top.count)

        hand = state.get_player_hand(self.pid)
        for eid in self.eids:
            assert eid in hand, eid

        for eid in self.eids:
            entity = state.entities[eid]
            entity.location = CardLocation.DISCARD

        assert state.pending_stack.pop() is top
