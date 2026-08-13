"""Single-file scoring harness — correctness + expectimax bench.

Both subcommands drive a candidate bot over the JSON-lines wire protocol
(documented in `reference/expectimax.py`), so this works against any
implementation, not just the reference Python.

Usage:
  python -m harness correctness                              # against reference expectimax bot
  python -m harness correctness --bot "./solution/my_bot"    # against your port
  python -m harness correctness --tests data/unit_tests/

  python -m harness bench                                    # uses data/bench_answer_key.json
  python -m harness bench -n 1                               # first game only — fast iteration
  python -m harness bench --bot "./solution/my_bot" --key path/to/key.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reference.engine.game_phase import GamePhase
from reference.engine.state_dump import StateView
from reference.engine.step_serialization import deserialize_step, serialize_step
from reference.engine.steps import (
    ActionFails,
    AssertCurrentPlayer,
    AssertEssencesOnCard,
    AssertLocation,
    AssertOwner,
    AssertPhase,
    AssertPool,
    AssertTurned,
    AssertVP,
    AssertWinners,
    ResolveGameSetup,
    Step,
)


# ---------------------------------------------------------------------------
# Wire protocol session
# ---------------------------------------------------------------------------

@dataclass
class Bot:
    proc: subprocess.Popen[str]
    # Wall-clock spent blocked on the bot's reply for the most recent send().
    # Excludes the harness's own json.dumps / json.loads — only the readline()
    # is timed. Bench uses this to attribute time to the bot, not the harness.
    last_reply_time: float = 0.0

    def send(self, msg: dict[str, Any]) -> dict[str, Any]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        t0 = time.perf_counter()
        reply = self.proc.stdout.readline()
        self.last_reply_time = time.perf_counter() - t0
        if not reply:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"Bot closed stdout. stderr: {stderr}")
        return json.loads(reply)

    def close(self) -> None:
        try:
            self.send({"cmd": "quit"})
        except Exception:
            pass
        if self.proc.stdin is not None:
            try:
                self.proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass  # proc already exited, pipe gone
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def spawn_bot(cmd: list[str], capture_stderr: bool = True) -> Bot:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if capture_stderr else subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    return Bot(proc=proc)


# ---------------------------------------------------------------------------
# Correctness: JSON unit-test runner
# ---------------------------------------------------------------------------

ASSERTION_TYPES = (
    AssertPool, AssertEssencesOnCard, AssertTurned, AssertLocation,
    AssertOwner, AssertCurrentPlayer, AssertPhase, AssertVP, AssertWinners,
)

# Chance-step types — these resolve information the bot doesn't choose
# (deck reveals, monument draws, scry reveals), so the bot's legal_actions
# enumeration of them isn't a meaningful test of its action-enumeration code.
_CHANCE_STEP_TYPES = frozenset({
    "ResolveDrawReveal",
    "ResolveScryReveal",
    "ResolveMonumentDraw",
    "ResolveMonumentReveal",
})


def run_assertion(step: Step, view: StateView) -> None:
    """Run a single assertion step against the deserialized state. Raise AssertionError on failure."""
    match step:
        case AssertPool():
            expected = [step.elan, step.life, step.calm, step.death, step.gold]
            got = view.player_pool(step.player_id)
            assert got == expected, f"AssertPool P{step.player_id}: got {got} expected {expected}"
        case AssertVP():
            got = view.player_vp(step.player_id)
            assert got == step.vp, f"AssertVP P{step.player_id}: got {got} expected {step.vp}"
        case AssertPhase():
            got = view.phase.name
            expected = step.phase.name if hasattr(step.phase, "name") else GamePhase(step.phase).name
            assert got == expected, f"AssertPhase: got {got} expected {expected}"
        case AssertCurrentPlayer():
            got = view.current_player
            assert got == step.player_id, f"AssertCurrentPlayer: got {got} expected {step.player_id}"
        case AssertWinners():
            got = sorted(view.winner_ids)
            expected = sorted(step.winner_ids)
            assert got == expected, f"AssertWinners: got {got} expected {expected}"
        case AssertTurned():
            e = view.find_entity(step.card_name)
            assert e["is_turned"] == step.turned, (
                f"AssertTurned {step.card_name}: got is_turned={e['is_turned']} expected {step.turned}"
            )
        case AssertLocation():
            e = view.find_entity(step.card_name)
            expected = step.location.name if hasattr(step.location, "name") else str(step.location)
            assert e["location"] == expected, (
                f"AssertLocation {step.card_name}: got {e['location']} expected {expected}"
            )
        case AssertOwner():
            e = view.find_entity(step.card_name)
            assert e["owner"] == step.player_id, (
                f"AssertOwner {step.card_name}: got owner={e['owner']} expected {step.player_id}"
            )
        case AssertEssencesOnCard():
            e = view.find_entity(step.card_name)
            got = e["essences_on_card"]
            expected = [step.elan, step.life, step.calm, step.death, step.gold]
            actual = got if got is not None else [0, 0, 0, 0, 0]
            assert actual == expected, (
                f"AssertEssencesOnCard {step.card_name}: got {actual} expected {expected}"
            )
        case _:
            raise AssertionError(f"Unknown assertion step: {type(step).__name__}")


def _canonicalize_for_compare(step_json: dict[str, object]) -> dict[str, object]:
    """Normalize set-like fields so order doesn't matter when comparing."""
    if step_json.get("__type__") == "DiscardChoice":
        out = dict(step_json)
        names = out.get("card_names")
        if isinstance(names, list):
            out["card_names"] = sorted(names)
        return out
    return step_json


