// Expectimax search with alpha-beta + iterative deepening. Mirrors
// reference/expectimax.py.
#include "engine.hpp"
#include <limits>
#include <vector>

namespace ra {

// Clone over uninitialized storage: clone_into writes every scalar plus the
// used entity/pending prefixes, so the unread tail slots can stay garbage.
// GameState is trivially copyable, so this skips both the full-struct copy and
// the default construction of all 64 entities / 48 pending slots.
#define CLONE_CHILD(child, src) \
    alignas(GameState) unsigned char child##_buf[sizeof(GameState)]; \
    GameState& child = *reinterpret_cast<GameState*>(child##_buf); \
    (src).clone_into(child)

static const double WIN_VALUE = 10000.0;
static const double LOSS_VALUE = -10000.0;
static const double HAND_WEIGHT = 0.25;
static const double GOLD_WEIGHT = 0.24;
static const double OTHER_ESSENCE_WEIGHT = 0.12;

static double evaluate(const GameState& st, int pid) {
    double vp = (double)calculate_victory_points(st, pid);
    const Pool& pool = st.players[pid].pool;
    double gold = (double)pool.gold();
    double other = (double)(pool.elan() + pool.life() + pool.calm() + pool.death());
    int cards_in_hand = 0;
    // Only artifacts can be in HAND; scan the artifact range only (~16 entities vs ~48)
    for (int i = st.artifact_start; i < st.artifact_end; i++)
        if (st.entities[i].owner_id == pid && st.entities[i].location == CardLocation::HAND) cards_in_hand++;
    return vp + GOLD_WEIGHT * gold + OTHER_ESSENCE_WEIGHT * other + HAND_WEIGHT * cards_in_hand;
}

static double evaluate_relative(const GameState& st, int pid) {
    if (st.phase == GamePhase::GAME_OVER) {
        if (st.winner_mask & (1 << pid)) return WIN_VALUE;
        return LOSS_VALUE;
    }
    double my = evaluate(st, pid);
    if (st.num_players == 1) return my;
    double best_opp = -1e300;
    for (int i = 0; i < st.num_players; i++) if (i != pid) best_opp = std::max(best_opp, evaluate(st, i));
    return my - best_opp;
}

struct Stats { long nodes = 0; };

// Move-ordering priority table indexed by ActionType (lower = try first).
// Ordering actions so that strong moves (UsePower, PlaceArtifact) are explored
// before weak moves (DiscardForEssences, Pass) gives alpha-beta much tighter
// bounds earlier, pruning far more of the tree.
//
// ActionType enum order (from engine.hpp):
//   0 ChooseMage  1 ChooseMagicItem  2 PlaceArtifact  3 ClaimMonument
//   4 ClaimTopMonument  5 ClaimPlaceOfPower  6 DiscardForEssences  7 UsePower
//   8 Pass  9 Decline  10 LifeLossReact  11 VictoryReact  12 LifeLossChoice
//   13 TakeStored  14 CollectCost  15 Gain  16 ScryDeckChoice  17 ScryChoice
//   18 DiscardChoice  19 ResolveDrawReveal  20 ResolveScryReveal
//   21 ResolveMonumentDraw  22 ResolveMonumentReveal
static constexpr int8_t ACTION_PRIO[] = {
    5, // ChooseMage
    5, // ChooseMagicItem
    1, // PlaceArtifact
    2, // ClaimMonument
    2, // ClaimTopMonument
    2, // ClaimPlaceOfPower
    6, // DiscardForEssences
    0, // UsePower          <- always try first
    9, // Pass              <- try last (very bad for MAX player)
    8, // Decline
    4, // LifeLossReact
    3, // VictoryReact
    4, // LifeLossChoice
    3, // TakeStored
    3, // CollectCost
    3, // Gain
    7, // ScryDeckChoice
    7, // ScryChoice
    7, // DiscardChoice
    7, // ResolveDrawReveal
    7, // ResolveScryReveal
    7, // ResolveMonumentDraw
    7, // ResolveMonumentReveal
};

// One reusable action buffer per recursion depth. The active search path holds a
// distinct `depth` at each level, so bufs[depth] is never aliased along a path.
// Single-threaded (the bot runs on 1 core), so plain statics are fine.
static std::vector<Action> g_bufs[64];

static double expectimax(const GameState& st, int depth, int maxpid,
                         double alpha, double beta, Stats& stats);

static double expectimax_chance(const GameState& st, int depth, int maxpid,
                                std::vector<Action>& avail, double alpha, double beta, Stats& stats) {
    double prob = 1.0 / (double)avail.size();
    double expected = 0.0;
    for (const Action& a : avail) {
        CLONE_CHILD(child, st);
        execute_action(child, a);
        double v = expectimax(child, depth - 1, maxpid, alpha, beta, stats);
        expected += prob * v;
    }
    return expected;
}

static double expectimax(const GameState& st, int depth, int maxpid,
                         double alpha, double beta, Stats& stats) {
    stats.nodes++;
    if (depth == 0 || st.phase == GamePhase::GAME_OVER)
        return evaluate_relative(st, maxpid);

    int cur = st.acting_player();
    std::vector<Action>& avail = g_bufs[depth & 63];
    avail.clear();
    generate_actions(st, cur, avail);
    if (avail.empty()) return evaluate_relative(st, maxpid);

    if (node_is_chance(st) && avail.size() > 1)
        return expectimax_chance(st, depth, maxpid, avail, alpha, beta, stats);

    // Sort moves by priority so strong actions are evaluated first.
    // This gives alpha-beta much better bounds up front, pruning more branches.
    // Alpha-beta is value-exact regardless of ordering, so results are unchanged.
    if (avail.size() > 1) {
        std::sort(avail.begin(), avail.end(), [](const Action& a, const Action& b) {
            return ACTION_PRIO[(int)a.type] < ACTION_PRIO[(int)b.type];
        });
    }

    bool is_max = (cur == maxpid);
    double best = is_max ? -1e300 : 1e300;
    for (const Action& a : avail) {
        CLONE_CHILD(child, st);
        execute_action(child, a);
        double v = expectimax(child, depth - 1, maxpid, alpha, beta, stats);
        if (is_max) { if (v > best) best = v; if (best > alpha) alpha = best; }
        else { if (v < best) best = v; if (best < beta) beta = best; }
        if (beta <= alpha) break;
    }
    return best;
}

SearchResult iterative_deepening(const GameState& st, int pid, int max_depth) {
    SearchResult result;
    std::vector<Action> root_actions;
    generate_actions(st, pid, root_actions);
    if (root_actions.empty()) return result;

    for (int depth = 1; depth <= max_depth; depth++) {
        Stats stats;
        double depth_best = -1e300;
        Action depth_best_action;
        bool have = false;
        for (const Action& a : root_actions) {
            CLONE_CHILD(child, st);
            execute_action(child, a);
            double v = expectimax(child, depth - 1, pid, -1e300, 1e300, stats);
            if (v > depth_best) { depth_best = v; depth_best_action = a; have = true; }
        }
        result.nodes += stats.nodes;
        result.depth_completed = depth;
        result.value = depth_best;
        if (have) { result.best = depth_best_action; result.has_best = true; }
        if (result.value >= WIN_VALUE - 1000.0) break;
    }
    return result;
}

} // namespace ra
