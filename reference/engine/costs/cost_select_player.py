from __future__ import annotations

from dataclasses import dataclass

from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class CostSelectPlayer:

    opponent_only: bool = False

    def pay(self, ctx: PowerContext) -> None:
        assert ctx.target_pid is not None
        assert 0 <= ctx.target_pid < len(ctx.state.players), ctx.target_pid
        if self.opponent_only:
            assert ctx.target_pid != ctx.pid, ctx.target_pid
