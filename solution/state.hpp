// Mutable game state. Designed as trivially-copyable POD (fixed-size arrays,
// no heap) so cloning during search is a cheap copy.
#pragma once
#include "common.hpp"
#include "cards.hpp"
#include <cstring>
#include <algorithm>

namespace ra {

// ---- Small fixed-capacity vector (no heap) -------------------------------
template <class T, int N>
struct SVec {
    T data[N];
    int n = 0;
    void push(T x) { data[n++] = x; }
    int size() const { return n; }
    bool empty() const { return n == 0; }
    T& operator[](int i) { return data[i]; }
    T operator[](int i) const { return data[i]; }
    T* begin() { return data; }
    T* end() { return data + n; }
    const T* begin() const { return data; }
    const T* end() const { return data + n; }
    bool contains(T x) const {
        for (int i = 0; i < n; i++) if (data[i] == x) return true;
        return false;
    }
    void clear() { n = 0; }
};

using EidVec = SVec<int16_t, 32>;

// ---- Entity (mutable) ----------------------------------------------------
struct Entity {
    ComponentType kind;
    const EntityData* data;
    CardLocation location = CardLocation::OUT_OF_GAME;
    uint8_t owner_id = UNOWNED;
    bool is_turned = false;
    bool has_essences = false;
    Pool essences_on_card;
    int order_index = UNKNOWN_ORDER;
};

// ---- PlayerState ---------------------------------------------------------
struct PlayerState {
    uint8_t pid = 0;
    Pool pool;
    bool has_passed = false;
    bool has_first_player_token = false;
    bool is_active = false;
};

// ---- NaturalCollectOption ------------------------------------------------
struct NaturalCollectOption {
    int8_t essence = -1; // -1 = None
    int16_t amount = 0;
    CollectOptionType option_type = CollectOptionType::FIXED_ESSENCE;
    int16_t alt_any_amount = 0;
    int restriction_mask = 0;
    int alt_restriction_mask = 0;
};

// ---- PendingChoice (flattened tagged POD) --------------------------------
enum class PendingType : uint8_t {
    CollectPhaseCursor, CollectCost, CollectStorage, Gain,
    LifeLossChoice, LifeLossScan, ScryDeckChoice, ScryChoice,
    ScryRevealChoice, DiscardChoice, VictoryReactChoice, DrawRevealChoice,
    MonumentDrawChoice, MonumentRevealChoice, PlacementChoice, GameSetupChoice
};

struct PendingChoice {
    PendingType type;
    uint8_t pid = 0;
    // Primary entity id: meaning depends on type
    //   CollectCost.eid, CollectStorage.eid, Gain.source_eid,
    //   ScryDeckChoice.source_eid, DiscardChoice.source_eid,
    //   VictoryReactChoice.component_eid, PlacementChoice.source_eid
    int16_t eid = -1;
    int power_index = 0;

    // CollectPhaseCursor
    int player = 0, component_index = 0, pass_num = 0;

    // CollectCost
    Pool cost_essences;
    bool cost_turn = false;

    // CollectStorage
    Pool stored;            // stored_essences amounts (essence i -> amount)
    bool has_natural = false;
    NaturalCollectOption natural[8];
    int natural_count = 0;
    int bonus_multiplier = 0;

    // Gain
    int any_amount = 0, restriction_mask = 0, alt_any_amount = 0, alt_restriction_mask = 0;

    // LifeLossChoice / LifeLossScan
    int amount = 0;
    int16_t source = -1;    // entity id of damage source (-1 = none/non-entity)
    int next_offset = 0;
    bool include_self = false, all_players = false;

    // Scry
    int scry_count = 0;
    DeckType deck_type = DeckType::ARTIFACT;
    int16_t eids[12];       // card_eids / known_eids
    int eid_count = 0;
    int reveal_count = 0;

    // DiscardChoice
    int count = 0;

