from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from reference.engine.action_types import UNOWNED
from reference.engine.card_location import CardLocation
from reference.engine.collect_decision import CollectDecision
from reference.engine.deck_type import DeckType
from reference.engine.game_phase import GamePhase
from reference.engine.pool import Pool


@dataclass(frozen=True)
class UsePower:
    card_name: str
    power_index: int = 0
    player_id: int = 0
    target_name: str | None = None
    target_player_id: int | None = None
    pay: Pool = field(default_factory=Pool)
    gain: Pool = field(default_factory=Pool)


@dataclass(frozen=True)
class PlaceArtifact:
    artifact_name: str
    pay: Pool
    player_id: int = 0


@dataclass(frozen=True)
class Pass:
    item_name: str
    player_id: int = 0


@dataclass(frozen=True)
class Decline:
    card_name: str
    player_id: int = 0


@dataclass(frozen=True)
class ClaimMonument:
    monument_name: str
    player_id: int = 0


@dataclass(frozen=True)
class ClaimTopMonument:
    player_id: int = 0


@dataclass(frozen=True)
class ClaimPlaceOfPower:
    pop_name: str
    pay: Pool
    player_id: int = 0


@dataclass(frozen=True)
class DiscardForEssences:
    card_name: str
    gain: Pool
    player_id: int = 0


@dataclass(frozen=True)
class LifeLossReact:
    card_name: str
    power_index: int = 0
    player_id: int = 0
    target_name: str | None = None
    pay: Pool = field(default_factory=Pool)
    gain: Pool = field(default_factory=Pool)


@dataclass(frozen=True)
class VictoryReact:
    card_name: str
    power_index: int = 0
    player_id: int = 0
    target_name: str | None = None
    pay: Pool = field(default_factory=Pool)


@dataclass(frozen=True)
class LifeLossChoice:
    player_id: int = 0
    pay: Pool = field(default_factory=Pool)


@dataclass(frozen=True)
class TakeStored:
    card_name: str
    player_id: int = 0
    decision: CollectDecision = CollectDecision.TAKE_STORED


@dataclass(frozen=True)
class CollectCost:
    card_name: str
    player_id: int = 0
    decision: CollectDecision = CollectDecision.PAY_COST


@dataclass(frozen=True)
class Gain:
    card_name: str
    gain: Pool
    player_id: int = 0
    use_alt: bool = False


@dataclass(frozen=True)
class ScryDeckChoice:
    player_id: int = 0
    scry_target: DeckType = DeckType.ARTIFACT


@dataclass(frozen=True)
class ScryChoice:
    player_id: int = 0
    scry_order: list[int] = field(default_factory=lambda: list[int]())  # noqa: PLW0108


@dataclass(frozen=True)
class DiscardChoice:
    card_names: tuple[str, ...]
    player_id: int = 0

    def __init__(self, *card_names: str, player_id: int = 0):
        object.__setattr__(self, "card_names", card_names)
        object.__setattr__(self, "player_id", player_id)


@dataclass(frozen=True)
class ChooseMage:
    mage_name: str
    player_id: int = 0


@dataclass(frozen=True)
class ChooseMagicItem:
    item_name: str
    player_id: int = 0


CHANCE_STEP_TYPES: frozenset[str] = frozenset(
    {
        "ResolveDrawReveal",
        "ResolveScryReveal",
        "ResolveMonumentDraw",
        "ResolveMonumentReveal",
    }
)


@dataclass(frozen=True, kw_only=True)
class ResolveGameSetup:
    places_of_power: tuple[str, ...]
    monument_display: tuple[str, ...]
    monument_deck: tuple[str, ...]
    mage_options: tuple[tuple[str, ...], ...]
    first_player: int = 0
    artifact_decks: tuple[tuple[str, ...], ...] | None = None
    starting_essences: tuple[Pool, ...] | None = None


@dataclass(frozen=True)
class ResolveDrawReveal:
    known_cards: list[str] = field(default_factory=lambda: list[str]())  # noqa: PLW0108
    revealed_cards: list[str] = field(default_factory=lambda: list[str]())  # noqa: PLW0108
    player_id: int = 0


@dataclass(frozen=True)
class ResolveScryReveal:
    revealed_cards: list[str]
    player_id: int = 0


@dataclass(frozen=True)
class ResolveMonumentDraw:
    monument_name: str
    player_id: int = 0


@dataclass(frozen=True)
class ResolveMonumentReveal:
    monument_name: str
    player_id: int = 0


@dataclass(frozen=True)
class AssertPool:
    player_id: int = 0
    elan: int = 0
    life: int = 0
    calm: int = 0
    death: int = 0
    gold: int = 0


@dataclass(frozen=True)
class AssertEssencesOnCard:
    card_name: str
    elan: int = 0
    life: int = 0
    calm: int = 0
    death: int = 0
    gold: int = 0
    player_id: int = 0


