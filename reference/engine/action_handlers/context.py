from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..action_types import PlayerId

if TYPE_CHECKING:
    from ..game_engine import GameEngine
    from ..game_state import GameState
    from ..player_state import PlayerState


@dataclass
class ActionContext:

    engine: GameEngine
    state: GameState
    pid: PlayerId

    @property
    def player(self) -> PlayerState:
        return self.state.players[self.pid]
