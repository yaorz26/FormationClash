from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

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
from src.core.rules import effect_display_name


class BattleSkillMixin:
    def apply_status_effect(
        self,
        player_id: int,
        character_id: str,
        effect_id: str,
        *,
        source_key: tuple[int, str] | None = None,
    ) -> bool:
        character = self.game_state.player(player_id).get_character(character_id)
        character_key = (player_id, character_id)
        had_tenacity = self._character_has_battle_effect(character_key, "tenacity")
        is_adverse = self._is_adverse_status_effect_for_character(effect_id, character_key)
        if is_adverse and self._character_has_battle_effect(character_key, "adverse_immunity"):
            return False
        if effect_id == "silenced" and self._character_has_battle_effect(character_key, "silence_immunity"):
            return False

        if effect_id == "silenced":
            character.status_effect_ids = set()
            self._clear_tracking_for_character(character_key)
        if effect_id == "shield":
            self._gain_shield(character_key)
            return True
        character.add_status_effect(effect_id)
        if effect_id == "gravity":
            self.gravity_stacks[character_key] = self.gravity_stacks.get(character_key, 0) + 1
        if effect_id == "enraged" and source_key is not None:
            self.enrage_sources[character_key] = source_key
        if source_key is not None:
            self.last_damage_sources[character_key] = source_key

        if is_adverse and (had_tenacity or self._character_has_battle_effect(character_key, "tenacity")):
            self.tenacity_pending_effects.setdefault(character_key, {})[effect_id] = False
        if effect_id == "cursed":
            self._resolve_curse_for_key(character_key, source_key)
        return True

    def active_skills(self, player_id: int, character_id: str) -> tuple[ActiveSkill, ...]:
        character = self.game_state.player(player_id).get_character(character_id)
        if character.has_status_effect("silenced"):
            return ()
        return character.active_skills

    def skill_targets(self, player_id: int, character_id: str, skill_id: str) -> list[Character]:
        skill = self._active_skill(player_id, character_id, skill_id)
        if self._skill_casts_without_manual_target(player_id, character_id, skill):
            return []
        return [
            self._character_by_key(target_key)
            for target_key in self._skill_target_keys(player_id, character_id, skill)
        ]

    def can_cast_skill(
        self,
        player_id: int,
        character_id: str,
        skill_id: str,
        target_id: str | Sequence[str] | None = None,
    ) -> bool:
        if self.game_state.phase != GamePhase.BATTLE:
            return False
        if self.current_player_id != player_id:
            return False
        if self.pending_summons:
            return False
        if self._has_pending_manual_choice():
            return False
        if self.pending_followup_attack is not None:
            return False
        if not self.can_character_move(player_id, character_id):
            return False
        if self._pending_revival_consumes_turn((player_id, character_id)):
            return False

        character = self.game_state.player(player_id).get_character(character_id)
        if character.has_status_effect("frozen"):
            return False

        try:
            skill = self._active_skill(player_id, character_id, skill_id)
        except BattleError:
            return False
        if skill.once_per_game and character.has_used_active_skill(skill.id):
            return False
        base_skill_id = skill.id.split("__copy_", 1)[0]
        if (
            base_skill_id == "vanguard_health_boost"
            and self.limited_skill_use_counts.get((player_id, character_id, base_skill_id), 0) >= 4
        ):
            return False

        if self._skill_casts_without_manual_target(player_id, character_id, skill):
            return target_id is None
        if target_id is None:
            if base_skill_id == "brutal_bomber_distribute":
                return bool(self.skill_targets(player_id, character_id, skill_id))
            return len(self.skill_targets(player_id, character_id, skill_id)) >= skill.min_targets
        try:
            self._skill_target_keys_for_ids(player_id, character_id, skill, target_id)
        except BattleError:
            return False
        return True

    def cast_skill(
        self,
        player_id: int,
        character_id: str,
        skill_id: str,
        target_id: str | Sequence[str] | None,
    ) -> SkillResult:
        skill = self._active_skill(player_id, character_id, skill_id)
        casts_without_target = self._skill_casts_without_manual_target(player_id, character_id, skill)
        if casts_without_target:
            if target_id is not None or not self.can_cast_skill(player_id, character_id, skill_id):
                raise BattleError("Invalid skill.")
        elif target_id is None or not self.can_cast_skill(player_id, character_id, skill_id, target_id):
            raise BattleError("Invalid skill.")

        self.action_damage_events.clear()
        caster = self.game_state.player(player_id).get_character(character_id)
        target_keys = (
            [(player_id, character_id)]
            if casts_without_target
            else self._skill_target_keys_for_ids(player_id, character_id, skill, target_id)
        )
        target_player_id, normalized_target_id = target_keys[0]
        target = self.game_state.player(target_player_id).get_character(normalized_target_id)
        base_skill_id = skill.id.split("__copy_", 1)[0]
        if casts_without_target:
            target_names = "所有迷惑敌人" if base_skill_id == "revenge_piper_song" else "无指定目标"
        else:
            target_names = "、".join(self._character_by_key(target_key).name for target_key in target_keys)
        alive_before = self._living_character_keys()
        events: list[str] = []
        damage = 0
        actual_target_name = target.name

        self._begin_tenacity_enemy_action(player_id)
        slot_index = self._record_movement(player_id, character_id)
        self._revive_if_pending((player_id, character_id), events)
        if skill.once_per_game:
            caster.use_active_skill(skill.id)

        if skill.kind == SkillKind.DAMAGE and skill.damage > 0:
            damage_result = self._resolve_damage(
                moving_player_id=player_id,
                source_key=(player_id, character_id),
                target_key=(target_player_id, normalized_target_id),
                base_damage=skill.damage,
                immune_character_keys=(),
                allow_guard=True,
            )
            damage = damage_result.damage
            actual_target_name = damage_result.receiver_name
            events.extend(damage_result.events)

        status_applied = False
        status_effect_name = ""
        if skill.kind == SkillKind.STATUS and skill.status_effect_id is not None:
            status_effect_name = effect_display_name(skill.status_effect_id)
            status_applied = self.apply_status_effect(
                target_player_id,
                normalized_target_id,
                skill.status_effect_id,
                source_key=(player_id, character_id),
            )
            if status_applied:
                events.append(f"{target.name} 获得{status_effect_name}。")
            else:
                events.append(f"{target.name} 免疫了{status_effect_name}。")
        elif skill.kind == SkillKind.HEAL and skill.heal > 0:
            before_health = target.current_health
            target.heal(skill.heal)
            healed = target.current_health - before_health
            events.append(f"{target.name} 恢复 {healed} 点生命。")
        elif skill.kind == SkillKind.ARMOR and skill.armor > 0:
            target.gain_armor(skill.armor)
            events.append(f"{target.name} 获得 {skill.armor} 点护甲。")
        elif skill.kind == SkillKind.ATTACK_BUFF and skill.attack_bonus > 0:
            target.attack += skill.attack_bonus
            events.append(f"{target.name} 攻击力 +{skill.attack_bonus}。")
        elif skill.kind == SkillKind.HEALTH_BUFF_RANK and skill.health_bonus > 0:
            boosted_names = self._boost_same_rank_health(player_id, character_id, skill.health_bonus)
            events.append(f"{'、'.join(boosted_names)} 生命 +{skill.health_bonus}。")
        elif skill.kind == SkillKind.ATTACK:
            attack_result = self._resolve_attack_with_context(
                attacker_player_id=player_id,
                attacker_id=character_id,
                target_player_id=target_player_id,
                target_id=normalized_target_id,
                attack_percent=skill.attack_percent,
                extra_target_reflect_percent=skill.target_reflect_percent,
            )
            damage = attack_result.damage
            actual_target_name = attack_result.actual_target_name
            events.extend(attack_result.events)
        elif skill.kind == SkillKind.CUSTOM:
            damage, status_effect_name, status_applied, actual_target_name = self._resolve_custom_skill(
                player_id=player_id,
                character_id=character_id,
                skill=skill,
                target_keys=target_keys,
                events=events,
            )

        waits_for_followup = self.pending_followup_attack == (player_id, character_id)
        if waits_for_followup:
            self.pending_followup_order_slot = slot_index
        else:
            self.remaining_moves[(player_id, character_id)] -= 1
            self._resolve_order_slot(player_id, slot_index)

        defeated_character_keys = self._newly_defeated_keys(alive_before)
        events.extend(self._queue_death_triggers(defeated_character_keys))
        defeated_character_names = self._newly_defeated_names(player_id, alive_before)
        winner_player_id = None
        if self.pending_death_triggers or self.pending_summons or self._has_pending_manual_choice():
            if not waits_for_followup:
                self.pending_post_action_player_id = player_id
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
            self._advance_turn_after_action(player_id)

        return SkillResult(
            caster_name=caster.name,
            skill_name=skill.name,
            target_name=target_names,
            damage=damage,
            status_effect_name=status_effect_name,
            status_applied=status_applied,
            winner_player_id=winner_player_id,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
            actual_target_name=actual_target_name,
            defeated_character_names=tuple(defeated_character_names),
            events=tuple(events),
            damage_events=tuple(self.action_damage_events),
        )

    def _active_skill(self, player_id: int, character_id: str, skill_id: str) -> ActiveSkill:
        character = self.game_state.player(player_id).get_character(character_id)
        for skill in character.active_skills:
            if skill.id == skill_id:
                return skill
        raise BattleError("Unknown skill.")

    def _skill_target_keys(self, player_id: int, character_id: str, skill: ActiveSkill) -> list[tuple[int, str]]:
        base_skill_id = skill.id.split("__copy_", 1)[0]
        forced_target_key = self._enraged_forced_target_key((player_id, character_id))
        if forced_target_key is not None and base_skill_id != "brutal_bomber_distribute" and skill.max_targets <= 1:
            return [forced_target_key]
        if base_skill_id == "copy_ally_active_skill":
            return [
                (player_id, character.id)
                for character in self._battle_characters(player_id)
                if character.id != character_id
                and character.is_alive
                and self._can_manually_select_target(player_id, (player_id, character.id))
                and self._copyable_active_skill(character) is not None
            ]
        if base_skill_id == "revenge_piper_song":
            enemy_keys = [
                (self.game_state.opponent_id(player_id), character.id)
                for character in self._battle_characters(self.game_state.opponent_id(player_id))
                if character.is_alive
                and self._can_manually_select_target(player_id, (self.game_state.opponent_id(player_id), character.id))
            ]
            if self._revenge_piper_damage_mode(player_id):
                return [
                    enemy_key
                    for enemy_key in enemy_keys
                    if self._character_by_key(enemy_key).has_status_effect("confused")
                ]
            return enemy_keys
        if base_skill_id == "brutal_bomber_distribute":
            opponent_id = self.game_state.opponent_id(player_id)
            living_enemies = [
                character
                for character in self._battle_characters(opponent_id)
                if character.is_alive and self._can_manually_select_target(player_id, (opponent_id, character.id))
            ]
            target_keys = [
                (player_id, character.id)
                for character in self._battle_characters(player_id)
                if character.is_alive and self._can_manually_select_target(player_id, (player_id, character.id))
            ]
            target_keys.extend(
                (opponent_id, target.id)
                for target in self._apply_attack_taunt(player_id, opponent_id, living_enemies)
            )
            if forced_target_key is not None:
                target_keys.insert(0, forced_target_key)
            return list(dict.fromkeys(target_keys))
        if skill.target == SkillTarget.SELF:
            caster = self.game_state.player(player_id).get_character(character_id)
            target_keys = [(player_id, character_id)] if caster.is_alive and caster.position is not None else []
            if forced_target_key is not None:
                return [forced_target_key, *[target_key for target_key in target_keys if target_key != forced_target_key]]
            return target_keys
        if skill.target == SkillTarget.ANY:
            target_player_ids = tuple(self.game_state.players)
        elif skill.target == SkillTarget.ALLY:
            target_player_ids = (player_id,)
        elif skill.target == SkillTarget.ENEMY:
            target_player_ids = (self.game_state.opponent_id(player_id),)
        else:
            target_player_ids = ()

        target_keys = [
            (target_player_id, character.id)
            for target_player_id in target_player_ids
            for character in self._battle_characters(target_player_id)
            if character.is_alive and self._can_manually_select_target(player_id, (target_player_id, character.id))
            and not (skill.exclude_self and target_player_id == player_id and character.id == character_id)
        ]
        if forced_target_key is not None:
            target_keys = [forced_target_key, *[target_key for target_key in target_keys if target_key != forced_target_key]]
        return target_keys

    def _skill_casts_without_manual_target(self, player_id: int, character_id: str, skill: ActiveSkill) -> bool:
        base_skill_id = skill.id.split("__copy_", 1)[0]
        if self._enraged_forced_target_key((player_id, character_id)) is not None:
            return False
        return (
            (base_skill_id == "revenge_piper_song" and self._revenge_piper_damage_mode(player_id))
            or base_skill_id in ("charger_leader_mobilize", "pharaoh_curse_all", "octopus_summon_tentacle")
        )

    def _skill_target_keys_for_ids(
        self,
        player_id: int,
        character_id: str,
        skill: ActiveSkill,
        target_ids: str | Sequence[str],
    ) -> list[tuple[int, str]]:
        normalized_ids = [target_ids] if isinstance(target_ids, str) else list(target_ids)
        if not (skill.min_targets <= len(normalized_ids) <= skill.max_targets):
            raise BattleError("Invalid skill target count.")
        base_skill_id = skill.id.split("__copy_", 1)[0]
        if base_skill_id != "brutal_bomber_distribute" and len(set(normalized_ids)) != len(normalized_ids):
            raise BattleError("Skill targets must be distinct.")
        forced_target_key = self._enraged_forced_target_key((player_id, character_id))
        if forced_target_key is not None and normalized_ids[0] != forced_target_key[1]:
            raise BattleError("Enraged characters must target Provocation first.")

        available = self._skill_target_keys(player_id, character_id, skill)
        selected: list[tuple[int, str]] = []
        for target_id in normalized_ids:
            for target_key in available:
                if target_key[1] == target_id:
                    selected.append(target_key)
                    break
            else:
                raise BattleError("Invalid skill target.")
        return selected

    def _skill_target_key(
        self,
        player_id: int,
        character_id: str,
        skill: ActiveSkill,
        target_id: str,
    ) -> tuple[int, str]:
        for target_key in self._skill_target_keys(player_id, character_id, skill):
            if target_key[1] == target_id:
                return target_key
        raise BattleError("Invalid skill target.")

    def _resolve_custom_skill(
        self,
        *,
        player_id: int,
        character_id: str,
        skill: ActiveSkill,
        target_keys: list[tuple[int, str]],
        events: list[str],
    ) -> tuple[int, str, bool, str]:
        caster_key = (player_id, character_id)
        caster = self._character_by_key(caster_key)
        status_effect_name = ""
        status_applied = False
        actual_target_name = self._character_by_key(target_keys[0]).name
        base_skill_id = skill.id.split("__copy_", 1)[0]
        if base_skill_id == "purify_allies":
            for target_key in target_keys:
                target = self._character_by_key(target_key)
                removed = self._purify_character(target_key)
                before_health = target.current_health
                target.heal(skill.heal)
                healed = target.current_health - before_health
                detail = f"，清除 {'、'.join(removed)}" if removed else ""
                events.append(f"{target.name} 被净化{detail}，恢复 {healed} 点生命。")
            return 0, status_effect_name, status_applied, actual_target_name

        if base_skill_id == "heavenly_eye":
            sacrifice_key, buff_key = target_keys
            sacrifice = self._character_by_key(sacrifice_key)
            target = self._character_by_key(buff_key)
            if self._execute_character(sacrifice_key, caster_key):
                events.append(f"{sacrifice.name} 被消灭。")
            else:
                events.append(f"{sacrifice.name} 的不死无视了消灭。")
            if caster.is_alive:
                target.attack += skill.attack_bonus
                target.gain_health(skill.health_bonus)
                events.append(f"{target.name} 获得 +{skill.health_bonus}生命与 +{skill.attack_bonus}攻击力。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "bride_weaken":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            self.round_attack_modifiers[target_key] = self.round_attack_modifiers.get(target_key, 0) - 4
            events.append(f"{target.name} 本回合攻击力 -4。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "bride_global_weaken":
            reduced = self._reduce_max_health_flat(caster_key, 4, source_key=caster_key)
            events.append(f"{caster.name} 生命上限 -{reduced}。")
            if not caster.is_alive:
                events.append(f"{caster.name} 因生命上限降低死亡，后续效果不触发。")
                return 0, status_effect_name, status_applied, caster.name
            for target_player_id in self.game_state.players:
                for character in self._battle_characters(target_player_id):
                    if character.is_alive:
                        key = (target_player_id, character.id)
                        self.round_attack_modifiers[key] = self.round_attack_modifiers.get(key, 0) - 3
            events.append("所有角色本回合攻击力 -3。")
            return 0, status_effect_name, status_applied, caster.name

        if base_skill_id == "dream_bind":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            status_effect_name = effect_display_name("dream_mark")
            status_applied = self.apply_status_effect(target_key[0], target_key[1], "dream_mark", source_key=caster_key)
            if status_applied:
                self.round_damage_taken_bonus[target_key] = self.round_damage_taken_bonus.get(target_key, 0) + 2
                self.dream_mark_owners[target_key] = caster_key
                events.append(f"{target.name} 获得摄梦，本回合受伤 +2。")
            else:
                events.append(f"{target.name} 免疫了摄梦。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "fountain_heal_all":
            healed_names: list[str] = []
            for ally in self._battle_characters(player_id):
                if ally.is_alive:
                    before = ally.current_health
                    ally.heal(skill.heal)
                    healed = ally.current_health - before
                    healed_names.append(f"{ally.name}+{healed}")
            events.append(f"圣灵之泉恢复：{'、'.join(healed_names) or '无'}。")
            return 0, status_effect_name, status_applied, caster.name

        if base_skill_id == "stone_lord_guardianize":
            from src.data.jobs import JOBS_BY_ID

            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            target.gain_health(skill.health_bonus)
            target.job = JOBS_BY_ID["guardian"]
            self._refresh_aura_health_bonuses()
            events.append(f"{target.name} 生命 +{skill.health_bonus}，职业变为守护者。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "lang_qi_flurry":
            lost_health = max(0, caster.max_health - caster.current_health)
            attack_count = min(7, lost_health)
            if attack_count <= 0:
                events.append(f"{caster.name} 未损失生命，技能未发动攻击。")
                return 0, status_effect_name, status_applied, caster.name

            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            attack_resolution = self._resolve_attack_with_context(
                attacker_player_id=player_id,
                attacker_id=character_id,
                target_player_id=target_key[0],
                target_id=target_key[1],
                attack_percent=100,
                extra_target_reflect_percent=0,
            )
            actual_target_name = attack_resolution.actual_target_name
            events.append(f"{caster.name} 第1次攻击 {target.name}。")
            events.extend(attack_resolution.events)

            remaining_attacks = attack_count - 1
            if remaining_attacks > 0 and caster.is_alive and self._has_followup_attack_target(player_id, character_id):
                self.pending_followup_attack = (player_id, character_id)
                self.pending_followup_remaining_attacks = remaining_attacks
                events.append(f"{caster.name} 还可选择 {remaining_attacks} 次攻击目标。")
            return attack_resolution.damage, status_effect_name, status_applied, actual_target_name

        if base_skill_id == "create_shield_barrier":
            self.team_barriers[player_id] = self.team_barrier_amount(player_id) + 12
            self.team_barrier_sources[player_id] = caster_key
            events.append(f"{caster.name} 生成保护全体友方单位的屏障，剩余可抵御伤害 {self.team_barriers[player_id]}。")
            return 0, status_effect_name, status_applied, caster.name

        if base_skill_id == "copy_ally_active_skill":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            copied_skill = self._copyable_active_skill(target)
            if copied_skill is None:
                events.append(f"{target.name} 没有可研习的主动技能。")
                return 0, status_effect_name, status_applied, target.name
            copy_count = sum(
                1
                for existing_skill in caster.active_skills
                if existing_skill.id.startswith(f"{copied_skill.id}__copy_")
            )
            copied = replace(
                copied_skill,
                id=f"{copied_skill.id}__copy_{copy_count + 1}",
                display_text=copied_skill.display_text or f"{copied_skill.name}：{copied_skill.description}",
                once_per_game=copied_skill.once_per_game,
            )
            caster.active_skills = (*caster.active_skills, copied)
            events.append(f"{caster.name} 获得 {target.name} 的主动技能 {copied_skill.name}。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "restore_arcane_limited_skills":
            restored_names: list[str] = []
            for ally in self._battle_characters(player_id):
                ally_key = (player_id, ally.id)
                if not ally.is_alive or not self._character_counts_as_job(ally_key, "arcane"):
                    continue
                restored_skill_ids = {
                    active_skill.id
                    for active_skill in ally.active_skills
                    if active_skill.once_per_game and ally.has_used_active_skill(active_skill.id)
                }
                if not restored_skill_ids:
                    continue
                ally.used_active_skill_ids.difference_update(restored_skill_ids)
                restored_names.append(ally.name)
            events.append(f"{caster.name} 恢复限定技能：{'、'.join(restored_names) or '无'}。")
            return 0, status_effect_name, status_applied, caster.name

        if base_skill_id == "alchemist_life_blast":
            total_damage = 0
            for area_key in self._same_side_area_keys(target_keys[0]):
                target = self._character_by_key(area_key)
                area_damage = self._percentage_damage(target.max_health, 25)
                damage_result = self._resolve_damage(
                    moving_player_id=player_id,
                    source_key=caster_key,
                    target_key=area_key,
                    base_damage=area_damage,
                    immune_character_keys=(),
                    allow_guard=True,
                )
                total_damage += damage_result.damage
                events.append(f"{target.name} 受到炼成爆破 {damage_result.damage} 点。")
                events.extend(damage_result.events)
            return total_damage, status_effect_name, status_applied, actual_target_name

        if base_skill_id == "saintly_priest_heal":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            heal_amount = self._percentage_damage(self.effective_attack(caster_key), 200)
            before_health = target.current_health
            target.heal(heal_amount)
            healed = target.current_health - before_health
            events.append(f"{target.name} 恢复 {healed} 点生命。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "revenge_piper_song":
            if self._revenge_piper_damage_mode(player_id):
                total_damage = 0
                for enemy_key in self._revenge_piper_confused_enemy_keys(player_id):
                    target = self._character_by_key(enemy_key)
                    damage_result = self._resolve_damage(
                        moving_player_id=player_id,
                        source_key=caster_key,
                        target_key=enemy_key,
                        base_damage=4,
                        immune_character_keys=(),
                        allow_guard=True,
                    )
                    total_damage += damage_result.damage
                    events.append(f"{target.name} 受到复仇笛音 {damage_result.damage} 点。")
                    events.extend(damage_result.events)
                return total_damage, status_effect_name, status_applied, caster.name

            status_effect_name = effect_display_name("confused")
            applied_names: list[str] = []
            for target_key in target_keys:
                target = self._character_by_key(target_key)
                status_applied = self.apply_status_effect(target_key[0], target_key[1], "confused", source_key=caster_key)
                if status_applied:
                    applied_names.append(target.name)
            events.append(f"{'、'.join(applied_names) or '无人'} 获得迷惑。")
            return 0, status_effect_name, bool(applied_names), actual_target_name

        if base_skill_id == "occultist_arcanize":
            from src.data.jobs import JOBS_BY_ID

            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            target.job = JOBS_BY_ID["arcane"]
            target.gain_health(skill.health_bonus)
            target.attack += skill.attack_bonus
            self._refresh_aura_health_bonuses()
            events.append(f"{target.name} 变为秘法者，获得 +{skill.health_bonus}生命与 +{skill.attack_bonus}攻击力。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "blood_mage_bleed":
            status_effect_name = effect_display_name("bleeding")
            applied_names: list[str] = []
            for area_key in self._same_side_area_keys(target_keys[0]):
                target = self._character_by_key(area_key)
                if self.apply_status_effect(area_key[0], area_key[1], "bleeding", source_key=caster_key):
                    applied_names.append(target.name)
            events.append(f"{'、'.join(applied_names) or '无人'} 获得流血。")
            return 0, status_effect_name, bool(applied_names), actual_target_name

        if base_skill_id == "vanguard_health_boost":
            boosted_names: list[str] = []
            for target_key in self._same_column_adjacent_character_keys(player_id, caster.position, exclude_id=None) if caster.position is not None else []:
                target = self._character_by_key(target_key)
                target.gain_health(skill.health_bonus or 2)
                boosted_names.append(target.name)
            if caster.is_alive:
                caster.gain_health(skill.health_bonus or 2)
                if caster.name not in boosted_names:
                    boosted_names.insert(0, caster.name)
            self.limited_skill_use_counts[(player_id, character_id, base_skill_id)] = (
                self.limited_skill_use_counts.get((player_id, character_id, base_skill_id), 0) + 1
            )
            events.append(f"{'、'.join(boosted_names) or caster.name} 生命 +2。")
            return 0, status_effect_name, status_applied, caster.name

        if base_skill_id == "bell_ringer_armor":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            damage_result = self._resolve_damage(
                moving_player_id=player_id,
                source_key=caster_key,
                target_key=target_key,
                base_damage=1,
                immune_character_keys=(),
                allow_guard=True,
            )
            target.gain_armor(4)
            events.append(f"{target.name} 受到敲钟 {damage_result.damage} 点，并获得 4 点护甲。")
            events.extend(damage_result.events)
            return damage_result.damage, status_effect_name, status_applied, damage_result.receiver_name

        if base_skill_id == "brutal_bomber_distribute":
            damage_by_target: dict[tuple[int, str], int] = {}
            for target_key in target_keys:
                damage_by_target[target_key] = damage_by_target.get(target_key, 0) + 1
            total_damage = 0
            damaged_friendly_keys: set[tuple[int, str]] = set()
            for target_key, assigned_damage in damage_by_target.items():
                target = self._character_by_key(target_key)
                if not target.is_alive:
                    continue
                damage_result = self._resolve_damage(
                    moving_player_id=player_id,
                    source_key=caster_key,
                    target_key=target_key,
                    base_damage=assigned_damage,
                    immune_character_keys=(),
                    allow_guard=True,
                )
                total_damage += damage_result.damage
                if damage_result.damage > 0 and damage_result.receiver_key[0] == player_id:
                    damaged_friendly_keys.add(damage_result.receiver_key)
                events.append(f"{target.name} 被分配 {assigned_damage} 点爆破，实际受到 {damage_result.damage} 点。")
                events.extend(damage_result.events)
            if damaged_friendly_keys and caster.is_alive:
                gain = len(damaged_friendly_keys)
                caster.attack += gain
                events.append(f"{caster.name} 因友方受伤攻击力 +{gain}。")
            return total_damage, status_effect_name, status_applied, caster.name

        if base_skill_id == "gatekeeper_brace":
            caster.add_status_effect("next_damage_reduction_4")
            events.append(f"{caster.name} 下次受到的伤害 -4。")
            return 0, status_effect_name, status_applied, caster.name

        if base_skill_id == "maple_round_attack_gain":
            self.round_attack_modifiers[caster_key] = self.round_attack_modifiers.get(caster_key, 0) + 5
            events.append(f"{caster.name} 本回合攻击力 +5。")
            return 0, status_effect_name, status_applied, caster.name

        if base_skill_id == "charger_leader_mobilize":
            boosted_names: list[str] = []
            for ally in self._battle_characters(player_id):
                ally_key = (player_id, ally.id)
                if not ally.is_alive or ally.position is None or not self._character_counts_as_job(ally_key, "charger"):
                    continue
                self.remaining_moves[ally_key] = self.remaining_moves.get(ally_key, 0) + 1
                boosted_names.append(ally.name)
            events.append(f"{'、'.join(boosted_names) or '无友方冲锋者'} 本回合移动次数 +1。")
            return 0, status_effect_name, status_applied, caster.name

        if base_skill_id == "witch_half_damage":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            base_damage = self._percentage_damage(target.max_health, 50)
            damage_result = self._resolve_damage(
                moving_player_id=player_id,
                source_key=caster_key,
                target_key=target_key,
                base_damage=base_damage,
                immune_character_keys=(),
                allow_guard=True,
            )
            events.append(f"{target.name} 受到巫咒 {damage_result.damage} 点。")
            events.extend(damage_result.events)
            return damage_result.damage, status_effect_name, status_applied, damage_result.receiver_name

        if base_skill_id == "witch_half_heal":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            heal_amount = self._percentage_damage(target.max_health, 50)
            before_health = target.current_health
            target.heal(heal_amount)
            healed = target.current_health - before_health
            events.append(f"{target.name} 恢复 {healed} 点生命。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "pharaoh_curse_all":
            status_effect_name = effect_display_name("cursed")
            applied_names: list[str] = []
            for target_player_id in self.game_state.players:
                for character in self._battle_characters(target_player_id):
                    if not character.is_alive:
                        continue
                    if self.apply_status_effect(target_player_id, character.id, "cursed", source_key=caster_key):
                        applied_names.append(character.name)
            events.append(f"{'、'.join(applied_names) or '无人'} 获得诅咒。")
            return 0, status_effect_name, bool(applied_names), caster.name

        if base_skill_id == "silence_elder_round_silence":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            status_effect_name = effect_display_name("silenced")
            status_applied = self.apply_status_effect(target_key[0], target_key[1], "silenced", source_key=caster_key)
            if status_applied:
                self.round_silenced_character_keys.add(target_key)
                events.append(f"{target.name} 本回合内被沉默。")
            else:
                events.append(f"{target.name} 免疫了沉默。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "silence_elder_bless":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            status_effect_name = effect_display_name("silenced")
            status_applied = self.apply_status_effect(target_key[0], target_key[1], "silenced", source_key=caster_key)
            target.gain_health(skill.health_bonus)
            target.attack += skill.attack_bonus
            events.append(f"{target.name} 被沉默，获得 +{skill.health_bonus}生命与 +{skill.attack_bonus}攻击力。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "baker_guardian_bread":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            target.gain_health(skill.health_bonus)
            target.add_status_effect("row_taunt")
            events.append(f"{target.name} 生命 +{skill.health_bonus}，获得同排嘲讽。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "baker_small_bread":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            target.gain_health(skill.health_bonus)
            before_health = target.current_health
            target.heal(skill.heal)
            healed = target.current_health - before_health
            events.append(f"{target.name} 生命 +{skill.health_bonus}，恢复 {healed} 点生命。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "mentor_gravity_field":
            target_key = target_keys[0]
            gravity_keys = self._same_faction_area_keys(target_key)
            applied_names: list[str] = []
            status_effect_name = effect_display_name("gravity")
            for gravity_key in gravity_keys:
                target = self._character_by_key(gravity_key)
                if self.apply_status_effect(gravity_key[0], gravity_key[1], "gravity", source_key=caster_key):
                    applied_names.append(target.name)
            events.append(f"{'、'.join(applied_names) or '无人'} 获得1层重力。")
            return 0, status_effect_name, bool(applied_names), self._character_by_key(target_key).name

        if base_skill_id == "octopus_summon_tentacle":
            self.pending_summons.append(
                SummonRequest(
                    player_id=player_id,
                    source_name=caster.name,
                    character_definition_id="tentacle",
                )
            )
            events.append(f"{caster.name} 可以召唤触手。")
            return 0, status_effect_name, status_applied, caster.name

        if base_skill_id == "provocation_enrage":
            target_key = target_keys[0]
            target = self._character_by_key(target_key)
            status_effect_name = effect_display_name("enraged")
            status_applied = self.apply_status_effect(target_key[0], target_key[1], "enraged", source_key=caster_key)
            if status_applied:
                self.enrage_sources[target_key] = caster_key
                events.append(f"{target.name} 本回合内获得激怒。")
            else:
                events.append(f"{target.name} 免疫了激怒。")
            return 0, status_effect_name, status_applied, target.name

        if base_skill_id == "artisan_overcharge":
            target_key = target_keys[0]
            lost = self._lose_current_health(caster_key, 3)
            events.append(f"{caster.name} 失去 {lost} 点生命。")
            if not caster.is_alive:
                events.append(f"{caster.name} 因失去生命死亡，后续攻击不触发。")
                return 0, status_effect_name, status_applied, caster.name
            self.round_attack_modifiers[caster_key] = self.round_attack_modifiers.get(caster_key, 0) + 8
            try:
                attack_resolution = self._resolve_attack_with_context(
                    attacker_player_id=player_id,
                    attacker_id=character_id,
                    target_player_id=target_key[0],
                    target_id=target_key[1],
                    attack_percent=100,
                    extra_target_reflect_percent=0,
                )
            finally:
                self.round_attack_modifiers[caster_key] = self.round_attack_modifiers.get(caster_key, 0) - 8
                if self.round_attack_modifiers.get(caster_key) == 0:
                    self.round_attack_modifiers.pop(caster_key, None)
            events.extend(attack_resolution.events)
            return attack_resolution.damage, status_effect_name, status_applied, attack_resolution.actual_target_name

        if base_skill_id == "monkey_summon_bananas":
            summoned_names: list[str] = []
            for row in range(3):
                position = Position(row=row, column=FormationColumn.FRONT)
                if self.game_state.player(player_id).character_at(position) is not None:
                    continue
                summoned = self._summon_character_at(player_id, "banana", position)
                summoned_names.append(summoned.name)
            events.append(f"{caster.name} 召唤香蕉：{'、'.join(summoned_names) or '无空位'}。")
            return 0, status_effect_name, status_applied, caster.name

        return 0, status_effect_name, status_applied, actual_target_name

    def _copyable_active_skill(self, character: Character) -> ActiveSkill | None:
        for skill in character.active_skills:
            if skill.id == "copy_ally_active_skill" or "__copy_" in skill.id:
                continue
            if skill.once_per_game and character.has_used_active_skill(skill.id):
                continue
            return skill
        return None

    def _same_side_area_keys(self, center_key: tuple[int, str]) -> list[tuple[int, str]]:
        player_id, _character_id = center_key
        center = self._character_by_key(center_key)
        keys = [center_key]
        if center.position is not None:
            keys.extend(self._adjacent_character_keys(player_id, center.position, exclude_id=center.id))
        return [
            key
            for key in dict.fromkeys(keys)
            if self._character_by_key(key).is_alive
        ]

    def _same_faction_area_keys(self, center_key: tuple[int, str]) -> list[tuple[int, str]]:
        center = self._character_by_key(center_key)
        center_factions = set(center.factions)
        if not center_factions:
            return [center_key]
        return [
            key
            for key in self._same_side_area_keys(center_key)
            if key == center_key or center_factions.intersection(self._character_by_key(key).factions)
        ]

    def _revenge_piper_enemy_keys(self, player_id: int) -> list[tuple[int, str]]:
        opponent_id = self.game_state.opponent_id(player_id)
        return [
            (opponent_id, character.id)
            for character in self._battle_characters(opponent_id)
            if character.is_alive and self._can_manually_select_target(player_id, (opponent_id, character.id))
        ]

    def _revenge_piper_confused_enemy_keys(self, player_id: int) -> list[tuple[int, str]]:
        return [
            enemy_key
            for enemy_key in self._revenge_piper_enemy_keys(player_id)
            if self._character_by_key(enemy_key).has_status_effect("confused")
        ]

    def _revenge_piper_damage_mode(self, player_id: int) -> bool:
        enemy_keys = self._revenge_piper_enemy_keys(player_id)
        return bool(enemy_keys) and all(self._character_by_key(enemy_key).has_status_effect("confused") for enemy_key in enemy_keys)

    def _lose_current_health(self, character_key: tuple[int, str], amount: int) -> int:
        character = self._character_by_key(character_key)
        if not character.is_alive or amount <= 0:
            return 0
        floor = 1 if self._character_has_battle_effect(character_key, "undying") else 0
        new_health = max(floor, character.current_health - amount)
        lost = character.current_health - new_health
        character.current_health = new_health
        return lost
