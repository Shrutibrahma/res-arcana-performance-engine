from __future__ import annotations

from dataclasses import dataclass

from ..action_types import PlayerId
from ..card_location import CardLocation
from ..deck_type import DeckType
from ..entity_data import UNKNOWN_ORDER
from ..game_phase import GamePhase
from ..pending_choices import (
    PendingScryChoice,
    PendingScryDeckChoice,
    PendingScryRevealChoice,
)
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionScryDeckChoice:
    pid: PlayerId
    scry_target: DeckType

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.ACTIONS, state.phase

        assert state.pending_stack
        top = state.pending_stack[-1]
        assert isinstance(top, PendingScryDeckChoice), type(top)
        assert top.pid == self.pid, top.pid
        choice = top
        scry_count = choice.scry_count

        scry_target = self.scry_target
        if scry_target == DeckType.MONUMENT:
            known = state.get_known_monument_deck()[:scry_count]
            unknown = state.get_unknown_monument_deck()
        else:
            deck_size = state.get_player_deck_count(self.pid)
            if deck_size < scry_count:
                discard_eids = [
                    eid
                    for eid, entity in state.iter_artifacts()
                    if entity.location == CardLocation.DISCARD and entity.owner_id == self.pid
                ]
                if discard_eids:
                    for eid in discard_eids:
                        state.entities[eid].location = CardLocation.DECK
                        state.entities[eid].order_index = UNKNOWN_ORDER

            known = state.get_known_deck_cards(self.pid)[:scry_count]
            unknown = state.get_unknown_deck_cards(self.pid)

        knowns_to_scry = len(known)
        unknowns_needed = scry_count - knowns_to_scry

        assert state.pending_stack.pop() is top

        if unknowns_needed > 0 and unknown:
            actual_unknowns_to_reveal = min(unknowns_needed, len(unknown))
            state.pending_stack.append(
                PendingScryRevealChoice(
                    pid=self.pid,
                    known_eids=tuple(known),
                    reveal_count=actual_unknowns_to_reveal,
                    deck_type=scry_target,
                )
            )
        else:
            state.pending_stack.append(
                PendingScryChoice(
                    pid=self.pid,
                    deck_type=scry_target,
                    card_eids=tuple(known),
                )
            )
