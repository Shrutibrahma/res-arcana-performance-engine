from __future__ import annotations

from typing import assert_never

from . import available_actions as aa
from .action_handlers import (
    ActionClaimMonument,
    ActionClaimPlaceOfPower,
    ActionClaimTopMonument,
    ActionContext,
    ActionDiscardForEssences,
    ActionPass,
    ActionPlaceArtifact,
    ActionUsePower,
)
from .action_types import EntityId, PlayerId
from .actions import (
    Action,
    AvailableAction,
)
from .card_data import get_card_database
from .card_location import CardLocation
from .card_type import CardType
from .collect_ability import CollectAbility
from .collect_option_type import CollectOptionType
from .component_type import ComponentType
from .conditional_type import ConditionalType
from .costs import (
    CostDestroyCardType,
    CostDiscardCard,
    DestroyMode,
    TurnableType,
)
from .effects import (
    EffectGainAny,
    EffectPlace,
    EffectTempVP,
)
from .entity_data import Entity
from .essence import ESSENCE_COUNT, Essence
from .game_phase import GamePhase
from .game_state import GameState
from .pending_choices import (
    NaturalCollectOption,
    PendingChoice,
    PendingCollectCost,
    PendingCollectPhaseCursor,
    PendingCollectStorage,
    PendingDiscardChoice,
    PendingDrawRevealChoice,
    PendingGain,
    PendingGameSetupChoice,
    PendingLifeLossChoice,
    PendingLifeLossScan,
    PendingMonumentDrawChoice,
    PendingMonumentRevealChoice,
    PendingPlacementChoice,
    PendingScryChoice,
    PendingScryDeckChoice,
    PendingScryRevealChoice,
    PendingVictoryReactChoice,
    StoredEssenceOption,
)
from .pool import Pool
from .power import Power
from .power_type import PowerType
from .react_trigger import ReactTrigger
from .select_card_filter import SelectCardFilter
from .select_card_location import SelectCardLocation

_MAIN_ACTION_TYPES = (
    ActionPlaceArtifact,
    ActionClaimMonument,
    ActionClaimTopMonument,
    ActionClaimPlaceOfPower,
    ActionDiscardForEssences,
    ActionUsePower,
    ActionPass,
)


