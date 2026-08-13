from __future__ import annotations

from dataclasses import dataclass, field

from ..action_types import EntityId, PlayerId
from ..effects import EffectTempVP
from ..game_phase import GamePhase
from ..pending_choices import PendingVictoryReactChoice
from ..pool import Pool
from ..power_context import PowerContext
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionVictoryReact:

    pid: PlayerId
    eid: EntityId
    power_index: int
    target_eid: EntityId | None = None
    pay: Pool = field(default_factory=Pool)

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase in (GamePhase.ACTIONS, GamePhase.VICTORY_CHECK), state.phase

        power_index = self.power_index

        assert state.pending_stack
        top = state.pending_stack[-1]
        assert isinstance(top, PendingVictoryReactChoice), type(top)
        assert top.pid == self.pid, top.pid
        assert top.component_eid == self.eid, top.component_eid
        choice = top

        component_eid = choice.component_eid
        assert component_eid is not None

        entity = state.entities[component_eid]
        data = entity.data
        assert data, component_eid
        assert power_index < len(data.powers), (power_index, data.name)

        power = data.powers[power_index]

        assert not entity.is_turned

        player = state.players[self.pid]
        fixed_cost = power.get_essence_cost()
        any_cost = power.get_any_cost()
        required_total = fixed_cost.total() + any_cost

        if required_total > 0:
            assert self.pay.total() == required_total, (
                self.pay.total(),
                required_total,
            )
            for ess in range(len(fixed_cost)):
                if fixed_cost[ess] > 0:
                    assert self.pay[ess] >= fixed_cost[ess], (
                        ess,
                        self.pay[ess],
                        fixed_cost[ess],
                    )
            assert player.pool.can_afford(self.pay)
            player.pool.pay(self.pay)

        if power.requires_turn:
            entity.is_turned = True

        temp_vp = 0
        for effect in power.effects:
            if isinstance(effect, EffectTempVP):
                temp_vp += effect.amount
                power_ctx = PowerContext(
                    engine=ctx.engine,
                    state=state,
                    pid=self.pid,
                    entity=entity,
                    eid=self.eid,
                    target_eid=self.target_eid,
                )
                effect.execute(power_ctx)

        assert state.pending_stack.pop() is top
