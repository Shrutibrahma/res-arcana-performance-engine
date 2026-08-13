// Immutable card data: EntityData, Power, Cost, Effect, CollectAbility.
// These are loaded once from cards.json and shared (by pointer) across all
// cloned game states.
#pragma once
#include "common.hpp"
#include <vector>
#include <string>

namespace ra {

// ---- SelectCardFilter ----------------------------------------------------
struct SelectCardFilter {
    SelectCardLocation location = SelectCardLocation::NONE;
    bool require_tapped = false;
    int card_type_mask = 0;
    bool own_cards_only = true;
    int component_type_mask = 0;
    bool exclude_self = false;

    bool has_filter() const { return location != SelectCardLocation::NONE; }
    bool matches_card_type_mask(int entity_mask) const {
        if (card_type_mask == 0) return true;
        return (card_type_mask & entity_mask) != 0;
    }
    bool matches_tapped_state(bool is_turned) const {
        if (!require_tapped) return true;
        return is_turned;
    }
    bool allows_component_type(ComponentType ct) const {
        if (component_type_mask == 0) return true;
        return (component_type_mask & (1 << (int)ct)) != 0;
    }
};

// ---- Discount ------------------------------------------------------------
struct Discount {
    int artifact = 0;
    int dragon = 0;
    int creature = 0;
    bool can_discount_gold = false;
};

// ---- Cost (tagged) -------------------------------------------------------
enum class CostType : uint8_t {
    PayEssence, TurnComponent, RemoveFromCard, PayIdentical,
    DestroyComponent, DestroyCardType, DiscardCard, SelectPlayer, SelectCard
};

struct Cost {
    CostType type;
    // PayEssence / RemoveFromCard
    Pool essences;
    int any_amount = 0;
    Essence exclude[ESSENCE_COUNT];
    int exclude_count = 0;
    // TurnComponent
    TurnableType turnable_type = TurnableType::DRAGON;
    // PayIdentical
    int base_cost = 0;
    int min_amount = 0;
    int essence_type = -1; // -1 = None
    // DestroyComponent
    DestroyMode destroy_mode = DestroyMode::ANY;
    // DestroyCardType / DiscardCard
    int card_type_mask = 0;
    int exclude_entity_flags = 0;
    // SelectPlayer
    bool opponent_only = false;
    // SelectCard
    SelectCardFilter filter;

    bool matches_type_discard(int data_card_type_mask) const {
        // CostDiscardCard.matches_type
        if (card_type_mask == 0) return true;
        return (card_type_mask & data_card_type_mask) != 0;
    }
};

// ---- Effect (tagged) -----------------------------------------------------
enum class EffectType : uint8_t {
    Gain, GainAny, Store, RivalsGain, Damage, Draw, IgnoreDamage,
    CheckVictory, Straighten, Scry, Place, GainDestroyedCost,
    GainGoldEqualToSameSpent, GainFromOpponent, GainSameTypeAsSpent,
    TempVP, GainGoldFromCost
};

struct Effect {
    EffectType type;
    // Gain / Store / RivalsGain
    Pool essences;
    // GainAny / Store / Damage / Draw / Scry / TempVP / GainDestroyedCost
    int amount = 0;
    Essence exclude[ESSENCE_COUNT];
    int exclude_count = 0;
    // Store
    bool what_spent = false;
    bool on_target = false;
    // Damage
    std::vector<Cost> defense_options;
    bool all_players = false;
    bool include_self = false;
    // Draw
    int discard_after = 0;
    bool require_deck_has_cards = false;
    // Straighten
    StraightenTarget straighten_target = StraightenTarget::SELECTED;
    // Place
    SelectCardFilter filter;
    int discount = 0;
    bool free = false;
    bool can_discount_gold = false;
    // GainDestroyedCost
    bool as_any = false;
    bool as_gold = false;
    int bonus = 0;
    // GainFromOpponent
    int their_essence = -1;
    int your_essence = -1;
    // GainGoldFromCost
    int divisor = 1;
};

// ---- Power ---------------------------------------------------------------
struct Power {
    bool requires_turn = false;
    std::vector<Cost> costs;
    std::vector<Effect> effects;
    PowerType power_type = PowerType::ACTION;
    ReactTrigger react_trigger = ReactTrigger::NONE;
    bool usable_when_turned = false;

    bool is_react() const { return power_type != PowerType::ACTION; }

