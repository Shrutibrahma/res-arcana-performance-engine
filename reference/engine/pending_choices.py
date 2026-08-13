from __future__ import annotations

from dataclasses import dataclass, field

from .action_types import (
    EntityId,
    PlayerId,
)
from .collect_option_type import CollectOptionType
from .deck_type import DeckType
from .essence import Essence
from .models import MAX_PLAYERS
from .pool import Pool
from .select_card_filter import SelectCardFilter


@dataclass(frozen=True, slots=True)
class StoredEssenceOption:
    essence: Essence
    amount: int


@dataclass(frozen=True, slots=True)
class NaturalCollectOption:
    essence: Essence | None = None
    amount: int = 0
    option_type: CollectOptionType = CollectOptionType.FIXED_ESSENCE
    alt_any_amount: int = 0
    restriction_mask: int = 0
    alt_restriction_mask: int = 0


@dataclass(frozen=True, slots=True)
class PendingCollectCost:

    pid: PlayerId
    eid: EntityId
    cost_essences: Pool = field(default_factory=Pool)
    cost_turn: bool = False


@dataclass(frozen=True, slots=True)
class PendingCollectStorage:

    pid: PlayerId
    eid: EntityId
    stored_essences: tuple[StoredEssenceOption, ...] = ()

    natural_collect: list[NaturalCollectOption] | None = None

    bonus_multiplier: int = 0


@dataclass(frozen=True, slots=True)
class PendingGain:

    pid: PlayerId
    any_amount: int
    source_eid: EntityId | None = None
    restriction_mask: int = 0
    alt_any_amount: int = 0
    alt_restriction_mask: int = 0


@dataclass(frozen=True, slots=True)
class PendingLifeLossChoice:

    pid: PlayerId
    amount: int
    source: EntityId | str | None = None


@dataclass(frozen=True, slots=True)
class PendingScryDeckChoice:
    pid: PlayerId
    scry_count: int
    source_eid: EntityId


@dataclass(frozen=True, slots=True)
class PendingScryChoice:
    pid: PlayerId
    deck_type: DeckType
    card_eids: tuple[EntityId, ...]

    @property
    def count(self) -> int:
        return len(self.card_eids)


@dataclass(frozen=True, slots=True)
class PendingScryRevealChoice:

    pid: PlayerId
    known_eids: tuple[EntityId, ...]
    reveal_count: int
    deck_type: DeckType


@dataclass(frozen=True, slots=True)
class PendingDiscardChoice:
    pid: PlayerId
    count: int
    source_eid: EntityId


@dataclass(frozen=True, slots=True)
class PendingVictoryReactChoice:

    pid: PlayerId
    component_eid: EntityId
    power_index: int


@dataclass(frozen=True, slots=True)
class PendingCollectPhaseCursor:

    player: int
    component_index: int
    pass_num: int

    @property
    def pid(self) -> PlayerId:
        return PlayerId(self.player)


@dataclass(frozen=True, slots=True)
class PendingLifeLossScan:
    source: EntityId | str | None
    amount: int
    next_offset: int
    pid: PlayerId
    include_self: bool
    all_players: bool


@dataclass(frozen=True, slots=True)
class PendingDrawRevealChoice:

    pid: PlayerId
    known_eids: tuple[EntityId, ...]
    reveal_count: int


@dataclass(frozen=True, slots=True)
class PendingMonumentDrawChoice:

    pid: PlayerId


@dataclass(frozen=True, slots=True)
class PendingMonumentRevealChoice:

    pid: PlayerId


@dataclass(frozen=True, slots=True)
class PendingPlacementChoice:

    pid: PlayerId
    source_eid: EntityId
    filter: SelectCardFilter = field(default_factory=SelectCardFilter)
    discount: int = 0
    free: bool = False
    can_discount_gold: bool = False


@dataclass(frozen=True, slots=True)
class PendingGameSetupChoice:

    pid: PlayerId = PlayerId(MAX_PLAYERS)  # noqa: RUF009  # NewType returns immutable int


PendingChoice = (
    PendingCollectPhaseCursor
    | PendingCollectCost
    | PendingCollectStorage
    | PendingGain
    | PendingLifeLossChoice
    | PendingLifeLossScan
    | PendingScryDeckChoice
    | PendingScryChoice
    | PendingScryRevealChoice
    | PendingDiscardChoice
    | PendingDrawRevealChoice
    | PendingMonumentDrawChoice
    | PendingMonumentRevealChoice
    | PendingPlacementChoice
    | PendingVictoryReactChoice
    | PendingGameSetupChoice
)
