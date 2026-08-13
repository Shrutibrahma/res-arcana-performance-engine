from __future__ import annotations

from dataclasses import dataclass

from .entity_data import EntityData


def validate_card_powers(card: EntityData) -> None:
    for idx, power in enumerate(card.powers):
        power.validate(idx)


@dataclass(frozen=True, slots=True)
class CardDatabase:

    artifacts: tuple[EntityData, ...] = ()
    mages: tuple[EntityData, ...] = ()
    magic_items: tuple[EntityData, ...] = ()
    monuments: tuple[EntityData, ...] = ()
    places_of_power: tuple[EntityData, ...] = ()

    def get_artifact(self, name: str) -> tuple[int, EntityData]:
        for i, art in enumerate(self.artifacts):
            if art.name == name:
                return (i, art)
        raise AssertionError(f"Artifact '{name}' not found")

    def get_mage(self, name: str) -> tuple[int, EntityData]:
        for i, mage in enumerate(self.mages):
            if mage.name == name:
                return (i, mage)
        raise AssertionError(f"Mage '{name}' not found")

    def get_monument(self, name: str) -> tuple[int, EntityData]:
        for i, mon in enumerate(self.monuments):
            if mon.name == name:
                return (i, mon)
        raise AssertionError(f"Monument '{name}' not found")

    def get_place_of_power(self, name: str) -> tuple[int, EntityData]:
        for i, pop in enumerate(self.places_of_power):
            if pop.name == name:
                return (i, pop)
        raise AssertionError(f"Place of Power '{name}' not found")

    def validate_all_powers(self) -> None:
        for card in self.artifacts:
            validate_card_powers(card)
        for card in self.mages:
            validate_card_powers(card)
        for card in self.magic_items:
            validate_card_powers(card)
        for card in self.monuments:
            validate_card_powers(card)
        for card in self.places_of_power:
            validate_card_powers(card)
