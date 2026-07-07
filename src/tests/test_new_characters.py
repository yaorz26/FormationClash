import unittest

from src.core import BattleSession, FormationColumn, FormationError, FormationSession, GamePhase, Position
from src.core.game_state import create_initial_game_state
from src.data.characters import create_character_pool, create_draft_character_pool, create_test_character_pool


def create_new_battle_session(
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


class NewCharacterTests(unittest.TestCase):
    def test_default_pool_uses_new_characters_and_keeps_old_test_pool_separate(self) -> None:
        character_ids = {character.id for character in create_character_pool()}
        test_character_ids = {character.id for character in create_test_character_pool()}

        self.assertIn("prophet", character_ids)
        self.assertIn("battle_mech", character_ids)
        self.assertIn("shadow_ninja", character_ids)
        self.assertIn("little_kun", character_ids)
        self.assertIn("old_turtle", character_ids)
        self.assertIn("cang_xuan_crane", character_ids)
        self.assertNotIn("luna", character_ids)
        self.assertIn("luna", test_character_ids)

    def test_draft_pool_excludes_summons_but_default_pool_keeps_them_for_battle_summons(self) -> None:
        default_ids = {character.id for character in create_character_pool()}
        draft_ids = {character.id for character in create_draft_character_pool()}
        arcanarch_draft_ids = {character.id for character in create_draft_character_pool(include_arcanarch=True)}

        self.assertIn("dream_eater", default_ids)
        self.assertIn("little_skeleton", default_ids)
        self.assertIn("ending", default_ids)
        self.assertIn("sun_guard", default_ids)
        self.assertNotIn("dream_eater", draft_ids)
        self.assertNotIn("little_skeleton", draft_ids)
        self.assertNotIn("ending", draft_ids)
        self.assertNotIn("sun_guard", draft_ids)
        self.assertIn("ending", arcanarch_draft_ids)
        self.assertIn("sun_guard", arcanarch_draft_ids)

    def test_current_new_character_markdown_roles_are_in_default_pool(self) -> None:
        character_ids = {character.id for character in create_character_pool()}

        for character_id in (
            "dogman",
            "white_wolf_king",
            "venom_snake",
            "great_wolf",
            "ninja",
            "fox",
            "ghost_shadow",
            "wind_child",
            "dragon_hunter",
            "snow_wolf",
            "mad_wolf",
            "order_prince",
            "time_wolf_consort",
            "scapegoat",
            "skeleton_king",
            "little_skeleton",
            "totem",
            "stone_lord",
            "wolf_god_statue",
            "super_prophet",
            "lang_qi",
        ):
            self.assertIn(character_id, character_ids)

    def test_dogman_crits_wolves_and_loses_attack_immunity_against_non_wolves(self) -> None:
        battle, _game_state = create_new_battle_session(
            {
                "dogman": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "werewolf": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
            },
        )

        wolf_result = battle.attack(1, "dogman", "werewolf")

        self.assertEqual(wolf_result.damage, 5)
        self.assertTrue(any("暴击" in event for event in wolf_result.events))

        battle, game_state = create_new_battle_session(
            {
                "dogman": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        non_wolf_result = battle.attack(1, "dogman", "villager")

        self.assertEqual(non_wolf_result.damage, 3)
        self.assertEqual(non_wolf_result.reflected_damage, 2)
        self.assertEqual(game_state.player(1).get_character("dogman").current_health, 2)

    def test_wolf_attack_modifiers_poison_and_ninja_critical(self) -> None:
        battle, _game_state = create_new_battle_session(
            {
                "white_wolf_king": Position(row=0, column=FormationColumn.FRONT),
                "dogman": Position(row=1, column=FormationColumn.FRONT),
                "snow_wolf": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        self.assertEqual(battle.effective_attack((1, "white_wolf_king")), 4)

        battle, _game_state = create_new_battle_session(
            {
                "dogman": Position(row=0, column=FormationColumn.FRONT),
                "werewolf": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "great_wolf": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        self.assertEqual(battle.effective_attack((2, "great_wolf")), 2)

        battle, game_state = create_new_battle_session(
            {
                "venom_snake": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        poison_target = game_state.player(2).get_character("advanced_villager")
        poison_result = battle.attack(1, "venom_snake", "advanced_villager")

        self.assertEqual(poison_result.damage, 2)
        self.assertEqual(poison_target.current_health, 5)
        self.assertTrue(any("剧毒" in event for event in poison_result.events))

        battle, game_state = create_new_battle_session(
            {
                "ninja": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        ninja_target = game_state.player(2).get_character("advanced_villager")
        first = battle.attack(1, "ninja", "advanced_villager")

        self.assertEqual(first.damage, 5)
        self.assertEqual(ninja_target.current_health, 5)

        battle.remaining_moves[(1, "ninja")] = 1
        game_state.current_turn_player_id = 1
        second = battle.attack(1, "ninja", "advanced_villager")

        self.assertEqual(second.damage, 3)
        self.assertEqual(ninja_target.current_health, 2)

    def test_fox_ghost_and_wind_child_position_effects(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "fox": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "advanced_villager": Position(row=1, column=FormationColumn.FRONT),
                "priest": Position(row=2, column=FormationColumn.FRONT),
            },
        )

        fox_result = battle.attack(1, "fox", "advanced_villager")

        self.assertEqual(game_state.player(2).get_character("villager").current_health, 5)
        self.assertEqual(game_state.player(2).get_character("priest").current_health, 5)
        self.assertTrue(any("左右溅射" in event for event in fox_result.events))

        isolated_battle, isolated_state = create_new_battle_session(
            {
                "ghost_shadow": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        self.assertFalse(isolated_state.player(1).get_character("ghost_shadow").is_alive)
        self.assertEqual(isolated_battle.game_state.winner_player_id, 2)

        _battle, adjacent_state = create_new_battle_session(
            {
                "ghost_shadow": Position(row=1, column=FormationColumn.FRONT),
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        self.assertTrue(adjacent_state.player(1).get_character("ghost_shadow").is_alive)

        battle, _game_state = create_new_battle_session(
            {
                "wind_child": Position(row=0, column=FormationColumn.FRONT),
                "villager": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "elder": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        battle.attack(1, "wind_child", "elder")

        self.assertEqual(battle.effective_attack((1, "villager")), 3)
        battle._start_next_round()
        self.assertEqual(battle.effective_attack((1, "villager")), 2)

    def test_dragon_hunter_snow_wolf_and_mad_wolf_attack_rules(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "dragon_hunter": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "armed_villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        non_dragon = game_state.player(2).get_character("armed_villager")
        battle.apply_status_effect(2, "armed_villager", "cursed")

        non_dragon_result = battle.attack(1, "dragon_hunter", "armed_villager")

        self.assertEqual(non_dragon_result.damage, 1)
        self.assertEqual(non_dragon.current_health, 1)
        self.assertTrue(non_dragon.is_alive)
        self.assertFalse(any("诅咒死亡" in event for event in non_dragon_result.events))

        battle, game_state = create_new_battle_session(
            {
                "dragon_hunter": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "dragon_mage": Position(row=0, column=FormationColumn.FRONT),
                "commander": Position(row=1, column=FormationColumn.FRONT),
            },
        )
        dragon = game_state.player(2).get_character("dragon_mage")

        dragon_result = battle.attack(1, "dragon_hunter", "dragon_mage")

        self.assertEqual(dragon.current_health, 1)
        self.assertTrue(dragon.has_status_effect("bleeding"))
        self.assertTrue(any("流血" in event for event in dragon_result.events))

        battle, game_state = create_new_battle_session(
            {
                "snow_wolf": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        snow_target = game_state.player(2).get_character("advanced_villager")
        snow_target.current_health = 6

        snow_result = battle.attack(1, "snow_wolf", "advanced_villager")

        self.assertFalse(snow_target.is_alive)
        self.assertTrue(any("消灭" in event for event in snow_result.events))

        battle, game_state = create_new_battle_session(
            {
                "snow_wolf": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
                "paladin": Position(row=1, column=FormationColumn.FRONT),
            },
        )
        guarded_target = game_state.player(2).get_character("advanced_villager")
        guarded_target.current_health = 6

        battle.attack(1, "snow_wolf", "advanced_villager")

        self.assertTrue(guarded_target.is_alive)
        self.assertEqual(guarded_target.current_health, 6)

        battle, game_state = create_new_battle_session(
            {
                "mad_wolf": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "armed_villager": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
            },
        )
        game_state.player(2).get_character("armed_villager").current_health = 1

        mad_result = battle.attack(1, "mad_wolf", "armed_villager")

        self.assertTrue(mad_result.target_defeated)
        self.assertEqual(battle.current_followup_attack(), (1, "mad_wolf"))
        self.assertTrue(battle.can_attack(1, "mad_wolf", "priest"))

    def test_vampire_critically_hits_bleeding_targets(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "vampire": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        target = game_state.player(2).get_character("villager")
        battle.apply_status_effect(2, "villager", "bleeding")

        result = battle.attack(1, "vampire", "villager")

        self.assertEqual(result.damage, 8)
        self.assertEqual(target.current_health, 0)
        self.assertTrue(any("暴击" in event for event in result.events))
        self.assertTrue(any(event.critical for event in result.damage_events))

    def test_undying_ignores_execute_and_keeps_health_floor(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "advanced_villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        villager = game_state.player(1).get_character("villager")
        villager.add_status_effect("undying")

        reduced = battle._reduce_max_health_flat((1, "villager"), 99, source_key=(2, "advanced_villager"))
        executed = battle._execute_character((1, "villager"), (2, "advanced_villager"))

        self.assertEqual(reduced, 5)
        self.assertFalse(executed)
        self.assertEqual(villager.max_health, 1)
        self.assertEqual(villager.current_health, 1)
        self.assertTrue(villager.is_alive)

    def test_forced_turn_order_and_repeat_second_hand_skill(self) -> None:
        battle, _game_state = create_new_battle_session(
            {
                "order_prince": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )
        self.assertEqual(battle.first_player_id, 1)

        battle, _game_state = create_new_battle_session(
            {
                "time_wolf_consort": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=1,
        )
        self.assertEqual(battle.first_player_id, 2)

        battle, _game_state = create_new_battle_session(
            {
                "order_prince": Position(row=0, column=FormationColumn.FRONT),
                "time_wolf_consort": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )
        self.assertEqual(battle.pending_start_order_choice_player_id, 1)
        self.assertIsNone(battle.current_player_id)
        self.assertEqual(battle.first_player_id, 2)

        battle, game_state = create_new_battle_session(
            {
                "time_wolf_consort": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=1,
        )
        game_state.current_turn_player_id = 1

        self.assertTrue(battle.can_use_second_hand_skill(1))
        battle.use_second_hand_skill(1)
        self.assertFalse(battle.can_use_second_hand_skill(1))

        battle._start_next_round()

        self.assertFalse(game_state.player(1).second_hand_skill_used)
        game_state.current_turn_player_id = 1
        self.assertTrue(battle.can_use_second_hand_skill(1))

    def test_order_prince_and_time_wolf_consort_choose_start_order_before_battle_start(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "order_prince": Position(row=0, column=FormationColumn.FRONT),
                "time_wolf_consort": Position(row=1, column=FormationColumn.FRONT),
                "mirror": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )

        self.assertEqual(battle.pending_start_order_choice_player_id, 1)
        self.assertIsNone(game_state.battle_first_player_id)
        self.assertIsNone(game_state.current_turn_player_id)
        self.assertFalse(battle.pending_death_triggers)

        result = battle.choose_start_order(1, choose_first=False)

        self.assertEqual(result.first_player_name, "玩家2")
        self.assertEqual(result.second_player_name, "玩家1")
        self.assertEqual(battle.first_player_id, 2)
        self.assertEqual(game_state.battle_first_player_id, 2)
        self.assertTrue(game_state.player(1).has_second_hand_skill)
        self.assertFalse(game_state.player(2).has_second_hand_skill)
        self.assertEqual(battle.pending_death_triggers[0].kind, "mirror_copy")
        self.assertEqual(game_state.current_turn_player_id, 1)

    def test_new_guardians_summons_death_triggers_and_active_skills(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "scapegoat": Position(row=0, column=FormationColumn.BACK),
                "advanced_villager": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "mage": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )
        protected = game_state.player(1).get_character("advanced_villager")

        battle.attack(2, "mage", "advanced_villager")

        self.assertEqual(protected.current_health, 8)

        game_state.player(1).get_character("scapegoat").current_health = 0
        game_state.current_turn_player_id = 2
        battle.remaining_moves[(2, "mage")] = 1
        battle.attack(2, "mage", "advanced_villager")

        self.assertEqual(protected.current_health, 6)

        battle, game_state = create_new_battle_session(
            {
                "cang_xuan_crane": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "skeleton_king": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
            },
        )
        game_state.player(2).get_character("skeleton_king").current_health = 5
        skeleton_position = Position(row=0, column=FormationColumn.FRONT)

        skeleton_result = battle.attack(1, "cang_xuan_crane", "skeleton_king")

        self.assertTrue(skeleton_result.target_defeated)
        self.assertEqual(game_state.player(2).character_at(skeleton_position).id, "little_skeleton")

        battle, game_state = create_new_battle_session(
            {
                "mage": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "totem": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        totem = game_state.player(2).get_character("totem")

        first = battle.attack(1, "mage", "totem")
        self.assertEqual(first.damage, 0)
        self.assertEqual(totem.current_health, 10)

        battle.remaining_moves[(1, "mage")] = 1
        game_state.current_turn_player_id = 1
        second = battle.attack(1, "mage", "totem")
        self.assertEqual(second.damage, 3)
        self.assertEqual(totem.current_health, 7)

        battle._start_next_round()
        battle.remaining_moves[(1, "mage")] = 1
        game_state.current_turn_player_id = 1
        third = battle.attack(1, "mage", "totem")
        self.assertEqual(third.damage, 0)
        self.assertEqual(totem.current_health, 7)

        battle, game_state = create_new_battle_session(
            {
                "stone_lord": Position(row=0, column=FormationColumn.BACK),
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        villager = game_state.player(1).get_character("villager")

        battle.cast_skill(1, "stone_lord", "stone_lord_guardianize", "villager")

        self.assertEqual(villager.job.id, "guardian")
        self.assertEqual(villager.max_health, 8)
        self.assertEqual(villager.current_health, 8)

        _battle, game_state = create_new_battle_session(
            {
                "wolf_god_statue": Position(row=0, column=FormationColumn.BACK),
                "dogman": Position(row=0, column=FormationColumn.FRONT),
                "snow_wolf": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        statue = game_state.player(1).get_character("wolf_god_statue")

        self.assertEqual(statue.max_health, 14)
        self.assertEqual(statue.current_health, 14)

        battle, game_state = create_new_battle_session(
            {
                "cang_xuan_crane": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "super_prophet": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        game_state.player(2).get_character("super_prophet").current_health = 5

        battle.attack(1, "cang_xuan_crane", "super_prophet")

        trigger = battle.current_death_trigger()
        self.assertIsNotNone(trigger)
        assert trigger is not None
        self.assertEqual(trigger.kind, "attack_buff")

        battle.resolve_death_trigger("cang_xuan_crane")

        self.assertEqual(game_state.player(1).get_character("cang_xuan_crane").attack, 8)

    def test_lang_qi_attacks_once_per_lost_health_up_to_seven_times(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "lang_qi": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        lang_qi = game_state.player(1).get_character("lang_qi")
        lang_qi.max_health = 10
        lang_qi.current_health = 3

        result = battle.cast_skill(1, "lang_qi", "lang_qi_flurry", "priest")

        self.assertEqual(sum("第1次攻击" in event for event in result.events), 1)
        self.assertEqual(result.damage, 0)
        self.assertEqual(battle.current_followup_attack(), (1, "lang_qi"))
        self.assertEqual(battle.current_followup_remaining_attacks(), 6)

        lang_qi.current_health = lang_qi.max_health
        for expected_remaining in (5, 4, 3, 2, 1, 0):
            followup = battle.attack(1, "lang_qi", "priest")
            self.assertEqual(followup.damage, 0)
            self.assertEqual(battle.current_followup_remaining_attacks(), expected_remaining)

        self.assertIsNone(battle.current_followup_attack())
        self.assertEqual(battle.remaining_move_count(1, "lang_qi"), 0)

    def test_shadow_ninja_grants_executor_attack_immunity_aura(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "shadow_ninja": Position(row=1, column=FormationColumn.FRONT),
                "demon": Position(row=0, column=FormationColumn.FRONT),
            },
            first_player_id=2,
        )

        self.assertTrue(battle._character_has_battle_effect((2, "shadow_ninja"), "attack_immunity"))
        self.assertTrue(battle._character_has_battle_effect((2, "demon"), "attack_immunity"))

        result = battle.attack(2, "demon", "villager")

        self.assertEqual(result.reflected_damage, 0)
        self.assertEqual(game_state.player(2).get_character("demon").current_health, 3)

    def test_one_shot_new_character_skills_are_limited(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "stone_lord": Position(row=0, column=FormationColumn.BACK),
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        battle.cast_skill(1, "stone_lord", "stone_lord_guardianize", "villager")
        battle.remaining_moves[(1, "stone_lord")] = 1
        game_state.current_turn_player_id = 1

        self.assertFalse(battle.can_cast_skill(1, "stone_lord", "stone_lord_guardianize", "villager"))

    def test_prophet_once_skill_buffs_any_character_attack(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "prophet": Position(row=0, column=FormationColumn.BACK),
            },
            {
                "werewolf": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        target = game_state.player(2).get_character("werewolf")

        result = battle.cast_skill(1, "prophet", "prophesy", "werewolf")

        self.assertEqual(result.skill_name, "预言")
        self.assertEqual(target.attack, 9)
        self.assertIn("werewolf", {character.id for character in battle.skill_targets(1, "prophet", "prophesy")})

        battle.remaining_moves[(1, "prophet")] = 1
        game_state.current_turn_player_id = 1
        self.assertFalse(battle.can_cast_skill(1, "prophet", "prophesy", "werewolf"))

    def test_werewolf_gains_attack_when_all_battle_allies_are_wolves(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "werewolf": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        self.assertEqual(game_state.player(1).get_character("werewolf").attack, 6)
        self.assertEqual(battle.effective_attack((1, "werewolf")), 6)

    def test_werewolf_does_not_gain_attack_with_non_wolf_battle_ally(self) -> None:
        _battle, game_state = create_new_battle_session(
            {
                "werewolf": Position(row=0, column=FormationColumn.FRONT),
                "villager": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        self.assertEqual(game_state.player(1).get_character("werewolf").attack, 4)

    def test_guard_armor_absorbs_damage_until_next_round(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "guard": Position(row=0, column=FormationColumn.FRONT),
                "villager": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "werewolf": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        target = game_state.player(1).get_character("guard")

        battle.cast_skill(1, "guard", "grant_armor", "guard")

        self.assertEqual(target.armor, 6)
        game_state.current_turn_player_id = 2
        result = battle.attack(2, "werewolf", "guard")

        self.assertEqual(result.damage, 6)
        self.assertEqual(target.current_health, target.max_health)
        self.assertEqual(target.armor, 0)

        battle._start_next_round()
        self.assertEqual(target.armor, 0)

    def test_holy_archer_splashes_to_other_enemy_in_same_row(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "holy_archer": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "vampire": Position(row=0, column=FormationColumn.FRONT),
                "mage": Position(row=0, column=FormationColumn.BACK),
            },
        )
        primary = game_state.player(2).get_character("vampire")
        splash = game_state.player(2).get_character("mage")

        result = battle.attack(1, "holy_archer", "vampire")

        self.assertEqual(primary.current_health, primary.max_health - 1)
        self.assertEqual(splash.current_health, splash.max_health - 1)
        self.assertTrue(any("溅射" in event for event in result.events))

    def test_hunter_death_trigger_can_damage_any_living_character(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "mage": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "hunter": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        hunter = game_state.player(2).get_character("hunter")
        hunter.current_health = 3

        attack_result = battle.attack(1, "mage", "hunter")

        self.assertTrue(attack_result.target_defeated)
        self.assertIsNotNone(battle.current_death_trigger())
        self.assertEqual(game_state.current_turn_player_id, 2)

        mage = game_state.player(1).get_character("mage")
        trigger_result = battle.resolve_death_trigger("mage")

        self.assertEqual(trigger_result.source_name, "猎人")
        self.assertEqual(trigger_result.damage, 2)
        self.assertEqual(mage.current_health, mage.max_health - 2)
        self.assertIsNone(battle.current_death_trigger())

    def test_paladin_ignores_first_fatal_damage_once(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "demon": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "paladin": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        paladin = game_state.player(2).get_character("paladin")
        paladin.current_health = 4

        first = battle.attack(1, "demon", "paladin")

        self.assertEqual(first.damage, 0)
        self.assertEqual(paladin.current_health, 4)
        self.assertTrue(paladin.has_used_passive_effect("first_fatal_immunity"))

        battle.remaining_moves[(1, "demon")] = 1
        game_state.current_turn_player_id = 1
        second = battle.attack(1, "demon", "paladin")

        self.assertGreater(second.damage, 0)
        self.assertFalse(paladin.is_alive)

    def test_bear_and_battle_mech_auras_update_effective_stats(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "bear": Position(row=0, column=FormationColumn.FRONT),
                "battle_mech": Position(row=1, column=FormationColumn.FRONT),
                "villager": Position(row=2, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        villager = game_state.player(1).get_character("villager")

        self.assertEqual(villager.max_health, 9)
        self.assertEqual(villager.current_health, 9)
        self.assertEqual(battle.effective_attack((1, "villager")), 5)

        mech = game_state.player(1).get_character("battle_mech")
        mech.take_damage(99)
        battle._refresh_aura_health_bonuses()

        self.assertEqual(villager.max_health, 6)
        self.assertEqual(villager.current_health, 6)
        self.assertEqual(battle.effective_attack((1, "villager")), 2)

    def test_dragon_wing_grants_same_row_friend_backline_attack(self) -> None:
        battle, _ = create_new_battle_session(
            {
                "dragon_wing": Position(row=0, column=FormationColumn.BACK),
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "vampire": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=0, column=FormationColumn.BACK),
            },
        )

        target_ids = {target.id for target in battle.attackable_targets(1, "villager")}

        self.assertIn("priest", target_ids)

    def test_assassin_can_choose_second_attack_after_first_kills_taunter(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "assassin": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "guard": Position(row=0, column=FormationColumn.FRONT),
                "prophet": Position(row=0, column=FormationColumn.BACK),
            },
        )
        guard = game_state.player(2).get_character("guard")
        guard.current_health = 2

        first = battle.attack(1, "assassin", "guard")

        self.assertTrue(first.target_defeated)
        self.assertEqual(battle.current_followup_attack(), (1, "assassin"))
        self.assertEqual(game_state.current_turn_player_id, 1)
        self.assertTrue(battle.can_attack(1, "assassin", "prophet"))

        second = battle.attack(1, "assassin", "prophet")

        self.assertEqual(second.damage, 2)
        self.assertIsNone(battle.current_followup_attack())
        self.assertEqual(game_state.player(2).get_character("prophet").current_health, 2)
        self.assertEqual(battle.remaining_move_count(1, "assassin"), 0)

    def test_assassin_first_kill_resolves_death_trigger_before_second_attack(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "assassin": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "hunter": Position(row=0, column=FormationColumn.FRONT),
                "prophet": Position(row=0, column=FormationColumn.BACK),
            },
        )
        hunter = game_state.player(2).get_character("hunter")
        hunter.current_health = 2

        first = battle.attack(1, "assassin", "hunter")

        self.assertTrue(first.target_defeated)
        self.assertEqual(battle.current_followup_attack(), (1, "assassin"))
        self.assertIsNotNone(battle.current_death_trigger())
        self.assertEqual(game_state.current_turn_player_id, 2)

        trigger = battle.resolve_death_trigger(None)

        self.assertTrue(trigger.skipped)
        self.assertIsNone(battle.current_death_trigger())
        self.assertEqual(game_state.current_turn_player_id, 1)
        self.assertTrue(battle.can_attack(1, "assassin", "prophet"))

    def test_shadow_ninja_grants_stealth_to_executors_and_blocks_manual_enemy_targets(self) -> None:
        battle, _game_state = create_new_battle_session(
            {
                "cang_xuan_crane": Position(row=0, column=FormationColumn.FRONT),
                "prophet": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "shadow_ninja": Position(row=1, column=FormationColumn.FRONT),
                "demon": Position(row=0, column=FormationColumn.FRONT),
            },
        )

        attack_target_ids = {target.id for target in battle.attackable_targets(1, "cang_xuan_crane")}
        skill_target_ids = {target.id for target in battle.skill_targets(1, "prophet", "prophesy")}

        self.assertNotIn("demon", attack_target_ids)
        self.assertIn("shadow_ninja", attack_target_ids)
        self.assertNotIn("demon", skill_target_ids)

    def test_stealth_only_side_is_defeated_but_shadow_ninja_death_removes_aura_first(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "cang_xuan_crane": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "shadow_ninja": Position(row=0, column=FormationColumn.FRONT),
                "demon": Position(row=1, column=FormationColumn.FRONT),
            },
        )
        shadow_ninja = game_state.player(2).get_character("shadow_ninja")

        self.assertTrue(battle._character_has_battle_effect((2, "demon"), "stealth"))

        result = battle.attack(1, "cang_xuan_crane", "shadow_ninja")

        self.assertTrue(result.target_defeated)
        self.assertFalse(battle._character_has_battle_effect((2, "demon"), "stealth"))
        self.assertFalse(shadow_ninja.is_alive)
        self.assertIsNone(result.winner_player_id)

        game_state.player(2).get_character("demon").add_status_effect("stealth")
        self.assertEqual(battle._check_winner(), 1)

    def test_stealthed_executor_can_still_take_splash_damage(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "holy_archer": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "mage": Position(row=0, column=FormationColumn.BACK),
            },
        )
        mage = game_state.player(2).get_character("mage")
        mage.add_status_effect("stealth")

        battle.attack(1, "holy_archer", "villager")

        self.assertEqual(mage.current_health, mage.max_health - 1)

    def test_little_kun_relocates_without_consuming_moves(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "little_kun": Position(row=0, column=FormationColumn.FRONT),
                "villager": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "priest": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        target_position = Position(row=2, column=FormationColumn.BACK)

        self.assertTrue(battle.can_relocate_character(1, "little_kun", target_position))
        result = battle.relocate_character(1, "little_kun", target_position)

        self.assertEqual(result.actor_name, "小鲲")
        self.assertEqual(game_state.player(1).get_character("little_kun").position, target_position)
        self.assertEqual(battle.remaining_move_count(1, "little_kun"), 1)
        self.assertEqual(game_state.current_turn_player_id, 1)
        self.assertFalse(battle.can_relocate_character(1, "little_kun", Position(row=1, column=FormationColumn.FRONT)))

    def test_little_kun_has_same_rank_taunt(self) -> None:
        battle, _game_state = create_new_battle_session(
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "little_kun": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
            },
        )

        target_ids = {target.id for target in battle.attackable_targets(1, "villager")}

        self.assertEqual(target_ids, {"little_kun"})

    def test_old_turtle_is_front_only_taunts_and_protects_allies(self) -> None:
        game_state = create_initial_game_state()
        old_turtle = {character.id: character for character in create_character_pool()}["old_turtle"]
        game_state.player(1).add_character(old_turtle)
        game_state.phase = GamePhase.FORMATION
        formation = FormationSession(game_state)
        with self.assertRaises(FormationError):
            formation.place_character(1, "old_turtle", Position(row=0, column=FormationColumn.BACK))

        battle, game_state = create_new_battle_session(
            {
                "holy_archer": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "old_turtle": Position(row=0, column=FormationColumn.FRONT),
                "paladin": Position(row=1, column=FormationColumn.FRONT),
                "prophet": Position(row=0, column=FormationColumn.BACK),
            },
        )
        prophet = game_state.player(2).get_character("prophet")

        target_ids = {target.id for target in battle.attackable_targets(1, "holy_archer")}
        result = battle.attack(1, "holy_archer", "old_turtle")

        self.assertEqual(target_ids, {"old_turtle"})
        self.assertEqual(result.actual_target_name, "老王八")
        self.assertEqual(prophet.current_health, prophet.max_health)
        self.assertTrue(any("预言家 受到溅射 0 点" in event for event in result.events))

        battle._start_next_round()
        round_two_damage = battle._resolve_damage(
            moving_player_id=1,
            source_key=(1, "holy_archer"),
            target_key=(2, "prophet"),
            base_damage=1,
            immune_character_keys=(),
            allow_guard=False,
        )

        self.assertEqual(round_two_damage.damage, 1)
        self.assertEqual(prophet.current_health, prophet.max_health - 1)

    def test_old_turtle_taunt_is_same_priority_as_other_taunts(self) -> None:
        battle, _game_state = create_new_battle_session(
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "old_turtle": Position(row=0, column=FormationColumn.FRONT),
                "guard": Position(row=1, column=FormationColumn.FRONT),
                "paladin": Position(row=2, column=FormationColumn.FRONT),
            },
        )

        target_ids = {target.id for target in battle.attackable_targets(1, "villager")}

        self.assertEqual(target_ids, {"old_turtle", "guard"})

    def test_cang_xuan_crane_clears_target_buffs_during_attack(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "cang_xuan_crane": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "swordsman": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        swordsman = game_state.player(2).get_character("swordsman")
        swordsman.attack += 3
        swordsman.armor = 4

        result = battle.attack(1, "cang_xuan_crane", "swordsman")

        self.assertEqual(result.reflected_damage, 0)
        self.assertEqual(swordsman.attack, swordsman.base_attack)
        self.assertEqual(swordsman.armor, 0)
        self.assertFalse(swordsman.is_alive)

    def test_cang_xuan_crane_targets_lowest_attack_and_ignores_taunt(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "cang_xuan_crane": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "old_turtle": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.BACK),
                "armed_villager": Position(row=2, column=FormationColumn.FRONT),
            },
        )
        game_state.player(2).get_character("old_turtle").attack = 3

        target_ids = {target.id for target in battle.attackable_targets(1, "cang_xuan_crane")}

        self.assertEqual(target_ids, {"priest"})

    def test_cang_xuan_crane_temporarily_suppresses_battle_mech_aura_then_it_returns(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "cang_xuan_crane": Position(row=0, column=FormationColumn.FRONT),
            },
            {
                "battle_mech": Position(row=0, column=FormationColumn.FRONT),
                "villager": Position(row=1, column=FormationColumn.FRONT),
            },
        )
        villager = game_state.player(2).get_character("villager")

        self.assertEqual(villager.max_health, 9)
        self.assertEqual(villager.current_health, 9)
        self.assertEqual(battle.effective_attack((2, "villager")), 5)

        battle.attack(1, "cang_xuan_crane", "battle_mech")

        self.assertEqual(villager.max_health, 9)
        self.assertEqual(villager.current_health, 9)
        self.assertEqual(battle.effective_attack((2, "villager")), 5)


if __name__ == "__main__":
    unittest.main()
