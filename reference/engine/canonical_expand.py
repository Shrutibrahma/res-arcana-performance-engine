from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator
from itertools import combinations_with_replacement
from typing import assert_never

from reference.engine.action_handlers.action_discard_choice import ActionDiscardChoice
from reference.engine.action_types import EntityId, PlayerId
from reference.engine.actions import Action
from reference.engine.available_actions import (
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
from reference.engine.costs import (
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
from reference.engine.effects import (
    EffectCheckVictory,
    EffectDamage,
    EffectDraw,
    EffectGain,
    EffectGainAny,
    EffectGainDestroyedCost,
    EffectGainFromOpponent,
    EffectGainGoldEqualToSameSpent,
    EffectGainGoldFromCost,
    EffectGainSameTypeAsSpent,
    EffectIgnoreDamage,
    EffectPlace,
    EffectRivalsGain,
    EffectScry,
    EffectStore,
    EffectStraighten,
    EffectTempVP,
)
from reference.engine.game_engine import GameEngine
from reference.engine.game_state import GameState
from reference.engine.pending_choices import PendingGain

from .collect_decision import CollectDecision
from .deck_type import DeckType
from .essence import Essence
from .pool import Pool
from .power import Power
from .target_option import TargetOption

_engine: GameEngine | None = None


def _get_engine() -> GameEngine:
    global _engine  # noqa: PLW0603  # singleton pattern
    if _engine is None:
        _engine = GameEngine()
    return _engine


def get_available_actions(state: GameState, pid: PlayerId) -> list[AvailableAction]:
    return _get_engine().get_available_actions(state, pid)


def enumerate_essence_payments(
    pool: Pool,
    amount: int,
    exclude_gold: bool = False,
    exclude: list[Essence] | tuple[Essence, ...] | None = None,
) -> Iterator[Pool]:
    exclude_set: set[Essence] = set(exclude) if exclude else set()
    if exclude_gold:
        exclude_set.add(Essence.GOLD)

    available_types: list[Essence] = []
    for e in Essence:
        if e in exclude_set:
            continue
        if pool[e] > 0:
            available_types.append(e)

    if not available_types:
        return

    def generate(
        remaining: int,
        start_idx: int,
        current: list[int],
    ) -> Iterator[list[int]]:
        if remaining == 0:
            yield current.copy()
            return
        if start_idx >= len(available_types):
            return

        essence = available_types[start_idx]
        max_take = min(remaining, pool[essence])

        for take in range(max_take + 1):
            current.append(take)
            yield from generate(remaining - take, start_idx + 1, current)
            current.pop()

    seen: set[tuple[int, ...]] = set()
    for combo in generate(amount, 0, []):
        payment = Pool()
        for i, e in enumerate(available_types):
            if i < len(combo):
                payment[e] = combo[i]

        if payment.total() != amount:
            continue

        key = tuple(payment)
        if key in seen:
            continue
        seen.add(key)

        yield payment


def enumerate_gain_any_choices(
    amount: int,
    exclude: list[Essence] | None = None,
) -> Iterator[Pool]:
    allowed_types = [Essence.ELAN, Essence.LIFE, Essence.CALM, Essence.DEATH]

    if exclude:
        allowed_types = [e for e in allowed_types if e not in exclude]

    if not allowed_types:
        return

    def generate(
        remaining: int,
        start_idx: int,
        current: list[int],
    ) -> Iterator[list[int]]:
        if remaining == 0:
            yield current.copy()
            return
        if start_idx >= len(allowed_types):
            return

        for take in range(remaining + 1):
            current.append(take)
            yield from generate(remaining - take, start_idx + 1, current)
            current.pop()

    seen: set[tuple[int, ...]] = set()
    for combo in generate(amount, 0, []):
        gain = Pool()
        for i, e in enumerate(allowed_types):
            if i < len(combo):
                gain[e] = combo[i]

        if gain.total() != amount:
            continue

        key = tuple(gain)
        if key in seen:
            continue
        seen.add(key)

        yield gain


def get_essence_payments(
    pool: Pool,
    amount: int,
    exclude_gold: bool = False,
    exclude: list[Essence] | tuple[Essence, ...] | None = None,
) -> list[Pool]:
    return list(enumerate_essence_payments(pool, amount, exclude_gold, exclude))


def get_gain_choices(
    amount: int,
    exclude: list[Essence] | None = None,
) -> list[Pool]:
    return list(enumerate_gain_any_choices(amount, exclude))


def expand_action(
    state: GameState,
    available: AvailableAction,
    pid: PlayerId,
) -> list[Action]:
    match available:
        case AvailableActionClaimMonument():
            return [available.to_action(pid)]

        case AvailableActionClaimTopMonument():
            return [available.to_action(pid)]

        case AvailableActionClaimPlaceOfPower():
            return [available.to_action(pid)]

        case AvailableActionPass():
            return [available.to_action(pid)]

        case AvailableActionChooseMage():
            return [available.to_action(pid)]

        case AvailableActionChooseMagicItem():
            return [available.to_action(pid)]

        case AvailableActionDiscardChoice(discard_count=k):
            from itertools import combinations

            hand = state.get_player_hand(pid)
            return [ActionDiscardChoice(pid=pid, eids=tuple(sorted(combo))) for combo in combinations(hand, k)]

        case AvailableActionResolveDrawReveal():
            return [available.to_action(pid)]

        case AvailableActionResolveMonumentDraw():
            return [available.to_action(pid)]

        case AvailableActionResolveMonumentReveal():
            return [available.to_action(pid)]

        case AvailableActionDecline():
            return [available.to_action(pid)]

        case AvailableActionPlaceArtifact():
            return [available.to_action(pid)]

        case AvailableActionDiscardForEssences(eid=eid):
            return _expand_discard_for_essences(pid, eid)

        case AvailableActionUsePower():
            return _expand_use_power(state, pid, available)

        case AvailableActionVictoryReact():
            return _expand_victory_react(state, pid, available)

        case AvailableActionLifeLossReact():
            return _expand_life_loss_react(state, pid, available)

        case AvailableActionLifeLossChoice(payment_options=targets):
            return _expand_life_loss_choice(state, pid, targets)

        case AvailableActionTakeStored(eid=eid, action_options=targets):
            return _expand_take_stored(pid, eid, targets)

        case AvailableActionScryDeckChoice(deck_options=targets):
            return _expand_scry_deck_choice(pid, targets)

        case AvailableActionScryChoice(scry_indices=indices):
            return _expand_scry_choice(pid, indices)

        case AvailableActionCollectCost(eid=eid, cost_options=targets):
            return _expand_collect_cost(pid, eid, targets)

        case AvailableActionGain():
            return _expand_pay(state, pid, available)

        case AvailableActionResolveScryReveal():
            return [available.to_action(pid)]

        case AvailableActionResolveGameSetup():
            return []

        case _ as never:
            assert_never(never)


def _expand_discard_for_essences(pid: PlayerId, eid: EntityId) -> list[Action]:
    results: list[Action] = []
    results.append(AvailableActionDiscardForEssences(eid=eid).to_action(pid, Pool(gold=1)))
    non_gold = [Essence.ELAN, Essence.LIFE, Essence.CALM, Essence.DEATH]
    for i, e1 in enumerate(non_gold):
        for e2 in non_gold[i:]:
            pool = Pool()
            pool.add(e1, 1)
            pool.add(e2, 1)
            results.append(AvailableActionDiscardForEssences(eid=eid).to_action(pid, pool))
    return results


def _expand_take_stored(
    pid: PlayerId,
    eid: EntityId,
    targets: tuple[TargetOption, ...],
) -> list[Action]:
    results: list[Action] = []
    for target in targets:
        if target == TargetOption.TAKE:
            results.append(
                AvailableActionTakeStored(eid=eid, action_options=targets).to_action(pid, CollectDecision.TAKE_STORED)
            )
        elif target == TargetOption.DECLINE:
            results.append(
                AvailableActionTakeStored(eid=eid, action_options=targets).to_action(pid, CollectDecision.LEAVE_STORED)
            )
    return results


def _expand_scry_deck_choice(
    pid: PlayerId,
    targets: tuple[DeckType, ...],
) -> list[Action]:
    return [AvailableActionScryDeckChoice(deck_options=targets).to_action(pid, deck) for deck in targets]


def _expand_scry_choice(
    pid: PlayerId,
    indices: tuple[int, ...],
) -> list[Action]:

    count = len(indices)

    if count == 0:
        return [AvailableActionScryChoice(scry_indices=()).to_action(pid, [])]

    results: list[Action] = [
        AvailableActionScryChoice(scry_indices=indices).to_action(pid, list(perm))
        for perm in itertools.permutations(range(count))
    ]
    return results


def _expand_collect_cost(
    pid: PlayerId,
    eid: EntityId,
    targets: tuple[TargetOption, ...],
) -> list[Action]:
    results: list[Action] = []
    for target in targets:
        if target == TargetOption.PAY:
            decision = CollectDecision.PAY_COST
        elif target == TargetOption.TURN:
            decision = CollectDecision.PAY_TURN
        elif target == TargetOption.DECLINE:
            decision = CollectDecision.DECLINE_COST
        else:
            continue
        results.append(AvailableActionCollectCost(eid=eid, cost_options=targets).to_action(pid, decision))
    return results


def _expand_life_loss_choice(
    state: GameState,
    pid: PlayerId,
    targets: tuple[TargetOption, ...],
) -> list[Action]:
    if not targets:
        return [AvailableActionLifeLossChoice().to_action(pid)]

    life_count = sum(1 for t in targets if t == TargetOption.LIFE)
    any_count = sum(1 for t in targets if t == TargetOption.ANY)

    if any_count == 0:
        pool = Pool(life=life_count)
        return [AvailableActionLifeLossChoice(payment_options=targets).to_action(pid, pool)]

    player_pool = state.players[pid].pool
    results: list[Action] = []

    any_payments = get_essence_payments(
        player_pool,
        any_count,
        exclude_gold=False,
        exclude=[Essence.LIFE],
    )

    for any_payment in any_payments:
        total = any_payment.copy()
        total.add(Essence.LIFE, life_count)
        if player_pool.can_afford(total):
            results.append(AvailableActionLifeLossChoice(payment_options=targets).to_action(pid, total))

    return results if results else [AvailableActionLifeLossChoice(payment_options=targets).to_action(pid)]


def _expand_pay(
    state: GameState,
    pid: PlayerId,
    available: AvailableActionGain,
) -> list[Action]:
    amount = available.amount
    alt_amount = available.alt_amount

    if amount == 0:
        for c in reversed(state.pending_stack):
            if isinstance(c, PendingGain) and c.pid == pid:
                amount = c.any_amount
                alt_amount = c.alt_any_amount
                break

    if amount == 0 and alt_amount == 0:
        return [available.to_action(pid, Pool(), use_alt=False)]

    results: list[Action] = []

    if amount > 0:
        if available.valid_essences:
            if amount == 1:
                for e in available.valid_essences:
                    choice = Pool()
                    choice[e] = 1
                    results.append(available.to_action(pid, choice, use_alt=False))
            else:
                _generate_essence_combinations(
                    amount,
                    list(available.valid_essences),
                    results,
                    available,
                    pid,
                    use_alt=False,
                )
        else:
            choices = get_gain_choices(amount)
            results.extend(available.to_action(pid, choice, use_alt=False) for choice in choices)

    if alt_amount > 0:
        alt_choices = get_gain_choices(alt_amount)
        results.extend(available.to_action(pid, choice, use_alt=True) for choice in alt_choices)

    return results if results else [available.to_action(pid, Pool(), use_alt=False)]


def _generate_essence_combinations(
    amount: int,
    allowed: list[Essence],
    results: list[Action],
    available: AvailableActionGain,
    pid: PlayerId,
    use_alt: bool,
) -> None:
    for combo in combinations_with_replacement(allowed, amount):
        choice = Pool()
        for e in combo:
            choice[e] += 1
        results.append(available.to_action(pid, choice, use_alt=use_alt))


def _collect_fixed_gains(power: Power, include_gain: bool = True) -> Pool:
    fixed = Pool()
    for effect in power.effects:
        if include_gain and isinstance(effect, EffectGain):
            fixed.add_pool(effect.essences)
        elif (
            isinstance(effect, EffectStore)
            and effect.any_amount == 0
            and not effect.what_spent
            and not effect.on_target
        ):
            fixed.add_pool(effect.essences)
    return fixed


def _expand_use_power(
    state: GameState,
    pid: PlayerId,
    available: AvailableActionUsePower,
) -> list[Action]:
    eid = available.eid
    power_index = available.power_index
    valid_targets = list(available.target_entities) if available.target_entities else []

    entity = state.entities[eid]
    if not entity.data or power_index >= len(entity.data.powers):
        return []

    power = entity.data.powers[power_index]
    player_pool = state.players[pid].pool
    results: list[Action] = []

    any_cost = power.get_any_cost()
    fixed_cost = power.get_essence_cost()
    exclude = power.get_any_cost_exclude()

    pay_identical_cost: CostPayIdentical | None = None
    for cost in power.costs:
        if isinstance(cost, CostPayIdentical):
            pay_identical_cost = cost
            break

    gain_any_amount = 0
    gain_any_exclude: list[Essence] = []
    store_any_amount = 0
    store_any_exclude: list[Essence] = []
    store_what_spent = False
    has_place_effect = False
    requires_player_target = False
    player_target_opponent_only = False
    gain_same_type_as_spent = False
    gain_gold_equal_to_same_spent = False
    convert_same_to_gold = False
    convert_same_to_gold_rate = 0
    gain_destroyed_cost_as_any = False
    gain_destroyed_cost_bonus = 0
    gain_gold_from_cost_divisor = 0

    for effect in power.effects:
        match effect:
            case EffectGainAny(amount=amount, exclude=gain_exclude):
                gain_any_amount = amount
                gain_any_exclude = list(gain_exclude) if gain_exclude else []
            case EffectStore(any_amount=any_amount, exclude=store_exclude, what_spent=what_spent, on_target=_):
                if any_amount > 0:
                    store_any_amount = any_amount
                    store_any_exclude = list(store_exclude) if store_exclude else []
                if what_spent:
                    store_what_spent = True
            case EffectPlace():
                has_place_effect = True
            case EffectGainSameTypeAsSpent():
                gain_same_type_as_spent = True
            case EffectGainGoldEqualToSameSpent():
                gain_gold_equal_to_same_spent = True
            case EffectGainDestroyedCost(as_any=True, bonus=bonus):
                gain_destroyed_cost_as_any = True
                gain_destroyed_cost_bonus = bonus
            case EffectGainGoldFromCost(divisor=divisor):
                gain_gold_from_cost_divisor = divisor
            case (
                EffectGain()
                | EffectRivalsGain()
                | EffectDamage()
                | EffectDraw()
                | EffectIgnoreDamage()
                | EffectCheckVictory()
                | EffectStraighten()
                | EffectScry()
                | EffectGainFromOpponent()
                | EffectTempVP()
                | EffectGainDestroyedCost()
            ):
                pass

    for cost in power.costs:
        match cost:
            case CostSelectPlayer(opponent_only=opponent_only):
                requires_player_target = True
                player_target_opponent_only = opponent_only
            case (
                CostTurnComponent()
                | CostPayEssence()
                | CostRemoveFromCard()
                | CostPayIdentical()
                | CostDestroyComponent()
                | CostDestroyCardType()
                | CostDiscardCard()
                | CostSelectCard()
            ):
                pass

    requires_target = False
    for cost in power.costs:
        if isinstance(cost, CostDestroyComponent) and cost.destroy_mode != DestroyMode.SELF:
            requires_target = True
            break
        if isinstance(cost, CostTurnComponent):
            requires_target = True
            break
        if isinstance(cost, CostDiscardCard):
            requires_target = True
            break
    for effect in power.effects:
        if isinstance(effect, EffectStore) and effect.on_target:
            requires_target = True
            break

    select_card_cost = power.get_select_card_cost()
    if select_card_cost and select_card_cost.filter.exclude_self:
        valid_targets = [t for t in valid_targets if t != eid]

    targets_to_use: list[EntityId | None] = list(valid_targets)
    if not requires_target:
        targets_to_use.append(None)
    if not targets_to_use:
        if requires_target:
            return []
        targets_to_use = [None]

    if pay_identical_cost is not None:
        base = pay_identical_cost.base_cost
        min_x = pay_identical_cost.min_amount
        min_total = base + min_x

        max_x = player_pool.total()
        max_total = min(player_pool.total(), base + max_x)

        payment_choices: list[Pool] = []
        for total in range(min_total, max_total + 1):
            x = total - base
            if pay_identical_cost.essence_type is not None:
                etype = pay_identical_cost.essence_type
                if player_pool[etype] >= x:
                    remaining_pool = player_pool.copy()
                    remaining_pool[etype] -= x
                    for base_payment in get_essence_payments(remaining_pool, base, exclude_gold=False):
                        choice = base_payment.copy()
                        choice[etype] += x
                        if player_pool.can_afford(choice):
                            payment_choices.append(choice)
            else:
                for etype in [
                    Essence.ELAN,
                    Essence.LIFE,
                    Essence.CALM,
                    Essence.DEATH,
                    Essence.GOLD,
                ]:
                    if player_pool[etype] >= x:
                        remaining_pool = player_pool.copy()
                        remaining_pool[etype] -= x
                        for base_payment in get_essence_payments(remaining_pool, base, exclude_gold=False):
                            choice = base_payment.copy()
                            choice[etype] += x
                            if player_pool.can_afford(choice):
                                payment_choices.append(choice)

        seen: set[tuple[int, ...]] = set()
        unique_payments: list[Pool] = []
        for p in payment_choices:
            key = tuple(p)
            if key not in seen:
                seen.add(key)
                unique_payments.append(p)

        for payment in unique_payments or [Pool()]:
            gain = Pool()
            if gain_gold_from_cost_divisor > 0:
                x = payment.total() - pay_identical_cost.base_cost
                gain[Essence.GOLD] = x // gain_gold_from_cost_divisor
            results.append(available.to_action(pid, pay=payment, gain=gain))
        return results if results else [available.to_action(pid)]

    if gain_same_type_as_spent:

        spendable_types = [
            Essence.ELAN,
            Essence.LIFE,
            Essence.CALM,
            Essence.DEATH,
            Essence.GOLD,
        ]
        gainable_types = [Essence.ELAN, Essence.LIFE, Essence.CALM, Essence.DEATH]
        results.append(available.to_action(pid, pay=Pool(), gain=Pool()))
        for spend_type in spendable_types:
            max_n = player_pool[spend_type]
            for n in range(1, max_n + 1):
                spend_choice = Pool()
                spend_choice[spend_type] = n
                for gain_type in gainable_types:
                    if gain_type != spend_type:
                        gain_choice = Pool()
                        gain_choice[gain_type] = n
                        results.append(available.to_action(pid, pay=spend_choice.copy(), gain=gain_choice.copy()))
        return results

    if gain_gold_equal_to_same_spent:
        allowed_types = [
            Essence.ELAN,
            Essence.LIFE,
            Essence.CALM,
            Essence.DEATH,
            Essence.GOLD,
        ]
        results.append(available.to_action(pid, pay=Pool()))
        for spend_type in allowed_types:
            max_n = player_pool[spend_type]
            for n in range(1, max_n + 1):
                spend_choice = Pool()
                spend_choice[spend_type] = n
                results.append(available.to_action(pid, pay=spend_choice.copy()))
        return results

    if convert_same_to_gold and convert_same_to_gold_rate > 0:
        allowed_types = [Essence.ELAN, Essence.LIFE, Essence.CALM, Essence.DEATH]
        for etype in allowed_types:
            max_n = player_pool[etype]

            for n in range(convert_same_to_gold_rate, max_n + 1, 1):
                spend_choice = Pool()
                spend_choice[etype] = n
                gain = Pool()
                gain[Essence.GOLD] = n // convert_same_to_gold_rate
                results.append(available.to_action(pid, pay=spend_choice.copy(), gain=gain))
        return results if results else [available.to_action(pid)]

    if store_what_spent and any_cost == 0 and fixed_cost.total() == 0:
        allowed_types = [
            Essence.ELAN,
            Essence.LIFE,
            Essence.CALM,
            Essence.DEATH,
            Essence.GOLD,
        ]
        results.append(available.to_action(pid, pay=Pool()))
        for etype in allowed_types:
            max_n = player_pool[etype]
            for n in range(1, max_n + 1):
                choice = Pool()
                choice[etype] = n
                results.append(available.to_action(pid, pay=choice.copy()))

        total_available = sum(player_pool[e] for e in allowed_types)
        if total_available > 0:
            for total in range(2, min(total_available + 1, 6)):
                for payment in get_essence_payments(player_pool, total):
                    if payment:
                        types_used = sum(1 for e in allowed_types if payment[e] > 0)
                        if types_used >= 2:
                            results.append(available.to_action(pid, pay=payment.copy()))
        return results

    payment_choices: list[Pool] = []
    has_any_cost = any_cost > 0
    has_fixed_cost = fixed_cost.total() > 0 if fixed_cost else False

    if has_any_cost:
        remaining_pool = player_pool.copy()
        for i in range(len(remaining_pool)):
            remaining_pool[i] -= fixed_cost[i]
            if remaining_pool[i] < 0:
                remaining_pool[i] = 0
        any_payments = get_essence_payments(remaining_pool, any_cost, exclude=exclude)
        for pay in any_payments:
            total = fixed_cost.copy()
            total.add_pool(pay)
            if player_pool.can_afford(total):
                payment_choices.append(total)
    elif has_fixed_cost:
        payment_choices = [fixed_cost.copy()]
    else:
        payment_choices = [Pool()]

    if not payment_choices:
        payment_choices = [Pool()]

    gain_choices: list[Pool] = [Pool()]
    if gain_any_amount > 0:
        gain_choices = list(get_gain_choices(gain_any_amount, exclude=gain_any_exclude))
        if not gain_choices:
            gain_choices = [Pool()]

    if store_any_amount > 0 and gain_choices == [Pool()]:
        gain_choices = list(get_gain_choices(store_any_amount, store_any_exclude))
        if not gain_choices:
            gain_choices = [Pool()]

    fixed_gains = _collect_fixed_gains(power, include_gain=store_any_amount == 0)
    if not fixed_gains.is_empty():
        new_choices: list[Pool] = []
        for choice in gain_choices:
            merged = fixed_gains.copy()
            merged.add_pool(choice)
            new_choices.append(merged)
        gain_choices = new_choices

    player_targets: list[PlayerId | None] = [None]
    if requires_player_target:
        player_targets = [PlayerId(i) for i in range(state.num_players) if not player_target_opponent_only or i != pid]

    if has_place_effect:
        results.extend(
            available.to_action(pid, target_id=None, pay=payment, gain=gain)
            for payment in payment_choices
            for gain in gain_choices
        )
        return results if results else [available.to_action(pid)]

    for target in targets_to_use:
        target_payment_choices: list[Pool] = payment_choices

        target_gain_choices = gain_choices
        if gain_destroyed_cost_as_any and isinstance(target, int):
            target_entity = state.entities[target]
            destroyed_cost = 0
            if target_entity.data:
                fixed = target_entity.data.placement_cost.total() if target_entity.data.placement_cost else 0
                destroyed_cost = fixed + target_entity.data.placement_cost_any
            gain_amount = destroyed_cost + gain_destroyed_cost_bonus
            if gain_amount > 0:
                target_gain_choices = list(get_gain_choices(gain_amount))
            if not target_gain_choices:
                target_gain_choices = [Pool()]

        for payment in target_payment_choices:
            for gain in target_gain_choices:
                for player_target in player_targets:
                    results.append(  # noqa: PERF401
                        available.to_action(
                            pid,
                            target_id=target,
                            target_pid=player_target,
                            pay=payment,
                            gain=gain,
                        )
                    )

    return results if results else [available.to_action(pid)]


def _expand_victory_react(
    state: GameState,
    pid: PlayerId,
    available: AvailableActionVictoryReact,
) -> list[Action]:
    entity = state.entities[available.eid]
    power = entity.data.powers[available.power_index]
    valid_targets = tuple(_get_engine().get_valid_targets(state, pid, power, available.eid))

    def build_action(p: PlayerId, tid: EntityId | None, ess: Pool) -> Action:
        return available.to_action(p, target_id=tid, pay=ess)

    return _expand_react_common(
        state,
        pid,
        available.eid,
        available.power_index,
        valid_targets,
        build_action,
    )


def _expand_life_loss_react(
    state: GameState,
    pid: PlayerId,
    available: AvailableActionLifeLossReact,
) -> list[Action]:

    if available.defense_option_index is not None:
        return _expand_dragon_defense(state, pid, available)

    entity = state.entities[available.eid]
    power = entity.data.powers[available.power_index]
    fixed_gains = _collect_fixed_gains(power)
    gain = fixed_gains
    valid_targets = tuple(_get_engine().get_valid_targets(state, pid, power, available.eid))

    def build_action(p: PlayerId, tid: EntityId | None, ess: Pool) -> Action:
        return available.to_action(p, target_id=tid, pay=ess, gain=gain)

    return _expand_react_common(
        state,
        pid,
        available.eid,
        available.power_index,
        valid_targets,
        build_action,
    )


def _expand_dragon_defense(
    state: GameState,
    pid: PlayerId,
    available: AvailableActionLifeLossReact,
) -> list[Action]:
    from reference.engine.effects.effect_damage import EffectDamage

    di = available.defense_option_index
    assert di is not None

    entity = state.entities[available.eid]
    assert entity.data is not None
    defense_cost = None
    for power in entity.data.powers:
        for effect in power.effects:
            if isinstance(effect, EffectDamage) and effect.defense_options:
                assert di < len(effect.defense_options)
                defense_cost = effect.defense_options[di]
                break
        if defense_cost is not None:
            break
    assert defense_cost is not None, "Dragon has no damage effect"

    results: list[Action] = []
    match defense_cost:
        case CostPayEssence(essences=essences):
            player_pool = state.players[pid].pool
            if player_pool.can_afford(essences):
                results.append(available.to_action(pid, pay=essences))
        case CostDiscardCard():
            results.extend(available.to_action(pid, target_id=hand_eid) for hand_eid in state.get_player_hand(pid))
        case CostDestroyComponent():
            results.extend(
                available.to_action(pid, target_id=art_eid) for art_eid in state.get_player_artifacts_in_play(pid)
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
    return results


def _expand_react_common(
    state: GameState,
    pid: PlayerId,
    eid: EntityId,
    power_index: int,
    valid_targets: tuple[EntityId, ...],
    action_builder: Callable[[PlayerId, EntityId | None, Pool], Action],
) -> list[Action]:
    entity = state.entities[eid]
    power = entity.data.powers[power_index]
    player_pool = state.players[pid].pool

    fixed_cost = power.get_essence_cost()
    any_cost = power.get_any_cost()

    gain_amount = 0
    for effect in power.effects:
        if isinstance(effect, EffectGainAny):
            gain_amount = effect.amount
            break

    targets_to_use: list[EntityId | None] = list(valid_targets) if valid_targets else [None]

    payment_choices: list[Pool] = []
    if any_cost > 0:
        remaining = player_pool.copy()
        for i in range(len(remaining)):
            remaining[i] = max(0, remaining[i] - fixed_cost[i])

        payments = get_essence_payments(remaining, any_cost)
        for pay in payments:
            total = fixed_cost.copy()
            total.add_pool(pay)
            if player_pool.can_afford(total):
                payment_choices.append(total)
    else:
        if player_pool.can_afford(fixed_cost):
            payment_choices = [fixed_cost.copy()]

    if not payment_choices:
        return []

    gain_choices: list[Pool | None] = [None]
    if gain_amount > 0:
        gain_choices = list(get_gain_choices(gain_amount))
        if not gain_choices:
            gain_choices = [None]

    results: list[Action] = [
        action_builder(pid, target, payment) for target in targets_to_use for payment in payment_choices
    ]

    return results
