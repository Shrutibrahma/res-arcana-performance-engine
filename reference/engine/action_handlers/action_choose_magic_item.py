from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..card_location import CardLocation
from ..component_type import ComponentType
from ..game_phase import GamePhase
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionChooseMagicItem:
    pid: PlayerId
    eid: EntityId

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.SETUP_CHOOSE_ITEMS, state.phase

        assert state.get_magic_item_selection_player() == self.pid

        assert 0 <= self.eid < len(state.entities), self.eid
        item = state.entities[self.eid]
        assert item.kind == ComponentType.MAGIC_ITEM, item.kind
        assert item.location == CardLocation.AVAILABLE, item.location

        item.location = CardLocation.IN_PLAY
        item.owner_id = self.pid

        next_pid = state.get_magic_item_selection_player()
        if next_pid is None:
            state.begin_round()
        else:
            state.current_player_index = PlayerId(next_pid)
