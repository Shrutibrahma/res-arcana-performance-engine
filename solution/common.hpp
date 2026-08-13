// Common types, enums, constants, and Pool for the Res Arcana C++ port.
#pragma once
#include <cstdint>
#include <array>
#include <string>

namespace ra {

// Thrown when an action is illegal (mirrors Python ValueError/AssertionError).
struct IllegalAction {};

// ---- Constants -----------------------------------------------------------
constexpr int ESSENCE_COUNT = 5;
constexpr int MAX_PLAYERS = 2;
constexpr int MAX_ENTITIES = 64;   // actual <= 48
constexpr int MAX_PENDING = 48;    // pending_stack depth ceiling
constexpr uint8_t UNOWNED = 5;
constexpr uint8_t SENTINEL_EID = 255;
constexpr int UNKNOWN_ORDER = -1;
constexpr int VICTORY_THRESHOLD = 10;

// ---- Essence -------------------------------------------------------------
enum Essence : int { ELAN = 0, LIFE = 1, CALM = 2, DEATH = 3, GOLD = 4 };

// ---- Enums (values must match reference) ---------------------------------
enum class GamePhase : uint8_t {
    SETUP_GAME = 0, SETUP_CHOOSE_MAGES = 1, SETUP_CHOOSE_ITEMS = 2,
    COLLECT = 3, ACTIONS = 4, VICTORY_CHECK = 5, GAME_OVER = 6
};

enum class CardLocation : uint8_t {
    OUT_OF_GAME = 0, AVAILABLE = 1, MONUMENT_DECK = 2, DECK = 3,
    HAND = 4, IN_PLAY = 5, DISCARD = 6, BEING_CHOSEN = 7
};

enum class ComponentType : uint8_t {
    ARTIFACT = 0, MAGE = 1, MAGIC_ITEM = 2, MONUMENT = 3, PLACE_OF_POWER = 4
};

enum class PowerType : uint8_t { ACTION = 0, IGNORE = 1, VICTORY = 2, BOUGHT = 3 };

enum class ReactTrigger : uint8_t { NONE = 0, DAMAGE = 1, VICTORY_CHECK = 2, DRAGON_ATTACK = 7 };

enum class TurnableType : uint8_t { DRAGON = 1, CREATURE = 2, MAGE = 4 };

enum class DestroyMode : uint8_t { ANY = 0, SELF = 1, ANOTHER = 2 };

enum class DeckType : uint8_t { ARTIFACT = 0, MONUMENT = 1 };

enum class StraightenTarget : uint8_t { SELECTED = 0, SELF = 1 };

enum class CardType : int { NONE = 0, DRAGON = 1, CREATURE = 2 };
// CardTypeMask: DRAGON = 1<<1 = 2, CREATURE = 1<<2 = 4
constexpr int CTM_DRAGON = 2;
constexpr int CTM_CREATURE = 4;
// EntityFlag
constexpr int EF_CANNOT_BE_FREE_PLACED = 1;
constexpr int EF_CANNOT_BE_DISCARDED = 2;

enum class SelectCardLocation : uint8_t {
    NONE = 0, HAND = 1, IN_PLAY = 2, DISCARD = 3, ANY_DISCARD = 4, MONUMENT = 6
};

enum class CollectDecision : uint8_t {
    PAY_COST = 0, PAY_TURN = 1, DECLINE_COST = 2, TAKE_STORED = 3, LEAVE_STORED = 4
};

enum class CollectOptionType : uint8_t { FIXED_ESSENCE = 0, ANY = 1 };

enum class ConditionalType : uint8_t { NONE = 0, STORED_GOLD = 2, PER_STORED_ESSENCE = 3 };

enum class TargetOption : uint8_t {
    TAKE = 0, DECLINE = 1, PAY = 2, TURN = 3, LIFE = 4, ANY = 5, DECK = 6, DISCARD = 7
};

// ---- Pool ----------------------------------------------------------------
struct Pool {
    int16_t v[ESSENCE_COUNT];
    Pool() : v{0,0,0,0,0} {}
    Pool(int e, int l, int c, int d, int g) : v{(int16_t)e,(int16_t)l,(int16_t)c,(int16_t)d,(int16_t)g} {}

    int16_t& operator[](int i) { return v[i]; }
    int16_t operator[](int i) const { return v[i]; }

    int elan()  const { return v[ELAN]; }
    int life()  const { return v[LIFE]; }
    int calm()  const { return v[CALM]; }
    int death() const { return v[DEATH]; }
    int gold()  const { return v[GOLD]; }

    void add(int essence, int amount = 1) { v[essence] += (int16_t)amount; }
    void subtract(int essence, int amount = 1) {
        if (v[essence] < amount) throw IllegalAction{};
        v[essence] -= (int16_t)amount;
    }

    int total() const { return v[0]+v[1]+v[2]+v[3]+v[4]; }

    bool can_afford(const Pool& cost) const {
        for (int i = 0; i < ESSENCE_COUNT; i++) if (v[i] < cost.v[i]) return false;
        return true;
    }
    void pay(const Pool& cost) {
        if (!can_afford(cost)) throw IllegalAction{};
        for (int i = 0; i < ESSENCE_COUNT; i++) v[i] -= cost.v[i];
    }
    void add_pool(const Pool& o) {
        for (int i = 0; i < ESSENCE_COUNT; i++) v[i] += o.v[i];
    }
    bool is_empty() const { return total() == 0; }
    bool operator==(const Pool& o) const {
        for (int i = 0; i < ESSENCE_COUNT; i++) if (v[i] != o.v[i]) return false;
        return true;
    }
    bool operator!=(const Pool& o) const { return !(*this == o); }
};

} // namespace ra
