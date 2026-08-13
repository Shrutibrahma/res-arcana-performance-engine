from __future__ import annotations

from dataclasses import dataclass

from ..action_types import UNOWNED, EntityId, PlayerId
from ..card_location import CardLocation
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionPass:

    pid: PlayerId
    new_magic_item_eid: EntityId

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        player = state.players[self.pid]

        assert not player.has_passed

        old_item_eid: EntityId | None = None
        for eid, item in state.iter_magic_items():
            if item.location == CardLocation.IN_PLAY and item.owner_id == self.pid:
                old_item_eid = eid
                break
        has_magic_item = old_item_eid is not None

        if has_magic_item:
            available_items = state.get_available_magic_items()
            assert self.new_magic_item_eid in available_items, self.new_magic_item_eid

            assert old_item_eid is not None
            old_item = state.entities[old_item_eid]
            old_item.location = CardLocation.AVAILABLE
            old_item.owner_id = UNOWNED
            old_item.is_turned = False

            new_item = state.entities[self.new_magic_item_eid]
            new_item.location = CardLocation.IN_PLAY
            new_item.owner_id = self.pid

        first_to_pass = True
        for p in state.players:
            if p.pid != self.pid and p.has_passed:
                first_to_pass = False
                break

        if first_to_pass:
            for p in state.players:
                p.has_first_player_token = p.pid == self.pid
            state.first_player_index = self.pid

        state.draw_card(self.pid)

        player.has_passed = True
