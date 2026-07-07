from __future__ import annotations

from collections.abc import Sequence

from src.core.battle_errors import BattleError
from src.core.battle_results import (
    AttackResolution,
    AttackResult,
    DamageEvent,
    ChaseResult,
    DamageResult,
    DeathTrigger,
    DeathTriggerResult,
    EndRoundResult,
    RelocateResult,
    SecondHandResult,
    SkillResult,
    SkipResult,
    SwordSaintChoiceResult,
    SummonRequest,
    SummonResult,
    ThawResult,
)
from src.core.models import ActiveSkill, Character, FormationColumn, GamePhase, Position, SkillKind, SkillTarget
from src.core.rules import effect_display_name, is_adverse_status_effect


class BattleAttackMixin:
    def attackable_targets(self, attacker_player_id: int, attacker_id: str) -> list[Character]:
        attacker = self.game_state.player(attacker_player_id).get_character(attacker_id)
        if not attacker.is_alive and (attacker_player_id, attacker_id) not in self.pending_revivals:
            return []

        attacker_key = (attacker_player_id, attacker_id)
        opponent_id = self.game_state.opponent_id(attacker_player_id)
        forced_target_key = self._enraged_forced_target_key(attacker_key)
        if forced_target_key is not None and forced_target_key[0] == opponent_id:
            forced_target = self._character_by_key(forced_target_key)
            return [forced_target] if forced_target.is_alive else []
        living_enemies = [
            character
            for character in self._battle_characters(opponent_id)
            if character.is_alive and self._can_manually_select_target(attacker_player_id, (opponent_id, character.id))
        ]
        if self._character_has_battle_effect(attacker_key, "lowest_attack_target_only"):
            return self._lowest_attack_targets(opponent_id, living_enemies)
        if self._player_has_frontline_taunt_aura(opponent_id):
            living_front = [
                character
                for character in living_enemies
                if character.position is not None and character.position.column == FormationColumn.FRONT
            ]
            if living_front:
                return self._apply_attack_taunt(attacker_player_id, opponent_id, living_front)
        if self._character_has_battle_effect((attacker_player_id, attacker_id), "backline_attack"):
            return self._apply_attack_taunt(attacker_player_id, opponent_id, living_enemies)

        if self._player_positions_count_as_front(opponent_id):
            living_front = living_enemies
        else:
            living_front = [
                character
                for character in living_enemies
                if character.position is not None and character.position.column == FormationColumn.FRONT
            ]
        candidates = living_front if living_front else living_enemies
        return self._apply_attack_taunt(attacker_player_id, opponent_id, candidates)

    def _lowest_attack_targets(self, player_id: int, candidates: list[Character]) -> list[Character]:
        if not candidates:
            return []
        lowest_attack = min(self.effective_attack((player_id, character.id)) for character in candidates)
        return [
            character
            for character in candidates
            if self.effective_attack((player_id, character.id)) == lowest_attack
        ]

    def can_attack(self, attacker_player_id: int, attacker_id: str, target_id: str) -> bool:
        if self.game_state.phase != GamePhase.BATTLE:
            return False
        if self.current_player_id != attacker_player_id:
            return False
        if self.pending_followup_attack is not None and self.pending_followup_attack != (attacker_player_id, attacker_id):
            return False
        if not self.can_character_move(attacker_player_id, attacker_id):
            return False
        if self._pending_revival_consumes_turn((attacker_player_id, attacker_id)):
            return False
        attacker = self.game_state.player(attacker_player_id).get_character(attacker_id)
        if attacker.has_status_effect("frozen"):
            return False
        if attacker.has_status_effect("silenced") and not attacker.is_alive:
            return False

        return any(target.id == target_id for target in self.attackable_targets(attacker_player_id, attacker_id))

    def attack(self, attacker_player_id: int, attacker_id: str, target_id: str) -> AttackResult:
        if not self.can_attack(attacker_player_id, attacker_id, target_id):
            raise BattleError("Invalid attack.")

        self.action_damage_events.clear()
        is_followup_attack = self.pending_followup_attack == (attacker_player_id, attacker_id)
        attacker = self.game_state.player(attacker_player_id).get_character(attacker_id)
        target_player_id = self.game_state.opponent_id(attacker_player_id)
        target = self.game_state.player(target_player_id).get_character(target_id)
        target_had_taunt = self._target_has_taunt_effect((target_player_id, target_id))
        alive_before = self._living_character_keys()
        events: list[str] = []

        if is_followup_attack:
            if self.pending_followup_order_slot is None:
                raise BattleError("Invalid follow-up attack state.")
            slot_index = self.pending_followup_order_slot
            followup_remaining_before = max(1, self.pending_followup_remaining_attacks)
            if followup_remaining_before > 1:
                events.append(f"{attacker.name} 继续攻击，当前技能剩余 {followup_remaining_before} 段。")
            else:
                events.append(f"{attacker.name} 进行第二次攻击。")
        else:
            self._begin_tenacity_enemy_action(attacker_player_id)
            slot_index = self._record_movement(attacker_player_id, attacker_id)

        self._revive_if_pending((attacker_player_id, attacker_id), events)
        attack_resolution = self._resolve_attack_with_context(
            attacker_player_id=attacker_player_id,
            attacker_id=attacker_id,
            target_player_id=target_player_id,
            target_id=target_id,
            attack_percent=100,
            extra_target_reflect_percent=0,
        )
        events.extend(attack_resolution.events)

        target_defeated = not target.is_alive
        attacker_defeated = not attacker.is_alive
        defeated_character_keys = self._newly_defeated_keys(alive_before)
        defeated_character_names = self._names_for_keys(attacker_player_id, defeated_character_keys)
        if is_followup_attack:
            remaining_after_followup = max(0, self.pending_followup_remaining_attacks - 1)
            waits_for_followup = (
                remaining_after_followup > 0
                and attacker.is_alive
                and self._has_followup_attack_target(attacker_player_id, attacker_id)
            )
            if waits_for_followup:
                self.pending_followup_remaining_attacks = remaining_after_followup
        else:
            waits_for_followup = (
                (
                    self._character_has_battle_effect((attacker_player_id, attacker_id), "double_attack")
                    or self._character_has_battle_effect((attacker_player_id, attacker_id), "sword_saint_double_attack")
                    or (
                        attack_resolution.target_defeated
                        and self._character_has_battle_effect((attacker_player_id, attacker_id), "extra_attack_on_kill")
                    )
                )
                and attacker.is_alive
                and self._has_followup_attack_target(attacker_player_id, attacker_id)
            )
            if waits_for_followup:
                self.pending_followup_remaining_attacks = 1
        if waits_for_followup:
            self.pending_followup_attack = (attacker_player_id, attacker_id)
            self.pending_followup_order_slot = slot_index
            if self.pending_followup_remaining_attacks > 1:
                events.append(f"{attacker.name} 还可选择 {self.pending_followup_remaining_attacks} 次攻击目标。")
            else:
                events.append(f"{attacker.name} 可以选择第二次攻击目标。")
        else:
            self._finish_attack_move(attacker_player_id, attacker_id, slot_index)
            if self._refund_fearless_attack_move((attacker_player_id, attacker_id), target_had_taunt):
                events.append(f"{attacker.name} 攻击不具有嘲讽的敌人，恢复1次移动次数。")

        events.extend(self._queue_death_triggers(defeated_character_keys))
        defeated_character_names = self._newly_defeated_names(attacker_player_id, alive_before)
        winner_player_id = None
        if self.pending_death_triggers or self.pending_summons or self._has_pending_manual_choice():
            if not waits_for_followup:
                self.pending_post_action_player_id = attacker_player_id
        else:
            winner_player_id = self._check_winner()
        if self._has_pending_manual_choice() and not self.pending_death_triggers and not self.pending_summons:
            self._set_current_player_for_pending_manual_choice()
        if (
            winner_player_id is None
            and not self.pending_death_triggers
            and not self.pending_summons
            and not self._has_pending_manual_choice()
            and not waits_for_followup
        ):
            self._advance_turn_after_action(attacker_player_id)

        return AttackResult(
            attacker_name=attacker.name,
            target_name=target.name,
            damage=attack_resolution.damage,
            target_defeated=target_defeated,
            skipped_actor_names=(),
            winner_player_id=winner_player_id,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
            actual_target_name=attack_resolution.actual_target_name,
            reflected_damage=attack_resolution.reflected_damage,
            attacker_defeated=attacker_defeated,
            defeated_character_names=tuple(defeated_character_names),
            events=tuple(events),
            damage_events=tuple(self.action_damage_events),
        )

    def effective_attack(
        self,
        character_key: tuple[int, str],
        target_key: tuple[int, str] | None = None,
    ) -> int:
        character = self._character_by_key(character_key)
        if not character.is_alive:
            return character.attack
        if character_key in self.suppressed_bonus_character_keys:
            return character.attack

        bonus = 0
        player_id, character_id = character_key
        if character.position is not None:
            for ally in self._battle_characters(player_id):
                if ally.id == character_id or not ally.is_alive or ally.position is None:
                    continue
                ally_key = (player_id, ally.id)
                if self._character_has_battle_effect(ally_key, "adjacent_attack_aura") and self._is_adjacent(
                    ally.position,
                    character.position,
                ):
                    bonus += 1
                if self._character_has_battle_effect(ally_key, "adjacent_holy_aura") and self._is_adjacent(
                    ally.position,
                    character.position,
                ):
                    bonus += 1
                if (
                    self._character_has_battle_effect(ally_key, "adjacent_wolf_health_attack_aura")
                    and "狼" in character.factions
                    and self._is_adjacent(ally.position, character.position)
                ):
                    bonus += 1
                if (
                    self._character_has_battle_effect(ally_key, "adjacent_wolf_attack_aura")
                    and "狼" in character.factions
                    and self._is_adjacent(ally.position, character.position)
                ):
                    bonus += 1
                if (
                    self._character_has_battle_effect(ally_key, "same_row_dragon_attack_aura")
                    and "龙" in character.factions
                    and ally.position.column == character.position.column
                ):
                    bonus += 2
                if (
                    self._character_has_battle_effect(ally_key, "rank_attack_health_aura")
                    and ally.position.column == character.position.column
                ):
                    bonus += 3
                if (
                    self._character_has_battle_effect(ally_key, "commander_warrior_aura")
                    and self._character_counts_as_job(character_key, "warrior")
                ):
                    bonus += 1

        if (
            target_key is not None
            and self._character_has_battle_effect(character_key, "bonus_vs_guardian_defender")
            and self._character_by_key(target_key).job.id in ("guardian", "defender")
        ):
            bonus += 2

        if self._character_has_battle_effect(character_key, "dragon_arcane_adapt") and self._has_adjacent_arcane_ally(character_key):
            bonus += 2

        if self._character_has_battle_effect(character_key, "other_friendly_wolf_attack_bonus"):
            bonus += self._other_friendly_wolf_count(character_key)

        if self._character_has_battle_effect(character_key, "other_wolf_attack_penalty"):
            bonus -= self._other_battle_wolf_count(character_key)

        if self.attacking_character_key == character_key and self._character_has_battle_effect(character_key, "stone_attack_buff"):
            bonus += 1

        attack = character.attack + bonus + self.round_attack_modifiers.get(character_key, 0)
        if self._character_has_battle_effect(character_key, "attack_multiplier_150"):
            attack = self._percentage_damage(attack, 150)
        if character.has_status_effect("weak"):
            attack = self._percentage_damage(attack, 50)
        return max(0, attack)

    def _resolve_attack_with_context(
        self,
        *,
        attacker_player_id: int,
        attacker_id: str,
        target_player_id: int,
        target_id: str,
        attack_percent: int,
        extra_target_reflect_percent: int,
    ) -> AttackResolution:
        attacker_key = (attacker_player_id, attacker_id)
        events: list[str] = []
        added_health = 0
        previous_attacker_key = self.attacking_character_key
        self.attacking_character_key = attacker_key
        attacker = self._character_by_key(attacker_key)
        if attacker.is_alive and self._character_has_battle_effect(attacker_key, "stone_attack_buff"):
            added_health = 2
            attacker.max_health += added_health
            attacker.current_health += added_health
            events.append(f"{attacker.name} 攻击时生命 +2。")

        try:
            base_damage = self._percentage_damage(
                self.effective_attack(attacker_key, (target_player_id, target_id)),
                attack_percent,
            )
            if self._character_has_battle_effect(attacker_key, "thunder_attack"):
                if base_damage > 0:
                    events.append(f"{attacker.name} 的攻击力伤害降低至0。")
                base_damage = 0
            is_critical = self._attack_is_critical(attacker_key, (target_player_id, target_id))
            if is_critical:
                critical_bonus = self._percentage_damage(base_damage, 50)
                base_damage += critical_bonus
                events.append(f"{attacker.name} 暴击，伤害 +{critical_bonus}。")
            resolution = self._resolve_attack_action(
                attacker_player_id=attacker_player_id,
                attacker_id=attacker_id,
                target_player_id=target_player_id,
                target_id=target_id,
                base_damage=base_damage,
                extra_target_reflect_percent=extra_target_reflect_percent,
                critical=is_critical,
            )
            return AttackResolution(
                damage=resolution.damage,
                actual_target_name=resolution.actual_target_name,
                reflected_damage=resolution.reflected_damage,
                target_defeated=resolution.target_defeated,
                attacker_defeated=resolution.attacker_defeated,
                events=tuple([*events, *resolution.events]),
            )
        finally:
            if added_health:
                attacker.max_health = max(1, attacker.max_health - added_health)
                if attacker.current_health > attacker.max_health:
                    attacker.current_health = attacker.max_health
            self.attacking_character_key = previous_attacker_key

    def _resolve_attack_action(
        self,
        *,
        attacker_player_id: int,
        attacker_id: str,
        target_player_id: int,
        target_id: str,
        base_damage: int,
        extra_target_reflect_percent: int,
        critical: bool = False,
    ) -> AttackResolution:
        attacker_key = (attacker_player_id, attacker_id)
        target_key = (target_player_id, target_id)
        target = self._character_by_key(target_key)
        events: list[str] = []
        primary_damage = 0
        reflected_damage = 0
        actual_target_name = target.name
        suppresses_target_buffs = self._character_has_battle_effect(attacker_key, "clear_target_buffs_on_attack")
        grants_target_undying = (
            self._character_has_battle_effect(attacker_key, "non_dragon_target_undying")
            and not self._is_dragon_character(target_key)
        )

        if grants_target_undying:
            self.temporary_undying_character_keys.add(target_key)
        if suppresses_target_buffs:
            events.extend(self._begin_temporary_buff_suppression(target_key))

        try:
            damage_result = self._resolve_damage(
                moving_player_id=attacker_player_id,
                source_key=attacker_key,
                target_key=target_key,
                base_damage=base_damage,
                immune_character_keys=(),
                allow_guard=True,
                critical=critical,
            )
            primary_damage += damage_result.damage
            actual_target_name = damage_result.receiver_name
            events.extend(damage_result.events)

            events.extend(
                self._resolve_splash_damage(
                    attacker_key=attacker_key,
                    target_key=target_key,
                    splash_damage=damage_result.damage,
                    moving_player_id=attacker_player_id,
                    critical=critical,
                )
            )
            events.extend(
                self._resolve_adjacent_rank_splash(
                    attacker_key=attacker_key,
                    target_key=target_key,
                    moving_player_id=attacker_player_id,
                )
            )
            thunder_damage, thunder_events = self._resolve_thunder_damage(
                attacker_key=attacker_key,
                target_key=target_key,
                moving_player_id=attacker_player_id,
            )
            primary_damage += thunder_damage
            events.extend(thunder_events)

            attacker_alive_before_reflect = self._character_by_key(attacker_key).is_alive
            reflect_damage, reflect_events = self._resolve_reflect_damage(
                attacker_key=attacker_key,
                target_key=target_key,
                extra_target_reflect_percent=extra_target_reflect_percent,
            )
            reflected_damage += reflect_damage
            events.extend(reflect_events)

            events.extend(
                self._apply_after_attack_effects(
                    attacker_key,
                    target_key,
                    damage_result.receiver_key,
                    primary_damage,
                    attacker_alive_before_reflect=attacker_alive_before_reflect,
                )
            )
        finally:
            if suppresses_target_buffs:
                self._end_temporary_buff_suppression(target_key)
            if grants_target_undying:
                self.temporary_undying_character_keys.discard(target_key)

        attacker = self._character_by_key(attacker_key)

        return AttackResolution(
            damage=primary_damage,
            actual_target_name=actual_target_name,
            reflected_damage=reflected_damage,
            target_defeated=not target.is_alive,
            attacker_defeated=not attacker.is_alive,
            events=tuple(events),
        )

    def _resolve_splash_damage(
        self,
        *,
        attacker_key: tuple[int, str],
        target_key: tuple[int, str],
        splash_damage: int,
        moving_player_id: int,
        critical: bool = False,
    ) -> list[str]:
        if splash_damage <= 0:
            return []
        if self._character_has_battle_effect(attacker_key, "same_row_splash"):
            actual_splash_damage = splash_damage
        elif self._character_has_battle_effect(attacker_key, "same_row_splash_50"):
            actual_splash_damage = self._percentage_damage(splash_damage, 50)
        else:
            return []

        target_player_id, target_id = target_key
        target = self._character_by_key(target_key)
        if target.position is None:
            return []

        events: list[str] = []
        for splash_key in self._same_row_character_keys(target_player_id, target.position.row, exclude_id=target_id):
            splash_target = self._character_by_key(splash_key)
            damage_result = self._resolve_damage(
                moving_player_id=moving_player_id,
                source_key=attacker_key,
                target_key=splash_key,
                base_damage=actual_splash_damage,
                immune_character_keys=(),
                allow_guard=True,
                critical=critical,
            )
            events.append(f"{splash_target.name} 受到溅射 {damage_result.damage} 点。")
            events.extend(damage_result.events)
        return events

    def _resolve_reflect_damage(
        self,
        *,
        attacker_key: tuple[int, str],
        target_key: tuple[int, str],
        extra_target_reflect_percent: int,
    ) -> tuple[int, list[str]]:
        reflect_percent = self._reflect_percent_for_attack(attacker_key, target_key, extra_target_reflect_percent)
        if reflect_percent <= 0:
            return 0, []

        reflector = self._character_by_key(target_key)
        reflected_attack = self.effective_attack(target_key, attacker_key)
        if self._target_effect_active_for_attack(target_key, "double_attack_for_reflect"):
            reflected_attack = self._percentage_damage(reflected_attack, 200)
        reflected_base_damage = self._percentage_damage(reflected_attack, reflect_percent)
        reflect_result = self._resolve_damage(
            moving_player_id=attacker_key[0],
            source_key=target_key,
            target_key=attacker_key,
            base_damage=reflected_base_damage,
            immune_character_keys=self._attack_immune_keys(attacker_key, target_key),
            allow_guard=True,
        )
        events = [f"{reflector.name} 反伤 {reflect_result.damage} 点。", *reflect_result.events]
        events.extend(self._apply_after_damage_effects(target_key, reflect_result.receiver_key, reflect_result.damage))
        return reflect_result.damage, events

    def _apply_after_attack_effects(
        self,
        attacker_key: tuple[int, str],
        target_key: tuple[int, str],
        receiver_key: tuple[int, str],
        primary_damage: int,
        *,
        attacker_alive_before_reflect: bool | None = None,
    ) -> list[str]:
        attacker = self._character_by_key(attacker_key)
        target = self._character_by_key(target_key)
        receiver = self._character_by_key(receiver_key)
        events: list[str] = []
        can_trigger_kill_effects = attacker.is_alive if attacker_alive_before_reflect is None else attacker_alive_before_reflect

        if attacker.is_alive and primary_damage > 0 and self._character_has_battle_effect(attacker_key, "lifesteal_on_attack"):
            before_health = attacker.current_health
            attacker.heal(primary_damage)
            healed = attacker.current_health - before_health
            events.append(f"{attacker.name} 吸血恢复 {healed} 点生命。")

        if target.is_alive and self._character_has_battle_effect(attacker_key, "bleed_on_attack"):
            status_applied = self.apply_status_effect(target_key[0], target_key[1], "bleeding")
            if status_applied:
                events.append(f"{target.name} 获得流血。")
            else:
                events.append(f"{target.name} 免疫了流血。")

        if target.is_alive and self._character_has_battle_effect(attacker_key, "freeze_on_attack"):
            status_applied = self.apply_status_effect(target_key[0], target_key[1], "frozen")
            if status_applied:
                events.append(f"{target.name} 获得冻结。")
            else:
                events.append(f"{target.name} 免疫了冻结。")

        if target.is_alive and self._character_has_battle_effect(attacker_key, "menace_bleed_weak_after_attack"):
            bleeding_applied = self.apply_status_effect(target_key[0], target_key[1], "bleeding", source_key=attacker_key)
            weak_applied = self.apply_status_effect(target_key[0], target_key[1], "weak", source_key=attacker_key)
            details: list[str] = []
            if bleeding_applied:
                details.append("流血")
            if weak_applied:
                details.append("虚弱")
            if details:
                events.append(f"{target.name} 获得{'、'.join(details)}。")
            else:
                events.append(f"{target.name} 免疫了流血与虚弱。")

        if attacker.is_alive and self._character_has_battle_effect(attacker_key, "growth_on_attack"):
            attacker.attack += 1
            attacker.gain_health(1)
            events.append(f"{attacker.name} 获得 +1攻击力与 +1生命。")

        if attacker.is_alive and self._character_has_battle_effect(attacker_key, "ending_after_attack"):
            lost = self._reduce_max_health_flat(attacker_key, 1, source_key=None)
            attacker.attack += 2
            events.append(f"{attacker.name} 攻击后生命上限 -{lost}，攻击力 +2。")

        events.extend(self._apply_after_damage_effects(attacker_key, receiver_key, primary_damage))

        if (
            target.is_alive
            and self._character_has_battle_effect(attacker_key, "dragon_bleed_on_attack")
            and self._is_dragon_character(target_key)
        ):
            status_applied = self.apply_status_effect(target_key[0], target_key[1], "bleeding")
            if status_applied:
                events.append(f"{target.name} 获得流血。")
            else:
                events.append(f"{target.name} 免疫了流血。")

        if (
            target.is_alive
            and receiver_key == target_key
            and target.current_health <= 4
            and self._character_has_battle_effect(attacker_key, "execute_low_health_unguarded")
        ):
            if self._execute_character(target_key, attacker_key):
                events.append(f"{target.name} 被 {attacker.name} 消灭。")
            else:
                events.append(f"{target.name} 的不死无视了消灭。")

        if (
            attacker.is_alive
            and self._character_has_battle_effect(attacker_key, "wind_child_attack_aura")
        ):
            for ally in self._battle_characters(attacker_key[0]):
                if ally.id == attacker_key[1] or not ally.is_alive:
                    continue
                ally_key = (attacker_key[0], ally.id)
                self.round_attack_modifiers[ally_key] = self.round_attack_modifiers.get(ally_key, 0) + 1
            events.append(f"{attacker.name} 使其余友方本回合攻击力 +1。")

        if (
            can_trigger_kill_effects
            and primary_damage > 0
            and not target.is_alive
            and self._target_effect_active_for_attack(attacker_key, "arson_on_kill")
        ):
            events.extend(self._resolve_arson_damage(attacker_key, target_key))

        if (
            can_trigger_kill_effects
            and not target.is_alive
            and self._target_effect_active_for_attack(attacker_key, "attack_gain_on_kill")
        ):
            attacker.attack += 2
            events.append(f"{attacker.name} 击杀后攻击力 +2。")

        if (
            attacker.is_alive
            and self._character_has_battle_effect(attacker_key, "sword_saint_double_attack")
            and self._sword_saint_warrior_keys(attacker_key)
        ):
            self.pending_sword_saint_choices.append(attacker_key)
            events.append(f"{attacker.name} 需要选择剑圣攻击后效果。")

        if attacker.is_alive and self._character_has_battle_effect(attacker_key, "chase_after_attack"):
            chase_targets = self._chase_target_keys(attacker_key, target_key)
            if chase_targets:
                self.pending_chase_choices.append((attacker_key, target_key))
                events.append(f"{attacker.name} 可以选择追击目标。")

        if attacker.is_alive and self._character_has_battle_effect(attacker_key, "heal_after_attack"):
            heal_amount = self.effective_attack(attacker_key)
            self.pending_death_triggers.append(
                DeathTrigger(
                    player_id=attacker_key[0],
                    character_id=attacker_key[1],
                    character_name=attacker.name,
                    damage=heal_amount,
                    kind="heal",
                )
            )
            events.append(f"{attacker.name} 攻击后可以选择一名角色恢复 {heal_amount} 点生命。")

        if attacker.is_alive and self._character_has_battle_effect(attacker_key, "menace_heal_after_attack"):
            heal_amount = attacker.current_health
            self.pending_death_triggers.append(
                DeathTrigger(
                    player_id=attacker_key[0],
                    character_id=attacker_key[1],
                    character_name=attacker.name,
                    damage=heal_amount,
                    kind="heal_ally",
                )
            )
            events.append(f"{attacker.name} 攻击后可以选择一名友方角色恢复 {heal_amount} 点生命。")

        return events

    def _apply_after_damage_effects(
        self,
        source_key: tuple[int, str],
        receiver_key: tuple[int, str],
        damage: int,
    ) -> list[str]:
        source = self._character_by_key(source_key)
        receiver = self._character_by_key(receiver_key)
        if not source.is_alive or damage <= 0 or not receiver.is_alive:
            return []

        events: list[str] = []
        if self._character_has_battle_effect(source_key, "max_health_cut_on_damage"):
            reduced = self._reduce_max_health_percent(receiver_key, 25, source_key=source_key)
            if reduced > 0:
                events.append(f"{receiver.name} 生命上限 -{reduced}。")

        if self._character_has_battle_effect(source_key, "max_health_cut_equal_damage") and receiver.is_alive:
            reduced = self._reduce_max_health_flat(receiver_key, damage, source_key=source_key)
            if reduced > 0:
                events.append(f"{receiver.name} 生命上限 -{reduced}。")

        if self._character_has_battle_effect(source_key, "poison_on_damage") and receiver.is_alive:
            poison_damage = self._percentage_damage(receiver.max_health, 25)
            if poison_damage > 0:
                poison_result = self._resolve_damage(
                    moving_player_id=source_key[0],
                    source_key=source_key,
                    target_key=receiver_key,
                    base_damage=poison_damage,
                    immune_character_keys=(),
                    allow_guard=False,
                )
                events.append(f"{receiver.name} 受到剧毒 {poison_result.damage} 点。")
                events.extend(poison_result.events)
        return events

    def _begin_temporary_buff_suppression(self, target_key: tuple[int, str]) -> list[str]:
        target = self._character_by_key(target_key)
        events: list[str] = []
        self.suppressed_bonus_character_keys.add(target_key)

        if target.attack > target.base_attack:
            lost_attack = target.attack - target.base_attack
            target.attack = target.base_attack
            events.append(f"{target.name} 失去 {lost_attack} 点攻击加成。")

        if target.armor > 0:
            lost_armor = target.armor
            target.armor = 0
            events.append(f"{target.name} 失去 {lost_armor} 点护甲。")

        max_health_before = target.max_health
        base_with_current_aura = target.base_max_health + target.aura_max_health_bonus
        if target.max_health > base_with_current_aura:
            target.max_health = base_with_current_aura
            if target.current_health > target.max_health:
                target.current_health = target.max_health

        self._refresh_aura_health_bonuses()
        if target.max_health < max_health_before:
            events.append(f"{target.name} 失去 {max_health_before - target.max_health} 点生命上限加成。")
        if events:
            events.insert(0, f"{target.name} 的加成效果被剥离。")
        else:
            events.append(f"{target.name} 暂时失去加成效果。")
        return events

    def _end_temporary_buff_suppression(self, target_key: tuple[int, str]) -> None:
        self.suppressed_bonus_character_keys.discard(target_key)
        self._refresh_aura_health_bonuses()

    def _has_followup_attack_target(self, attacker_player_id: int, attacker_id: str) -> bool:
        attacker = self._character_by_key((attacker_player_id, attacker_id))
        if not attacker.is_alive or attacker.position is None:
            return False
        if attacker.has_status_effect("frozen"):
            return False
        return bool(self.attackable_targets(attacker_player_id, attacker_id))

    def _finish_attack_move(self, attacker_player_id: int, attacker_id: str, slot_index: int) -> None:
        move_key = (attacker_player_id, attacker_id)
        self.remaining_moves[move_key] = max(0, self.remaining_moves.get(move_key, 0) - 1)
        self._resolve_order_slot(attacker_player_id, slot_index)
        if self.pending_followup_attack == move_key:
            self.pending_followup_attack = None
            self.pending_followup_order_slot = None
            self.pending_followup_remaining_attacks = 0

    def _refund_fearless_attack_move(self, attacker_key: tuple[int, str], target_had_taunt: bool) -> bool:
        attacker = self._character_by_key(attacker_key)
        if target_had_taunt or not attacker.is_alive:
            return False
        if not self._character_has_battle_effect(attacker_key, "fearless_move_refund"):
            return False
        used_count = self.fearless_refund_counts.get(attacker_key, 0)
        if used_count >= 3:
            return False
        self.fearless_refund_counts[attacker_key] = used_count + 1
        self.remaining_moves[attacker_key] = self.remaining_moves.get(attacker_key, 0) + 1
        return True

    def _resume_or_finish_pending_followup(self) -> int | None:
        if self._has_pending_manual_choice():
            self._set_current_player_for_pending_manual_choice()
            return None

        pending = self.pending_followup_attack
        slot_index = self.pending_followup_order_slot
        if pending is None or slot_index is None:
            return self._check_winner()

        winner_player_id = self._check_winner()
        if winner_player_id is not None:
            self.pending_followup_attack = None
            self.pending_followup_order_slot = None
            return winner_player_id

        attacker_player_id, attacker_id = pending
        if self.pending_followup_remaining_attacks > 0 and self._has_followup_attack_target(attacker_player_id, attacker_id):
            self.game_state.current_turn_player_id = attacker_player_id
            return None

        self._finish_attack_move(attacker_player_id, attacker_id, slot_index)
        winner_player_id = self._check_winner()
        if winner_player_id is None:
            self._advance_turn_after_action(attacker_player_id)
        return winner_player_id

    def _attack_damage(self, attacker_player_id: int, attacker_id: str, target_player_id: int, target_id: str) -> int:
        return self.effective_attack((attacker_player_id, attacker_id), (target_player_id, target_id))

    def _resolve_damage(
        self,
        *,
        moving_player_id: int,
        source_key: tuple[int, str],
        target_key: tuple[int, str],
        base_damage: int,
        immune_character_keys: Sequence[tuple[int, str]],
        allow_guard: bool,
        critical: bool = False,
    ) -> DamageResult:
        requested_target = self._character_by_key(target_key)
        receiver_key = target_key
        events: list[str] = []

        if self._damage_is_immune(target_key, immune_character_keys):
            events.append(f"{requested_target.name} 免疫了 {base_damage} 点伤害。")
            return DamageResult(
                requested_target_name=requested_target.name,
                receiver_name=requested_target.name,
                damage=0,
                receiver_key=target_key,
                events=tuple(events),
            )

        if (
            base_damage > 0
            and self._character_has_battle_effect(target_key, "first_damage_immunity_each_round")
            and not requested_target.has_used_passive_effect("first_damage_immunity_each_round")
        ):
            requested_target.mark_passive_effect_used("first_damage_immunity_each_round")
            events.append(f"{requested_target.name} 免疫了本轮首次伤害。")
            return DamageResult(
                requested_target_name=requested_target.name,
                receiver_name=requested_target.name,
                damage=0,
                receiver_key=target_key,
                events=tuple(events),
            )

        if base_damage > 0 and self._character_has_battle_effect(target_key, "shield") and self._consume_shield(target_key):
            remaining = self.shield_stack_count(target_key)
            suffix = f"，剩余 {remaining} 层" if remaining > 0 else ""
            events.append(f"{requested_target.name} 的护盾免疫了 {base_damage} 点伤害{suffix}。")
            return DamageResult(
                requested_target_name=requested_target.name,
                receiver_name=requested_target.name,
                damage=0,
                receiver_key=target_key,
                events=tuple(events),
            )

        barrier_result = self._resolve_team_barrier_damage(target_key, base_damage)
        if barrier_result is not None:
            events.extend(barrier_result.events)
            return DamageResult(
                requested_target_name=requested_target.name,
                receiver_name=barrier_result.receiver_name,
                damage=0,
                receiver_key=target_key,
                events=tuple(events),
            )

        if allow_guard and not self._target_cannot_be_guarded(target_key):
            guarded_receiver_keys = self._guard_receiver_keys(moving_player_id, target_key)
            if guarded_receiver_keys:
                total_damage = 0
                receiver_names: list[str] = []
                first_receiver_key = guarded_receiver_keys[0]
                for guarded_receiver_key in guarded_receiver_keys:
                    receiver = self._character_by_key(guarded_receiver_key)
                    receiver_names.append(receiver.name)
                    guarded_result = self._resolve_damage(
                        moving_player_id=moving_player_id,
                        source_key=source_key,
                        target_key=guarded_receiver_key,
                        base_damage=base_damage,
                        immune_character_keys=immune_character_keys,
                        allow_guard=False,
                        critical=critical,
                    )
                    total_damage += guarded_result.damage
                    events.extend(guarded_result.events)
                events.insert(0, f"{requested_target.name} 的伤害由 {'、'.join(receiver_names)} 抵御。")
                return DamageResult(
                    requested_target_name=requested_target.name,
                    receiver_name="、".join(receiver_names),
                    damage=total_damage,
                    receiver_key=first_receiver_key,
                    events=tuple(events),
                )

        receiver = self._character_by_key(receiver_key)
        if receiver_key != target_key and self._damage_is_immune(receiver_key, immune_character_keys):
            events.append(f"{receiver.name} 免疫了 {base_damage} 点伤害。")
            return DamageResult(
                requested_target_name=requested_target.name,
                receiver_name=receiver.name,
                damage=0,
                receiver_key=receiver_key,
                events=tuple(events),
            )

        damage = base_damage
        if receiver.has_status_effect("bleeding"):
            bleeding_bonus = self._percentage_damage(base_damage, 50)
            damage += bleeding_bonus
            receiver.remove_status_effect("bleeding")
            events.append(f"{receiver.name} 的流血使伤害 +{bleeding_bonus}。")

        damage_taken_bonus = self.round_damage_taken_bonus.get(receiver_key, 0)
        if damage_taken_bonus > 0:
            damage += damage_taken_bonus
            events.append(f"{receiver.name} 受伤 +{damage_taken_bonus}。")

        source = self._character_by_key(source_key)
        damage_before_reductions = damage
        if (
            damage_before_reductions > 0
            and self._character_has_battle_effect(receiver_key, "damage_reduction_vs_enraged_50")
            and source.has_status_effect("enraged")
            and self.enrage_sources.get(source_key) == receiver_key
        ):
            reduction = self._percentage_damage(damage_before_reductions, 50)
            reduced_damage = max(0, damage - reduction)
            if reduced_damage != damage:
                events.append(f"{receiver.name} 受到激怒角色的伤害 -50%。")
            damage = reduced_damage

        if damage_before_reductions > 0 and self._character_has_battle_effect(receiver_key, "damage_reduction_50"):
            reduction = self._percentage_damage(damage_before_reductions, 50)
            reduced_damage = max(0, damage - reduction)
            if reduced_damage != damage:
                events.append(f"{receiver.name} 受伤 -50%。")
            damage = reduced_damage

        if self._character_has_battle_effect(receiver_key, "damage_reduction_1"):
            reduced_damage = max(0, damage - 1)
            if reduced_damage != damage:
                events.append(f"{receiver.name} 受伤 -1。")
            damage = reduced_damage

        if damage > 0 and receiver.has_status_effect("next_damage_reduction_4"):
            reduced_damage = max(0, damage - 4)
            receiver.remove_status_effect("next_damage_reduction_4")
            events.append(f"{receiver.name} 下次受伤 -4。")
            damage = reduced_damage

        if damage_before_reductions > 0 and self._has_other_ally_effect(receiver_key, "eternal_ally_damage_reduction_1"):
            reduced_damage = max(1, damage - 1)
            if reduced_damage != damage:
                events.append(f"{receiver.name} 受伤 -1。")
            damage = reduced_damage

        if (
            damage > 0
            and self._character_has_battle_effect(source_key, "kill_only_dragon")
            and not self._is_dragon_character(receiver_key)
            and receiver.current_health + receiver.armor <= damage
        ):
            damage = max(0, receiver.current_health + receiver.armor - 1)
            events.append(f"{source.name} 无法杀死非龙角色。")

        if (
            damage > 0
            and self._character_has_battle_effect(receiver_key, "first_fatal_immunity")
            and not receiver.has_used_passive_effect("first_fatal_immunity")
            and receiver.current_health + receiver.armor <= damage
        ):
            receiver.mark_passive_effect_used("first_fatal_immunity")
            events.append(f"{receiver.name} 免疫了首次致命伤害。")
            return DamageResult(
                requested_target_name=requested_target.name,
                receiver_name=receiver.name,
                damage=0,
                receiver_key=receiver_key,
                events=tuple(events),
            )

        was_undying = self._character_has_battle_effect(receiver_key, "undying")
        armor_before = receiver.armor
        receiver.take_damage(damage)
        if damage > 0 and not receiver.is_alive and was_undying:
            receiver.current_health = 1
            events.append(f"{receiver.name} 的不死使其保留 1 点生命。")
        if damage > 0:
            self.action_damage_events.append(DamageEvent(receiver_key[0], receiver_key[1], damage, critical=critical))
            self.last_damage_sources[receiver_key] = source_key
            events.extend(self._resolve_damage_dealt_triggers(source_key, receiver_key, damage))
        armor_absorbed = armor_before - receiver.armor
        if armor_absorbed > 0:
            events.append(f"{receiver.name} 的护甲吸收 {armor_absorbed} 点伤害。")
        self._refresh_aura_health_bonuses()
        if receiver.is_alive and receiver.has_status_effect("cursed") and self._resolve_curse_for_key(receiver_key, source_key):
            events.append(f"{receiver.name} 触发诅咒死亡。")
        return DamageResult(
            requested_target_name=requested_target.name,
            receiver_name=receiver.name,
            damage=damage,
            receiver_key=receiver_key,
            events=tuple(events),
        )

    def _resolve_damage_dealt_triggers(
        self,
        source_key: tuple[int, str],
        receiver_key: tuple[int, str],
        damage: int,
    ) -> list[str]:
        events: list[str] = []
        receiver = self._character_by_key(receiver_key)
        if receiver.is_alive and self._character_has_battle_effect(receiver_key, "attack_gain_when_damaged"):
            receiver.attack += damage
            events.append(f"{receiver.name} 受伤后攻击力 +{damage}。")

        if receiver.is_alive and self._character_has_battle_effect(receiver_key, "gain_shield_when_damaged"):
            stacks = self._gain_shield(receiver_key)
            events.append(f"{receiver.name} 受伤后获得一层护盾，当前 {stacks} 层。")

        source = self._character_by_key(source_key)
        if not self._character_has_battle_effect(source_key, "damage_threshold_attack_buff"):
            return events

        trigger_count = self.damage_threshold_trigger_counts.get(source_key, 0)
        if trigger_count >= 2:
            return events

        total = self.damage_threshold_totals.get(source_key, 0) + damage
        while total >= 6 and trigger_count < 2:
            total -= 6
            trigger_count += 1
            self.pending_death_triggers.append(
                DeathTrigger(
                    player_id=source_key[0],
                    character_id=source_key[1],
                    character_name=source.name,
                    damage=0,
                    kind="damage_prophecy",
                    attack_bonus=3,
                )
            )
            events.append(f"{source.name} 累计造成6点伤害，可以使一名角色攻击力 +3。")
        self.damage_threshold_totals[source_key] = total
        self.damage_threshold_trigger_counts[source_key] = trigger_count
        if self.current_death_trigger() is not None:
            self.game_state.current_turn_player_id = self.current_death_trigger().player_id
        return events

    def _damage_is_immune(
        self,
        character_key: tuple[int, str],
        immune_character_keys: Sequence[tuple[int, str]],
    ) -> bool:
        return character_key in set(immune_character_keys) or self._character_has_battle_effect(character_key, "immunity")

    def _guard_receiver_key(
        self,
        moving_player_id: int,
        target_key: tuple[int, str],
    ) -> tuple[int, str] | None:
        receiver_keys = self._guard_receiver_keys(moving_player_id, target_key)
        return receiver_keys[0] if receiver_keys else None

    def _guard_receiver_keys(
        self,
        moving_player_id: int,
        target_key: tuple[int, str],
    ) -> list[tuple[int, str]]:
        target_player_id, target_id = target_key
        target = self.game_state.player(target_player_id).get_character(target_id)
        if target.position is None:
            return []

        receiver_keys: list[tuple[int, str]] = []
        for player_id, character in self._ordered_battle_character_refs(moving_player_id):
            if player_id != target_player_id:
                continue
            if character.id == target.id:
                continue
            if not character.is_alive or character.position is None:
                continue
            character_key = (player_id, character.id)
            guards_all = self._character_has_battle_effect(character_key, "guard_all_allies")
            guards_adjacent = self._character_has_battle_effect(character_key, "guard_adjacent") and self._is_adjacent(
                character.position,
                target.position,
            )
            guards_same_rank = (
                self._character_has_battle_effect(character_key, "guard_same_rank")
                and character.position.column == target.position.column
            )
            if not (guards_all or guards_adjacent or guards_same_rank):
                continue
            receiver_keys.append(character_key)

        return receiver_keys

    def team_barrier_amount(self, player_id: int) -> int:
        return max(0, self.team_barriers.get(player_id, 0))

    def _resolve_team_barrier_damage(self, target_key: tuple[int, str], base_damage: int) -> DamageResult | None:
        target_player_id, _target_id = target_key
        barrier_amount = self.team_barrier_amount(target_player_id)
        if base_damage <= 0 or barrier_amount <= 0:
            return None

        target = self._character_by_key(target_key)
        absorbed = min(barrier_amount, base_damage)
        overflow = max(0, base_damage - barrier_amount)
        remaining = max(0, barrier_amount - base_damage)
        if remaining > 0:
            self.team_barriers[target_player_id] = remaining
        else:
            self.team_barriers.pop(target_player_id, None)

        if overflow > 0:
            event = f"屏障为 {target.name} 承受 {absorbed} 点伤害，并抵消 {overflow} 点溢出伤害，剩余 0。"
        else:
            event = f"屏障为 {target.name} 抵消 {base_damage} 点伤害，剩余 {remaining}。"
        events = [event]
        if remaining == 0:
            events.extend(self._resolve_team_barrier_break_damage(target_player_id, target_key))
        return DamageResult(
            requested_target_name=target.name,
            receiver_name=target.name,
            damage=0,
            receiver_key=target_key,
            events=tuple(events),
        )

    def _resolve_team_barrier_break_damage(
        self,
        player_id: int,
        fallback_source_key: tuple[int, str],
    ) -> list[str]:
        source_key = self.team_barrier_sources.pop(player_id, None) or fallback_source_key
        events = ["屏障被击破，对所有友方角色造成1点伤害。"]
        for ally in list(self._battle_characters(player_id)):
            if not ally.is_alive:
                continue
            damage_result = self._resolve_damage(
                moving_player_id=player_id,
                source_key=source_key,
                target_key=(player_id, ally.id),
                base_damage=1,
                immune_character_keys=(),
                allow_guard=True,
            )
            events.append(f"{ally.name} 受到屏障破裂 {damage_result.damage} 点。")
            events.extend(damage_result.events)
        return events

    def _target_cannot_be_guarded(self, target_key: tuple[int, str]) -> bool:
        return self._character_has_battle_effect(target_key, "cannot_be_guarded")

    def _target_has_taunt_effect(self, target_key: tuple[int, str]) -> bool:
        return (
            self._character_has_battle_effect(target_key, "row_taunt")
            or self._character_has_battle_effect(target_key, "all_taunt")
        )

    def _can_manually_select_target(self, selecting_player_id: int, target_key: tuple[int, str]) -> bool:
        target_player_id, _target_id = target_key
        if self._character_has_battle_effect(target_key, "unselectable"):
            return False
        if target_player_id == selecting_player_id:
            return True
        return not self._character_has_battle_effect(target_key, "stealth")

    def _apply_attack_taunt(
        self,
        attacker_player_id: int,
        defender_player_id: int,
        candidates: list[Character],
    ) -> list[Character]:
        if not candidates:
            return []

        all_taunters = [
            character
            for character in self._battle_characters(defender_player_id)
            if character.is_alive
            and character.position is not None
            and self._can_manually_select_target(attacker_player_id, (defender_player_id, character.id))
            and self._character_has_battle_effect((defender_player_id, character.id), "all_taunt")
        ]

        row_taunters: dict[FormationColumn, list[Character]] = {}
        for character in self._battle_characters(defender_player_id):
            if (
                character.is_alive
                and character.position is not None
                and self._can_manually_select_target(attacker_player_id, (defender_player_id, character.id))
                and self._character_has_battle_effect((defender_player_id, character.id), "row_taunt")
            ):
                row_taunters.setdefault(character.position.column, []).append(character)

        filtered: list[Character] = []
        seen_ids: set[str] = set()
        for taunter in all_taunters:
            filtered.append(taunter)
            seen_ids.add(taunter.id)
        for candidate in candidates:
            if candidate.position is None:
                continue

            row_guardians = row_taunters.get(candidate.position.column)
            if row_guardians:
                replacement_candidates = row_guardians
            elif not all_taunters:
                replacement_candidates = [candidate]
            else:
                replacement_candidates = []

            for replacement in replacement_candidates:
                if replacement.id not in seen_ids:
                    filtered.append(replacement)
                    seen_ids.add(replacement.id)

        return filtered if filtered else candidates

    def _reflect_percent_for_attack(
        self,
        attacker_key: tuple[int, str],
        target_key: tuple[int, str],
        extra_target_reflect_percent: int = 0,
    ) -> int:
        percent = 0
        if self._target_effect_active_for_attack(target_key, "reflect_100"):
            percent += 100
        if self._target_effect_active_for_attack(target_key, "reflect_50"):
            percent += 50
        if self._character_has_battle_effect(attacker_key, "target_gain_reflect_50"):
            percent += 50
        percent += self.gravity_stack_count(attacker_key) * 50
        percent += extra_target_reflect_percent
        return percent

    def _target_effect_active_for_attack(self, target_key: tuple[int, str], effect_id: str) -> bool:
        target = self._character_by_key(target_key)
        if target_key in self.suppressed_bonus_character_keys and not is_adverse_status_effect(effect_id):
            return False
        if effect_id in target.job.effect_ids:
            return True
        if target.has_status_effect("silenced") and effect_id not in ("silenced", "silence_immunity"):
            return False
        return effect_id in target.status_effect_ids or effect_id in target.effective_passive_effect_ids

    def _attack_immune_keys(
        self,
        attacker_key: tuple[int, str],
        target_key: tuple[int, str],
    ) -> tuple[tuple[int, str], ...]:
        suppress_attack_immunity = (
            self._character_has_battle_effect(attacker_key, "wolf_target_critical_else_no_attack_immunity")
            and not self._is_wolf_character(target_key)
        )
        if self._character_has_battle_effect(attacker_key, "attack_immunity") and not suppress_attack_immunity:
            return (attacker_key,)
        if (
            self._character_has_battle_effect(attacker_key, "conditional_attack_immunity")
            and self.effective_attack(target_key, attacker_key) <= self.effective_attack(attacker_key, target_key)
        ):
            return (attacker_key,)
        return ()

    def _attack_is_critical(self, attacker_key: tuple[int, str], target_key: tuple[int, str]) -> bool:
        if (
            self._character_has_battle_effect(attacker_key, "wolf_target_critical_else_no_attack_immunity")
            and self._is_wolf_character(target_key)
        ):
            return True
        target = self._character_by_key(target_key)
        if self._character_has_battle_effect(attacker_key, "critical_vs_bleeding") and target.has_status_effect("bleeding"):
            return True
        if self._character_has_battle_effect(attacker_key, "critical_when_damaged"):
            attacker = self._character_by_key(attacker_key)
            if attacker.current_health < attacker.max_health:
                return True
        return (
            self._character_has_battle_effect(attacker_key, "critical_vs_uninjured")
            and target.current_health == target.max_health
        )

    def current_sword_saint_choice(self) -> tuple[int, str] | None:
        if not self.pending_sword_saint_choices:
            return None
        return self.pending_sword_saint_choices[0]

    def current_chase_choice(self) -> tuple[tuple[int, str], tuple[int, str]] | None:
        if not self.pending_chase_choices:
            return None
        return self.pending_chase_choices[0]

    def sword_saint_choice_options(self) -> tuple[str, ...]:
        choice_key = self.current_sword_saint_choice()
        if choice_key is None:
            return ()
        options = ["heal"]
        if self.sword_saint_inspire_counts.get(choice_key, 0) < 4:
            options.insert(0, "inspire")
        return tuple(options)

    def can_resolve_sword_saint_choice(self, option: str) -> bool:
        choice_key = self.current_sword_saint_choice()
        if self.game_state.phase != GamePhase.BATTLE or choice_key is None:
            return False
        if self.pending_death_triggers or self.pending_summons:
            return False
        if option not in self.sword_saint_choice_options():
            return False
        return bool(self._sword_saint_warrior_keys(choice_key))

    def resolve_sword_saint_choice(self, option: str) -> SwordSaintChoiceResult:
        if not self.can_resolve_sword_saint_choice(option):
            raise BattleError("Invalid sword saint choice.")

        attacker_key = self.pending_sword_saint_choices.pop(0)
        attacker = self._character_by_key(attacker_key)
        warrior_keys = self._sword_saint_warrior_keys(attacker_key)
        events: list[str] = []
        choice_name = "鼓舞"

        if option == "inspire":
            for warrior_key in warrior_keys:
                warrior = self._character_by_key(warrior_key)
                warrior.attack += 1
                warrior.gain_health(1)
            self.sword_saint_inspire_counts[attacker_key] = self.sword_saint_inspire_counts.get(attacker_key, 0) + 1
            events.append(f"{attacker.name} 鼓舞所有友方战士 +1生命与 +1攻击。")
        else:
            choice_name = "恢复"
            healed_names: list[str] = []
            for warrior_key in warrior_keys:
                warrior = self._character_by_key(warrior_key)
                before = warrior.current_health
                warrior.heal(3)
                healed_names.append(f"{warrior.name}+{warrior.current_health - before}")
            events.append(f"{attacker.name} 使友方战士恢复：{'、'.join(healed_names)}。")

        winner_player_id = self._finish_after_pending_manual_choice(attacker_key[0])
        return SwordSaintChoiceResult(
            source_name=attacker.name,
            choice_name=choice_name,
            winner_player_id=winner_player_id,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
            events=tuple(events),
        )

    def chase_targets(self) -> list[Character]:
        chase_choice = self.current_chase_choice()
        if chase_choice is None:
            return []
        attacker_key, target_key = chase_choice
        return [self._character_by_key(chase_key) for chase_key in self._chase_target_keys(attacker_key, target_key)]

    def can_resolve_chase_target(self, target_id: str | None = None) -> bool:
        if self.game_state.phase != GamePhase.BATTLE:
            return False
        if self.pending_death_triggers or self.pending_summons:
            return False
        if self.current_chase_choice() is None:
            return False
        if target_id is None:
            return bool(self.chase_targets())
        return any(target.id == target_id for target in self.chase_targets())

    def resolve_chase_target(self, target_id: str) -> ChaseResult:
        if not self.can_resolve_chase_target(target_id):
            raise BattleError("Invalid chase target.")

        self.action_damage_events.clear()
        attacker_key, original_target_key = self.pending_chase_choices.pop(0)
        attacker = self._character_by_key(attacker_key)
        chase_key = next(
            chase_key
            for chase_key in self._chase_target_keys(attacker_key, original_target_key)
            if chase_key[1] == target_id
        )
        chase_target = self._character_by_key(chase_key)
        alive_before = self._living_character_keys()
        chase_damage = self._percentage_damage(self.effective_attack(attacker_key, chase_key), 50)
        damage_result = self._resolve_damage(
            moving_player_id=attacker_key[0],
            source_key=attacker_key,
            target_key=chase_key,
            base_damage=chase_damage,
            immune_character_keys=(),
            allow_guard=True,
        )
        events = [f"{attacker.name} 追击 {chase_target.name}，造成 {damage_result.damage} 点。", *damage_result.events]
        defeated_character_keys = self._newly_defeated_keys(alive_before)
        events.extend(self._queue_death_triggers(defeated_character_keys))
        defeated_character_names = self._newly_defeated_names(attacker_key[0], alive_before)

        winner_player_id = self._finish_after_pending_manual_choice(attacker_key[0])
        return ChaseResult(
            source_name=attacker.name,
            target_name=chase_target.name,
            damage=damage_result.damage,
            winner_player_id=winner_player_id,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
            actual_target_name=damage_result.receiver_name,
            defeated_character_names=tuple(defeated_character_names),
            events=tuple(events),
            damage_events=tuple(self.action_damage_events),
        )

    def _sword_saint_warrior_keys(self, attacker_key: tuple[int, str]) -> list[tuple[int, str]]:
        return [
            (attacker_key[0], ally.id)
            for ally in self._battle_characters(attacker_key[0])
            if ally.is_alive and self._character_counts_as_job((attacker_key[0], ally.id), "warrior")
        ]

    def _chase_target_keys(self, attacker_key: tuple[int, str], target_key: tuple[int, str]) -> list[tuple[int, str]]:
        attacker = self._character_by_key(attacker_key)
        target = self._character_by_key(target_key)
        if not attacker.is_alive or target.position is None:
            return []

        opponent_id = target_key[0]
        candidate_keys = [target_key]
        candidate_keys.extend(self._adjacent_character_keys(opponent_id, target.position, exclude_id=target.id))
        return [
            candidate_key
            for candidate_key in dict.fromkeys(candidate_keys)
            if self._character_by_key(candidate_key).is_alive
            and self._can_manually_select_target(attacker_key[0], candidate_key)
        ]

    def _set_current_player_for_pending_manual_choice(self) -> None:
        sword_choice = self.current_sword_saint_choice()
        if sword_choice is not None:
            self.game_state.current_turn_player_id = sword_choice[0]
            return
        chase_choice = self.current_chase_choice()
        if chase_choice is not None:
            self.game_state.current_turn_player_id = chase_choice[0][0]

    def _finish_after_pending_manual_choice(self, acting_player_id: int | None) -> int | None:
        if self.pending_death_triggers:
            next_trigger = self.current_death_trigger()
            if next_trigger is not None:
                self.game_state.current_turn_player_id = next_trigger.player_id
            return None
        if self.pending_summons:
            next_summon = self.current_summon_request()
            if next_summon is not None:
                self.game_state.current_turn_player_id = next_summon.player_id
            return None
        if self._has_pending_manual_choice():
            self._set_current_player_for_pending_manual_choice()
            return None
        if self.pending_followup_attack is not None:
            return self._resume_or_finish_pending_followup()

        post_action_player_id = self.pending_post_action_player_id
        self.pending_post_action_player_id = None
        winner_player_id = self._check_winner()
        if winner_player_id is None:
            player_to_advance = post_action_player_id if post_action_player_id is not None else acting_player_id
            if player_to_advance is not None:
                self._advance_turn_after_action(player_to_advance)
        return winner_player_id

    def _player_has_frontline_taunt_aura(self, player_id: int) -> bool:
        return any(
            character.is_alive
            and self._character_has_battle_effect((player_id, character.id), "frontline_taunt_aura")
            for character in self._battle_characters(player_id)
        )

    def _player_positions_count_as_front(self, player_id: int) -> bool:
        return any(
            self._character_has_battle_effect((player_id, character.id), "all_positions_front")
            for character in self._battle_characters(player_id)
        )

    def _resolve_adjacent_rank_splash(
        self,
        *,
        attacker_key: tuple[int, str],
        target_key: tuple[int, str],
        moving_player_id: int,
    ) -> list[str]:
        if not self._character_has_battle_effect(attacker_key, "adjacent_rank_splash_1"):
            return []
        target = self._character_by_key(target_key)
        if target.position is None:
            return []

        events: list[str] = []
        for splash_key in self._same_column_adjacent_character_keys(target_key[0], target.position, exclude_id=target.id):
            splash_target = self._character_by_key(splash_key)
            damage_result = self._resolve_damage(
                moving_player_id=moving_player_id,
                source_key=attacker_key,
                target_key=splash_key,
                base_damage=1,
                immune_character_keys=(),
                allow_guard=True,
            )
            events.append(f"{splash_target.name} 受到左右溅射 {damage_result.damage} 点。")
            events.extend(damage_result.events)
        return events

    def _resolve_thunder_damage(
        self,
        *,
        attacker_key: tuple[int, str],
        target_key: tuple[int, str],
        moving_player_id: int,
    ) -> tuple[int, list[str]]:
        if not self._character_has_battle_effect(attacker_key, "thunder_attack"):
            return 0, []
        target = self._character_by_key(target_key)
        if target.position is None:
            return 0, []

        total_damage = 0
        events: list[str] = []
        for thunder_key in self._same_rank_character_keys(target_key[0], target.position.column):
            thunder_target = self._character_by_key(thunder_key)
            thunder_damage = self._percentage_damage(thunder_target.max_health, 25)
            damage_result = self._resolve_damage(
                moving_player_id=moving_player_id,
                source_key=attacker_key,
                target_key=thunder_key,
                base_damage=thunder_damage,
                immune_character_keys=(),
                allow_guard=True,
            )
            total_damage += damage_result.damage
            events.append(f"{thunder_target.name} 受到雷鸣 {damage_result.damage} 点。")
            events.extend(damage_result.events)
        return total_damage, events

    def _percentage_damage(self, amount: int, percent: int) -> int:
        if amount <= 0 or percent <= 0:
            return 0
        return (amount * percent + 99) // 100
