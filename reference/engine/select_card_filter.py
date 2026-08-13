from __future__ import annotations

from dataclasses import dataclass

from .component_type import ComponentType
from .entity_data import Entity
from .select_card_location import SelectCardLocation


@dataclass(frozen=True, slots=True)
class SelectCardFilter:

    location: SelectCardLocation = SelectCardLocation.NONE
    require_tapped: bool = False
    card_type_mask: int = 0
    own_cards_only: bool = True
    component_type_mask: int = 0
    exclude_self: bool = False

    def allows_component_type(self, comp_type: ComponentType) -> bool:
        if self.component_type_mask == 0:
            return True
        return bool(self.component_type_mask & (1 << comp_type))

    def has_filter(self) -> bool:
        return self.location != SelectCardLocation.NONE

    def matches_card_type_mask(self, entity_card_type_mask: int) -> bool:
        if self.card_type_mask == 0:
            return True
        return bool(self.card_type_mask & entity_card_type_mask)

    def matches_tapped_state(self, is_turned: bool) -> bool:
        if not self.require_tapped:
            return True
        return is_turned

    def should_include_component(self, comp_type: ComponentType) -> bool:
        match comp_type:
            case ComponentType.ARTIFACT:
                return self.allows_component_type(ComponentType.ARTIFACT)
            case ComponentType.MAGE:
                return self.allows_component_type(ComponentType.MAGE) or (
                    self.component_type_mask == 0 and self.card_type_mask == 0
                )
            case ComponentType.PLACE_OF_POWER | ComponentType.MONUMENT | ComponentType.MAGIC_ITEM:
                return self.component_type_mask == 0 and self.card_type_mask == 0

    def matches_entity(self, entity: Entity) -> bool:
        if not self.matches_tapped_state(entity.is_turned):
            return False

        if entity.kind == ComponentType.ARTIFACT:
            if not self.matches_card_type_mask(entity.data.card_type_mask):
                return False

        return True
