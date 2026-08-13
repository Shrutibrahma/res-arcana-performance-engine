from __future__ import annotations

from typing import TYPE_CHECKING

from . import affordability
from .action_types import (
    SENTINEL_EID,
    EntityId,
    PlayerId,
)
from .available_action_types import (
    AvailableAction,
    AvailableActionChooseMage,
    AvailableActionChooseMagicItem,
    AvailableActionClaimMonument,
    AvailableActionClaimPlaceOfPower,
    AvailableActionClaimTopMonument,
    AvailableActionCollectCost,
    AvailableActionDecline,
    AvailableActionDiscardChoice,
    AvailableActionDiscardForEssences,
    AvailableActionGain,
    AvailableActionLifeLossChoice,
    AvailableActionLifeLossReact,
    AvailableActionPass,
    AvailableActionPlaceArtifact,
    AvailableActionResolveDrawReveal,
    AvailableActionResolveGameSetup,
    AvailableActionResolveMonumentDraw,
    AvailableActionResolveMonumentReveal,
    AvailableActionResolveScryReveal,
    AvailableActionScryChoice,
    AvailableActionScryDeckChoice,
    AvailableActionTakeStored,
    AvailableActionUsePower,
    AvailableActionVictoryReact,
)
from .card_location import CardLocation
from .card_type import CardType
from .costs import (
    Cost,
    CostDestroyCardType,
    CostDestroyComponent,
    CostDiscardCard,
    CostPayEssence,
    CostPayIdentical,
    CostRemoveFromCard,
    CostSelectCard,
    CostSelectPlayer,
    CostTurnComponent,
    DestroyMode,
)
from .deck_type import DeckType
from .effects import EffectDamage, EffectDraw
from .entity_data import Entity
from .essence import Essence
from .game_phase import GamePhase
from .game_state import GameState
from .pending_choices import (
    PendingChoice,
    PendingCollectCost,
    PendingCollectPhaseCursor,
    PendingCollectStorage,
    PendingDiscardChoice,
    PendingDrawRevealChoice,
    PendingGain,
    PendingGameSetupChoice,
    PendingLifeLossChoice,
    PendingLifeLossScan,
    PendingMonumentDrawChoice,
    PendingMonumentRevealChoice,
    PendingPlacementChoice,
    PendingScryChoice,
    PendingScryDeckChoice,
    PendingScryRevealChoice,
    PendingVictoryReactChoice,
)
from .pool import Pool
from .power import Power
from .react_trigger import ReactTrigger
from .select_card_location import SelectCardLocation
from .target_option import TargetOption
from .turnable_type import TurnableType

if TYPE_CHECKING:
    from .game_engine import GameEngine


