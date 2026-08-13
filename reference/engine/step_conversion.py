from __future__ import annotations

from .action_handlers.action_claim_top_monument import ActionClaimTopMonument
from .action_handlers.action_resolve_draw import ActionResolveDrawReveal
from .action_handlers.action_resolve_game_setup import ActionResolveGameSetup
from .action_handlers.action_resolve_monument_draw import ActionResolveMonumentDraw
from .action_handlers.action_resolve_monument_reveal import ActionResolveMonumentReveal
from .action_handlers.action_resolve_scry_reveal import ActionResolveScryReveal
from .action_types import EntityId, PlayerId
from .actions import (
    Action,
    ActionChooseMage,
    ActionChooseMagicItem,
    ActionClaimMonument,
    ActionClaimPlaceOfPower,
    ActionCollectCost,
    ActionDecline,
    ActionDiscardChoice,
    ActionDiscardForEssences,
    ActionGain,
    ActionLifeLossChoice,
    ActionLifeLossReact,
    ActionPass,
    ActionPlaceArtifact,
    ActionScryChoice,
    ActionScryDeckChoice,
    ActionTakeStored,
    ActionUsePower,
    ActionVictoryReact,
)
from .card_location import CardLocation
from .component_type import ComponentType
from .game_state import GameState
from .pool import Pool
from .steps import (
    ChooseMage,
    ChooseMagicItem,
    ClaimMonument,
    ClaimPlaceOfPower,
    ClaimTopMonument,
    CollectCost,
    Decline,
    DiscardChoice,
    DiscardForEssences,
    Gain,
    LifeLossChoice,
    LifeLossReact,
    Pass,
    PlaceArtifact,
    ResolveDrawReveal,
    ResolveGameSetup,
    ResolveMonumentDraw,
    ResolveMonumentReveal,
    ResolveScryReveal,
    ScryChoice,
    ScryDeckChoice,
    Step,
    TakeStored,
    UsePower,
    VictoryReact,
)


def resolve(state: GameState, name: str) -> EntityId:
    for eid, entity in state.iter_entities():
        if entity.data and entity.data.name == name:
            return eid
    raise ValueError(f"Card '{name}' not found in game state")


def resolve_optional(state: GameState, name: str | None) -> EntityId | None:
    if name is None:
        return None
    return resolve(state, name)


def find_by_name(
    state: GameState,
    name: str,
    component_type: ComponentType,
    location: CardLocation | None = None,
    owner_id: PlayerId | None = None,
) -> EntityId:
    for eid, entity in state.iter_entities(component_type, location=location, owner_id=owner_id):
        if entity.data and entity.data.name == name:
            return eid
    raise ValueError(f"'{name}' not found")


def find_card_in_deck(state: GameState, pid: PlayerId, name: str) -> EntityId:
    for eid in state.get_player_deck(pid):
        entity = state.entities[eid]
        if entity.data and entity.data.name == name:
            return eid
    for eid in state.get_player_discard(pid):
        entity = state.entities[eid]
        if entity.data and entity.data.name == name:
            return eid
    raise ValueError(f"Card '{name}' not found in player {pid}'s deck or discard")


def setup_step_to_action(setup: ResolveGameSetup) -> Action:
    from .action_handlers.action_resolve_game_setup import ActionResolveGameSetup

    return ActionResolveGameSetup(
        pid=PlayerId(0),
        places_of_power=setup.places_of_power,
        monument_display=setup.monument_display,
        monument_deck=setup.monument_deck,
        mage_options=setup.mage_options,
        first_player=setup.first_player,
        artifact_decks=setup.artifact_decks if setup.artifact_decks is not None else (),
        starting_essences=setup.starting_essences,
    )


