import unittest

from src.core import DraftSession, GamePhase
from src.core.draft import DRAFT_PICK_COUNTS
from src.core.game_state import create_initial_game_state
from src.data.characters import create_character_pool


class DraftSessionTests(unittest.TestCase):
    def test_pick_counts_match_required_draft_order(self) -> None:
        self.assertEqual(DRAFT_PICK_COUNTS, (1, 2, 2, 2, 2, 2, 1))
        self.assertEqual(sum(DRAFT_PICK_COUNTS), 12)

    def test_draft_assigns_six_characters_to_each_player(self) -> None:
        game_state = create_initial_game_state()
        character_pool = create_character_pool()
        draft = DraftSession(game_state, character_pool, first_player_id=1)

        for character in character_pool[:12]:
            draft.select_character(character.id)

        player_one_ids = [character.id for character in game_state.player(1).selected_characters]
        player_two_ids = [character.id for character in game_state.player(2).selected_characters]
        expected_player_one_ids = [
            character_pool[index].id for index in (0, 3, 4, 7, 8, 11)
        ]
        expected_player_two_ids = [
            character_pool[index].id for index in (1, 2, 5, 6, 9, 10)
        ]

        self.assertEqual(player_one_ids, expected_player_one_ids)
        self.assertEqual(player_two_ids, expected_player_two_ids)
        self.assertEqual(game_state.phase, GamePhase.FORMATION)
        self.assertIsNone(game_state.current_turn_player_id)
        self.assertTrue(draft.is_complete)

    def test_draft_rejects_duplicate_character_selection(self) -> None:
        game_state = create_initial_game_state()
        character_pool = create_character_pool()
        draft = DraftSession(game_state, character_pool, first_player_id=2)
        first_character_id = character_pool[0].id

        draft.select_character(first_character_id)

        with self.assertRaises(ValueError):
            draft.select_character(first_character_id)

    def test_draft_tracks_available_characters(self) -> None:
        game_state = create_initial_game_state()
        character_pool = create_character_pool()
        draft = DraftSession(game_state, character_pool, first_player_id=1)

        draft.select_character(character_pool[0].id)
        available_ids = {character.id for character in draft.available_characters}

        self.assertNotIn(character_pool[0].id, available_ids)
        self.assertEqual(len(available_ids), len(character_pool) - 1)

    def test_draft_can_retract_last_pick_and_restore_turn(self) -> None:
        game_state = create_initial_game_state()
        character_pool = create_character_pool()
        draft = DraftSession(game_state, character_pool, first_player_id=1)

        draft.select_character(character_pool[0].id)
        self.assertEqual(game_state.current_turn_player_id, 2)

        retracted = draft.retract_last_pick()

        self.assertEqual(retracted.id, character_pool[0].id)
        self.assertEqual(game_state.player(1).selected_characters, [])
        self.assertIn(character_pool[0].id, {character.id for character in draft.available_characters})
        self.assertEqual(game_state.current_turn_player_id, 1)
        self.assertEqual(draft.current_step_index, 0)
        self.assertEqual(draft.current_step_remaining_picks, 1)

    def test_draft_can_retract_after_final_pick_returns_to_draft_phase(self) -> None:
        game_state = create_initial_game_state()
        character_pool = create_character_pool()
        draft = DraftSession(game_state, character_pool, first_player_id=1)

        for character in character_pool[:12]:
            draft.select_character(character.id)
        self.assertEqual(game_state.phase, GamePhase.FORMATION)

        retracted = draft.retract_last_pick()

        self.assertEqual(retracted.id, character_pool[11].id)
        self.assertEqual(game_state.phase, GamePhase.DRAFT)
        self.assertFalse(draft.is_complete)
        self.assertEqual(game_state.current_turn_player_id, 1)
        self.assertEqual(draft.current_step_remaining_picks, 1)


if __name__ == "__main__":
    unittest.main()