def _can_pay_cost(
    cost: Cost,
    state: GameState,
    pid: PlayerId,
    eid: EntityId,
    entity: Entity,
) -> bool:
    match cost:
        case CostPayEssence():
            pool = state.players[pid].pool
            if not pool.can_afford(cost.essences):
                return False
            if cost.any_amount == 0:
                return True
            available = pool.total() - cost.essences.total()
            for excl in cost.exclude:
                remaining_excl = pool[excl] - cost.essences[excl]
                if remaining_excl > 0:
                    available -= remaining_excl
            return available >= cost.any_amount

        case CostPayIdentical():
            pool = state.players[pid].pool
            min_total = cost.base_cost + cost.min_amount
            if pool.total() < min_total:
                return False
            if cost.essence_type is not None:
                return pool[cost.essence_type] >= cost.min_amount
            else:
                return max(pool) >= cost.min_amount

        case CostRemoveFromCard():
            if entity.essences_on_card is None:
                return False
            return entity.essences_on_card.can_afford(cost.essences)

        case CostDiscardCard():
            hand = state.get_player_hand(pid)
            for hand_eid in hand:
                entity = state.entities[hand_eid]
                if cost.exclude_entity_flags and (entity.data.entity_flags & cost.exclude_entity_flags):
                    continue
                if not cost.matches_type(entity.data):
                    continue
                return True
            return False

        case CostDestroyComponent():
            match cost.destroy_mode:
                case DestroyMode.SELF:
                    return True
                case DestroyMode.ANY:
                    return len(state.get_player_artifacts_in_play(pid)) > 0
                case DestroyMode.ANOTHER:
                    for art_eid in state.get_player_artifacts_in_play(pid):
                        if art_eid != eid:
                            return True
                    return False

        case CostDestroyCardType():
            for art_eid in state.get_player_artifacts_in_play(pid):
                art = state.entities[art_eid]
                if art.data and cost.matches_type(art.data):
                    return True
            return False

        case CostTurnComponent():
            if cost.turnable_type == TurnableType.MAGE:
                for _mage_id, mage in state.iter_mages():
                    if mage.location == CardLocation.IN_PLAY and mage.owner_id == pid:
                        return not mage.is_turned
                return False
            else:
                card_type = {
                    TurnableType.DRAGON: CardType.DRAGON,
                    TurnableType.CREATURE: CardType.CREATURE,
                }[cost.turnable_type]
                for art_eid in state.get_player_artifacts_in_play(pid):
                    art = state.entities[art_eid]
                    if art.data and art.data.card_type_mask & (1 << card_type) and not art.is_turned:
                        return True
                return False

        case CostSelectPlayer():
            if cost.opponent_only:
                return len(state.players) > 1
            return True

        case CostSelectCard():
            return True


def _can_pay_all_costs(
    state: GameState,
    pid: PlayerId,
    eid: EntityId,
    entity: Entity,
    power: Power,
) -> bool:
    assert not (power.requires_turn and entity.is_turned)
    return all(_can_pay_cost(cost, state, pid, eid, entity) for cost in power.costs)


