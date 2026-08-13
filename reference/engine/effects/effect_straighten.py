from __future__ import annotations

from dataclasses import dataclass

from ..power_context import PowerContext
from ..straighten_target import StraightenTarget


@dataclass(frozen=True, slots=True)
class EffectStraighten:

    target: StraightenTarget = StraightenTarget.SELECTED

    def execute(self, ctx: PowerContext) -> None:
        if self.target == StraightenTarget.SELF:
            ctx.entity.is_turned = False

        elif self.target == StraightenTarget.SELECTED and ctx.target_eid is not None:
            target_eid = ctx.target_eid
            if 0 <= target_eid < len(ctx.state.entities):
                entity = ctx.state.entities[target_eid]
                if entity.owner_id == ctx.pid:
                    entity.is_turned = False
