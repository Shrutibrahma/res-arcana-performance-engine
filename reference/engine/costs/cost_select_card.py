from __future__ import annotations

from dataclasses import dataclass, field

from ..power_context import PowerContext
from ..select_card_filter import SelectCardFilter


@dataclass(frozen=True, slots=True)
class CostSelectCard:

    filter: SelectCardFilter = field(default_factory=SelectCardFilter)

    def has_filter(self) -> bool:
        return self.filter.has_filter()

    def pay(self, ctx: PowerContext) -> None:
        if ctx.target_eid is None:
            return
        assert 0 <= ctx.target_eid < len(ctx.state.entities), f"Invalid target card {ctx.target_eid}"