def get_available_actions(engine: GameEngine, state: GameState, pid: PlayerId) -> list[AvailableAction]:
    if pid < 0 or pid >= state.num_players:
        return []

    if state.phase == GamePhase.GAME_OVER:
        return []

    player = state.players[pid]
    actions: list[AvailableAction] = []

    top_pending: PendingChoice | None = None
    if state.pending_stack:
        top = state.pending_stack[-1]
        if top.pid == pid:
            top_pending = top

    if top_pending is not None:
        match top_pending:
            case PendingDiscardChoice():
                actions.append(AvailableActionDiscardChoice(discard_count=top_pending.count))
                return actions

            case PendingScryDeckChoice():
                actions.append(
                    AvailableActionScryDeckChoice(
                        deck_options=(DeckType.ARTIFACT, DeckType.MONUMENT),
                    )
                )
                return actions

            case PendingScryChoice():
                actions.append(AvailableActionScryChoice(scry_indices=tuple(top_pending.card_eids)))
                return actions

            case PendingVictoryReactChoice():

                entity_id = top_pending.component_eid
                assert entity_id is not None
                entity = state.entities[entity_id]

                assert not entity.is_turned, entity_id
                powers_to_check: list[tuple[int, Power]] = []
                first_power = entity.data.powers[top_pending.power_index]
                powers_to_check.append((top_pending.power_index, first_power))

                for power_idx, power in powers_to_check:
                    essence_cost = power.get_cost(CostPayEssence)
                    can_afford = True
                    if essence_cost is not None:
                        assert isinstance(essence_cost, CostPayEssence)
                        if not player.pool.can_afford(essence_cost.essences):
                            can_afford = False

                    requires_target = power.requires_target()
                    valid_targets: list[EntityId] = []
                    if requires_target:
                        valid_targets = engine.get_valid_targets(state, pid, power, entity_id)
                        if not valid_targets:
                            can_afford = False

                    if can_afford:
                        actions.append(
                            AvailableActionVictoryReact(
                                eid=entity_id,
                                power_index=power_idx,
                            )
                        )

                actions.append(AvailableActionDecline(eid=entity_id))

                return actions

            case PendingLifeLossChoice():
                next_life_loss_player: int | None = None
                for c in reversed(state.pending_stack):
                    if isinstance(c, PendingLifeLossChoice):
                        next_life_loss_player = c.pid
                        break
                if next_life_loss_player != pid:
                    return []
                return _actions_for_life_loss(engine, state, pid, top_pending)

            case PendingCollectCost():
                return _actions_for_collect_cost(engine, state, pid, top_pending)

            case PendingCollectStorage():
                return _actions_for_collect_storage(engine, state, pid, top_pending)

            case PendingGain():
                return _actions_for_pay(top_pending)

            case PendingDrawRevealChoice():
                return _generate_draw_reveal_actions(state, top_pending)

            case PendingCollectPhaseCursor() | PendingLifeLossScan():

                return actions

            case PendingMonumentDrawChoice():
                known = state.get_known_monument_deck()
                if known:
                    actions.append(AvailableActionResolveMonumentDraw(eid=known[0]))
                else:
                    for mon_eid, mon in state.iter_monuments():
                        if mon.location in (
                            CardLocation.MONUMENT_DECK,
                            CardLocation.OUT_OF_GAME,
                        ):
                            actions.append(AvailableActionResolveMonumentDraw(eid=mon_eid))
                return actions

            case PendingMonumentRevealChoice():
                known = state.get_known_monument_deck()
                if known:
                    actions.append(AvailableActionResolveMonumentReveal(eid=known[0]))
                else:
                    actions.extend(
                        AvailableActionResolveMonumentReveal(eid=mon_eid)
                        for mon_eid, mon in state.iter_monuments()
                        if mon.location in (CardLocation.MONUMENT_DECK, CardLocation.OUT_OF_GAME)
                    )
                return actions

            case PendingScryRevealChoice():
                if top_pending.deck_type == DeckType.MONUMENT:
                    unknown_pool = state.get_unknown_monument_deck()
                else:
                    unknown_pool = state.get_unknown_deck_cards(top_pending.pid)
                reveal_count = top_pending.reveal_count

                from itertools import combinations

                actions.extend(
                    AvailableActionResolveScryReveal(revealed_eids=combo)
                    for combo in combinations(unknown_pool, reveal_count)
                )
                return actions

            case PendingGameSetupChoice():
                actions.append(AvailableActionResolveGameSetup())
                return actions

            case PendingPlacementChoice():
                filter_loc = top_pending.filter.location
                valid_targets: list[EntityId] = []
                if filter_loc == SelectCardLocation.HAND:
                    for art_eid in state.get_player_hand(pid):
                        entity = state.entities[art_eid]
                        if engine.placement_target_matches_filter(entity, top_pending.filter, free=top_pending.free):
                            valid_targets.append(art_eid)
                elif filter_loc == SelectCardLocation.DISCARD:
                    for art_eid in state.get_player_discard(pid):
                        entity = state.entities[art_eid]
                        if engine.placement_target_matches_filter(entity, top_pending.filter, free=top_pending.free):
                            valid_targets.append(art_eid)
                elif filter_loc == SelectCardLocation.ANY_DISCARD:
                    for i in range(state.num_players):
                        other_pid = PlayerId(i)
                        for art_eid in state.get_player_discard(other_pid):
                            entity = state.entities[art_eid]
                            if engine.placement_target_matches_filter(
                                entity, top_pending.filter, free=top_pending.free
                            ):
                                valid_targets.append(art_eid)

                for art_eid in valid_targets:
                    artifact = state.entities[art_eid]

                    if top_pending.free:
                        actions.append(AvailableActionPlaceArtifact(eid=art_eid, pay=Pool()))
                    else:
                        gold_budget = affordability.calculate_gold_discount_budget(
                            state,
                            pid,
                            artifact.data,
                            extra_discount=top_pending.discount,
                            extra_can_discount_gold=top_pending.can_discount_gold,
                        )
                        valid_payments = affordability.get_valid_payments(
                            state,
                            pid,
                            artifact.data,
                            extra_discount=top_pending.discount,
                            gold_discount_budget=gold_budget,
                        )
                        actions.extend(
                            AvailableActionPlaceArtifact(eid=art_eid, pay=payment) for payment in valid_payments
                        )

                source_eid = top_pending.source_eid
                assert source_eid is not None, "source_eid must be set for placement decline"
                actions.append(AvailableActionDecline(eid=source_eid))
                return actions

    if state.phase == GamePhase.SETUP_CHOOSE_MAGES:
        actions.extend(
            AvailableActionChooseMage(eid=mage_eid)
            for mage_eid, mage in state.iter_mages()
            if mage.location == CardLocation.BEING_CHOSEN and mage.owner_id == pid
        )
        return actions

    if state.phase == GamePhase.SETUP_CHOOSE_ITEMS:
        if state.get_magic_item_selection_player() == pid:
            actions.extend(
                AvailableActionChooseMagicItem(eid=item_eid) for item_eid in state.get_available_magic_items()
            )
        return actions

    if state.phase != GamePhase.ACTIONS:
        return []

    if player.has_passed:
        return []

    if state.current_player_index != pid:
        return []

    if engine.has_any_blocking_pending_choice(state):
        return []

    for art_eid in state.get_player_hand(pid):
        artifact = state.entities[art_eid]
        gold_budget = affordability.calculate_gold_discount_budget(
            state,
            pid,
            artifact.data,
        )
        valid_payments = affordability.get_valid_payments(
            state,
            pid,
            artifact.data,
            gold_discount_budget=gold_budget,
        )
        actions.extend(AvailableActionPlaceArtifact(eid=art_eid, pay=payment) for payment in valid_payments)

    if player.pool.gold >= 4:
        actions.extend(AvailableActionClaimMonument(eid=mon_eid) for mon_eid in state.get_monument_display())

        if state.get_top_monument_from_deck() is not None:
            actions.append(AvailableActionClaimTopMonument())

    for pop_eid, pop in state.iter_places_of_power():
        if pop.location != CardLocation.AVAILABLE:
            continue
        valid_payments = affordability.get_valid_payments(state, pid, pop.data, is_artifact=False)
        actions.extend(AvailableActionClaimPlaceOfPower(eid=pop_eid, pay=payment) for payment in valid_payments)

    actions.extend(AvailableActionDiscardForEssences(eid=art_eid) for art_eid in state.get_player_hand(pid))

    for eid, entity in state.get_all_player_components(pid):
        for i, power in enumerate(entity.data.powers):
            if power.is_react:
                continue
            if entity.is_turned and not power.usable_when_turned:
                continue
            if not _can_pay_all_costs(state, pid, eid, entity, power):
                continue
            if (
                any(isinstance(e, EffectDraw) and e.require_deck_has_cards for e in power.effects)
                and state.get_player_deck_count(pid) == 0
            ):
                continue
            requires_target = power.requires_target()
            valid_targets: list[EntityId] = []
            if requires_target:
                valid_targets = engine.get_valid_targets(state, pid, power, eid)

                has_turn_creature_cost = (
                    power.has_turn_component_cost(TurnableType.MAGE)
                    or power.has_turn_component_cost(TurnableType.DRAGON)
                    or power.has_turn_component_cost(TurnableType.CREATURE)
                )
                if has_turn_creature_cost and not valid_targets:
                    continue
            actions.append(
                AvailableActionUsePower(
                    eid=eid,
                    power_index=i,
                    target_entities=tuple(valid_targets),
                )
            )

    has_magic_item = any(
        item.location == CardLocation.IN_PLAY and item.owner_id == pid for _eid, item in state.iter_magic_items()
    )

    if has_magic_item:
        actions.extend(
            AvailableActionPass(new_magic_item_eid=item_eid) for item_eid in state.get_available_magic_items()
        )
    else:
        actions.append(AvailableActionPass(new_magic_item_eid=SENTINEL_EID))

    return actions

    return False


