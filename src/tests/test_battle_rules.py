import unittest

from src.core import BattleError, BattleSession, DraftSession, Effect, EffectCategory, FormationColumn, FormationSession, GamePhase, Position
from src.core.game_state import create_initial_game_state
from src.data.characters import create_test_character_pool as create_character_pool
from src.data.keywords import EFFECTS_BY_ID


def create_battle_session(first_player_id: int = 1) -> tuple[BattleSession, object]:
    game_state = create_initial_game_state()
    character_pool = create_character_pool()
    draft = DraftSession(game_state, character_pool, first_player_id=1)

    for character in character_pool[:12]:
        draft.select_character(character.id)

    formation = FormationSession(game_state)
    formation.place_character(1, "luna", Position(row=0, column=FormationColumn.FRONT))
    formation.place_character(1, "morgan", Position(row=1, column=FormationColumn.BACK))
    formation.place_character(1, "duran", Position(row=1, column=FormationColumn.FRONT))
    formation.place_character(1, "maker", Position(row=2, column=FormationColumn.BACK))
    formation.place_character(1, "sable", Position(row=2, column=FormationColumn.FRONT))
    formation.confirm_player_formation(1)

    formation.place_character(2, "brant", Position(row=0, column=FormationColumn.BACK))
    formation.place_character(2, "kira", Position(row=0, column=FormationColumn.FRONT))
    formation.place_character(2, "iris", Position(row=1, column=FormationColumn.BACK))
    formation.place_character(2, "voss", Position(row=1, column=FormationColumn.FRONT))
    formation.place_character(2, "spark", Position(row=2, column=FormationColumn.BACK))
    formation.place_character(2, "naya", Position(row=2, column=FormationColumn.FRONT))
    formation.confirm_player_formation(2)

    return BattleSession(game_state, first_player_id=first_player_id), game_state


def create_hero_battle_session(first_player_id: int = 2) -> tuple[BattleSession, object]:
    game_state = create_initial_game_state()
    character_pool = create_character_pool()
    draft = DraftSession(game_state, character_pool, first_player_id=1)

    for character in character_pool[:12]:
        draft.select_character(character.id)

    formation = FormationSession(game_state)
    formation.place_character(1, "orion", Position(row=0, column=FormationColumn.FRONT))
    formation.confirm_player_formation(1)

    formation.place_character(2, "voss", Position(row=0, column=FormationColumn.FRONT))
    formation.confirm_player_formation(2)

    return BattleSession(game_state, first_player_id=first_player_id), game_state