class GameEngine:
    def __init__(self):
        self.db = get_card_database()

    def execute_action(self, state: GameState, action: Action) -> None:
        is_main_action = isinstance(action, _MAIN_ACTION_TYPES)
        if is_main_action:
            assert state.phase == GamePhase.ACTIONS, state.phase
            assert state.current_player_index == action.pid, (
                action.pid,
                state.current_player_index,
            )

            for c in reversed(state.pending_stack):
                if c.pid == action.pid:
                    blocking_choice = self._pending_choice_blocks_main_action(c, action)
                    assert not blocking_choice, type(c).__name__

        phase_before = state.phase

        ctx = ActionContext(engine=self, state=state, pid=action.pid)
        action.execute(ctx)

        self.advance_cursors(state)

        phase_after_action = state.phase
        phase_changed_during_action = phase_after_action != phase_before

        if (
            state.phase == GamePhase.ACTIONS
            and state.all_players_passed()
            and not any(isinstance(c, PendingDrawRevealChoice) for c in state.pending_stack)
        ):
            self.end_action_phase(state)
            phase_changed_during_action = True

        if state.phase == GamePhase.COLLECT and phase_before != GamePhase.COLLECT:
            self.process_phase(state)

        phase_before_transitions = state.phase
        self._check_phase_transitions(state)

        if state.phase == GamePhase.COLLECT and phase_before_transitions != GamePhase.COLLECT:
            self.process_phase(state)

            self._check_phase_transitions(state)

        if (
            phase_before == GamePhase.ACTIONS
            and state.phase == GamePhase.ACTIONS
            and not phase_changed_during_action
            and not state.all_players_passed()
        ):
            has_blocking = self.has_any_blocking_pending_choice(state)

            if is_main_action:
                if has_blocking:
                    state.pending_turn_advance = True
                else:
                    state.advance_to_next_player()
                    state.pending_turn_advance = False
            elif state.pending_turn_advance and not has_blocking:

                state.advance_to_next_player()
                state.pending_turn_advance = False

    def _blocks_turn_advancement(self, choice: PendingChoice) -> bool:
        match choice:
            case (
                PendingScryDeckChoice()
                | PendingScryChoice()
                | PendingDiscardChoice()
                | PendingPlacementChoice()
                | PendingMonumentDrawChoice()
                | PendingGain()
                | PendingLifeLossChoice()
                | PendingLifeLossScan()
                | PendingDrawRevealChoice()
                | PendingMonumentRevealChoice()
                | PendingScryRevealChoice()
                | PendingGameSetupChoice()
            ):
                return True

            case PendingVictoryReactChoice():
                raise AssertionError("PendingVictoryReactChoice should not exist during ACTIONS phase")
            case PendingCollectStorage():
                raise AssertionError("PendingCollectStorage should not exist during ACTIONS phase")
            case PendingCollectCost():
                raise AssertionError("PendingCollectCost should not exist during ACTIONS phase")
            case PendingCollectPhaseCursor():
                raise AssertionError("PendingCollectPhaseCursor should not exist during ACTIONS phase")

            case _:
                assert_never(choice)

    def _pending_choice_blocks_main_action(self, choice: PendingChoice, action: Action) -> bool:
        match choice:
            case PendingPlacementChoice():
                return not isinstance(action, ActionPlaceArtifact)

            case (
                PendingScryDeckChoice()
                | PendingScryChoice()
                | PendingDiscardChoice()
                | PendingMonumentDrawChoice()
                | PendingGain()
                | PendingLifeLossChoice()
                | PendingLifeLossScan()
                | PendingDrawRevealChoice()
                | PendingMonumentRevealChoice()
                | PendingScryRevealChoice()
                | PendingGameSetupChoice()
            ):
                return True

            case (
                PendingVictoryReactChoice()
                | PendingCollectStorage()
                | PendingCollectCost()
                | PendingCollectPhaseCursor()
            ):
                raise AssertionError(f"{type(choice).__name__} should not exist during ACTIONS phase")

            case _:
                assert_never(choice)

    def has_any_blocking_pending_choice(self, state: GameState) -> bool:
        return any(self._blocks_turn_advancement(choice) for choice in state.pending_stack)

    def scan_for_victory_react_powers(
        self, state: GameState, triggered_by: PlayerId | None = None
    ) -> list[PendingVictoryReactChoice]:
        pending_choices: list[PendingVictoryReactChoice] = []

        for i in range(state.num_players):
            pid = PlayerId(i)
            player = state.players[pid]
            if not player.is_active:
                continue

            component_ids = (
                state.get_player_monuments(pid)
                + state.get_player_artifacts_in_play(pid)
                + state.get_player_places_of_power(pid)
            )

            for eid in component_ids:
                entity = state.entities[eid]

                for power_idx, power in enumerate(entity.data.powers):
                    if power.react_trigger != ReactTrigger.VICTORY_CHECK:
                        continue

                    if entity.is_turned:
                        break

                    essence_cost = power.get_essence_cost()
                    can_afford = player.pool.can_afford(essence_cost)
                    if not can_afford:
                        break

                    temp_vp = 0
                    for effect in power.effects:
                        if isinstance(effect, EffectTempVP):
                            temp_vp += effect.amount

                    pending_choices.append(
                        PendingVictoryReactChoice(
                            pid=pid,
                            component_eid=eid,
                            power_index=power_idx,
                        )
                    )
                    break

        pending_choices.sort(
            key=lambda c: (
                1 if c.pid == triggered_by else 0,
                c.pid,
                -c.component_eid,
            )
        )
        return pending_choices

    def end_action_phase(self, state: GameState) -> None:
        state.begin_victory_check()
        pending_reacts = self.scan_for_victory_react_powers(state)
        if pending_reacts:
            state.pending_stack.extend(pending_reacts)
            return
        self.finalize_victory_check(state)

    def finalize_victory_check(self, state: GameState) -> None:
        is_mid_round = state.is_mid_round_victory_check
        state.is_mid_round_victory_check = False
        vp_list: list[tuple[PlayerId, int]] = []
        for i in range(state.num_players):
            pid = PlayerId(i)
            vp = self.calculate_victory_points(state, pid)
            vp_list.append((pid, vp))

        threshold = state.victory_threshold
        winners: list[PlayerId] = [pid for pid, vp in vp_list if vp >= threshold]

        if winners:
            if len(winners) > 1:
                vp_by_pid = {pid: vp for pid, vp in vp_list}
                max_vp = max(vp_by_pid[pid] for pid in winners)
                winners = [pid for pid in winners if vp_by_pid[pid] == max_vp]

            if len(winners) > 1:
                best_tiebreaker: int = -1
                final_winners: list[PlayerId] = []
                for pid in winners:
                    pool = state.players[pid].pool
                    tb = sum(pool[:4]) + pool[Essence.GOLD] * 2
                    if tb > best_tiebreaker:
                        best_tiebreaker = tb
                        final_winners = [pid]
                    elif tb == best_tiebreaker:
                        final_winners.append(pid)
                winners = final_winners

            state.set_winner(winners)

        else:
            for i in range(len(state.temp_vp)):
                state.temp_vp[i] = 0

            if is_mid_round:
                state.phase = GamePhase.ACTIONS

                if state.pending_turn_advance and not self.has_any_blocking_pending_choice(state):
                    state.advance_to_next_player()
                    state.pending_turn_advance = False
            else:
                assert state.phase == GamePhase.VICTORY_CHECK, state.phase
                for player in state.players:
                    if player.is_active:
                        for _eid, entity in state.get_all_player_components(player.pid):
                            entity.is_turned = False
                state.begin_round()

    def _check_phase_transitions(self, state: GameState) -> None:
        if state.phase == GamePhase.COLLECT:
            self._check_collect_to_actions(state)
        elif state.phase == GamePhase.VICTORY_CHECK:
            self._check_victory_finalization(state)

    def _check_collect_to_actions(self, state: GameState) -> None:
        while True:
            if not state.pending_stack:
                state.begin_action_phase()
                return
            top = state.pending_stack[-1]
            if isinstance(top, PendingCollectPhaseCursor):
                self.advance_collect_phase(state)
            else:
                return

    def _check_victory_finalization(self, state: GameState) -> None:
        if not any(isinstance(c, PendingVictoryReactChoice) for c in state.pending_stack):
            self.finalize_victory_check(state)

    def trigger_monument_bought(self, state: GameState, pid: PlayerId, monument_eid: EntityId) -> None:
        mon = state.entities[monument_eid]
        mon_data = mon.data
        for power in mon_data.powers:
            if power.power_type == PowerType.BOUGHT:
                for effect in power.effects:
                    if isinstance(effect, EffectGainAny):

                        assert not effect.exclude
                        if effect.amount > 0:
                            restriction_mask = 1 << Essence.GOLD
                            state.pending_stack.append(
                                PendingGain(
                                    pid=pid,
                                    any_amount=effect.amount,
                                    restriction_mask=restriction_mask,
                                    source_eid=monument_eid,
                                )
                            )

    def build_stored_options(self, stored: Pool) -> tuple[StoredEssenceOption, ...]:
        options: list[StoredEssenceOption] = [
            StoredEssenceOption(essence=Essence(i), amount=stored[i]) for i in range(ESSENCE_COUNT) if stored[i] > 0
        ]
        return tuple(options)

    def execute_collect_phase(self, state: GameState) -> None:
        state.pending_stack.append(PendingCollectPhaseCursor(player=0, component_index=0, pass_num=0))

    def advance_collect_phase(self, state: GameState) -> None:
        cursor_idx = len(state.pending_stack) - 1
        cursor = state.pending_stack[cursor_idx]
        assert isinstance(cursor, PendingCollectPhaseCursor)
        player_val = cursor.player
        comp_idx = cursor.component_index
        pass_num = cursor.pass_num

        while True:
            if player_val >= state.num_players:
                state.pending_stack.pop(cursor_idx)
                return

            pid = PlayerId(player_val)
            components = state.get_all_player_components(pid)

            while comp_idx < len(components):
                eid, entity = components[comp_idx]
                comp_idx += 1

                collect = entity.data.collect_ability
                stack_before = len(state.pending_stack)

                if pass_num == 0:
                    if collect is not None:
                        if collect.has_collect_cost:
                            continue

                        if collect.has_conditional:
                            assert collect.conditional_type is not None
                            stored = entity.essences_on_card
                            match collect.conditional_type:
                                case ConditionalType.STORED_GOLD:
                                    if stored is not None and stored.gold > 0:
                                        self._push_collect_storage(state, pid, collect, entity, eid)
                                case ConditionalType.PER_STORED_ESSENCE:
                                    if stored is not None and not stored.is_empty():
                                        self._push_per_stored_pay(state, pid, collect, entity, eid)
                                case _ as unreachable:
                                    assert_never(unreachable)
                        else:
                            self._apply_collect(state, pid, collect, eid)

                    has_stored = entity.essences_on_card is not None and not entity.essences_on_card.is_empty()
                    if has_stored and (collect is None or not collect.has_conditional):
                        self._offer_take_stored(state, pid, entity, eid)
                else:
                    if collect is not None and collect.has_collect_cost:
                        state.pending_stack.append(
                            PendingCollectCost(
                                pid=pid,
                                eid=eid,
                                cost_essences=collect.cost_essences,
                                cost_turn=collect.cost_turn,
                            )
                        )

                if len(state.pending_stack) > stack_before:
                    state.pending_stack[cursor_idx] = PendingCollectPhaseCursor(
                        player=player_val, component_index=comp_idx, pass_num=pass_num
                    )
                    return

            if pass_num == 0:
                pass_num = 1
                comp_idx = 0
            else:
                player_val += 1
                pass_num = 0
                comp_idx = 0

    def advance_cursors(self, state: GameState) -> None:
        while state.pending_stack:
            top = state.pending_stack[-1]
            if isinstance(top, PendingLifeLossScan):
                self._advance_life_loss_scan(state)
            else:
                break

    def _advance_life_loss_scan(self, state: GameState) -> None:
        cursor_idx = len(state.pending_stack) - 1
        scan = state.pending_stack[cursor_idx]
        assert isinstance(scan, PendingLifeLossScan)

        num_players = state.num_players
        offset = scan.next_offset

        while offset < num_players:
            target_pid = PlayerId((scan.pid + offset) % num_players)
            offset += 1

            if target_pid == scan.pid:
                if not scan.include_self or not scan.all_players:
                    continue

            if state.players[target_pid].has_passed:
                continue

            state.pending_stack[cursor_idx] = PendingLifeLossScan(
                source=scan.source,
                amount=scan.amount,
                next_offset=offset,
                pid=scan.pid,
                include_self=scan.include_self,
                all_players=scan.all_players,
            )
            state.pending_stack.append(
                PendingLifeLossChoice(
                    pid=target_pid,
                    amount=scan.amount,
                    source=scan.source,
                )
            )
            return

        state.pending_stack.pop(cursor_idx)

    def _apply_collect(
        self,
        state: GameState,
        pid: PlayerId,
        collect: CollectAbility | None,
        source: EntityId,
    ) -> None:
        if collect is None:
            return

        player = state.players[pid]

        if not collect.essences.is_empty():
            player.pool.add_pool(collect.essences)

        if collect.any_amount > 0:
            state.pending_stack.append(
                PendingGain(
                    pid=pid,
                    any_amount=collect.any_amount,
                    restriction_mask=collect.restriction_mask,
                    source_eid=source,
                )
            )
        assert not (collect.choice_mask != 0 and collect.alt_any_amount > 0)

        if collect.choice_mask != 0:
            restriction_mask = collect.choice_mask_to_restriction()

            state.pending_stack.append(
                PendingGain(
                    pid=pid,
                    any_amount=1,
                    restriction_mask=restriction_mask,
                    source_eid=source,
                )
            )

    def _push_collect_storage(
        self,
        state: GameState,
        pid: PlayerId,
        collect: CollectAbility | None,
        entity: Entity,
        entity_id: EntityId,
    ) -> None:
        stored = entity.essences_on_card
        assert stored is not None
        stored_options = self.build_stored_options(stored)

        natural_options: list[NaturalCollectOption] = []

        if collect is not None:
            if not collect.essences.is_empty():
                natural_options.extend(
                    NaturalCollectOption(essence=Essence(i), amount=collect.essences[i])
                    for i in range(ESSENCE_COUNT)
                    if collect.essences[i] > 0
                )

            if collect.any_amount > 0:
                natural_options.append(
                    NaturalCollectOption(
                        option_type=CollectOptionType.ANY,
                        amount=collect.any_amount,
                        restriction_mask=collect.restriction_mask,
                    )
                )

            if collect.choice_mask != 0:
                restriction_mask = collect.choice_mask_to_restriction()
                natural_options.append(
                    NaturalCollectOption(
                        option_type=CollectOptionType.ANY,
                        amount=1,
                        restriction_mask=restriction_mask,
                        alt_any_amount=collect.alt_any_amount,
                        alt_restriction_mask=collect.restriction_mask,
                    )
                )
            elif collect.alt_any_amount > 0:
                natural_options.append(
                    NaturalCollectOption(
                        option_type=CollectOptionType.ANY,
                        amount=collect.alt_any_amount,
                        restriction_mask=collect.restriction_mask,
                    )
                )

        state.pending_stack.append(
            PendingCollectStorage(
                pid=pid,
                eid=entity_id,
                stored_essences=stored_options,
                natural_collect=natural_options,
            )
        )

    def _offer_take_stored(self, state: GameState, pid: PlayerId, entity: Entity, entity_id: EntityId) -> None:
        stored = entity.essences_on_card
        assert stored is not None
        stored_options = self.build_stored_options(stored)

        if stored_options:
            state.pending_stack.append(
                PendingCollectStorage(
                    pid=pid,
                    eid=entity_id,
                    stored_essences=stored_options,
                )
            )

    def _push_per_stored_pay(
        self,
        state: GameState,
        pid: PlayerId,
        collect: CollectAbility,
        entity: Entity,
        entity_id: EntityId,
    ) -> None:
        stored = entity.essences_on_card
        assert stored is not None
        stored_options = self.build_stored_options(stored)

        multiplier = collect.per_stored_essence_multiplier

        state.pending_stack.append(
            PendingCollectStorage(
                pid=pid,
                eid=entity_id,
                stored_essences=stored_options,
                bonus_multiplier=multiplier,
            )
        )

    def calculate_victory_points(self, state: GameState, pid: PlayerId) -> int:
        vp = 0
        if state.players[pid].has_first_player_token:
            vp += 1

        artifact_count = 0
        vp_per_two = 0
        for eid in state.get_player_artifacts_in_play(pid):
            art = state.entities[eid]
            artifact_count += 1
            vp += art.data.victory_points

            if art.data.victory_points_per_two_artifacts > 0:
                vp_per_two = art.data.victory_points_per_two_artifacts
        if vp_per_two > 0:
            vp += (artifact_count // 2) * vp_per_two

        for eid in state.get_player_monuments(pid):
            mon = state.entities[eid]
            vp += mon.data.victory_points

            if mon.essences_on_card is not None:
                for i, mult in enumerate(mon.data.points_per_essence):
                    vp += mon.essences_on_card[i] * mult

        for eid in state.get_player_places_of_power(pid):
            pop = state.entities[eid]
            vp += pop.data.base_points
            if pop.essences_on_card is not None:
                for i, mult in enumerate(pop.data.points_per_essence):
                    vp += pop.essences_on_card[i] * mult

            if pop.data.vp_per_dragon > 0:
                dragon_count = len(state.get_player_dragons(pid))
                vp += dragon_count * pop.data.vp_per_dragon

            if pop.data.vp_per_creature > 0:
                creature_count = len(state.get_player_creatures(pid))
                vp += creature_count * pop.data.vp_per_creature

            if pop.data.vp_per_artifact_count_num > 0:
                artifact_count = len(state.get_player_artifacts_in_play(pid))
                vp += (artifact_count * pop.data.vp_per_artifact_count_num) // pop.data.vp_per_artifact_count_denom

        vp += state.temp_vp[pid]

        return vp

    def get_available_actions(self, state: GameState, pid: PlayerId) -> list[AvailableAction]:
        return aa.get_available_actions(self, state, pid)

    def placement_target_matches_filter(self, entity: Entity, filter: SelectCardFilter, *, free: bool) -> bool:
        if not filter.matches_card_type_mask(entity.data.card_type_mask):
            return False
        if free and entity.data.cannot_be_free_placed:
            return False
        return True

    def get_valid_targets(
        self,
        state: GameState,
        pid: PlayerId,
        power: Power,
        source_entity_id: EntityId | None = None,
    ) -> list[EntityId]:
        targets: list[EntityId] = []
        select_card_cost = power.get_select_card_cost()

        if select_card_cost is not None and select_card_cost.has_filter():
            targets.extend(
                self.get_targets_from_filter(
                    state,
                    pid,
                    select_card_cost.filter,
                    power=power,
                    source_entity_id=source_entity_id,
                )
            )

            return targets

        for effect in power.effects:
            if isinstance(effect, EffectPlace):
                return []

        if power.has_turn_component_cost(TurnableType.MAGE):
            for mage_id, mage in state.iter_mages():
                if mage.location == CardLocation.IN_PLAY and mage.owner_id == pid and not mage.is_turned:
                    targets.append(mage_id)

        if power.has_turn_component_cost(TurnableType.DRAGON):
            targets.extend(state.get_straightened_of_type(pid, TurnableType.DRAGON))

        if power.has_turn_component_cost(TurnableType.CREATURE):
            targets.extend(state.get_straightened_of_type(pid, TurnableType.CREATURE))

        discard_cost = power.get_cost(CostDiscardCard)
        if discard_cost is not None:
            for eid in state.get_player_hand(pid):
                entity = state.entities[eid]
                if discard_cost.exclude_entity_flags and (entity.data.entity_flags & discard_cost.exclude_entity_flags):
                    continue
                if discard_cost.card_type_mask and not discard_cost.matches_type(entity.data):
                    continue
                targets.append(eid)

        if power.has_destroy_component_cost(DestroyMode.ANY):
            targets.extend(state.get_player_artifacts_in_play(pid))

        if power.has_destroy_component_cost(DestroyMode.ANOTHER):
            targets.extend(eid for eid in state.get_player_artifacts_in_play(pid) if eid != source_entity_id)

        destroy_cost = power.get_cost(CostDestroyCardType)
        destroy_card_type_mask = destroy_cost.card_type_mask if destroy_cost else 0
        if destroy_card_type_mask:
            for eid in state.get_player_artifacts_in_play(pid):
                art = state.entities[eid]
                if art.data:
                    matches = False
                    if (destroy_card_type_mask & (1 << CardType.CREATURE)) and art.data.is_creature:
                        matches = True
                    if (destroy_card_type_mask & (1 << CardType.DRAGON)) and art.data.is_dragon:
                        matches = True
                    if matches:
                        targets.append(eid)

        seen: set[EntityId] = set()
        unique_targets: list[EntityId] = []
        for t in targets:
            if t not in seen:
                seen.add(t)
                unique_targets.append(t)

        return unique_targets

    def get_targets_from_filter(
        self,
        state: GameState,
        pid: PlayerId,
        filter_obj: SelectCardFilter,
        *,
        power: Power | None = None,
        source_entity_id: EntityId | None = None,
    ) -> list[EntityId]:
        targets: list[EntityId] = []

        match filter_obj.location:
            case SelectCardLocation.NONE:
                pass

            case SelectCardLocation.HAND:

                raise AssertionError("SelectCardLocation.HAND not used in CostSelectCard")

            case SelectCardLocation.IN_PLAY:

                for eid, entity in state.get_all_player_components(pid):
                    if filter_obj.should_include_component(entity.kind):
                        if filter_obj.matches_entity(entity):
                            targets.append(eid)

            case SelectCardLocation.DISCARD:
                for eid in state.get_player_discard(pid):
                    entity = state.entities[eid]
                    if filter_obj.matches_entity(entity):
                        targets.append(eid)

            case SelectCardLocation.ANY_DISCARD:

                raise AssertionError("SelectCardLocation.ANY_DISCARD not used in CostSelectCard")

            case SelectCardLocation.MONUMENT:
                targets.extend(state.get_monument_display())
                top_mon = state.get_top_monument_from_deck()
                if top_mon is not None:
                    targets.append(top_mon)

            case _ as unreachable:
                assert_never(unreachable)

        if (
            power is not None
            and power.requires_turn
            and filter_obj.require_tapped
            and source_entity_id is not None
            and source_entity_id not in targets
        ):
            source = state.entities[source_entity_id]
            if not source.is_turned:
                if filter_obj.matches_card_type_mask(source.data.card_type_mask):
                    targets.append(source_entity_id)

        return targets

    def process_phase(self, state: GameState) -> None:
        if state.phase == GamePhase.COLLECT:
            self.execute_collect_phase(state)
