// Shared declarations across the engine/move-gen/search/wire files.
// The concrete Action type, the illegal-action signal, and the cross-file
// function prototypes all live here.
#pragma once
#include "common.hpp"
#include "cards.hpp"
#include "state.hpp"
#include <vector>

namespace ra {

// IllegalAction is defined in common.hpp.
#define RA_CHECK(cond) do { if (!(cond)) throw ::ra::IllegalAction{}; } while (0)

// ---- Concrete action (flattened tagged POD) ------------------------------
enum class ActionType : uint8_t {
    ChooseMage, ChooseMagicItem, PlaceArtifact, ClaimMonument, ClaimTopMonument,
    ClaimPlaceOfPower, DiscardForEssences, UsePower, Pass, Decline,
    LifeLossReact, VictoryReact, LifeLossChoice, TakeStored, CollectCost,
    Gain, ScryDeckChoice, ScryChoice, DiscardChoice, ResolveDrawReveal,
    ResolveScryReveal, ResolveMonumentDraw, ResolveMonumentReveal
};

struct Action {
    ActionType type;
    uint8_t pid = 0;
    int16_t eid = -1;          // primary entity (eid / source_eid / new_magic_item_eid)
    int power_index = 0;
    int16_t target_eid = -1;   // -1 = None
    int target_pid = -1;       // -1 = None
    Pool pay;
    Pool gain;
    bool use_alt = false;
    CollectDecision decision = CollectDecision::PAY_COST;
    DeckType scry_target = DeckType::ARTIFACT;

    // Variable-length payloads (kept small; bounded by hand/deck sizes).
    int16_t list_a[16]; int list_a_n = 0;   // discard eids / known_eids / scry card list
    int16_t list_b[16]; int list_b_n = 0;   // revealed_eids
    int8_t  scry_order[12]; int scry_order_n = 0;
};

// ---- Engine (engine.cpp) -------------------------------------------------
void execute_action(GameState& state, const Action& a);
int  calculate_victory_points(const GameState& state, int pid);
void get_valid_targets(const GameState& state, int pid, const Power& power,
                       int16_t source_eid, EidVec& out);
int  draw_card(GameState& state, int pid, int count);
bool has_any_blocking_pending_choice(const GameState& state);

// ---- Affordability + move generation (moves.cpp) -------------------------
int  calculate_gold_discount_budget(const GameState& state, int pid,
                                     const EntityData* card_data,
                                     int extra_discount, bool extra_can_discount_gold);
void get_valid_payments(const GameState& state, int pid, const EntityData* card_data,
                        int extra_discount, bool is_artifact,
                        int gold_discount_budget, std::vector<Pool>& out);
void generate_actions(const GameState& state, int pid, std::vector<Action>& out);
bool node_is_chance(const GameState& state);

// ---- Search (search.cpp) -------------------------------------------------
struct SearchResult {
    double value = 0.0;
    Action best;
    bool has_best = false;
    long nodes = 0;
    int depth_completed = 0;
};
SearchResult iterative_deepening(const GameState& state, int pid, int max_depth);

} // namespace ra
