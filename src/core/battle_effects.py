from __future__ import annotations

from collections.abc import Sequence

from src.core.battle_errors import BattleError
from src.core.battle_results import (
    AttackResolution,
    AttackResult,
    DamageResult,
    DeathTrigger,
    DeathTriggerResult,
    EndRoundResult,
    RelocateResult,
    SecondHandResult,
    SkillResult,
    SkipResult,
    SummonRequest,
    SummonResult,
    ThawResult,
)
from src.core.models import ActiveSkill, Character, FormationColumn, GamePhase, Position, SkillKind, SkillTarget
from src.core.rules import effect_display_name, is_adverse_status_effect


class BattleEffectMixin:
    def current_death_trigger(self) -> DeathTrigger | None:
        if not self.pending_death_triggers:
            return None
        return self.pending_death_triggers[0]

    def death_trigger_targets(self) -> list[Character]:
        trigger = self.current_death_trigger()
        if trigger is None:
            return []
        if trigger.kind == "mirror_copy":
            return [
                character
                for character in self._battle_characters(trigger.player_id)
                if character.id != trigger.character_id
                and character.is_alive
                and self._can_manually_select_target(trigger.player_id, (trigger.player_id, character.id))
            ]
        if trigger.kind == "heal_ally":
            return [
                character
                for character in self._battle_characters(trigger.player_id)
                if character.is_alive and self._can_manually_select_target(trigger.player_id, (trigger.player_id, character.id))
            ]
        return [
            character
            for player_id in self.game_state.players
            for character in self._battle_characters(player_id)
            if character.is_alive and self._can_manually_select_target(trigger.player_id, (player_id, character.id))
        ]

    def can_resolve_death_trigger(self, target_id: str | None = None) -> bool:
        if self.game_state.phase != GamePhase.BATTLE:
            return False
        if not self.pending_death_triggers:
            return False
        if target_id is None:
            if self.pending_death_triggers[0].kind == "mirror_copy":
                return False
            return True
        return any(character.id == target_id for character in self.death_trigger_targets())

    def resolve_death_trigger(self, target_id: str | None = None) -> DeathTriggerResult:
        if not self.can_resolve_death_trigger(target_id):
            raise BattleError("Invalid death trigger target.")

        self.action_damage_events.clear()
        trigger = self.pending_death_triggers.pop(0)
        alive_before = self._living_character_keys()
        events: list[str] = []
        damage = 0
        target_name = ""
        actual_target_name = ""
        skipped = target_id is None

        if skipped:
            action_text_by_kind = {
                "damage": "死亡追击",
                "attack_buff": "死亡预言",
                "damage_prophecy": "伤害预言",
                "heal": "攻击后治疗",
                "heal_ally": "攻击后治疗",
                "mirror_copy": "镜像复制",
            }
            action_text = action_text_by_kind.get(trigger.kind, "强制结算")
            events.append(f"{trigger.character_name} 跳过{action_text}。")
        else:
            target_key = self._any_living_character_key(target_id)
            target = self._character_by_key(target_key)
            target_name = target.name
            if trigger.kind == "mirror_copy":
                mirror = self._character_by_key((trigger.player_id, trigger.character_id))
                self._copy_character_skills(mirror, target)
                mirror.mark_passive_effect_used("battle_start_copy_ally_skills")
                actual_target_name = target.name
                events.append(f"{mirror.name} 复制了 {target.name} 的技能。")
            elif trigger.kind in ("attack_buff", "damage_prophecy"):
                target.attack += trigger.attack_bonus
                actual_target_name = target.name
                events.append(f"{target.name} 攻击力 +{trigger.attack_bonus}。")
            elif trigger.kind in ("heal", "heal_ally"):
                before_health = target.current_health
                target.heal(trigger.damage)
                healed = target.current_health - before_health
                actual_target_name = target.name
                events.append(f"{target.name} 恢复 {healed} 点生命。")
            else:
                damage_result = self._resolve_damage(
                    moving_player_id=trigger.player_id,
                    source_key=(trigger.player_id, trigger.character_id),
                    target_key=target_key,
                    base_damage=trigger.damage,
                    immune_character_keys=(),
                    allow_guard=True,
                )
                damage = damage_result.damage
                actual_target_name = damage_result.receiver_name
                events.extend(damage_result.events)

        defeated_character_keys = self._newly_defeated_keys(alive_before)
        events.extend(self._queue_death_triggers(defeated_character_keys))
        defeated_character_names = self._newly_defeated_names(trigger.player_id, alive_before)

        winner_player_id = None
        if not self.pending_death_triggers:
            if self.pending_summons:
                summon = self.current_summon_request()
                if summon is not None:
                    self.game_state.current_turn_player_id = summon.player_id
            elif self._has_pending_manual_choice():
                self._set_current_player_for_pending_manual_choice()
            elif self.pending_followup_attack is not None:
                winner_player_id = self._resume_or_finish_pending_followup()
            else:
                acting_player_id = self.pending_post_action_player_id
                self.pending_post_action_player_id = None
                winner_player_id = self._check_winner()
                if winner_player_id is None and acting_player_id is not None:
                    self._advance_turn_after_action(acting_player_id)
                elif winner_player_id is None and trigger.kind == "mirror_copy":
                    self.game_state.current_turn_player_id = self._next_player_with_moves(self.first_player_id)
        else:
            next_trigger = self.current_death_trigger()
            if next_trigger is not None:
                self.game_state.current_turn_player_id = next_trigger.player_id

        return DeathTriggerResult(
            source_name=trigger.character_name,
            target_name=target_name,
            damage=damage,
            skipped=skipped,
            winner_player_id=winner_player_id,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
            actual_target_name=actual_target_name,
            defeated_character_names=tuple(defeated_character_names),
            events=tuple(events),
            damage_events=tuple(self.action_damage_events),
        )

    def summon_positions(self, player_id: int) -> list[Position]:
        return [
            Position(row=row, column=column)
            for row in range(3)
            for column in (FormationColumn.BACK, FormationColumn.FRONT)
            if self.game_state.player(player_id).character_at(Position(row=row, column=column)) is None
        ]

    def can_resolve_summon(self, position: Position | None = None) -> bool:
        summon = self.current_summon_request()
        if self.game_state.phase != GamePhase.BATTLE or summon is None:
            return False
        if self.pending_death_triggers:
            return False
        if position is None:
            return bool(self.summon_positions(summon.player_id))
        return position in self.summon_positions(summon.player_id)

    def resolve_summon(self, position: Position) -> SummonResult:
        if not self.can_resolve_summon(position):
            raise BattleError("Invalid summon position.")

        summon = self.pending_summons.pop(0)
        character = self._create_summoned_character(summon.character_definition_id, summon.player_id)
        self.game_state.player(summon.player_id).add_character(character)
        self.game_state.player(summon.player_id).place_character(character.id, position)
        self.remaining_moves[(summon.player_id, character.id)] = character.default_move_count
        self._refresh_aura_health_bonuses()
        events = [f"{summon.source_name} 召唤了 {character.name}。"]
        summoned_key = (summon.player_id, character.id)

        winner_player_id = None
        if self.pending_summons:
            next_summon = self.current_summon_request()
            if next_summon is not None:
                self.game_state.current_turn_player_id = next_summon.player_id
        elif summon.character_definition_id == "tentacle" and self.remaining_moves.get(summoned_key, 0) > 0:
            self.pending_post_action_player_id = None
            self.game_state.current_turn_player_id = summon.player_id
        elif self._has_pending_manual_choice():
            self._set_current_player_for_pending_manual_choice()
        elif self.pending_followup_attack is not None:
            winner_player_id = self._resume_or_finish_pending_followup()
        else:
            acting_player_id = self.pending_post_action_player_id
            self.pending_post_action_player_id = None
            winner_player_id = self._check_winner()
            if winner_player_id is None and acting_player_id is not None:
                self._advance_turn_after_action(acting_player_id)

        return SummonResult(
            source_name=summon.source_name,
            summoned_name=character.name,
            position=position,
            winner_player_id=winner_player_id,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
            events=tuple(events),
        )

    def _apply_battle_start_passives(self) -> None:
        for player_id in self.game_state.players:
            battle_characters = self._battle_characters(player_id)
            if not battle_characters:
                continue
            for character in battle_characters:
                character_key = (player_id, character.id)
                if (
                    self._character_has_battle_effect(character_key, "magic_guard_start_guardian")
                    and not character.has_used_passive_effect("magic_guard_start_guardian")
                ):
                    arcane_count = sum(
                        1
                        for ally in battle_characters
                        if self._character_counts_as_job((player_id, ally.id), "arcane")
                    )
                    if arcane_count >= 2:
                        from src.data.jobs import JOBS_BY_ID

                        character.gain_health(4)
                        character.job = JOBS_BY_ID["guardian"]
                        character.mark_passive_effect_used("magic_guard_start_guardian")
                if (
                    self._character_has_battle_effect(character_key, "arcane_start_attack_bonus")
                    and not character.has_used_passive_effect("arcane_start_attack_bonus")
                ):
                    arcane_count = sum(
                        1
                        for ally in battle_characters
                        if self._character_counts_as_job((player_id, ally.id), "arcane")
                    )
                    if arcane_count:
                        character.attack += arcane_count * 2
                        character.mark_passive_effect_used("arcane_start_attack_bonus")
            for character in battle_characters:
                character_key = (player_id, character.id)
                if self._character_has_battle_effect(character_key, "wolf_statue_health_bonus"):
                    wolf_count = sum(
                        1
                        for ally in battle_characters
                        if ally.id != character.id and "狼" in ally.factions
                    )
                    if wolf_count and not character.has_used_passive_effect("wolf_statue_health_bonus"):
                        character.gain_health(wolf_count * 2)
                        character.mark_passive_effect_used("wolf_statue_health_bonus")
            all_wolf = all("狼" in character.factions for character in battle_characters)
            if not all_wolf:
                continue
            for character in battle_characters:
                if "all_wolf_attack_bonus" not in character.effective_passive_effect_ids:
                    continue
                if character.has_used_passive_effect("all_wolf_attack_bonus"):
                    continue
                character.attack += 2
                character.mark_passive_effect_used("all_wolf_attack_bonus")

        for player_id in self.game_state.players:
            for character in self._battle_characters(player_id):
                character_key = (player_id, character.id)
                if not self._character_has_battle_effect(character_key, "battle_start_copy_ally_skills"):
                    continue
                if character.has_used_passive_effect("battle_start_copy_ally_skills"):
                    continue
                if not self._mirror_copy_targets(player_id, character.id):
                    continue
                self.pending_death_triggers.append(
                    DeathTrigger(
                        player_id=player_id,
                        character_id=character.id,
                        character_name=character.name,
                        damage=0,
                        kind="mirror_copy",
                    )
                )

    def _mirror_copy_targets(self, player_id: int, character_id: str) -> list[Character]:
        return [
            ally
            for ally in self._battle_characters(player_id)
            if ally.id != character_id
            and ally.is_alive
            and ally.position is not None
            and self._can_manually_select_target(player_id, (player_id, ally.id))
        ]

    def _copy_character_skills(self, receiver: Character, source: Character) -> None:
        receiver.passive_effect_ids = tuple(
            dict.fromkeys((*receiver.passive_effect_ids, *source.passive_effect_ids))
        )
        receiver.active_effect_ids = tuple(
            dict.fromkeys((*receiver.active_effect_ids, *source.active_effect_ids))
        )
        receiver.active_skills = tuple(dict.fromkeys((*receiver.active_skills, *source.active_skills)))

    def _character_has_battle_effect(self, character_key: tuple[int, str], effect_id: str) -> bool:
        character = self._character_by_key(character_key)
        if not character.is_alive:
            return False
        if effect_id == "undying" and character_key in self.temporary_undying_character_keys:
            return True
        if character_key in self.suppressed_bonus_character_keys and not is_adverse_status_effect(effect_id):
            return False
        if effect_id in character.job.effect_ids:
            return True
        if character.has_status_effect("silenced") and effect_id not in ("silenced", "silence_immunity"):
            return False
        if effect_id in character.status_effect_ids:
            return True
        if effect_id in character.effective_passive_effect_ids:
            return True
        if effect_id in ("unselectable", "immunity", "undying") and self._has_lone_wolf_survivor_state(character_key):
            return True
        if effect_id == "backline_attack" and self._has_same_row_backline_aura(character_key):
            return True
        if effect_id == "stealth" and self._has_executor_stealth_aura(character_key):
            return True
        if effect_id == "attack_immunity" and self._has_executor_attack_immunity_aura(character_key):
            return True
        if effect_id == "immunity" and self._has_ally_immunity_aura(character_key):
            return True
        return False

    def _is_adverse_status_effect_for_character(self, effect_id: str, character_key: tuple[int, str]) -> bool:
        if not is_adverse_status_effect(effect_id):
            return False
        if effect_id == "bleeding" and self._has_enemy_bleeding_nonadverse_aura(character_key):
            return False
        return True

    def _has_enemy_bleeding_nonadverse_aura(self, character_key: tuple[int, str]) -> bool:
        player_id, _character_id = character_key
        opponent_id = self.game_state.opponent_id(player_id)
        return any(
            enemy.is_alive
            and self._character_has_battle_effect((opponent_id, enemy.id), "enemy_bleeding_not_adverse")
            for enemy in self._battle_characters(opponent_id)
        )

    def _enraged_forced_target_key(self, character_key: tuple[int, str]) -> tuple[int, str] | None:
        character = self._character_by_key(character_key)
        if not character.is_alive or not character.has_status_effect("enraged"):
            return None
        source_key = self.enrage_sources.get(character_key)
        if source_key is None:
            return None
        try:
            source = self._character_by_key(source_key)
        except KeyError:
            return None
        if not source.is_alive or source.position is None:
            return None
        return source_key

    def _has_lone_wolf_survivor_state(self, character_key: tuple[int, str]) -> bool:
        player_id, character_id = character_key
        character = self._character_by_key(character_key)
        if "lone_wolf_survivor" not in character.effective_passive_effect_ids:
            return False
        if not character.is_alive or character.position is None:
            return False
        for ally in self._battle_characters(player_id):
            if ally.id == character_id or not ally.is_alive or ally.position is None:
                continue
            if not self._character_has_battle_effect((player_id, ally.id), "stealth"):
                return True
        return False

    def _has_executor_stealth_aura(self, character_key: tuple[int, str]) -> bool:
        player_id, character_id = character_key
        character = self._character_by_key(character_key)
        if character.job.id != "executor":
            return False

        for ally in self._battle_characters(player_id):
            if ally.id == character_id or not ally.is_alive or ally.position is None:
                continue
            if self._character_has_battle_effect((player_id, ally.id), "executor_stealth_aura"):
                return True
        return False

    def _has_executor_attack_immunity_aura(self, character_key: tuple[int, str]) -> bool:
        player_id, character_id = character_key
        character = self._character_by_key(character_key)
        if character.job.id != "executor":
            return False

        for ally in self._battle_characters(player_id):
            if ally.id == character_id or not ally.is_alive or ally.position is None:
                continue
            if self._character_has_battle_effect((player_id, ally.id), "executor_attack_immunity_aura"):
                return True
        return False

    def _has_ally_immunity_aura(self, character_key: tuple[int, str]) -> bool:
        if self.game_state.round_number != 1:
            return False
        player_id, character_id = character_key
        for ally in self._battle_characters(player_id):
            if ally.id == character_id or not ally.is_alive or ally.position is None:
                continue
            if self._character_has_battle_effect((player_id, ally.id), "ally_immunity_aura"):
                return True
        return False

    def _has_same_row_backline_aura(self, character_key: tuple[int, str]) -> bool:
        player_id, character_id = character_key
        character = self._character_by_key(character_key)
        if character.position is None:
            return False

        for ally in self._battle_characters(player_id):
            if ally.id == character_id or not ally.is_alive or ally.position is None:
                continue
            if ally.position.row != character.position.row:
                continue
            if self._character_has_battle_effect((player_id, ally.id), "same_row_backline_aura"):
                return True
        return False

    def _refresh_aura_health_bonuses(self) -> None:
        bonuses: dict[tuple[int, str], int] = {}
        for player_id in self.game_state.players:
            for character in self._battle_characters(player_id):
                bonus = 0
                character_key = (player_id, character.id)
                if character.position is not None:
                    if (
                        character_key not in self.suppressed_bonus_character_keys
                        and self._character_has_battle_effect(character_key, "dragon_will_health_bonus")
                    ):
                        job_ids: set[str] = set()
                        for ally in self._battle_characters(player_id):
                            if ally.id == character.id or not ally.is_alive or ally.position is None:
                                continue
                            if not self._is_adjacent(ally.position, character.position):
                                continue
                            job_ids.add(ally.job.id)
                            if self._character_counts_as_job((player_id, ally.id), "arcane"):
                                job_ids.add("arcane")
                        bonus += len(job_ids) * 2
                    for ally in self._battle_characters(player_id):
                        if ally.id == character.id or not ally.is_alive or ally.position is None:
                            continue
                        ally_key = (player_id, ally.id)
                        if (
                            (player_id, character.id) not in self.suppressed_bonus_character_keys
                            and self._character_has_battle_effect(ally_key, "rank_attack_health_aura")
                            and ally.position.column == character.position.column
                        ):
                            bonus += 3
                        if (
                            (player_id, character.id) not in self.suppressed_bonus_character_keys
                            and self._character_has_battle_effect(ally_key, "adjacent_holy_aura")
                            and self._is_adjacent(ally.position, character.position)
                        ):
                            bonus += 2
                        if (
                            (player_id, character.id) not in self.suppressed_bonus_character_keys
                            and self._character_has_battle_effect(ally_key, "commander_warrior_aura")
                            and self._character_counts_as_job((player_id, character.id), "warrior")
                        ):
                            bonus += 2
                        if (
                            (player_id, character.id) not in self.suppressed_bonus_character_keys
                            and self._character_has_battle_effect(ally_key, "adjacent_wolf_health_attack_aura")
                            and "狼" in character.factions
                            and self._is_adjacent(ally.position, character.position)
                        ):
                            bonus += 2
                bonuses[(player_id, character.id)] = bonus

        for character_key, new_bonus in bonuses.items():
            character = self._character_by_key(character_key)
            old_bonus = character.aura_max_health_bonus
            if old_bonus == new_bonus:
                continue
            base_max_health = character.max_health - old_bonus
            character.max_health = base_max_health + new_bonus
            if new_bonus > old_bonus and character.is_alive:
                character.current_health += new_bonus - old_bonus
            if character.current_health > character.max_health:
                character.current_health = character.max_health
            character.aura_max_health_bonus = new_bonus

    def _same_row_character_keys(
        self,
        player_id: int,
        row: int,
        *,
        exclude_id: str | None = None,
    ) -> list[tuple[int, str]]:
        return [
            (player_id, character.id)
            for character in self._battle_characters(player_id)
            if character.is_alive
            and character.position is not None
            and character.position.row == row
            and character.id != exclude_id
        ]

    def _same_rank_character_keys(
        self,
        player_id: int,
        column: FormationColumn,
        *,
        exclude_id: str | None = None,
    ) -> list[tuple[int, str]]:
        return [
            (player_id, character.id)
            for character in self._battle_characters(player_id)
            if character.is_alive
            and character.position is not None
            and character.position.column == column
            and character.id != exclude_id
        ]

    def _boost_same_rank_health(self, player_id: int, caster_id: str, amount: int) -> list[str]:
        caster = self.game_state.player(player_id).get_character(caster_id)
        if caster.position is None:
            return []

        boosted_names: list[str] = []
        for character in self._battle_characters(player_id):
            if character.is_alive and character.position is not None and character.position.column == caster.position.column:
                character.gain_health(amount)
                boosted_names.append(character.name)
        return boosted_names

    def _purify_character(self, character_key: tuple[int, str]) -> list[str]:
        character = self._character_by_key(character_key)
        removed_ids = [
            effect_id
            for effect_id in character.status_effect_ids
            if self._is_adverse_status_effect_for_character(effect_id, character_key)
        ]
        for effect_id in removed_ids:
            character.remove_status_effect(effect_id)
        if removed_ids:
            self._clear_tracking_for_character(character_key, removed_ids)
        return [effect_display_name(effect_id) for effect_id in removed_ids]

    def shield_stack_count(self, character_key: tuple[int, str]) -> int:
        character = self._character_by_key(character_key)
        if not character.has_status_effect("shield"):
            return 0
        return max(1, self.shield_stacks.get(character_key, 0))

    def gravity_stack_count(self, character_key: tuple[int, str]) -> int:
        character = self._character_by_key(character_key)
        if not character.has_status_effect("gravity"):
            return 0
        return max(1, self.gravity_stacks.get(character_key, 0))

    def _gain_shield(self, character_key: tuple[int, str], amount: int = 1) -> int:
        if amount <= 0:
            return self.shield_stack_count(character_key)
        character = self._character_by_key(character_key)
        current = self.shield_stack_count(character_key)
        character.add_status_effect("shield")
        self.shield_stacks[character_key] = current + amount
        return self.shield_stacks[character_key]

    def _consume_shield(self, character_key: tuple[int, str]) -> bool:
        if self.shield_stack_count(character_key) <= 0:
            return False
        character = self._character_by_key(character_key)
        remaining = self.shield_stack_count(character_key) - 1
        if remaining > 0:
            self.shield_stacks[character_key] = remaining
        else:
            self.shield_stacks.pop(character_key, None)
            character.remove_status_effect("shield")
        return True

    def _clear_tracking_for_character(
        self,
        character_key: tuple[int, str],
        effect_ids: Sequence[str] | None = None,
    ) -> None:
        effect_id_set = set(effect_ids) if effect_ids is not None else None
        if effect_id_set is None or "dream_mark" in effect_id_set:
            self.dream_mark_owners.pop(character_key, None)
            self.round_damage_taken_bonus.pop(character_key, None)
        if effect_id_set is None or "shield" in effect_id_set:
            self.shield_stacks.pop(character_key, None)
        if effect_id_set is None or "gravity" in effect_id_set:
            self.gravity_stacks.pop(character_key, None)
        if effect_id_set is None or "enraged" in effect_id_set:
            self.enrage_sources.pop(character_key, None)
        if effect_id_set is None or "silenced" in effect_id_set:
            self.round_silenced_character_keys.discard(character_key)
        if effect_id_set is None:
            self.tenacity_pending_effects.pop(character_key, None)
        else:
            pending = self.tenacity_pending_effects.get(character_key)
            if pending is not None:
                for effect_id in effect_id_set:
                    pending.pop(effect_id, None)
                if not pending:
                    self.tenacity_pending_effects.pop(character_key, None)

    def _clear_revival_tracking_for_character(self, character_key: tuple[int, str]) -> None:
        self._clear_tracking_for_character(character_key)
        self.last_damage_sources.pop(character_key, None)
        self.round_attack_modifiers.pop(character_key, None)
        self.suppressed_bonus_character_keys.discard(character_key)
        self.temporary_undying_character_keys.discard(character_key)
        self.damage_threshold_totals.pop(character_key, None)
        self.damage_threshold_trigger_counts.pop(character_key, None)
        self.sword_saint_inspire_counts.pop(character_key, None)
        self.fearless_refund_counts.pop(character_key, None)
        for skill_key in list(self.limited_skill_use_counts):
            if skill_key[:2] == character_key:
                self.limited_skill_use_counts.pop(skill_key, None)

    def _execute_character(self, character_key: tuple[int, str], source_key: tuple[int, str] | None) -> bool:
        character = self._character_by_key(character_key)
        if not character.is_alive:
            return False
        if self._character_has_battle_effect(character_key, "undying"):
            character.max_health = max(1, character.max_health)
            character.current_health = max(1, character.current_health)
            return False
        if source_key is not None:
            self.last_damage_sources[character_key] = source_key
        character.current_health = 0
        return True

    def _reduce_max_health_flat(
        self,
        character_key: tuple[int, str],
        amount: int,
        *,
        source_key: tuple[int, str] | None,
    ) -> int:
        character = self._character_by_key(character_key)
        if not character.is_alive or amount <= 0:
            return 0
        minimum_health = 1 if self._character_has_battle_effect(character_key, "undying") else 0
        new_max_health = max(minimum_health, character.max_health - amount)
        reduced = character.max_health - new_max_health
        character.max_health = new_max_health
        if character.max_health <= 0:
            character.max_health = 0
            self._execute_character(character_key, source_key)
        elif character.current_health > character.max_health:
            character.current_health = character.max_health
        elif minimum_health and character.current_health < minimum_health:
            character.current_health = minimum_health
        if source_key is not None:
            self.last_damage_sources[character_key] = source_key
        return reduced

    def _reduce_max_health_percent(
        self,
        character_key: tuple[int, str],
        percent: int,
        *,
        source_key: tuple[int, str] | None,
    ) -> int:
        character = self._character_by_key(character_key)
        amount = self._percentage_damage(character.max_health, percent)
        return self._reduce_max_health_flat(character_key, amount, source_key=source_key)

    def _resolve_arson_damage(self, attacker_key: tuple[int, str], defeated_target_key: tuple[int, str]) -> list[str]:
        target = self._character_by_key(defeated_target_key)
        if target.position is None:
            return []

        events: list[str] = []
        for splash_key in self._adjacent_character_keys(defeated_target_key[0], target.position, exclude_id=target.id):
            splash_target = self._character_by_key(splash_key)
            damage_result = self._resolve_damage(
                moving_player_id=attacker_key[0],
                source_key=attacker_key,
                target_key=splash_key,
                base_damage=1,
                immune_character_keys=(),
                allow_guard=True,
            )
            events.append(f"{splash_target.name} 受到纵火 {damage_result.damage} 点。")
            events.extend(damage_result.events)
        return events

    def _resolve_bomb_death_damage(
        self,
        bomber_key: tuple[int, str],
        killer_key: tuple[int, str],
    ) -> list[str]:
        bomber = self._character_by_key(bomber_key)
        killer = self._character_by_key(killer_key)
        if killer.position is None:
            return []

        events: list[str] = [f"{bomber.name} 触发死亡爆炸。"]
        target_keys = self._same_row_character_keys(killer_key[0], killer.position.row)
        if killer_key not in target_keys and killer.is_alive:
            target_keys.insert(0, killer_key)
        seen: set[tuple[int, str]] = set()
        for target_key in target_keys:
            if target_key in seen:
                continue
            seen.add(target_key)
            target = self._character_by_key(target_key)
            if not target.is_alive:
                continue
            damage_result = self._resolve_damage(
                moving_player_id=bomber_key[0],
                source_key=bomber_key,
                target_key=target_key,
                base_damage=3,
                immune_character_keys=(),
                allow_guard=True,
            )
            events.append(f"{target.name} 受到爆炸 {damage_result.damage} 点。")
            events.extend(damage_result.events)
        return events

    def _adjacent_character_keys(
        self,
        player_id: int,
        position: Position,
        *,
        exclude_id: str | None = None,
    ) -> list[tuple[int, str]]:
        return [
            (player_id, character.id)
            for character in self._battle_characters(player_id)
            if character.is_alive
            and character.position is not None
            and character.id != exclude_id
            and self._is_adjacent(character.position, position)
        ]

    def _same_column_adjacent_character_keys(
        self,
        player_id: int,
        position: Position,
        *,
        exclude_id: str | None = None,
    ) -> list[tuple[int, str]]:
        return [
            (player_id, character.id)
            for character in self._battle_characters(player_id)
            if character.is_alive
            and character.position is not None
            and character.id != exclude_id
            and character.position.column == position.column
            and abs(character.position.row - position.row) == 1
        ]

    def _create_summoned_character(self, definition_id: str, player_id: int) -> Character:
        from src.data.characters import CHARACTER_DEFINITIONS_BY_ID
        from src.data.jobs import JOBS_BY_ID

        definition = CHARACTER_DEFINITIONS_BY_ID[definition_id]
        character = definition.create_character(JOBS_BY_ID)
        existing_ids = {existing.id for existing in self.game_state.player(player_id).selected_characters}
        if character.id not in existing_ids:
            return character

        index = 1
        while f"{character.id}_{index}" in existing_ids:
            index += 1
        character.id = f"{character.id}_{index}"
        return character

    def _summon_character_at(self, player_id: int, definition_id: str, position: Position) -> Character:
        character = self._create_summoned_character(definition_id, player_id)
        player = self.game_state.player(player_id)
        player.add_character(character)
        player.place_character(character.id, position)
        self.remaining_moves[(player_id, character.id)] = character.default_move_count
        self._refresh_aura_health_bonuses()
        return character

    def _resolve_curse_for_key(
        self,
        character_key: tuple[int, str],
        source_key: tuple[int, str] | None,
    ) -> bool:
        character = self._character_by_key(character_key)
        if not character.is_alive or not character.has_status_effect("cursed"):
            return False
        if character.current_health * 2 > character.max_health:
            return False
        self._execute_character(character_key, source_key)
        return not character.is_alive

    def _begin_tenacity_enemy_action(self, acting_player_id: int) -> None:
        for character_key, effect_states in list(self.tenacity_pending_effects.items()):
            target_player_id, _character_id = character_key
            if target_player_id == acting_player_id:
                continue
            character = self._character_by_key(character_key)
            if not character.is_alive:
                self.tenacity_pending_effects.pop(character_key, None)
                continue
            for effect_id in list(effect_states):
                if character.has_status_effect(effect_id):
                    effect_states[effect_id] = True
                else:
                    effect_states.pop(effect_id, None)
            if not effect_states:
                self.tenacity_pending_effects.pop(character_key, None)

    def _resolve_tenacity_after_enemy_action(self, acting_player_id: int) -> None:
        for character_key, effect_states in list(self.tenacity_pending_effects.items()):
            target_player_id, _character_id = character_key
            if target_player_id == acting_player_id:
                continue
            character = self._character_by_key(character_key)
            if not character.is_alive:
                self.tenacity_pending_effects.pop(character_key, None)
                continue
            removed_ids = [
                effect_id
                for effect_id, enemy_action_started in effect_states.items()
                if enemy_action_started and character.has_status_effect(effect_id)
            ]
            for effect_id in removed_ids:
                character.remove_status_effect(effect_id)
            self._clear_tracking_for_character(character_key, removed_ids)

    def _revive_if_pending(self, character_key: tuple[int, str], events: list[str]) -> bool:
        if character_key not in self.pending_revivals:
            return False
        character = self._character_by_key(character_key)
        if character.is_alive:
            self.pending_revivals.discard(character_key)
            return False
        character.reset_for_revival()
        self._clear_revival_tracking_for_character(character_key)
        self.pending_revivals.discard(character_key)
        self._refresh_aura_health_bonuses()
        events.append(f"{character.name} 复活。")
        return True

    def _pending_revival_consumes_turn(self, character_key: tuple[int, str]) -> bool:
        if character_key not in self.pending_revivals:
            return False
        character = self._character_by_key(character_key)
        return "revive_skip_turn" in character.effective_passive_effect_ids

    def _character_counts_as_job(self, character_key: tuple[int, str], job_id: str) -> bool:
        character = self._character_by_key(character_key)
        if character.job.id == job_id:
            return True
        if (
            job_id == "arcane"
            and self._character_has_battle_effect(character_key, "dragon_arcane_adapt")
            and self._has_adjacent_arcane_ally(character_key)
        ):
            return True
        return False

    def _has_adjacent_arcane_ally(self, character_key: tuple[int, str]) -> bool:
        player_id, character_id = character_key
        character = self._character_by_key(character_key)
        if character.position is None:
            return False
        for ally in self._battle_characters(player_id):
            if ally.id == character_id or not ally.is_alive or ally.position is None:
                continue
            if not self._is_adjacent(ally.position, character.position):
                continue
            if ally.job.id == "arcane":
                return True
        return False

    def _is_wolf_character(self, character_key: tuple[int, str]) -> bool:
        return "狼" in self._character_by_key(character_key).factions

    def _is_dragon_character(self, character_key: tuple[int, str]) -> bool:
        return "龙" in self._character_by_key(character_key).factions

    def _other_friendly_wolf_count(self, character_key: tuple[int, str]) -> int:
        player_id, character_id = character_key
        return sum(
            1
            for ally in self._battle_characters(player_id)
            if ally.id != character_id and ally.is_alive and "狼" in ally.factions
        )

    def _other_battle_wolf_count(self, character_key: tuple[int, str]) -> int:
        return sum(
            1
            for player_id in self.game_state.players
            for character in self._battle_characters(player_id)
            if (player_id, character.id) != character_key and character.is_alive and "狼" in character.factions
        )

    def _has_other_ally_effect(self, character_key: tuple[int, str], effect_id: str) -> bool:
        player_id, character_id = character_key
        for ally in self._battle_characters(player_id):
            if ally.id == character_id or ally.position is None:
                continue
            if effect_id not in ally.effective_passive_effect_ids:
                continue
            if ally.has_status_effect("silenced"):
                continue
            if ally.is_alive or "eternal_effect" in ally.effective_passive_effect_ids:
                return True
        return False

    def _any_living_character_key(self, target_id: str) -> tuple[int, str]:
        for player_id in self.game_state.players:
            for character in self._battle_characters(player_id):
                if character.id == target_id and character.is_alive:
                    return player_id, character.id
        raise BattleError("Invalid target.")

    def _newly_defeated_keys(self, alive_before: set[tuple[int, str]]) -> list[tuple[int, str]]:
        defeated_keys: list[tuple[int, str]] = []
        for player_id in self.game_state.players:
            for character in self._battle_characters(player_id):
                character_key = (player_id, character.id)
                if character_key in alive_before and not character.is_alive:
                    defeated_keys.append(character_key)
        return defeated_keys

    def _names_for_keys(self, moving_player_id: int, character_keys: Sequence[tuple[int, str]]) -> list[str]:
        key_set = set(character_keys)
        return [
            character.name
            for player_id, character in self._ordered_battle_character_refs(moving_player_id)
            if (player_id, character.id) in key_set
        ]

    def _queue_death_triggers(self, defeated_keys: Sequence[tuple[int, str]]) -> list[str]:
        events: list[str] = []
        for character_key in defeated_keys:
            player_id, character_id = character_key
            character = self._character_by_key(character_key)
            killer_key = self.last_damage_sources.get(character_key)

            if killer_key is not None and killer_key[0] != player_id:
                killer = self._character_by_key(killer_key)
                if killer.is_alive:
                    for ally in self._battle_characters(player_id):
                        ally_key = (player_id, ally.id)
                        if not ally.is_alive or not self._character_has_battle_effect(ally_key, "gravity_on_ally_killed"):
                            continue
                        if self.apply_status_effect(killer_key[0], killer_key[1], "gravity", source_key=ally_key):
                            events.append(f"{killer.name} 因杀死友方单位获得1层重力。")

            if (
                killer_key is not None
                and "silence_killer_on_death" in character.effective_passive_effect_ids
                and not character.has_used_passive_effect("silence_killer_on_death")
            ):
                character.mark_passive_effect_used("silence_killer_on_death")
                killer = self._character_by_key(killer_key)
                if killer.is_alive:
                    applied = self.apply_status_effect(killer_key[0], killer_key[1], "silenced", source_key=character_key)
                    if applied:
                        events.append(f"{killer.name} 被 {character.name} 沉默。")
                    else:
                        events.append(f"{killer.name} 免疫了沉默。")

            if (
                killer_key is not None
                and "bomb_death_damage" in character.effective_passive_effect_ids
                and not character.has_used_passive_effect("bomb_death_damage")
            ):
                character.mark_passive_effect_used("bomb_death_damage")
                alive_before_bomb = self._living_character_keys()
                events.extend(self._resolve_bomb_death_damage(character_key, killer_key))
                bomb_defeated_keys = self._newly_defeated_keys(alive_before_bomb)
                if bomb_defeated_keys:
                    events.extend(self._queue_death_triggers(bomb_defeated_keys))

            if (
                character.has_status_effect("dream_mark")
                and character_key in self.dream_mark_owners
                and not character.has_used_passive_effect("dream_mark_summon")
            ):
                owner_key = self.dream_mark_owners[character_key]
                owner = self._character_by_key(owner_key)
                if owner.is_alive:
                    character.mark_passive_effect_used("dream_mark_summon")
                    self.pending_summons.append(
                        SummonRequest(
                            player_id=owner_key[0],
                            source_name=owner.name,
                            character_definition_id="dream_eater",
                        )
                    )
                    events.append(f"{character.name} 的摄梦触发，{owner.name} 可以召唤食梦者。")

            if (
                "summon_little_skeleton_on_death" in character.effective_passive_effect_ids
                and not character.has_used_passive_effect("summon_little_skeleton_on_death")
                and character.position is not None
            ):
                character.mark_passive_effect_used("summon_little_skeleton_on_death")
                summoned = self._summon_character_at(player_id, "little_skeleton", character.position)
                events.append(f"{character.name} 死亡后召唤了 {summoned.name}。")

            if (
                "death_other_allies_health_4" in character.effective_passive_effect_ids
                and not character.has_used_passive_effect("death_other_allies_health_4")
            ):
                character.mark_passive_effect_used("death_other_allies_health_4")
                boosted_names: list[str] = []
                for ally in self._battle_characters(player_id):
                    if ally.id == character_id or not ally.is_alive:
                        continue
                    ally.gain_health(4)
                    boosted_names.append(ally.name)
                if boosted_names:
                    events.append(f"{character.name} 死亡后使 {'、'.join(boosted_names)} 生命 +4。")

            if (
                "eternal_revival" in character.effective_passive_effect_ids
                and character_key not in self.pending_revivals
            ):
                self.pending_revivals.add(character_key)
                if self.remaining_moves.get(character_key, 0) <= 0:
                    self.remaining_moves[character_key] = character.default_move_count
                events.append(f"{character.name} 将在下个自己回合复活。")

            if "death_damage_any" not in character.effective_passive_effect_ids:
                if (
                    "death_attack_buff_any" in character.effective_passive_effect_ids
                    and not character.has_used_passive_effect("death_attack_buff_any")
                ):
                    character.mark_passive_effect_used("death_attack_buff_any")
                    self.pending_death_triggers.append(
                        DeathTrigger(
                            player_id=player_id,
                            character_id=character_id,
                            character_name=character.name,
                            damage=0,
                            kind="attack_buff",
                            attack_bonus=3,
                        )
                    )
                continue
            if not character.has_used_passive_effect("death_damage_any"):
                character.mark_passive_effect_used("death_damage_any")
                self.pending_death_triggers.append(
                    DeathTrigger(
                        player_id=player_id,
                        character_id=character_id,
                        character_name=character.name,
                        damage=character.attack,
                    )
                )

        current_trigger = self.current_death_trigger()
        if current_trigger is not None:
            self.game_state.current_turn_player_id = current_trigger.player_id
        elif self.pending_summons:
            summon = self.current_summon_request()
            if summon is not None:
                self.game_state.current_turn_player_id = summon.player_id
        return events

    def _is_adjacent(self, first: Position, second: Position) -> bool:
        if first == second:
            return False
        if first.row == second.row and first.column != second.column:
            return True
        return first.column == second.column and abs(first.row - second.row) == 1

    def _living_character_keys(self) -> set[tuple[int, str]]:
        return {
            (player_id, character.id)
            for player_id in self.game_state.players
            for character in self._battle_characters(player_id)
            if character.is_alive
        }

    def _newly_defeated_names(
        self,
        moving_player_id: int,
        alive_before: set[tuple[int, str]],
    ) -> list[str]:
        defeated_names: list[str] = []
        for player_id, character in self._ordered_battle_character_refs(moving_player_id):
            if (player_id, character.id) in alive_before and not character.is_alive:
                defeated_names.append(character.name)
        return defeated_names

    def _character_by_key(self, character_key: tuple[int, str]) -> Character:
        player_id, character_id = character_key
        return self.game_state.player(player_id).get_character(character_id)