    const Cost* get_cost(CostType t) const {
        for (auto& c : costs) if (c.type == t) return &c;
        return nullptr;
    }
    bool has_cost(CostType t) const { return get_cost(t) != nullptr; }

    bool has_turn_component_cost(TurnableType tt) const {
        for (auto& c : costs)
            if (c.type == CostType::TurnComponent && c.turnable_type == tt) return true;
        return false;
    }
    bool has_destroy_component_cost(DestroyMode dm) const {
        for (auto& c : costs)
            if (c.type == CostType::DestroyComponent && c.destroy_mode == dm) return true;
        return false;
    }
    Pool get_essence_cost() const {
        const Cost* c = get_cost(CostType::PayEssence);
        if (c) return c->essences;
        return Pool();
    }
    int get_any_cost() const {
        int total = 0;
        for (auto& c : costs) if (c.type == CostType::PayEssence) total += c.any_amount;
        return total;
    }
    // union of excludes across PayEssence costs that have any_amount>0
    void get_any_cost_exclude(bool out[ESSENCE_COUNT]) const {
        for (int i = 0; i < ESSENCE_COUNT; i++) out[i] = false;
        for (auto& c : costs)
            if (c.type == CostType::PayEssence && c.any_amount > 0)
                for (int k = 0; k < c.exclude_count; k++) out[(int)c.exclude[k]] = true;
    }
    const Cost* get_select_card_cost() const { return get_cost(CostType::SelectCard); }

    bool requires_target() const; // defined in engine
};

// ---- CollectAbility ------------------------------------------------------
struct CollectAbility {
    Pool essences;
    int choice_mask = 0;
    int any_amount = 0;
    int alt_any_amount = 0;
    int restriction_mask = 0;
    ConditionalType conditional_type = ConditionalType::NONE;
    int per_stored_essence_multiplier = 0;
    Pool cost_essences;
    bool cost_turn = false;

    bool has_conditional() const { return conditional_type != ConditionalType::NONE; }
    bool has_collect_cost() const { return !cost_essences.is_empty() || cost_turn; }
    int choice_mask_to_restriction() const { return (~choice_mask) & 0b11111; }
};

// ---- EntityData ----------------------------------------------------------
struct EntityData {
    std::string name;
    std::vector<Power> powers;
    bool has_collect = false;
    CollectAbility collect_ability;

    bool has_placement_cost = false;
    Pool placement_cost;
    int placement_cost_any = 0;

    int card_type_mask = 0;
    int entity_flags = 0;

    int victory_points = 0;
    int victory_points_per_two_artifacts = 0;

    Discount discount;

    int points_per_essence[ESSENCE_COUNT] = {0,0,0,0,0};

    int base_points = 0;
    int vp_per_dragon = 0;
    int vp_per_creature = 0;
    int vp_per_artifact_count_num = 0;
    int vp_per_artifact_count_denom = 1;

    bool is_dragon() const { return (card_type_mask & CTM_DRAGON) != 0; }
    bool is_creature() const { return (card_type_mask & CTM_CREATURE) != 0; }
    bool cannot_be_free_placed() const { return (entity_flags & EF_CANNOT_BE_FREE_PLACED) != 0; }
    int total_placement_cost() const {
        if (!has_placement_cost) return placement_cost_any;
        return placement_cost.total() + placement_cost_any;
    }
};

// ---- CardDatabase --------------------------------------------------------
struct CardDatabase {
    std::vector<EntityData> mages;
    std::vector<EntityData> magic_items;
    std::vector<EntityData> artifacts;
    std::vector<EntityData> monuments;
    std::vector<EntityData> places_of_power;

    const EntityData* get(const std::vector<EntityData>& v, const std::string& name) const {
        for (auto& e : v) if (e.name == name) return &e;
        return nullptr;
    }
    const EntityData* get_mage(const std::string& n) const { return get(mages, n); }
    const EntityData* get_magic_item(const std::string& n) const { return get(magic_items, n); }
    const EntityData* get_artifact(const std::string& n) const { return get(artifacts, n); }
    const EntityData* get_monument(const std::string& n) const { return get(monuments, n); }
    const EntityData* get_place_of_power(const std::string& n) const { return get(places_of_power, n); }
};

// Load the card database from cards.json (path relative to executable or cwd).
CardDatabase load_card_database(const std::string& path);
const CardDatabase& get_card_database();

} // namespace ra