def step_to_action(state: GameState, step: Step) -> Action:
    match step:
        case UsePower(
            card_name,
            power_index,
            player_id,
            target_name,
            target_player_id,
            pay,
            gain,
        ):
            return ActionUsePower(
                pid=PlayerId(player_id),
                eid=resolve(state, card_name),
                power_index=power_index,
                target_eid=resolve_optional(state, target_name),
                target_pid=(PlayerId(target_player_id) if target_player_id is not None else None),
                pay=pay or Pool(),
                gain=gain or Pool(),
            )
        case PlaceArtifact(artifact_name, pay, player_id):
            entity_id: EntityId | None = None
            for eid, art in state.iter_entities(ComponentType.ARTIFACT):
                if art.data and art.data.name == artifact_name:
                    if (
                        art.owner_id == player_id and art.location == CardLocation.HAND
                    ) or art.location == CardLocation.DISCARD:
                        entity_id = eid
                        break
            assert entity_id is not None, f"Artifact '{artifact_name}' not found"
            return ActionPlaceArtifact(
                pid=PlayerId(player_id),
                eid=entity_id,
                pay=pay,
            )
        case Decline(card_name, player_id):
            return ActionDecline(pid=PlayerId(player_id), eid=resolve(state, card_name))
        case ClaimMonument(monument_name, player_id):
            monument_eid: EntityId | None = None
            for eid, entity in state.iter_entities(ComponentType.MONUMENT):
                if (
                    entity.data
                    and entity.data.name == monument_name
                    and entity.location in (CardLocation.AVAILABLE, CardLocation.MONUMENT_DECK)
                ):
                    monument_eid = eid
                    break
            assert monument_eid is not None, f"Monument '{monument_name}' not found"
            return ActionClaimMonument(pid=PlayerId(player_id), eid=monument_eid)
        case ClaimTopMonument(player_id):
            return ActionClaimTopMonument(pid=PlayerId(player_id))
        case ResolveMonumentDraw(monument_name, player_id):
            return ActionResolveMonumentDraw(
                pid=PlayerId(player_id),
                eid=find_by_name(
                    state,
                    monument_name,
                    ComponentType.MONUMENT,
                    CardLocation.MONUMENT_DECK,
                ),
            )
        case ResolveMonumentReveal(monument_name, player_id):
            return ActionResolveMonumentReveal(
                pid=PlayerId(player_id),
                eid=find_by_name(
                    state,
                    monument_name,
                    ComponentType.MONUMENT,
                    CardLocation.MONUMENT_DECK,
                ),
            )
        case ClaimPlaceOfPower(pop_name, pay, player_id):
            return ActionClaimPlaceOfPower(
                pid=PlayerId(player_id),
                eid=find_by_name(
                    state,
                    pop_name,
                    ComponentType.PLACE_OF_POWER,
                    CardLocation.AVAILABLE,
                ),
                pay=pay,
            )
        case DiscardForEssences(card_name, gain, player_id):
            return ActionDiscardForEssences(
                pid=PlayerId(player_id),
                eid=resolve(state, card_name),
                gain=gain,
            )
        case Pass(item_name, player_id):
            new_magic_item_eid = find_by_name(state, item_name, ComponentType.MAGIC_ITEM, CardLocation.AVAILABLE)
            return ActionPass(pid=PlayerId(player_id), new_magic_item_eid=new_magic_item_eid)
        case LifeLossReact(
            card_name,
            power_index,
            player_id,
            target_name,
            pay,
            gain,
        ):
            return ActionLifeLossReact(
                pid=PlayerId(player_id),
                eid=resolve(state, card_name),
                power_index=power_index,
                target_eid=resolve_optional(state, target_name),
                pay=pay or Pool(),
                gain=gain or Pool(),
            )
        case VictoryReact(card_name, power_index, player_id, target_name, pay):
            return ActionVictoryReact(
                pid=PlayerId(player_id),
                eid=resolve(state, card_name),
                power_index=power_index,
                target_eid=resolve_optional(state, target_name),
                pay=pay or Pool(),
            )
        case LifeLossChoice(player_id, pay):
            return ActionLifeLossChoice(
                pid=PlayerId(player_id),
                pay=pay or Pool(),
            )
        case TakeStored(card_name, player_id, decision):
            return ActionTakeStored(
                pid=PlayerId(player_id),
                target_eid=resolve(state, card_name),
                decision=decision,
            )
        case CollectCost(card_name, player_id, decision):
            return ActionCollectCost(
                pid=PlayerId(player_id),
                eid=resolve(state, card_name),
                decision=decision,
            )
        case Gain(card_name, gain, player_id, use_alt):
            return ActionGain(
                pid=PlayerId(player_id),
                source_eid=resolve(state, card_name),
                gain=gain,
                use_alt=use_alt,
            )
        case ScryDeckChoice(player_id, scry_target):
            return ActionScryDeckChoice(pid=PlayerId(player_id), scry_target=scry_target)
        case ScryChoice(player_id, scry_order):
            return ActionScryChoice(pid=PlayerId(player_id), scry_order=scry_order)
        case DiscardChoice(card_names, player_id):
            eids = tuple(resolve(state, name) for name in card_names)
            return ActionDiscardChoice(pid=PlayerId(player_id), eids=eids)
        case ChooseMage(mage_name, player_id):
            mage_eid = find_by_name(
                state,
                mage_name,
                ComponentType.MAGE,
                CardLocation.BEING_CHOSEN,
                PlayerId(player_id),
            )
            return ActionChooseMage(pid=PlayerId(player_id), eid=mage_eid)
        case ChooseMagicItem(item_name, player_id):
            item_eid = find_by_name(state, item_name, ComponentType.MAGIC_ITEM, CardLocation.AVAILABLE)
            return ActionChooseMagicItem(pid=PlayerId(player_id), eid=item_eid)
        case ResolveDrawReveal(known_cards, revealed_cards, player_id):
            known = tuple(find_card_in_deck(state, PlayerId(player_id), name) for name in known_cards)
            revealed = tuple(find_card_in_deck(state, PlayerId(player_id), name) for name in revealed_cards)
            return ActionResolveDrawReveal(
                pid=PlayerId(player_id),
                known_eids=known,
                revealed_eids=revealed,
            )
        case ResolveScryReveal(revealed_cards, player_id):
            revealed_eids = tuple(resolve(state, name) for name in revealed_cards)
            return ActionResolveScryReveal(pid=PlayerId(player_id), revealed_eids=revealed_eids)
        case other:
            raise ValueError(f"Unknown step type: {type(other).__name__}")


