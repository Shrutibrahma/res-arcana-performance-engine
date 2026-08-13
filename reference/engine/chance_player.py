from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol, cast

from .action_handlers.action_resolve_game_setup import ActionResolveGameSetup
from .action_types import PlayerId
from .actions import Action
from .card_database import CardDatabase
from .game_state import GameState
from .models import (
    ARTIFACTS_PER_PLAYER,
    MAGES_PER_PLAYER_SETUP,
    SETUP_SCALING,
)


class ChancePlayer(Protocol):
    def choose(self, state: GameState, actions: list[Action]) -> Action: ...


@dataclass
class RNGChancePlayer:
    rng: random.Random

    def choose(self, state: GameState, actions: list[Action]) -> Action:
        assert actions, "No actions to choose from"
        return self.rng.choice(actions)

    def get_state(self) -> tuple[object, ...]:
        return self.rng.getstate()

    def set_state(self, rng_state: tuple[object, ...]) -> None:

        self.rng.setstate(cast(tuple[int, tuple[int, ...], float | None], rng_state))

    def _select(self, population: list[int], k: int) -> list[int]:
        result: list[int] = []
        n = len(population)
        for i, item in enumerate(population):
            remaining = n - i
            needed = k - len(result)
            if needed <= 0:
                break
            if self.rng.random() < needed / remaining:
                result.append(item)
        return result

    def generate_game_setup(
        self,
        state: GameState,
        db: CardDatabase,
    ) -> ActionResolveGameSetup:
        num_players = state.num_players

        monuments_count, pops_count = SETUP_SCALING[num_players]

        num_pairings = len(db.places_of_power) // 2
        pairing_indices = list(range(num_pairings))
        selected_pairings = self._select(pairing_indices, min(pops_count, len(pairing_indices)))

        pops: list[str] = []
        for pairing_idx in selected_pairings:
            card_idx = 2 * pairing_idx if self.rng.random() < 0.5 else 2 * pairing_idx + 1
            pops.append(db.places_of_power[card_idx].name)

        monument_indices = list(range(len(db.monuments)))
        selected_monuments = self._select(monument_indices, min(monuments_count, len(monument_indices)))
        display_picks = set(self.rng.sample(range(len(selected_monuments)), min(2, len(selected_monuments))))
        display_monuments = [
            db.monuments[selected_monuments[i]].name for i in range(len(selected_monuments)) if i in display_picks
        ]
        deck_monuments = [
            db.monuments[selected_monuments[i]].name for i in range(len(selected_monuments)) if i not in display_picks
        ]

        mage_indices = list(range(len(db.mages)))
        self.rng.shuffle(mage_indices)

        mage_options: list[tuple[str, ...]] = []
        for pid in range(num_players):
            player_mages: list[str] = []
            for i in range(MAGES_PER_PLAYER_SETUP):
                idx = pid * MAGES_PER_PLAYER_SETUP + i
                if idx < len(mage_indices):
                    player_mages.append(db.mages[mage_indices[idx]].name)
            mage_options.append(tuple(player_mages))

        first_player = self.rng.randint(0, num_players - 1)

        remaining_artifacts = list(range(len(db.artifacts)))

        artifact_decks: list[tuple[str, ...]] = []
        for _pid in range(num_players):
            count = min(ARTIFACTS_PER_PLAYER, len(remaining_artifacts))
            player_indices = self._select(remaining_artifacts, count)
            selected_set = set(player_indices)
            remaining_artifacts = [x for x in remaining_artifacts if x not in selected_set]
            artifact_decks.append(tuple(db.artifacts[i].name for i in player_indices))

        return ActionResolveGameSetup(
            pid=PlayerId(0),
            places_of_power=tuple(pops),
            monument_display=tuple(display_monuments),
            monument_deck=tuple(deck_monuments),
            mage_options=tuple(mage_options),
            first_player=first_player,
            artifact_decks=tuple(artifact_decks),
        )