@dataclass(frozen=True)
class AssertTurned:
    card_name: str
    turned: bool = True
    player_id: int = 0


@dataclass(frozen=True)
class AssertLocation:
    card_name: str
    location: CardLocation


@dataclass(frozen=True)
class AssertOwner:
    card_name: str
    player_id: int = UNOWNED


@dataclass(frozen=True)
class AssertCurrentPlayer:
    player_id: int


@dataclass(frozen=True)
class AssertPhase:
    phase: GamePhase


@dataclass(frozen=True)
class AssertVP:
    player_id: int
    vp: int


@dataclass(frozen=True)
class AssertWinners:
    winner_ids: list[int]


@dataclass(frozen=True)
class ActionFails:
    action: DeclarativeAction
    msg: str | None = None


DeclarativeAction = (
    UsePower
    | PlaceArtifact
    | Decline
    | ClaimMonument
    | ClaimTopMonument
    | ResolveMonumentDraw
    | ResolveMonumentReveal
    | ClaimPlaceOfPower
    | DiscardForEssences
    | Pass
    | LifeLossReact
    | VictoryReact
    | LifeLossChoice
    | TakeStored
    | ChooseMage
    | ChooseMagicItem
    | CollectCost
    | Gain
    | ScryDeckChoice
    | ScryChoice
    | DiscardChoice
    | ResolveDrawReveal
    | ResolveScryReveal
)

Step = (
    DeclarativeAction
    | ResolveGameSetup
    | ActionFails
    | AssertPool
    | AssertEssencesOnCard
    | AssertTurned
    | AssertLocation
    | AssertOwner
    | AssertCurrentPlayer
    | AssertPhase
    | AssertVP
    | AssertWinners
)


def format_pool(pool: Pool) -> str:
    parts: list[str] = []
    if pool.elan:
        parts.append(f"elan={pool.elan}")
    if pool.life:
        parts.append(f"life={pool.life}")
    if pool.calm:
        parts.append(f"calm={pool.calm}")
    if pool.death:
        parts.append(f"death={pool.death}")
    if pool.gold:
        parts.append(f"gold={pool.gold}")
    if not parts:
        return "Pool()"
    return f"Pool({', '.join(parts)})"


def _fv(val: object) -> str:
    match val:
        case str():
            return f'"{val}"'
        case bool():
            return repr(val)
        case CollectDecision():
            return f"CollectDecision.{val.name}"
        case DeckType():
            return f"DeckType.{val.name}"
        case CardLocation():
            return f"CardLocation.{val.name}"
        case GamePhase():
            return f"GamePhase.{val.name}"
        case int():
            return repr(val)
        case None:
            return "None"
        case Pool():
            return format_pool(val)
        case list():
            items = ", ".join(_fv(v) for v in cast(list[object], val))
            return f"[{items}]"
        case tuple():
            tup = cast(tuple[object, ...], val)
            if not tup:
                return "()"
            if isinstance(tup[0], tuple):
                inner = ", ".join(_fv(t) for t in tup)
                return f"({inner})"
            items = ", ".join(_fv(v) for v in tup)
            return f"({items},)"
        case _:
            return repr(val)


def _build(cls_name: str, positionals: list[object], keywords: list[tuple[str, object, object]]) -> str:
    parts = [_fv(v) for v in positionals]
    for name, val, default in keywords:
        if val != default:
            parts.append(f"{name}={_fv(val)}")
    return f"{cls_name}({', '.join(parts)})"


def _kw_pool(name: str, val: Pool) -> tuple[str, object, object]:
    return (name, val, Pool())


