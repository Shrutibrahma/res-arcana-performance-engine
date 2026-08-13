// Wire protocol: JSON-lines server on stdin/stdout, plus step<->action
// conversion, game setup, and the get_state dump. Mirrors reference
// expectimax.py's main loop and engine/step_*.py.
#include "engine.hpp"
#include "vendor/nlohmann/json.hpp"
#include <cstdio>
#include <iostream>
#include <string>
#include <vector>

using json = nlohmann::json;
namespace ra {

// ---- session ----
static GameState g_state;
static int g_player_id = 0;
static std::vector<Action> g_cached;

// ---- name tables ----
static const char* PHASE_NAMES[] = {
    "SETUP_GAME", "SETUP_CHOOSE_MAGES", "SETUP_CHOOSE_ITEMS",
    "COLLECT", "ACTIONS", "VICTORY_CHECK", "GAME_OVER"};
static const char* KIND_NAMES[] = {"ARTIFACT", "MAGE", "MAGIC_ITEM", "MONUMENT", "PLACE_OF_POWER"};
static const char* LOC_NAMES[] = {"OUT_OF_GAME", "AVAILABLE", "MONUMENT_DECK", "DECK",
                                  "HAND", "IN_PLAY", "DISCARD", "BEING_CHOSEN"};

// ---- pool / enum json ----
static Pool parse_pool_obj(const json& o) {
    Pool p;
    if (o.is_object()) {
        p.v[ELAN]  = (int16_t)o.value("elan", 0);
        p.v[LIFE]  = (int16_t)o.value("life", 0);
        p.v[CALM]  = (int16_t)o.value("calm", 0);
        p.v[DEATH] = (int16_t)o.value("death", 0);
        p.v[GOLD]  = (int16_t)o.value("gold", 0);
    }
    return p;
}
static Pool parse_pool(const json& j, const char* key) {
    if (j.contains(key)) return parse_pool_obj(j[key]);
    return Pool();
}
static json pool_to_json(const Pool& p) {
    json o = json::object();
    if (p.v[ELAN])  o["elan"]  = p.v[ELAN];
    if (p.v[LIFE])  o["life"]  = p.v[LIFE];
    if (p.v[CALM])  o["calm"]  = p.v[CALM];
    if (p.v[DEATH]) o["death"] = p.v[DEATH];
    if (p.v[GOLD])  o["gold"]  = p.v[GOLD];
    return o;
}
static json enum_json(const char* cls, int value) {
    json o = json::object();
    o["__enum__"] = cls;
    o["value"] = value;
    return o;
}
static int parse_enum(const json& j, const char* key, int def) {
    if (j.contains(key) && j[key].is_object() && j[key].contains("value")) {
        const auto& v = j[key]["value"];
        if (v.is_number_integer()) return v.get<int>();
    }
    return def;
}

// ---- name resolution (names are unique across all entities) ----
static int16_t resolve_by_name(const GameState& s, const std::string& name) {
    for (int i = 0; i < s.entity_count; i++) {
        const Entity& e = s.entities[i];
        if (e.data && e.data->name == name) return (int16_t)i;
    }
    return -1;
}
static int16_t resolve_opt(const GameState& s, const json& j, const char* key) {
    if (j.contains(key) && j[key].is_string())
        return resolve_by_name(s, j[key].get<std::string>());
    return -1;
}

// ---- setup ----
static void build_setup_state(GameState& s, const json& setup, int num_players) {
    const CardDatabase& db = get_card_database();
    s = GameState();
    s.num_players = (uint8_t)num_players;
    s.phase = GamePhase::SETUP_GAME;
    for (int i = 0; i < num_players; i++) {
        s.players[i].pid = (uint8_t)i;
        s.players[i].is_active = true;
        s.players[i].pool = Pool(1, 1, 1, 1, 1);
        s.players[i].has_passed = false;
        s.players[i].has_first_player_token = false;
    }
    s.temp_vp[0] = s.temp_vp[1] = 0;

    const json& pops = setup.at("places_of_power");
    const json& mon_display = setup.at("monument_display");
    const json& mon_deck = setup.at("monument_deck");
    const json& mage_options = setup.at("mage_options");
    int first_player = setup.value("first_player", 0);
    static const json empty_arr = json::array();
    const json& artifact_decks = (setup.contains("artifact_decks") && setup["artifact_decks"].is_array())
                                     ? setup["artifact_decks"] : empty_arr;

    int idx = 0;
    auto put = [&](ComponentType kind, const EntityData* d, CardLocation loc, int owner) {
        Entity& e = s.entities[idx++];
        e = Entity{};
        e.kind = kind;
        e.data = d;
        e.location = loc;
        e.owner_id = (uint8_t)owner;
        e.is_turned = false;
        e.has_essences = false;
        e.order_index = UNKNOWN_ORDER;
    };

    s.artifact_start = (uint8_t)idx;
    for (int pid = 0; pid < (int)artifact_decks.size(); pid++) {
        const json& names = artifact_decks[pid];
        for (int i = 0; i < (int)names.size(); i++) {
            const EntityData* d = db.get_artifact(names[i].get<std::string>());
            put(ComponentType::ARTIFACT, d, (i < 3) ? CardLocation::HAND : CardLocation::DECK, pid);
        }
    }
    s.artifact_end = (uint8_t)idx;

    s.mage_start = (uint8_t)idx;
    for (int pid = 0; pid < (int)mage_options.size(); pid++)
        for (const auto& mn : mage_options[pid])
            put(ComponentType::MAGE, db.get_mage(mn.get<std::string>()), CardLocation::BEING_CHOSEN, pid);
    s.mage_end = (uint8_t)idx;

    s.magic_item_start = (uint8_t)idx;
    for (const auto& d : db.magic_items)
        put(ComponentType::MAGIC_ITEM, &d, CardLocation::AVAILABLE, UNOWNED);
    s.magic_item_end = (uint8_t)idx;

    s.monument_start = (uint8_t)idx;
    for (const auto& mn : mon_display)
        put(ComponentType::MONUMENT, db.get_monument(mn.get<std::string>()), CardLocation::AVAILABLE, UNOWNED);
    for (const auto& mn : mon_deck)
        put(ComponentType::MONUMENT, db.get_monument(mn.get<std::string>()), CardLocation::MONUMENT_DECK, UNOWNED);
    s.monument_end = (uint8_t)idx;

    s.pop_start = (uint8_t)idx;
    for (const auto& pn : pops)
        put(ComponentType::PLACE_OF_POWER, db.get_place_of_power(pn.get<std::string>()), CardLocation::AVAILABLE, UNOWNED);
    s.pop_end = (uint8_t)idx;

    s.entity_count = (uint8_t)idx;

    s.current_player_index = (uint8_t)first_player;
    s.first_player_index = (uint8_t)first_player;
    for (int i = 0; i < num_players; i++)
        s.players[i].has_first_player_token = (i == first_player);

    if (setup.contains("starting_essences") && setup["starting_essences"].is_array()) {
        const json& se = setup["starting_essences"];
        for (int pid = 0; pid < (int)se.size() && pid < num_players; pid++)
            s.players[pid].pool = parse_pool_obj(se[pid]);
    }

    s.phase = GamePhase::SETUP_CHOOSE_MAGES;
}

// ---- json -> Action (deserialize_step + step_to_action) ----
static Action json_to_action(const GameState& s, const json& j) {
    Action a;
    std::string t = j.at("__type__").get<std::string>();
    a.pid = (uint8_t)j.value("player_id", 0);

    auto names_list = [&](const char* key, int16_t* dst, int& n) {
        n = 0;
        if (j.contains(key) && j[key].is_array())
            for (const auto& x : j[key]) {
                int16_t e = resolve_by_name(s, x.get<std::string>());
                RA_CHECK(e >= 0);
                dst[n++] = e;
            }
    };

    if (t == "UsePower") {
        a.type = ActionType::UsePower;
        a.eid = resolve_by_name(s, j.at("card_name").get<std::string>());
        a.power_index = j.value("power_index", 0);
        a.target_eid = resolve_opt(s, j, "target_name");
        a.target_pid = j.contains("target_player_id") && j["target_player_id"].is_number_integer()
                           ? j["target_player_id"].get<int>() : -1;
        a.pay = parse_pool(j, "pay");
        a.gain = parse_pool(j, "gain");
    } else if (t == "PlaceArtifact") {
        a.type = ActionType::PlaceArtifact;
        a.eid = resolve_by_name(s, j.at("artifact_name").get<std::string>());
        a.pay = parse_pool(j, "pay");
    } else if (t == "Pass") {
        a.type = ActionType::Pass;
        a.eid = resolve_by_name(s, j.at("item_name").get<std::string>());
    } else if (t == "Decline") {
        a.type = ActionType::Decline;
        a.eid = resolve_by_name(s, j.at("card_name").get<std::string>());
    } else if (t == "ClaimMonument") {
        a.type = ActionType::ClaimMonument;
        a.eid = resolve_by_name(s, j.at("monument_name").get<std::string>());
    } else if (t == "ClaimTopMonument") {
        a.type = ActionType::ClaimTopMonument;
    } else if (t == "ClaimPlaceOfPower") {
        a.type = ActionType::ClaimPlaceOfPower;
        a.eid = resolve_by_name(s, j.at("pop_name").get<std::string>());
        a.pay = parse_pool(j, "pay");
    } else if (t == "DiscardForEssences") {
        a.type = ActionType::DiscardForEssences;
        a.eid = resolve_by_name(s, j.at("card_name").get<std::string>());
        a.gain = parse_pool(j, "gain");
    } else if (t == "LifeLossReact") {
        a.type = ActionType::LifeLossReact;
        a.eid = resolve_by_name(s, j.at("card_name").get<std::string>());
        a.power_index = j.value("power_index", 0);
        a.target_eid = resolve_opt(s, j, "target_name");
        a.pay = parse_pool(j, "pay");
        a.gain = parse_pool(j, "gain");
    } else if (t == "VictoryReact") {
        a.type = ActionType::VictoryReact;
        a.eid = resolve_by_name(s, j.at("card_name").get<std::string>());
        a.power_index = j.value("power_index", 0);
        a.target_eid = resolve_opt(s, j, "target_name");
        a.pay = parse_pool(j, "pay");
    } else if (t == "LifeLossChoice") {
        a.type = ActionType::LifeLossChoice;
        a.pay = parse_pool(j, "pay");
    } else if (t == "TakeStored") {
        a.type = ActionType::TakeStored;
        a.eid = resolve_by_name(s, j.at("card_name").get<std::string>());
        a.decision = (CollectDecision)parse_enum(j, "decision", (int)CollectDecision::TAKE_STORED);
    } else if (t == "CollectCost") {
        a.type = ActionType::CollectCost;
        a.eid = resolve_by_name(s, j.at("card_name").get<std::string>());
        a.decision = (CollectDecision)parse_enum(j, "decision", (int)CollectDecision::PAY_COST);
    } else if (t == "Gain") {
        a.type = ActionType::Gain;
        a.eid = resolve_by_name(s, j.at("card_name").get<std::string>());
        a.gain = parse_pool(j, "gain");
        a.use_alt = j.value("use_alt", false);
    } else if (t == "ScryDeckChoice") {
        a.type = ActionType::ScryDeckChoice;
        a.scry_target = (DeckType)parse_enum(j, "scry_target", (int)DeckType::ARTIFACT);
    } else if (t == "ScryChoice") {
        a.type = ActionType::ScryChoice;
        a.scry_order_n = 0;
        if (j.contains("scry_order") && j["scry_order"].is_array())
            for (const auto& x : j["scry_order"]) a.scry_order[a.scry_order_n++] = (int8_t)x.get<int>();
    } else if (t == "DiscardChoice") {
        a.type = ActionType::DiscardChoice;
        names_list("card_names", a.list_a, a.list_a_n);
    } else if (t == "ChooseMage") {
        a.type = ActionType::ChooseMage;
        a.eid = resolve_by_name(s, j.at("mage_name").get<std::string>());
    } else if (t == "ChooseMagicItem") {
        a.type = ActionType::ChooseMagicItem;
        a.eid = resolve_by_name(s, j.at("item_name").get<std::string>());
    } else if (t == "ResolveDrawReveal") {
        a.type = ActionType::ResolveDrawReveal;
        names_list("known_cards", a.list_a, a.list_a_n);
        names_list("revealed_cards", a.list_b, a.list_b_n);
    } else if (t == "ResolveScryReveal") {
        a.type = ActionType::ResolveScryReveal;
        names_list("revealed_cards", a.list_b, a.list_b_n);
    } else if (t == "ResolveMonumentDraw") {
        a.type = ActionType::ResolveMonumentDraw;
        a.eid = resolve_by_name(s, j.at("monument_name").get<std::string>());
    } else if (t == "ResolveMonumentReveal") {
        a.type = ActionType::ResolveMonumentReveal;
        a.eid = resolve_by_name(s, j.at("monument_name").get<std::string>());
    } else {
        throw IllegalAction{};
    }
    return a;
}

static const char* ename(const GameState& s, int16_t eid) {
    return s.entities[eid].data->name.c_str();
}

// ---- Action -> json (action_to_step + serialize_step) ----
static json action_to_json(const GameState& s, const Action& a) {
    json o = json::object();
    auto put_pay_opt = [&](const char* key, const Pool& p) { if (!p.is_empty()) o[key] = pool_to_json(p); };
    switch (a.type) {
        case ActionType::Pass:
            o["__type__"] = "Pass";
            o["item_name"] = ename(s, a.eid);
            o["player_id"] = a.pid;
            break;
        case ActionType::UsePower:
            o["__type__"] = "UsePower";
            o["card_name"] = ename(s, a.eid);
            o["power_index"] = a.power_index;
            o["player_id"] = a.pid;
            if (a.target_eid >= 0) o["target_name"] = ename(s, a.target_eid);
            if (a.target_pid >= 0) o["target_player_id"] = a.target_pid;
            put_pay_opt("pay", a.pay);
            put_pay_opt("gain", a.gain);
            break;
        case ActionType::PlaceArtifact:
            o["__type__"] = "PlaceArtifact";
            o["artifact_name"] = ename(s, a.eid);
            o["pay"] = pool_to_json(a.pay);  // required field: always emitted
            o["player_id"] = a.pid;
            break;
        case ActionType::ClaimMonument:
            o["__type__"] = "ClaimMonument";
            o["monument_name"] = ename(s, a.eid);
            o["player_id"] = a.pid;
            break;
        case ActionType::ClaimTopMonument:
            o["__type__"] = "ClaimTopMonument";
            o["player_id"] = a.pid;
            break;
        case ActionType::ResolveMonumentDraw:
            o["__type__"] = "ResolveMonumentDraw";
            o["monument_name"] = ename(s, a.eid);
            o["player_id"] = a.pid;
            break;
        case ActionType::ResolveMonumentReveal:
            o["__type__"] = "ResolveMonumentReveal";
            o["monument_name"] = ename(s, a.eid);
            o["player_id"] = a.pid;
            break;
        case ActionType::ClaimPlaceOfPower:
            o["__type__"] = "ClaimPlaceOfPower";
            o["pop_name"] = ename(s, a.eid);
            o["pay"] = pool_to_json(a.pay);
            o["player_id"] = a.pid;
            break;
        case ActionType::DiscardForEssences:
            o["__type__"] = "DiscardForEssences";
            o["card_name"] = ename(s, a.eid);
            o["gain"] = pool_to_json(a.gain);
            o["player_id"] = a.pid;
            break;
        case ActionType::LifeLossReact:
            o["__type__"] = "LifeLossReact";
            o["card_name"] = ename(s, a.eid);
            o["power_index"] = a.power_index;
            o["player_id"] = a.pid;
            if (a.target_eid >= 0) o["target_name"] = ename(s, a.target_eid);
            put_pay_opt("pay", a.pay);
            put_pay_opt("gain", a.gain);
            break;
        case ActionType::VictoryReact:
            o["__type__"] = "VictoryReact";
            o["card_name"] = ename(s, a.eid);
            o["power_index"] = a.power_index;
            o["player_id"] = a.pid;
            if (a.target_eid >= 0) o["target_name"] = ename(s, a.target_eid);
            put_pay_opt("pay", a.pay);
            break;
        case ActionType::LifeLossChoice:
            o["__type__"] = "LifeLossChoice";
            o["player_id"] = a.pid;
            put_pay_opt("pay", a.pay);
            break;
        case ActionType::TakeStored:
            o["__type__"] = "TakeStored";
            o["card_name"] = ename(s, a.eid);
            o["player_id"] = a.pid;
            o["decision"] = enum_json("CollectDecision", (int)a.decision);
            break;
        case ActionType::CollectCost:
            o["__type__"] = "CollectCost";
            o["card_name"] = ename(s, a.eid);
            o["player_id"] = a.pid;
            o["decision"] = enum_json("CollectDecision", (int)a.decision);
            break;
        case ActionType::Gain:
            o["__type__"] = "Gain";
            o["card_name"] = ename(s, a.eid);
            o["gain"] = pool_to_json(a.gain);
            o["player_id"] = a.pid;
            if (a.use_alt) o["use_alt"] = true;
            break;
        case ActionType::ScryDeckChoice:
            o["__type__"] = "ScryDeckChoice";
            o["player_id"] = a.pid;
            o["scry_target"] = enum_json("DeckType", (int)a.scry_target);
            break;
        case ActionType::ScryChoice: {
            o["__type__"] = "ScryChoice";
            o["player_id"] = a.pid;
            if (a.scry_order_n > 0) {
                json arr = json::array();
                for (int i = 0; i < a.scry_order_n; i++) arr.push_back((int)a.scry_order[i]);
                o["scry_order"] = arr;
            }
            break;
        }
        case ActionType::DiscardChoice: {
            o["__type__"] = "DiscardChoice";
            json arr = json::array();
            for (int i = 0; i < a.list_a_n; i++) arr.push_back(ename(s, a.list_a[i]));
            o["card_names"] = arr;
            o["player_id"] = a.pid;
            break;
        }
        case ActionType::ResolveDrawReveal: {
            o["__type__"] = "ResolveDrawReveal";
            if (a.list_a_n > 0) {
                json arr = json::array();
                for (int i = 0; i < a.list_a_n; i++) arr.push_back(ename(s, a.list_a[i]));
                o["known_cards"] = arr;
            }
            if (a.list_b_n > 0) {
                json arr = json::array();
                for (int i = 0; i < a.list_b_n; i++) arr.push_back(ename(s, a.list_b[i]));
                o["revealed_cards"] = arr;
            }
            o["player_id"] = a.pid;
            break;
        }
        case ActionType::ResolveScryReveal: {
            o["__type__"] = "ResolveScryReveal";
            json arr = json::array();
            for (int i = 0; i < a.list_b_n; i++) arr.push_back(ename(s, a.list_b[i]));
            o["revealed_cards"] = arr;
            o["player_id"] = a.pid;
            break;
        }
        case ActionType::Decline:
            o["__type__"] = "Decline";
            o["card_name"] = ename(s, a.eid);
            o["player_id"] = a.pid;
            break;
        case ActionType::ChooseMage:
            o["__type__"] = "ChooseMage";
            o["mage_name"] = ename(s, a.eid);
            o["player_id"] = a.pid;
            break;
        case ActionType::ChooseMagicItem:
            o["__type__"] = "ChooseMagicItem";
            o["item_name"] = ename(s, a.eid);
            o["player_id"] = a.pid;
            break;
    }
    return o;
}

// ---- get_state dump ----
static json dump_state(const GameState& s) {
    json o = json::object();
    o["phase"] = PHASE_NAMES[(int)s.phase];
    o["round"] = s.round_number;
    o["current_player"] = s.acting_player();
    o["first_player"] = s.first_player_index;
    json winners = json::array();
    for (int i = 0; i < s.num_players; i++)
        if (s.winner_mask & (1 << i)) winners.push_back(i);
    o["winner_ids"] = winners;

    json players = json::array();
    for (int i = 0; i < s.num_players; i++) {
        json p = json::object();
        const Pool& pool = s.players[i].pool;
        p["pool"] = {pool.v[0], pool.v[1], pool.v[2], pool.v[3], pool.v[4]};
        p["vp"] = calculate_victory_points(s, i);
        p["has_passed"] = s.players[i].has_passed;
        p["has_first_player_token"] = s.players[i].has_first_player_token;
        players.push_back(p);
    }
    o["players"] = players;

    json entities = json::array();
    for (int i = 0; i < s.entity_count; i++) {
        const Entity& e = s.entities[i];
        json je = json::object();
        je["name"] = e.data->name;
        je["kind"] = KIND_NAMES[(int)e.kind];
        je["location"] = LOC_NAMES[(int)e.location];
        je["owner"] = (int)e.owner_id;
        je["is_turned"] = e.is_turned;
        if (e.has_essences) {
            const Pool& p = e.essences_on_card;
            je["essences_on_card"] = {p.v[0], p.v[1], p.v[2], p.v[3], p.v[4]};
        } else {
            je["essences_on_card"] = nullptr;
        }
        je["order_index"] = e.order_index;
        entities.push_back(je);
    }
    o["entities"] = entities;
    return o;
}

static void refresh_actions() {
    int pid = g_state.acting_player();
    g_cached.clear();
    generate_actions(g_state, pid, g_cached);
}

static void respond(const json& msg) {
    std::cout << msg.dump() << "\n";
    std::cout.flush();
}

void run_server() {
    std::ios_base::sync_with_stdio(false);
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        json msg;
        try {
            msg = json::parse(line);
        } catch (...) {
            respond({{"error", "Invalid JSON"}});
            continue;
        }
        std::string cmd = msg.value("cmd", std::string());
        try {
            if (cmd == "quit") {
                respond({{"status", "ok"}});
                break;
            } else if (cmd == "new_game_from_setup") {
                g_player_id = msg.value("player_id", 0);
                int np = msg.value("num_players", 2);
                build_setup_state(g_state, msg.at("setup"), np);
                refresh_actions();
                respond({{"status", "ok"}});
            } else if (cmd == "search") {
                int depth = msg.value("depth", 3);
                int pid = msg.contains("maximizing_pid") && msg["maximizing_pid"].is_number_integer()
                              ? msg["maximizing_pid"].get<int>() : g_player_id;
                SearchResult r = iterative_deepening(g_state, pid, depth);
                json out = json::object();
                out["step"] = action_to_json(g_state, r.best);
                out["nodes"] = r.nodes;
                out["depth"] = r.depth_completed;
                respond(out);
            } else if (cmd == "advance") {
                GameState snap = g_state;
                try {
                    Action a = json_to_action(g_state, msg.at("step"));
                    execute_action(g_state, a);
                    refresh_actions();
                    respond({{"status", "ok"}});
                } catch (const IllegalAction&) {
                    g_state = snap;
                    respond({{"status", "error"}, {"msg", "illegal"}});
                }
            } else if (cmd == "get_state") {
                respond({{"state", dump_state(g_state)}});
            } else if (cmd == "legal_actions") {
                json arr = json::array();
                for (const Action& a : g_cached) arr.push_back(action_to_json(g_state, a));
                respond({{"actions", arr}});
            } else {
                respond({{"error", "Unknown command"}});
            }
        } catch (const std::exception& e) {
            respond({{"error", std::string(cmd) + " failed"}});
        } catch (const IllegalAction&) {
            respond({{"error", std::string(cmd) + " failed"}});
        }
    }
}

} // namespace ra

int main() {
    ra::run_server();
    return 0;
}
