from __future__ import annotations

from dataclasses import dataclass

from ..pending_choices import PendingDiscardChoice
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectDraw:
    amount: int
    discard_after: int = 0
    require_deck_has_cards: bool = False

    def execute(self, ctx: PowerContext) -> None:
        assert self.amount > 0
        if self.require_deck_has_cards:
            assert ctx.state.get_player_deck_count(ctx.pid) > 0

        actual_draws = ctx.state.draw_card(ctx.pid, count=self.amount)

        if self.discard_after > 0:
            shortfall = self.amount - actual_draws
            actual_discards = max(0, self.discard_after - shortfall)
            if actual_discards > 0:

                assert ctx.eid is not None
                ctx.state.pending_stack.insert(
                    0,
                    PendingDiscardChoice(
                        pid=ctx.pid,
                        count=actual_discards,
                        source_eid=ctx.eid,
                    ),
                )