def _run_step(bot: Bot, step: Step) -> None:
    if isinstance(step, ActionFails):
        # Expect bot to reject the wrapped step.
        reply = bot.send({"cmd": "advance", "step": serialize_step(step.action)})
        assert reply.get("status") == "error", f"ActionFails: expected error, got {reply}"
        return

    if isinstance(step, ASSERTION_TYPES):
        reply = bot.send({"cmd": "get_state"})
        assert "state" in reply, f"get_state returned {reply}"
        run_assertion(step, StateView(reply["state"]))
        return

    # Player-decision step: enumerate first to force the bot's `legal_actions`
    # path, then verify the about-to-apply step is in the returned set. This
    # catches enumeration bugs (buffer overflows, missed cases) that pure-apply
    # tests miss. Chance steps are skipped — the bot doesn't enumerate those.
    step_json = serialize_step(step)
    if step_json.get("__type__") not in _CHANCE_STEP_TYPES:
        reply = bot.send({"cmd": "legal_actions"})
        assert "actions" in reply, f"legal_actions returned {reply}"
        actions = reply["actions"]
        test_canonical = _canonicalize_for_compare(step_json)
        actions_canonical = [_canonicalize_for_compare(a) for a in actions]
        assert test_canonical in actions_canonical, (
            f"step not in legal_actions ({len(actions)} actions returned): "
            f"step={step_json!r}"
        )

    reply = bot.send({"cmd": "advance", "step": step_json})
    assert reply.get("status") == "ok", f"advance failed: {reply}"


def run_test(test_path: Path, bot: Bot) -> tuple[bool, str]:
    """Run one JSON test against a long-lived bot. Returns (passed, message)."""
    data = json.loads(test_path.read_text())
    num_players = data.get("num_players", 1)
    expansions = tuple(sorted(data.get("expansions", [0])))
    if expansions != (0,):
        return True, "skipped (non-base expansions)"
    if num_players not in (1, 2):
        return True, f"skipped (num_players={num_players})"

    setup_step = deserialize_step(data["setup"])
    assert isinstance(setup_step, ResolveGameSetup)
    steps = [deserialize_step(s) for s in data["steps"]]

    try:
        reply = bot.send({
            "cmd": "new_game_from_setup",
            "setup": serialize_step(setup_step),
            "player_id": 0,
            "num_players": num_players,
        })
    except Exception as e:
        return False, f"setup: bot died: {e}"
    if reply.get("status") != "ok":
        return False, f"setup failed: {reply}"

    for i, step in enumerate(steps):
        try:
            _run_step(bot, step)
        except AssertionError as e:
            return False, f"step {i} ({type(step).__name__}): {e}"
        except Exception as e:
            return False, f"step {i} ({type(step).__name__}): unexpected error: {e}"
    return True, "ok"


def cmd_correctness(args: argparse.Namespace) -> int:
    test_files = sorted(args.tests.glob("*.json"))

    # Honor `--skip-list <file>`: filenames (basenames) listed there are
    # excluded from the run. One filename per line; '#' starts a comment.
    # Used to drop holdout replays the perf engine can't replay without
    # touching the source-of-truth corpus in `~/res_arcana/`.
    skip_names: set[str] = set()
    if args.skip_list is not None and args.skip_list.is_file():
        for line in args.skip_list.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                skip_names.add(line)
    test_files = [tf for tf in test_files if tf.name not in skip_names]

    bot_cmd = args.bot.split()
    bot = spawn_bot(bot_cmd)

    t0 = time.perf_counter()
    passed = 0
    skipped = len(skip_names)
    failed: list[tuple[str, str]] = []
    respawns = 0

    try:
        for tf in test_files:
            ok, msg = run_test(tf, bot)
            if msg == "ok":
                passed += 1
                if args.verbose:
                    print(f"  PASS {tf.name}")
            elif "skipped" in msg:
                skipped += 1
            else:
                failed.append((tf.name, msg))
                print(f"  FAIL {tf.name}: {msg}", file=sys.stderr)

            # If the bot died mid-test, respawn so the next test isn't
            # cascade-failed by a dead pipe. One bot crash doesn't tank
            # the rest of the suite.
            if bot.proc.poll() is not None:
                try:
                    bot.close()
                except Exception:
                    pass
                bot = spawn_bot(bot_cmd)
                respawns += 1
    finally:
        bot.close()

    elapsed = time.perf_counter() - t0
    extra = f" [respawned bot {respawns}x]" if respawns else ""
    print(f"\n{passed} passed, {len(failed)} failed, {skipped} skipped in {elapsed:.1f}s{extra}")
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# Bench: expectimax over a precomputed answer key
# ---------------------------------------------------------------------------

