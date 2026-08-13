# Res Arcana Performance Engine

## Overview

C++20 implementation of the Res Arcana performance exercise with a Python reference engine, harness, data files, optimized solution code, and submission writeup. The project ports and optimizes game-engine logic and search/evaluation behavior.

## Tech Stack

C++20, Python, JSON, shell build script

## Repository Contents

This repository contains the source code and related files for the project. Existing project documentation, submissions, scripts, source folders, data/config files, and supporting assets are preserved below.

## Notes

- Canonical public repository: https://github.com/Shrutibrahma/res-arcana-performance-engine
- Original local path: `C:\Users\shrut\Downloads\Shruti_Exam\ABC`
- README rewritten during portfolio cleanup for clearer presentation.

---

## Original README

# ABC

## Overview

Education analytics / prediction project.

## Tech Stack

C/C++, Python

## Project Contents

This repository contains the source code and related files for this project as recovered from the local project archive. It may include coursework, prototypes, demos, notebooks, dashboards, firmware/app code, assets, and supporting documentation depending on the original folder.

## Repository Notes

- Original local path: `C:\Users\shrut\Downloads\Shruti_Exam\ABC`
- Portfolio category: Takehome / Coding Challenge
- Published repo name: `abc`
- Generated README created during portfolio repository archival.

## How To Use

Inspect the project files for framework-specific setup. Common entry points include README instructions, package manifests, notebooks, Python scripts, app folders, dashboard folders, or firmware/toolchain project files.

---

## Original README

# ABC

## Overview

Education analytics / prediction project.

## Tech Stack

C/C++, Python

## Project Contents

This repository contains the source code and related files for this project as recovered from the local project archive. It may include coursework, prototypes, demos, notebooks, dashboards, firmware/app code, assets, and supporting documentation depending on the original folder.

## Repository Notes

- Original local path: `C:\Users\shrut\Downloads\Shruti_Exam\ABC`
- Portfolio category: Takehome / Coding Challenge
- Published repo name: `abc`
- Generated README created during portfolio repository archival.

## How To Use

Inspect the project files for framework-specific setup. Common entry points include README instructions, package manifests, notebooks, Python scripts, app folders, dashboard folders, or firmware/toolchain project files.

---

## Original README

# Res Arcana Performance Exercise

As part of long-horizon RL training to improve reasoning and strategic
thinking, we're teaching Claude to play board games. To do this at scale, we
want a highly optimized board game implementation.

You've been provided a correct Python implementation of the board game Res
Arcana that enforces the proper game rules, enumerates legal moves, and
searches positions to find good moves.

Your objective is to port and optimize this implementation so that it
maintains correctness while being as fast as possible.

Use your own taste, conceptual understanding of performance principles, and
good judgment to make the port fast. In testing, just launching agents to
hill climb on their own did *not* produce good results - you'll end up with
no idea what is going on and no ability to notice Claude's errors and
confusions.

Minimize dead time while waiting for Claude; make sure you are actively:

- Looking at profiling metrics
- Reading key snippets of code
- Prioritizing and/or parallelizing multiple avenues of work
- Forming hypotheses and validating or rejecting them

There is no limit on token budget and you will not be scored on how few
tokens you've used, but be aware that if you use Opus excessively, you will likely run out of usage on a $20 plan. 

It's possible to do well on $20 by managing context, steering more instead
of letting Opus wander around figuring out what to do, and by using Sonnet
and/or Haiku for all the mechanical work. If you do run out, note this in
your submission file and finish by hand - there are a number of sizable
optimizations to find that don't require much typing.

You don't need to be familiar with the game rules - your code just needs to
match the reference implementation in observable behavior.

You may choose Rust, C++, Java, or Go for your port - we recommend choosing
whatever you're most comfortable with and sticking to it.

## Deliverables

Your deliverable is a `zip` file containing:

- A `solution` folder with the source code for your optimized port
- Agent transcripts in raw form (for Claude Code, normally stored at
  `~/.claude/projects/<project-hash>/<session-id>.jsonl`)
- The completed `SUBMISSION.md` template

## Scoring Overview

### Correctness (25%)

- The provided test harness passes against your port
- The provided benchmark produces valid output on our private test set
  without error. The test set is the same size and drawn from the same
  distribution.

### Writeup (25%)

All sections of `SUBMISSION.md` completed:

- Compilation instructions work
- Optimizations described clearly and faithfully to the code
- Invariants are true
- Three reasonable future work ideas

### Speedup (50%)

For your chosen language, you'll be scored proportional to
`log(your_speedup) / log(gold_speedup)`, where the gold solution was written
by our engineers.

It's definitely possible to beat these values, probably substantially - feel
free to submit early if you reach or exceed these values.

