from __future__ import annotations

from dataclasses import dataclass

from ..action_types import PlayerId
from ..game_phase import GamePhase
from ..pending_choices import PendingScryChoice
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionScryChoice:
    pid: PlayerId
    scry_order: list[int]

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.ACTIONS, state.phase

        assert state.pending_stack
        top = state.pending_stack[-1]
        assert isinstance(top, PendingScryChoice), type(top)
        assert top.pid == self.pid, top.pid
        choice = top
        card_indices = choice.card_eids

        scry_order = self.scry_order
        if not scry_order:
            scry_order = list(range(len(card_indices)))

        assert sorted(scry_order) == list(range(len(card_indices))), scry_order

        reordered_eids = [card_indices[i] for i in scry_order]

        for new_pos, eid in enumerate(reordered_eids):
            state.entities[eid].order_index = new_pos

        assert state.pending_stack.pop() is top
