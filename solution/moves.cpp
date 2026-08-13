// Move generation: affordability/payment enumeration + the fused
// get_available_actions + expand_action. Mirrors reference
// engine/affordability.py, canonical_expand.py, available_actions.py.
#include "engine.hpp"
#include <algorithm>
#include <functional>

namespace ra {

// ---------------------------------------------------------------------------
// payment enumeration (canonical_expand.enumerate_essence_payments)
// ---------------------------------------------------------------------------
static void gen_payments_rec(const Pool& pool, const int* types, int ntypes,
                             int idx, int remaining, Pool cur, std::vector<Pool>& out) {
    if (remaining == 0) { out.push_back(cur); return; }
    if (idx >= ntypes) return;
    int e = types[idx];
    int maxtake = std::min(remaining, (int)pool[e]);
    for (int take = 0; take <= maxtake; take++) {
        Pool nx = cur; nx.v[e] = (int16_t)take;
        gen_payments_rec(pool, types, ntypes, idx + 1, remaining - take, nx, out);
    }
}
// excl_mask: bit e set => exclude essence e (also pass exclude_gold via mask)
static void enumerate_essence_payments(const Pool& pool, int amount, int excl_mask,
                                       std::vector<Pool>& out) {
    int types[ESSENCE_COUNT], nt = 0;
    for (int e = 0; e < ESSENCE_COUNT; e++) {
        if (excl_mask & (1 << e)) continue;
        if (pool[e] > 0) types[e ? nt : nt] = e, nt++;  // keep order ELAN..GOLD
    }
    if (nt == 0) return;
    // rebuild types in order
    nt = 0;
    for (int e = 0; e < ESSENCE_COUNT; e++) {
        if (excl_mask & (1 << e)) continue;
        if (pool[e] > 0) types[nt++] = e;
    }
    std::vector<Pool> raw;
    gen_payments_rec(pool, types, nt, 0, amount, Pool(), raw);
    // dedupe + total==amount
    for (Pool& p : raw) {
        if (p.total() != amount) continue;
        bool dup = false;
        for (const Pool& q : out) if (q == p) { dup = true; break; }
        if (!dup) out.push_back(p);
    }
}

// gain choices: distribute amount over ELAN,LIFE,CALM,DEATH (combinations w/ replacement)
static void gain_rec(int amount, int idx, const int* types, int nt, Pool cur, std::vector<Pool>& out) {
    if (amount == 0) { out.push_back(cur); return; }
    if (idx >= nt) return;
    for (int take = 0; take <= amount; take++) {
        Pool nx = cur; nx.v[types[idx]] = (int16_t)take;
        gain_rec(amount - take, idx + 1, types, nt, nx, out);
    }
}
static void get_gain_choices(int amount, int excl_mask, std::vector<Pool>& out) {
    int types[4]; int nt = 0;
    int base[4] = {ELAN, LIFE, CALM, DEATH};
    for (int i = 0; i < 4; i++) if (!(excl_mask & (1 << base[i]))) types[nt++] = base[i];
    if (nt == 0) return;
    std::vector<Pool> raw;
    gain_rec(amount, 0, types, nt, Pool(), raw);
    for (Pool& p : raw) {
        if (p.total() != amount) continue;
        bool dup = false;
        for (const Pool& q : out) if (q == p) { dup = true; break; }
        if (!dup) out.push_back(p);
    }
}

// ---------------------------------------------------------------------------
// affordability (affordability.py)
// ---------------------------------------------------------------------------
static int calculate_discount(const GameState& st, int pid, const EntityData* d,
                              int extra_discount, bool is_artifact) {
    if (!is_artifact) return 0;
    Discount disc = st.get_total_discount(pid);
    int discount = disc.artifact + extra_discount;
    if (d->is_dragon()) discount += disc.dragon;
    if (d->is_creature()) discount += disc.creature;
    return discount;
}

int calculate_gold_discount_budget(const GameState& st, int pid, const EntityData* d,
                                   int extra_discount, bool extra_can_discount_gold) {
    int gold_budget = extra_can_discount_gold ? extra_discount : 0;
    EidVec comps = st.get_all_player_components(pid);
    for (int eid : comps) {
        const Discount& cd = st.entities[eid].data->discount;
        if (!cd.can_discount_gold) continue;
        int src = cd.artifact;
        if (d->is_dragon()) src += cd.dragon;
        if (d->is_creature()) src += cd.creature;
        gold_budget += src;
    }
    return gold_budget;
}

static const int ANY_PAYABLE[5] = {ELAN, LIFE, CALM, DEATH, GOLD};

namespace {
struct PaymentEnum {
    const GameState* st; int pid; const Pool* pool;
    const EntityData* d; int any_cost; int gold_discount_budget;
    int discountable[5]; int ndiscountable;
    std::vector<Pool>* out;
    Pool fixed_cost;

