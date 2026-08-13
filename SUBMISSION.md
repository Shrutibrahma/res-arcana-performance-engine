# Res Arcana Performance Exercise - Submission

Language: **C++ (C++20)**. The reference Python engine was ported in full and is
verified against the provided harness: **485 / 485 correctness tests pass.**

## Compilation Instructions For The Grader

All sources live in `solution/`. A vendored copy of `nlohmann/json` is included
in-tree at `solution/vendor/nlohmann/json.hpp` (no network needed). The card
database is read at runtime from `data/cards.json` (the binary searches
`data/cards.json`, `../data/cards.json`, `../../data/cards.json`, `./cards.json`).

Build on the Linux scoring sandbox (gcc 14, x86-64-v3):

```bash
g++ -O3 -std=c++20 -march=x86-64-v3 -flto -funroll-loops \
    -o solution/bot solution/cards.cpp solution/wire.cpp solution/engine.cpp \
    solution/moves.cpp solution/search.cpp
```

(Equivalently `g++ -O3 -std=c++20 -march=x86-64-v3 -flto -funroll-loops -o solution/bot solution/*.cpp`.)

Run / test:

```bash
python -m harness correctness --bot "./solution/bot"
python -m harness bench --bot "./solution/bot"
```

> Note: `-ffast-math` is deliberately **not** used. The evaluation function must
> stay bit-compatible with Python `float64` so that minimax tie-breaking returns
> a move inside the answer key's `optimal_steps` set; fast-math reordering could
> silently break the bench.

During development on Windows the identical sources were built with MSVC
(`cl /nologo /O2 /Ob3 /Oi /Ot /arch:AVX2 /GL /DNDEBUG /EHsc /std:c++20`); the
code is portable and uses no compiler-specific extensions in the hot path.

## Summary of Optimizations

The port mirrors the reference engine's observable behaviour exactly, then
removes the per-node costs that dominate Python's runtime.

