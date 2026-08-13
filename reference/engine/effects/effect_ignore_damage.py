from __future__ import annotations

from dataclasses import dataclass

from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectIgnoreDamage:
    def execute(self, ctx: PowerContext) -> None:
        pass
