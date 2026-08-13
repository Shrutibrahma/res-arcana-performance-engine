from __future__ import annotations

from dataclasses import dataclass

from ..power_context import PowerContext
from ..turnable_type import TurnableType


@dataclass(frozen=True, slots=True)
class CostTurnComponent:

    turnable_type: TurnableType

    def pay(self, ctx: PowerContext) -> None:
        assert ctx.target_eid is not None
        straightened = ctx.state.get_straightened_of_type(ctx.pid, self.turnable_type)
        assert ctx.target_eid in straightened, ctx.target_eid
        ctx.state.entities[ctx.target_eid].is_turned = True