**1. Flat, trivially-copyable state (no heap in the hot path).** `GameState` is a
fixed-size POD: `Entity entities[64]`, `PlayerState players[2]`, and a
`PendingChoice pending[48]` stack, plus scalar header fields. There are no
`std::vector`, `std::map`, or `std::string` members anywhere a search node can
touch. The pending stack — which in Python is a `list` deep-copied at every node
(the reference's single biggest cost) — is a fixed array. Variable-length action
payloads (scry orders, discard sets, reveal sets) are small fixed arrays inside
the `Action` struct.

**2. Immutable card data shared by pointer.** All rules content (powers, costs,
effects, collect abilities) is loaded once into a `CardDatabase` and referenced
through `const EntityData*`. Cloning a state copies pointers, never card data.
Cards are referenced by integer entity id, never by name, in the engine; string
names are used only at the wire boundary.

**3. Cheap clone via used-prefix copy over uninitialized storage.** Search clones
with `clone_into`, which copies only the live prefixes (`entity_count` entities,
`pending_count` pending entries) and the scalar header, rather than the whole
64+48-slot struct. The destination is raw `alignas(GameState)` storage, so we
also skip default-constructing the unused tail. Because the type is trivially
copyable this is a plain prefix `memcpy`. Measured: **12.8 ms → 10.2 ms per
search.**

**4. Per-depth reusable action buffers.** Move generation writes into a buffer
selected by recursion depth (`g_bufs[depth]`). The active search path holds a
distinct `depth` at each level, so the buffers never alias along a path, and the
allocation is reused across the ~1M nodes of a search instead of being
`new`/`delete`d per node. Measured: **10.2 ms → 9.9 ms.**

**5. Fused move generation.** `get_available_actions` + `expand_action` are
implemented as a single pass that emits concrete `Action`s directly, avoiding an
intermediate `AvailableAction` representation and its allocations.

**6. Alpha-beta with iterative deepening**, matching the reference search exactly
(same depth, same `float64` heuristic, chance nodes averaged). Pruning is
value-preserving, so any move returned still lies in the optimal set.

**7. Compiler flags.** `-O3 -march=x86-64-v3 -flto -funroll-loops`. LTO lets the
small hot helpers (`Pool` ops, entity-range scans, `clone_into`) inline across
translation units; `x86-64-v3` gives wide vector `memcpy` for the clone.

Net effect so far: from a ~12.8 ms/search baseline down to ~9.9 ms/search at the
point of writing, with the remaining headroom identified below. Correctness is
unchanged (485/485) at every step.

## Invariants

These bounds are taken from the rules / exercise spec and are relied on for the
fixed-size representation:

- **Essence values ≤ 255.** Stated in the README ("you may assume at most 255").
  Pools are stored as small integers (`int16_t` per essence, 5 per pool); 255 fits
  comfortably and leaves headroom for intermediate sums without overflow.
- **Entities ≤ 48; we allocate 64.** From the documented 2-player base layout:
  16 artifacts (8/player) + 4 mages (2 choices/player) + 8 magic items +
  ≤10 monuments (display+deck) + ≤10 places of power = ≤ 48. `MAX_ENTITIES = 64`
  is a safe ceiling, so `entity id` fits in a `uint8_t`/`int16_t`.
- **Pending-stack depth is small; we allocate 48.** Choices are pushed by collect
  cursors, gains, reveals, life-loss scans and placement/scry chains, which nest
  only a few deep in practice. `MAX_PENDING = 48` is never approached.
- **Players ≤ 2.** The exercise restricts to ≤ 2 players; `UNOWNED = 5` and the
  sentinel id `255` both fit a `uint8_t`.
- **Rounds ≤ 255.** Stated in the README; `round_number` needs no wide type.
- **`order_index ∈ {-1, 0..7}`** (deck/monument ordering), comfortably an `int8`-
  range value.
- **Card data is immutable** after load, so it is shared by pointer across all
  cloned states and never copied.

## Future Work

1. **Make/undo instead of clone.** The search still copies the live state prefix
   per node. Applying actions in place and undoing them on return (recording only
   the touched fields) would remove the per-node `memcpy` entirely — likely the
   single largest remaining win, but it requires careful undo logic for the
   pending stack and is the riskiest change for correctness.
2. **Eliminate inner allocations in move generation.** Payment and gain
   enumeration (`enumerate_essence_payments`, `get_valid_payments`,
   `get_gain_choices`) still build `std::vector<Pool>` per call. Replacing these
   with fixed-capacity stack buffers (a bounded `Pool` array; the legal payment
   count is small and provably ≤ a few hundred) removes the last hot-path heap
   churn.
3. **Cache per-player entity index lists.** Helpers like `get_player_hand`,
   `get_player_artifacts_in_play`, and `get_all_player_components` re-scan the
   entity array several times per node and return `EidVec` by value. Maintaining
   cached hand/in-play/discard index lists on `PlayerState`, updated only when a
   card changes location, would turn these scans into O(1) lookups. (A
   transposition table keyed on a state hash is a further option, though repeated
   states are less common here than in chess-like games.)

## Agent Transcript Files

Claude Code transcripts for this session are stored locally under
`~/.claude/projects/<project-hash>/<session-id>.jsonl` (on this machine,
`C:\Users\<user>\.claude\projects\...`). They are included with the submission
zip. The work was done primarily with the Opus model for the initial full port
and the trickier debugging, with mechanical edits handled inline.

## Before You Submit

Technical notes for the grader:

- The development machine is Windows; the grader builds on Linux with gcc 14. The
  sources are standard C++20 with a vendored header-only JSON library, so the
  provided `g++` command builds cleanly in the sandbox. No code is MSVC-specific.
- A subtle Python semantic worth flagging (it drove several correctness fixes):
  the reference `Pool` subclasses `list`, so truthiness checks like `if ctx.gain:`
  are **always true** (they test list length 5, not zero-ness). The C++ port
  reproduces this exactly — using `total()`/`is_empty()` only where Python calls
  those methods, and treating bare `if pool:` as unconditional.

Feedback:

The scaffolding (`common.hpp` / `cards.hpp` / `state.hpp` / `cards.cpp`) plus the
clear wire-protocol notes made the port tractable and let the work focus on the
engine semantics and performance rather than boilerplate. A short list of the
trickiest behavioural gotchas (the `Pool`-is-a-`list` truthiness, the
`artifact_decks`-optional setup field, the `ResolveGameSetup` entity ordering)
would have saved some debugging time, but finding them via the test suite was
reasonable.
