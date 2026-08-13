# Solution Notes — Res Arcana C++ Bot

## PHASE 0 — Wire Protocol Contract

All messages are single-line JSON over stdin/stdout. Every inbound message has a `"cmd"` field.

### Inbound → Outbound

#### 1. `new_game_from_setup`
```json
{"cmd": "new_game_from_setup", "setup": <ResolveGameSetup JSON>, "player_id": int, "num_players": int}
```
→ `{"status": "ok"}`

`setup` is a serialized `ResolveGameSetup` step with fields:
- `__type__`: `"ResolveGameSetup"`
- `places_of_power`: list of PoP name strings (0–10, typically 4)
- `monument_display`: list of monument name strings (typically 2)
- `monument_deck`: list of monument name strings (typically 5–8), may start with `"?"` (unknown)
- `mage_options`: list of list of mage name strings, one inner list per player (each ~2 names)
- `first_player`: int (default 0)
- `artifact_decks`: list of list of artifact name strings, one inner list per player (each exactly 8)
- `starting_essences`: optional list of pool objects per player

#### 2. `search`
```json
{"cmd": "search", "depth": int, "maximizing_pid": int}
```
`depth` defaults to 3. `maximizing_pid` is the player to optimize for.

→ `{"step": <serialized step JSON>, "nodes": int, "depth": int}`

`step` must be one of the legal declarative action types. `nodes` is total nodes searched. `depth` is the deepest completed iteration.

**CRITICAL**: Bench verifies the returned step is in the `optimal_steps` list from the answer key.

#### 3. `advance`
```json
{"cmd": "advance", "step": <serialized step JSON>}
```
→ `{"status": "ok"}` on success
→ `{"status": "error", "msg": "..."}` on illegal action (bot must roll back state)

The bot must snapshot state before applying, and restore on error. This is tested by `ActionFails` test cases.

#### 4. `get_state`
```json
{"cmd": "get_state"}
```
→ `{"state": <state dump>}`

State dump structure:
```json
{
  "phase": "ACTIONS",
  "round": 2,
  "current_player": 0,
  "first_player": 0,
  "winner_ids": [],
  "players": [
    {"pool": [1,1,1,1,1], "vp": 3, "has_passed": false, "has_first_player_token": true},
    ...
  ],
  "entities": [
    {"name": "...", "kind": "ARTIFACT", "location": "IN_PLAY", "owner": 0, "is_turned": false,
     "essences_on_card": null, "order_index": -1},
    ...
  ]
}
```
`pool` is `[elan, life, calm, death, gold]`.

#### 5. `legal_actions`
```json
{"cmd": "legal_actions"}
```
→ `{"actions": [<serialized step JSON>, ...]}`

Returns all currently available actions as serialized steps. For non-chance states, the harness verifies that the step being applied appears in this list. `DiscardChoice` comparison is order-insensitive.

#### 6. `quit`
```json
{"cmd": "quit"}
```
→ `{"status": "ok"}` then exit.

---

## PHASE 0 — Step Serialization Format

Steps serialize via `serialize_step` / `deserialize_step`. Key observations:
- Each step has `"__type__": "<ClassName>"` field
- `Pool` serializes as `{"elan": 1, "gold": 2}` (omits zero fields)
- Enums serialize as `{"__enum__": "ClassName", "value": int_value}`
- Lists of strings serialize as-is