def _actions_for_life_loss(
    engine: GameEngine,
    state: GameState,
    pid: PlayerId,
    life_loss_choice: PendingLifeLossChoice,
) -> list[AvailableAction]:
    player = state.players[pid]
    actions: list[AvailableAction] = []

    source_is_dragon = False
    source_eid = life_loss_choice.source
    if isinstance(source_eid, int) and source_eid >= 0:
        source_entity = state.entities[source_eid]
        if source_entity and source_entity.data:
            source_is_dragon = source_entity.data.is_dragon

    def can_use_react_power(entity: Entity, power: Power) -> bool:
        if entity.is_turned and power.requires_turn:
            return False
        if power.react_trigger == ReactTrigger.DAMAGE:
            return True
        if power.react_trigger == ReactTrigger.DRAGON_ATTACK and source_is_dragon:
            return True
        return False

    for eid, entity in state.get_all_player_components(pid):
        for i, power in enumerate(entity.data.powers):
            if can_use_react_power(entity, power):
                requires_target = power.requires_target()
                valid_targets: list[EntityId] = []
                if requires_target:
                    valid_targets = engine.get_valid_targets(state, pid, power, eid)
                    if not valid_targets:
                        continue
                essence_cost = power.get_essence_cost()
                if essence_cost and not player.pool.can_afford(essence_cost):
                    continue
                actions.append(
                    AvailableActionLifeLossReact(
                        eid=eid,
                        power_index=i,
                    )
                )

    if isinstance(source_eid, int) and source_eid >= 0:
        source_entity = state.entities[source_eid]
        if source_entity and source_entity.data and source_entity.data.is_dragon:
            for power in source_entity.data.powers:
                for effect in power.effects:
                    if isinstance(effect, EffectDamage) and effect.defense_options:
                        for di, defense_cost in enumerate(effect.defense_options):
                            match defense_cost:
                                case CostPayEssence(essences=essences):
                                    can_afford = True
                                    for e_val, amount in enumerate(essences):
                                        if amount > 0 and player.pool[e_val] < amount:
                                            can_afford = False
                                            break
                                    if can_afford:
                                        actions.append(
                                            AvailableActionLifeLossReact(
                                                eid=source_eid,
                                                power_index=0,
                                                defense_option_index=di,
                                            )
                                        )
                                case CostDiscardCard():
                                    hand_cards = [
                                        EntityId(i)
                                        for i in range(len(state.entities))
                                        if state.entities[i].owner_id == pid
                                        and state.entities[i].location == CardLocation.HAND
                                    ]
                                    if hand_cards:
                                        actions.append(
                                            AvailableActionLifeLossReact(
                                                eid=source_eid,
                                                power_index=0,
                                                defense_option_index=di,
                                            )
                                        )
                                case CostDestroyComponent():
                                    artifact_targets = list(state.get_player_artifacts_in_play(pid))
                                    if artifact_targets:
                                        actions.append(
                                            AvailableActionLifeLossReact(
                                                eid=source_eid,
                                                power_index=0,
                                                defense_option_index=di,
                                            )
                                        )
                                case (
                                    CostTurnComponent()
                                    | CostRemoveFromCard()
                                    | CostPayIdentical()
                                    | CostDestroyCardType()
                                    | CostSelectPlayer()
                                    | CostSelectCard()
                                ):
                                    raise AssertionError(f"Unexpected defense cost type: {defense_cost}")

    amount = life_loss_choice.amount
    life_available = player.pool.life
    non_life_available = player.pool.total() - life_available
    has_payment_option = False

    for life_to_pay in range(min(life_available, amount) + 1):
        remaining_damage = amount - life_to_pay
        non_life_needed = remaining_damage * 2
        if non_life_available >= non_life_needed:
            payment_targets: tuple[int, ...] = tuple(
                [TargetOption.LIFE] * life_to_pay + [TargetOption.ANY] * non_life_needed
            )
            actions.append(AvailableActionLifeLossChoice(payment_options=payment_targets))
            has_payment_option = True

    if not has_payment_option:
        total_essences = player.pool.total()
        if total_essences > 0:
            life_to_pay = life_available
            non_life_to_pay = non_life_available

            payment_targets = tuple([TargetOption.LIFE] * life_to_pay + [TargetOption.ANY] * non_life_to_pay)
            actions.append(AvailableActionLifeLossChoice(payment_options=payment_targets))
        else:
            actions.append(AvailableActionLifeLossChoice())

    return actions


