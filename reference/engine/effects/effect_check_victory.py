from __future__ import annotations

from dataclasses import dataclass

from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class EffectCheckVictory:

    def execute(self, ctx: PowerContext) -> None:
        state = ctx.state
        state.is_mid_round_victory_check = True
        state.begin_victory_check()

        pending_reacts = ctx.engine.scan_for_victory_react_powers(state, triggered_by=ctx.pid)

        if pending_reacts:
            state.pending_stack.extend(pending_reacts)
            state.pending_turn_advance = True
            return

        ctx.engine.finalize_victory_check(state)
