from __future__ import annotations

from dataclasses import dataclass, field

from ..action_types import EntityId, PlayerId
from ..card_location import CardLocation
from ..component_type import ComponentType
from ..costs import (
    Cost,
    CostDestroyCardType,
    CostDestroyComponent,
    CostDiscardCard,
    CostPayEssence,
    CostPayIdentical,
    CostRemoveFromCard,
    CostSelectCard,
    CostSelectPlayer,
    CostTurnComponent,
)
from ..destroy_mode import DestroyMode
from ..effects import EffectDamage, EffectIgnoreDamage
from ..game_phase import GamePhase
from ..game_state import Entity, GameState
from ..pending_choices import PendingLifeLossChoice
from ..pool import Pool
from ..power_context import PowerContext
from ..react_trigger import ReactTrigger
from .context import ActionContext


@dataclass(frozen=True, slots=True)
class ActionLifeLossReact:

    pid: PlayerId
    eid: EntityId
    power_index: int
    target_eid: EntityId | None = None
    pay: Pool = field(default_factory=Pool)
    gain: Pool = field(default_factory=Pool)

    def execute(self, ctx: ActionContext) -> None:
        state = ctx.state

        assert state.phase == GamePhase.ACTIONS, state.phase

        assert state.pending_stack
        top = state.pending_stack[-1]
        assert isinstance(top, PendingLifeLossChoice), type(top)
        assert top.pid == self.pid, top.pid
        choice = top

        entity_id = self.eid

        power_index = self.power_index

        if entity_id < len(state.entities):
            entity = state.entities[entity_id]
            if entity.data and entity.data.is_dragon and choice.source == entity_id:
                self._execute_dragon_defense_react(ctx, state, choice, entity_id, entity)
                return

        component_type, found_eid, data, power = state.find_component_power(self.pid, entity_id, power_index)

        assert component_type is not None, entity_id
        assert found_eid is not None, entity_id
        assert data is not None, entity_id

        entity = state.entities[found_eid]

        assert power is not None, power_index
        assert power.is_react

        assert any(isinstance(effect, EffectIgnoreDamage) for effect in power.effects)

        if power.react_trigger == ReactTrigger.DRAGON_ATTACK:
            source = choice.source
            is_dragon_source = False
            if isinstance(source, int):
                source_entity = state.entities[source]
                if source_entity.data and source_entity.data.is_dragon:
                    is_dragon_source = True
            assert is_dragon_source

        can_use_when_turned = power.is_react and not power.requires_turn
        assert not entity.is_turned or can_use_when_turned or power.usable_when_turned

        player = state.players[self.pid]
        essence_cost = power.get_essence_cost()
        assert player.pool.can_afford(essence_cost)

        player.pool.pay(essence_cost)

        if power.requires_turn:
            entity.is_turned = True

        if power.has_destroy_component_cost(DestroyMode.SELF) and component_type == ComponentType.ARTIFACT:
            entity.location = CardLocation.DISCARD
            entity.essences_on_card = None

        assert state.pending_stack.pop() is top

        power_ctx = PowerContext(
            engine=ctx.engine,
            state=state,
            pid=self.pid,
            entity=entity,
            eid=self.eid,
            gain=self.gain,
        )

        for effect in power.effects:
            effect.execute(power_ctx)

    def _execute_dragon_defense_react(
        self,
        ctx: ActionContext,
        state: GameState,
        choice: PendingLifeLossChoice,
        dragon_eid: EntityId,
        dragon_entity: Entity,
    ) -> None:
        assert choice.source == dragon_eid

        player = state.players[self.pid]

        assert dragon_entity.data is not None
        defense_options: list[Cost] = []
        for power in dragon_entity.data.powers:
            for effect in power.effects:
                if isinstance(effect, EffectDamage) and effect.defense_options:
                    defense_options = effect.defense_options
                    break
            if defense_options:
                break

        assert defense_options

        defense_paid = False

        for defense_cost in defense_options:
            match defense_cost:
                case CostPayEssence(essences=essences):
                    if self.pay == essences:
                        assert player.pool.can_afford(essences)
                        player.pool.pay(essences)
                        defense_paid = True
                        break
                case CostDiscardCard():
                    if self.target_eid is not None:
                        target_entity = state.entities[self.target_eid]
                        if target_entity.location == CardLocation.HAND:
                            assert target_entity.owner_id == self.pid
                            target_entity.location = CardLocation.DISCARD
                            defense_paid = True
                            break
                case CostDestroyComponent():
                    if self.target_eid is not None:
                        target_entity = state.entities[self.target_eid]
                        if target_entity.location == CardLocation.IN_PLAY:
                            assert target_entity.owner_id == self.pid
                            assert target_entity.kind == ComponentType.ARTIFACT, target_entity.kind
                            target_entity.location = CardLocation.DISCARD
                            target_entity.essences_on_card = None
                            defense_paid = True
                            break
                case (
                    CostTurnComponent()
                    | CostRemoveFromCard()
                    | CostPayIdentical()
                    | CostDestroyCardType()
                    | CostSelectPlayer()
                    | CostSelectCard()
                ):
                    raise AssertionError(f"Unexpected defense cost type: {defense_cost}")

        assert defense_paid

        assert state.pending_stack.pop() is choice
