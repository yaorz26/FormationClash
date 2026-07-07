import unittest

from src.core import BattleSession, FormationColumn, FormationSession, GamePhase, Position
from src.core.game_state import create_initial_game_state
from src.data.characters import create_character_pool


def create_stage_three_battle(
    player_one_positions: dict[str, Position],
    player_two_positions: dict[str, Position],
    *,
    first_player_id: int = 1,
) -> tuple[BattleSession, object]:
    game_state = create_initial_game_state()
    characters = {character.id: character for character in create_character_pool()}
    for character_id in player_one_positions:
        game_state.player(1).add_character(characters[character_id])
    for character_id in player_two_positions:
        game_state.player(2).add_character(characters[character_id])

    game_state.phase = GamePhase.FORMATION
    formation = FormationSession(game_state)
    for character_id, position in player_one_positions.items():
        formation.place_character(1, character_id, position)
    formation.confirm_player_formation(1)
    for character_id, position in player_two_positions.items():
        formation.place_character(2, character_id, position)
    formation.confirm_player_formation(2)

    return BattleSession(game_state, first_player_id=first_player_id), game_state


class StageThreeCharacterTests(unittest.TestCase):
    def test_new_character_pool_contains_stage_three_characters(self) -> None:
        character_ids = {character.id for character in create_character_pool()}

        for character_id in (
            "arsonist",
            "saintess",
            "heavenly_eye",
            "ghost_bride",
            "dreamer",
            "dream_eater",
            "crow",
            "spirit_fountain",
            "advanced_villager",
            "armed_villager",
            "ghost_knight",
            "rust_sword_knight",
            "elf",
            "giant_guard",
            "commander",
            "bomber",
            "fire_god",
            "stone_golem",
            "dragon_mage",
            "eternal_wolf_bone",
            "wolf_godfather",
            "gravekeeper",
            "dragon_will",
            "siege_cart",
            "shield_mage",
            "magic_guard",
            "bulwark",
            "dual_blade_knight",
            "lumberjack",
            "fire_wolf",
            "wolf_king",
            "charge",
            "dragon_intermediate_mage",
            "magic_wolf",
            "sword_saint",
            "angel",
            "sekiro",
            "alchemist",
            "saintly_priest",
            "revenge_piper",
            "dragon_reinforcement",
            "occultist",
            "formation_master",
            "blood_mage",
            "mirror",
            "penguin",
            "artisan",
            "naughty_monkey",
            "banana",
            "alloy_batter",
            "dragon_claw",
            "battle_priest",
            "werewolf_prophet",
            "glacier",
            "spider",
            "life_fountain",
        ):
            self.assertIn(character_id, character_ids)

    def test_bugfix_updates_gravekeeper_health_and_character_factions(self) -> None:
        characters = {character.id: character for character in create_character_pool()}

        self.assertEqual(characters["gravekeeper"].max_health, 8)

        expected_factions = {
            "crow": "自然",
            "fire_god": "自然",
            "stone_golem": "自然",
            "venom_snake": "自然",
            "fox": "自然",
            "wind_child": "自然",
            "totem": "自然",
            "scapegoat": "自然",
            "bear": "自然",
            "stone_lord": "自然",
            "old_turtle": "自然",
            "little_kun": "自然",
            "cang_xuan_crane": "自然",
            "spirit_fountain": "圣职",
            "priest": "圣职",
            "holy_archer": "圣职",
            "paladin": "圣职",
            "angel": "圣职",
            "mage": "奥术",
            "super_prophet": "奥术",
            "eternal_wolf_bone": "狼",
        }
        for character_id, faction in expected_factions.items():
            self.assertIn(faction, characters[character_id].factions)

    def test_charge_makes_back_positions_count_as_front_during_formation(self) -> None:
        game_state = create_initial_game_state()
        characters = {character.id: character for character in create_character_pool()}
        game_state.player(1).add_character(characters["charge"])
        game_state.player(1).add_character(characters["paladin"])
        game_state.phase = GamePhase.FORMATION
        formation = FormationSession(game_state)

        formation.place_character(1, "charge", Position(row=0, column=FormationColumn.FRONT))
        formation.place_character(1, "paladin", Position(row=1, column=FormationColumn.BACK))

        self.assertEqual(characters["paladin"].position, Position(row=1, column=FormationColumn.BACK))

    def test_new_adjacent_auras_and_start_passives(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "wolf_godfather": Position(row=1, column=FormationColumn.FRONT),
                "werewolf": Position(row=0, column=FormationColumn.FRONT),
                "wolf_king": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        werewolf = game_state.player(1).get_character("werewolf")

        self.assertEqual(werewolf.max_health, 4)
        self.assertGreaterEqual(battle.effective_attack((1, "werewolf")), 5)

        dragon_battle, dragon_state = create_stage_three_battle(
            {
                "dragon_will": Position(row=1, column=FormationColumn.FRONT),
                "prophet": Position(row=1, column=FormationColumn.BACK),
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "rider": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        dragon_will = dragon_state.player(1).get_character("dragon_will")

        self.assertIsNotNone(dragon_battle)
        self.assertEqual(dragon_will.max_health, 16)

    def test_magic_guard_becomes_guardian_when_two_arcane_allies_exist(self) -> None:
        _battle, game_state = create_stage_three_battle(
            {
                "magic_guard": Position(row=0, column=FormationColumn.FRONT),
                "prophet": Position(row=1, column=FormationColumn.FRONT),
                "mage": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        magic_guard = game_state.player(1).get_character("magic_guard")

        self.assertEqual(magic_guard.job.id, "guardian")
        self.assertEqual(magic_guard.max_health, 16)

    def test_multiple_guards_each_take_damage_and_bulwark_blocks_backline_attacks(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "mage": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=1, column=FormationColumn.FRONT),
                "paladin": Position(row=0, column=FormationColumn.FRONT),
                "bulwark": Position(row=2, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.BACK),
            },
        )
        target = game_state.player(2).get_character("advanced_villager")
        paladin = game_state.player(2).get_character("paladin")
        bulwark = game_state.player(2).get_character("bulwark")

        result = battle.attack(1, "mage", "advanced_villager")

        self.assertEqual(target.current_health, target.max_health)
        self.assertLess(paladin.current_health, paladin.max_health)
        self.assertLess(bulwark.current_health, bulwark.max_health)
        self.assertTrue(any("抵御" in event for event in result.events))

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "mage")] = 1
        game_state.player(1).get_character("mage").passive_effect_ids = ("backline_attack",)

        self.assertNotIn("priest", {target.id for target in battle.attackable_targets(1, "mage")})

    def test_shield_mage_creates_barrier_before_guard_and_absorbs_overflow(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "bulwark": Position(row=1, column=FormationColumn.FRONT),
                "shield_mage": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "dual_blade_knight": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        battle.cast_skill(1, "shield_mage", "create_shield_barrier", "shield_mage")
        self.assertIsNone(battle.current_summon_request())
        self.assertEqual(battle.team_barrier_amount(1), 12)
        villager = game_state.player(1).get_character("villager")
        bulwark = game_state.player(1).get_character("bulwark")
        villager_health = villager.current_health
        bulwark_health = bulwark.current_health

        game_state.current_turn_player_id = 2
        battle.remaining_moves[(2, "dual_blade_knight")] = 1
        result = battle.attack(2, "dual_blade_knight", "villager")

        self.assertEqual(villager.current_health, villager_health)
        self.assertEqual(bulwark.current_health, bulwark_health)
        self.assertEqual(battle.team_barrier_amount(1), 5)
        self.assertTrue(any("屏障" in event for event in result.events))

        battle.team_barriers[1] = 3

        result = battle._resolve_damage(
            moving_player_id=2,
            source_key=(2, "dual_blade_knight"),
            target_key=(1, "villager"),
            base_damage=7,
            immune_character_keys=(),
            allow_guard=True,
        )

        self.assertEqual(result.damage, 0)
        self.assertEqual(villager.current_health, villager_health)
        self.assertEqual(battle.team_barrier_amount(1), 0)
        self.assertTrue(any("溢出伤害" in event for event in result.events))

    def test_shield_barrier_breaks_and_damages_all_allies(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "shield_mage": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "dual_blade_knight": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        villager = game_state.player(1).get_character("villager")
        shield_mage = game_state.player(1).get_character("shield_mage")
        battle.team_barriers[1] = 1
        battle.team_barrier_sources[1] = (1, "shield_mage")

        result = battle._resolve_damage(
            moving_player_id=2,
            source_key=(2, "dual_blade_knight"),
            target_key=(1, "villager"),
            base_damage=7,
            immune_character_keys=(),
            allow_guard=True,
        )

        self.assertEqual(result.damage, 0)
        self.assertEqual(villager.current_health, villager.max_health - 1)
        self.assertEqual(shield_mage.current_health, shield_mage.max_health - 1)
        self.assertTrue(any("屏障被击破" in event for event in result.events))

    def test_immunity_resolves_before_barrier(self) -> None:
        battle, _game_state = create_stage_three_battle(
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "shield_mage": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "dual_blade_knight": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        battle.team_barriers[1] = 12

        result = battle._resolve_damage(
            moving_player_id=2,
            source_key=(2, "dual_blade_knight"),
            target_key=(1, "villager"),
            base_damage=7,
            immune_character_keys=((1, "villager"),),
            allow_guard=True,
        )

        self.assertEqual(result.damage, 0)
        self.assertEqual(battle.team_barrier_amount(1), 12)
        self.assertTrue(any("免疫" in event for event in result.events))
        self.assertFalse(any("屏障" in event for event in result.events))

    def test_dragon_mage_copies_skills_and_magic_wolf_restores_used_limited_skills(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "dragon_intermediate_mage": Position(row=0, column=FormationColumn.FRONT),
                "prophet": Position(row=1, column=FormationColumn.FRONT),
                "magic_wolf": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        dragon = game_state.player(1).get_character("dragon_intermediate_mage")
        prophet = game_state.player(1).get_character("prophet")

        battle.cast_skill(1, "dragon_intermediate_mage", "copy_ally_active_skill", "prophet")
        copied_skill = next(skill for skill in dragon.active_skills if skill.id.startswith("prophesy__copy_"))
        self.assertTrue(copied_skill.once_per_game)

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "dragon_intermediate_mage")] = 1
        battle.cast_skill(1, "dragon_intermediate_mage", copied_skill.id, "dragon_intermediate_mage")
        self.assertTrue(dragon.has_used_active_skill(copied_skill.id))

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "prophet")] = 1
        battle.cast_skill(1, "prophet", "prophesy", "dragon_intermediate_mage")
        self.assertTrue(prophet.has_used_active_skill("prophesy"))

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "magic_wolf")] = 1
        battle.cast_skill(1, "magic_wolf", "restore_arcane_limited_skills", "magic_wolf")

        self.assertFalse(prophet.has_used_active_skill("prophesy"))

    def test_dragon_mage_copies_non_limited_skill_as_reusable(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "dragon_intermediate_mage": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        dragon = game_state.player(1).get_character("dragon_intermediate_mage")

        battle.cast_skill(1, "dragon_intermediate_mage", "copy_ally_active_skill", "priest")
        copied_skill = next(skill for skill in dragon.active_skills if skill.id.startswith("heal_target__copy_"))

        self.assertFalse(copied_skill.once_per_game)

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "dragon_intermediate_mage")] = 1
        battle.cast_skill(1, "dragon_intermediate_mage", copied_skill.id, "dragon_intermediate_mage")
        self.assertFalse(dragon.has_used_active_skill(copied_skill.id))
        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "dragon_intermediate_mage")] = 1
        self.assertTrue(battle.can_cast_skill(1, "dragon_intermediate_mage", copied_skill.id, "dragon_intermediate_mage"))

    def test_executor_and_hero_new_attack_mechanics(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "lumberjack": Position(row=0, column=FormationColumn.FRONT),
                "villager": Position(row=0, column=FormationColumn.BACK),
                "fire_wolf": Position(row=1, column=FormationColumn.FRONT),
                "sword_saint": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
                "mage": Position(row=1, column=FormationColumn.BACK),
            },
        )
        lumberjack = game_state.player(1).get_character("lumberjack")
        lumberjack.current_health = 3

        lumber = battle.attack(1, "lumberjack", "advanced_villager")
        self.assertTrue(any("暴击" in event for event in lumber.events))

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "fire_wolf")] = 1
        fire = battle.attack(1, "fire_wolf", "priest")
        self.assertTrue(any("溅射" in event for event in fire.events))

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "sword_saint")] = 1
        sword = battle.attack(1, "sword_saint", "advanced_villager")
        self.assertEqual(battle.current_sword_saint_choice(), (1, "sword_saint"))
        self.assertTrue(any("剑圣" in event for event in sword.events))

        choice = battle.resolve_sword_saint_choice("inspire")

        self.assertEqual(battle.current_followup_attack(), (1, "sword_saint"))
        self.assertTrue(any("鼓舞" in event for event in choice.events))

    def test_sekiro_unselectable_undying_and_chase(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "sekiro": Position(row=0, column=FormationColumn.FRONT),
                "villager": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )

        self.assertNotIn("sekiro", {target.id for target in battle.attackable_targets(2, "advanced_villager")})
        damage_result = battle._resolve_damage(
            moving_player_id=2,
            source_key=(2, "advanced_villager"),
            target_key=(1, "sekiro"),
            base_damage=99,
            immune_character_keys=(),
            allow_guard=False,
        )
        sekiro = game_state.player(1).get_character("sekiro")
        self.assertEqual(damage_result.damage, 0)
        self.assertTrue(sekiro.is_alive)

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "sekiro")] = 1
        result = battle.attack(1, "sekiro", "advanced_villager")
        self.assertIsNotNone(battle.current_chase_choice())
        self.assertIn("priest", {target.id for target in battle.chase_targets()})

        chase = battle.resolve_chase_target("priest")

        self.assertTrue(any("追击" in event for event in result.events))
        self.assertEqual(chase.target_name, "牧师")
        self.assertTrue(any("追击" in event for event in chase.events))

    def test_saintess_aura_purifies_adverse_effects(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "saintess": Position(row=1, column=FormationColumn.FRONT),
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "crow": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )
        villager = game_state.player(1).get_character("villager")

        self.assertEqual(villager.max_health, 8)
        self.assertEqual(battle.effective_attack((1, "villager")), 3)

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "saintess")] = 1
        battle.apply_status_effect(1, "villager", "bleeding")
        villager.current_health = 3

        battle.cast_skill(1, "saintess", "purify_allies", ["villager"])

        self.assertFalse(villager.has_status_effect("bleeding"))
        self.assertEqual(villager.current_health, 5)

    def test_heavenly_eye_executes_one_other_ally_and_buffs_another(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "heavenly_eye": Position(row=0, column=FormationColumn.BACK),
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "advanced_villager": Position(row=1, column=FormationColumn.FRONT),
                "armed_villager": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        sacrifice = game_state.player(1).get_character("villager")
        target = game_state.player(1).get_character("advanced_villager")

        battle.cast_skill(1, "heavenly_eye", "heavenly_eye", ["villager", "advanced_villager"])

        self.assertFalse(sacrifice.is_alive)
        self.assertEqual(target.attack, 5)
        self.assertEqual(target.max_health, 14)
        self.assertEqual(target.current_health, 14)

        battle.remaining_moves[(1, "heavenly_eye")] = 1
        game_state.current_turn_player_id = 1
        self.assertFalse(battle.can_cast_skill(1, "heavenly_eye", "heavenly_eye", ["advanced_villager", "armed_villager"]))

    def test_dreamer_mark_adds_damage_and_summons_dream_eater_on_death(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "dreamer": Position(row=0, column=FormationColumn.BACK),
                "mage": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "armed_villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        target = game_state.player(2).get_character("armed_villager")

        battle.cast_skill(1, "dreamer", "dream_bind", "armed_villager")
        self.assertTrue(target.has_status_effect("dream_mark"))

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "mage")] = 1
        result = battle.attack(1, "mage", "armed_villager")

        self.assertFalse(target.is_alive)
        self.assertTrue(any("受伤 +2" in event for event in result.events))
        self.assertIsNotNone(battle.current_summon_request())

        summon_result = battle.resolve_summon(Position(row=1, column=FormationColumn.FRONT))
        summoned = game_state.player(1).get_character("dream_eater")

        self.assertEqual(summon_result.summoned_name, "食梦者")
        self.assertEqual(summoned.position, Position(row=1, column=FormationColumn.FRONT))

    def test_curse_executes_character_at_half_health_or_less(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "crow": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        target = game_state.player(2).get_character("advanced_villager")
        target.current_health = 5

        battle.cast_skill(1, "crow", "curse_target", "advanced_villager")

        self.assertFalse(target.is_alive)

    def test_attack_passives_for_arson_rust_fire_stone_and_bomber(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "arsonist": Position(row=0, column=FormationColumn.FRONT),
                "rust_sword_knight": Position(row=1, column=FormationColumn.FRONT),
                "fire_god": Position(row=2, column=FormationColumn.FRONT),
                "stone_golem": Position(row=0, column=FormationColumn.BACK),
            },
            {
                "armed_villager": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
                "advanced_villager": Position(row=2, column=FormationColumn.FRONT),
            },
        )
        adjacent = game_state.player(2).get_character("priest")

        arson = battle.attack(1, "arsonist", "armed_villager")
        self.assertTrue(any("纵火" in event for event in arson.events))
        self.assertEqual(adjacent.current_health, adjacent.max_health - 1)

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "rust_sword_knight")] = 1
        rust_target = game_state.player(2).get_character("advanced_villager")
        battle.attack(1, "rust_sword_knight", "advanced_villager")
        self.assertEqual(rust_target.max_health, 7)

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "fire_god")] = 1
        self.assertEqual(battle.effective_attack((1, "fire_god")), 3)

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "stone_golem")] = 1
        stone = game_state.player(1).get_character("stone_golem")
        stone_result = battle.attack(1, "stone_golem", "priest")
        self.assertEqual(stone_result.damage, 2)
        self.assertEqual(stone.max_health, 8)

    def test_rust_sword_knight_reflect_damage_triggers_max_health_cut(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "rust_sword_knight": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        attacker = game_state.player(1).get_character("advanced_villager")

        result = battle.attack(1, "advanced_villager", "rust_sword_knight")

        self.assertEqual(result.reflected_damage, 2)
        self.assertEqual(attacker.max_health, 7)
        self.assertEqual(attacker.current_health, 7)
        self.assertIn("高级村民 生命上限 -3。", result.events)

    def test_ghost_knight_silences_killer_and_bomber_hits_killer_row(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "arsonist": Position(row=0, column=FormationColumn.FRONT),
                "prophet": Position(row=0, column=FormationColumn.BACK),
            },
            {
                "ghost_knight": Position(row=0, column=FormationColumn.FRONT),
                "bomber": Position(row=1, column=FormationColumn.FRONT),
            },
        )

        battle.attack(1, "arsonist", "ghost_knight")
        self.assertTrue(game_state.player(1).get_character("arsonist").has_status_effect("silenced"))

        game_state.player(1).get_character("arsonist").remove_status_effect("silenced")
        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "arsonist")] = 1
        bomber_result = battle.attack(1, "arsonist", "bomber")

        self.assertTrue(any("死亡爆炸" in event for event in bomber_result.events))
        self.assertLess(game_state.player(1).get_character("prophet").current_health, game_state.player(1).get_character("prophet").max_health)

    def test_commander_and_dragon_mage_aura_stats(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "commander": Position(row=0, column=FormationColumn.FRONT),
                "dragon_mage": Position(row=1, column=FormationColumn.FRONT),
                "prophet": Position(row=1, column=FormationColumn.BACK),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        dragon = game_state.player(1).get_character("dragon_mage")

        self.assertEqual(dragon.max_health, 6)
        self.assertEqual(battle.effective_attack((1, "dragon_mage")), 5)
        self.assertTrue(battle._character_counts_as_job((1, "dragon_mage"), "arcane"))

    def test_eternal_wolf_bone_revives_on_its_next_move_and_can_revive_repeatedly(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "cang_xuan_crane": Position(row=0, column=FormationColumn.FRONT),
                "villager": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "eternal_wolf_bone": Position(row=0, column=FormationColumn.FRONT),
                "demon": Position(row=1, column=FormationColumn.FRONT),
            },
        )

        result = battle.attack(1, "cang_xuan_crane", "eternal_wolf_bone")

        self.assertTrue(result.target_defeated)
        self.assertIsNone(result.winner_player_id)
        self.assertIn((2, "eternal_wolf_bone"), battle.pending_revivals)
        self.assertTrue(battle.can_character_move(2, "eternal_wolf_bone"))

        wolf_bone = game_state.player(2).get_character("eternal_wolf_bone")
        wolf_bone.job = game_state.player(2).get_character("demon").job
        wolf_bone.attack = 99
        wolf_bone.max_health = 7
        wolf_bone.current_health = 0
        wolf_bone.armor = 2
        wolf_bone.passive_effect_ids = ()
        wolf_bone.active_effect_ids = ("dummy_effect",)
        wolf_bone.active_skills = ()
        wolf_bone.add_status_effect("bleeding")
        wolf_bone.add_status_effect("shield")
        wolf_bone.use_active_skill("dummy_skill")
        wolf_bone.mark_passive_effect_used("eternal_revival")
        battle.shield_stacks[(2, "eternal_wolf_bone")] = 3
        battle.round_attack_modifiers[(2, "eternal_wolf_bone")] = 5
        battle.damage_threshold_totals[(2, "eternal_wolf_bone")] = 6
        battle.damage_threshold_trigger_counts[(2, "eternal_wolf_bone")] = 1

        revive_attack = battle.attack(2, "eternal_wolf_bone", "cang_xuan_crane")

        self.assertTrue(wolf_bone.is_alive)
        self.assertEqual(wolf_bone.max_health, wolf_bone.base_max_health)
        self.assertEqual(wolf_bone.current_health, wolf_bone.base_max_health)
        self.assertEqual(wolf_bone.attack, wolf_bone.base_attack)
        self.assertEqual(wolf_bone.job, wolf_bone.base_job)
        self.assertEqual(wolf_bone.passive_effect_ids, wolf_bone.base_passive_effect_ids)
        self.assertEqual(wolf_bone.active_effect_ids, wolf_bone.base_active_effect_ids)
        self.assertEqual(wolf_bone.active_skills, wolf_bone.base_active_skills)
        self.assertEqual(wolf_bone.armor, 0)
        self.assertFalse(wolf_bone.status_effect_ids)
        self.assertFalse(wolf_bone.used_active_skill_ids)
        self.assertFalse(wolf_bone.used_passive_effect_ids)
        self.assertNotIn((2, "eternal_wolf_bone"), battle.shield_stacks)
        self.assertNotIn((2, "eternal_wolf_bone"), battle.round_attack_modifiers)
        self.assertNotIn((2, "eternal_wolf_bone"), battle.damage_threshold_totals)
        self.assertNotIn((2, "eternal_wolf_bone"), battle.damage_threshold_trigger_counts)
        self.assertTrue(any("复活" in event for event in revive_attack.events))

        second_death = battle.attack(1, "villager", "eternal_wolf_bone")

        self.assertTrue(second_death.target_defeated)
        self.assertIsNone(second_death.winner_player_id)
        self.assertIn((2, "eternal_wolf_bone"), battle.pending_revivals)

    def test_eternal_wolf_bone_does_not_prevent_defeat_when_it_is_last_ally(self) -> None:
        battle, _game_state = create_stage_three_battle(
            {
                "cang_xuan_crane": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "eternal_wolf_bone": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        result = battle.attack(1, "cang_xuan_crane", "eternal_wolf_bone")

        self.assertTrue(result.target_defeated)
        self.assertEqual(result.winner_player_id, 1)

    def test_ending_after_attack_and_revival_turn_is_consumed(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "ending": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "elder": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        ending = game_state.player(1).get_character("ending")

        battle.attack(1, "ending", "elder")

        self.assertEqual(ending.current_health, 2)
        self.assertEqual(ending.max_health, 2)
        self.assertEqual(ending.attack, 14)

        battle, game_state = create_stage_three_battle(
            {
                "ending": Position(row=0, column=FormationColumn.FRONT),
                "advanced_villager": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "armed_villager": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )

        battle.attack(2, "armed_villager", "ending")

        self.assertIn((1, "ending"), battle.pending_revivals)
        self.assertTrue(battle.can_character_move(1, "ending"))
        self.assertTrue(battle.can_revive_character(1, "ending"))
        self.assertFalse(battle.can_attack(1, "ending", "armed_villager"))
        self.assertTrue(battle.can_skip_move(1, "ending"))

        skip_result = battle.skip_move(1, "ending")

        ending = game_state.player(1).get_character("ending")
        self.assertFalse(ending.is_alive)
        self.assertEqual(battle.remaining_move_count(1, "ending"), 0)
        self.assertIn((1, "ending"), battle.pending_revivals)
        self.assertFalse(any("复活" in event for event in skip_result.events))

        battle, game_state = create_stage_three_battle(
            {
                "ending": Position(row=0, column=FormationColumn.FRONT),
                "advanced_villager": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "armed_villager": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )
        battle.attack(2, "armed_villager", "ending")
        ending = game_state.player(1).get_character("ending")
        ending.attack = 99
        ending.max_health = 1
        ending.current_health = 0
        ending.armor = 4
        ending.add_status_effect("bleeding")
        ending.add_status_effect("shield")
        ending.use_active_skill("dummy_skill")
        ending.mark_passive_effect_used("ending_after_attack")
        battle.shield_stacks[(1, "ending")] = 2
        battle.round_attack_modifiers[(1, "ending")] = -3

        revive_result = battle.revive_character(1, "ending")

        self.assertTrue(ending.is_alive)
        self.assertEqual(ending.max_health, ending.base_max_health)
        self.assertEqual(ending.current_health, ending.base_max_health)
        self.assertEqual(ending.attack, ending.base_attack)
        self.assertEqual(ending.armor, 0)
        self.assertFalse(ending.status_effect_ids)
        self.assertFalse(ending.used_active_skill_ids)
        self.assertFalse(ending.used_passive_effect_ids)
        self.assertNotIn((1, "ending"), battle.shield_stacks)
        self.assertNotIn((1, "ending"), battle.round_attack_modifiers)
        self.assertEqual(battle.remaining_move_count(1, "ending"), 0)
        self.assertNotIn((1, "ending"), battle.pending_revivals)
        self.assertTrue(any("复活" in event for event in revive_result.events))

    def test_sun_guard_reduces_damage_and_shield_resolves_before_barrier(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "sun_guard": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "armed_villager": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )
        sun_guard = game_state.player(1).get_character("sun_guard")

        damage_result = battle._resolve_damage(
            moving_player_id=2,
            source_key=(2, "armed_villager"),
            target_key=(1, "sun_guard"),
            base_damage=4,
            immune_character_keys=(),
            allow_guard=True,
        )

        self.assertEqual(damage_result.damage, 2)
        self.assertEqual(sun_guard.current_health, 10)
        self.assertEqual(battle.shield_stack_count((1, "sun_guard")), 1)

        battle.team_barriers[1] = 12
        shield_result = battle._resolve_damage(
            moving_player_id=2,
            source_key=(2, "armed_villager"),
            target_key=(1, "sun_guard"),
            base_damage=4,
            immune_character_keys=(),
            allow_guard=True,
        )

        self.assertEqual(shield_result.damage, 0)
        self.assertEqual(battle.shield_stack_count((1, "sun_guard")), 0)
        self.assertEqual(battle.team_barrier_amount(1), 12)

        battle.apply_status_effect(1, "sun_guard", "shield")
        zero_result = battle._resolve_damage(
            moving_player_id=2,
            source_key=(2, "armed_villager"),
            target_key=(1, "sun_guard"),
            base_damage=0,
            immune_character_keys=(),
            allow_guard=True,
        )

        self.assertEqual(zero_result.damage, 0)
        self.assertEqual(battle.shield_stack_count((1, "sun_guard")), 1)

    def test_shield_is_after_immunity_and_damage_reductions_are_independent(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "sun_guard": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "armed_villager": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )
        sun_guard = game_state.player(1).get_character("sun_guard")
        sun_guard.add_status_effect("immunity")
        battle.apply_status_effect(1, "sun_guard", "shield")

        immune_result = battle._resolve_damage(
            moving_player_id=2,
            source_key=(2, "armed_villager"),
            target_key=(1, "sun_guard"),
            base_damage=4,
            immune_character_keys=(),
            allow_guard=True,
        )

        self.assertEqual(immune_result.damage, 0)
        self.assertEqual(battle.shield_stack_count((1, "sun_guard")), 1)

        sun_guard.remove_status_effect("immunity")
        battle._consume_shield((1, "sun_guard"))
        sun_guard.add_status_effect("damage_reduction_1")

        reduced_result = battle._resolve_damage(
            moving_player_id=2,
            source_key=(2, "armed_villager"),
            target_key=(1, "sun_guard"),
            base_damage=5,
            immune_character_keys=(),
            allow_guard=True,
        )

        self.assertEqual(reduced_result.damage, 1)

    def test_latest_arcane_area_skills_and_blood_mage_bleeding_rules(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "alchemist": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=1, column=FormationColumn.FRONT),
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "armed_villager": Position(row=1, column=FormationColumn.BACK),
            },
        )

        result = battle.cast_skill(1, "alchemist", "alchemist_life_blast", "advanced_villager")

        self.assertEqual(result.damage, 6)
        self.assertEqual(game_state.player(2).get_character("advanced_villager").current_health, 7)
        self.assertEqual(game_state.player(2).get_character("villager").current_health, 4)
        self.assertEqual(game_state.player(2).get_character("armed_villager").current_health, 1)

        battle, game_state = create_stage_three_battle(
            {
                "blood_mage": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "old_turtle": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        old_turtle = game_state.player(2).get_character("old_turtle")

        battle.cast_skill(1, "blood_mage", "blood_mage_bleed", "old_turtle")

        self.assertTrue(old_turtle.has_status_effect("bleeding"))
        self.assertEqual(battle._purify_character((2, "old_turtle")), [])
        self.assertTrue(old_turtle.has_status_effect("bleeding"))

    def test_revenge_piper_confuses_then_damages_confused_enemies(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "revenge_piper": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "advanced_villager": Position(row=1, column=FormationColumn.FRONT),
            },
        )

        confuse = battle.cast_skill(1, "revenge_piper", "revenge_piper_song", ["villager", "advanced_villager"])

        self.assertTrue(game_state.player(2).get_character("villager").has_status_effect("confused"))
        self.assertTrue(game_state.player(2).get_character("advanced_villager").has_status_effect("confused"))
        self.assertTrue(confuse.status_applied)

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "revenge_piper")] = 1
        self.assertTrue(battle.can_cast_skill(1, "revenge_piper", "revenge_piper_song"))
        self.assertEqual(battle.skill_targets(1, "revenge_piper", "revenge_piper_song"), [])
        damage = battle.cast_skill(1, "revenge_piper", "revenge_piper_song", None)

        self.assertEqual(damage.damage, 8)
        self.assertEqual(damage.target_name, "所有迷惑敌人")
        self.assertEqual(game_state.player(2).get_character("villager").current_health, 2)
        self.assertEqual(game_state.player(2).get_character("advanced_villager").current_health, 6)

    def test_formation_master_occultist_and_mirror_mechanics(self) -> None:
        battle, _game_state = create_stage_three_battle(
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "formation_master": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        battle.move_orders[1] = ["villager", "formation_master"]
        battle.round_resolved_order_slots[1] = set()
        battle.remaining_moves[(1, "villager")] = 1
        battle.remaining_moves[(1, "formation_master")] = 1

        self.assertTrue(battle.can_character_move(1, "formation_master"))

        battle, game_state = create_stage_three_battle(
            {
                "occultist": Position(row=0, column=FormationColumn.FRONT),
                "guard": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        guard = game_state.player(1).get_character("guard")

        battle.cast_skill(1, "occultist", "occultist_arcanize", "guard")

        self.assertEqual(guard.job.id, "arcane")
        self.assertEqual(guard.max_health, 10)
        self.assertEqual(guard.attack, 3)
        self.assertFalse(battle._character_has_battle_effect((1, "guard"), "row_taunt"))

        battle, _game_state = create_stage_three_battle(
            {
                "glacier": Position(row=0, column=FormationColumn.FRONT),
                "mirror": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )

        mirror_trigger = battle.current_death_trigger()
        self.assertIsNotNone(mirror_trigger)
        assert mirror_trigger is not None
        self.assertEqual(mirror_trigger.kind, "mirror_copy")
        self.assertEqual(battle.current_player_id, 1)
        self.assertFalse(battle.can_resolve_death_trigger(None))
        self.assertFalse(battle.can_resolve_death_trigger("priest"))
        self.assertIn("glacier", {target.id for target in battle.death_trigger_targets()})
        self.assertFalse(battle._character_has_battle_effect((1, "mirror"), "freeze_on_attack"))

        battle.resolve_death_trigger("glacier")

        self.assertTrue(battle._character_has_battle_effect((1, "mirror"), "freeze_on_attack"))
        self.assertFalse(battle._character_has_battle_effect((1, "mirror"), "backline_attack"))
        self.assertIsNone(battle.current_death_trigger())
        self.assertEqual(battle.current_player_id, 2)

    def test_artisan_and_monkey_active_skills(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "artisan": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        artisan = game_state.player(1).get_character("artisan")

        result = battle.cast_skill(1, "artisan", "artisan_overcharge", "priest")

        self.assertEqual(artisan.current_health, 1)
        self.assertEqual(result.damage, 10)
        self.assertFalse(game_state.player(2).get_character("priest").is_alive)

        battle, game_state = create_stage_three_battle(
            {
                "naughty_monkey": Position(row=0, column=FormationColumn.BACK),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        battle.cast_skill(1, "naughty_monkey", "monkey_summon_bananas", "naughty_monkey")

        front_ids = {
            game_state.player(1).character_at(Position(row=row, column=FormationColumn.FRONT)).id
            for row in range(3)
        }
        self.assertEqual(front_ids, {"banana", "banana_1", "banana_2"})

    def test_latest_attack_and_damage_passives(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "mage": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "alloy_batter": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        batter = game_state.player(2).get_character("alloy_batter")

        battle._resolve_damage(
            moving_player_id=1,
            source_key=(1, "mage"),
            target_key=(2, "alloy_batter"),
            base_damage=3,
            immune_character_keys=(),
            allow_guard=False,
        )

        self.assertEqual(batter.attack, 4)

        battle, _game_state = create_stage_three_battle(
            {
                "dragon_claw": Position(row=0, column=FormationColumn.FRONT),
                "dragon_mage": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        self.assertEqual(battle.effective_attack((1, "dragon_mage")), 4)

        battle, game_state = create_stage_three_battle(
            {
                "battle_priest": Position(row=0, column=FormationColumn.FRONT),
                "villager": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        game_state.player(1).get_character("villager").current_health = 3

        battle.attack(1, "battle_priest", "priest")
        heal_trigger = battle.current_death_trigger()
        self.assertIsNotNone(heal_trigger)
        assert heal_trigger is not None
        self.assertEqual(heal_trigger.kind, "heal")
        battle.resolve_death_trigger("villager")
        self.assertEqual(game_state.player(1).get_character("villager").current_health, 6)

        battle, game_state = create_stage_three_battle(
            {
                "werewolf_prophet": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        battle._resolve_damage(
            moving_player_id=1,
            source_key=(1, "werewolf_prophet"),
            target_key=(2, "advanced_villager"),
            base_damage=6,
            immune_character_keys=(),
            allow_guard=False,
        )
        prophecy = battle.current_death_trigger()
        self.assertIsNotNone(prophecy)
        assert prophecy is not None
        self.assertEqual(prophecy.kind, "damage_prophecy")
        battle.resolve_death_trigger("werewolf_prophet")
        self.assertEqual(game_state.player(1).get_character("werewolf_prophet").attack, 6)

        battle, game_state = create_stage_three_battle(
            {
                "glacier": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        battle.attack(1, "glacier", "priest")
        self.assertTrue(game_state.player(2).get_character("priest").has_status_effect("frozen"))

        battle, game_state = create_stage_three_battle(
            {
                "spider": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        battle.attack(1, "spider", "advanced_villager")
        spider_target = game_state.player(2).get_character("advanced_villager")
        self.assertEqual(spider_target.current_health, 6)
        self.assertEqual(spider_target.max_health, 6)

    def test_new_character3_pool_contains_latest_characters(self) -> None:
        character_ids = {character.id for character in create_character_pool()}

        for character_id in (
            "fearless",
            "vanguard",
            "flanker",
            "bell_ringer",
            "thunder",
            "brutal_bomber",
            "gatekeeper",
            "maple",
            "charger_leader",
            "snake_fang",
            "witch",
            "pharaoh",
            "silence_elder",
            "baker",
            "mentor",
            "menace",
            "octopus",
            "tentacle",
            "provocation",
        ):
            self.assertIn(character_id, character_ids)

    def test_fearless_refunds_attacks_against_non_taunters_only_three_times(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "fearless": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "spirit_fountain": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
            },
        )

        for _index in range(3):
            game_state.current_turn_player_id = 1
            battle.attack(1, "fearless", "spirit_fountain")
            self.assertEqual(battle.remaining_move_count(1, "fearless"), 2)

        game_state.current_turn_player_id = 1
        battle.attack(1, "fearless", "spirit_fountain")
        self.assertEqual(battle.remaining_move_count(1, "fearless"), 1)

        taunt_battle, taunt_state = create_stage_three_battle(
            {
                "fearless": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "guard": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
            },
        )
        taunt_state.current_turn_player_id = 1
        taunt_battle.attack(1, "fearless", "guard")
        self.assertEqual(taunt_battle.remaining_move_count(1, "fearless"), 1)

    def test_thunder_attack_deals_same_rank_max_health_damage(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "thunder": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
                "spirit_fountain": Position(row=0, column=FormationColumn.BACK),
            },
        )

        result = battle.attack(1, "thunder", "advanced_villager")

        self.assertEqual(result.damage, 5)
        self.assertEqual(game_state.player(2).get_character("advanced_villager").current_health, 7)
        self.assertEqual(game_state.player(2).get_character("priest").current_health, 4)
        self.assertEqual(game_state.player(2).get_character("spirit_fountain").current_health, 8)

    def test_brutal_bomber_groups_duplicate_damage_and_counts_damaged_allies(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "brutal_bomber": Position(row=0, column=FormationColumn.FRONT),
                "giant_guard": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        result = battle.cast_skill(
            1,
            "brutal_bomber",
            "brutal_bomber_distribute",
            ["giant_guard", "giant_guard", "giant_guard", "priest", "priest", "priest", "priest", "priest"],
        )

        self.assertEqual(result.damage, 7)
        self.assertEqual(game_state.player(1).get_character("giant_guard").current_health, 6)
        self.assertEqual(game_state.player(1).get_character("brutal_bomber").attack, 2)

    def test_gravity_weak_and_enraged_targeting_rules(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "provocation": Position(row=0, column=FormationColumn.BACK),
                "guard": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "prophet": Position(row=1, column=FormationColumn.FRONT),
            },
        )
        battle.apply_status_effect(2, "villager", "gravity")
        battle.apply_status_effect(2, "villager", "gravity")
        self.assertEqual(battle.gravity_stack_count((2, "villager")), 2)
        battle.apply_status_effect(2, "villager", "weak")
        self.assertEqual(battle.effective_attack((2, "villager"), (1, "guard")), 1)
        game_state.player(2).get_character("villager").remove_status_effect("weak")

        game_state.current_turn_player_id = 1
        battle.cast_skill(1, "provocation", "provocation_enrage", "villager")
        forced_targets = {target.id for target in battle.attackable_targets(2, "villager")}
        self.assertEqual(forced_targets, {"provocation"})

        result = battle.attack(2, "villager", "provocation")
        self.assertEqual(result.damage, 1)
        self.assertEqual(battle._reflect_percent_for_attack((2, "villager"), (1, "provocation")), 100)

    def test_mentor_adds_gravity_to_enemy_that_kills_ally(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "mentor": Position(row=1, column=FormationColumn.FRONT),
                "armed_villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "mage": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )

        battle.attack(2, "mage", "armed_villager")

        self.assertTrue(game_state.player(2).get_character("mage").has_status_effect("gravity"))
        self.assertEqual(battle.gravity_stack_count((2, "mage")), 1)

    def test_octopus_summons_tentacle_that_can_move_immediately(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "octopus": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        result = battle.cast_skill(1, "octopus", "octopus_summon_tentacle", None)
        self.assertIsNone(result.winner_player_id)
        self.assertTrue(battle.can_resolve_summon(Position(row=1, column=FormationColumn.FRONT)))

        summon_result = battle.resolve_summon(Position(row=1, column=FormationColumn.FRONT))

        self.assertEqual(summon_result.next_player_id, 1)
        tentacle = game_state.player(1).get_character("tentacle")
        self.assertTrue(tentacle.is_alive)
        self.assertGreater(battle.remaining_move_count(1, "tentacle"), 0)

    def test_vanguard_skill_can_be_used_at_most_four_times(self) -> None:
        battle, game_state = create_stage_three_battle(
            {
                "vanguard": Position(row=1, column=FormationColumn.FRONT),
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "armed_villager": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        for _index in range(4):
            game_state.current_turn_player_id = 1
            battle.remaining_moves[(1, "vanguard")] = 1
            self.assertTrue(battle.can_cast_skill(1, "vanguard", "vanguard_health_boost", "vanguard"))
            battle.cast_skill(1, "vanguard", "vanguard_health_boost", "vanguard")

        game_state.current_turn_player_id = 1
        battle.remaining_moves[(1, "vanguard")] = 1
        self.assertFalse(battle.can_cast_skill(1, "vanguard", "vanguard_health_boost", "vanguard"))


if __name__ == "__main__":
    unittest.main()
