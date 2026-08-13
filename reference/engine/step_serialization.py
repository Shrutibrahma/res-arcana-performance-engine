from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import fields as dc_fields
from enum import Enum
from typing import Protocol, cast

from reference.engine.card_location import CardLocation
from reference.engine.collect_decision import CollectDecision
from reference.engine.deck_type import DeckType
from reference.engine.game_phase import GamePhase
from reference.engine.pool import Pool
from reference.engine.steps import (
    ActionFails,
    AssertCurrentPlayer,
    AssertEssencesOnCard,
    AssertLocation,
    AssertOwner,
    AssertPhase,
    AssertPool,
    AssertTurned,
    AssertVP,
    AssertWinners,
    ChooseMage,
    ChooseMagicItem,
    ClaimMonument,
    ClaimPlaceOfPower,
    ClaimTopMonument,
    CollectCost,
    DeclarativeAction,
    Decline,
    DiscardChoice,
    DiscardForEssences,
    Gain,
    LifeLossChoice,
    LifeLossReact,
    Pass,
    PlaceArtifact,
    ResolveDrawReveal,
    ResolveGameSetup,
    ResolveMonumentDraw,
    ResolveMonumentReveal,
    ResolveScryReveal,
    ScryChoice,
    ScryDeckChoice,
    Step,
    TakeStored,
    UsePower,
    VictoryReact,
)

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]

_ESSENCE_FIELDS = ("elan", "life", "calm", "death", "gold")


class _HasValue(Protocol):
    @property
    def value(self) -> int: ...


_PYO3_ENUM_NAMES: dict[str, str] = {
    "PyCollectDecision": "CollectDecision",
    "PyDeckType": "DeckType",
    "PyCardLocation": "CardLocation",
    "PyGamePhase": "GamePhase",
}


def _is_pool(v: object) -> bool:
    return hasattr(v, "elan") and hasattr(v, "gold") and hasattr(v, "death")


def _serialize_value(v: object) -> JsonValue:
    if v is None:
        return None
    if _is_pool(v):
        pool = cast(Pool, v)
        d: dict[str, JsonValue] = {}
        if pool.elan != 0:
            d["elan"] = pool.elan
        if pool.life != 0:
            d["life"] = pool.life
        if pool.calm != 0:
            d["calm"] = pool.calm
        if pool.death != 0:
            d["death"] = pool.death
        if pool.gold != 0:
            d["gold"] = pool.gold
        return d
    if isinstance(v, (list, tuple)):
        return [_serialize_value(item) for item in cast(Sequence[object], v)]
    if isinstance(v, bool):
        return v

    if isinstance(v, Enum):
        return {"__enum__": type(v).__name__, "value": v.value}
    if isinstance(v, (str, int, float)):
        return v
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return serialize_step(cast(Step, v))
    type_name = type(v).__name__
    if type_name in _PYO3_ENUM_NAMES:
        canonical = _PYO3_ENUM_NAMES[type_name]
        return {"__enum__": canonical, "value": cast(_HasValue, v).value}
    assert False, f"Unexpected type: {type(v)}"


_ALWAYS_EMIT = frozenset({"player_id", "power_index"})


def serialize_step(step: Step) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {"__type__": type(step).__name__}
    defaults: dict[str, object] = {}
    if dataclasses.is_dataclass(step) and not isinstance(step, type):
        for f in dc_fields(step):
            if f.default is not dataclasses.MISSING:
                defaults[f.name] = f.default
            elif f.default_factory is not dataclasses.MISSING:
                defaults[f.name] = f.default_factory()
    for k, v in step.__dict__.items():
        if v is None:
            continue
        if k not in _ALWAYS_EMIT and k in defaults and v == defaults[k] and not isinstance(v, Enum):
            continue
        sv = _serialize_value(v)
        if k not in _ALWAYS_EMIT and k in defaults and isinstance(sv, dict) and not sv and _is_pool(v):
            continue
        result[k] = sv
    return result


def _int_field(d: dict[str, JsonValue], key: str, default: int = 0) -> int:
    v = d.get(key, default)
    assert isinstance(v, int), f"{key}: expected int, got {type(v)}"
    return v


def _dict_to_pool(d: dict[str, JsonValue]) -> Pool:
    return Pool(
        elan=_int_field(d, "elan"),
        life=_int_field(d, "life"),
        calm=_int_field(d, "calm"),
        death=_int_field(d, "death"),
        gold=_int_field(d, "gold"),
    )


