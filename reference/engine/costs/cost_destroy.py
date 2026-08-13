from __future__ import annotations

from dataclasses import dataclass

from ..card_location import CardLocation
from ..destroy_mode import DestroyMode
from ..power_context import PowerContext


@dataclass(frozen=True, slots=True)
class CostDestroyComponent:

    destroy_mode: DestroyMode

    def pay(self, ctx: PowerContext) -> None:
        match self.destroy_mode:
            case DestroyMode.SELF:
                assert ctx.eid is not None, "eid must be set for SELF destroy"
                ctx.entity.location = CardLocation.DISCARD
                ctx.entity.essences_on_card = None
            case DestroyMode.ANY:
                self._pay_any(ctx)
            case DestroyMode.ANOTHER:
                self._pay_another(ctx)

    def _pay_any(self, ctx: PowerContext) -> None:
        in_play = ctx.state.get_player_artifacts_in_play(ctx.pid)
        target_id = ctx.target_eid

        destroyed_eid: int
        if target_id is not None and target_id in in_play:
            destroyed_eid = target_id
        elif in_play:
            destroyed_eid = in_play[0]
        else:
            raise AssertionError("No artifact to destroy")

        destroyed_entity = ctx.state.entities[destroyed_eid]
        destroyed_entity.location = CardLocation.DISCARD
        destroyed_entity.essences_on_card = None

    def _pay_another(self, ctx: PowerContext) -> None:
        in_play = ctx.state.get_player_artifacts_in_play(ctx.pid)
        target_id = ctx.target_eid

        assert target_id is not None, "Must specify which artifact to destroy"
        assert target_id != ctx.eid, "Cannot destroy self with this power"
        assert target_id in in_play, f"Artifact {target_id} not in play"

        destroyed_entity = ctx.state.entities[target_id]
        destroyed_entity.location = CardLocation.DISCARD
        destroyed_entity.essences_on_card = None
