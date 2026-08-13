from __future__ import annotations

from dataclasses import dataclass, field

from .conditional_type import ConditionalType
from .pool import Pool


@dataclass(frozen=True, slots=True)
class CollectAbility:

    essences: Pool = field(default_factory=Pool)
    choice_mask: int = 0
    any_amount: int = 0
    alt_any_amount: int = 0
    restriction_mask: int = 0
    conditional_type: ConditionalType | None = None
    per_stored_essence_multiplier: int = 0

    cost_essences: Pool = field(default_factory=Pool)
    cost_turn: bool = False

    @property
    def has_conditional(self) -> bool:
        return self.conditional_type is not None

    @property
    def has_collect_cost(self) -> bool:
        return not self.cost_essences.is_empty() or self.cost_turn

    def choice_mask_to_restriction(self) -> int:
        return (~self.choice_mask) & 0b11111