Common step types the bot returns:
- `UsePower`: `{__type__, card_name, power_index, player_id, target_name?, target_player_id?, pay, gain}`
- `PlaceArtifact`: `{__type__, artifact_name, pay, player_id}`
- `Pass`: `{__type__, item_name, player_id}`
- `Decline`: `{__type__, card_name, player_id}`
- `ClaimMonument`: `{__type__, monument_name, player_id}`
- `ClaimTopMonument`: `{__type__, player_id}`
- `ClaimPlaceOfPower`: `{__type__, pop_name, pay, player_id}`
- `DiscardForEssences`: `{__type__, card_name, gain, player_id}`
- `ChooseMage`: `{__type__, mage_name, player_id}`
- `ChooseMagicItem`: `{__type__, item_name, player_id}`
- `TakeStored`: `{__type__, card_name, player_id, decision}`
- `CollectCost`: `{__type__, card_name, player_id, decision}`
- `Gain`: `{__type__, card_name, gain, player_id, use_alt}`
- `LifeLossChoice`: `{__type__, player_id, pay}`
- `LifeLossReact`: `{__type__, card_name, power_index, player_id, target_name?, pay, gain}`
- `VictoryReact`: `{__type__, card_name, power_index, player_id, target_name?, pay}`
- `ScryDeckChoice`: `{__type__, player_id, scry_target}`
- `ScryChoice`: `{__type__, player_id, scry_order}`
- `DiscardChoice`: `{__type__, card_names, player_id}`
- Chance steps (bot does NOT choose): `ResolveDrawReveal`, `ResolveScryReveal`, `ResolveMonumentDraw`, `ResolveMonumentReveal`

---

## PHASE 1 — Entity Array Bounds (Fixed at Game Start)

Layout of `state.entities[]` after `ActionResolveGameSetup.execute()`:
```
[artifacts...][mages...][magic_items...][monuments...][places_of_power...]
```

For 2-player base game:
| Range | Type | Count | Details |
|-------|------|-------|---------|
| [0, 16) | ARTIFACT | 16 | 8 per player |
| [16, 20) | MAGE | 4 | 2 choices per player |
| [20, 28) | MAGIC_ITEM | 8 | all base magic items |
| [28, 38) | MONUMENT | ≤10 | display + deck |
| [38, 48) | PLACE_OF_POWER | ≤10 | from setup |

**Max total entities: 48. Use array of 64 to be safe.**

Key constants:
- `ESSENCE_COUNT = 5` (elan=0, life=1, calm=2, death=3, gold=4)
- `UNOWNED = PlayerId(5)` 
- `SENTINEL_EID = EntityId(255)`
- `UNKNOWN_ORDER = -1`
- `ARTIFACTS_PER_PLAYER = 8`
- `MAX_PLAYERS = 2`
- Victory threshold = 10 VP

---

## PHASE 1 — Hot Path Functions

| Function | File | Notes |
|----------|------|-------|
| `clone_state` | expectimax.py:79 | Prime bottleneck — deepcopy of pending_stack |
| `apply_action` → `execute_action` | game_engine.py:86 | Dispatches to action handler |
| `get_available_actions` | available_actions.py | Large, many branches |
| `expand_action` | canonical_expand.py | Expands AvailableAction → Action list |
| `_expectimax` | expectimax.py:164 | Recursive search |
| `iterative_deepening` | expectimax.py:263 | Outer loop |
| `evaluate_relative` | expectimax.py:138 | Leaf evaluation |
| `calculate_victory_points` | game_engine.py | Called at leaves |

**Primary target**: `clone_state` — currently uses `copy.deepcopy(pending_stack)` which is slow. C++ equivalent: memcpy the POD GameState + serialize pending_stack to a fixed-size byte buffer.

---

## Invariants to Exploit

- Pool values are always non-negative and small (≤ ~30 essences total). `uint8_t` per essence.
- `EntityId` fits in `uint8_t` (max ~48 entities).
- `PlayerId` fits in `uint8_t` (max 2 players, UNOWNED=5).
- `pending_stack` depth is bounded (empirically ≤ 32 entries).
- Entity array is **fixed size** after setup — no realloc during search.
- `entity.data` is immutable (read-only pointer to card DB) — shared, not cloned.
- `order_index` fits in `int8_t` (values: -1=UNKNOWN, 0–7 for deck order).

---

## Optimizations Log

*(filled as work progresses)*

---

## Ideas Not Pursued (for writeup)

*(filled as work progresses)*
