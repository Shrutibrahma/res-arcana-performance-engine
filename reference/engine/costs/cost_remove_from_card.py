from __future__ import annotations

from dataclasses import dataclass, field

from ..pool import Pool
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class CostRemoveFromCard:

    essences: Pool = field(default_factory=Pool)

    def pay(self, ctx: PowerContext) -> None:
        if ctx.entity.essences_on_card is not None:
            ctx.entity.essences_on_card.pay(self.essences)