def bench_expectimax(key_path: Path, bot_cmd: list[str], max_games: int | None = None) -> float:
    """Replay each precomputed game, ask the bot to search at each decision step,
    verify it returns one of the optimal moves. Times only the search calls.

    The bench is gameable in two ways without the answer key:
      - returning best_action=None  → bot's own assertion catches it
      - returning an arbitrary action → answer-key check catches it
    """
    with open(key_path) as f:
        key = json.load(f)
    depth: int = key["depth"]
    games: list[dict[str, Any]] = key["games"]
    assert games, "answer key has no games"
    if max_games is not None:
        games = games[:max_games]

    bot = spawn_bot(bot_cmd, capture_stderr=False)
    total_search_time = 0.0
    total_search_calls = 0
    total_nodes = 0
    per_seed: list[tuple[int, float, int, int]] = []  # (seed, time, calls, nodes)

    try:
        for game in games:
            actions: list[dict[str, Any]] = game["actions"]
            # actions[0]["step"] is the ResolveGameSetup. Everything after is a
            # chance node or a player decision (annotated with a "search" block).
            seed_time = 0.0
            seed_calls = 0
            seed_nodes = 0

            reply = bot.send({
                "cmd": "new_game_from_setup",
                "setup": actions[0]["step"],
                "player_id": 0,
                "num_players": int(game["num_players"]),
            })
            assert reply.get("status") == "ok", f"setup failed: {reply}"

            for entry in actions[1:]:
                if "search" in entry:
                    search = entry["search"]
                    reply = bot.send({
                        "cmd": "search",
                        "depth": depth,
                        "maximizing_pid": int(search["maximizing_pid"]),
                    })
                    seed_time += bot.last_reply_time
                    seed_calls += 1
                    assert "step" in reply, f"search failed: {reply}"
                    chosen = reply["step"]
                    optimal = search["optimal_steps"]
                    if chosen not in optimal:
                        raise AssertionError(
                            f"seed={game['seed']}: bot returned step not in optimal "
                            f"set (returned={chosen!r})"
                        )
                    nodes = reply.get("nodes", 0)
                    if isinstance(nodes, int):
                        seed_nodes += nodes

                # Always advance with the canonical step from the answer key,
                # so the game proceeds along the same path for everyone.
                reply = bot.send({"cmd": "advance", "step": entry["step"]})
                assert reply.get("status") == "ok", f"advance failed: {reply}"

            per_seed.append((int(game["seed"]), seed_time, seed_calls, seed_nodes))
            total_search_time += seed_time
            total_search_calls += seed_calls
            total_nodes += seed_nodes
    finally:
        bot.close()

    # Per-seed report (compact). Helps diagnose "one position is pathological."
    print("  per-seed: seed/time(s)/calls/nodes/ms-per-call")
    for seed, t, c, n in per_seed:
        ms = (t / c * 1000) if c else 0.0
        print(f"    seed={seed:>3} {t:>7.2f}s x{c:>3} {n:>10d} nodes {ms:>7.2f} ms/call")

    rate = total_nodes / total_search_time if total_search_time > 0 else 0
    print(
        f"expectimax depth={depth} x{total_search_calls} searches in {len(games)} games: "
        f"{total_search_time:.2f}s ({total_nodes} nodes, {rate:.0f} nodes/s)"
    )
    return total_search_time


def cmd_bench(args: argparse.Namespace) -> int:
    bot_cmd = args.bot.split() if args.bot else [sys.executable, "-m", "reference.expectimax"]
    bench_expectimax(args.key, bot_cmd, max_games=args.games)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(prog="harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_corr = sub.add_parser("correctness", help="Run JSON unit tests against a bot")
    p_corr.add_argument("--bot", default=f"{sys.executable} -m reference.expectimax",
                        help="Command to spawn the candidate's bot.")
    p_corr.add_argument("--tests", type=Path, default=Path("data/unit_tests"),
                        help="Directory of JSON tests to run.")
    p_corr.add_argument("--skip-list", type=Path, default=None,
                        help="Path to a file listing test filenames to skip "
                             "(one per line; '#' starts a comment).")
    p_corr.add_argument("--verbose", action="store_true")
    p_corr.set_defaults(func=cmd_correctness)

    p_bench = sub.add_parser("bench", help="Expectimax bench against an answer key")
    p_bench.add_argument("--bot", default=None,
                         help="Command to spawn the bot (e.g., './solution/my_bot'). "
                              "Defaults to the reference Python expectimax bot.")
    p_bench.add_argument("--key", type=Path,
                         default=Path(__file__).parent / "data" / "bench_answer_key.json",
                         help="Path to the precomputed answer key.")
    p_bench.add_argument("-n", "--games", type=int, default=None,
                         help="Run only the first N games from the answer key (for fast iteration). "
                              "Default: all.")
    p_bench.set_defaults(func=cmd_bench)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
