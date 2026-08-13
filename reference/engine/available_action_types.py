from __future__ import annotations

from dataclasses import dataclass

from .action_handlers import (
    ActionChooseMage,
    ActionChooseMagicItem,
    ActionClaimMonument,
    ActionClaimPlaceOfPower,
    ActionClaimTopMonument,
    ActionCollectCost,
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
from .action_types import EntityId, PlayerId
from .collect_decision import CollectDecision
from .deck_type import DeckType
from .essence import Essence
from .pool import Pool
from .target_option import TargetOption


@dataclass(frozen=True)
class AvailableActionPlaceArtifact:

    eid: EntityId
    pay: Pool

    def to_action(self, pid: PlayerId) -> ActionPlaceArtifact:
        return ActionPlaceArtifact(
            pid=pid,
            eid=self.eid,
            pay=self.pay,
        )


@dataclass(frozen=True)
class AvailableActionClaimMonument:

    eid: EntityId

    def to_action(self, pid: PlayerId) -> ActionClaimMonument:
        return ActionClaimMonument(pid=pid, eid=self.eid)


@dataclass(frozen=True)
class AvailableActionClaimTopMonument:

    def to_action(self, pid: PlayerId) -> ActionClaimTopMonument:
        return ActionClaimTopMonument(pid=pid)


@dataclass(frozen=True)
class AvailableActionClaimPlaceOfPower:

    eid: EntityId
    pay: Pool

    def to_action(self, pid: PlayerId) -> ActionClaimPlaceOfPower:
        return ActionClaimPlaceOfPower(
            pid=pid,
            eid=self.eid,
            pay=self.pay,
        )


@dataclass(frozen=True)
class AvailableActionDiscardForEssences:

    eid: EntityId

    def to_action(self, pid: PlayerId, gain: Pool) -> ActionDiscardForEssences:
        return ActionDiscardForEssences(
            pid=pid,
            eid=self.eid,
            gain=gain,
        )


@dataclass(frozen=True)
class AvailableActionUsePower:

    eid: EntityId
    power_index: int
    target_entities: tuple[EntityId, ...] = ()

    def to_action(
        self,
        pid: PlayerId,
        target_id: EntityId | None = None,
        target_pid: PlayerId | None = None,
        pay: Pool | None = None,
        gain: Pool | None = None,
    ) -> ActionUsePower:
        return ActionUsePower(
            pid=pid,
            eid=self.eid,
            power_index=self.power_index,
            target_eid=target_id,
            target_pid=target_pid,
            pay=pay if pay is not None else Pool(),
            gain=gain if gain is not None else Pool(),
        )


@dataclass(frozen=True)
class AvailableActionPass:

    new_magic_item_eid: EntityId

    def to_action(self, pid: PlayerId) -> ActionPass:
        return ActionPass(pid=pid, new_magic_item_eid=self.new_magic_item_eid)


@dataclass(frozen=True)
class AvailableActionVictoryReact:

    eid: EntityId
    power_index: int

    def to_action(
        self,
        pid: PlayerId,
        target_id: EntityId | None = None,
        pay: Pool | None = None,
    ) -> ActionVictoryReact:
        return ActionVictoryReact(
            pid=pid,
            eid=self.eid,
            power_index=self.power_index,
            target_eid=target_id,
            pay=pay if pay is not None else Pool(),
        )


@dataclass(frozen=True)
class AvailableActionLifeLossReact:

    eid: EntityId
    power_index: int
    defense_option_index: int | None = None

    def to_action(
        self,
        pid: PlayerId,
        target_id: EntityId | None = None,
        pay: Pool | None = None,
        gain: Pool | None = None,
    ) -> ActionLifeLossReact:
        return ActionLifeLossReact(
            pid=pid,
            eid=self.eid,
            power_index=self.power_index,
            target_eid=target_id,
            pay=pay if pay is not None else Pool(),
            gain=gain if gain is not None else Pool(),
        )


@dataclass(frozen=True)
class AvailableActionLifeLossChoice:

    payment_options: tuple[TargetOption, ...] = ()

    def to_action(self, pid: PlayerId, pay: Pool | None = None) -> ActionLifeLossChoice:
        return ActionLifeLossChoice(pid=pid, pay=pay if pay is not None else Pool())


@dataclass(frozen=True)
class AvailableActionTakeStored:

    eid: EntityId
    action_options: tuple[TargetOption, ...] = ()

    def to_action(self, pid: PlayerId, decision: CollectDecision) -> ActionTakeStored:
        return ActionTakeStored(pid=pid, target_eid=self.eid, decision=decision)


@dataclass(frozen=True)
class AvailableActionScryDeckChoice:

    deck_options: tuple[DeckType, ...] = ()

    def to_action(self, pid: PlayerId, scry_target: DeckType) -> ActionScryDeckChoice:
        return ActionScryDeckChoice(pid=pid, scry_target=scry_target)


@dataclass(frozen=True)
class AvailableActionScryChoice:

    scry_indices: tuple[int, ...] = ()

    def to_action(self, pid: PlayerId, scry_order: list[int]) -> ActionScryChoice:
        return ActionScryChoice(pid=pid, scry_order=scry_order)


@dataclass(frozen=True)
class AvailableActionDiscardChoice:

    discard_count: int

    def to_action(self, pid: PlayerId, eids: tuple[EntityId, ...]) -> ActionDiscardChoice:
        return ActionDiscardChoice(pid=pid, eids=eids)


@dataclass(frozen=True)
class AvailableActionChooseMage:

    eid: EntityId

    def to_action(self, pid: PlayerId) -> ActionChooseMage:
        return ActionChooseMage(pid=pid, eid=self.eid)


@dataclass(frozen=True)
class AvailableActionChooseMagicItem:

    eid: EntityId

    def to_action(self, pid: PlayerId) -> ActionChooseMagicItem:
        return ActionChooseMagicItem(pid=pid, eid=self.eid)


@dataclass(frozen=True)
class AvailableActionResolveDrawReveal:

    revealed_eids: tuple[EntityId, ...]
    known_eids: tuple[EntityId, ...] = ()

    def to_action(self, pid: PlayerId) -> ActionResolveDrawReveal:
        return ActionResolveDrawReveal(pid=pid, revealed_eids=self.revealed_eids, known_eids=self.known_eids)


@dataclass(frozen=True)
class AvailableActionResolveMonumentDraw:

    eid: EntityId

    def to_action(self, pid: PlayerId) -> ActionResolveMonumentDraw:
        return ActionResolveMonumentDraw(pid=pid, eid=self.eid)


@dataclass(frozen=True)
class AvailableActionResolveMonumentReveal:

    eid: EntityId

    def to_action(self, pid: PlayerId) -> ActionResolveMonumentReveal:
        return ActionResolveMonumentReveal(pid=pid, eid=self.eid)


@dataclass(frozen=True)
class AvailableActionResolveGameSetup:

    def to_action(
        self,
        pid: PlayerId,
        places_of_power: tuple[str, ...],
        monument_display: tuple[str, ...],
        monument_deck: tuple[str, ...],
        mage_options: tuple[tuple[str, ...], ...],
        first_player: int,
        artifact_decks: tuple[tuple[str, ...], ...],
    ) -> ActionResolveGameSetup:
        return ActionResolveGameSetup(
            pid=pid,
            places_of_power=places_of_power,
            monument_display=monument_display,
            monument_deck=monument_deck,
            mage_options=mage_options,
            first_player=first_player,
            artifact_decks=artifact_decks,
        )


@dataclass(frozen=True)
class AvailableActionResolveScryReveal:

    revealed_eids: tuple[EntityId, ...]

    def to_action(self, pid: PlayerId) -> ActionResolveScryReveal:
        return ActionResolveScryReveal(pid=pid, revealed_eids=self.revealed_eids)


@dataclass(frozen=True)
class AvailableActionCollectCost:

    eid: EntityId
    cost_options: tuple[TargetOption, ...] = ()

    def to_action(self, pid: PlayerId, decision: CollectDecision) -> ActionCollectCost:
        return ActionCollectCost(pid=pid, eid=self.eid, decision=decision)


@dataclass(frozen=True)
class AvailableActionGain:

    source_eid: EntityId
    amount: int
    valid_essences: tuple[Essence, ...] = ()
    alt_amount: int = 0

    def to_action(self, pid: PlayerId, gain: Pool, use_alt: bool = False) -> ActionGain:
        return ActionGain(
            pid=pid,
            source_eid=self.source_eid,
            gain=gain,
            use_alt=use_alt,
        )


@dataclass(frozen=True)
class AvailableActionDecline:

    eid: EntityId

    def to_action(self, pid: PlayerId) -> ActionDecline:
        return ActionDecline(pid=pid, eid=self.eid)


AvailableAction = (
    AvailableActionPlaceArtifact
    | AvailableActionClaimMonument
    | AvailableActionClaimTopMonument
    | AvailableActionClaimPlaceOfPower
    | AvailableActionDiscardForEssences
    | AvailableActionUsePower
    | AvailableActionPass
    | AvailableActionVictoryReact
    | AvailableActionLifeLossReact
    | AvailableActionLifeLossChoice
    | AvailableActionTakeStored
    | AvailableActionScryDeckChoice
    | AvailableActionScryChoice
    | AvailableActionDiscardChoice
    | AvailableActionChooseMage
    | AvailableActionChooseMagicItem
    | AvailableActionResolveDrawReveal
    | AvailableActionResolveMonumentDraw
    | AvailableActionResolveMonumentReveal
    | AvailableActionResolveGameSetup
    | AvailableActionResolveScryReveal
    | AvailableActionCollectCost
    | AvailableActionGain
    | AvailableActionDecline
)
