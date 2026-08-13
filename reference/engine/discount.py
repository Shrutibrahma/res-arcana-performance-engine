from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Discount:

    artifact: int = 0
    dragon: int = 0
    creature: int = 0
    can_discount_gold: bool = False