    // PlacementChoice
    SelectCardFilter filter;
    int p_discount = 0;
    bool p_free = false;
    bool can_discount_gold = false;
};

// ---- GameState -----------------------------------------------------------
struct GameState {
    uint8_t num_players = 2;
    uint8_t artifact_start=0, artifact_end=0, mage_start=0, mage_end=0,
            magic_item_start=0, magic_item_end=0, monument_start=0, monument_end=0,
            pop_start=0, pop_end=0;
    GamePhase phase = GamePhase::SETUP_GAME;
    int round_number = 0;
    uint8_t current_player_index = 0;
    uint8_t first_player_index = 0;
    bool pending_turn_advance = false;
    int winner_mask = 0;
    bool is_mid_round_victory_check = false;
    int temp_vp[MAX_PLAYERS] = {0,0};

    Entity entities[MAX_ENTITIES];
    uint8_t entity_count = 0;

    PlayerState players[MAX_PLAYERS];

    PendingChoice pending[MAX_PENDING];
    uint8_t pending_count = 0;

    // ---- Fast clone (copies only the used prefixes) ----
    void clone_into(GameState& dst) const {
        // Copy scalar header via memcpy of the non-array members is awkward;
        // copy fields explicitly then the used array prefixes.
        dst.num_players = num_players;
        dst.artifact_start = artifact_start; dst.artifact_end = artifact_end;
        dst.mage_start = mage_start; dst.mage_end = mage_end;
        dst.magic_item_start = magic_item_start; dst.magic_item_end = magic_item_end;
        dst.monument_start = monument_start; dst.monument_end = monument_end;
        dst.pop_start = pop_start; dst.pop_end = pop_end;
        dst.phase = phase;
        dst.round_number = round_number;
        dst.current_player_index = current_player_index;
        dst.first_player_index = first_player_index;
        dst.pending_turn_advance = pending_turn_advance;
        dst.winner_mask = winner_mask;
        dst.is_mid_round_victory_check = is_mid_round_victory_check;
        dst.temp_vp[0] = temp_vp[0]; dst.temp_vp[1] = temp_vp[1];
        dst.entity_count = entity_count;
        std::memcpy(dst.entities, entities, sizeof(Entity) * entity_count);
        dst.players[0] = players[0];
        dst.players[1] = players[1];
        dst.pending_count = pending_count;
        std::memcpy(dst.pending, pending, sizeof(PendingChoice) * pending_count);
    }

    // ---- pending stack helpers ----
    PendingChoice& push_pending() { return pending[pending_count++]; }
    void push_pending(const PendingChoice& p) { pending[pending_count++] = p; }
    PendingChoice& top_pending() { return pending[pending_count - 1]; }
    const PendingChoice& top_pending() const { return pending[pending_count - 1]; }
    void pop_pending() { pending_count--; }
    // remove pending at index idx (preserving order of the rest)
    void erase_pending(int idx) {
        for (int i = idx; i < pending_count - 1; i++) pending[i] = pending[i + 1];
        pending_count--;
    }
    void insert_pending_front(const PendingChoice& p) {
        for (int i = pending_count; i > 0; i--) pending[i] = pending[i - 1];
        pending[0] = p;
        pending_count++;
    }

    uint8_t acting_player() const {
        if (pending_count > 0) return pending[pending_count - 1].pid;
        return current_player_index;
    }

    bool is_game_over() const { return phase == GamePhase::GAME_OVER; }

    int winner_ids(int out[MAX_PLAYERS]) const {
        int k = 0;
        for (int i = 0; i < num_players; i++) if (winner_mask & (1 << i)) out[k++] = i;
        return k;
    }