class _Reader:
    __slots__ = ("d",)

    def __init__(self, d: dict[str, JsonValue]) -> None:
        self.d = d

    def str(self, key: str) -> str:
        v = self.d[key]
        assert isinstance(v, str), f"{key}: expected str, got {type(v)}"
        return v

    def opt_str(self, key: str) -> str | None:
        v = self.d.get(key)
        return v if isinstance(v, str) else None

    def int(self, key: str, default: int = 0) -> int:
        v = self.d.get(key, default)
        assert isinstance(v, int), f"{key}: expected int, got {type(v)}"
        return v

    def opt_int(self, key: str) -> int | None:
        v = self.d.get(key)
        return v if isinstance(v, int) else None

    def bool(self, key: str, default: bool = False) -> bool:
        return bool(self.d.get(key, default))

    def pool(self, key: str) -> Pool:
        v = self.d.get(key)
        if isinstance(v, dict):
            return _dict_to_pool(v)
        return Pool()

    def str_list(self, key: str) -> list[str]:
        v = self.d.get(key, [])
        assert isinstance(v, list), f"{key}: expected list"
        return [str(x) for x in v]

    def int_list(self, key: str) -> list[int]:
        v = self.d.get(key, [])
        assert isinstance(v, list), f"{key}: expected list"
        result: list[int] = []
        for x in v:
            assert isinstance(x, int), f"{key}: expected int element, got {type(x)}"
            result.append(x)
        return result

    def str_tuple(self, key: str) -> tuple[str, ...]:
        return tuple(self.str_list(key))

    def nested_str_tuple(self, key: str) -> tuple[tuple[str, ...], ...]:
        v = self.d.get(key, [])
        assert isinstance(v, list), f"{key}: expected list"
        result: list[tuple[str, ...]] = []
        for inner in v:
            assert isinstance(inner, list), f"{key}: expected nested list"
            result.append(tuple(str(x) for x in inner))
        return tuple(result)

    def opt_nested_str_tuple(self, key: str) -> tuple[tuple[str, ...], ...] | None:
        if key not in self.d:
            return None
        return self.nested_str_tuple(key)

    def opt_pool_tuple(self, key: str) -> tuple[Pool, ...] | None:
        v = self.d.get(key)
        if v is None:
            return None
        assert isinstance(v, list), f"{key}: expected list"
        return tuple((_dict_to_pool(cast(dict[str, JsonValue], x)) if isinstance(x, dict) else Pool()) for x in v)

    def collect_decision(self, key: str, default: CollectDecision) -> CollectDecision:
        v = self.d.get(key)
        if isinstance(v, dict) and "__enum__" in v:
            val = v["value"]
            if isinstance(val, str):
                return CollectDecision[val]
            return CollectDecision(val)
        return default

    def opt_collect_decision(self, key: str) -> CollectDecision | None:
        v = self.d.get(key)
        if isinstance(v, dict) and "__enum__" in v:
            val = v["value"]
            if isinstance(val, str):
                return CollectDecision[val]
            return CollectDecision(val)
        return None

    def deck_type(self, key: str, default: DeckType) -> DeckType:
        v = self.d.get(key)
        if isinstance(v, dict) and "__enum__" in v:
            val = v["value"]
            if isinstance(val, str):
                return DeckType[val]
            return DeckType(val)
        return default

    def card_location(self, key: str) -> CardLocation:
        v = self.d[key]
        if isinstance(v, dict) and "__enum__" in v:
            return CardLocation(v["value"])
        assert False, f"{key}: expected CardLocation enum"

    def game_phase(self, key: str) -> GamePhase:
        v = self.d[key]
        if isinstance(v, dict) and "__enum__" in v:
            return GamePhase(v["value"])
        assert False, f"{key}: expected GamePhase enum"


def deserialize_step_from_str(s: str) -> Step:
    import json

    return deserialize_step(json.loads(s))