def _entity_name(state: GameState, eid: EntityId) -> str:
    return state.entities[eid].data.name


def _entity_name_or_none(state: GameState, eid: EntityId | None) -> str | None:
    if eid is None:
        return None
    return _entity_name(state, eid)


def action_to_step(action: Action, state: GameState) -> Step:
    match action:
        case ActionPass():
            return Pass(_entity_name(state, action.new_magic_item_eid), player_id=action.pid)
        case ActionUsePower():
            return UsePower(
                _entity_name(state, action.eid),
                power_index=action.power_index,
                player_id=action.pid,
                target_name=_entity_name_or_none(state, action.target_eid),
                target_player_id=action.target_pid,
                pay=action.pay,
                gain=action.gain,
            )
        case ActionPlaceArtifact():
            return PlaceArtifact(
                _entity_name(state, action.eid),
                action.pay,
                player_id=action.pid,
            )
        case ActionClaimMonument():
            return ClaimMonument(_entity_name(state, action.eid), player_id=action.pid)
        case ActionClaimTopMonument():
            return ClaimTopMonument(player_id=action.pid)
        case ActionResolveMonumentDraw():
            return ResolveMonumentDraw(_entity_name(state, action.eid), player_id=action.pid)
        case ActionClaimPlaceOfPower():
            return ClaimPlaceOfPower(
                _entity_name(state, action.eid),
                action.pay,
                player_id=action.pid,
            )
        case ActionDiscardForEssences():
            return DiscardForEssences(
                _entity_name(state, action.eid),
                action.gain,
                player_id=action.pid,
            )
        case ActionLifeLossReact():
            return LifeLossReact(
                _entity_name(state, action.eid),
                power_index=action.power_index,
                player_id=action.pid,
                target_name=_entity_name_or_none(state, action.target_eid),
                pay=action.pay,
                gain=action.gain,
            )
        case ActionVictoryReact():
            return VictoryReact(
                _entity_name(state, action.eid),
                power_index=action.power_index,
                player_id=action.pid,
                target_name=_entity_name_or_none(state, action.target_eid),
                pay=action.pay,
            )
        case ActionLifeLossChoice():
            return LifeLossChoice(player_id=action.pid, pay=action.pay)
        case ActionTakeStored():
            return TakeStored(
                _entity_name(state, action.target_eid),
                player_id=action.pid,
                decision=action.decision,
            )
        case ActionCollectCost():
            return CollectCost(
                _entity_name(state, action.eid),
                player_id=action.pid,
                decision=action.decision,
            )
        case ActionGain():
            return Gain(
                _entity_name(state, action.source_eid),
                action.gain,
                player_id=action.pid,
                use_alt=action.use_alt,
            )
        case ActionResolveDrawReveal():
            known = [_entity_name(state, eid) for eid in action.known_eids]
            revealed = [_entity_name(state, eid) for eid in action.revealed_eids]
            return ResolveDrawReveal(known_cards=known, revealed_cards=revealed, player_id=action.pid)
        case ActionDiscardChoice():
            names = tuple(_entity_name(state, eid) for eid in action.eids)
            return DiscardChoice(*names, player_id=action.pid)
        case ActionScryDeckChoice():
            return ScryDeckChoice(player_id=action.pid, scry_target=action.scry_target)
        case ActionScryChoice():
            return ScryChoice(player_id=action.pid, scry_order=list(action.scry_order))
        case ActionResolveScryReveal():
            return ResolveScryReveal(
                [_entity_name(state, eid) for eid in action.revealed_eids],
                player_id=action.pid,
            )
        case ActionResolveMonumentReveal():
            return ResolveMonumentReveal(_entity_name(state, action.eid), player_id=action.pid)
        case ActionDecline():
            return Decline(_entity_name(state, action.eid), player_id=action.pid)
        case ActionChooseMage():
            return ChooseMage(_entity_name(state, action.eid), player_id=action.pid)
        case ActionChooseMagicItem():
            return ChooseMagicItem(_entity_name(state, action.eid), player_id=action.pid)
        case ActionResolveGameSetup():
            return ResolveGameSetup(
                places_of_power=action.places_of_power,
                monument_display=action.monument_display,
                monument_deck=action.monument_deck,
                mage_options=action.mage_options,
                first_player=action.first_player,
                artifact_decks=action.artifact_decks,
            )
        case _:
            raise ValueError(f"Unsupported action type: {type(action).__name__}")
