from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..essence import ESSENCE_COUNT, Essence
from ..pending_choices import PendingGain
from ..pool import Pool
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionGain:

    pid: PlayerId
    source_eid: EntityId
    gain: Pool
    use_alt: bool = False

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        choice_idx = None
        choice_data = None
        for i, c in enumerate(state.pending_stack):
            if isinstance(c, PendingGain):
                if c.pid == self.pid and c.source_eid == self.source_eid:
                    choice_idx = i
                    choice_data = c
                    break

        assert choice_idx is not None, (self.pid, self.source_eid)
        assert choice_data is not None

        if self.use_alt and choice_data.alt_any_amount > 0:
            expected_amount = choice_data.alt_any_amount
            restriction_mask = choice_data.alt_restriction_mask
        else:
            expected_amount = choice_data.any_amount
            restriction_mask = choice_data.restriction_mask

        assert self.gain.total() == expected_amount, (
            self.gain.total(),
            expected_amount,
        )

        for i in range(ESSENCE_COUNT):
            if (restriction_mask & (1 << i)) and self.gain[i] > 0:
                assert False, (Essence(i), self.gain)

        state.players[self.pid].pool.add_pool(self.gain)

        state.pending_stack.pop(choice_idx)
