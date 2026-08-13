from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..card_location import CardLocation
from ..component_type import ComponentType
from ..game_phase import GamePhase
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionChooseMage:
    pid: PlayerId
    eid: EntityId

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.SETUP_CHOOSE_MAGES, state.phase

        assert 0 <= self.eid < len(state.entities), self.eid
        mage = state.entities[self.eid]
        assert mage.kind == ComponentType.MAGE, mage.kind
        assert mage.owner_id == self.pid, (mage.owner_id, self.pid)
        assert mage.location == CardLocation.BEING_CHOSEN, mage.location

        rejected = 0
        for _, m in state.iter_mages():
            if m.owner_id == self.pid and m.location == CardLocation.BEING_CHOSEN and m is not mage:
                m.location = CardLocation.OUT_OF_GAME
                rejected += 1

        if rejected == 0:

            mage.location = CardLocation.IN_PLAY

        next_pid: PlayerId | None = None
        for pid in range(state.num_players):
            all_being_chosen = True
            for _, m in state.iter_mages():
                if m.owner_id == pid and m.location != CardLocation.BEING_CHOSEN:
                    all_being_chosen = False
                    break
            if all_being_chosen:
                next_pid = PlayerId(pid)
                break

        if next_pid is not None:
            state.current_player_index = next_pid
        else:

            for _, m in state.iter_mages():
                if m.location == CardLocation.BEING_CHOSEN:
                    m.location = CardLocation.IN_PLAY
            item_pid = state.get_magic_item_selection_player()
            if item_pid is not None:
                state.current_player_index = PlayerId(item_pid)
            state.phase = GamePhase.SETUP_CHOOSE_ITEMS
