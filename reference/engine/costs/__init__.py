from ..destroy_mode import DestroyMode
from ..turnable_type import TurnableType
from .cost_destroy import CostDestroyComponent
from .cost_destroy_card_type import CostDestroyCardType
from .cost_discard import CostDiscardCard
from .cost_pay_essence import CostPayEssence
from .cost_pay_identical import CostPayIdentical
from .cost_remove_from_card import CostRemoveFromCard
from .cost_select_card import CostSelectCard
from .cost_select_player import CostSelectPlayer
from .cost_turn_component import CostTurnComponent

Cost = (
    CostTurnComponent
    | CostPayEssence
    | CostRemoveFromCard
    | CostPayIdentical
    | CostDestroyComponent
    | CostDestroyCardType
    | CostDiscardCard
    | CostSelectPlayer
    | CostSelectCard
)

__all__ = [
    "Cost",
    "CostDestroyCardType",
    "CostDestroyComponent",
    "CostDiscardCard",
    "CostPayEssence",
    "CostPayIdentical",
    "CostRemoveFromCard",
    "CostSelectCard",
    "CostSelectPlayer",
    "CostTurnComponent",
    "DestroyMode",
    "TurnableType",
]
