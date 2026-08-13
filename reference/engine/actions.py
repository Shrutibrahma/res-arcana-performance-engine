from __future__ import annotations

from .action_handlers import (
    ActionChooseMage,
    ActionChooseMagicItem,
    ActionClaimMonument,
    ActionClaimPlaceOfPower,
    ActionClaimTopMonument,
    ActionCollectCost,
    ActionContext,
    ActionDecline,
    ActionDiscardChoice,
    ActionDiscardForEssences,
    ActionGain,
    ActionLifeLossChoice,
    ActionLifeLossReact,
    ActionPass,
    ActionPlaceArtifact,
    ActionResolveDrawReveal,
    ActionResolveGameSetup,
    ActionResolveMonumentDraw,
    ActionResolveMonumentReveal,
    ActionResolveScryReveal,
    ActionScryChoice,
    ActionScryDeckChoice,
    ActionTakeStored,
    ActionUsePower,
    ActionVictoryReact,
)
from .available_actions import AvailableAction
from .react_trigger import ReactTrigger

__all__ = [
    "Action",
    "ActionChooseMage",
    "ActionChooseMagicItem",
    "ActionClaimMonument",
    "ActionClaimPlaceOfPower",
    "ActionClaimTopMonument",
    "ActionCollectCost",
    "ActionContext",
    "ActionDecline",
    "ActionDiscardChoice",
    "ActionDiscardForEssences",
    "ActionGain",
    "ActionLifeLossChoice",
    "ActionLifeLossReact",
    "ActionPass",
    "ActionPlaceArtifact",
    "ActionResolveDrawReveal",
    "ActionResolveGameSetup",
    "ActionResolveMonumentDraw",
    "ActionResolveMonumentReveal",
    "ActionResolveScryReveal",
    "ActionScryChoice",
    "ActionScryDeckChoice",
    "ActionTakeStored",
    "ActionUsePower",
    "ActionVictoryReact",
    "AvailableAction",
    "ReactTrigger",
]


Action = (
    ActionPlaceArtifact
    | ActionClaimMonument
    | ActionClaimTopMonument
    | ActionClaimPlaceOfPower
    | ActionDiscardForEssences
    | ActionUsePower
    | ActionPass
    | ActionVictoryReact
    | ActionLifeLossReact
    | ActionLifeLossChoice
    | ActionTakeStored
    | ActionScryDeckChoice
    | ActionScryChoice
    | ActionDiscardChoice
    | ActionChooseMage
    | ActionChooseMagicItem
    | ActionResolveDrawReveal
    | ActionResolveMonumentDraw
    | ActionResolveMonumentReveal
    | ActionResolveGameSetup
    | ActionResolveScryReveal
    | ActionCollectCost
    | ActionGain
    | ActionDecline
)
