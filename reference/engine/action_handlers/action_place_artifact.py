from __future__ import annotations

from dataclasses import dataclass, field

from ..action_types import EntityId, PlayerId
from ..card_location import CardLocation
from ..pending_choices import PendingPlacementChoice
from ..pool import Pool
from ..select_card_location import SelectCardLocation
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionPlaceArtifact:

    pid: PlayerId
    eid: EntityId
    pay: Pool = field(default_factory=Pool)

    def execute(self, ctx: ActionContext) -> None:
        player = ctx.player
        state = ctx.state

        pending_choice: PendingPlacementChoice | None = None
        if state.pending_stack:
            top = state.pending_stack[-1]
            if isinstance(top, PendingPlacementChoice) and top.pid == self.pid:
                pending_choice = top

        artifact_eid = self.eid
        entity = state.entities[artifact_eid]
        card_data = entity.data

        assert card_data

        if pending_choice is not None:
            filter_loc = pending_choice.filter.location

            if filter_loc == SelectCardLocation.HAND:
                assert entity.location == CardLocation.HAND, entity.location
                assert entity.owner_id == self.pid, entity.owner_id
            elif filter_loc in (
                SelectCardLocation.DISCARD,
                SelectCardLocation.ANY_DISCARD,
            ):
                assert entity.location == CardLocation.DISCARD, entity.location
                assert filter_loc != SelectCardLocation.DISCARD or entity.owner_id == self.pid
            else:
                raise AssertionError(f"Invalid filter location: {filter_loc}")

            if pending_choice.filter.card_type_mask > 0:
                assert pending_choice.filter.matches_card_type_mask(card_data.card_type_mask)

            if pending_choice.free:
                assert not card_data.cannot_be_free_placed, card_data.name
        else:
            hand = state.get_player_hand(self.pid)
            assert artifact_eid in hand, artifact_eid

        if pending_choice is not None and pending_choice.free:
            entity.location = CardLocation.IN_PLAY
            entity.is_turned = False
            if entity.owner_id != self.pid:
                entity.owner_id = self.pid

            state.pending_stack.pop()
            return

        from ..affordability import calculate_gold_discount_budget, get_valid_payments

        extra_discount = pending_choice.discount if pending_choice is not None else 0
        extra_can_discount_gold = pending_choice.can_discount_gold if pending_choice is not None else False

        gold_budget = calculate_gold_discount_budget(
            state,
            self.pid,
            card_data,
            extra_discount=extra_discount,
            extra_can_discount_gold=extra_can_discount_gold,
        )

        valid_payments = get_valid_payments(
            state,
            self.pid,
            card_data,
            extra_discount=extra_discount,
            gold_discount_budget=gold_budget,
        )

        assert any(vp == self.pay for vp in valid_payments), (self.pay, card_data.name)

        if self.pay.total() > 0:
            player.pool.pay(self.pay)

        entity.location = CardLocation.IN_PLAY
        entity.is_turned = False
        if entity.owner_id != self.pid:
            entity.owner_id = self.pid

        if pending_choice is not None:
            state.pending_stack.pop()