    void add_payment(const Pool& p) {
        for (const Pool& q : *out) if (q == p) return;
        out->push_back(p);
    }
    void enumerate_any(Pool base, int remaining, int eidx) {
        if (remaining == 0) { if (pool->can_afford(base)) add_payment(base); return; }
        if (eidx >= 5) return;
        int e = ANY_PAYABLE[eidx];
        int already = base[e];
        int avail = (*pool)[e] - already;
        int hi = std::min(avail, remaining);
        for (int amt = 0; amt <= hi; amt++) {
            Pool np = base; np.v[e] = (int16_t)(already + amt);
            enumerate_any(np, remaining - amt, eidx + 1);
        }
    }
    void enumerate_discount(int remaining, int eidx, Pool curfixed) {
        if (eidx == ndiscountable) {
            int to_any = std::min(remaining, any_cost);
            int any_after = any_cost - to_any;
            int unused = remaining - to_any;
            if (unused > 0) return;
            if (any_after == 0) { if (pool->can_afford(curfixed)) add_payment(curfixed); }
            else enumerate_any(curfixed, any_after, 0);
            return;
        }
        int e = discountable[eidx];
        int original = fixed_cost[e];
        int maxd = std::min(original, remaining);
        if (e == GOLD) maxd = std::min(maxd, gold_discount_budget);
        for (int da = 0; da <= maxd; da++) {
            Pool np = curfixed; np.v[e] = (int16_t)(original - da);
            enumerate_discount(remaining - da, eidx + 1, np);
        }
    }
};
}

void get_valid_payments(const GameState& st, int pid, const EntityData* d,
                        int extra_discount, bool is_artifact,
                        int gold_discount_budget, std::vector<Pool>& out) {
    const Pool& pool = st.players[pid].pool;
    Pool fixed_cost = d->has_placement_cost ? d->placement_cost : Pool();
    int any_cost = d->placement_cost_any;
    int discount = calculate_discount(st, pid, d, extra_discount, is_artifact);
    bool eff_cdg = gold_discount_budget > 0;

    int discountable[5]; int nd = 0;
    discountable[nd++] = ELAN; discountable[nd++] = LIFE; discountable[nd++] = CALM; discountable[nd++] = DEATH;
    if (eff_cdg) discountable[nd++] = GOLD;

    int fixed_discountable = 0;
    for (int i = 0; i < nd; i++) fixed_discountable += fixed_cost[discountable[i]];
    int total_discountable = fixed_discountable + any_cost;
    int eff_discount = std::min(discount, total_discountable);

    PaymentEnum pe;
    pe.st = &st; pe.pid = pid; pe.pool = &pool; pe.d = d; pe.any_cost = any_cost;
    pe.gold_discount_budget = gold_discount_budget; pe.out = &out; pe.fixed_cost = fixed_cost;
    pe.ndiscountable = nd;
    for (int i = 0; i < nd; i++) pe.discountable[i] = discountable[i];

    Pool initial;
    if (!eff_cdg) initial.v[GOLD] = fixed_cost[GOLD];
    if (!pool.can_afford(initial)) return;

    if (eff_discount == 0) {
        for (int i = 0; i < nd; i++) initial.v[discountable[i]] = fixed_cost[discountable[i]];
        if (any_cost == 0) { if (pool.can_afford(initial)) pe.add_payment(initial); }
        else pe.enumerate_any(initial, any_cost, 0);
    } else {
        pe.enumerate_discount(eff_discount, 0, initial);
    }
}

// ---------------------------------------------------------------------------
// affordability for power costs (available_actions._can_pay_cost)
// ---------------------------------------------------------------------------
static bool can_pay_cost(const Cost& c, const GameState& st, int pid, int16_t eid, const Entity& entity) {
    const Pool& pool = st.players[pid].pool;
    switch (c.type) {
        case CostType::PayEssence: {
            if (!pool.can_afford(c.essences)) return false;
            if (c.any_amount == 0) return true;
            int avail = pool.total() - c.essences.total();
            for (int k = 0; k < c.exclude_count; k++) {
                int ex = (int)c.exclude[k];
                int rem = pool[ex] - c.essences[ex];
                if (rem > 0) avail -= rem;
            }
            return avail >= c.any_amount;
        }
        case CostType::PayIdentical: {
            int min_total = c.base_cost + c.min_amount;
            if (pool.total() < min_total) return false;
            if (c.essence_type >= 0) return pool[c.essence_type] >= c.min_amount;
            int mx = 0; for (int e = 0; e < ESSENCE_COUNT; e++) mx = std::max(mx, (int)pool[e]);
            return mx >= c.min_amount;
        }
        case CostType::RemoveFromCard:
            if (!entity.has_essences) return false;
            return entity.essences_on_card.can_afford(c.essences);
        case CostType::DiscardCard: {
            for (int he : st.get_player_hand(pid)) {
                const Entity& e = st.entities[he];
                if (c.exclude_entity_flags && (e.data->entity_flags & c.exclude_entity_flags)) continue;
                if (!c.matches_type_discard(e.data->card_type_mask)) continue;
                return true;
            }
            return false;
        }
        case CostType::DestroyComponent: {
            if (c.destroy_mode == DestroyMode::SELF) return true;
            if (c.destroy_mode == DestroyMode::ANY) return st.get_player_artifacts_in_play(pid).size() > 0;
            for (int ae : st.get_player_artifacts_in_play(pid)) if (ae != eid) return true;
            return false;
        }
        case CostType::DestroyCardType: {
            for (int ae : st.get_player_artifacts_in_play(pid)) {
                const EntityData* d = st.entities[ae].data;
                if (d && c.matches_type_discard(d->card_type_mask)) return true; // matches DRAGON/CREATURE bits
            }
            return false;
        }
        case CostType::TurnComponent: {
            if (c.turnable_type == TurnableType::MAGE) {
                for (int i = st.mage_start; i < st.mage_end; i++) {
                    const Entity& m = st.entities[i];
                    if (m.location == CardLocation::IN_PLAY && m.owner_id == pid) return !m.is_turned;
                }
                return false;
            }
            for (int ae : st.get_player_artifacts_in_play(pid)) {
                const Entity& art = st.entities[ae];
                int ctmbit = (c.turnable_type == TurnableType::DRAGON) ? CTM_DRAGON : CTM_CREATURE;
                if (art.data && (art.data->card_type_mask & ctmbit) && !art.is_turned) return true;
            }
            return false;
        }
        case CostType::SelectPlayer:
            if (c.opponent_only) return st.num_players > 1;
            return true;
        case CostType::SelectCard:
            return true;
    }
    return true;
}

static bool can_pay_all_costs(const GameState& st, int pid, int16_t eid, const Entity& entity, const Power& power) {
    for (const Cost& c : power.costs) if (!can_pay_cost(c, st, pid, eid, entity)) return false;
    return true;
}

// ---------------------------------------------------------------------------
// expansion helpers for UsePower / reacts (canonical_expand)
// ---------------------------------------------------------------------------
static Pool collect_fixed_gains(const Power& power, bool include_gain) {
    Pool fixed;
    for (const Effect& e : power.effects) {
        if (include_gain && e.type == EffectType::Gain) fixed.add_pool(e.essences);
        else if (e.type == EffectType::Store && e.amount == 0 && !e.what_spent && !e.on_target)
            fixed.add_pool(e.essences);
    }
    return fixed;
}

static Action mk(ActionType t, int pid) { Action a; a.type = t; a.pid = (uint8_t)pid; return a; }

// _expand_use_power
static void expand_use_power(const GameState& st, int pid, int16_t eid, int power_index,
                             const EidVec& valid_targets_in, std::vector<Action>& out) {
    const Entity& entity = st.entities[eid];
    if (!entity.data || power_index >= (int)entity.data->powers.size()) return;
    const Power& power = entity.data->powers[power_index];
    const Pool& player_pool = st.players[pid].pool;

    int any_cost = power.get_any_cost();
    Pool fixed_cost = power.get_essence_cost();
    bool excl[ESSENCE_COUNT]; power.get_any_cost_exclude(excl);
    int excl_mask = 0; for (int e = 0; e < ESSENCE_COUNT; e++) if (excl[e]) excl_mask |= (1 << e);

    const Cost* pay_identical = nullptr;
    for (const Cost& c : power.costs) if (c.type == CostType::PayIdentical) { pay_identical = &c; break; }

    int gain_any_amount = 0, gain_any_excl = 0;
    int store_any_amount = 0, store_any_excl = 0;
    bool store_what_spent = false, has_place = false;
    bool requires_player_target = false, player_opponent_only = false;
    bool gain_same_type = false, gain_gold_equal = false;
    bool gdc_as_any = false; int gdc_bonus = 0;
    int gain_gold_from_cost_divisor = 0;

    for (const Effect& e : power.effects) {
        switch (e.type) {
            case EffectType::GainAny:
                gain_any_amount = e.amount;
                for (int k = 0; k < e.exclude_count; k++) gain_any_excl |= (1 << (int)e.exclude[k]);
                break;
            case EffectType::Store:
                if (e.amount > 0) { store_any_amount = e.amount; for (int k = 0; k < e.exclude_count; k++) store_any_excl |= (1 << (int)e.exclude[k]); }
                if (e.what_spent) store_what_spent = true;
                break;
            case EffectType::Place: has_place = true; break;
            case EffectType::GainSameTypeAsSpent: gain_same_type = true; break;
            case EffectType::GainGoldEqualToSameSpent: gain_gold_equal = true; break;
            case EffectType::GainDestroyedCost: if (e.as_any) { gdc_as_any = true; gdc_bonus = e.bonus; } break;
            case EffectType::GainGoldFromCost: gain_gold_from_cost_divisor = e.divisor; break;
            default: break;
        }
    }
    for (const Cost& c : power.costs)
        if (c.type == CostType::SelectPlayer) { requires_player_target = true; player_opponent_only = c.opponent_only; }

    bool requires_target = false;
    for (const Cost& c : power.costs) {
        if (c.type == CostType::DestroyComponent && c.destroy_mode != DestroyMode::SELF) { requires_target = true; break; }
        if (c.type == CostType::TurnComponent) { requires_target = true; break; }
        if (c.type == CostType::DiscardCard) { requires_target = true; break; }
    }
    if (!requires_target)
        for (const Effect& e : power.effects) if (e.type == EffectType::Store && e.on_target) { requires_target = true; break; }

    EidVec valid_targets = valid_targets_in;
    const Cost* sc = power.get_select_card_cost();
    if (sc && sc->filter.exclude_self) {
        EidVec f; for (int t : valid_targets) if (t != eid) f.push(t); valid_targets = f;
    }

    // targets_to_use
    std::vector<int16_t> targets;
    for (int t : valid_targets) targets.push_back(t);
    if (!requires_target) targets.push_back(-1);
    if (targets.empty()) {
        if (requires_target) return;
        targets.push_back(-1);
    }

    auto emit = [&](int16_t target, int target_pid, const Pool& pay, const Pool& gain) {
        Action a = mk(ActionType::UsePower, pid);
        a.eid = eid; a.power_index = power_index;
        a.target_eid = target; a.target_pid = target_pid;
        a.pay = pay; a.gain = gain;
        out.push_back(a);
    };

    // PayIdentical branch
    if (pay_identical) {
        int base = pay_identical->base_cost;
        int min_x = pay_identical->min_amount;
        int min_total = base + min_x;
        int max_total = player_pool.total();
        std::vector<Pool> payment_choices;
        for (int total = min_total; total <= max_total; total++) {
            int x = total - base;
            auto handle_etype = [&](int etype) {
                if (player_pool[etype] >= x) {
                    Pool remaining = player_pool; remaining.v[etype] -= (int16_t)x;
                    std::vector<Pool> bases;
                    enumerate_essence_payments(remaining, base, 0, bases);
                    for (Pool bp : bases) {
                        bp.v[etype] += (int16_t)x;
                        if (player_pool.can_afford(bp)) payment_choices.push_back(bp);
                    }
                }
            };
            if (pay_identical->essence_type >= 0) handle_etype(pay_identical->essence_type);
            else for (int et = 0; et < ESSENCE_COUNT; et++) handle_etype(et);
        }
        std::vector<Pool> uniq;
        for (const Pool& p : payment_choices) { bool d = false; for (const Pool& q : uniq) if (q == p) { d = true; break; } if (!d) uniq.push_back(p); }
        if (uniq.empty()) uniq.push_back(Pool());
        for (const Pool& payment : uniq) {
            Pool gain;
            if (gain_gold_from_cost_divisor > 0) {
                int x = payment.total() - pay_identical->base_cost;
                gain.v[GOLD] = (int16_t)(x / gain_gold_from_cost_divisor);
            }
            Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index;
            a.pay = payment; a.gain = gain; out.push_back(a);
        }
        if (out.empty()) { Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index; out.push_back(a); }
        return;
    }

    if (gain_same_type) {
        int spend_types[5] = {ELAN, LIFE, CALM, DEATH, GOLD};
        int gain_types[4] = {ELAN, LIFE, CALM, DEATH};
        { Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index; out.push_back(a); }
        for (int sp : spend_types) {
            int maxn = player_pool[sp];
            for (int n = 1; n <= maxn; n++) {
                Pool spend; spend.v[sp] = (int16_t)n;
                for (int gt : gain_types) if (gt != sp) {
                    Pool gain; gain.v[gt] = (int16_t)n;
                    Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index;
                    a.pay = spend; a.gain = gain; out.push_back(a);
                }
            }
        }
        return;
    }

    if (gain_gold_equal) {
        int types[5] = {ELAN, LIFE, CALM, DEATH, GOLD};
        { Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index; out.push_back(a); }
        for (int sp : types) {
            int maxn = player_pool[sp];
            for (int n = 1; n <= maxn; n++) {
                Pool spend; spend.v[sp] = (int16_t)n;
                Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index;
                a.pay = spend; out.push_back(a);
            }
        }
        return;
    }

    if (store_what_spent && any_cost == 0 && fixed_cost.total() == 0) {
        int types[5] = {ELAN, LIFE, CALM, DEATH, GOLD};
        { Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index; out.push_back(a); }
        for (int et : types) {
            int maxn = player_pool[et];
            for (int n = 1; n <= maxn; n++) {
                Pool choice; choice.v[et] = (int16_t)n;
                Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index; a.pay = choice; out.push_back(a);
            }
        }
        int total_avail = 0; for (int et : types) total_avail += player_pool[et];
        if (total_avail > 0) {
            for (int total = 2; total < std::min(total_avail + 1, 6); total++) {
                std::vector<Pool> pays; enumerate_essence_payments(player_pool, total, 0, pays);
                for (const Pool& payment : pays) {
                    if (payment.total() == 0) continue;
                    int types_used = 0; for (int et : types) if (payment[et] > 0) types_used++;
                    if (types_used >= 2) {
                        Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index; a.pay = payment; out.push_back(a);
                    }
                }
            }
        }
        return;
    }

    // general path
    std::vector<Pool> payment_choices;
    bool has_any = any_cost > 0;
    bool has_fixed = fixed_cost.total() > 0;
    if (has_any) {
        Pool remaining = player_pool;
        for (int i = 0; i < ESSENCE_COUNT; i++) { remaining.v[i] -= fixed_cost[i]; if (remaining.v[i] < 0) remaining.v[i] = 0; }
        std::vector<Pool> anypays; enumerate_essence_payments(remaining, any_cost, excl_mask, anypays);
        for (Pool pay : anypays) {
            Pool total = fixed_cost; total.add_pool(pay);
            if (player_pool.can_afford(total)) payment_choices.push_back(total);
        }
    } else if (has_fixed) {
        payment_choices.push_back(fixed_cost);
    } else {
        payment_choices.push_back(Pool());
    }
    if (payment_choices.empty()) payment_choices.push_back(Pool());

    std::vector<Pool> gain_choices; gain_choices.push_back(Pool());
    if (gain_any_amount > 0) {
        gain_choices.clear(); get_gain_choices(gain_any_amount, gain_any_excl, gain_choices);
        if (gain_choices.empty()) gain_choices.push_back(Pool());
    }
    if (store_any_amount > 0 && gain_choices.size() == 1 && gain_choices[0].is_empty()) {
        gain_choices.clear(); get_gain_choices(store_any_amount, store_any_excl, gain_choices);
        if (gain_choices.empty()) gain_choices.push_back(Pool());
    }

    Pool fixed_gains = collect_fixed_gains(power, store_any_amount == 0);
    if (!fixed_gains.is_empty()) {
        std::vector<Pool> nc;
        for (const Pool& ch : gain_choices) { Pool m = fixed_gains; m.add_pool(ch); nc.push_back(m); }
        gain_choices = nc;
    }

    std::vector<int> player_targets; player_targets.push_back(-1);
    if (requires_player_target) {
        player_targets.clear();
        for (int i = 0; i < st.num_players; i++) if (!player_opponent_only || i != pid) player_targets.push_back(i);
    }

    if (has_place) {
        for (const Pool& payment : payment_choices)
            for (const Pool& gain : gain_choices)
                emit(-1, -1, payment, gain);
        if (out.empty()) { Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index; out.push_back(a); }
        return;
    }

    for (int16_t target : targets) {
        std::vector<Pool> tgain = gain_choices;
        if (gdc_as_any && target >= 0) {
            const Entity& te = st.entities[target];
            int destroyed_cost = 0;
            if (te.data) {
                int fx = te.data->has_placement_cost ? te.data->placement_cost.total() : 0;
                destroyed_cost = fx + te.data->placement_cost_any;
            }
            int gain_amount = destroyed_cost + gdc_bonus;
            if (gain_amount > 0) { tgain.clear(); get_gain_choices(gain_amount, 0, tgain); }
            if (tgain.empty()) tgain.push_back(Pool());
        }
        for (const Pool& payment : payment_choices)
            for (const Pool& gain : tgain)
                for (int ptarget : player_targets)
                    emit(target, ptarget, payment, gain);
    }
    if (out.empty()) { Action a = mk(ActionType::UsePower, pid); a.eid = eid; a.power_index = power_index; out.push_back(a); }
}

// react expansion common
static void expand_react_common(const GameState& st, int pid, int16_t eid, int power_index,
                                const EidVec& valid_targets, bool is_victory, const Pool& fixed_gain_for_life,
                                std::vector<Action>& out) {
    const Entity& entity = st.entities[eid];
    const Power& power = entity.data->powers[power_index];
    const Pool& player_pool = st.players[pid].pool;
    Pool fixed_cost = power.get_essence_cost();
    int any_cost = power.get_any_cost();
    int gain_amount = 0;
    for (const Effect& e : power.effects) if (e.type == EffectType::GainAny) { gain_amount = e.amount; break; }

    std::vector<int16_t> targets;
    for (int t : valid_targets) targets.push_back(t);
    if (targets.empty()) targets.push_back(-1);

    std::vector<Pool> payment_choices;
    if (any_cost > 0) {
        Pool remaining = player_pool;
        for (int i = 0; i < ESSENCE_COUNT; i++) { remaining.v[i] -= fixed_cost[i]; if (remaining.v[i] < 0) remaining.v[i] = 0; }
        std::vector<Pool> pays; enumerate_essence_payments(remaining, any_cost, 0, pays);
        for (Pool pay : pays) { Pool total = fixed_cost; total.add_pool(pay); if (player_pool.can_afford(total)) payment_choices.push_back(total); }
    } else {
        if (player_pool.can_afford(fixed_cost)) payment_choices.push_back(fixed_cost);
    }
    if (payment_choices.empty()) return;

    std::vector<Pool> gain_choices; bool has_gain = false;
    if (gain_amount > 0) { get_gain_choices(gain_amount, 0, gain_choices); has_gain = true; if (gain_choices.empty()) { gain_choices.clear(); has_gain = false; } }
    if (!has_gain) gain_choices.assign(1, Pool());

    for (int16_t target : targets)
        for (const Pool& payment : payment_choices) {
            Action a = mk(is_victory ? ActionType::VictoryReact : ActionType::LifeLossReact, pid);
            a.eid = eid; a.power_index = power_index; a.target_eid = target; a.pay = payment;
            if (!is_victory) a.gain = fixed_gain_for_life;
            out.push_back(a);
        }
}

// ---------------------------------------------------------------------------
// generate_actions  (get_available_actions + expand_action fused)
// ---------------------------------------------------------------------------
void generate_actions(const GameState& st, int pid, std::vector<Action>& out) {
    if (pid < 0 || pid >= st.num_players) return;
    if (st.phase == GamePhase::GAME_OVER) return;
    const PlayerState& player = st.players[pid];

    const PendingChoice* topp = nullptr;
    if (st.pending_count > 0 && st.pending[st.pending_count - 1].pid == pid)
        topp = &st.pending[st.pending_count - 1];

    if (topp) {
        switch (topp->type) {
            case PendingType::DiscardChoice: {
                // expand: combinations(hand, count)
                EidVec hand = st.get_player_hand(pid);
                int k = topp->count;
                int n = hand.size();
                std::vector<int> idx(k);
                for (int i = 0; i < k; i++) idx[i] = i;
                if (k <= n) {
                    while (true) {
                        Action a = mk(ActionType::DiscardChoice, pid);
                        int16_t tmp[16]; for (int i = 0; i < k; i++) tmp[i] = hand[idx[i]];
                        std::sort(tmp, tmp + k);
                        a.list_a_n = k; for (int i = 0; i < k; i++) a.list_a[i] = tmp[i];
                        out.push_back(a);
                        int i = k - 1;
                        while (i >= 0 && idx[i] == n - k + i) i--;
                        if (i < 0) break;
                        idx[i]++;
                        for (int j = i + 1; j < k; j++) idx[j] = idx[j - 1] + 1;
                    }
                }
                return;
            }
            case PendingType::ScryDeckChoice: {
                for (int dt = 0; dt < 2; dt++) {
                    Action a = mk(ActionType::ScryDeckChoice, pid);
                    a.scry_target = (DeckType)dt; out.push_back(a);
                }
                return;
            }
            case PendingType::ScryChoice: {
                int n = topp->eid_count;
                if (n == 0) { Action a = mk(ActionType::ScryChoice, pid); a.scry_order_n = 0; out.push_back(a); return; }
                int perm[12]; for (int i = 0; i < n; i++) perm[i] = i;
                do {
                    Action a = mk(ActionType::ScryChoice, pid);
                    a.scry_order_n = n; for (int i = 0; i < n; i++) a.scry_order[i] = (int8_t)perm[i];
                    out.push_back(a);
                } while (std::next_permutation(perm, perm + n));
                return;
            }
            case PendingType::VictoryReactChoice: {
                int16_t entity_id = topp->eid;
                const Entity& entity = st.entities[entity_id];
                const Power& power = entity.data->powers[topp->power_index];
                Pool ec = power.get_essence_cost();
                bool can_afford = player.pool.can_afford(ec);
                if (power.requires_target()) {
                    EidVec vt; get_valid_targets(st, pid, power, entity_id, vt);
                    if (vt.empty()) can_afford = false;
                }
                if (can_afford) {
                    EidVec vt; get_valid_targets(st, pid, power, entity_id, vt);
                    expand_react_common(st, pid, entity_id, topp->power_index, vt, true, Pool(), out);
                }
                Action d = mk(ActionType::Decline, pid); d.eid = entity_id; out.push_back(d);
                return;
            }
            case PendingType::LifeLossChoice: {
                // next life loss player must be pid
                int next_llp = -1;
                for (int i = st.pending_count - 1; i >= 0; i--)
                    if (st.pending[i].type == PendingType::LifeLossChoice) { next_llp = st.pending[i].pid; break; }
                if (next_llp != pid) return;
                // reacts
                int16_t source_eid = topp->source;
                bool source_is_dragon = false;
                if (source_eid >= 0) {
                    const Entity& se = st.entities[source_eid];
                    if (se.data) source_is_dragon = se.data->is_dragon();
                }
                EidVec comps = st.get_all_player_components(pid);
                for (int eid : comps) {
                    const Entity& entity = st.entities[eid];
                    for (int i = 0; i < (int)entity.data->powers.size(); i++) {
                        const Power& power = entity.data->powers[i];
                        bool usable = false;
                        if (!(entity.is_turned && power.requires_turn)) {
                            if (power.react_trigger == ReactTrigger::DAMAGE) usable = true;
                            else if (power.react_trigger == ReactTrigger::DRAGON_ATTACK && source_is_dragon) usable = true;
                        }
                        if (!usable) continue;
                        EidVec vt;
                        if (power.requires_target()) { get_valid_targets(st, pid, power, eid, vt); if (vt.empty()) continue; }
                        Pool ec = power.get_essence_cost();
                        if (!ec.is_empty() && !player.pool.can_afford(ec)) continue;
                        Pool fixed_gains = collect_fixed_gains(power, true);
                        expand_react_common(st, pid, eid, i, vt, false, fixed_gains, out);
                    }
                }
                // dragon defense reacts
                if (source_eid >= 0) {
                    const Entity& se = st.entities[source_eid];
                    if (se.data && se.data->is_dragon()) {
                        for (const Power& power : se.data->powers)
                            for (const Effect& ef : power.effects)
                                if (ef.type == EffectType::Damage && !ef.defense_options.empty())
                                    for (int di = 0; di < (int)ef.defense_options.size(); di++) {
                                        const Cost& dc = ef.defense_options[di];
                                        bool ok = false;
                                        if (dc.type == CostType::PayEssence) {
                                            ok = true;
                                            for (int e = 0; e < ESSENCE_COUNT; e++)
                                                if (dc.essences[e] > 0 && player.pool[e] < dc.essences[e]) { ok = false; break; }
                                        } else if (dc.type == CostType::DiscardCard) {
                                            for (int i = st.artifact_start; i < st.artifact_end; i++)
                                                if (st.entities[i].owner_id == pid && st.entities[i].location == CardLocation::HAND) { ok = true; break; }
                                        } else if (dc.type == CostType::DestroyComponent) {
                                            ok = st.get_player_artifacts_in_play(pid).size() > 0;
                                        }
                                        if (ok) {
                                            // expand dragon defense
                                            if (dc.type == CostType::PayEssence) {
                                                if (player.pool.can_afford(dc.essences)) {
                                                    Action a = mk(ActionType::LifeLossReact, pid); a.eid = source_eid; a.power_index = 0; a.pay = dc.essences; out.push_back(a);
                                                }
                                            } else if (dc.type == CostType::DiscardCard) {
                                                for (int he : st.get_player_hand(pid)) { Action a = mk(ActionType::LifeLossReact, pid); a.eid = source_eid; a.power_index = 0; a.target_eid = he; out.push_back(a); }
                                            } else if (dc.type == CostType::DestroyComponent) {
                                                for (int ae : st.get_player_artifacts_in_play(pid)) { Action a = mk(ActionType::LifeLossReact, pid); a.eid = source_eid; a.power_index = 0; a.target_eid = ae; out.push_back(a); }
                                            }
                                        }
                                    }
                    }
                }
                // payment options
                int amount = topp->amount;
                int life_avail = player.pool.life();
                int non_life_avail = player.pool.total() - life_avail;
                bool has_payment = false;
                for (int life_to_pay = 0; life_to_pay <= std::min(life_avail, amount); life_to_pay++) {
                    int rem = amount - life_to_pay;
                    int non_life_needed = rem * 2;
                    if (non_life_avail >= non_life_needed) {
                        // expand life loss choice: pay = life:life_to_pay + any over non-life essences
                        int any_count = non_life_needed;
                        int life_count = life_to_pay;
                        if (any_count == 0) {
                            Pool pool; pool.v[LIFE] = (int16_t)life_count;
                            Action a = mk(ActionType::LifeLossChoice, pid); a.pay = pool; out.push_back(a);
                        } else {
                            std::vector<Pool> anypays; enumerate_essence_payments(player.pool, any_count, (1 << LIFE), anypays);
                            for (Pool ap : anypays) {
                                Pool total = ap; total.add(LIFE, life_count);
                                if (player.pool.can_afford(total)) { Action a = mk(ActionType::LifeLossChoice, pid); a.pay = total; out.push_back(a); }
                            }
                        }
                        has_payment = true;
                    }
                }
                if (!has_payment) {
                    int total_ess = player.pool.total();
                    if (total_ess > 0) {
                        Pool total; total.v[LIFE] = (int16_t)life_avail;
                        for (int e = 0; e < ESSENCE_COUNT; e++) if (e != LIFE) total.v[e] = player.pool[e];
                        Action a = mk(ActionType::LifeLossChoice, pid); a.pay = total; out.push_back(a);
                    } else {
                        Action a = mk(ActionType::LifeLossChoice, pid); out.push_back(a);
                    }
                }
                return;
            }
            case PendingType::CollectCost: {
                int16_t entity_id = topp->eid;
                const Entity& entity = st.entities[entity_id];
                bool can_afford = player.pool.can_afford(topp->cost_essences);
                bool can_turn = topp->cost_turn && !entity.is_turned;
                bool any = false;
                if (can_afford) { Action a = mk(ActionType::CollectCost, pid); a.eid = entity_id; a.decision = CollectDecision::PAY_COST; out.push_back(a); any = true; }
                if (can_turn) { Action a = mk(ActionType::CollectCost, pid); a.eid = entity_id; a.decision = CollectDecision::PAY_TURN; out.push_back(a); any = true; }
                if (!any) { Action a = mk(ActionType::CollectCost, pid); a.eid = entity_id; a.decision = CollectDecision::DECLINE_COST; out.push_back(a); }
                return;
            }
            case PendingType::CollectStorage: {
                int16_t entity_id = topp->eid;
                Action t = mk(ActionType::TakeStored, pid); t.eid = entity_id; t.decision = CollectDecision::TAKE_STORED; out.push_back(t);
                Action d = mk(ActionType::TakeStored, pid); d.eid = entity_id; d.decision = CollectDecision::LEAVE_STORED; out.push_back(d);
                return;
            }
            case PendingType::Gain: {
                // _expand_pay
                int amount = topp->any_amount;
                int alt_amount = topp->alt_any_amount;
                int rmask = topp->restriction_mask;
                int16_t source = topp->eid;
                if (amount == 0 && alt_amount == 0) {
                    Action a = mk(ActionType::Gain, pid); a.eid = source; a.use_alt = false; out.push_back(a); return;
                }
                int valid_excl = rmask; // restriction_mask already marks invalid essences
                if (amount > 0) {
                    // valid_essences = those not restricted
                    std::vector<int> valid;
                    int order[5] = {ELAN, LIFE, CALM, DEATH, GOLD};
                    for (int e : order) if (!(rmask & (1 << e))) valid.push_back(e);
                    if (!valid.empty()) {
                        if (amount == 1) {
                            for (int e : valid) { Action a = mk(ActionType::Gain, pid); a.eid = source; Pool g; g.v[e] = 1; a.gain = g; out.push_back(a); }
                        } else {
                            // combinations_with_replacement over valid
                            std::vector<int> combo(amount, 0);
                            std::function<void(int,int)> rec = [&](int start, int depth) {
                                if (depth == amount) {
                                    Pool g; for (int c : combo) g.v[c] += 1;
                                    Action a = mk(ActionType::Gain, pid); a.eid = source; a.gain = g; out.push_back(a);
                                    return;
                                }
                                for (int i = start; i < (int)valid.size(); i++) { combo[depth] = valid[i]; rec(i, depth + 1); }
                            };
                            rec(0, 0);
                        }
                    } else {
                        std::vector<Pool> choices; get_gain_choices(amount, 0, choices);
                        for (const Pool& c : choices) { Action a = mk(ActionType::Gain, pid); a.eid = source; a.gain = c; out.push_back(a); }
                    }
                }
                if (alt_amount > 0) {
                    std::vector<Pool> choices; get_gain_choices(alt_amount, 0, choices);
                    for (const Pool& c : choices) { Action a = mk(ActionType::Gain, pid); a.eid = source; a.gain = c; a.use_alt = true; out.push_back(a); }
                }
                if (out.empty()) { Action a = mk(ActionType::Gain, pid); a.eid = source; out.push_back(a); }
                (void)valid_excl;
                return;
            }
            case PendingType::DrawRevealChoice: {
                int reveal_count = topp->reveal_count;
                Action base = mk(ActionType::ResolveDrawReveal, pid);
                base.list_a_n = topp->eid_count;
                for (int i = 0; i < topp->eid_count; i++) base.list_a[i] = topp->eids[i];
                if (reveal_count == 0) { base.list_b_n = 0; out.push_back(base); return; }
                EidVec unknown = st.get_unknown_deck_cards(topp->pid);
                if (unknown.empty()) { base.list_b_n = 0; out.push_back(base); return; }
                // combinations(unknown, reveal_count)
                int n = unknown.size(), k = reveal_count;
                std::vector<int> idx(k); for (int i = 0; i < k; i++) idx[i] = i;
                while (true) {
                    Action a = base; a.list_b_n = k; for (int i = 0; i < k; i++) a.list_b[i] = unknown[idx[i]];
                    out.push_back(a);
                    int i = k - 1; while (i >= 0 && idx[i] == n - k + i) i--;
                    if (i < 0) break; idx[i]++; for (int j = i + 1; j < k; j++) idx[j] = idx[j - 1] + 1;
                }
                return;
            }
            case PendingType::MonumentDrawChoice: {
                EidVec known = st.get_known_monument_deck();
                if (!known.empty()) { Action a = mk(ActionType::ResolveMonumentDraw, pid); a.eid = known[0]; out.push_back(a); }
                else for (int i = st.monument_start; i < st.monument_end; i++) {
                    const Entity& m = st.entities[i];
                    if (m.location == CardLocation::MONUMENT_DECK || m.location == CardLocation::OUT_OF_GAME) {
                        Action a = mk(ActionType::ResolveMonumentDraw, pid); a.eid = i; out.push_back(a);
                    }
                }
                return;
            }
            case PendingType::MonumentRevealChoice: {
                EidVec known = st.get_known_monument_deck();
                if (!known.empty()) { Action a = mk(ActionType::ResolveMonumentReveal, pid); a.eid = known[0]; out.push_back(a); }
                else for (int i = st.monument_start; i < st.monument_end; i++) {
                    const Entity& m = st.entities[i];
                    if (m.location == CardLocation::MONUMENT_DECK || m.location == CardLocation::OUT_OF_GAME) {
                        Action a = mk(ActionType::ResolveMonumentReveal, pid); a.eid = i; out.push_back(a);
                    }
                }
                return;
            }
            case PendingType::ScryRevealChoice: {
                EidVec unknown = (topp->deck_type == DeckType::MONUMENT)
                                     ? st.get_unknown_monument_deck() : st.get_unknown_deck_cards(topp->pid);
                int n = unknown.size(), k = topp->reveal_count;
                if (k <= n && k >= 0) {
                    std::vector<int> idx(k); for (int i = 0; i < k; i++) idx[i] = i;
                    if (k == 0) { Action a = mk(ActionType::ResolveScryReveal, pid); a.list_b_n = 0; out.push_back(a); return; }
                    while (true) {
                        Action a = mk(ActionType::ResolveScryReveal, pid); a.list_b_n = k;
                        for (int i = 0; i < k; i++) a.list_b[i] = unknown[idx[i]];
                        out.push_back(a);
                        int i = k - 1; while (i >= 0 && idx[i] == n - k + i) i--;
                        if (i < 0) break; idx[i]++; for (int j = i + 1; j < k; j++) idx[j] = idx[j - 1] + 1;
                    }
                }
                return;
            }
            case PendingType::PlacementChoice: {
                SelectCardLocation floc = topp->filter.location;
                EidVec targets;
                auto matches = [&](const Entity& e) {
                    if (!topp->filter.matches_card_type_mask(e.data->card_type_mask)) return false;
                    if (topp->p_free && e.data->cannot_be_free_placed()) return false;
                    return true;
                };
                if (floc == SelectCardLocation::HAND) {
                    for (int ae : st.get_player_hand(pid)) if (matches(st.entities[ae])) targets.push(ae);
                } else if (floc == SelectCardLocation::DISCARD) {
                    for (int ae : st.get_player_discard(pid)) if (matches(st.entities[ae])) targets.push(ae);
                } else if (floc == SelectCardLocation::ANY_DISCARD) {
                    for (int p = 0; p < st.num_players; p++)
                        for (int ae : st.get_player_discard(p)) if (matches(st.entities[ae])) targets.push(ae);
                }
                for (int ae : targets) {
                    const Entity& artifact = st.entities[ae];
                    if (topp->p_free) {
                        Action a = mk(ActionType::PlaceArtifact, pid); a.eid = ae; out.push_back(a);
                    } else {
                        int gb = calculate_gold_discount_budget(st, pid, artifact.data, topp->p_discount, topp->can_discount_gold);
                        std::vector<Pool> pays; get_valid_payments(st, pid, artifact.data, topp->p_discount, true, gb, pays);
                        for (const Pool& p : pays) { Action a = mk(ActionType::PlaceArtifact, pid); a.eid = ae; a.pay = p; out.push_back(a); }
                    }
                }
                Action d = mk(ActionType::Decline, pid); d.eid = topp->eid; out.push_back(d);
                return;
            }
            case PendingType::CollectPhaseCursor:
            case PendingType::LifeLossScan:
            case PendingType::GameSetupChoice:
                return;
        }
    }

    if (st.phase == GamePhase::SETUP_CHOOSE_MAGES) {
        for (int i = st.mage_start; i < st.mage_end; i++) {
            const Entity& m = st.entities[i];
            if (m.location == CardLocation::BEING_CHOSEN && m.owner_id == pid) {
                Action a = mk(ActionType::ChooseMage, pid); a.eid = i; out.push_back(a);
            }
        }
        return;
    }
    if (st.phase == GamePhase::SETUP_CHOOSE_ITEMS) {
        if (st.get_magic_item_selection_player() == pid)
            for (int item : st.get_available_magic_items()) { Action a = mk(ActionType::ChooseMagicItem, pid); a.eid = item; out.push_back(a); }
        return;
    }

    if (st.phase != GamePhase::ACTIONS) return;
    if (player.has_passed) return;
    if (st.current_player_index != pid) return;
    if (has_any_blocking_pending_choice(st)) return;

    // place artifacts from hand
    for (int ae : st.get_player_hand(pid)) {
        const EntityData* d = st.entities[ae].data;
        int gb = calculate_gold_discount_budget(st, pid, d, 0, false);
        std::vector<Pool> pays; get_valid_payments(st, pid, d, 0, true, gb, pays);
        for (const Pool& p : pays) { Action a = mk(ActionType::PlaceArtifact, pid); a.eid = ae; a.pay = p; out.push_back(a); }
    }

    if (player.pool.gold() >= 4) {
        for (int me : st.get_monument_display()) { Action a = mk(ActionType::ClaimMonument, pid); a.eid = me; out.push_back(a); }
        if (st.get_top_monument_from_deck() >= 0) { Action a = mk(ActionType::ClaimTopMonument, pid); out.push_back(a); }
    }

    for (int i = st.pop_start; i < st.pop_end; i++) {
        const Entity& pop = st.entities[i];
        if (pop.location != CardLocation::AVAILABLE) continue;
        std::vector<Pool> pays; get_valid_payments(st, pid, pop.data, 0, false, 0, pays);
        for (const Pool& p : pays) { Action a = mk(ActionType::ClaimPlaceOfPower, pid); a.eid = i; a.pay = p; out.push_back(a); }
    }

    for (int ae : st.get_player_hand(pid)) {
        // discard for essences expansion
        int16_t e = ae;
        { Action a = mk(ActionType::DiscardForEssences, pid); a.eid = e; a.gain = Pool(); a.gain.v[GOLD] = 1; out.push_back(a); }
        int ng[4] = {ELAN, LIFE, CALM, DEATH};
        for (int i = 0; i < 4; i++) for (int j = i; j < 4; j++) {
            Pool g; g.add(ng[i], 1); g.add(ng[j], 1);
            Action a = mk(ActionType::DiscardForEssences, pid); a.eid = e; a.gain = g; out.push_back(a);
        }
    }

    // use power
    EidVec comps = st.get_all_player_components(pid);
    for (int eid : comps) {
        const Entity& entity = st.entities[eid];
        for (int i = 0; i < (int)entity.data->powers.size(); i++) {
            const Power& power = entity.data->powers[i];
            if (power.is_react()) continue;
            if (entity.is_turned && !power.usable_when_turned) continue;
            if (!can_pay_all_costs(st, pid, eid, entity, power)) continue;
            bool needs_deck = false;
            for (const Effect& e : power.effects) if (e.type == EffectType::Draw && e.require_deck_has_cards) needs_deck = true;
            if (needs_deck && st.get_player_deck_count(pid) == 0) continue;
            EidVec vt;
            if (power.requires_target()) {
                get_valid_targets(st, pid, power, eid, vt);
                bool has_turn_cost = power.has_turn_component_cost(TurnableType::MAGE) ||
                                     power.has_turn_component_cost(TurnableType::DRAGON) ||
                                     power.has_turn_component_cost(TurnableType::CREATURE);
                if (has_turn_cost && vt.empty()) continue;
            }
            expand_use_power(st, pid, eid, i, vt, out);
        }
    }

    // pass
    bool has_magic_item = false;
    for (int i = st.magic_item_start; i < st.magic_item_end; i++) {
        const Entity& it = st.entities[i];
        if (it.location == CardLocation::IN_PLAY && it.owner_id == pid) { has_magic_item = true; break; }
    }
    if (has_magic_item) {
        for (int item : st.get_available_magic_items()) { Action a = mk(ActionType::Pass, pid); a.eid = item; out.push_back(a); }
    } else {
        Action a = mk(ActionType::Pass, pid); a.eid = SENTINEL_EID; out.push_back(a);
    }
}

bool node_is_chance(const GameState& st) {
    if (st.pending_count == 0) return false;
    PendingType t = st.pending[st.pending_count - 1].type;
    return t == PendingType::DrawRevealChoice || t == PendingType::ScryRevealChoice ||
           t == PendingType::MonumentDrawChoice || t == PendingType::MonumentRevealChoice;
}

} // namespace ra
