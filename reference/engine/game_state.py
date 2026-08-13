from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import assert_never

from .action_types import UNOWNED, EntityId, PlayerId
from .card_database import CardDatabase
from .card_location import CardLocation
from .component_type import ComponentType
from .entity_data import UNKNOWN_ORDER, Discount, Entity, EntityData
from .expansions import (
    EXPANSION_BASE,
    EXPANSIONS_BASE,
    ExpansionCode,
)
from .game_phase import GamePhase
from .pending_choices import (
    PendingChoice,
    PendingDrawRevealChoice,
    PendingGameSetupChoice,
    PendingMonumentDrawChoice,
    PendingMonumentRevealChoice,
    PendingScryRevealChoice,
)
from .player_state import PlayerState
from .pool import Pool
from .power import Power
from .turnable_type import TurnableType


@dataclass
class GameState:

    num_players: int = 2
    entities: list[Entity] = field(default_factory=list[Entity])
    artifact_range: tuple[int, int] = (0, 0)
    mage_range: tuple[int, int] = (0, 0)
    magic_item_range: tuple[int, int] = (0, 0)
    monument_range: tuple[int, int] = (0, 0)
    pop_range: tuple[int, int] = (0, 0)
    players: list[PlayerState] = field(default_factory=list[PlayerState])
    phase: GamePhase = GamePhase.SETUP_GAME
    expansions: frozenset[ExpansionCode] = field(default_factory=lambda: frozenset({EXPANSION_BASE}))
    pending_stack: list[PendingChoice] = field(default_factory=list[PendingChoice])

    round_number: int = 0
    current_player_index: PlayerId = PlayerId(0)  # noqa: RUF009  # NewType returns immutable int
    first_player_index: PlayerId = PlayerId(0)  # noqa: RUF009  # NewType returns immutable int
    pending_turn_advance: bool = False
    winner_mask: int = 0
    is_mid_round_victory_check: bool = False
    temp_vp: list[int] = field(default_factory=list[int])

    def acting_player(self) -> PlayerId:
        if self.pending_stack:
            return self.pending_stack[-1].pid
        return self.current_player_index

    def is_chance(self) -> bool:
        if not self.pending_stack:
            return False
        top = self.pending_stack[-1]
        return isinstance(
            top,
            (
                PendingDrawRevealChoice,
                PendingScryRevealChoice,
                PendingMonumentDrawChoice,
                PendingMonumentRevealChoice,
            ),
        )

    def is_game_over(self) -> bool:
        return self.phase == GamePhase.GAME_OVER

    @property
    def victory_threshold(self) -> int:
        return 10

    @property
    def winner_ids(self) -> list[int]:
        return [i for i in range(self.num_players) if self.winner_mask & (1 << i)]

    def set_entities(
        self,
        entities: list[Entity],
        artifact_range: tuple[int, int],
        mage_range: tuple[int, int],
        magic_item_range: tuple[int, int],
        monument_range: tuple[int, int],
        pop_range: tuple[int, int],
    ) -> None:
        self.entities = entities
        self.artifact_range = artifact_range
        self.mage_range = mage_range
        self.magic_item_range = magic_item_range
        self.monument_range = monument_range
        self.pop_range = pop_range

    def iter_entities(
        self,
        component_type: ComponentType | None = None,
        location: CardLocation | None = None,
        owner_id: PlayerId | None = None,
        is_turned: bool | None = None,
    ) -> Iterator[tuple[EntityId, Entity]]:
        match component_type:
            case None:
                start = 0
                end = len(self.entities)
            case ComponentType.ARTIFACT:
                start, end = self.artifact_range
            case ComponentType.MAGE:
                start, end = self.mage_range
            case ComponentType.MAGIC_ITEM:
                start, end = self.magic_item_range
            case ComponentType.MONUMENT:
                start, end = self.monument_range
            case ComponentType.PLACE_OF_POWER:
                start, end = self.pop_range
            case _:
                assert_never()

        for i in range(start, end):
            e = self.entities[i]
            if (
                (location is None or location == e.location)
                and (is_turned is None or is_turned == e.is_turned)
                and (owner_id is None or owner_id == e.owner_id)
            ):
                yield EntityId(i), self.entities[i]

    def iter_artifacts(self) -> Iterator[tuple[EntityId, Entity]]:
        start, end = self.artifact_range
        for i in range(start, end):
            yield EntityId(i), self.entities[i]

    def iter_mages(self) -> Iterator[tuple[EntityId, Entity]]:
        start, end = self.mage_range
        for i in range(start, end):
            yield EntityId(i), self.entities[i]

    def iter_magic_items(self) -> Iterator[tuple[EntityId, Entity]]:
        start, end = self.magic_item_range
        for i in range(start, end):
            yield EntityId(i), self.entities[i]

    def iter_monuments(self) -> Iterator[tuple[EntityId, Entity]]:
        start, end = self.monument_range
        for i in range(start, end):
            yield EntityId(i), self.entities[i]

    def iter_places_of_power(self) -> Iterator[tuple[EntityId, Entity]]:
        start, end = self.pop_range
        for i in range(start, end):
            yield EntityId(i), self.entities[i]

    def get_player_hand(self, pid: PlayerId) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, art in self.iter_artifacts():
            if art.location == CardLocation.HAND and art.owner_id == pid:
                result.append(eid)
        result.sort(key=lambda e: self.entities[e].order_index)
        return result

    def get_player_deck(self, pid: PlayerId) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, art in self.iter_artifacts():
            if art.location == CardLocation.DECK and art.owner_id == pid:
                result.append(eid)
        result.sort(key=lambda e: self.entities[e].order_index)
        return result

    def get_known_deck_cards(self, pid: PlayerId) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, art in self.iter_artifacts():
            if art.location == CardLocation.DECK and art.owner_id == pid and art.order_index != UNKNOWN_ORDER:
                result.append(eid)
        result.sort(key=lambda e: self.entities[e].order_index)
        return result

    def get_unknown_deck_cards(self, pid: PlayerId) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, art in self.iter_artifacts():
            if art.location == CardLocation.DECK and art.owner_id == pid and art.order_index == UNKNOWN_ORDER:
                result.append(eid)
        return result

    def get_player_artifacts_in_play(self, pid: PlayerId) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, art in self.iter_artifacts():
            if art.location == CardLocation.IN_PLAY and art.owner_id == pid:
                result.append(eid)
        return result

    def get_player_discard(self, pid: PlayerId) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, art in self.iter_artifacts():
            if art.location == CardLocation.DISCARD and art.owner_id == pid:
                result.append(eid)
        return result

    def get_player_deck_count(self, pid: PlayerId) -> int:
        count = 0
        for _eid, art in self.iter_artifacts():
            if art.location == CardLocation.DECK and art.owner_id == pid:
                count += 1
        return count

    def get_player_mage(self, pid: PlayerId) -> EntityId:
        for eid, mage in self.iter_mages():
            if mage.location == CardLocation.IN_PLAY and mage.owner_id == pid:
                return eid
        raise AssertionError(f"Player {pid} has no mage")

    def get_player_magic_item(self, pid: PlayerId) -> EntityId:
        for eid, item in self.iter_magic_items():
            if item.location == CardLocation.IN_PLAY and item.owner_id == pid:
                return eid
        raise AssertionError(f"Player {pid} has no magic item")

    def get_player_monuments(self, pid: PlayerId) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, mon in self.iter_monuments():
            if mon.location == CardLocation.IN_PLAY and mon.owner_id == pid:
                result.append(eid)
        return result

    def get_player_places_of_power(self, pid: PlayerId) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, pop in self.iter_places_of_power():
            if pop.location == CardLocation.IN_PLAY and pop.owner_id == pid:
                result.append(eid)
        return result

    def get_available_magic_items(self) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, item in self.iter_magic_items():
            if item.location == CardLocation.AVAILABLE:
                result.append(eid)
        return result

    def get_monument_display(self) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, mon in self.iter_monuments():
            if mon.location == CardLocation.AVAILABLE:
                result.append(eid)
        return result

    def get_monument_deck(self) -> list[EntityId]:
        deck_cards: list[tuple[int, EntityId]] = []
        for eid, mon in self.iter_monuments():
            if mon.location == CardLocation.MONUMENT_DECK:
                deck_cards.append((mon.order_index, eid))
        deck_cards.sort()
        return [eid for _, eid in deck_cards]

    def get_known_monument_deck(self) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, mon in self.iter_monuments():
            if mon.location == CardLocation.MONUMENT_DECK and mon.order_index != UNKNOWN_ORDER:
                result.append(eid)
        result.sort(key=lambda e: self.entities[e].order_index)
        return result

    def get_unknown_monument_deck(self) -> list[EntityId]:
        result: list[EntityId] = []
        for eid, mon in self.iter_monuments():
            if mon.location == CardLocation.MONUMENT_DECK and mon.order_index == UNKNOWN_ORDER:
                result.append(eid)
        return result

    def draw_card(self, pid: PlayerId, count: int = 1) -> int:
        if count <= 0:
            return 0

        deck_size = len(self.get_player_deck(pid))
        discard_size = len(self.get_player_discard(pid))
        actual_draws = min(count, deck_size + discard_size)

        if actual_draws == 0:
            return 0

        known = self.get_known_deck_cards(pid)
        known_draws = min(len(known), actual_draws)
        unknown_draws = actual_draws - known_draws

        if unknown_draws > 0:
            unknown_in_deck = len(self.get_unknown_deck_cards(pid))
            if unknown_draws > unknown_in_deck:
                for _, art in self.iter_artifacts():
                    if art.location == CardLocation.DISCARD and art.owner_id == pid:
                        art.location = CardLocation.DECK
                        art.order_index = UNKNOWN_ORDER

        known_eids = tuple(known[:known_draws])

        self.pending_stack.append(
            PendingDrawRevealChoice(
                pid=pid,
                known_eids=known_eids,
                reveal_count=unknown_draws,
            )
        )

        return actual_draws

    def claim_monument(self, pid: PlayerId, monument_eid: EntityId) -> None:
        mon = self.entities[monument_eid]
        assert mon.location in (
            CardLocation.AVAILABLE,
            CardLocation.MONUMENT_DECK,
        ), mon.location
        mon.location = CardLocation.IN_PLAY
        mon.owner_id = pid
        mon.order_index = UNKNOWN_ORDER

    def get_top_monument_from_deck(self) -> EntityId | None:
        deck = self.get_monument_deck()
        return deck[0] if deck else None

    def all_players_passed(self) -> bool:
        for i in range(self.num_players):
            if self.players[i].is_active and not self.players[i].has_passed:
                return False
        return True

    def advance_to_next_player(self) -> None:
        assert self.phase == GamePhase.ACTIONS, self.phase
        for _ in range(self.num_players):
            self.current_player_index = PlayerId((self.current_player_index + 1) % self.num_players)
            player = self.players[self.current_player_index]
            if player.is_active and not player.has_passed:
                break
        else:
            raise AssertionError(f"No active non-passed player found among {self.num_players} players")

    def find_entity_by_name(self, name: str) -> EntityId:
        for i, entity in enumerate(self.entities):
            if entity.location == CardLocation.OUT_OF_GAME:
                continue
            if entity.data and entity.data.name == name:
                return EntityId(i)
        raise AssertionError(f"Entity not found: {name}")

    def get_player_creatures(self, pid: PlayerId) -> list[tuple[EntityId, Entity]]:
        result: list[tuple[EntityId, Entity]] = []
        for eid in self.get_player_artifacts_in_play(pid):
            entity = self.entities[eid]
            if entity.data and entity.data.is_creature:
                result.append((eid, entity))
        return result

    def get_player_dragons(self, pid: PlayerId) -> list[tuple[EntityId, Entity]]:
        result: list[tuple[EntityId, Entity]] = []
        for eid in self.get_player_artifacts_in_play(pid):
            entity = self.entities[eid]
            if entity.data and entity.data.is_dragon:
                result.append((eid, entity))
        return result

    def get_all_player_components(self, pid: PlayerId) -> list[tuple[EntityId, Entity]]:
        result: list[tuple[EntityId, Entity]] = []

        result.extend((eid, self.entities[eid]) for eid in self.get_player_artifacts_in_play(pid))

        for eid, mage in self.iter_mages():
            if mage.location == CardLocation.IN_PLAY and mage.owner_id == pid:
                result.append((eid, mage))

        for eid, item in self.iter_magic_items():
            if item.location == CardLocation.IN_PLAY and item.owner_id == pid:
                result.append((eid, item))

        result.extend((eid, self.entities[eid]) for eid in self.get_player_monuments(pid))

        result.extend((eid, self.entities[eid]) for eid in self.get_player_places_of_power(pid))

        return result

    def get_total_discount(self, pid: PlayerId) -> Discount:
        total = Discount()

        for _eid, entity in self.get_all_player_components(pid):
            d = entity.data.discount
            total = Discount(
                artifact=total.artifact + d.artifact,
                dragon=total.dragon + d.dragon,
                creature=total.creature + d.creature,
                can_discount_gold=total.can_discount_gold or d.can_discount_gold,
            )

        return total

    def begin_round(self) -> None:

        assert self.phase in (
            GamePhase.SETUP_CHOOSE_ITEMS,
            GamePhase.VICTORY_CHECK,
        ), self.phase
        self.round_number += 1
        self.phase = GamePhase.COLLECT
        self.current_player_index = self.first_player_index

        for player in self.players:
            player.has_passed = False

    def begin_action_phase(self) -> None:
        assert self.phase == GamePhase.COLLECT, self.phase
        self.phase = GamePhase.ACTIONS
        self.current_player_index = self.first_player_index

        self.pending_turn_advance = False

    def begin_victory_check(self) -> None:
        assert self.phase == GamePhase.ACTIONS, self.phase
        self.phase = GamePhase.VICTORY_CHECK

    def set_winner(self, player_ids: list[PlayerId]) -> None:
        self.winner_mask = 0
        for pid in player_ids:
            self.winner_mask |= 1 << pid

        self.phase = GamePhase.GAME_OVER

    def find_component_power(
        self,
        pid: PlayerId,
        entity_id: EntityId,
        power_index: int | None,
    ) -> tuple[
        ComponentType | None,
        EntityId | None,
        EntityData | None,
        Power | None,
    ]:
        if entity_id < 0 or entity_id >= len(self.entities):
            return (None, None, None, None)

        entity = self.entities[entity_id]

        if entity.owner_id != pid and entity.location != CardLocation.AVAILABLE:
            return (None, None, None, None)

        if entity.location != CardLocation.IN_PLAY:
            return (None, None, None, None)

        if power_index is not None and power_index < len(entity.data.powers):
            return (
                entity.kind,
                entity_id,
                entity.data,
                entity.data.powers[power_index],
            )

        return (entity.kind, entity_id, entity.data, None)

    def get_straightened_of_type(self, pid: PlayerId, turnable_type: TurnableType) -> list[EntityId]:
        result: list[EntityId] = []
        for eid in self.get_player_artifacts_in_play(pid):
            art = self.entities[eid]
            if art.is_turned or not art.data:
                continue
            match turnable_type:
                case TurnableType.DRAGON:
                    if art.data.is_dragon:
                        result.append(eid)
                case TurnableType.CREATURE:
                    if art.data.is_creature:
                        result.append(eid)
                case TurnableType.MAGE:
                    pass
        return result

    def get_magic_item_selection_player(self) -> int | None:
        claimed = 0
        for _eid, item in self.iter_magic_items():
            if item.location == CardLocation.IN_PLAY:
                claimed += 1

        if claimed >= self.num_players:
            return None

        return (self.first_player_index - 1 - claimed + self.num_players) % self.num_players


def create_game(
    db: CardDatabase,
    num_players: int,
    expansions: frozenset[ExpansionCode] = EXPANSIONS_BASE,
) -> GameState:
    assert expansions == EXPANSIONS_BASE, f"Only base expansion supported: {expansions}"
    assert num_players in (1, 2), num_players

    players: list[PlayerState] = []
    for i in range(num_players):
        pool = Pool(values=[1, 1, 1, 1, 1])
        players.append(PlayerState(pid=PlayerId(i), is_active=True, pool=pool))

    state = GameState(
        num_players=num_players,
        expansions=expansions,
        first_player_index=PlayerId(0),
        entities=[],
        artifact_range=(0, 0),
        mage_range=(0, 0),
        magic_item_range=(0, 0),
        monument_range=(0, 0),
        pop_range=(0, 0),
        players=players,
        phase=GamePhase.SETUP_GAME,
        round_number=0,
        temp_vp=[0] * num_players,
    )

    state.pending_stack.append(PendingGameSetupChoice())

    return state