def deserialize_step(d: dict[str, JsonValue]) -> Step:
    r = _Reader(d)
    match d["__type__"]:
        case "UsePower":
            return UsePower(
                card_name=r.str("card_name"),
                power_index=r.int("power_index"),
                player_id=r.int("player_id"),
                target_name=r.opt_str("target_name"),
                target_player_id=r.opt_int("target_player_id"),
                pay=r.pool("pay"),
                gain=r.pool("gain"),
            )
        case "PlaceArtifact":
            return PlaceArtifact(
                artifact_name=r.str("artifact_name"),
                pay=r.pool("pay"),
                player_id=r.int("player_id"),
            )
        case "Pass":
            return Pass(item_name=r.str("item_name"), player_id=r.int("player_id"))
        case "Decline":
            return Decline(card_name=r.str("card_name"), player_id=r.int("player_id"))
        case "ClaimMonument":
            return ClaimMonument(monument_name=r.str("monument_name"), player_id=r.int("player_id"))
        case "ClaimTopMonument":
            return ClaimTopMonument(player_id=r.int("player_id"))
        case "ClaimPlaceOfPower":
            return ClaimPlaceOfPower(
                pop_name=r.str("pop_name"),
                pay=r.pool("pay"),
                player_id=r.int("player_id"),
            )
        case "DiscardForEssences":
            return DiscardForEssences(
                card_name=r.str("card_name"),
                gain=r.pool("gain"),
                player_id=r.int("player_id"),
            )
        case "LifeLossReact":
            return LifeLossReact(
                card_name=r.str("card_name"),
                power_index=r.int("power_index"),
                player_id=r.int("player_id"),
                target_name=r.opt_str("target_name"),
                pay=r.pool("pay"),
                gain=r.pool("gain"),
            )
        case "VictoryReact":
            return VictoryReact(
                card_name=r.str("card_name"),
                power_index=r.int("power_index"),
                player_id=r.int("player_id"),
                target_name=r.opt_str("target_name"),
                pay=r.pool("pay"),
            )
        case "LifeLossChoice":
            return LifeLossChoice(player_id=r.int("player_id"), pay=r.pool("pay"))
        case "TakeStored":
            return TakeStored(
                card_name=r.str("card_name"),
                player_id=r.int("player_id"),
                decision=r.collect_decision("decision", CollectDecision.TAKE_STORED),
            )
        case "CollectCost":
            return CollectCost(
                card_name=r.str("card_name"),
                player_id=r.int("player_id"),
                decision=r.collect_decision("decision", CollectDecision.PAY_COST),
            )
        case "Gain":
            return Gain(
                card_name=r.str("card_name"),
                gain=r.pool("gain"),
                player_id=r.int("player_id"),
                use_alt=r.bool("use_alt"),
            )
        case "ScryDeckChoice":
            return ScryDeckChoice(
                player_id=r.int("player_id"),
                scry_target=r.deck_type("scry_target", DeckType.ARTIFACT),
            )
        case "ScryChoice":
            return ScryChoice(player_id=r.int("player_id"), scry_order=r.int_list("scry_order"))
        case "DiscardChoice":
            names = r.str_list("card_names")
            return DiscardChoice(*names, player_id=r.int("player_id"))
        case "ChooseMage":
            return ChooseMage(mage_name=r.str("mage_name"), player_id=r.int("player_id"))
        case "ChooseMagicItem":
            return ChooseMagicItem(item_name=r.str("item_name"), player_id=r.int("player_id"))
        case "ResolveGameSetup":
            return ResolveGameSetup(
                places_of_power=r.str_tuple("places_of_power"),
                monument_display=r.str_tuple("monument_display"),
                monument_deck=r.str_tuple("monument_deck"),
                mage_options=r.nested_str_tuple("mage_options"),
                first_player=r.int("first_player"),
                artifact_decks=r.opt_nested_str_tuple("artifact_decks"),
                starting_essences=r.opt_pool_tuple("starting_essences"),
            )
        case "ResolveDrawReveal":
            return ResolveDrawReveal(
                known_cards=r.str_list("known_cards"),
                revealed_cards=r.str_list("revealed_cards"),
                player_id=r.int("player_id"),
            )
        case "ResolveScryReveal":
            return ResolveScryReveal(
                revealed_cards=r.str_list("revealed_cards"),
                player_id=r.int("player_id"),
            )
        case "ResolveMonumentDraw":
            return ResolveMonumentDraw(monument_name=r.str("monument_name"), player_id=r.int("player_id"))
        case "ResolveMonumentReveal":
            return ResolveMonumentReveal(monument_name=r.str("monument_name"), player_id=r.int("player_id"))
        case "AssertVP":
            return AssertVP(player_id=r.int("player_id"), vp=r.int("vp"))
        case "AssertWinners":
            return AssertWinners(winner_ids=r.int_list("winner_ids"))
        case "AssertPool":
            return AssertPool(
                player_id=r.int("player_id"),
                elan=r.int("elan"),
                life=r.int("life"),
                calm=r.int("calm"),
                death=r.int("death"),
                gold=r.int("gold"),
            )
        case "AssertEssencesOnCard":
            return AssertEssencesOnCard(
                card_name=r.str("card_name"),
                elan=r.int("elan"),
                life=r.int("life"),
                calm=r.int("calm"),
                death=r.int("death"),
                gold=r.int("gold"),
                player_id=r.int("player_id"),
            )
        case "AssertTurned":
            return AssertTurned(
                card_name=r.str("card_name"),
                turned=r.bool("turned", True),
                player_id=r.int("player_id"),
            )
        case "AssertLocation":
            return AssertLocation(card_name=r.str("card_name"), location=r.card_location("location"))
        case "AssertOwner":
            from reference.engine.action_types import UNOWNED

            return AssertOwner(card_name=r.str("card_name"), player_id=r.int("player_id", UNOWNED))
        case "AssertCurrentPlayer":
            return AssertCurrentPlayer(player_id=r.int("player_id"))
        case "AssertPhase":
            return AssertPhase(phase=r.game_phase("phase"))
        case "ActionFails":
            inner_dict = d.get("action")
            assert isinstance(inner_dict, dict), "ActionFails requires 'action' field"
            inner = deserialize_step(inner_dict)
            assert isinstance(inner, DeclarativeAction)
            return ActionFails(
                action=inner,
                msg=r.opt_str("msg"),
            )
        case _:
            raise ValueError(f"Unknown step type: {d['__type__']}")
