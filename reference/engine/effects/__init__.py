from ..power_context import PowerContext
from .countable_component import CountableComponent
from .effect_check_victory import EffectCheckVictory
from .effect_damage import EffectDamage
from .effect_draw import EffectDraw
from .effect_gain import EffectGain
from .effect_gain_any import EffectGainAny
from .effect_gain_destroyed_cost import EffectGainDestroyedCost
from .effect_gain_from_opponent import EffectGainFromOpponent
from .effect_gain_gold_equal_to_same_spent import EffectGainGoldEqualToSameSpent
from .effect_gain_gold_from_cost import EffectGainGoldFromCost
from .effect_gain_same_type_as_spent import EffectGainSameTypeAsSpent
from .effect_ignore_damage import EffectIgnoreDamage
from .effect_place import EffectPlace
from .effect_rivals_gain import EffectRivalsGain
from .effect_scry import EffectScry
from .effect_store import EffectStore
from .effect_straighten import EffectStraighten
from .effect_temp_vp import EffectTempVP

Effect = (
    EffectGain
    | EffectGainAny
    | EffectStore
    | EffectRivalsGain
    | EffectDamage
    | EffectDraw
    | EffectIgnoreDamage
    | EffectCheckVictory
    | EffectStraighten
    | EffectScry
    | EffectPlace
    | EffectGainDestroyedCost
    | EffectGainGoldEqualToSameSpent
    | EffectGainFromOpponent
    | EffectGainSameTypeAsSpent
    | EffectTempVP
    | EffectGainGoldFromCost
)

__all__ = [
    "CountableComponent",
    "Effect",
    "EffectCheckVictory",
    "EffectDamage",
    "EffectDraw",
    "EffectGain",
    "EffectGainAny",
    "EffectGainDestroyedCost",
    "EffectGainFromOpponent",
    "EffectGainGoldEqualToSameSpent",
    "EffectGainGoldFromCost",
    "EffectGainSameTypeAsSpent",
    "EffectIgnoreDamage",
    "EffectPlace",
    "EffectRivalsGain",
    "EffectScry",
    "EffectStore",
    "EffectStraighten",
    "EffectTempVP",
    "PowerContext",
]
