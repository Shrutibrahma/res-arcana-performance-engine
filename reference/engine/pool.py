from __future__ import annotations

from .essence import ESSENCE_COUNT, Essence


class Pool(list[int]):

    def __init__(
        self,
        values: list[int] | None = None,
        *,
        elan: int = 0,
        life: int = 0,
        calm: int = 0,
        death: int = 0,
        gold: int = 0,
    ):
        if values is not None:
            padded = list(values) + [0] * (ESSENCE_COUNT - len(values))
            super().__init__(padded[:ESSENCE_COUNT])
        else:
            super().__init__([elan, life, calm, death, gold])
        assert all(v >= 0 for v in self), f"Pool values must be non-negative: {list(self)}"

    @property
    def elan(self) -> int:
        return self[Essence.ELAN]

    @property
    def life(self) -> int:
        return self[Essence.LIFE]

    @property
    def calm(self) -> int:
        return self[Essence.CALM]

    @property
    def death(self) -> int:
        return self[Essence.DEATH]

    @property
    def gold(self) -> int:
        return self[Essence.GOLD]

    def add(self, essence: Essence, amount: int = 1) -> None:
        self[essence] += amount

    def subtract(self, essence: Essence, amount: int = 1) -> None:
        if self[essence] < amount:
            raise ValueError(f"Cannot subtract {amount} {essence.name} from pool with only {self[essence]}")
        self[essence] -= amount

    def total(self) -> int:
        return sum(self)

    def can_afford(self, cost: Pool) -> bool:
        for i in range(ESSENCE_COUNT):
            if self[i] < cost[i]:
                return False
        return True

    def pay(self, cost: Pool) -> None:
        if not self.can_afford(cost):
            raise ValueError(f"Cannot afford {cost} from pool {self}")
        for i in range(ESSENCE_COUNT):
            self[i] -= cost[i]

    def add_pool(self, other: Pool) -> None:
        for i in range(ESSENCE_COUNT):
            self[i] += other[i]

    def copy(self) -> Pool:
        return Pool(values=list(self))

    def is_empty(self) -> bool:
        return sum(self) == 0

    def __repr__(self) -> str:
        parts: list[str] = []
        names = ["elan", "life", "calm", "death", "gold"]
        for i, v in enumerate(self):
            if v != 0:
                parts.append(f"{names[i]}={v}")
        if not parts:
            return "Pool()"
        return f"Pool({', '.join(parts)})"
