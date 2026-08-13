from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..collect_decision import CollectDecision
from ..game_phase import GamePhase
from ..pending_choices import PendingCollectCost, PendingCollectStorage
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionCollectCost:

    pid: PlayerId
    eid: EntityId
    decision: CollectDecision

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.COLLECT, state.phase

        choice_idx = None
        choice_data = None
        for i, c in enumerate(state.pending_stack):
            if isinstance(c, PendingCollectCost):
                if c.pid == self.pid and c.eid == self.eid:
                    choice_idx = i
                    choice_data = c
                    break

        assert choice_idx is not None, (self.pid, self.eid)
        assert choice_data is not None

        player = state.players[self.pid]
        entity_id = choice_data.eid

        if self.decision == CollectDecision.DECLINE_COST:
            state.pending_stack.pop(choice_idx)
            return

        elif self.decision == CollectDecision.PAY_TURN:
            state.entities[entity_id].is_turned = True

        else:
            cost_essences = choice_data.cost_essences
            assert player.pool.can_afford(cost_essences)
            player.pool.pay(cost_essences)

        state.pending_stack.pop(choice_idx)

        entity = state.entities[entity_id]
        if entity.essences_on_card is not None and not entity.essences_on_card.is_empty():
            stored_options = ctx.engine.build_stored_options(entity.essences_on_card)
            state.pending_stack.append(
                PendingCollectStorage(
                    pid=self.pid,
                    eid=entity_id,
                    stored_essences=stored_options,
                )
            )