class BattleSessionTests(unittest.TestCase):
    def test_battle_starts_with_first_player_and_round_moves(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)

        self.assertEqual(game_state.phase, GamePhase.BATTLE)
        self.assertEqual(game_state.round_number, 1)
        self.assertEqual(game_state.current_turn_player_id, 2)
        self.assertEqual(game_state.battle_first_player_id, 2)
        self.assertFalse(game_state.player(2).has_second_hand_skill)
        self.assertTrue(game_state.player(1).has_second_hand_skill)
        self.assertFalse(game_state.player(1).second_hand_skill_used)
        self.assertEqual(battle.remaining_move_count(2, "iris"), 2)

    def test_unplaced_characters_do_not_participate_in_battle(self) -> None:
        battle, _ = create_battle_session(first_player_id=2)

        self.assertEqual(battle.remaining_move_count(1, "orion"), 0)
        self.assertNotIn("orion", {character.id for character in battle.available_actors(1)})
        self.assertNotIn("orion", {target.id for target in battle.attackable_targets(2, "kira")})

    def test_default_attack_must_target_living_front_first(self) -> None:
        battle, _ = create_battle_session(first_player_id=1)

        target_ids = {target.id for target in battle.attackable_targets(1, "luna")}

        self.assertIn("kira", target_ids)
        self.assertIn("voss", target_ids)
        self.assertIn("naya", target_ids)
        self.assertNotIn("brant", target_ids)
        self.assertFalse(battle.can_attack(1, "luna", "brant"))

    def test_back_targets_become_legal_when_no_living_front_exists(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        for character_id in ("kira", "voss", "naya"):
            character = game_state.player(2).get_character(character_id)
            character.take_damage(character.max_health)

        target_ids = {target.id for target in battle.attackable_targets(1, "luna")}

        self.assertEqual(target_ids, {"brant", "iris", "spark"})
        self.assertTrue(battle.can_attack(1, "luna", "brant"))

    def test_raider_can_attack_backline_while_front_is_alive(self) -> None:
        battle, _ = create_battle_session(first_player_id=2)

        target_ids = {target.id for target in battle.attackable_targets(2, "kira")}

        self.assertIn("morgan", target_ids)
        self.assertNotIn("maker", target_ids)
        self.assertTrue(battle.can_attack(2, "kira", "morgan"))

    def test_attack_deals_damage_and_rotates_turn(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        target = game_state.player(2).get_character("kira")

        result = battle.attack(1, "luna", "kira")

        self.assertEqual(result.damage, 3)
        self.assertEqual(target.current_health, target.max_health - 3)
        self.assertEqual(battle.remaining_move_count(1, "luna"), 0)
        self.assertEqual(game_state.current_turn_player_id, 2)

    def test_reflect_damages_non_immune_attacker_after_attack_damage(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        for character_id in ("kira", "voss", "naya"):
            character = game_state.player(2).get_character(character_id)
            character.take_damage(character.max_health)
        game_state.player(1).get_character("duran").take_damage(99)
        attacker = game_state.player(1).get_character("luna")
        target = game_state.player(2).get_character("brant")

        result = battle.attack(1, "luna", "brant")

        self.assertEqual(result.damage, 3)
        self.assertEqual(result.reflected_damage, 3)
        self.assertEqual(target.current_health, target.max_health - 3)
        self.assertEqual(attacker.current_health, attacker.max_health - 3)

    def test_attack_that_kills_target_still_triggers_reflect(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        for character_id in ("kira", "voss", "naya"):
            character = game_state.player(2).get_character(character_id)
            character.take_damage(character.max_health)
        game_state.player(1).get_character("duran").take_damage(99)
        attacker = game_state.player(1).get_character("luna")
        target = game_state.player(2).get_character("brant")
        target.current_health = 1

        result = battle.attack(1, "luna", "brant")

        self.assertTrue(result.target_defeated)
        self.assertEqual(result.reflected_damage, target.attack)
        self.assertEqual(attacker.current_health, attacker.max_health - target.attack)
        self.assertIn("布兰特 反伤 3 点。", result.events)

    def test_raider_is_immune_to_reflect_while_attacking(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        game_state.player(1).get_character("duran").take_damage(99)
        attacker = game_state.player(1).get_character("sable")
        target = game_state.player(2).get_character("brant")

        result = battle.attack(1, "sable", "brant")

        self.assertEqual(result.reflected_damage, 0)
        self.assertEqual(target.current_health, target.max_health - attacker.attack)
        self.assertEqual(attacker.current_health, attacker.max_health)

    def test_charger_grants_target_reflect_for_this_attack(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        game_state.player(1).get_character("duran").take_damage(99)
        attacker = game_state.player(2).get_character("iris")
        target = game_state.player(1).get_character("luna")

        result = battle.attack(2, "iris", "luna")

        self.assertEqual(result.damage, 3)
        self.assertEqual(result.reflected_damage, 2)
        self.assertEqual(target.current_health, target.max_health - 3)
        self.assertEqual(attacker.current_health, attacker.max_health - 2)

    def test_guardian_taunts_same_front_or_back_rank_targets(self) -> None:
        battle, _ = create_battle_session(first_player_id=2)

        target_ids = {target.id for target in battle.attackable_targets(2, "kira")}

        self.assertIn("morgan", target_ids)
        self.assertNotIn("maker", target_ids)
        self.assertIn("duran", target_ids)
        self.assertFalse(battle.can_attack(2, "kira", "maker"))
        self.assertTrue(battle.can_attack(2, "kira", "duran"))

    def test_silence_does_not_disable_job_effects(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        guardian = game_state.player(1).get_character("morgan")

        self.assertTrue(battle.apply_status_effect(1, "morgan", "silenced"))

        target_ids = {target.id for target in battle.attackable_targets(2, "kira")}
        self.assertTrue(guardian.has_status_effect("silenced"))
        self.assertIn("morgan", target_ids)
        self.assertNotIn("maker", target_ids)
        self.assertFalse(battle.can_attack(2, "kira", "maker"))

    def test_defender_redirects_adjacent_friend_damage(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        guardian = game_state.player(1).get_character("morgan")
        defender = game_state.player(1).get_character("duran")

        result = battle.attack(2, "kira", "morgan")

        self.assertEqual(result.actual_target_name, "杜兰")
        self.assertEqual(result.damage, 4)
        self.assertEqual(guardian.current_health, guardian.max_health)
        self.assertEqual(defender.current_health, defender.max_health - 4)

    def test_immunity_is_resolved_before_guard_redirect(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        immune_target = game_state.player(1).get_character("morgan")
        defender = game_state.player(1).get_character("duran")
        attacker = game_state.player(2).get_character("kira")
        immune_target.passive_effect_ids = ("immunity",)

        result = battle.attack(2, "kira", "morgan")

        self.assertEqual(result.actual_target_name, "摩根")
        self.assertEqual(result.damage, 0)
        self.assertEqual(immune_target.current_health, immune_target.max_health)
        self.assertEqual(defender.current_health, defender.max_health)
        self.assertIn(f"{immune_target.name} 免疫了 {attacker.attack} 点伤害。", result.events)
        self.assertFalse(any("抵御" in event for event in result.events))

    def test_guard_redirects_damage_but_reflect_uses_original_target(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        attacker = game_state.player(2).get_character("voss")
        target = game_state.player(1).get_character("morgan")
        defender = game_state.player(1).get_character("duran")
        attacker.passive_effect_ids = ("backline_attack",)
        target.passive_effect_ids = ("reflect_100",)

        result = battle.attack(2, "voss", "morgan")

        self.assertEqual(result.actual_target_name, "杜兰")
        self.assertEqual(result.reflected_damage, target.attack)
        self.assertEqual(defender.current_health, defender.max_health - attacker.attack)
        self.assertEqual(attacker.current_health, attacker.max_health - target.attack)
        self.assertIn("摩根 反伤 2 点。", result.events)

    def test_reflect_damage_can_be_redirected_by_defender(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        attacker = game_state.player(2).get_character("voss")
        target = game_state.player(1).get_character("morgan")
        reflector_side_defender = game_state.player(2).get_character("iris")
        attacker.passive_effect_ids = ("backline_attack",)
        target.passive_effect_ids = ("reflect_100",)
        reflector_side_defender.passive_effect_ids = ("guard_adjacent",)

        result = battle.attack(2, "voss", "morgan")

        self.assertEqual(result.reflected_damage, target.attack)
        self.assertEqual(attacker.current_health, attacker.max_health)
        self.assertEqual(reflector_side_defender.current_health, reflector_side_defender.max_health - target.attack)
        self.assertIn("沃斯 的伤害由 艾瑞丝 抵御。", result.events)

    def test_defender_does_not_redirect_diagonal_friend_damage(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        game_state.player(1).get_character("morgan").take_damage(99)
        target = game_state.player(1).get_character("maker")
        defender = game_state.player(1).get_character("duran")

        result = battle.attack(2, "kira", "maker")

        self.assertEqual(result.actual_target_name, "制作者")
        self.assertEqual(target.current_health, target.max_health - 4)
        self.assertEqual(defender.current_health, defender.max_health)

    def test_hero_reduces_incoming_damage_by_one(self) -> None:
        battle, game_state = create_hero_battle_session(first_player_id=2)
        hero = game_state.player(1).get_character("orion")
        attacker = game_state.player(2).get_character("voss")

        result = battle.attack(2, "voss", "orion")

        self.assertEqual(result.damage, 3)
        self.assertEqual(result.reflected_damage, 2)
        self.assertEqual(hero.current_health, hero.max_health - 3)
        self.assertEqual(attacker.current_health, attacker.max_health - 2)

    def test_bleeding_increases_next_damage_and_is_consumed(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        target = game_state.player(1).get_character("duran")
        self.assertTrue(battle.apply_status_effect(1, "duran", "bleeding"))

        result = battle.attack(2, "voss", "luna")

        self.assertEqual(result.damage, 6)
        self.assertEqual(target.current_health, target.max_health - 6)
        self.assertFalse(target.has_status_effect("bleeding"))

    def test_creator_ignores_adverse_status_effects(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        creator = game_state.player(1).get_character("maker")

        applied = battle.apply_status_effect(1, "maker", "frozen")

        self.assertFalse(applied)
        self.assertFalse(creator.has_status_effect("frozen"))

    def test_non_adverse_debuff_is_not_blocked_or_purified_as_adverse(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        creator = game_state.player(1).get_character("maker")
        effect = Effect(
            id="test_non_adverse_debuff",
            name="测试非不利Debuff",
            category=EffectCategory.DEBUFF,
            description="测试用。",
            is_adverse=False,
        )
        EFFECTS_BY_ID[effect.id] = effect
        try:
            applied = battle.apply_status_effect(1, "maker", effect.id)
            removed_names = battle._purify_character((1, "maker"))
        finally:
            EFFECTS_BY_ID.pop(effect.id, None)

        self.assertTrue(applied)
        self.assertTrue(creator.has_status_effect(effect.id))
        self.assertEqual(removed_names, [])

    def test_curse_and_silence_are_debuffs_but_not_adverse_effects(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        creator = game_state.player(1).get_character("maker")

        self.assertTrue(battle.apply_status_effect(1, "maker", "cursed"))
        self.assertTrue(creator.has_status_effect("cursed"))
        self.assertEqual(battle._purify_character((1, "maker")), [])
        self.assertTrue(creator.has_status_effect("cursed"))

        self.assertTrue(battle.apply_status_effect(1, "maker", "silenced"))
        self.assertTrue(creator.has_status_effect("silenced"))
        self.assertFalse(creator.has_status_effect("cursed"))
        self.assertEqual(battle._purify_character((1, "maker")), [])
        self.assertTrue(creator.has_status_effect("silenced"))

    def test_tenacity_waits_for_next_enemy_action_after_status_is_applied(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        target = game_state.player(1).get_character("luna")
        target.add_status_effect("tenacity")

        battle.cast_skill(2, "naya", "freeze_target", "luna")

        self.assertTrue(target.has_status_effect("frozen"))

        battle.skip_move(1, "luna")
        self.assertTrue(target.has_status_effect("frozen"))

        battle.end_player_round(1)
        battle.skip_move(2, "kira")

        self.assertFalse(target.has_status_effect("frozen"))

    def test_frozen_character_can_thaw_or_skip_but_not_attack(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        actor = game_state.player(1).get_character("luna")
        self.assertTrue(battle.apply_status_effect(1, "luna", "frozen"))

        self.assertTrue(battle.can_character_move(1, "luna"))
        self.assertFalse(battle.can_attack(1, "luna", "kira"))
        self.assertFalse(battle.can_cast_skill(1, "luna", "arcane_bolt"))
        self.assertTrue(battle.can_skip_move(1, "luna"))
        self.assertTrue(battle.can_thaw_character(1, "luna"))

        skip_result = battle.skip_move(1, "luna")

        self.assertEqual(skip_result.actor_name, "露娜")
        self.assertTrue(actor.has_status_effect("frozen"))
        self.assertEqual(battle.remaining_move_count(1, "luna"), 0)
        self.assertEqual(game_state.current_turn_player_id, 1)

    def test_thaw_consumes_frozen_character_move(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        actor = game_state.player(1).get_character("luna")
        self.assertTrue(battle.apply_status_effect(1, "luna", "frozen"))

        result = battle.thaw_character(1, "luna")

        self.assertEqual(result.actor_name, "露娜")
        self.assertFalse(actor.has_status_effect("frozen"))
        self.assertEqual(battle.remaining_move_count(1, "luna"), 0)
        self.assertEqual(game_state.current_turn_player_id, 2)

    def test_active_damage_skill_deals_damage_and_consumes_move(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        target = game_state.player(2).get_character("kira")

        result = battle.cast_skill(1, "luna", "arcane_bolt", "kira")

        self.assertEqual(result.skill_name, "星火")
        self.assertEqual(result.damage, 2)
        self.assertEqual(target.current_health, target.max_health - 2)
        self.assertEqual(battle.remaining_move_count(1, "luna"), 0)
        self.assertEqual(game_state.current_turn_player_id, 2)

    def test_default_skill_targets_ignore_attack_frontline_rules(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        target = game_state.player(2).get_character("brant")

        self.assertFalse(battle.can_attack(1, "luna", "brant"))
        self.assertTrue(battle.can_cast_skill(1, "luna", "arcane_bolt", "brant"))

        result = battle.cast_skill(1, "luna", "arcane_bolt", "brant")

        self.assertEqual(result.target_name, "布兰特")
        self.assertEqual(target.current_health, target.max_health - 2)

    def test_default_skill_targets_can_select_friendly_characters(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        target = game_state.player(1).get_character("maker")

        self.assertTrue(battle.can_cast_skill(1, "luna", "arcane_bolt", "maker"))

        result = battle.cast_skill(1, "luna", "arcane_bolt", "maker")

        self.assertEqual(result.target_name, "制作者")
        self.assertEqual(target.current_health, target.max_health - 2)

    def test_active_status_skill_applies_adverse_status(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        target = game_state.player(1).get_character("luna")

        result = battle.cast_skill(2, "naya", "freeze_target", "luna")

        self.assertEqual(result.skill_name, "冻结术")
        self.assertTrue(result.status_applied)
        self.assertTrue(target.has_status_effect("frozen"))
        self.assertEqual(battle.remaining_move_count(2, "naya"), 0)

    def test_default_status_skill_targets_can_select_friendly_characters(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        target = game_state.player(2).get_character("voss")

        result = battle.cast_skill(2, "naya", "freeze_target", "voss")

        self.assertEqual(result.target_name, "沃斯")
        self.assertTrue(result.status_applied)
        self.assertTrue(target.has_status_effect("frozen"))

    def test_invalid_backline_attack_raises_error(self) -> None:
        battle, _ = create_battle_session(first_player_id=1)

        with self.assertRaises(BattleError):
            battle.attack(1, "luna", "brant")

    def test_round_advances_after_all_available_moves_are_spent(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        for key in list(battle.remaining_moves):
            battle.remaining_moves[key] = 0
        battle.remaining_moves[(1, "luna")] = 1
        battle.remaining_moves[(2, "kira")] = 1
        game_state.current_turn_player_id = 1

        battle.attack(1, "luna", "kira")
        self.assertEqual(game_state.current_turn_player_id, 2)

        battle.attack(2, "kira", "luna")

        self.assertEqual(game_state.round_number, 2)
        self.assertEqual(game_state.current_turn_player_id, 1)
        self.assertEqual(battle.remaining_move_count(1, "luna"), 1)

    def test_player_with_remaining_moves_continues_when_opponent_has_none(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        for key in list(battle.remaining_moves):
            battle.remaining_moves[key] = 0
        battle.remaining_moves[(1, "luna")] = 1
        battle.remaining_moves[(1, "duran")] = 1
        game_state.current_turn_player_id = 1

        battle.attack(1, "luna", "kira")

        self.assertEqual(game_state.current_turn_player_id, 1)

    def test_second_hand_skill_grants_next_turn_once(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        for key in list(battle.remaining_moves):
            battle.remaining_moves[key] = 0
        battle.remaining_moves[(1, "luna")] = 1
        battle.remaining_moves[(2, "kira")] = 1
        battle.remaining_moves[(2, "voss")] = 1
        game_state.current_turn_player_id = 2

        self.assertFalse(battle.can_use_second_hand_skill(1))
        self.assertTrue(battle.can_use_second_hand_skill(2))

        result = battle.use_second_hand_skill(2)

        self.assertEqual(result.player_name, "玩家2")
        self.assertTrue(game_state.player(2).second_hand_skill_used)
        self.assertEqual(game_state.current_turn_player_id, 2)
        self.assertFalse(battle.can_use_second_hand_skill(2))

        battle.attack(2, "kira", "luna")

        self.assertEqual(game_state.current_turn_player_id, 2)

        battle.attack(2, "voss", "duran")

        self.assertEqual(game_state.current_turn_player_id, 1)
        with self.assertRaises(BattleError):
            battle.use_second_hand_skill(2)

    def test_killing_all_enemy_characters_ends_game(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        for character in game_state.player(2).selected_characters:
            if character.id != "kira":
                character.take_damage(character.max_health)
        target = game_state.player(2).get_character("kira")
        target.current_health = 1

        result = battle.attack(1, "luna", "kira")

        self.assertTrue(result.target_defeated)
        self.assertEqual(result.winner_player_id, 1)
        self.assertEqual(game_state.phase, GamePhase.FINISHED)
        self.assertEqual(game_state.winner_player_id, 1)
        self.assertIsNone(game_state.current_turn_player_id)

    def test_movement_order_records_first_time_actor_sequence(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        for key in list(battle.remaining_moves):
            battle.remaining_moves[key] = 0
        for character_id in ("luna", "duran", "sable"):
            battle.remaining_moves[(1, character_id)] = 1
        game_state.current_turn_player_id = 1

        battle.attack(1, "luna", "kira")
        battle.attack(1, "duran", "kira")
        battle.attack(1, "sable", "kira")

        self.assertEqual(battle.move_orders[1], ["luna", "duran", "sable"])

    def test_charger_can_record_multiple_move_order_slots(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        for key in list(battle.remaining_moves):
            battle.remaining_moves[key] = 0
        battle.remaining_moves[(2, "iris")] = 2
        battle.remaining_moves[(2, "voss")] = 1
        game_state.current_turn_player_id = 2

        battle.attack(2, "iris", "luna")
        battle.attack(2, "voss", "luna")
        battle.attack(2, "iris", "luna")

        self.assertEqual(battle.move_orders[2], ["iris", "voss", "iris"])

    def test_charger_second_historical_move_keeps_relative_order(self) -> None:
        battle, game_state = create_battle_session(first_player_id=2)
        battle.move_orders[2] = ["iris", "voss", "iris"]
        battle._start_next_round()
        for key in list(battle.remaining_moves):
            battle.remaining_moves[key] = 0
        battle.remaining_moves[(2, "iris")] = 2
        battle.remaining_moves[(2, "voss")] = 1
        game_state.current_turn_player_id = 2

        battle.attack(2, "iris", "luna")

        self.assertTrue(battle.can_character_move(2, "voss"))
        self.assertFalse(battle.can_character_move(2, "iris"))
        self.assertEqual(battle.blocked_actor_names_before_choice(2, "iris"), ("沃斯",))

        with self.assertRaises(BattleError):
            battle.attack(2, "iris", "luna")

        battle.attack(2, "voss", "luna")

        self.assertTrue(battle.can_character_move(2, "iris"))

    def test_later_historical_actor_requires_explicit_skip_of_blocker(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        battle.move_orders[1] = ["luna", "duran", "sable"]
        battle._start_next_round()
        for key in list(battle.remaining_moves):
            battle.remaining_moves[key] = 0
        for character_id in ("luna", "duran", "sable", "maker"):
            battle.remaining_moves[(1, character_id)] = 1
        game_state.current_turn_player_id = 1

        battle.attack(1, "luna", "kira")

        self.assertFalse(battle.can_character_move(1, "sable"))
        self.assertEqual(battle.blocked_actor_names_before_choice(1, "sable"), ("杜兰",))
        with self.assertRaises(BattleError):
            battle.attack(1, "sable", "kira")

        skip_result = battle.skip_move(1, "duran")

        self.assertEqual(skip_result.actor_name, "杜兰")
        self.assertEqual(skip_result.next_player_id, 1)
        self.assertEqual(battle.remaining_move_count(1, "duran"), 0)
        self.assertIn("duran", battle.round_skipped_ids[1])
        self.assertNotIn("duran", {character.id for character in battle.available_actors(1)})

        result = battle.attack(1, "sable", "kira")

        self.assertEqual(result.skipped_actor_names, ())

    def test_new_actor_can_insert_into_existing_order_without_skip(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        battle.move_orders[1] = ["luna", "duran", "sable"]
        battle._start_next_round()
        for key in list(battle.remaining_moves):
            battle.remaining_moves[key] = 0
        for character_id in ("luna", "maker", "duran", "sable"):
            battle.remaining_moves[(1, character_id)] = 1
        game_state.current_turn_player_id = 1

        battle.attack(1, "luna", "kira")
        result = battle.attack(1, "maker", "kira")

        self.assertEqual(result.skipped_actor_names, ())
        self.assertEqual(battle.move_orders[1], ["luna", "maker", "duran", "sable"])
        self.assertEqual(battle.remaining_move_count(1, "duran"), 1)

    def test_explicit_skip_keeps_turn_when_player_still_has_actors(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        battle.move_orders[1] = ["luna", "duran", "sable"]
        battle._start_next_round()
        for key in list(battle.remaining_moves):
            battle.remaining_moves[key] = 0
        for character_id in ("luna", "duran", "sable"):
            battle.remaining_moves[(1, character_id)] = 1
        game_state.current_turn_player_id = 1

        battle.attack(1, "luna", "kira")

        result = battle.skip_move(1, "duran")

        self.assertEqual(result.next_player_id, 1)
        self.assertTrue(battle.can_character_move(1, "sable"))
        self.assertEqual(battle.skipped_actor_names_for_choice(1, "sable"), ())

    def test_end_player_round_consumes_remaining_current_player_moves(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        for key in list(battle.remaining_moves):
            battle.remaining_moves[key] = 0
        for character_id in ("luna", "duran"):
            battle.remaining_moves[(1, character_id)] = 1
        battle.remaining_moves[(2, "kira")] = 1
        game_state.current_turn_player_id = 1

        result = battle.end_player_round(1)

        self.assertEqual(result.player_name, "玩家1")
        self.assertEqual(result.consumed_actor_names, ("露娜", "杜兰"))
        self.assertEqual(game_state.current_turn_player_id, 2)
        self.assertEqual(battle.remaining_move_count(1, "luna"), 0)
        self.assertEqual(battle.remaining_move_count(1, "duran"), 0)


if __name__ == "__main__":
    unittest.main()
