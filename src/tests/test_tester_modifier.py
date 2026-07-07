import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.config import WINDOW_SIZE
from src.core import FormationColumn, GamePhase, Position
from src.tests.test_new_characters import create_new_battle_session
from src.ui.game_screen import GameScreen
from src.ui.screen_manager import ScreenManager


class TesterModifierTests(unittest.TestCase):
    def test_debug_clear_replace_reset_debuff_damage_and_heal(self) -> None:
        battle, game_state = create_new_battle_session(
            {
                "villager": Position(row=0, column=FormationColumn.FRONT),
                "priest": Position(row=1, column=FormationColumn.FRONT),
            },
            {
                "werewolf": Position(row=0, column=FormationColumn.FRONT),
            },
        )
        front = Position(row=0, column=FormationColumn.FRONT)

        cleared = battle.debug_clear_position(1, front)

        self.assertEqual(cleared.name, "村民")
        self.assertIsNone(game_state.player(1).character_at(front))
        self.assertEqual(battle.remaining_move_count(1, "villager"), 0)

        replacement = battle.debug_replace_position(1, front, "arsonist")

        self.assertEqual(replacement.name, "纵火者")
        self.assertEqual(game_state.player(1).character_at(front).id, replacement.id)
        self.assertEqual(battle.remaining_move_count(1, replacement.id), replacement.default_move_count)

        battle.move_orders[1] = [replacement.id, "priest"]
        battle.round_resolved_order_slots[1] = {0}
        battle.round_skipped_ids[1].add("priest")
        battle.debug_reset_move_orders()

        self.assertEqual(battle.move_orders[1], [])
        self.assertEqual(battle.round_resolved_order_slots[1], set())
        self.assertEqual(battle.round_skipped_ids[1], set())

        self.assertTrue(battle.debug_apply_debuff(1, replacement.id, "bleeding"))
        self.assertTrue(replacement.has_status_effect("bleeding"))
        self.assertTrue(battle.debug_apply_buff(1, replacement.id, "stealth"))
        self.assertTrue(replacement.has_status_effect("stealth"))

        dealt = battle.debug_deal_damage(1, replacement.id, 2)
        self.assertEqual(dealt, 2)
        self.assertEqual(replacement.current_health, replacement.max_health - 2)

        healed = battle.debug_heal(1, replacement.id, 1)
        self.assertEqual(healed, 1)
        self.assertEqual(replacement.current_health, replacement.max_health - 1)

    def test_tester_button_opens_window_and_draws_slots(self) -> None:
        pygame.init()
        try:
            screen = GameScreen(ScreenManager())
            battle, game_state = create_new_battle_session(
                {
                    "villager": Position(row=0, column=FormationColumn.FRONT),
                },
                {
                    "werewolf": Position(row=0, column=FormationColumn.FRONT),
                },
            )
            screen.game_state = game_state
            screen.battle_session = battle
            surface = pygame.Surface(WINDOW_SIZE)

            screen.handle_event(
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": screen.tester_button.rect.center})
            )
            screen.draw(surface)

            self.assertTrue(screen.tester_open)
            self.assertEqual(len(screen.tester_slot_rects), 12)
            player_one_back = next(
                rect
                for rect, player_id, position in screen.tester_slot_rects
                if player_id == 1 and position == Position(row=0, column=FormationColumn.BACK)
            )
            player_one_front = next(
                rect
                for rect, player_id, position in screen.tester_slot_rects
                if player_id == 1 and position == Position(row=0, column=FormationColumn.FRONT)
            )
            player_two_front = next(
                rect
                for rect, player_id, position in screen.tester_slot_rects
                if player_id == 2 and position == Position(row=0, column=FormationColumn.FRONT)
            )
            player_two_back = next(
                rect
                for rect, player_id, position in screen.tester_slot_rects
                if player_id == 2 and position == Position(row=0, column=FormationColumn.BACK)
            )
            self.assertLess(player_one_back.x, player_one_front.x)
            self.assertLess(player_two_front.x, player_two_back.x)
            self.assertIn("replace", screen.tester_action_rects)
            self.assertIn("reset_order", screen.tester_action_rects)
            self.assertIn("debuff_dropdown", screen.tester_action_rects)
            self.assertIn("buff_dropdown", screen.tester_action_rects)
            self.assertIn("apply_buff", screen.tester_action_rects)
        finally:
            pygame.quit()

    def test_tester_dropdown_selects_replacement_and_applies_buff(self) -> None:
        pygame.init()
        try:
            screen = GameScreen(ScreenManager())
            battle, game_state = create_new_battle_session(
                {
                    "villager": Position(row=0, column=FormationColumn.FRONT),
                },
                {
                    "werewolf": Position(row=0, column=FormationColumn.FRONT),
                },
            )
            screen.game_state = game_state
            screen.battle_session = battle
            screen.tester_open = True
            screen.tester_selected_slot = (1, Position(row=0, column=FormationColumn.FRONT))
            surface = pygame.Surface(WINDOW_SIZE)

            screen.draw(surface)
            screen.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    {"button": 1, "pos": screen.tester_action_rects["replace_dropdown"].center},
                )
            )
            screen.draw(surface)

            self.assertEqual(screen.tester_dropdown, "replace")

            item_rect, _dropdown_id, index = next(
                item for item in screen.tester_dropdown_item_rects if item[1] == "replace" and item[2] != 0
            )
            screen.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    {"button": 1, "pos": item_rect.center},
                )
            )

            self.assertEqual(screen.tester_replace_index, index)
            self.assertIsNone(screen.tester_dropdown)

            screen.draw(surface)
            screen.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    {"button": 1, "pos": screen.tester_action_rects["apply_buff"].center},
                )
            )

            self.assertTrue(game_state.player(1).get_character("villager").has_status_effect("stealth"))
        finally:
            pygame.quit()

    def test_tester_can_quick_enter_battle_from_non_battle_screen(self) -> None:
        pygame.init()
        try:
            screen = GameScreen(ScreenManager())
            surface = pygame.Surface(WINDOW_SIZE)

            screen.open_tester()
            screen.draw(surface)
            screen.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    {"button": 1, "pos": screen.tester_action_rects["quick_battle"].center},
                )
            )

            self.assertEqual(screen.game_state.phase, GamePhase.BATTLE)
            self.assertIsNotNone(screen.battle_session)
            self.assertTrue(screen.tester_open)
            self.assertIsNotNone(screen.game_state.player(1).character_at(Position(row=0, column=FormationColumn.FRONT)))
        finally:
            pygame.quit()


if __name__ == "__main__":
    unittest.main()
