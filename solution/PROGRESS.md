# Progress — Res Arcana C++ Port

## Current Status

| Item | State |
|------|-------|
| Wire protocol documented | ✅ (NOTES.md) |
| Project scaffold (Makefile, main) | 🚧 |
| Data structures | ⬜ |
| Card DB loader (cards.json) | ⬜ |
| Engine: execute_action + phases | ⬜ |
| available_actions / expand_action | ⬜ |
| step serialization / conversion | ⬜ |
| Compiles | ⬜ |
| Correctness tests | ⬜ 0/485 |
| Bench speed | ⬜ |

## Build

```
g++ -O3 -march=x86-64-v3 -funroll-loops -ffp-contract=off -std=c++17
```
NO -ffast-math (eval float64 must match Python).

## Test Log

| Date | Passed | Notes |
|------|--------|-------|
| — | — | not built yet |

## Speed Log

| Date | ms/search | nodes/s | Notes |
|------|-----------|---------|-------|
| — | — | — | not benched yet |

## Optimization Table

| # | Change | Tests | Before | After | Kept? |
|---|--------|-------|--------|-------|-------|

## Fixed-Array Bounds (safe ceilings + assert)

- `entities[64]` — actual ≤48 (16 art + 4 mage + 8 item + ≤10 mon + ≤10 pop)
- `pending[32]` — pending_stack depth
- `pool[5]` — ESSENCE_COUNT, uint8 each
- All sized to ceiling with `assert()` guard on push.

## Invariants (discovered during port)

- Pool values small & non-negative → uint8_t.
- EntityId, PlayerId fit in uint8_t (UNOWNED=5, SENTINEL=255).
- entity.data is immutable pointer into card DB — never cloned.
- order_index ∈ {-1, 0..7} → int8_t.
- Max 2 powers/card, max 2 effects/power.
- Only 1 VICTORY_CHECK react card (Golden Statue); 0 LIFE_LOSS react cards in DB.

## Ideas Not Pursued (for writeup)

- (filled as work progresses)