def format_step(step: Step) -> str:
    match step:
        case UsePower():
            return _build(
                "UsePower",
                [step.card_name],
                [
                    ("power_index", step.power_index, 0),
                    ("player_id", step.player_id, 0),
                    ("target_name", step.target_name, None),
                    ("target_player_id", step.target_player_id, None),
                    _kw_pool("pay", step.pay),
                    _kw_pool("gain", step.gain),
                ],
            )
        case PlaceArtifact():
            return _build(
                "PlaceArtifact",
                [step.artifact_name, step.pay],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case Pass():
            return _build(
                "Pass",
                [step.item_name],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case Decline():
            return _build(
                "Decline",
                [step.card_name],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case ClaimMonument():
            return _build(
                "ClaimMonument",
                [step.monument_name],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case ClaimTopMonument():
            return _build(
                "ClaimTopMonument",
                [],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case ClaimPlaceOfPower():
            return _build(
                "ClaimPlaceOfPower",
                [step.pop_name, step.pay],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case DiscardForEssences():
            return _build(
                "DiscardForEssences",
                [step.card_name, step.gain],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case LifeLossReact():
            return _build(
                "LifeLossReact",
                [step.card_name],
                [
                    ("power_index", step.power_index, 0),
                    ("player_id", step.player_id, 0),
                    ("target_name", step.target_name, None),
                    _kw_pool("pay", step.pay),
                    _kw_pool("gain", step.gain),
                ],
            )
        case VictoryReact():
            return _build(
                "VictoryReact",
                [step.card_name],
                [
                    ("power_index", step.power_index, 0),
                    ("player_id", step.player_id, 0),
                    ("target_name", step.target_name, None),
                    _kw_pool("pay", step.pay),
                ],
            )
        case LifeLossChoice():
            return _build(
                "LifeLossChoice",
                [],
                [
                    ("player_id", step.player_id, 0),
                    _kw_pool("pay", step.pay),
                ],
            )
        case TakeStored():
            return _build(
                "TakeStored",
                [step.card_name],
                [
                    ("player_id", step.player_id, 0),
                    ("decision", step.decision, CollectDecision.TAKE_STORED),
                ],
            )
        case CollectCost():
            return _build(
                "CollectCost",
                [step.card_name],
                [
                    ("player_id", step.player_id, 0),
                    ("decision", step.decision, CollectDecision.PAY_COST),
                ],
            )
        case Gain():
            return _build(
                "Gain",
                [step.card_name, step.gain],
                [
                    ("player_id", step.player_id, 0),
                    ("use_alt", step.use_alt, False),
                ],
            )
        case ScryDeckChoice():
            return _build(
                "ScryDeckChoice",
                [],
                [
                    ("player_id", step.player_id, 0),
                    ("scry_target", step.scry_target, DeckType.ARTIFACT),
                ],
            )
        case ScryChoice():
            return _build(
                "ScryChoice",
                [],
                [
                    ("player_id", step.player_id, 0),
                    ("scry_order", step.scry_order, []),
                ],
            )
        case DiscardChoice():
            cards = ", ".join(_fv(n) for n in step.card_names)
            if step.player_id != 0:
                return f"DiscardChoice({cards}, player_id={step.player_id})"
            return f"DiscardChoice({cards})"
        case ChooseMage():
            return _build(
                "ChooseMage",
                [step.mage_name],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case ChooseMagicItem():
            return _build(
                "ChooseMagicItem",
                [step.item_name],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case ResolveGameSetup():
            return _build(
                "ResolveGameSetup",
                [],
                [
                    ("places_of_power", step.places_of_power, None),
                    ("monument_display", step.monument_display, None),
                    ("monument_deck", step.monument_deck, None),
                    ("mage_options", step.mage_options, None),
                    ("first_player", step.first_player, 0),
                    ("artifact_decks", step.artifact_decks, None),
                    ("starting_essences", step.starting_essences, None),
                ],
            )
        case ResolveDrawReveal():
            return _build(
                "ResolveDrawReveal",
                [],
                [
                    ("known_cards", step.known_cards, []),
                    ("revealed_cards", step.revealed_cards, []),
                    ("player_id", step.player_id, 0),
                ],
            )
        case ResolveScryReveal():
            return _build(
                "ResolveScryReveal",
                [step.revealed_cards],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case ResolveMonumentDraw():
            return _build(
                "ResolveMonumentDraw",
                [step.monument_name],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case ResolveMonumentReveal():
            return _build(
                "ResolveMonumentReveal",
                [step.monument_name],
                [
                    ("player_id", step.player_id, 0),
                ],
            )
        case AssertPool():
            return _build(
                "AssertPool",
                [],
                [
                    ("player_id", step.player_id, 0),
                    ("elan", step.elan, 0),
                    ("life", step.life, 0),
                    ("calm", step.calm, 0),
                    ("death", step.death, 0),
                    ("gold", step.gold, 0),
                ],
            )
        case AssertEssencesOnCard():
            return _build(
                "AssertEssencesOnCard",
                [step.card_name],
                [
                    ("elan", step.elan, 0),
                    ("life", step.life, 0),
                    ("calm", step.calm, 0),
                    ("death", step.death, 0),
                    ("gold", step.gold, 0),
                    ("player_id", step.player_id, 0),
                ],
            )
        case AssertTurned():
            return _build(
                "AssertTurned",
                [step.card_name],
                [
                    ("turned", step.turned, True),
                    ("player_id", step.player_id, 0),
                ],
            )
        case AssertLocation():
            return _build("AssertLocation", [step.card_name, step.location], [])
        case AssertOwner():
            return _build(
                "AssertOwner",
                [step.card_name],
                [
                    ("player_id", step.player_id, UNOWNED),
                ],
            )
        case AssertCurrentPlayer():
            return _build("AssertCurrentPlayer", [step.player_id], [])
        case AssertPhase():
            return _build("AssertPhase", [step.phase], [])
        case AssertVP():
            return _build("AssertVP", [step.player_id, step.vp], [])
        case AssertWinners():
            return _build("AssertWinners", [step.winner_ids], [])
        case ActionFails():
            inner = format_step(step.action)
            if step.msg is not None:
                return f"ActionFails({inner}, msg={_fv(step.msg)})"
            return f"ActionFails({inner})"
