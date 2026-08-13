from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..deck_type import DeckType
from ..game_phase import GamePhase
from ..pending_choices import PendingScryChoice, PendingScryRevealChoice
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionResolveScryReveal:

    pid: PlayerId
    revealed_eids: tuple[EntityId, ...]

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.ACTIONS, state.phase

        assert state.pending_stack
        top = state.pending_stack[-1]
        assert isinstance(top, PendingScryRevealChoice), type(top)
        assert top.pid == self.pid, top.pid
        choice = top

        assert len(self.revealed_eids) == choice.reveal_count, (
            len(self.revealed_eids),
            choice.reveal_count,
        )

        if choice.deck_type == DeckType.MONUMENT:
            unknown_pool = state.get_unknown_monument_deck()
        else:
            unknown_pool = state.get_unknown_deck_cards(choice.pid)

        unknown_set = set(unknown_pool)
        for eid in self.revealed_eids:
            assert eid in unknown_set, eid

        all_revealed = list(choice.known_eids) + list(self.revealed_eids)

        assert state.pending_stack.pop() is top

        state.pending_stack.append(
            PendingScryChoice(
                pid=self.pid,
                deck_type=choice.deck_type,
                card_eids=tuple(all_revealed),
            )
        )
