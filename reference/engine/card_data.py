from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .card_database import CardDatabase
from .card_type import EntityFlag
from .collect_ability import CollectAbility
from .conditional_type import ConditionalType
from .costs import (
    Cost,
    CostDestroyCardType,
    CostDestroyComponent,
    CostDiscardCard,
    CostPayEssence,
    CostPayIdentical,
    CostRemoveFromCard,
    CostSelectCard,
    CostSelectPlayer,
    CostTurnComponent,
    DestroyMode,
    TurnableType,
)
from .discount import Discount
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
from .entity_data import EntityData
from .essence import Essence
from .expansions import EXPANSION_BASE
from .pool import Pool
from .power import Power
from .power_type import PowerType
from .react_trigger import ReactTrigger
from .select_card_filter import SelectCardFilter
from .select_card_location import SelectCardLocation
from .straighten_target import StraightenTarget

_CARDS_PATH = Path(__file__).parent.parent.parent / "data" / "cards.json"


def _pool(v: list[int] | None) -> Pool:
    return Pool(values=v) if v else Pool()


def _essence(name: str) -> Essence:
    return Essence[name]


def _filter(d: dict[str, Any]) -> SelectCardFilter:
    return SelectCardFilter(
        location=SelectCardLocation[d["location"]],
        require_tapped=d.get("require_tapped", False),
        card_type_mask=d.get("card_type_mask", 0),
        own_cards_only=d.get("own_cards_only", False),
        component_type_mask=d.get("component_type_mask", 0),
        exclude_self=d.get("exclude_self", False),
    )


def _cost(d: dict[str, Any]) -> Cost:
    t = d["type"]
    if t == "PayEssence":
        return CostPayEssence(
            essences=_pool(d.get("essences")),
            any_amount=d.get("any_amount", 0),
            exclude=tuple(_essence(x) for x in d.get("exclude", [])),
        )
    if t == "TurnComponent":
        return CostTurnComponent(turnable_type=TurnableType[d["turnable_type"]])
    if t == "RemoveFromCard":
        return CostRemoveFromCard(essences=_pool(d["essences"]))
    if t == "PayIdentical":
        et = d.get("essence_type")
        return CostPayIdentical(
            base_cost=d.get("base_cost", 0),
            min_amount=d["min_amount"],
            essence_type=_essence(et) if et else None,
        )
    if t == "DestroyComponent":
        return CostDestroyComponent(destroy_mode=DestroyMode[d["destroy_mode"]])
    if t == "DestroyCardType":
        return CostDestroyCardType(card_type_mask=d["card_type_mask"])
    if t == "DiscardCard":
        return CostDiscardCard(
            card_type_mask=d.get("card_type_mask", 0),
            exclude_entity_flags=d.get("exclude_entity_flags", 0),
        )
    if t == "SelectPlayer":
        return CostSelectPlayer(opponent_only=d.get("opponent_only", False))
    if t == "SelectCard":
        return CostSelectCard(filter=_filter(d["filter"]))
    raise AssertionError(f"Unknown cost type: {t}")


def _effect(d: dict[str, Any]) -> Effect:
    t = d["type"]
    if t == "Gain":
        return EffectGain(essences=_pool(d["essences"]))
    if t == "GainAny":
        return EffectGainAny(
            amount=d["amount"],
            exclude=tuple(_essence(x) for x in d.get("exclude", [])),
        )
    if t == "Store":
        return EffectStore(
            essences=_pool(d.get("essences")),
            any_amount=d.get("any_amount", 0),
            exclude=tuple(_essence(x) for x in d.get("exclude", [])),
            what_spent=d.get("what_spent", False),
            on_target=d.get("on_target", False),
        )
    if t == "RivalsGain":
        return EffectRivalsGain(essences=_pool(d["essences"]))
    if t == "Damage":
        return EffectDamage(
            amount=d["amount"],
            defense_options=[_cost(c) for c in d.get("defense_options", [])],
            all_players=d.get("all_players", False),
            include_self=d.get("include_self", False),
        )
    if t == "Draw":
        return EffectDraw(
            amount=d["amount"],
            discard_after=d.get("discard_after", 0),
            require_deck_has_cards=d.get("require_deck_has_cards", False),
        )
    if t == "IgnoreDamage":
        return EffectIgnoreDamage()
    if t == "CheckVictory":
        return EffectCheckVictory()
    if t == "Straighten":
        return EffectStraighten(target=StraightenTarget[d["target"]])
    if t == "Scry":
        return EffectScry(amount=d["amount"])
    if t == "Place":
        return EffectPlace(
            filter=_filter(d["filter"]),
            discount=d.get("discount", 0),
            free=d.get("free", False),
            can_discount_gold=d.get("can_discount_gold", False),
        )
    if t == "GainDestroyedCost":
        return EffectGainDestroyedCost(
            as_any=d.get("as_any", False),
            as_gold=d.get("as_gold", False),
            bonus=d.get("bonus", 0),
        )
    if t == "GainGoldEqualToSameSpent":
        return EffectGainGoldEqualToSameSpent()
    if t == "GainFromOpponent":
        return EffectGainFromOpponent(
            their_essence=_essence(d["their_essence"]),
            your_essence=_essence(d["your_essence"]),
        )
    if t == "GainSameTypeAsSpent":
        return EffectGainSameTypeAsSpent()
    if t == "TempVP":
        return EffectTempVP(amount=d["amount"])
    if t == "GainGoldFromCost":
        return EffectGainGoldFromCost(divisor=d["divisor"])
    raise AssertionError(f"Unknown effect type: {t}")


