import unittest

from src.core import FormationColumn, GamePhase, PlacementRestriction, Position
from src.core.effects import resolve_effects
from src.core.game_state import create_initial_game_state
from src.core.rules import character_has_effect, job_allows_position
from src.data import (
    CHARACTER_DEFINITIONS,
    EFFECTS_BY_ID,
    JOBS_BY_ID,
    create_character_pool,
)


class StageTwoModelTests(unittest.TestCase):
    def test_initial_game_state_has_two_players_in_draft_phase(self) -> None:
        game_state = create_initial_game_state("先手", "后手")

        self.assertEqual(game_state.phase, GamePhase.DRAFT)
        self.assertEqual(game_state.player(1).name, "先手")
        self.assertEqual(game_state.player(2).name, "后手")
        self.assertFalse(game_state.is_finished)

    def test_character_pool_can_be_created_from_default_data(self) -> None:
        characters = create_character_pool()

        self.assertEqual(len(characters), len(CHARACTER_DEFINITIONS))
        self.assertGreaterEqual(len(characters), 8)
        self.assertTrue(all(character.is_alive for character in characters))

    def test_job_effects_are_attached_to_created_characters(self) -> None:
        characters = {character.id: character for character in create_character_pool()}

        warrior = characters["villager"]
        raider = characters["assassin"]
        charger = characters["rider"]

        self.assertTrue(character_has_effect(warrior, "reflect_100"))
        self.assertTrue(character_has_effect(raider, "attack_immunity"))
        self.assertTrue(character_has_effect(raider, "backline_attack"))
        self.assertEqual(charger.default_move_count, 2)

    def test_active_skills_are_attached_to_created_characters(self) -> None:
        characters = {character.id: character for character in create_character_pool()}

        self.assertEqual([skill.name for skill in characters["prophet"].active_skills], ["预言"])
        self.assertEqual([skill.name for skill in characters["priest"].active_skills], ["治疗"])
        self.assertEqual([skill.name for skill in characters["knight"].active_skills], ["崇高冲锋"])
        self.assertEqual([skill.name for skill in characters["guard"].active_skills], ["守护"])
        self.assertEqual([skill.name for skill in characters["officer"].active_skills], ["集体增援"])

    def test_player_can_select_and_place_character(self) -> None:
        game_state = create_initial_game_state()
        player = game_state.player(1)
        character = create_character_pool()[0]
        position = Position(row=1, column=FormationColumn.FRONT)

        player.add_character(character)
        player.place_character(character.id, position)

        self.assertEqual(player.character_at(position), character)
        self.assertEqual(character.position, position)

    def test_effect_catalog_resolves_known_effects(self) -> None:
        effects = resolve_effects(("frozen", "bleeding"), EFFECTS_BY_ID)

        self.assertEqual([effect.name for effect in effects], ["冻结", "流血"])
        self.assertTrue(all(effect.is_adverse for effect in effects))

    def test_front_only_jobs_reject_back_position(self) -> None:
        defender = JOBS_BY_ID["defender"]
        front = Position(row=0, column=FormationColumn.FRONT)
        back = Position(row=0, column=FormationColumn.BACK)

        self.assertTrue(defender.has_restriction(PlacementRestriction.FRONT_ONLY))
        self.assertTrue(job_allows_position(defender, front))
        self.assertFalse(job_allows_position(defender, back))

    def test_hero_row_pair_exclusive_rejects_same_row(self) -> None:
        hero = JOBS_BY_ID["hero"]
        target = Position(row=2, column=FormationColumn.FRONT)
        same_row_back = Position(row=2, column=FormationColumn.BACK)
        other_row_back = Position(row=1, column=FormationColumn.BACK)

        self.assertTrue(hero.has_restriction(PlacementRestriction.ROW_PAIR_EXCLUSIVE))
        self.assertFalse(job_allows_position(hero, target, [same_row_back]))
        self.assertTrue(job_allows_position(hero, target, [other_row_back]))

    def test_player_defeat_depends_on_selected_characters(self) -> None:
        game_state = create_initial_game_state()
        player = game_state.player(1)
        character = create_character_pool()[0]

        self.assertFalse(player.is_defeated)

        player.add_character(character)
        character.take_damage(character.max_health)

        self.assertFalse(character.is_alive)
        self.assertTrue(player.is_defeated)


if __name__ == "__main__":
    unittest.main()
