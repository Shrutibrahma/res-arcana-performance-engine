from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from .costs import (
    Cost,
    CostDestroyCardType,
    CostDestroyComponent,
    CostDiscardCard,
    CostPayEssence,
    CostSelectCard,
    CostSelectPlayer,
    CostTurnComponent,
    DestroyMode,
)
from .effects import (
    Effect,
    EffectCheckVictory,
    EffectDamage,
    EffectDraw,
    EffectGain,
    EffectGainAny,
    EffectGainDestroyedCost,
    EffectGainFromOpponent,
    EffectGainGoldEqualToSameSpent,
    EffectGainGoldFromCost,
    EffectGainSameTypeAsSpent,
    EffectIgnoreDamage,
    EffectPlace,
    EffectRivalsGain,
    EffectScry,
    EffectStore,
    EffectStraighten,
    EffectTempVP,
)
from .essence import Essence
from .pool import Pool
from .power_type import PowerType
from .react_trigger import ReactTrigger
from .straighten_target import StraightenTarget
from .turnable_type import TurnableType


@dataclass(frozen=True, slots=True)
class Power:

    requires_turn: bool = False
    costs: tuple[Cost, ...] = ()
    effects: tuple[Effect, ...] = ()
    effect_description: str = ""
    power_type: PowerType = PowerType.ACTION
    react_trigger: ReactTrigger = ReactTrigger.NONE
    usable_when_turned: bool = False

    @property
    def is_react(self) -> bool:
        return self.power_type != PowerType.ACTION

    def has_cost(self, cost_type: type) -> bool:
        return any(isinstance(c, cost_type) for c in self.costs)

    def get_cost[T](self, cost_type: type[T]) -> T | None:
        for c in self.costs:
            if isinstance(c, cost_type):
                return cast(T, c)
        return None

    def has_turn_component_cost(self, turnable_type: TurnableType) -> bool:
        for c in self.costs:
            if isinstance(c, CostTurnComponent) and c.turnable_type == turnable_type:
                return True
        return False

    def has_destroy_component_cost(self, destroy_mode: DestroyMode) -> bool:
        for c in self.costs:
            if isinstance(c, CostDestroyComponent) and c.destroy_mode == destroy_mode:
                return True
        return False

    def get_essence_cost(self) -> Pool:
        cost = self.get_cost(CostPayEssence)
        if cost is not None:
            return cost.essences
        return Pool()

    def get_any_cost(self) -> int:
        total = 0
        for c in self.costs:
            if isinstance(c, CostPayEssence):
                total += c.any_amount
        return total

    def get_any_cost_exclude(self) -> list[Essence]:
        excludes: set[Essence] = set()
        for c in self.costs:
            if isinstance(c, CostPayEssence) and c.any_amount > 0:
                excludes.update(c.exclude)
        return list(excludes)

    def get_select_card_cost(self) -> CostSelectCard | None:
        return self.get_cost(CostSelectCard)

    def requires_target(self) -> bool:
        select_card_cost = self.get_select_card_cost()
        if select_card_cost is not None and select_card_cost.has_filter():
            return True
        if self.has_cost(CostDiscardCard):
            return True
        if self.has_destroy_component_cost(DestroyMode.ANY):
            return True
        if self.has_destroy_component_cost(DestroyMode.ANOTHER):
            return True
        if self.has_cost(CostDestroyCardType):
            return True
        if (
            self.has_turn_component_cost(TurnableType.MAGE)
            or self.has_turn_component_cost(TurnableType.DRAGON)
            or self.has_turn_component_cost(TurnableType.CREATURE)
        ):
            return True

        for effect in self.effects:
            match effect:
                case EffectStraighten(target=StraightenTarget.SELECTED):
                    return True
                case EffectGainFromOpponent() | EffectPlace():
                    return True
                case EffectStore(on_target=True):
                    return True
                case (
                    EffectGain()
                    | EffectGainAny()
                    | EffectStore()
                    | EffectRivalsGain()
                    | EffectDamage()
                    | EffectDraw()
                    | EffectIgnoreDamage()
                    | EffectCheckVictory()
                    | EffectStraighten()
                    | EffectScry()
                    | EffectGainDestroyedCost()
                    | EffectGainGoldEqualToSameSpent()
                    | EffectGainSameTypeAsSpent()
                    | EffectTempVP()
                    | EffectGainGoldFromCost()
                ):
                    pass

        return False

    def validate(self, power_idx: int) -> None:
        needs_target_player = any(_effect_requires_target_player(e) for e in self.effects)
        needs_target_id = any(_effect_requires_target_id(e) for e in self.effects)

        has_target_player_cost = any(_cost_provides_target_player(c) for c in self.costs)
        has_target_id_cost = any(_cost_provides_target_id(c) for c in self.costs)

        assert not (needs_target_player and not has_target_player_cost), power_idx
        assert not (needs_target_id and not has_target_id_cost), power_idx


def _effect_requires_target_player(effect: Effect) -> bool:
    match effect:
        case EffectGainFromOpponent():
            return True
        case _:
            return False


def _effect_requires_target_id(effect: Effect) -> bool:
    match effect:
        case EffectGainDestroyedCost():
            return True
        case EffectStraighten(target=StraightenTarget.SELECTED):
            return True
        case EffectStore(on_target=True):
            return True
        case _:
            return False


def _cost_provides_target_player(cost: Cost) -> bool:
    return isinstance(cost, CostSelectPlayer)


def _cost_provides_target_id(cost: Cost) -> bool:
    return isinstance(
        cost,
        (
            CostSelectCard,
            CostDiscardCard,
            CostDestroyComponent,
            CostDestroyCardType,
        ),
    )