def _power(d: dict[str, Any]) -> Power:
    return Power(
        power_type=PowerType[d["power_type"]],
        requires_turn=d.get("requires_turn", False),
        react_trigger=ReactTrigger[d.get("react_trigger", "NONE")],
        usable_when_turned=d.get("usable_when_turned", False),
        effect_description=d.get("effect_description", ""),
        costs=tuple(_cost(c) for c in d.get("costs", [])),
        effects=tuple(_effect(e) for e in d.get("effects", [])),
    )


def _discount(d: dict[str, Any]) -> Discount:
    return Discount(
        artifact=d.get("artifact", 0),
        dragon=d.get("dragon", 0),
        creature=d.get("creature", 0),
        can_discount_gold=d.get("can_discount_gold", False),
    )


def _collect_ability(d: dict[str, Any]) -> CollectAbility:
    ct = d.get("conditional_type")
    return CollectAbility(
        essences=_pool(d.get("essences")),
        choice_mask=d.get("choice_mask", 0),
        any_amount=d.get("any_amount", 0),
        alt_any_amount=d.get("alt_any_amount", 0),
        restriction_mask=d.get("restriction_mask", 0),
        conditional_type=ConditionalType[ct] if ct else None,
        per_stored_essence_multiplier=d.get("per_stored_essence_multiplier", 0),
        cost_essences=_pool(d.get("cost_essences")),
        cost_turn=d.get("cost_turn", False),
    )


def _entity(d: dict[str, Any]) -> EntityData:
    return EntityData(
        name=d["name"],
        powers=tuple(_power(p) for p in d.get("powers", [])),
        collect_ability=_collect_ability(d["collect_ability"]) if "collect_ability" in d else None,
        expansion=EXPANSION_BASE,
        placement_cost=_pool(d["placement_cost"]) if "placement_cost" in d else None,
        placement_cost_any=d.get("placement_cost_any", 0),
        card_type_mask=d.get("card_type_mask", 0),
        entity_flags=EntityFlag(d.get("entity_flags", 0)),
        victory_points=d.get("victory_points", 0),
        victory_points_per_two_artifacts=d.get("victory_points_per_two_artifacts", 0),
        discount=_discount(d["discount"]) if "discount" in d else Discount(),
        points_per_essence=tuple(d.get("points_per_essence", (0, 0, 0, 0, 0))),
        base_points=d.get("base_points", 0),
        vp_per_dragon=d.get("vp_per_dragon", 0),
        vp_per_creature=d.get("vp_per_creature", 0),
        vp_per_artifact_count_num=d.get("vp_per_artifact_count_num", 0),
        vp_per_artifact_count_denom=d.get("vp_per_artifact_count_denom", 1),
    )


_cached_db: CardDatabase | None = None
_cached_lists: dict[str, list[EntityData]] | None = None


def _load() -> dict[str, list[EntityData]]:
    global _cached_lists  # noqa: PLW0603
    if _cached_lists is not None:
        return _cached_lists
    with open(_CARDS_PATH) as f:
        raw = json.load(f)
    _cached_lists = {
        category: [_entity(d) for d in raw[category]]
        for category in ("mages", "magic_items", "artifacts", "monuments", "places_of_power")
    }
    return _cached_lists


def __getattr__(name: str) -> list[EntityData]:
    mapping = {
        "MAGES": "mages",
        "MAGIC_ITEMS": "magic_items",
        "ARTIFACTS": "artifacts",
        "MONUMENTS": "monuments",
        "PLACES_OF_POWER": "places_of_power",
    }
    if name in mapping:
        return _load()[mapping[name]]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_card_database() -> CardDatabase:
    global _cached_db  # noqa: PLW0603
    if _cached_db is not None:
        return _cached_db
    lists = _load()
    db = CardDatabase(
        mages=tuple(lists["mages"]),
        magic_items=tuple(lists["magic_items"]),
        artifacts=tuple(lists["artifacts"]),
        monuments=tuple(lists["monuments"]),
        places_of_power=tuple(lists["places_of_power"]),
    )
    db.validate_all_powers()
    _cached_db = db
    return db
