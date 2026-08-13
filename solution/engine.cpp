// Game engine: action handlers, cost/effect execution, phase transitions,
// the collect phase, victory check, target enumeration, and the top-level
// execute_action dispatcher. Mirrors reference/engine/*.
#include "engine.hpp"
#include <algorithm>

namespace ra {

// ===========================================================================
// Power::requires_target  (mirrors power.py)
// ===========================================================================
bool Power::requires_target() const {
    const Cost* sc = get_select_card_cost();
    if (sc && sc->filter.has_filter()) return true;
    if (has_cost(CostType::DiscardCard)) return true;
    if (has_destroy_component_cost(DestroyMode::ANY)) return true;
    if (has_destroy_component_cost(DestroyMode::ANOTHER)) return true;
    if (has_cost(CostType::DestroyCardType)) return true;
    if (has_turn_component_cost(TurnableType::MAGE) ||
        has_turn_component_cost(TurnableType::DRAGON) ||
        has_turn_component_cost(TurnableType::CREATURE)) return true;
    for (const Effect& e : effects) {
        if (e.type == EffectType::Straighten && e.straighten_target == StraightenTarget::SELECTED) return true;
        if (e.type == EffectType::GainFromOpponent) return true;
        if (e.type == EffectType::Place) return true;
        if (e.type == EffectType::Store && e.on_target) return true;
    }
    return false;
}

// ===========================================================================
// Victory points (mirrors game_engine.calculate_victory_points)
// ===========================================================================
int calculate_victory_points(const GameState& state, int pid) {
    int vp = 0;
    if (state.players[pid].has_first_player_token) vp += 1;

    int artifact_count = 0, vp_per_two = 0;
    int dragon_count = 0, creature_count = 0;   // cached to avoid re-scanning below
    EidVec arts = state.get_player_artifacts_in_play(pid);
    for (int eid : arts) {
        const EntityData* d = state.entities[eid].data;
        artifact_count++;
        vp += d->victory_points;
        if (d->victory_points_per_two_artifacts > 0) vp_per_two = d->victory_points_per_two_artifacts;
        if (d->is_dragon())   dragon_count++;
        if (d->is_creature()) creature_count++;
    }
    if (vp_per_two > 0) vp += (artifact_count / 2) * vp_per_two;

    for (int eid : state.get_player_monuments(pid)) {
        const Entity& mon = state.entities[eid];
        vp += mon.data->victory_points;
        if (mon.has_essences)
            for (int i = 0; i < ESSENCE_COUNT; i++)
                vp += mon.essences_on_card[i] * mon.data->points_per_essence[i];
    }

    for (int eid : state.get_player_places_of_power(pid)) {
        const Entity& pop = state.entities[eid];
        const EntityData* d = pop.data;
        vp += d->base_points;
        if (pop.has_essences)
            for (int i = 0; i < ESSENCE_COUNT; i++)
                vp += pop.essences_on_card[i] * d->points_per_essence[i];
        // Use pre-computed counts — avoids re-scanning artifact range 2-3x per PoP
        if (d->vp_per_dragon > 0)            vp += dragon_count   * d->vp_per_dragon;
        if (d->vp_per_creature > 0)          vp += creature_count * d->vp_per_creature;
        if (d->vp_per_artifact_count_num > 0)
            vp += (artifact_count * d->vp_per_artifact_count_num) / d->vp_per_artifact_count_denom;
    }

    vp += state.temp_vp[pid];
    return vp;
}

// ===========================================================================
// essences_on_card helpers (None  <=>  !has_essences)
// ===========================================================================
static inline bool eoc_present_nonempty(const Entity& e) {
    return e.has_essences && e.essences_on_card.total() > 0;
}
static inline void eoc_set_none(Entity& e) { e.has_essences = false; e.essences_on_card = Pool(); }
static inline void eoc_add_pool(Entity& e, const Pool& p) {
    if (!e.has_essences) { e.has_essences = true; e.essences_on_card = Pool(); }
    e.essences_on_card.add_pool(p);
}
static inline void eoc_add(Entity& e, int essence, int amt) {
    if (!e.has_essences) { e.has_essences = true; e.essences_on_card = Pool(); }
    e.essences_on_card.add(essence, amt);
}

// ===========================================================================
// draw_card (mirrors game_state.draw_card)
// ===========================================================================
int draw_card(GameState& state, int pid, int count) {
    if (count <= 0) return 0;
    int deck_size = state.get_player_deck_count(pid);
    int discard_size = state.get_player_discard(pid).size();
    int actual = std::min(count, deck_size + discard_size);
    if (actual == 0) return 0;

    EidVec known = state.get_known_deck_cards(pid);
    int known_draws = std::min(known.size(), actual);
    int unknown_draws = actual - known_draws;

    if (unknown_draws > 0) {
        int unknown_in_deck = state.get_unknown_deck_cards(pid).size();
        if (unknown_draws > unknown_in_deck) {
            for (int i = state.artifact_start; i < state.artifact_end; i++) {
                Entity& a = state.entities[i];
                if (a.location == CardLocation::DISCARD && a.owner_id == pid) {
                    a.location = CardLocation::DECK;
                    a.order_index = UNKNOWN_ORDER;
                }
            }
        }
    }

    PendingChoice p{};
    p.type = PendingType::DrawRevealChoice;
    p.pid = (uint8_t)pid;
    p.eid_count = known_draws;
    for (int i = 0; i < known_draws; i++) p.eids[i] = known[i];
    p.reveal_count = unknown_draws;
    state.push_pending(p);
    return actual;
}

// ===========================================================================
// target enumeration (mirrors game_engine.get_targets_from_filter / get_valid_targets)
// ===========================================================================
// mirrors select_card_filter.should_include_component
static bool scf_should_include(const SelectCardFilter& f, ComponentType ct) {
    switch (ct) {
        case ComponentType::ARTIFACT:
            return f.allows_component_type(ComponentType::ARTIFACT);
        case ComponentType::MAGE:
            return f.allows_component_type(ComponentType::MAGE) ||
                   (f.component_type_mask == 0 && f.card_type_mask == 0);
        case ComponentType::PLACE_OF_POWER:
        case ComponentType::MONUMENT:
        case ComponentType::MAGIC_ITEM:
            return f.component_type_mask == 0 && f.card_type_mask == 0;
    }
    return false;
}

static void get_targets_from_filter(const GameState& state, int pid, const SelectCardFilter& f,
                                    const Power* power, int16_t source_eid, EidVec& out) {
    switch (f.location) {
        case SelectCardLocation::NONE: break;
        case SelectCardLocation::IN_PLAY: {
            EidVec comps = state.get_all_player_components(pid);
            for (int eid : comps) {
                const Entity& e = state.entities[eid];
                if (!scf_should_include(f, e.kind)) continue;
                // matches_entity
                if (!f.matches_tapped_state(e.is_turned)) continue;
                if (e.kind == ComponentType::ARTIFACT && !f.matches_card_type_mask(e.data->card_type_mask)) continue;
                out.push(eid);
            }
            break;
        }
        case SelectCardLocation::DISCARD: {
            for (int eid : state.get_player_discard(pid)) {
                const Entity& e = state.entities[eid];
                if (!f.matches_tapped_state(e.is_turned)) continue;
                if (e.kind == ComponentType::ARTIFACT && !f.matches_card_type_mask(e.data->card_type_mask)) continue;
                out.push(eid);
            }
            break;
        }
        case SelectCardLocation::MONUMENT: {
            for (int eid : state.get_monument_display()) out.push(eid);
            int16_t top = state.get_top_monument_from_deck();
            if (top >= 0) out.push(top);
            break;
        }
        default: break; // HAND/ANY_DISCARD unreachable for CostSelectCard
    }

    if (power && power->requires_turn && f.require_tapped && source_eid >= 0 && !out.contains(source_eid)) {
        const Entity& src = state.entities[source_eid];
        if (!src.is_turned && f.matches_card_type_mask(src.data->card_type_mask))
            out.push(source_eid);
    }
}

void get_valid_targets(const GameState& state, int pid, const Power& power,
                       int16_t source_eid, EidVec& out) {
    EidVec raw;
    const Cost* sc = power.get_select_card_cost();
    if (sc && sc->filter.has_filter()) {
        get_targets_from_filter(state, pid, sc->filter, &power, source_eid, raw);
        // dedupe-preserving (filter path returns directly in reference)
        for (int t : raw) if (!out.contains(t)) out.push(t);
        return;
    }
    for (const Effect& e : power.effects) if (e.type == EffectType::Place) return;

    if (power.has_turn_component_cost(TurnableType::MAGE)) {
        for (int i = state.mage_start; i < state.mage_end; i++) {
            const Entity& m = state.entities[i];
            if (m.location == CardLocation::IN_PLAY && m.owner_id == pid && !m.is_turned) raw.push(i);
        }
    }
    if (power.has_turn_component_cost(TurnableType::DRAGON))
        for (int e : state.get_straightened_of_type(pid, TurnableType::DRAGON)) raw.push(e);
    if (power.has_turn_component_cost(TurnableType::CREATURE))
        for (int e : state.get_straightened_of_type(pid, TurnableType::CREATURE)) raw.push(e);

    const Cost* discard = power.get_cost(CostType::DiscardCard);
    if (discard) {
        for (int eid : state.get_player_hand(pid)) {
            const Entity& e = state.entities[eid];
            if (discard->exclude_entity_flags && (e.data->entity_flags & discard->exclude_entity_flags)) continue;
            if (discard->card_type_mask && !discard->matches_type_discard(e.data->card_type_mask)) continue;
            raw.push(eid);
        }
    }
    if (power.has_destroy_component_cost(DestroyMode::ANY))
        for (int e : state.get_player_artifacts_in_play(pid)) raw.push(e);
    if (power.has_destroy_component_cost(DestroyMode::ANOTHER))
        for (int e : state.get_player_artifacts_in_play(pid)) if (e != source_eid) raw.push(e);

    const Cost* dct = power.get_cost(CostType::DestroyCardType);
    int dmask = dct ? dct->card_type_mask : 0;
    if (dmask) {
        for (int eid : state.get_player_artifacts_in_play(pid)) {
            const EntityData* d = state.entities[eid].data;
            bool matches = false;
            if ((dmask & CTM_CREATURE) && d->is_creature()) matches = true;
            if ((dmask & CTM_DRAGON) && d->is_dragon()) matches = true;
            if (matches) raw.push(eid);
        }
    }
    for (int t : raw) if (!out.contains(t)) out.push(t);
}

// ===========================================================================
// PowerContext + cost/effect execution
// ===========================================================================
struct PowerCtx {
    GameState* state;
    int pid;
    int16_t eid = -1;
    int16_t target_eid = -1;
    int target_pid = -1;
    const Pool* pay_essence_cost = nullptr;
    Pool pay;
    Pool gain;
    int identical_amount = 0;
    Entity* entity = nullptr;
    PlayerState& player() { return state->players[pid]; }
};

static void scan_for_victory_react_powers(GameState& state, int triggered_by); // fwd
static void finalize_victory_check(GameState& state);                          // fwd

static void pay_cost(const Cost& c, PowerCtx& ctx) {
    GameState& st = *ctx.state;
    switch (c.type) {
        case CostType::PayEssence: {
            const Pool& choice = ctx.pay;
            if (choice.is_empty()) {
                RA_CHECK(c.any_amount == 0);
                if (c.essences.total() > 0) ctx.player().pool.pay(c.essences);
                return;
            }
            if (c.any_amount == 0) {
                RA_CHECK(choice == c.essences);
                ctx.player().pool.pay(choice);
                return;
            }
            for (int e = 0; e < ESSENCE_COUNT; e++) RA_CHECK(choice[e] >= c.essences[e]);
            int required = c.essences.total() + c.any_amount;
            RA_CHECK(choice.total() == required);
            for (int k = 0; k < c.exclude_count; k++) {
                int ex = (int)c.exclude[k];
                RA_CHECK(choice[ex] <= c.essences[ex]);
            }
            ctx.player().pool.pay(choice);
            return;
        }
        case CostType::TurnComponent: {
            RA_CHECK(ctx.target_eid >= 0);
            EidVec str = st.get_straightened_of_type(ctx.pid, c.turnable_type);
            RA_CHECK(str.contains(ctx.target_eid));
            st.entities[ctx.target_eid].is_turned = true;
            return;
        }
        case CostType::RemoveFromCard: {
            if (ctx.entity->has_essences) ctx.entity->essences_on_card.pay(c.essences);
            return;
        }
        case CostType::PayIdentical: {
            const Pool& choice = ctx.pay;
            int total = choice.total();
            int x = total - c.base_cost;
            RA_CHECK(x >= c.min_amount);
            if (c.essence_type >= 0) {
                RA_CHECK(choice[c.essence_type] >= x);
            } else {
                bool found = false;
                for (int e = 0; e < ESSENCE_COUNT; e++) if (choice[e] >= x) { found = true; break; }
                RA_CHECK(found);
            }
            RA_CHECK(ctx.player().pool.can_afford(choice));
            ctx.player().pool.pay(choice);
            ctx.identical_amount = x;
            return;
        }
        case CostType::DestroyComponent: {
            if (c.destroy_mode == DestroyMode::SELF) {
                RA_CHECK(ctx.eid >= 0);
                ctx.entity->location = CardLocation::DISCARD;
                eoc_set_none(*ctx.entity);
            } else if (c.destroy_mode == DestroyMode::ANY) {
                EidVec in_play = st.get_player_artifacts_in_play(ctx.pid);
                int destroyed;
                if (ctx.target_eid >= 0 && in_play.contains(ctx.target_eid)) destroyed = ctx.target_eid;
                else { RA_CHECK(!in_play.empty()); destroyed = in_play[0]; }
                Entity& de = st.entities[destroyed];
                de.location = CardLocation::DISCARD;
                eoc_set_none(de);
            } else { // ANOTHER
                EidVec in_play = st.get_player_artifacts_in_play(ctx.pid);
                RA_CHECK(ctx.target_eid >= 0);
                RA_CHECK(ctx.target_eid != ctx.eid);
                RA_CHECK(in_play.contains(ctx.target_eid));
                Entity& de = st.entities[ctx.target_eid];
                de.location = CardLocation::DISCARD;
                eoc_set_none(de);
            }
            return;
        }
        case CostType::DestroyCardType: {
            RA_CHECK(ctx.target_eid >= 0);
            EidVec in_play = st.get_player_artifacts_in_play(ctx.pid);
            RA_CHECK(in_play.contains(ctx.target_eid));
            Entity& e = st.entities[ctx.target_eid];
            bool matches = ((c.card_type_mask & CTM_DRAGON) && e.data->is_dragon()) ||
                           ((c.card_type_mask & CTM_CREATURE) && e.data->is_creature());
            RA_CHECK(matches);
            e.location = CardLocation::DISCARD;
            eoc_set_none(e);
            return;
        }
        case CostType::DiscardCard: {
            RA_CHECK(ctx.target_eid >= 0);
            EidVec hand = st.get_player_hand(ctx.pid);
            RA_CHECK(hand.contains(ctx.target_eid));
            Entity& e = st.entities[ctx.target_eid];
            RA_CHECK(!(c.exclude_entity_flags && (e.data->entity_flags & c.exclude_entity_flags)));
            RA_CHECK(c.matches_type_discard(e.data->card_type_mask));
            e.location = CardLocation::DISCARD;
            return;
        }
        case CostType::SelectPlayer:
            RA_CHECK(ctx.target_pid >= 0);
            RA_CHECK(ctx.target_pid < st.num_players);
            if (c.opponent_only) RA_CHECK(ctx.target_pid != ctx.pid);
            return;
        case CostType::SelectCard:
            if (ctx.target_eid >= 0) RA_CHECK(ctx.target_eid < st.entity_count);
            return;
    }
}

static void exec_effect(const Effect& ef, PowerCtx& ctx) {
    GameState& st = *ctx.state;
    switch (ef.type) {
        case EffectType::Gain:
            if (!ef.essences.is_empty()) ctx.player().pool.add_pool(ef.essences);
            return;
        case EffectType::GainAny: {
            const Pool& g = ctx.gain;
            RA_CHECK(!g.is_empty());
            RA_CHECK(g.total() == ef.amount);
            RA_CHECK(g.gold() == 0);
            for (int k = 0; k < ef.exclude_count; k++) RA_CHECK(g[(int)ef.exclude[k]] == 0);
            ctx.player().pool.add_pool(g);
            return;
        }
        case EffectType::Store: {
            Entity* target = (ef.on_target && ctx.target_eid >= 0) ? &st.entities[ctx.target_eid] : ctx.entity;
            RA_CHECK(!ef.on_target || ctx.target_eid >= 0);
            if (!ef.essences.is_empty()) eoc_add_pool(*target, ef.essences);
            if (ef.amount > 0) {  // Python: `if any_amount>0 and ctx.gain` — gain (5-list) is always truthy
                RA_CHECK(ctx.gain.total() == ef.amount);
                for (int k = 0; k < ef.exclude_count; k++) RA_CHECK(ctx.gain[(int)ef.exclude[k]] == 0);
                eoc_add_pool(*target, ctx.gain);
            }
            if (ef.what_spent) {
                Pool spent = ctx.pay;  // Python: `ctx.pay if ctx.pay else essence_cost` — pay always truthy
                if (!spent.is_empty()) {
                    if (ctx.pay_essence_cost == nullptr) ctx.player().pool.pay(ctx.pay);
                    eoc_add_pool(*target, spent);
                }
            }
            return;
        }
        case EffectType::RivalsGain: {
            if (ef.essences.is_empty()) return;
            for (int p = 0; p < st.num_players; p++)
                if (p != ctx.pid) st.players[p].pool.add_pool(ef.essences);
            return;
        }
        case EffectType::Damage: {
            RA_CHECK(ef.amount > 0);
            PendingChoice p{};
            p.type = PendingType::LifeLossScan;
            p.source = ctx.eid;
            p.amount = ef.amount;
            p.next_offset = ef.include_self ? 0 : 1;
            p.pid = (uint8_t)ctx.pid;
            p.include_self = ef.include_self;
            p.all_players = ef.all_players;
            st.push_pending(p);
            return;
        }
        case EffectType::Draw: {
            RA_CHECK(ef.amount > 0);
            if (ef.require_deck_has_cards) RA_CHECK(st.get_player_deck_count(ctx.pid) > 0);
            int actual = draw_card(st, ctx.pid, ef.amount);
            if (ef.discard_after > 0) {
                int shortfall = ef.amount - actual;
                int actual_discards = std::max(0, ef.discard_after - shortfall);
                if (actual_discards > 0) {
                    RA_CHECK(ctx.eid >= 0);
                    PendingChoice p{};
                    p.type = PendingType::DiscardChoice;
                    p.pid = (uint8_t)ctx.pid;
                    p.count = actual_discards;
                    p.eid = ctx.eid;
                    st.insert_pending_front(p);
                }
            }
            return;
        }
        case EffectType::IgnoreDamage: return;
        case EffectType::CheckVictory: {
            st.is_mid_round_victory_check = true;
            st.begin_victory_check();
            scan_for_victory_react_powers(st, ctx.pid);
            // scan_for_victory_react_powers pushes reacts; detect if any pushed
            bool any = false;
            for (int i = 0; i < st.pending_count; i++)
                if (st.pending[i].type == PendingType::VictoryReactChoice) { any = true; break; }
            if (any) { st.pending_turn_advance = true; return; }
            finalize_victory_check(st);
            return;
        }
        case EffectType::Straighten: {
            if (ef.straighten_target == StraightenTarget::SELF) ctx.entity->is_turned = false;
            else if (ef.straighten_target == StraightenTarget::SELECTED && ctx.target_eid >= 0) {
                if (ctx.target_eid >= 0 && ctx.target_eid < st.entity_count) {
                    Entity& e = st.entities[ctx.target_eid];
                    if (e.owner_id == ctx.pid) e.is_turned = false;
                }
            }
            return;
        }
        case EffectType::Scry: {
            RA_CHECK(ef.amount > 0);
            RA_CHECK(ctx.eid >= 0);
            PendingChoice p{};
            p.type = PendingType::ScryDeckChoice;
            p.pid = (uint8_t)ctx.pid;
            p.scry_count = ef.amount;
            p.eid = ctx.eid;
            st.push_pending(p);
            return;
        }
        case EffectType::Place: {
            RA_CHECK(ctx.eid >= 0);
            PendingChoice p{};
            p.type = PendingType::PlacementChoice;
            p.pid = (uint8_t)ctx.pid;
            p.eid = ctx.eid;
            p.filter = ef.filter;
            p.p_discount = ef.discount;
            p.p_free = ef.free;
            p.can_discount_gold = ef.can_discount_gold;
            st.push_pending(p);
            return;
        }
        case EffectType::GainDestroyedCost: {
            if (ctx.target_eid < 0) return;
            const Entity& art = st.entities[ctx.target_eid];
            int base_value = art.data->total_placement_cost();
            if (ef.as_gold) {
                ctx.player().pool.add(GOLD, base_value);
            } else if (ef.as_any) {
                int any_value = base_value + ef.bonus;
                if (any_value > 0) {
                    if (!ctx.gain.is_empty() && ctx.gain.total() == any_value) {
                        RA_CHECK(ctx.gain.gold() == 0);
                        ctx.player().pool.add_pool(ctx.gain);
                    } else {
                        PendingChoice p{};
                        p.type = PendingType::Gain;
                        p.pid = (uint8_t)ctx.pid;
                        p.any_amount = any_value;
                        p.restriction_mask = (1 << GOLD);
                        p.eid = ctx.eid;
                        st.push_pending(p);
                    }
                }
            }
            return;
        }
        case EffectType::GainGoldEqualToSameSpent: {
            if (ctx.pay.is_empty() || ctx.pay.total() == 0) return;
            int nz = 0;
            for (int e = 0; e < ESSENCE_COUNT; e++) if (ctx.pay[e] > 0) nz++;
            RA_CHECK(nz == 1);
            RA_CHECK(ctx.player().pool.can_afford(ctx.pay));
            int same = ctx.pay.total();
            ctx.player().pool.pay(ctx.pay);
            ctx.player().pool.add(GOLD, same);
            return;
        }
        case EffectType::GainFromOpponent: {
            if (ef.their_essence < 0 || ef.your_essence < 0) return;
            if (ctx.target_pid < 0 || ctx.target_pid == ctx.pid) return;
            int count = st.players[ctx.target_pid].pool[ef.their_essence];
            if (count > 0) ctx.player().pool.add(ef.your_essence, count);
            return;
        }
        case EffectType::GainSameTypeAsSpent: {
            if (ctx.pay.is_empty() || ctx.pay.total() == 0) return;
            int nz = 0; for (int e = 0; e < ESSENCE_COUNT; e++) if (ctx.pay[e] > 0) nz++;
            RA_CHECK(nz == 1);
            RA_CHECK(ctx.player().pool.can_afford(ctx.pay));
            int spent = ctx.pay.total();
            RA_CHECK(!ctx.gain.is_empty());
            RA_CHECK(ctx.gain.total() == spent);
            int gz = 0, gtype = -1;
            for (int e = 0; e < ESSENCE_COUNT; e++) if (ctx.gain[e] > 0) { gz++; gtype = e; }
            RA_CHECK(gz == 1);
            RA_CHECK(gtype != GOLD);
            ctx.player().pool.pay(ctx.pay);
            ctx.player().pool.add_pool(ctx.gain);
            return;
        }
        case EffectType::TempVP:
            st.temp_vp[ctx.pid] += ef.amount;
            return;
        case EffectType::GainGoldFromCost: {
            int amount = ctx.identical_amount;
            int gold_gained = amount / ef.divisor;
            RA_CHECK(ctx.gain.gold() == gold_gained);
            if (gold_gained > 0) ctx.player().pool.add(GOLD, gold_gained);
            return;
        }
    }
}

// ===========================================================================
// collect-phase helpers (mirrors game_engine)
// ===========================================================================
static void build_stored_into(const Pool& stored, PendingChoice& p) {
    p.stored = stored;  // essence->amount; has_stored = total>0
}

static void apply_collect(GameState& st, int pid, const EntityData* d, int16_t source) {
    if (!d->has_collect) return;
    const CollectAbility& c = d->collect_ability;
    PlayerState& player = st.players[pid];
    if (!c.essences.is_empty()) player.pool.add_pool(c.essences);
    if (c.any_amount > 0) {
        PendingChoice p{};
        p.type = PendingType::Gain; p.pid = (uint8_t)pid;
        p.any_amount = c.any_amount; p.restriction_mask = c.restriction_mask; p.eid = source;
        st.push_pending(p);
    }
    if (c.choice_mask != 0) {
        PendingChoice p{};
        p.type = PendingType::Gain; p.pid = (uint8_t)pid;
        p.any_amount = 1; p.restriction_mask = c.choice_mask_to_restriction(); p.eid = source;
        st.push_pending(p);
    }
}

static void push_collect_storage(GameState& st, int pid, const EntityData* d, Entity& entity, int16_t eid) {
    PendingChoice p{};
    p.type = PendingType::CollectStorage; p.pid = (uint8_t)pid; p.eid = eid;
    build_stored_into(entity.essences_on_card, p);
    p.has_natural = true;
    p.natural_count = 0;
    if (d->has_collect) {
        const CollectAbility& c = d->collect_ability;
        if (!c.essences.is_empty())
            for (int i = 0; i < ESSENCE_COUNT; i++)
                if (c.essences[i] > 0) {
                    NaturalCollectOption& n = p.natural[p.natural_count++];
                    n = NaturalCollectOption{}; n.essence = (int8_t)i; n.amount = c.essences[i];
                    n.option_type = CollectOptionType::FIXED_ESSENCE;
                }
        if (c.any_amount > 0) {
            NaturalCollectOption& n = p.natural[p.natural_count++];
            n = NaturalCollectOption{}; n.option_type = CollectOptionType::ANY; n.amount = c.any_amount;
            n.restriction_mask = c.restriction_mask;
        }
        if (c.choice_mask != 0) {
            NaturalCollectOption& n = p.natural[p.natural_count++];
            n = NaturalCollectOption{}; n.option_type = CollectOptionType::ANY; n.amount = 1;
            n.restriction_mask = c.choice_mask_to_restriction();
            n.alt_any_amount = c.alt_any_amount; n.alt_restriction_mask = c.restriction_mask;
        } else if (c.alt_any_amount > 0) {
            NaturalCollectOption& n = p.natural[p.natural_count++];
            n = NaturalCollectOption{}; n.option_type = CollectOptionType::ANY; n.amount = c.alt_any_amount;
            n.restriction_mask = c.restriction_mask;
        }
    }
    st.push_pending(p);
}

static void offer_take_stored(GameState& st, int pid, Entity& entity, int16_t eid) {
    if (entity.essences_on_card.total() <= 0) return; // build_stored_options empty -> skip
    PendingChoice p{};
    p.type = PendingType::CollectStorage; p.pid = (uint8_t)pid; p.eid = eid;
    build_stored_into(entity.essences_on_card, p);
    p.has_natural = false; p.natural_count = 0; p.bonus_multiplier = 0;
    st.push_pending(p);
}

static void push_per_stored_pay(GameState& st, int pid, const CollectAbility& c, Entity& entity, int16_t eid) {
    PendingChoice p{};
    p.type = PendingType::CollectStorage; p.pid = (uint8_t)pid; p.eid = eid;
    build_stored_into(entity.essences_on_card, p);
    p.has_natural = false; p.natural_count = 0;
    p.bonus_multiplier = c.per_stored_essence_multiplier;
    st.push_pending(p);
}

static void advance_collect_phase(GameState& st) {
    int cursor_idx = st.pending_count - 1;
    PendingChoice cursor = st.pending[cursor_idx];
    int player_val = cursor.player, comp_idx = cursor.component_index, pass_num = cursor.pass_num;

    while (true) {
        if (player_val >= st.num_players) { st.erase_pending(cursor_idx); return; }
        int pid = player_val;
        EidVec components = st.get_all_player_components(pid);

        while (comp_idx < components.size()) {
            int16_t eid = components[comp_idx];
            comp_idx++;
            Entity& entity = st.entities[eid];
            const EntityData* d = entity.data;
            int stack_before = st.pending_count;

            if (pass_num == 0) {
                if (d->has_collect) {
                    const CollectAbility& c = d->collect_ability;
                    if (c.has_collect_cost()) continue;
                    if (c.has_conditional()) {
                        if (c.conditional_type == ConditionalType::STORED_GOLD) {
                            if (entity.has_essences && entity.essences_on_card.gold() > 0)
                                push_collect_storage(st, pid, d, entity, eid);
                        } else if (c.conditional_type == ConditionalType::PER_STORED_ESSENCE) {
                            if (entity.has_essences && entity.essences_on_card.total() > 0)
                                push_per_stored_pay(st, pid, c, entity, eid);
                        }
                    } else {
                        apply_collect(st, pid, d, eid);
                    }
                }
                bool has_stored = entity.has_essences && entity.essences_on_card.total() > 0;
                bool no_conditional = !d->has_collect || !d->collect_ability.has_conditional();
                if (has_stored && no_conditional) offer_take_stored(st, pid, entity, eid);
            } else {
                if (d->has_collect && d->collect_ability.has_collect_cost()) {
                    PendingChoice p{};
                    p.type = PendingType::CollectCost; p.pid = (uint8_t)pid; p.eid = eid;
                    p.cost_essences = d->collect_ability.cost_essences;
                    p.cost_turn = d->collect_ability.cost_turn;
                    st.push_pending(p);
                }
            }

            if (st.pending_count > stack_before) {
                PendingChoice& cur = st.pending[cursor_idx];
                cur.player = player_val; cur.component_index = comp_idx; cur.pass_num = pass_num;
                cur.pid = (uint8_t)player_val;
                return;
            }
        }

        if (pass_num == 0) { pass_num = 1; comp_idx = 0; }
        else { player_val++; pass_num = 0; comp_idx = 0; }
    }
}

static void execute_collect_phase(GameState& st) {
    PendingChoice p{};
    p.type = PendingType::CollectPhaseCursor;
    p.player = 0; p.component_index = 0; p.pass_num = 0; p.pid = 0;
    st.push_pending(p);
}

// ===========================================================================
// victory react scan / finalize (mirrors game_engine)
// ===========================================================================
struct VRChoice { uint8_t pid; int16_t eid; int power_index; };

static void scan_for_victory_react_powers(GameState& st, int triggered_by) {
    std::vector<VRChoice> choices;
    for (int i = 0; i < st.num_players; i++) {
        int pid = i;
        if (!st.players[pid].is_active) continue;
        EidVec comps;
        for (int e : st.get_player_monuments(pid)) comps.push(e);
        for (int e : st.get_player_artifacts_in_play(pid)) comps.push(e);
        for (int e : st.get_player_places_of_power(pid)) comps.push(e);
        for (int eid : comps) {
            const Entity& entity = st.entities[eid];
            const EntityData* d = entity.data;
            for (int pi = 0; pi < (int)d->powers.size(); pi++) {
                const Power& power = d->powers[pi];
                if (power.react_trigger != ReactTrigger::VICTORY_CHECK) continue;
                if (entity.is_turned) break;
                Pool ec = power.get_essence_cost();
                if (!st.players[pid].pool.can_afford(ec)) break;
                choices.push_back({(uint8_t)pid, (int16_t)eid, pi});
                break;
            }
        }
    }
    std::sort(choices.begin(), choices.end(), [&](const VRChoice& a, const VRChoice& b) {
        int ka = (a.pid == triggered_by) ? 1 : 0;
        int kb = (b.pid == triggered_by) ? 1 : 0;
        if (ka != kb) return ka < kb;
        if (a.pid != b.pid) return a.pid < b.pid;
        return (-a.eid) < (-b.eid);
    });
    for (const VRChoice& c : choices) {
        PendingChoice p{};
        p.type = PendingType::VictoryReactChoice;
        p.pid = c.pid; p.eid = c.eid; p.power_index = c.power_index;
        st.push_pending(p);
    }
}

static bool has_blocking_pending(const GameState& st); // fwd

static void finalize_victory_check(GameState& st) {
    bool is_mid_round = st.is_mid_round_victory_check;
    st.is_mid_round_victory_check = false;

    int vp[MAX_PLAYERS];
    for (int i = 0; i < st.num_players; i++) vp[i] = calculate_victory_points(st, i);

    int winners[MAX_PLAYERS], nwin = 0;
    for (int i = 0; i < st.num_players; i++) if (vp[i] >= VICTORY_THRESHOLD) winners[nwin++] = i;

    if (nwin > 0) {
        if (nwin > 1) {
            int maxvp = -1000000;
            for (int k = 0; k < nwin; k++) maxvp = std::max(maxvp, vp[winners[k]]);
            int tmp[MAX_PLAYERS], n2 = 0;
            for (int k = 0; k < nwin; k++) if (vp[winners[k]] == maxvp) tmp[n2++] = winners[k];
            nwin = n2; for (int k = 0; k < n2; k++) winners[k] = tmp[k];
        }
        if (nwin > 1) {
            int best = -1; int tmp[MAX_PLAYERS], n2 = 0;
            for (int k = 0; k < nwin; k++) {
                int pid = winners[k];
                const Pool& pool = st.players[pid].pool;
                int tb = pool[0] + pool[1] + pool[2] + pool[3] + pool[GOLD] * 2;
                if (tb > best) { best = tb; n2 = 0; tmp[n2++] = pid; }
                else if (tb == best) tmp[n2++] = pid;
            }
            nwin = n2; for (int k = 0; k < n2; k++) winners[k] = tmp[k];
        }
        st.set_winner(winners, nwin);
    } else {
        for (int i = 0; i < st.num_players; i++) st.temp_vp[i] = 0;
        if (is_mid_round) {
            st.phase = GamePhase::ACTIONS;
            if (st.pending_turn_advance && !has_blocking_pending(st)) {
                st.advance_to_next_player();
                st.pending_turn_advance = false;
            }
        } else {
            for (int i = 0; i < st.num_players; i++) {
                if (!st.players[i].is_active) continue;
                EidVec comps = st.get_all_player_components(i);
                for (int e : comps) st.entities[e].is_turned = false;
            }
            st.begin_round();
        }
    }
}

// ===========================================================================
// blocking-choice predicates (mirrors game_engine)
// ===========================================================================
static bool blocks_turn_advancement(const PendingChoice& c) {
    switch (c.type) {
        case PendingType::ScryDeckChoice:
        case PendingType::ScryChoice:
        case PendingType::DiscardChoice:
        case PendingType::PlacementChoice:
        case PendingType::MonumentDrawChoice:
        case PendingType::Gain:
        case PendingType::LifeLossChoice:
        case PendingType::LifeLossScan:
        case PendingType::DrawRevealChoice:
        case PendingType::MonumentRevealChoice:
        case PendingType::ScryRevealChoice:
        case PendingType::GameSetupChoice:
            return true;
        default:
            return false;
    }
}
static bool has_blocking_pending(const GameState& st) {
    for (int i = 0; i < st.pending_count; i++) if (blocks_turn_advancement(st.pending[i])) return true;
    return false;
}
bool has_any_blocking_pending_choice(const GameState& st) { return has_blocking_pending(st); }

static bool pending_blocks_main_action(const PendingChoice& c, const Action& a) {
    if (c.type == PendingType::PlacementChoice) return a.type != ActionType::PlaceArtifact;
    switch (c.type) {
        case PendingType::ScryDeckChoice:
        case PendingType::ScryChoice:
        case PendingType::DiscardChoice:
        case PendingType::MonumentDrawChoice:
        case PendingType::Gain:
        case PendingType::LifeLossChoice:
        case PendingType::LifeLossScan:
        case PendingType::DrawRevealChoice:
        case PendingType::MonumentRevealChoice:
        case PendingType::ScryRevealChoice:
        case PendingType::GameSetupChoice:
            return true;
        default:
            return false;
    }
}

// ===========================================================================
// trigger monument bought
// ===========================================================================
static void trigger_monument_bought(GameState& st, int pid, int16_t monument_eid) {
    const EntityData* d = st.entities[monument_eid].data;
    for (const Power& power : d->powers) {
        if (power.power_type != PowerType::BOUGHT) continue;
        for (const Effect& e : power.effects) {
            if (e.type == EffectType::GainAny && e.amount > 0) {
                PendingChoice p{};
                p.type = PendingType::Gain; p.pid = (uint8_t)pid;
                p.any_amount = e.amount; p.restriction_mask = (1 << GOLD); p.eid = monument_eid;
                st.push_pending(p);
            }
        }
    }
}

// ===========================================================================
// life-loss scan advance (mirrors game_engine.advance_cursors)
// ===========================================================================
static void advance_life_loss_scan(GameState& st) {
    int cursor_idx = st.pending_count - 1;
    PendingChoice scan = st.pending[cursor_idx];
    int num_players = st.num_players;
    int offset = scan.next_offset;
    while (offset < num_players) {
        int target_pid = (scan.pid + offset) % num_players;
        offset++;
        if (target_pid == scan.pid) {
            if (!scan.include_self || !scan.all_players) continue;
        }
        if (st.players[target_pid].has_passed) continue;
        PendingChoice& cur = st.pending[cursor_idx];
        cur.next_offset = offset;
        PendingChoice p{};
        p.type = PendingType::LifeLossChoice;
        p.pid = (uint8_t)target_pid; p.amount = scan.amount; p.source = scan.source;
        st.push_pending(p);
        return;
    }
    st.erase_pending(cursor_idx);
}

static void advance_cursors(GameState& st) {
    while (st.pending_count > 0 && st.pending[st.pending_count - 1].type == PendingType::LifeLossScan)
        advance_life_loss_scan(st);
}

// ===========================================================================
// phase-transition checks
// ===========================================================================
static void check_collect_to_actions(GameState& st) {
    while (true) {
        if (st.pending_count == 0) { st.begin_action_phase(); return; }
        if (st.pending[st.pending_count - 1].type == PendingType::CollectPhaseCursor)
            advance_collect_phase(st);
        else return;
    }
}
static void check_victory_finalization(GameState& st) {
    for (int i = 0; i < st.pending_count; i++)
        if (st.pending[i].type == PendingType::VictoryReactChoice) return;
    finalize_victory_check(st);
}
static void check_phase_transitions(GameState& st) {
    if (st.phase == GamePhase::COLLECT) check_collect_to_actions(st);
    else if (st.phase == GamePhase::VICTORY_CHECK) check_victory_finalization(st);
}
static void process_phase(GameState& st) {
    if (st.phase == GamePhase::COLLECT) execute_collect_phase(st);
}

static void end_action_phase(GameState& st) {
    st.begin_victory_check();
    scan_for_victory_react_powers(st, -1);
    bool any = false;
    for (int i = 0; i < st.pending_count; i++)
        if (st.pending[i].type == PendingType::VictoryReactChoice) { any = true; break; }
    if (any) return;
    finalize_victory_check(st);
}

// ===========================================================================
// pending lookup helpers
// ===========================================================================
static int find_pending(const GameState& st, PendingType t, int pid, int16_t eid) {
    for (int i = 0; i < st.pending_count; i++) {
        const PendingChoice& c = st.pending[i];
        if (c.type == t && c.pid == pid && c.eid == eid) return i;
    }
    return -1;
}

// ===========================================================================
// individual action handlers
// ===========================================================================
static void h_choose_mage(GameState& st, const Action& a) {
    RA_CHECK(st.phase == GamePhase::SETUP_CHOOSE_MAGES);
    RA_CHECK(a.eid >= 0 && a.eid < st.entity_count);
    Entity& mage = st.entities[a.eid];
    RA_CHECK(mage.kind == ComponentType::MAGE);
    RA_CHECK(mage.owner_id == a.pid);
    RA_CHECK(mage.location == CardLocation::BEING_CHOSEN);

    int rejected = 0;
    for (int i = st.mage_start; i < st.mage_end; i++) {
        Entity& m = st.entities[i];
        if (m.owner_id == a.pid && m.location == CardLocation::BEING_CHOSEN && i != a.eid) {
            m.location = CardLocation::OUT_OF_GAME;
            rejected++;
        }
    }
    if (rejected == 0) mage.location = CardLocation::IN_PLAY;

    int next_pid = -1;
    for (int pid = 0; pid < st.num_players; pid++) {
        bool all_bc = true;
        for (int i = st.mage_start; i < st.mage_end; i++) {
            const Entity& m = st.entities[i];
            if (m.owner_id == pid && m.location != CardLocation::BEING_CHOSEN) { all_bc = false; break; }
        }
        if (all_bc) { next_pid = pid; break; }
    }
    if (next_pid >= 0) {
        st.current_player_index = (uint8_t)next_pid;
    } else {
        for (int i = st.mage_start; i < st.mage_end; i++) {
            Entity& m = st.entities[i];
            if (m.location == CardLocation::BEING_CHOSEN) m.location = CardLocation::IN_PLAY;
        }
        int item_pid = st.get_magic_item_selection_player();
        if (item_pid >= 0) st.current_player_index = (uint8_t)item_pid;
        st.phase = GamePhase::SETUP_CHOOSE_ITEMS;
    }
}

static void h_choose_magic_item(GameState& st, const Action& a) {
    RA_CHECK(st.phase == GamePhase::SETUP_CHOOSE_ITEMS);
    RA_CHECK(st.get_magic_item_selection_player() == a.pid);
    RA_CHECK(a.eid >= 0 && a.eid < st.entity_count);
    Entity& item = st.entities[a.eid];
    RA_CHECK(item.kind == ComponentType::MAGIC_ITEM);
    RA_CHECK(item.location == CardLocation::AVAILABLE);
    item.location = CardLocation::IN_PLAY;
    item.owner_id = (uint8_t)a.pid;
    int next_pid = st.get_magic_item_selection_player();
    if (next_pid < 0) st.begin_round();
    else st.current_player_index = (uint8_t)next_pid;
}

static void h_place_artifact(GameState& st, const Action& a) {
    PlayerState& player = st.players[a.pid];
    int pc_idx = -1;
    if (st.pending_count > 0) {
        PendingChoice& top = st.top_pending();
        if (top.type == PendingType::PlacementChoice && top.pid == a.pid) pc_idx = st.pending_count - 1;
    }
    int16_t artifact_eid = a.eid;
    RA_CHECK(artifact_eid >= 0 && artifact_eid < st.entity_count);
    Entity& entity = st.entities[artifact_eid];
    const EntityData* d = entity.data;
    RA_CHECK(d != nullptr);

    if (pc_idx >= 0) {
        const PendingChoice& pc = st.pending[pc_idx];
        SelectCardLocation loc = pc.filter.location;
        if (loc == SelectCardLocation::HAND) {
            RA_CHECK(entity.location == CardLocation::HAND);
            RA_CHECK(entity.owner_id == a.pid);
        } else if (loc == SelectCardLocation::DISCARD || loc == SelectCardLocation::ANY_DISCARD) {
            RA_CHECK(entity.location == CardLocation::DISCARD);
            RA_CHECK(loc != SelectCardLocation::DISCARD || entity.owner_id == a.pid);
        } else {
            throw IllegalAction{};
        }
        if (pc.filter.card_type_mask > 0)
            RA_CHECK(pc.filter.matches_card_type_mask(d->card_type_mask));
        if (pc.p_free) RA_CHECK(!d->cannot_be_free_placed());
    } else {
        EidVec hand = st.get_player_hand(a.pid);
        RA_CHECK(hand.contains(artifact_eid));
    }

    if (pc_idx >= 0 && st.pending[pc_idx].p_free) {
        entity.location = CardLocation::IN_PLAY;
        entity.is_turned = false;
        if (entity.owner_id != a.pid) entity.owner_id = (uint8_t)a.pid;
        st.pop_pending();
        return;
    }

    int extra_discount = pc_idx >= 0 ? st.pending[pc_idx].p_discount : 0;
    bool extra_cdg = pc_idx >= 0 ? st.pending[pc_idx].can_discount_gold : false;
    int gold_budget = calculate_gold_discount_budget(st, a.pid, d, extra_discount, extra_cdg);
    std::vector<Pool> payments;
    get_valid_payments(st, a.pid, d, extra_discount, true, gold_budget, payments);
    bool ok = false;
    for (const Pool& vp : payments) if (vp == a.pay) { ok = true; break; }
    RA_CHECK(ok);

    if (a.pay.total() > 0) player.pool.pay(a.pay);
    entity.location = CardLocation::IN_PLAY;
    entity.is_turned = false;
    if (entity.owner_id != a.pid) entity.owner_id = (uint8_t)a.pid;
    if (pc_idx >= 0) st.pop_pending();
}

static void h_claim_monument(GameState& st, const Action& a) {
    PlayerState& player = st.players[a.pid];
    RA_CHECK(player.pool.gold() >= 4);
    int16_t eid = a.eid;
    RA_CHECK(eid >= 0 && eid < st.entity_count);
    Entity& mon = st.entities[eid];
    RA_CHECK(mon.kind == ComponentType::MONUMENT);
    RA_CHECK(mon.location == CardLocation::AVAILABLE);
    player.pool.subtract(GOLD, 4);
    st.claim_monument(a.pid, eid);
    EidVec deck = st.get_monument_deck();
    if (!deck.empty()) {
        PendingChoice p{};
        p.type = PendingType::MonumentRevealChoice; p.pid = (uint8_t)a.pid;
        st.push_pending(p);
    }
    trigger_monument_bought(st, a.pid, eid);
}

static void h_claim_top_monument(GameState& st, const Action& a) {
    PlayerState& player = st.players[a.pid];
    RA_CHECK(player.pool.gold() >= 4);
    RA_CHECK(st.get_top_monument_from_deck() >= 0);
    player.pool.subtract(GOLD, 4);
    PendingChoice p{};
    p.type = PendingType::MonumentDrawChoice; p.pid = (uint8_t)a.pid;
    st.push_pending(p);
}

static void h_claim_pop(GameState& st, const Action& a) {
    PlayerState& player = st.players[a.pid];
    int16_t eid = a.eid;
    RA_CHECK(eid >= 0 && eid < st.entity_count);
    Entity& pop = st.entities[eid];
    RA_CHECK(pop.kind == ComponentType::PLACE_OF_POWER);
    RA_CHECK(pop.location == CardLocation::AVAILABLE);
    const EntityData* d = pop.data;
    int total_cost = d->total_placement_cost();
    RA_CHECK(player.pool.total() >= total_cost);
    Pool fixed = d->has_placement_cost ? d->placement_cost : Pool();
    RA_CHECK(player.pool.can_afford(fixed));
    player.pool.pay(fixed);
    int any_cost = d->placement_cost_any;
    if (any_cost > 0) {
        RA_CHECK(a.pay.total() == any_cost);
        player.pool.pay(a.pay);
    }
    RA_CHECK(pop.location == CardLocation::AVAILABLE);
    pop.location = CardLocation::IN_PLAY;
    pop.owner_id = (uint8_t)a.pid;
}

static void h_discard_for_essences(GameState& st, const Action& a) {
    PlayerState& player = st.players[a.pid];
    int16_t eid = a.eid;
    EidVec hand = st.get_player_hand(a.pid);
    RA_CHECK(hand.contains(eid));
    Entity& entity = st.entities[eid];
    RA_CHECK(!a.gain.is_empty());
    int total = a.gain.total();
    if (a.gain.gold() > 0) {
        RA_CHECK(total == 1);
        RA_CHECK(a.gain.gold() == 1);
    } else {
        RA_CHECK(total == 2);
    }
    player.pool.add_pool(a.gain);
    entity.location = CardLocation::DISCARD;
}

static void h_pass(GameState& st, const Action& a) {
    PlayerState& player = st.players[a.pid];
    RA_CHECK(!player.has_passed);
    int old_item = -1;
    for (int i = st.magic_item_start; i < st.magic_item_end; i++) {
        const Entity& it = st.entities[i];
        if (it.location == CardLocation::IN_PLAY && it.owner_id == a.pid) { old_item = i; break; }
    }
    if (old_item >= 0) {
        EidVec avail = st.get_available_magic_items();
        RA_CHECK(avail.contains(a.eid));
        Entity& oi = st.entities[old_item];
        oi.location = CardLocation::AVAILABLE; oi.owner_id = UNOWNED; oi.is_turned = false;
        Entity& ni = st.entities[a.eid];
        ni.location = CardLocation::IN_PLAY; ni.owner_id = (uint8_t)a.pid;
    }
    bool first_to_pass = true;
    for (int i = 0; i < st.num_players; i++)
        if (i != a.pid && st.players[i].has_passed) { first_to_pass = false; break; }
    if (first_to_pass) {
        for (int i = 0; i < st.num_players; i++) st.players[i].has_first_player_token = (i == a.pid);
        st.first_player_index = (uint8_t)a.pid;
    }
    draw_card(st, a.pid, 1);
    player.has_passed = true;
}

static void h_decline(GameState& st, const Action& a) {
    RA_CHECK(st.pending_count > 0);
    PendingChoice& top = st.top_pending();
    RA_CHECK(top.pid == a.pid);
    if (top.type == PendingType::VictoryReactChoice) {
        RA_CHECK(top.eid == a.eid);
        st.pop_pending();
        bool any = false;
        for (int i = 0; i < st.pending_count; i++)
            if (st.pending[i].type == PendingType::VictoryReactChoice) { any = true; break; }
        if (!any) finalize_victory_check(st);
    } else if (top.type == PendingType::PlacementChoice) {
        RA_CHECK(top.eid == a.eid);
        st.pop_pending();
    } else {
        throw IllegalAction{};
    }
}

static void h_use_power(GameState& st, const Action& a) {
    GameState::FCP fcp = st.find_component_power(a.pid, a.eid, a.power_index);
    RA_CHECK(fcp.found);
    RA_CHECK(fcp.power != nullptr);
    Entity& entity = st.entities[fcp.eid];
    const Power& power = *fcp.power;
    RA_CHECK(!power.is_react());
    RA_CHECK(power.usable_when_turned || !entity.is_turned);

    const Cost* pay_cost_obj = power.get_cost(CostType::PayEssence);
    PowerCtx ctx;
    ctx.state = &st; ctx.pid = a.pid; ctx.entity = &entity; ctx.eid = a.eid;
    ctx.pay_essence_cost = pay_cost_obj ? &pay_cost_obj->essences : nullptr;
    ctx.target_eid = a.target_eid; ctx.target_pid = a.target_pid;
    ctx.pay = a.pay; ctx.gain = a.gain;

    const Cost* sc = power.get_select_card_cost();
    if (sc && sc->filter.has_filter()) {
        EidVec targets;
        get_targets_from_filter(st, a.pid, sc->filter, &power, a.eid, targets);
        RA_CHECK(a.target_eid < 0 || targets.contains(a.target_eid));
    }

    if (power.requires_turn) entity.is_turned = true;
    for (const Cost& c : power.costs) pay_cost(c, ctx);
    for (const Effect& e : power.effects) exec_effect(e, ctx);
}

static void h_life_loss_react(GameState& st, const Action& a) {
    RA_CHECK(st.pending_count > 0);
    PendingChoice top = st.top_pending();
    RA_CHECK(top.type == PendingType::LifeLossChoice);
    RA_CHECK(top.pid == a.pid);
    int16_t entity_id = a.eid;

    // dragon defense react
    if (entity_id >= 0 && entity_id < st.entity_count) {
        Entity& e = st.entities[entity_id];
        if (e.data && e.data->is_dragon() && top.source == entity_id) {
            PlayerState& player = st.players[a.pid];
            const Cost* defense_options = nullptr; int ndef = 0;
            for (const Power& power : e.data->powers) {
                for (const Effect& ef : power.effects) {
                    if (ef.type == EffectType::Damage && !ef.defense_options.empty()) {
                        defense_options = ef.defense_options.data();
                        ndef = (int)ef.defense_options.size();
                        break;
                    }
                }
                if (defense_options) break;
            }
            RA_CHECK(defense_options != nullptr);
            bool paid = false;
            for (int di = 0; di < ndef && !paid; di++) {
                const Cost& dc = defense_options[di];
                if (dc.type == CostType::PayEssence) {
                    if (a.pay == dc.essences) {
                        RA_CHECK(player.pool.can_afford(dc.essences));
                        player.pool.pay(dc.essences);
                        paid = true;
                    }
                } else if (dc.type == CostType::DiscardCard) {
                    if (a.target_eid >= 0) {
                        Entity& te = st.entities[a.target_eid];
                        if (te.location == CardLocation::HAND) {
                            RA_CHECK(te.owner_id == a.pid);
                            te.location = CardLocation::DISCARD;
                            paid = true;
                        }
                    }
                } else if (dc.type == CostType::DestroyComponent) {
                    if (a.target_eid >= 0) {
                        Entity& te = st.entities[a.target_eid];
                        if (te.location == CardLocation::IN_PLAY) {
                            RA_CHECK(te.owner_id == a.pid);
                            RA_CHECK(te.kind == ComponentType::ARTIFACT);
                            te.location = CardLocation::DISCARD;
                            eoc_set_none(te);
                            paid = true;
                        }
                    }
                } else {
                    throw IllegalAction{};
                }
            }
            RA_CHECK(paid);
            RA_CHECK(st.pending_count > 0 && st.top_pending().type == PendingType::LifeLossChoice);
            st.pop_pending();
            return;
        }
    }

    GameState::FCP fcp = st.find_component_power(a.pid, entity_id, a.power_index);
    RA_CHECK(fcp.found);
    RA_CHECK(fcp.power != nullptr);
    Entity& entity = st.entities[fcp.eid];
    const Power& power = *fcp.power;
    RA_CHECK(power.is_react());
    bool has_ignore = false;
    for (const Effect& e : power.effects) if (e.type == EffectType::IgnoreDamage) has_ignore = true;
    RA_CHECK(has_ignore);

    if (power.react_trigger == ReactTrigger::DRAGON_ATTACK) {
        int16_t source = top.source;
        bool is_dragon_source = false;
        if (source >= 0) {
            const Entity& se = st.entities[source];
            if (se.data && se.data->is_dragon()) is_dragon_source = true;
        }
        RA_CHECK(is_dragon_source);
    }
    bool can_use_when_turned = power.is_react() && !power.requires_turn;
    RA_CHECK(!entity.is_turned || can_use_when_turned || power.usable_when_turned);

    PlayerState& player = st.players[a.pid];
    Pool ec = power.get_essence_cost();
    RA_CHECK(player.pool.can_afford(ec));
    player.pool.pay(ec);
    if (power.requires_turn) entity.is_turned = true;
    if (power.has_destroy_component_cost(DestroyMode::SELF) && fcp.kind == ComponentType::ARTIFACT) {
        entity.location = CardLocation::DISCARD;
        eoc_set_none(entity);
    }
    RA_CHECK(st.pending_count > 0 && st.top_pending().type == PendingType::LifeLossChoice);
    st.pop_pending();

    PowerCtx ctx;
    ctx.state = &st; ctx.pid = a.pid; ctx.entity = &entity; ctx.eid = a.eid;
    ctx.gain = a.gain;
    for (const Effect& e : power.effects) exec_effect(e, ctx);
}

static void h_victory_react(GameState& st, const Action& a) {
    RA_CHECK(st.pending_count > 0);
    PendingChoice top = st.top_pending();
    RA_CHECK(top.type == PendingType::VictoryReactChoice);
    RA_CHECK(top.pid == a.pid);
    RA_CHECK(top.eid == a.eid);
    int16_t component_eid = top.eid;
    Entity& entity = st.entities[component_eid];
    const EntityData* d = entity.data;
    RA_CHECK(a.power_index < (int)d->powers.size());
    const Power& power = d->powers[a.power_index];
    RA_CHECK(!entity.is_turned);

    PlayerState& player = st.players[a.pid];
    Pool fixed = power.get_essence_cost();
    int any_cost = power.get_any_cost();
    int required = fixed.total() + any_cost;
    if (required > 0) {
        RA_CHECK(a.pay.total() == required);
        for (int e = 0; e < ESSENCE_COUNT; e++)
            if (fixed[e] > 0) RA_CHECK(a.pay[e] >= fixed[e]);
        RA_CHECK(player.pool.can_afford(a.pay));
        player.pool.pay(a.pay);
    }
    if (power.requires_turn) entity.is_turned = true;
    for (const Effect& e : power.effects) {
        if (e.type == EffectType::TempVP) {
            PowerCtx ctx;
            ctx.state = &st; ctx.pid = a.pid; ctx.entity = &entity; ctx.eid = a.eid;
            ctx.target_eid = a.target_eid;
            exec_effect(e, ctx);
        }
    }
    RA_CHECK(st.pending_count > 0 && st.top_pending().type == PendingType::VictoryReactChoice);
    st.pop_pending();
}

static void h_life_loss_choice(GameState& st, const Action& a) {
    RA_CHECK(st.pending_count > 0);
    PendingChoice top = st.top_pending();
    RA_CHECK(top.type == PendingType::LifeLossChoice);
    RA_CHECK(top.pid == a.pid);
    PlayerState& player = st.players[a.pid];
    int damage = top.amount;
    int life_avail = player.pool.life();
    int non_life_avail = player.pool.total() - life_avail;
    int total_ess = player.pool.total();

    int max_life = std::min(life_avail, damage);
    int rem = damage - max_life;
    int max_pairs = non_life_avail / 2;
    int max_non_life = std::min(max_pairs, rem);
    int coverable = max_life + max_non_life;
    bool can_fully = coverable >= damage;

    if (a.pay.total() == 0) {
        RA_CHECK(total_ess == 0);
        st.pop_pending();
        return;
    }
    for (int e = 0; e < ESSENCE_COUNT; e++) RA_CHECK(a.pay[e] <= player.pool[e]);
    int life_paid = a.pay.life();
    int non_life_paid = a.pay.total() - life_paid;
    int paid = a.pay.total();
    if (can_fully) {
        RA_CHECK(non_life_paid % 2 == 0);
        int covered = life_paid + non_life_paid / 2;
        RA_CHECK(covered == damage);
    } else {
        RA_CHECK(paid == total_ess);
    }
    for (int e = 0; e < ESSENCE_COUNT; e++)
        for (int k = 0; k < a.pay[e]; k++) player.pool.subtract(e);
    st.pop_pending();
}

static void h_take_stored(GameState& st, const Action& a) {
    RA_CHECK(st.phase == GamePhase::COLLECT);
    int16_t entity_id = a.eid;
    bool take = (a.decision == CollectDecision::TAKE_STORED);
    int idx = find_pending(st, PendingType::CollectStorage, a.pid, entity_id);
    RA_CHECK(idx >= 0);
    PendingChoice choice = st.pending[idx];
    RA_CHECK(entity_id >= 0 && entity_id < st.entity_count);
    Entity& entity = st.entities[entity_id];
    RA_CHECK(entity.owner_id == a.pid);
    bool has_stored = choice.stored.total() > 0;

    if (take) {
        if (eoc_present_nonempty(entity)) {
            st.players[a.pid].pool.add_pool(entity.essences_on_card);
            eoc_set_none(entity);
        }
    } else {
        if (choice.bonus_multiplier > 0 && has_stored) {
            for (int i = 0; i < ESSENCE_COUNT; i++)
                if (choice.stored[i] > 0) eoc_add(entity, i, choice.bonus_multiplier);
        } else if (choice.has_natural && has_stored) {
            for (int k = 0; k < choice.natural_count; k++) {
                const NaturalCollectOption& opt = choice.natural[k];
                if (opt.option_type == CollectOptionType::FIXED_ESSENCE) {
                    if (opt.essence >= 0 && opt.amount > 0)
                        st.players[a.pid].pool.add(opt.essence, opt.amount);
                } else { // ANY
                    PendingChoice p{};
                    p.type = PendingType::Gain; p.pid = (uint8_t)a.pid;
                    p.any_amount = opt.amount; p.restriction_mask = opt.restriction_mask;
                    p.alt_any_amount = opt.alt_any_amount; p.alt_restriction_mask = opt.alt_restriction_mask;
                    p.eid = entity_id;
                    st.push_pending(p);
                }
            }
        }
    }
    st.erase_pending(idx);
}

static void h_collect_cost(GameState& st, const Action& a) {
    RA_CHECK(st.phase == GamePhase::COLLECT);
    int idx = find_pending(st, PendingType::CollectCost, a.pid, a.eid);
    RA_CHECK(idx >= 0);
    PendingChoice choice = st.pending[idx];
    PlayerState& player = st.players[a.pid];
    int16_t entity_id = choice.eid;

    if (a.decision == CollectDecision::DECLINE_COST) {
        st.erase_pending(idx);
        return;
    } else if (a.decision == CollectDecision::PAY_TURN) {
        st.entities[entity_id].is_turned = true;
    } else {
        RA_CHECK(player.pool.can_afford(choice.cost_essences));
        player.pool.pay(choice.cost_essences);
    }
    st.erase_pending(idx);
    Entity& entity = st.entities[entity_id];
    if (eoc_present_nonempty(entity)) {
        PendingChoice p{};
        p.type = PendingType::CollectStorage; p.pid = (uint8_t)a.pid; p.eid = entity_id;
        build_stored_into(entity.essences_on_card, p);
        p.has_natural = false; p.natural_count = 0; p.bonus_multiplier = 0;
        st.push_pending(p);
    }
}

static void h_gain(GameState& st, const Action& a) {
    int idx = -1;
    for (int i = 0; i < st.pending_count; i++) {
        const PendingChoice& c = st.pending[i];
        if (c.type == PendingType::Gain && c.pid == a.pid && c.eid == a.eid) { idx = i; break; }
    }
    RA_CHECK(idx >= 0);
    PendingChoice choice = st.pending[idx];
    int expected, rmask;
    if (a.use_alt && choice.alt_any_amount > 0) {
        expected = choice.alt_any_amount; rmask = choice.alt_restriction_mask;
    } else {
        expected = choice.any_amount; rmask = choice.restriction_mask;
    }
    RA_CHECK(a.gain.total() == expected);
    for (int i = 0; i < ESSENCE_COUNT; i++)
        if ((rmask & (1 << i)) && a.gain[i] > 0) throw IllegalAction{};
    st.players[a.pid].pool.add_pool(a.gain);
    st.erase_pending(idx);
}

static void h_scry_deck_choice(GameState& st, const Action& a) {
    RA_CHECK(st.phase == GamePhase::ACTIONS);
    RA_CHECK(st.pending_count > 0);
    PendingChoice top = st.top_pending();
    RA_CHECK(top.type == PendingType::ScryDeckChoice);
    RA_CHECK(top.pid == a.pid);
    int scry_count = top.scry_count;

    EidVec known, unknown;
    if (a.scry_target == DeckType::MONUMENT) {
        EidVec km = st.get_known_monument_deck();
        for (int i = 0; i < km.size() && i < scry_count; i++) known.push(km[i]);
        unknown = st.get_unknown_monument_deck();
    } else {
        int deck_size = st.get_player_deck_count(a.pid);
        if (deck_size < scry_count) {
            EidVec disc = st.get_player_discard(a.pid);
            if (!disc.empty())
                for (int eid : disc) {
                    st.entities[eid].location = CardLocation::DECK;
                    st.entities[eid].order_index = UNKNOWN_ORDER;
                }
        }
        EidVec kd = st.get_known_deck_cards(a.pid);
        for (int i = 0; i < kd.size() && i < scry_count; i++) known.push(kd[i]);
        unknown = st.get_unknown_deck_cards(a.pid);
    }
    int knowns_to_scry = known.size();
    int unknowns_needed = scry_count - knowns_to_scry;
    st.pop_pending();

    if (unknowns_needed > 0 && !unknown.empty()) {
        int actual = std::min(unknowns_needed, unknown.size());
        PendingChoice p{};
        p.type = PendingType::ScryRevealChoice; p.pid = (uint8_t)a.pid;
        p.eid_count = known.size();
        for (int i = 0; i < known.size(); i++) p.eids[i] = known[i];
        p.reveal_count = actual; p.deck_type = a.scry_target;
        st.push_pending(p);
    } else {
        PendingChoice p{};
        p.type = PendingType::ScryChoice; p.pid = (uint8_t)a.pid; p.deck_type = a.scry_target;
        p.eid_count = known.size();
        for (int i = 0; i < known.size(); i++) p.eids[i] = known[i];
        st.push_pending(p);
    }
}

static void h_scry_choice(GameState& st, const Action& a) {
    RA_CHECK(st.phase == GamePhase::ACTIONS);
    RA_CHECK(st.pending_count > 0);
    PendingChoice top = st.top_pending();
    RA_CHECK(top.type == PendingType::ScryChoice);
    RA_CHECK(top.pid == a.pid);
    int n = top.eid_count;
    int order[12];
    int order_n = a.scry_order_n;
    if (order_n == 0) { for (int i = 0; i < n; i++) order[i] = i; order_n = n; }
    else for (int i = 0; i < order_n; i++) order[i] = a.scry_order[i];
    // validate sorted(order)==range(n)
    RA_CHECK(order_n == n);
    bool seen[12] = {false};
    for (int i = 0; i < n; i++) { RA_CHECK(order[i] >= 0 && order[i] < n && !seen[order[i]]); seen[order[i]] = true; }
    for (int new_pos = 0; new_pos < n; new_pos++) {
        int16_t eid = top.eids[order[new_pos]];
        st.entities[eid].order_index = new_pos;
    }
    st.pop_pending();
}

static void h_discard_choice(GameState& st, const Action& a) {
    RA_CHECK(st.phase == GamePhase::ACTIONS);
    RA_CHECK(st.pending_count > 0);
    PendingChoice top = st.top_pending();
    RA_CHECK(top.type == PendingType::DiscardChoice);
    RA_CHECK(top.pid == a.pid);
    RA_CHECK(a.list_a_n == top.count);
    EidVec hand = st.get_player_hand(a.pid);
    for (int i = 0; i < a.list_a_n; i++) RA_CHECK(hand.contains(a.list_a[i]));
    for (int i = 0; i < a.list_a_n; i++) st.entities[a.list_a[i]].location = CardLocation::DISCARD;
    st.pop_pending();
}

static void h_resolve_draw_reveal(GameState& st, const Action& a) {
    RA_CHECK(st.pending_count > 0);
    PendingChoice top = st.top_pending();
    RA_CHECK(top.type == PendingType::DrawRevealChoice);
    st.pop_pending();
    RA_CHECK(top.pid == a.pid);
    RA_CHECK(a.list_b_n == top.reveal_count);

    // known orders sorted desc
    int known_orders[16], kn = 0;
    for (int i = 0; i < top.eid_count; i++) known_orders[kn++] = st.entities[top.eids[i]].order_index;
    std::sort(known_orders, known_orders + kn, std::greater<int>());

    for (int i = 0; i < top.eid_count; i++) {
        Entity& e = st.entities[top.eids[i]];
        RA_CHECK(e.location == CardLocation::DECK);
        RA_CHECK(e.owner_id == a.pid);
        RA_CHECK(e.order_index != UNKNOWN_ORDER);
        e.location = CardLocation::HAND;
        e.order_index = UNKNOWN_ORDER;
    }
    for (int i = st.artifact_start; i < st.artifact_end; i++) {
        Entity& art = st.entities[i];
        if (art.location == CardLocation::DECK && art.owner_id == a.pid && art.order_index != UNKNOWN_ORDER) {
            int adj = 0;
            for (int k = 0; k < kn; k++) if (art.order_index > known_orders[k]) adj++;
            if (adj > 0) art.order_index -= adj;
        }
    }
    for (int i = 0; i < a.list_b_n; i++) {
        Entity& e = st.entities[a.list_b[i]];
        RA_CHECK(e.location == CardLocation::DECK);
        RA_CHECK(e.owner_id == a.pid);
        RA_CHECK(e.order_index == UNKNOWN_ORDER);
        e.location = CardLocation::HAND;
    }
}

static void h_resolve_scry_reveal(GameState& st, const Action& a) {
    RA_CHECK(st.phase == GamePhase::ACTIONS);
    RA_CHECK(st.pending_count > 0);
    PendingChoice top = st.top_pending();
    RA_CHECK(top.type == PendingType::ScryRevealChoice);
    RA_CHECK(top.pid == a.pid);
    RA_CHECK(a.list_b_n == top.reveal_count);
    EidVec unknown = (top.deck_type == DeckType::MONUMENT)
                         ? st.get_unknown_monument_deck()
                         : st.get_unknown_deck_cards(top.pid);
    for (int i = 0; i < a.list_b_n; i++) RA_CHECK(unknown.contains(a.list_b[i]));
    PendingChoice p{};
    p.type = PendingType::ScryChoice; p.pid = (uint8_t)a.pid; p.deck_type = top.deck_type;
    p.eid_count = 0;
    for (int i = 0; i < top.eid_count; i++) p.eids[p.eid_count++] = top.eids[i];
    for (int i = 0; i < a.list_b_n; i++) p.eids[p.eid_count++] = a.list_b[i];
    st.pop_pending();
    st.push_pending(p);
}

static void h_resolve_monument_draw(GameState& st, const Action& a) {
    RA_CHECK(st.phase == GamePhase::ACTIONS);
    RA_CHECK(st.pending_count > 0);
    PendingChoice top = st.top_pending();
    RA_CHECK(top.type == PendingType::MonumentDrawChoice);
    RA_CHECK(top.pid == a.pid);
    Entity& target = st.entities[a.eid];
    RA_CHECK(target.location == CardLocation::MONUMENT_DECK);
    EidVec known = st.get_known_monument_deck();
    int drawn_order = target.order_index;
    if (!known.empty()) {
        RA_CHECK(a.eid == known[0]);
        for (int i = 1; i < known.size(); i++) {
            Entity& o = st.entities[known[i]];
            if (o.order_index > drawn_order) o.order_index -= 1;
        }
    } else {
        RA_CHECK(drawn_order == UNKNOWN_ORDER);
    }
    st.claim_monument(a.pid, a.eid);
    target.order_index = UNKNOWN_ORDER;
    st.pop_pending();
    trigger_monument_bought(st, a.pid, a.eid);
}

static void h_resolve_monument_reveal(GameState& st, const Action& a) {
    RA_CHECK(st.phase == GamePhase::ACTIONS);
    RA_CHECK(st.pending_count > 0);
    PendingChoice top = st.top_pending();
    RA_CHECK(top.type == PendingType::MonumentRevealChoice);
    RA_CHECK(top.pid == a.pid);
    Entity& target = st.entities[a.eid];
    RA_CHECK(target.location == CardLocation::MONUMENT_DECK);
    EidVec known = st.get_known_monument_deck();
    int drawn_order = target.order_index;
    if (!known.empty()) {
        RA_CHECK(a.eid == known[0]);
        for (int i = 1; i < known.size(); i++) {
            Entity& o = st.entities[known[i]];
            if (o.order_index > drawn_order) o.order_index -= 1;
        }
    } else {
        RA_CHECK(drawn_order == UNKNOWN_ORDER);
    }
    target.location = CardLocation::AVAILABLE;
    target.order_index = UNKNOWN_ORDER;
    st.pop_pending();
}

// ===========================================================================
// dispatch + top-level execute_action
// ===========================================================================
static bool is_main_action(ActionType t) {
    switch (t) {
        case ActionType::PlaceArtifact:
        case ActionType::ClaimMonument:
        case ActionType::ClaimTopMonument:
        case ActionType::ClaimPlaceOfPower:
        case ActionType::DiscardForEssences:
        case ActionType::UsePower:
        case ActionType::Pass:
            return true;
        default:
            return false;
    }
}

static void dispatch(GameState& st, const Action& a) {
    switch (a.type) {
        case ActionType::ChooseMage:            h_choose_mage(st, a); break;
        case ActionType::ChooseMagicItem:       h_choose_magic_item(st, a); break;
        case ActionType::PlaceArtifact:         h_place_artifact(st, a); break;
        case ActionType::ClaimMonument:         h_claim_monument(st, a); break;
        case ActionType::ClaimTopMonument:      h_claim_top_monument(st, a); break;
        case ActionType::ClaimPlaceOfPower:     h_claim_pop(st, a); break;
        case ActionType::DiscardForEssences:    h_discard_for_essences(st, a); break;
        case ActionType::UsePower:              h_use_power(st, a); break;
        case ActionType::Pass:                  h_pass(st, a); break;
        case ActionType::Decline:               h_decline(st, a); break;
        case ActionType::LifeLossReact:         h_life_loss_react(st, a); break;
        case ActionType::VictoryReact:          h_victory_react(st, a); break;
        case ActionType::LifeLossChoice:        h_life_loss_choice(st, a); break;
        case ActionType::TakeStored:            h_take_stored(st, a); break;
        case ActionType::CollectCost:           h_collect_cost(st, a); break;
        case ActionType::Gain:                  h_gain(st, a); break;
        case ActionType::ScryDeckChoice:        h_scry_deck_choice(st, a); break;
        case ActionType::ScryChoice:            h_scry_choice(st, a); break;
        case ActionType::DiscardChoice:         h_discard_choice(st, a); break;
        case ActionType::ResolveDrawReveal:     h_resolve_draw_reveal(st, a); break;
        case ActionType::ResolveScryReveal:     h_resolve_scry_reveal(st, a); break;
        case ActionType::ResolveMonumentDraw:   h_resolve_monument_draw(st, a); break;
        case ActionType::ResolveMonumentReveal: h_resolve_monument_reveal(st, a); break;
    }
}

void execute_action(GameState& st, const Action& a) {
    bool main = is_main_action(a.type);
    if (main) {
        RA_CHECK(st.phase == GamePhase::ACTIONS);
        RA_CHECK(st.current_player_index == a.pid);
        for (int i = st.pending_count - 1; i >= 0; i--) {
            const PendingChoice& c = st.pending[i];
            if (c.pid == a.pid) RA_CHECK(!pending_blocks_main_action(c, a));
        }
    }
    GamePhase phase_before = st.phase;

    dispatch(st, a);

    advance_cursors(st);

    GamePhase phase_after_action = st.phase;
    bool phase_changed_during_action = phase_after_action != phase_before;

    if (st.phase == GamePhase::ACTIONS && st.all_players_passed()) {
        bool draw_pending = false;
        for (int i = 0; i < st.pending_count; i++)
            if (st.pending[i].type == PendingType::DrawRevealChoice) { draw_pending = true; break; }
        if (!draw_pending) {
            end_action_phase(st);
            phase_changed_during_action = true;
        }
    }

    if (st.phase == GamePhase::COLLECT && phase_before != GamePhase::COLLECT)
        process_phase(st);

    GamePhase phase_before_transitions = st.phase;
    check_phase_transitions(st);

    if (st.phase == GamePhase::COLLECT && phase_before_transitions != GamePhase::COLLECT) {
        process_phase(st);
        check_phase_transitions(st);
    }

    if (phase_before == GamePhase::ACTIONS && st.phase == GamePhase::ACTIONS &&
        !phase_changed_during_action && !st.all_players_passed()) {
        bool has_blocking = has_blocking_pending(st);
        if (main) {
            if (has_blocking) st.pending_turn_advance = true;
            else { st.advance_to_next_player(); st.pending_turn_advance = false; }
        } else if (st.pending_turn_advance && !has_blocking) {
            st.advance_to_next_player();
            st.pending_turn_advance = false;
        }
    }
}

} // namespace ra