def _actions_for_collect_cost(
    engine: GameEngine,
    state: GameState,
    pid: PlayerId,
    collect_choice: PendingCollectCost,
) -> list[AvailableAction]:
    actions: list[AvailableAction] = []

    entity_id = collect_choice.eid
    assert entity_id is not None, "entity_id must be set for collect cost"
    entity = state.entities[entity_id]
    cost_essences = collect_choice.cost_essences
    player = state.players[pid]
    can_afford = player.pool.can_afford(cost_essences)
    if can_afford:
        actions.append(
            AvailableActionCollectCost(
                eid=entity_id,
                cost_options=(TargetOption.PAY,),
            )
        )
    can_turn = collect_choice.cost_turn and not entity.is_turned
    if can_turn:
        actions.append(
            AvailableActionCollectCost(
                eid=entity_id,
                cost_options=(TargetOption.TURN,),
            )
        )
    if not actions:
        actions.append(
            AvailableActionCollectCost(
                eid=entity_id,
                cost_options=(TargetOption.DECLINE,),
            )
        )

    return actions


def _actions_for_collect_storage(
    engine: GameEngine,
    state: GameState,
    pid: PlayerId,
    choice: PendingCollectStorage,
) -> list[AvailableAction]:
    actions: list[AvailableAction] = []

    entity_id = choice.eid
    assert entity_id is not None, "entity_id must be set for collect storage"

    actions.append(
        AvailableActionTakeStored(
            eid=entity_id,
            action_options=(TargetOption.TAKE,),
        )
    )

    actions.append(
        AvailableActionTakeStored(
            eid=entity_id,
            action_options=(TargetOption.DECLINE,),
        )
    )

    return actions


