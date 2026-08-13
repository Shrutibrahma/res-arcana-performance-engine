from __future__ import annotations

from dataclasses import dataclass

from ..action_types import EntityId, PlayerId
from ..card_location import CardLocation
from ..pool import Pool
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionDiscardForEssences:

    pid: PlayerId
    eid: EntityId
    gain: Pool

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        player = state.players[self.pid]

        artifact_eid = self.eid

        hand = state.get_player_hand(self.pid)
        assert artifact_eid in hand, artifact_eid

        entity = state.entities[artifact_eid]

        assert self.gain

        total = self.gain.total()
        if self.gain.gold > 0:
            assert total == 1, total
            assert self.gain.gold == 1, self.gain.gold
        else:
            assert total == 2, total

        player.pool.add_pool(self.gain)

        entity.location = CardLocation.DISCARD
