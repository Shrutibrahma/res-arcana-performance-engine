// Loads cards.json into the immutable CardDatabase. Mirrors reference
// engine/card_data.py.
#include "cards.hpp"
#include "vendor/nlohmann/json.hpp"
#include <fstream>
#include <stdexcept>
#include <cstdlib>

using json = nlohmann::json;

namespace ra {

static int essence_from_name(const std::string& n) {
    if (n == "ELAN") return ELAN;
    if (n == "LIFE") return LIFE;
    if (n == "CALM") return CALM;
    if (n == "DEATH") return DEATH;
    if (n == "GOLD") return GOLD;
    throw std::runtime_error("bad essence: " + n);
}

static Pool pool_from_json(const json& j) {
    Pool p;
    if (j.is_array()) {
        for (int i = 0; i < ESSENCE_COUNT && i < (int)j.size(); i++)
            p.v[i] = (int16_t)j[i].get<int>();
    }
    return p;
}

static SelectCardLocation scl_from_name(const std::string& n) {
    if (n == "NONE") return SelectCardLocation::NONE;
    if (n == "HAND") return SelectCardLocation::HAND;
    if (n == "IN_PLAY") return SelectCardLocation::IN_PLAY;
    if (n == "DISCARD") return SelectCardLocation::DISCARD;
    if (n == "ANY_DISCARD") return SelectCardLocation::ANY_DISCARD;
    if (n == "MONUMENT") return SelectCardLocation::MONUMENT;
    throw std::runtime_error("bad select card location: " + n);
}

static SelectCardFilter filter_from_json(const json& d) {
    SelectCardFilter f;
    f.location = scl_from_name(d.at("location").get<std::string>());
    f.require_tapped = d.value("require_tapped", false);
    f.card_type_mask = d.value("card_type_mask", 0);
    f.own_cards_only = d.value("own_cards_only", false);
    f.component_type_mask = d.value("component_type_mask", 0);
    f.exclude_self = d.value("exclude_self", false);
    return f;
}

static TurnableType tt_from_name(const std::string& n) {
    if (n == "DRAGON") return TurnableType::DRAGON;
    if (n == "CREATURE") return TurnableType::CREATURE;
    if (n == "MAGE") return TurnableType::MAGE;
    throw std::runtime_error("bad turnable type: " + n);
}
static DestroyMode dm_from_name(const std::string& n) {
    if (n == "ANY") return DestroyMode::ANY;
    if (n == "SELF") return DestroyMode::SELF;
    if (n == "ANOTHER") return DestroyMode::ANOTHER;
    throw std::runtime_error("bad destroy mode: " + n);
}
static StraightenTarget st_from_name(const std::string& n) {
    if (n == "SELECTED") return StraightenTarget::SELECTED;
    if (n == "SELF") return StraightenTarget::SELF;
    throw std::runtime_error("bad straighten target: " + n);
}

static void set_exclude(Cost& c, const json& d) {
    if (d.contains("exclude")) {
        for (auto& x : d["exclude"]) {
            c.exclude[c.exclude_count++] = (Essence)essence_from_name(x.get<std::string>());
        }
    }
}

static Cost cost_from_json(const json& d) {
    Cost c;
    std::string t = d.at("type").get<std::string>();
    if (t == "PayEssence") {
        c.type = CostType::PayEssence;
        if (d.contains("essences")) c.essences = pool_from_json(d["essences"]);
        c.any_amount = d.value("any_amount", 0);
        set_exclude(c, d);
    } else if (t == "TurnComponent") {
        c.type = CostType::TurnComponent;
        c.turnable_type = tt_from_name(d.at("turnable_type").get<std::string>());
    } else if (t == "RemoveFromCard") {
        c.type = CostType::RemoveFromCard;
        c.essences = pool_from_json(d.at("essences"));
    } else if (t == "PayIdentical") {
        c.type = CostType::PayIdentical;
        c.base_cost = d.value("base_cost", 0);
        c.min_amount = d.at("min_amount").get<int>();
        if (d.contains("essence_type") && !d["essence_type"].is_null())
            c.essence_type = essence_from_name(d["essence_type"].get<std::string>());
        else
            c.essence_type = -1;
    } else if (t == "DestroyComponent") {
        c.type = CostType::DestroyComponent;
        c.destroy_mode = dm_from_name(d.at("destroy_mode").get<std::string>());
    } else if (t == "DestroyCardType") {
        c.type = CostType::DestroyCardType;
        c.card_type_mask = d.at("card_type_mask").get<int>();
    } else if (t == "DiscardCard") {
        c.type = CostType::DiscardCard;
        c.card_type_mask = d.value("card_type_mask", 0);
        c.exclude_entity_flags = d.value("exclude_entity_flags", 0);
    } else if (t == "SelectPlayer") {
        c.type = CostType::SelectPlayer;
        c.opponent_only = d.value("opponent_only", false);
    } else if (t == "SelectCard") {
        c.type = CostType::SelectCard;
        c.filter = filter_from_json(d.at("filter"));
    } else {
        throw std::runtime_error("Unknown cost type: " + t);
    }
    return c;
}

static Effect effect_from_json(const json& d) {
    Effect e;
    std::string t = d.at("type").get<std::string>();
    if (t == "Gain") {
        e.type = EffectType::Gain;
        e.essences = pool_from_json(d.at("essences"));
    } else if (t == "GainAny") {
        e.type = EffectType::GainAny;
        e.amount = d.at("amount").get<int>();
        if (d.contains("exclude"))
            for (auto& x : d["exclude"]) e.exclude[e.exclude_count++] = (Essence)essence_from_name(x.get<std::string>());
    } else if (t == "Store") {
        e.type = EffectType::Store;
        if (d.contains("essences")) e.essences = pool_from_json(d["essences"]);
        e.amount = d.value("any_amount", 0);
        if (d.contains("exclude"))
            for (auto& x : d["exclude"]) e.exclude[e.exclude_count++] = (Essence)essence_from_name(x.get<std::string>());
        e.what_spent = d.value("what_spent", false);
        e.on_target = d.value("on_target", false);
    } else if (t == "RivalsGain") {
        e.type = EffectType::RivalsGain;
        e.essences = pool_from_json(d.at("essences"));
    } else if (t == "Damage") {
        e.type = EffectType::Damage;
        e.amount = d.at("amount").get<int>();
        if (d.contains("defense_options"))
            for (auto& c : d["defense_options"]) e.defense_options.push_back(cost_from_json(c));
        e.all_players = d.value("all_players", false);
        e.include_self = d.value("include_self", false);
    } else if (t == "Draw") {
        e.type = EffectType::Draw;
        e.amount = d.at("amount").get<int>();
        e.discard_after = d.value("discard_after", 0);
        e.require_deck_has_cards = d.value("require_deck_has_cards", false);
    } else if (t == "IgnoreDamage") {
        e.type = EffectType::IgnoreDamage;
    } else if (t == "CheckVictory") {
        e.type = EffectType::CheckVictory;
    } else if (t == "Straighten") {
        e.type = EffectType::Straighten;
        e.straighten_target = st_from_name(d.at("target").get<std::string>());
    } else if (t == "Scry") {
        e.type = EffectType::Scry;
        e.amount = d.at("amount").get<int>();
    } else if (t == "Place") {
        e.type = EffectType::Place;
        e.filter = filter_from_json(d.at("filter"));
        e.discount = d.value("discount", 0);
        e.free = d.value("free", false);
        e.can_discount_gold = d.value("can_discount_gold", false);
    } else if (t == "GainDestroyedCost") {
        e.type = EffectType::GainDestroyedCost;
        e.as_any = d.value("as_any", false);
        e.as_gold = d.value("as_gold", false);
        e.bonus = d.value("bonus", 0);
    } else if (t == "GainGoldEqualToSameSpent") {
        e.type = EffectType::GainGoldEqualToSameSpent;
    } else if (t == "GainFromOpponent") {
        e.type = EffectType::GainFromOpponent;
        e.their_essence = essence_from_name(d.at("their_essence").get<std::string>());
        e.your_essence = essence_from_name(d.at("your_essence").get<std::string>());
    } else if (t == "GainSameTypeAsSpent") {
        e.type = EffectType::GainSameTypeAsSpent;
    } else if (t == "TempVP") {
        e.type = EffectType::TempVP;
        e.amount = d.at("amount").get<int>();
    } else if (t == "GainGoldFromCost") {
        e.type = EffectType::GainGoldFromCost;
        e.divisor = d.at("divisor").get<int>();
    } else {
        throw std::runtime_error("Unknown effect type: " + t);
    }
    return e;
}

static PowerType pt_from_name(const std::string& n) {
    if (n == "ACTION") return PowerType::ACTION;
    if (n == "IGNORE") return PowerType::IGNORE;
    if (n == "VICTORY") return PowerType::VICTORY;
    if (n == "BOUGHT") return PowerType::BOUGHT;
    throw std::runtime_error("bad power type: " + n);
}
static ReactTrigger rt_from_name(const std::string& n) {
    if (n == "NONE") return ReactTrigger::NONE;
    if (n == "DAMAGE") return ReactTrigger::DAMAGE;
    if (n == "VICTORY_CHECK") return ReactTrigger::VICTORY_CHECK;
    if (n == "DRAGON_ATTACK") return ReactTrigger::DRAGON_ATTACK;
    throw std::runtime_error("bad react trigger: " + n);
}

static Power power_from_json(const json& d) {
    Power p;
    p.power_type = pt_from_name(d.at("power_type").get<std::string>());
    p.requires_turn = d.value("requires_turn", false);
    p.react_trigger = rt_from_name(d.value("react_trigger", std::string("NONE")));
    p.usable_when_turned = d.value("usable_when_turned", false);
    if (d.contains("costs"))
        for (auto& c : d["costs"]) p.costs.push_back(cost_from_json(c));
    if (d.contains("effects"))
        for (auto& e : d["effects"]) p.effects.push_back(effect_from_json(e));
    return p;
}

static Discount discount_from_json(const json& d) {
    Discount dc;
    dc.artifact = d.value("artifact", 0);
    dc.dragon = d.value("dragon", 0);
    dc.creature = d.value("creature", 0);
    dc.can_discount_gold = d.value("can_discount_gold", false);
    return dc;
}

static CollectAbility collect_from_json(const json& d) {
    CollectAbility c;
    if (d.contains("essences")) c.essences = pool_from_json(d["essences"]);
    c.choice_mask = d.value("choice_mask", 0);
    c.any_amount = d.value("any_amount", 0);
    c.alt_any_amount = d.value("alt_any_amount", 0);
    c.restriction_mask = d.value("restriction_mask", 0);
    if (d.contains("conditional_type") && !d["conditional_type"].is_null()) {
        std::string ct = d["conditional_type"].get<std::string>();
        if (ct == "STORED_GOLD") c.conditional_type = ConditionalType::STORED_GOLD;
        else if (ct == "PER_STORED_ESSENCE") c.conditional_type = ConditionalType::PER_STORED_ESSENCE;
    }
    c.per_stored_essence_multiplier = d.value("per_stored_essence_multiplier", 0);
    if (d.contains("cost_essences")) c.cost_essences = pool_from_json(d["cost_essences"]);
    c.cost_turn = d.value("cost_turn", false);
    return c;
}

static EntityData entity_from_json(const json& d) {
    EntityData e;
    e.name = d.at("name").get<std::string>();
    if (d.contains("powers"))
        for (auto& p : d["powers"]) e.powers.push_back(power_from_json(p));
    if (d.contains("collect_ability")) {
        e.has_collect = true;
        e.collect_ability = collect_from_json(d["collect_ability"]);
    }
    if (d.contains("placement_cost")) {
        e.has_placement_cost = true;
        e.placement_cost = pool_from_json(d["placement_cost"]);
    }
    e.placement_cost_any = d.value("placement_cost_any", 0);
    e.card_type_mask = d.value("card_type_mask", 0);
    e.entity_flags = d.value("entity_flags", 0);
    e.victory_points = d.value("victory_points", 0);
    e.victory_points_per_two_artifacts = d.value("victory_points_per_two_artifacts", 0);
    if (d.contains("discount")) e.discount = discount_from_json(d["discount"]);
    if (d.contains("points_per_essence")) {
        const json& ppe = d["points_per_essence"];
        for (int i = 0; i < ESSENCE_COUNT && i < (int)ppe.size(); i++)
            e.points_per_essence[i] = ppe[i].get<int>();
    }
    e.base_points = d.value("base_points", 0);
    e.vp_per_dragon = d.value("vp_per_dragon", 0);
    e.vp_per_creature = d.value("vp_per_creature", 0);
    e.vp_per_artifact_count_num = d.value("vp_per_artifact_count_num", 0);
    e.vp_per_artifact_count_denom = d.value("vp_per_artifact_count_denom", 1);
    return e;
}

CardDatabase load_card_database(const std::string& path) {
    std::ifstream f(path);
    if (!f.good()) throw std::runtime_error("cannot open cards.json: " + path);
    json raw;
    f >> raw;
    CardDatabase db;
    for (auto& d : raw["mages"]) db.mages.push_back(entity_from_json(d));
    for (auto& d : raw["magic_items"]) db.magic_items.push_back(entity_from_json(d));
    for (auto& d : raw["artifacts"]) db.artifacts.push_back(entity_from_json(d));
    for (auto& d : raw["monuments"]) db.monuments.push_back(entity_from_json(d));
    for (auto& d : raw["places_of_power"]) db.places_of_power.push_back(entity_from_json(d));
    return db;
}

static CardDatabase* g_db = nullptr;
std::string g_cards_path; // set by main before first use (optional)

const CardDatabase& get_card_database() {
    if (g_db) return *g_db;
    const char* candidates[] = {
        nullptr, // g_cards_path placeholder
        "data/cards.json",
        "../data/cards.json",
        "../../data/cards.json",
        "./cards.json",
    };
    for (int i = 0; i < 5; i++) {
        std::string p;
        if (i == 0) { if (g_cards_path.empty()) continue; p = g_cards_path; }
        else p = candidates[i];
        std::ifstream test(p);
        if (test.good()) {
            test.close();
            g_db = new CardDatabase(load_card_database(p));
            return *g_db;
        }
    }
    throw std::runtime_error("cards.json not found in any candidate path");
}

} // namespace ra