def _actions_for_pay(
    choice: PendingGain,
) -> list[AvailableAction]:
    valid_essences: list[Essence] = [
        e
        for e in [
            Essence.ELAN,
            Essence.LIFE,
            Essence.CALM,
            Essence.DEATH,
            Essence.GOLD,
        ]
        if not (choice.restriction_mask & (1 << e))
    ]

    source_eid = choice.source_eid
    assert source_eid is not None, "source_eid must be set for essence choice"
    return [
        AvailableActionGain(
            source_eid=source_eid,
            amount=choice.any_amount,
            valid_essences=tuple(valid_essences),
            alt_amount=choice.alt_any_amount,
        )
    ]


def _generate_draw_reveal_actions(
    state: GameState,
    choice: PendingDrawRevealChoice,
) -> list[AvailableAction]:
    from itertools import combinations

    reveal_count = choice.reveal_count

    known = choice.known_eids

    if reveal_count == 0:
        return [AvailableActionResolveDrawReveal(revealed_eids=(), known_eids=known)]

    unknown_pool = state.get_unknown_deck_cards(choice.pid)
    if not unknown_pool:
        return [AvailableActionResolveDrawReveal(revealed_eids=(), known_eids=known)]

    assert reveal_count <= len(unknown_pool), (reveal_count, len(unknown_pool))

    return [
        AvailableActionResolveDrawReveal(revealed_eids=combo, known_eids=known)
        for combo in combinations(unknown_pool, reveal_count)
    ]
