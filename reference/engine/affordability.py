from __future__ import annotations

from .action_types import PlayerId
from .entity_data import EntityData
from .essence import Essence
from .game_state import GameState
from .pool import Pool

DISCOUNTABLE_ESSENCES = [Essence.ELAN, Essence.LIFE, Essence.CALM, Essence.DEATH]

ANY_PAYABLE_ESSENCES = [
    Essence.ELAN,
    Essence.LIFE,
    Essence.CALM,
    Essence.DEATH,
    Essence.GOLD,
]


def calculate_discount(
    state: GameState,
    pid: PlayerId,
    card_data: EntityData,
    extra_discount: int = 0,
    is_artifact: bool = True,
) -> int:
    if not is_artifact:
        return 0

    discounts = state.get_total_discount(pid)
    discount = discounts.artifact + extra_discount

    if card_data.is_dragon:
        discount += discounts.dragon
    if card_data.is_creature:
        discount += discounts.creature

    return discount


def calculate_gold_discount_budget(
    state: GameState,
    pid: PlayerId,
    card_data: EntityData,
    extra_discount: int = 0,
    extra_can_discount_gold: bool = False,
) -> int:
    gold_budget = extra_discount if extra_can_discount_gold else 0

    for _eid, entity in state.get_all_player_components(pid):
        d = entity.data.discount
        if not d.can_discount_gold:
            continue
        source_applicable = d.artifact
        if card_data.is_dragon:
            source_applicable += d.dragon
        if card_data.is_creature:
            source_applicable += d.creature
        gold_budget += source_applicable

    return gold_budget


def get_valid_payments(
    state: GameState,
    pid: PlayerId,
    card_data: EntityData,
    extra_discount: int = 0,
    is_artifact: bool = True,
    gold_discount_budget: int = 0,
) -> list[Pool]:
    player = state.players[pid]
    pool = player.pool

    fixed_cost = card_data.placement_cost.copy() if card_data.placement_cost else Pool()
    any_cost = card_data.placement_cost_any or 0

    discount = calculate_discount(state, pid, card_data, extra_discount, is_artifact)

    effective_can_discount_gold = gold_discount_budget > 0

    discountable_essences = list(DISCOUNTABLE_ESSENCES)
    if effective_can_discount_gold:
        discountable_essences.append(Essence.GOLD)

    fixed_discountable = sum(fixed_cost[e] for e in discountable_essences)
    total_discountable = fixed_discountable + any_cost
    effective_discount = min(discount, total_discountable)

    valid_payments: list[Pool] = []
    seen: set[tuple[int, ...]] = set()

    def add_payment(payment: Pool) -> None:
        payment_tuple = tuple(payment)
        if payment_tuple not in seen:
            seen.add(payment_tuple)
            valid_payments.append(payment.copy())

    def enumerate_any_payments(
        base_payment: Pool,
        remaining_any: int,
        essence_idx: int = 0,
    ) -> None:
        if remaining_any == 0:
            if pool.can_afford(base_payment):
                add_payment(base_payment)
            return

        if essence_idx >= len(ANY_PAYABLE_ESSENCES):
            return

        essence = ANY_PAYABLE_ESSENCES[essence_idx]

        already_paying = base_payment[essence]
        available = pool[essence] - already_paying

        for amount in range(min(available, remaining_any) + 1):
            new_payment = base_payment.copy()
            new_payment[essence] = already_paying + amount
            enumerate_any_payments(new_payment, remaining_any - amount, essence_idx + 1)

    def enumerate_discount_allocations(
        remaining_discount: int,
        essence_idx: int,
        current_fixed_payment: Pool,
    ) -> None:
        if essence_idx == len(discountable_essences):
            discount_to_any = min(remaining_discount, any_cost)
            any_after_discount = any_cost - discount_to_any
            unused_discount = remaining_discount - discount_to_any

            if unused_discount > 0:
                return

            if any_after_discount == 0:
                if pool.can_afford(current_fixed_payment):
                    add_payment(current_fixed_payment)
            else:
                enumerate_any_payments(current_fixed_payment, any_after_discount)
            return

        essence = discountable_essences[essence_idx]
        original = fixed_cost[essence]

        max_discount = min(original, remaining_discount)
        if essence == Essence.GOLD:
            max_discount = min(max_discount, gold_discount_budget)

        for discount_amount in range(max_discount + 1):
            new_payment = current_fixed_payment.copy()
            new_payment[essence] = original - discount_amount
            enumerate_discount_allocations(
                remaining_discount - discount_amount,
                essence_idx + 1,
                new_payment,
            )

    initial_payment = Pool()
    if not effective_can_discount_gold:
        initial_payment[Essence.GOLD] = fixed_cost[Essence.GOLD]

    if not pool.can_afford(initial_payment):
        return []

    if effective_discount == 0:
        for e in discountable_essences:
            initial_payment[e] = fixed_cost[e]
        if any_cost == 0:
            if pool.can_afford(initial_payment):
                add_payment(initial_payment)
        else:
            enumerate_any_payments(initial_payment, any_cost)
    else:
        enumerate_discount_allocations(effective_discount, 0, initial_payment)

    return valid_payments
