from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..game_phase import GamePhase
from ..pending_choices import (
    PendingPlacementChoice,
    PendingVictoryReactChoice,
)
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionDecline:

    pid: PlayerId
    eid: EntityId

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase in (
            GamePhase.COLLECT,
            GamePhase.ACTIONS,
            GamePhase.VICTORY_CHECK,
        ), state.phase

        assert state.pending_stack
        top = state.pending_stack[-1]
        assert top.pid == self.pid, (self.pid, top.pid)

        match top:
            case PendingVictoryReactChoice():
                assert top.component_eid == self.eid, (self.eid, top.component_eid)
                state.pending_stack.pop()
                if not any(isinstance(c, PendingVictoryReactChoice) for c in state.pending_stack):
                    ctx.engine.finalize_victory_check(state)

            case PendingPlacementChoice():
                assert top.source_eid == self.eid, (self.eid, top.source_eid)
                state.pending_stack.pop()

            case _:
                raise AssertionError(f"DECLINE called with non-declinable top of stack: {type(top).__name__}")
