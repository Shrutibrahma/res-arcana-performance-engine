from __future__ import annotations

from dataclasses import dataclass, field

from ..action_types import EntityId, PlayerId
from ..costs import CostPayEssence
from ..effects import EffectStore
from ..pool import Pool
from ..power_context import PowerContext
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionUsePower:
    pid: PlayerId
    eid: EntityId
    power_index: int
    target_eid: EntityId | None = None
    target_pid: PlayerId | None = None
    pay: Pool = field(default_factory=Pool)
    gain: Pool = field(default_factory=Pool)

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        component_type, entity_idx, _card_data, power = state.find_component_power(self.pid, self.eid, self.power_index)

        assert component_type is not None, self.eid
        assert entity_idx is not None, self.eid
        assert power is not None, self.power_index

        entity = state.entities[entity_idx]

        assert not power.is_react
        assert power.usable_when_turned or not entity.is_turned

        pay_cost = power.get_cost(CostPayEssence)
        power_ctx = PowerContext(
            engine=ctx.engine,
            state=state,
            pid=self.pid,
            entity=entity,
            eid=self.eid,
            pay_essence_cost=pay_cost.essences if pay_cost else None,
            target_eid=self.target_eid,
            target_pid=self.target_pid,
            pay=self.pay,
            gain=self.gain,
        )

        select_card_cost = power.get_select_card_cost()
        if select_card_cost is not None and select_card_cost.has_filter():
            select_targets = ctx.engine.get_targets_from_filter(
                state,
                self.pid,
                select_card_cost.filter,
                power=power,
                source_entity_id=self.eid,
            )
            assert self.target_eid is None or self.target_eid in select_targets, self.target_eid

        if select_card_cost and select_card_cost.filter.exclude_self:
            for effect in power.effects:
                if isinstance(effect, EffectStore):
                    assert not (effect.on_target and self.target_eid == self.eid)

        if power.requires_turn:
            power_ctx.entity.is_turned = True
        for cost in power.costs:
            cost.pay(power_ctx)

        for effect in power.effects:
            effect.execute(power_ctx)