    // ---- entity range iteration helpers ----
    // Each returns lists of entity ids matching filters.
    EidVec get_player_hand(uint8_t pid) const {
        EidVec r;
        for (int i = artifact_start; i < artifact_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::HAND && e.owner_id == pid) r.push(i);
        }
        sort_by_order(r);
        return r;
    }
    EidVec get_player_deck(uint8_t pid) const {
        EidVec r;
        for (int i = artifact_start; i < artifact_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::DECK && e.owner_id == pid) r.push(i);
        }
        sort_by_order(r);
        return r;
    }
    EidVec get_known_deck_cards(uint8_t pid) const {
        EidVec r;
        for (int i = artifact_start; i < artifact_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::DECK && e.owner_id == pid && e.order_index != UNKNOWN_ORDER)
                r.push(i);
        }
        sort_by_order(r);
        return r;
    }
    EidVec get_unknown_deck_cards(uint8_t pid) const {
        EidVec r;
        for (int i = artifact_start; i < artifact_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::DECK && e.owner_id == pid && e.order_index == UNKNOWN_ORDER)
                r.push(i);
        }
        return r;
    }
    EidVec get_player_artifacts_in_play(uint8_t pid) const {
        EidVec r;
        for (int i = artifact_start; i < artifact_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::IN_PLAY && e.owner_id == pid) r.push(i);
        }
        return r;
    }
    EidVec get_player_discard(uint8_t pid) const {
        EidVec r;
        for (int i = artifact_start; i < artifact_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::DISCARD && e.owner_id == pid) r.push(i);
        }
        return r;
    }
    int get_player_deck_count(uint8_t pid) const {
        int c = 0;
        for (int i = artifact_start; i < artifact_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::DECK && e.owner_id == pid) c++;
        }
        return c;
    }
    EidVec get_player_monuments(uint8_t pid) const {
        EidVec r;
        for (int i = monument_start; i < monument_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::IN_PLAY && e.owner_id == pid) r.push(i);
        }
        return r;
    }
    EidVec get_player_places_of_power(uint8_t pid) const {
        EidVec r;
        for (int i = pop_start; i < pop_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::IN_PLAY && e.owner_id == pid) r.push(i);
        }
        return r;
    }
    EidVec get_available_magic_items() const {
        EidVec r;
        for (int i = magic_item_start; i < magic_item_end; i++)
            if (entities[i].location == CardLocation::AVAILABLE) r.push(i);
        return r;
    }
    EidVec get_monument_display() const {
        EidVec r;
        for (int i = monument_start; i < monument_end; i++)
            if (entities[i].location == CardLocation::AVAILABLE) r.push(i);
        return r;
    }
    EidVec get_monument_deck() const {
        // sorted by order_index
        EidVec r;
        for (int i = monument_start; i < monument_end; i++)
            if (entities[i].location == CardLocation::MONUMENT_DECK) r.push(i);
        sort_by_order(r);
        return r;
    }
    EidVec get_known_monument_deck() const {
        EidVec r;
        for (int i = monument_start; i < monument_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::MONUMENT_DECK && e.order_index != UNKNOWN_ORDER) r.push(i);
        }
        sort_by_order(r);
        return r;
    }
    EidVec get_unknown_monument_deck() const {
        EidVec r;
        for (int i = monument_start; i < monument_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::MONUMENT_DECK && e.order_index == UNKNOWN_ORDER) r.push(i);
        }
        return r;
    }
    int16_t get_top_monument_from_deck() const {
        EidVec d = get_monument_deck();
        return d.empty() ? -1 : d[0];
    }

    void claim_monument(uint8_t pid, int16_t monument_eid) {
        Entity& mon = entities[monument_eid];
        mon.location = CardLocation::IN_PLAY;
        mon.owner_id = pid;
        mon.order_index = UNKNOWN_ORDER;
    }

    bool all_players_passed() const {
        for (int i = 0; i < num_players; i++)
            if (players[i].is_active && !players[i].has_passed) return false;
        return true;
    }
    void advance_to_next_player() {
        for (int k = 0; k < num_players; k++) {
            current_player_index = (uint8_t)((current_player_index + 1) % num_players);
            const PlayerState& p = players[current_player_index];
            if (p.is_active && !p.has_passed) return;
        }
        // matches Python's "no active non-passed player" assertion path; should
        // not occur in valid play.
    }

    EidVec get_player_creatures(uint8_t pid) const {
        EidVec r;
        EidVec inplay = get_player_artifacts_in_play(pid);
        for (int eid : inplay)
            if (entities[eid].data && entities[eid].data->is_creature()) r.push(eid);
        return r;
    }
    EidVec get_player_dragons(uint8_t pid) const {
        EidVec r;
        EidVec inplay = get_player_artifacts_in_play(pid);
        for (int eid : inplay)
            if (entities[eid].data && entities[eid].data->is_dragon()) r.push(eid);
        return r;
    }

    // artifacts in play + mage + magic item + monuments + pops (in this order)
    EidVec get_all_player_components(uint8_t pid) const {
        EidVec r;
        for (int eid : get_player_artifacts_in_play(pid)) r.push(eid);
        for (int i = mage_start; i < mage_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::IN_PLAY && e.owner_id == pid) r.push(i);
        }
        for (int i = magic_item_start; i < magic_item_end; i++) {
            const Entity& e = entities[i];
            if (e.location == CardLocation::IN_PLAY && e.owner_id == pid) r.push(i);
        }
        for (int eid : get_player_monuments(pid)) r.push(eid);
        for (int eid : get_player_places_of_power(pid)) r.push(eid);
        return r;
    }

    Discount get_total_discount(uint8_t pid) const {
        Discount total;
        EidVec comps = get_all_player_components(pid);
        for (int eid : comps) {
            const Discount& d = entities[eid].data->discount;
            total.artifact += d.artifact;
            total.dragon += d.dragon;
            total.creature += d.creature;
            total.can_discount_gold = total.can_discount_gold || d.can_discount_gold;
        }
        return total;
    }

    EidVec get_straightened_of_type(uint8_t pid, TurnableType tt) const {
        EidVec r;
        for (int eid : get_player_artifacts_in_play(pid)) {
            const Entity& art = entities[eid];
            if (art.is_turned || !art.data) continue;
            if (tt == TurnableType::DRAGON && art.data->is_dragon()) r.push(eid);
            else if (tt == TurnableType::CREATURE && art.data->is_creature()) r.push(eid);
            // MAGE: pass (matches Python)
        }
        return r;
    }

    int get_magic_item_selection_player() const {
        int claimed = 0;
        for (int i = magic_item_start; i < magic_item_end; i++)
            if (entities[i].location == CardLocation::IN_PLAY) claimed++;
        if (claimed >= num_players) return -1;
        return (first_player_index - 1 - claimed + num_players) % num_players;
    }

    // find_component_power: returns power pointer (or null) and fills found_eid.
    // Returns whether component was found (component_type not None).
    struct FCP { bool found; ComponentType kind; int16_t eid; const EntityData* data; const Power* power; };
    FCP find_component_power(uint8_t pid, int16_t entity_id, int power_index) const {
        FCP out{false, ComponentType::ARTIFACT, -1, nullptr, nullptr};
        if (entity_id < 0 || entity_id >= entity_count) return out;
        const Entity& e = entities[entity_id];
        if (e.owner_id != pid && e.location != CardLocation::AVAILABLE) return out;
        if (e.location != CardLocation::IN_PLAY) return out;
        out.found = true; out.kind = e.kind; out.eid = entity_id; out.data = e.data;
        if (power_index >= 0 && power_index < (int)e.data->powers.size())
            out.power = &e.data->powers[power_index];
        return out;
    }

    // phase transitions
    void begin_round() {
        round_number += 1;
        phase = GamePhase::COLLECT;
        current_player_index = first_player_index;
        for (int i = 0; i < num_players; i++) players[i].has_passed = false;
    }
    void begin_action_phase() {
        phase = GamePhase::ACTIONS;
        current_player_index = first_player_index;
        pending_turn_advance = false;
    }
    void begin_victory_check() { phase = GamePhase::VICTORY_CHECK; }
    void set_winner(const int* pids, int count) {
        winner_mask = 0;
        for (int i = 0; i < count; i++) winner_mask |= (1 << pids[i]);
        phase = GamePhase::GAME_OVER;
    }

    // helper: insertion sort an EidVec by entity order_index ascending
    void sort_by_order(EidVec& v) const {
        for (int i = 1; i < v.n; i++) {
            int16_t key = v.data[i];
            int ko = entities[key].order_index;
            int j = i - 1;
            while (j >= 0 && entities[v.data[j]].order_index > ko) {
                v.data[j + 1] = v.data[j];
                j--;
            }
            v.data[j + 1] = key;
        }
    }
};

} // namespace ra
