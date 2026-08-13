from __future__ import annotations

from dataclasses import dataclass

from ..action_types import UNOWNED, PlayerId
from ..card_location import CardLocation
from ..component_type import ComponentType
from ..entity_data import UNKNOWN_ORDER, Entity
from ..game_phase import GamePhase
from ..pending_choices import PendingGameSetupChoice
from ..pool import Pool
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionResolveGameSetup:

    pid: PlayerId
    places_of_power: tuple[str, ...]
    monument_display: tuple[str, ...]
    monument_deck: tuple[str, ...]
    mage_options: tuple[tuple[str, ...], ...]
    first_player: int
    artifact_decks: tuple[tuple[str, ...], ...]

    starting_essences: tuple[Pool, ...] | None = None

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state
        db = ctx.engine.db

        assert state.phase == GamePhase.SETUP_GAME, state.phase

        choice_idx: int | None = None
        for i, c in enumerate(state.pending_stack):
            if isinstance(c, PendingGameSetupChoice):
                choice_idx = i
                break
        assert choice_idx is not None

        all_mage_names: list[str] = []
        for _pid, mage_names in enumerate(self.mage_options):
            for mage_name in mage_names:
                if mage_name.startswith("?"):
                    continue
                assert mage_name not in all_mage_names, mage_name
                all_mage_names.append(mage_name)
                _, mage_data = db.get_mage(mage_name)
                assert mage_data.expansion in state.expansions, (
                    mage_name,
                    mage_data.expansion,
                )

        seen_pops: set[str] = set()
        for pop_name in self.places_of_power:
            assert pop_name not in seen_pops, pop_name
            seen_pops.add(pop_name)
            _, pop_data = db.get_place_of_power(pop_name)
            assert pop_data.expansion in state.expansions, (
                pop_name,
                pop_data.expansion,
            )

        seen_monuments: set[str] = set()
        for mon_name in self.monument_display:
            assert mon_name not in seen_monuments, mon_name
            seen_monuments.add(mon_name)
            _, mon_data = db.get_monument(mon_name)
            assert mon_data.expansion in state.expansions, (
                mon_name,
                mon_data.expansion,
            )
        for mon_name in self.monument_deck:
            if mon_name.startswith("?"):
                continue
            assert mon_name not in seen_monuments, mon_name
            seen_monuments.add(mon_name)
            _, mon_data = db.get_monument(mon_name)
            assert mon_data.expansion in state.expansions, (
                mon_name,
                mon_data.expansion,
            )

        seen_artifacts: set[str] = set()
        for _pid, artifact_names in enumerate(self.artifact_decks):
            for artifact_name in artifact_names:
                if artifact_name.startswith("?"):
                    continue
                assert artifact_name not in seen_artifacts, artifact_name
                seen_artifacts.add(artifact_name)
                _, artifact_data = db.get_artifact(artifact_name)
                assert artifact_data.expansion in state.expansions, (
                    artifact_name,
                    artifact_data.expansion,
                )

        artifacts: list[Entity] = []
        mages: list[Entity] = []
        magic_items: list[Entity] = []
        monuments: list[Entity] = []
        places_of_power: list[Entity] = []

        for pop_name in self.places_of_power:
            _, card_data = db.get_place_of_power(pop_name)
            entity = Entity(
                kind=ComponentType.PLACE_OF_POWER,
                data=card_data,
                location=CardLocation.AVAILABLE,
                owner_id=UNOWNED,
                is_turned=False,
            )
            places_of_power.append(entity)

        for _i, mon_name in enumerate(self.monument_display):
            _, card_data = db.get_monument(mon_name)
            entity = Entity(
                kind=ComponentType.MONUMENT,
                data=card_data,
                location=CardLocation.AVAILABLE,
                owner_id=UNOWNED,
                is_turned=False,
            )
            monuments.append(entity)

        for _i, mon_name in enumerate(self.monument_deck):
            _, card_data = db.get_monument(mon_name)
            entity = Entity(
                kind=ComponentType.MONUMENT,
                data=card_data,
                location=CardLocation.MONUMENT_DECK,
                owner_id=UNOWNED,
                is_turned=False,
                order_index=UNKNOWN_ORDER,
            )
            monuments.append(entity)

        for card_data in db.magic_items:
            if card_data.expansion in state.expansions:
                entity = Entity(
                    kind=ComponentType.MAGIC_ITEM,
                    data=card_data,
                    location=CardLocation.AVAILABLE,
                    owner_id=UNOWNED,
                    is_turned=False,
                )
                magic_items.append(entity)

        for pid, mage_names in enumerate(self.mage_options):
            for mage_name in mage_names:
                _, card_data = db.get_mage(mage_name)
                entity = Entity(
                    kind=ComponentType.MAGE,
                    data=card_data,
                    location=CardLocation.BEING_CHOSEN,
                    owner_id=PlayerId(pid),
                    is_turned=False,
                )
                mages.append(entity)

        for pid, artifact_names in enumerate(self.artifact_decks):
            for i, artifact_name in enumerate(artifact_names):
                _, card_data = db.get_artifact(artifact_name)
                location = CardLocation.HAND if i < 3 else CardLocation.DECK
                entity = Entity(
                    kind=ComponentType.ARTIFACT,
                    data=card_data,
                    location=location,
                    owner_id=PlayerId(pid),
                    is_turned=False,
                )
                artifacts.append(entity)

        entities: list[Entity] = []

        artifact_start = len(entities)
        entities.extend(artifacts)
        artifact_end = len(entities)

        mage_start = len(entities)
        entities.extend(mages)
        mage_end = len(entities)

        magic_item_start = len(entities)
        entities.extend(magic_items)
        magic_item_end = len(entities)

        monument_start = len(entities)
        entities.extend(monuments)
        monument_end = len(entities)

        pop_start = len(entities)
        entities.extend(places_of_power)
        pop_end = len(entities)

        state.set_entities(
            entities=entities,
            artifact_range=(artifact_start, artifact_end),
            mage_range=(mage_start, mage_end),
            magic_item_range=(magic_item_start, magic_item_end),
            monument_range=(monument_start, monument_end),
            pop_range=(pop_start, pop_end),
        )

        state.current_player_index = PlayerId(self.first_player)
        state.first_player_index = PlayerId(self.first_player)
        for i, player in enumerate(state.players):
            player.has_first_player_token = i == self.first_player

        if self.starting_essences is not None:
            for pid, pool in enumerate(self.starting_essences):
                if pid < len(state.players):
                    state.players[pid].pool = pool

        state.pending_stack.pop(choice_idx)

        state.phase = GamePhase.SETUP_CHOOSE_MAGES
