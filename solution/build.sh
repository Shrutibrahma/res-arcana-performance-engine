#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# No -ffast-math: the evaluation function is float64 and must match Python
# exactly so minimax tie-breaking stays inside the answer key's optimal set.
g++ -O3 -std=c++20 -march=x86-64-v3 -flto -funroll-loops \
    -o bot cards.cpp wire.cpp engine.cpp moves.cpp search.cpp