| Language | Validation set time | ms / search | Ã— speedup vs Python  |
|---|---:|---:|---:|
| Python | 271 s | 903 ms | 1Ã— |
| Java | 0.35 s | 1.17 ms | 772Ã— |
| Go | 0.30 s | 1.00 ms | 903Ã— |
| C++ | 0.27 s | 0.90 ms | 1003Ã— |
| Rust | 0.15 s | 0.50 ms | 1807Ã— |

## Rule Simplifications

The reference simplifies the official rules, and your implementation should
follow these accordingly:

- Perfect information: search can see hidden information like the contents
  of decks and the opponent's hand
- No simultaneous actions: whenever players would choose simultaneously,
  they choose in player order instead
- A maximum of two players are supported

## Setup

The reference code requires Python 3.10+ and no other dependencies. You can
develop on any operating system, but your port must run in a Linux
environment (more details below). To test the Python implementation is
working:

`python -m harness correctness`

## Testing Your Code for Correctness

If your script or binary is `./solution/my_bot`:

`python -m harness correctness --bot "./solution/my_bot"`

It doesn't matter how fast the tests run; we're only concerned about the
time on the benchmark.

## Benchmarking Your Code

```
python -m harness bench --bot "./solution/my_bot"        # full validation set
python -m harness bench --bot "./solution/my_bot" -n 2   # first 2 games only â€” faster iteration
```

The benchmark iterates through a game transcript, runs your search
algorithm, and verifies your move is in the set of moves with the best
minimax value (given the fixed depth and heuristic function). Multiple moves
may tie for best; in this case your algorithm can return any of them, not
necessarily the same one as the Python implementation.

You may not change the depth or the semantics of the heuristic function,
but you can otherwise optimize the search freely including using other
algorithms to compute minimax value.

## Repository layout

```
res_arcana_perf/
â”œâ”€â”€ reference/        # Read only Python reference implementation
â”‚   â”œâ”€â”€ engine/         game rules, state, action handlers
â”‚   â””â”€â”€ expectimax.py   wire-protocol bot + reference search algorithm
â”œâ”€â”€ harness.py        # Read only test & timing infrastructure
â”œâ”€â”€ data/             # Read only data files
â”‚   â”œâ”€â”€ cards.json              card content
â”‚   â”œâ”€â”€ unit_tests/             485 JSON tests
â”‚   â”œâ”€â”€ bench_answer_key.json   10-game answer key for self-checking bench
â”‚   â””â”€â”€ rules.md                game rules reference
â”œâ”€â”€ solution/         # YOUR WORK â€” write your port here
â”œâ”€â”€ SUBMISSION.md     # Writeup template â€” fill in and include with your zip
â””â”€â”€ README.md
```

---

## Additional details on the scoring environment

For our security, your code will be compiled and timed within a Linux
x86-64 sandbox **with no Internet access**. You don't need to use any
external dependencies, but if you do (e.g., JSON parsing) then you must
include them in your submission - you **cannot** rely on GitHub, crates.io,
etc. in your build command.

- C/C++: include third-party headers/sources in-tree.
- Rust: `cargo vendor` (commit the `vendor/` directory and the
  `.cargo/config.toml` snippet it prints).
- Go: `go mod vendor` (commit the `vendor/` directory).
- Java: ship JARs in `solution/lib/` and have your build resolve them
  locally, or produce an uber-JAR.

The sandbox has Python 3.10+, gcc 14, rustc 1.95, Go 1.26, and Temurin JDK
25 LTS.

The scoring machine builds your `solution` folder against an **unmodified**
copy of `reference/`, `harness.py`, and `data/` so you should **not** make
any changes to these.

Your executable is scheduled on 1 CPU core. If you use threads, they will
contend rather than parallelize.

### Hard Cap Resource Limits

- Your submission zip must be at most 128 MB
- Memory is limited with cgroups to `memory.max=256 MiB`
- You cannot use a GPU
- Your submission must compile in at most 300 seconds on 1 CPU

### Other notes

- If you set `-march=` in your build, the scoring machine supports
  `x86-64-v3`.
- You may use multi-stage builds like PGO and BOLT, respecting the maximum
  compile time.

## Datatypes and Maximum Values

In the real board game, resource values (essences) are considered unlimited
and Python uses arbitrary precision integers to represent this. For ease of
optimization you may assume that they are at most `255`, so it's safe to
represent these with 8 bits. Test data is guaranteed to have at most `255`
rounds. Otherwise, maximum values are determined by the game rules.

You may prove an invariant (e.g. "the maximum points achievable is X") and
rely on it for optimization; if you do, include your reasoning in your
submission.

For the output of the evaluation function, you must use `float64` to match
Python and avoid rounding errors.



