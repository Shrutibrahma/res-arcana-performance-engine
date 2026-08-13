from __future__ import annotations

from dataclasses import dataclass, field

from ..action_types import PlayerId
from ..essence import Essence
from ..game_phase import GamePhase
from ..pending_choices import PendingLifeLossChoice
from ..pool import Pool
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionLifeLossChoice:

    pid: PlayerId
    pay: Pool = field(default_factory=Pool)

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.ACTIONS, state.phase

        assert state.pending_stack
        top = state.pending_stack[-1]
        assert isinstance(top, PendingLifeLossChoice), type(top)
        assert top.pid == self.pid, top.pid
        choice = top

        player = state.players[self.pid]
        damage_amount = choice.amount

        life_available = player.pool.life
        non_life_available = player.pool.total() - life_available
        total_essences = player.pool.total()

        max_life_payment = min(life_available, damage_amount)
        remaining_after_life = damage_amount - max_life_payment
        max_non_life_pairs = non_life_available // 2
        max_non_life_damage = min(max_non_life_pairs, remaining_after_life)
        max_damage_coverable = max_life_payment + max_non_life_damage

        can_fully_cover = max_damage_coverable >= damage_amount

        if self.pay.total() == 0:
            assert total_essences == 0, total_essences
            assert state.pending_stack.pop() is top
            return

        for essence in Essence:
            assert self.pay[essence] <= player.pool[essence], (
                essence,
                self.pay[essence],
                player.pool[essence],
            )

        life_paid = self.pay.life
        non_life_paid = self.pay.total() - life_paid
        essences_paid = self.pay.total()

        if can_fully_cover:
            assert non_life_paid % 2 == 0, non_life_paid
            damage_covered = life_paid + (non_life_paid // 2)
            assert damage_covered == damage_amount, (damage_covered, damage_amount)
        else:
            assert essences_paid == total_essences, (essences_paid, total_essences)

        for essence in Essence:
            for _ in range(self.pay[essence]):
                player.pool.subtract(essence)

        assert state.pending_stack.pop() is top
