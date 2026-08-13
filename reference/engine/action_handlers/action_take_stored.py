from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from ..action_types import EntityId, PlayerId
from ..collect_decision import CollectDecision
from ..collect_option_type import CollectOptionType
from ..game_phase import GamePhase
from ..pending_choices import PendingCollectStorage, PendingGain
from ..pool import Pool
from .context import ActionContext

StorageChoiceType = PendingCollectStorage


@dataclass(frozen=True, slots=True)
class ActionTakeStored:
    pid: PlayerId
    target_eid: EntityId
    decision: CollectDecision

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.COLLECT, state.phase

        entity_id = self.target_eid
        take_stored = self.decision == CollectDecision.TAKE_STORED

        choice_idx: int | None = None
        choice_data: StorageChoiceType | None = None
        for i, c in enumerate(state.pending_stack):
            if isinstance(c, PendingCollectStorage):
                if c.pid == self.pid and c.eid == entity_id:
                    choice_idx = i
                    choice_data = c
                    break

        assert choice_idx is not None, entity_id
        assert choice_data is not None, entity_id

        assert 0 <= entity_id < len(state.entities), entity_id
        entity = state.entities[entity_id]
        assert entity.owner_id == self.pid, (entity_id, entity.owner_id, self.pid)

        stored_essences = choice_data.stored_essences
        has_stored = len(stored_essences) > 0

        if take_stored:
            if entity.essences_on_card is not None and not entity.essences_on_card.is_empty():
                state.players[self.pid].pool.add_pool(entity.essences_on_card)
                entity.essences_on_card = None
        else:
            if choice_data.bonus_multiplier > 0 and has_stored:
                for stored in choice_data.stored_essences:
                    if entity.essences_on_card is None:
                        entity.essences_on_card = Pool()
                    entity.essences_on_card.add(stored.essence, choice_data.bonus_multiplier)
            elif choice_data.natural_collect is not None and has_stored:
                for option in choice_data.natural_collect:
                    match option.option_type:
                        case CollectOptionType.FIXED_ESSENCE:
                            if option.essence is not None and option.amount > 0:
                                state.players[self.pid].pool.add(option.essence, option.amount)
                        case CollectOptionType.ANY:
                            state.pending_stack.append(
                                PendingGain(
                                    pid=self.pid,
                                    any_amount=option.amount,
                                    restriction_mask=option.restriction_mask,
                                    alt_any_amount=option.alt_any_amount,
                                    alt_restriction_mask=option.alt_restriction_mask,
                                    source_eid=entity_id,
                                )
                            )
                        case _ as unreachable:
                            assert_never(unreachable)

        state.pending_stack.pop(choice_idx)
