import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src import user_settings
from src.core import ActiveSkill, FormationColumn, Position, SkillKind
from src.data.jobs import JOBS
from src.tests.test_battle_rules import create_battle_session
from src.tests.test_new_characters import create_new_battle_session
from src.tests.test_new_character3 import create_stage_three_battle
from src.assets import get_font
from src.ui.components import wrap_text
from src.ui.encyclopedia_screen import EncyclopediaScreen
from src.ui.game_screen import GameScreen
from src.ui.settings_screen import SettingsScreen
from src.ui.screen_manager import ScreenManager


class DummyScreen:
    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def update(self, delta_seconds: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pass


class BattleUILayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        pygame.init()
        user_settings.animations_enabled = True
        user_settings.show_arcanarch_in_draft = False
        self.screen = GameScreen(ScreenManager())

    def tearDown(self) -> None:
        user_settings.animations_enabled = True
        user_settings.show_arcanarch_in_draft = False
        pygame.quit()

    def test_battle_board_mirrors_right_player_front_row(self) -> None:
        player_one_back = self.screen._battle_card_rect(1, Position(row=0, column=FormationColumn.BACK))
        player_one_front = self.screen._battle_card_rect(1, Position(row=0, column=FormationColumn.FRONT))
        player_two_front = self.screen._battle_card_rect(2, Position(row=0, column=FormationColumn.FRONT))
        player_two_back = self.screen._battle_card_rect(2, Position(row=0, column=FormationColumn.BACK))

        self.assertLess(player_one_back.x, player_one_front.x)
        self.assertLess(player_two_front.x, player_two_back.x)

    def test_battle_board_has_barrier_frame_for_protected_team(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle
        battle.team_barriers[1] = 12

        barrier_rect = self.screen._team_barrier_rect(battle, 1)

        self.assertIsNotNone(barrier_rect)
        assert barrier_rect is not None
        self.assertTrue(barrier_rect.colliderect(self.screen._battle_card_rect(1, Position(row=0, column=FormationColumn.FRONT))))
        self.assertTrue(barrier_rect.colliderect(self.screen._battle_card_rect(1, Position(row=2, column=FormationColumn.BACK))))

    def test_draft_character_buttons_are_sorted_by_job_and_filterable(self) -> None:
        job_order = {job.id: index for index, job in enumerate(JOBS)}
        visible_jobs = [
            self.screen.draft_session._find_character(button.character_id).job.id
            for button in self.screen.character_buttons
        ]

        self.assertEqual(
            [job_order[job_id] for job_id in visible_jobs],
            sorted(job_order[job_id] for job_id in visible_jobs),
        )

        self.screen.select_draft_job_filter("raider")

        filtered_jobs = {
            self.screen.draft_session._find_character(button.character_id).job.id
            for button in self.screen.character_buttons
        }
        self.assertEqual(filtered_jobs, {"raider"})
        self.assertEqual(self.screen.draft_scroll_offset, 0)

        draft_filter_job_ids = {getattr(button, "job_id") for button in self.screen.draft_job_filter_buttons}
        self.assertNotIn("summon", draft_filter_job_ids)
        self.assertNotIn("arcanarch", draft_filter_job_ids)
        self.assertFalse(any(character.job.id == "summon" for character in self.screen.character_pool))
        self.assertFalse(any(character.job.id == "arcanarch" for character in self.screen.character_pool))

    def test_setting_can_show_arcanarch_in_new_draft_pool(self) -> None:
        user_settings.show_arcanarch_in_draft = True
        screen = GameScreen(ScreenManager())

        self.assertTrue(any(character.job.id == "arcanarch" for character in screen.character_pool))
        self.assertIn("arcanarch", {getattr(button, "job_id") for button in screen.draft_job_filter_buttons})

        settings = SettingsScreen(ScreenManager())
        settings.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": settings.arcanarch_button.rect.center},
            )
        )

        self.assertFalse(user_settings.show_arcanarch_in_draft)
        self.assertEqual(settings.arcanarch_button.text, "选角帝法者：隐藏")

    def test_draft_character_list_scrolls_inside_pool_area(self) -> None:
        if self.screen._draft_content_height() <= self.screen._draft_character_area().height:
            self.skipTest("Character pool does not overflow in this data set.")

        self.screen.draw(pygame.Surface((1120, 720)))
        self.screen.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, {"y": -6}))

        character_area = self.screen._draft_character_area()
        visible_buttons = [button for button in self.screen.character_buttons if button.rect.colliderect(character_area)]
        self.assertGreater(self.screen.draft_scroll_offset, 0)
        self.assertTrue(visible_buttons)
        self.assertTrue(any(button.rect.y < character_area.y for button in self.screen.character_buttons))
        self.assertTrue(
            all(
                button.rect.bottom > character_area.y and button.rect.y < character_area.bottom
                for button in visible_buttons
            )
        )

        self.screen.select_draft_job_filter("raider")

        self.assertEqual(self.screen.draft_scroll_offset, 0)

    def test_skill_button_opens_named_skill_menu(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle

        self.screen.select_battle_character(1, "luna")
        self.assertTrue(self.screen.skill_button.enabled)

        self.screen.begin_skill_menu()

        self.assertEqual(self.screen.battle_action_mode, "skill_menu")
        self.assertEqual([button.text for button in self.screen.skill_option_buttons], ["星火"])
        self.assertTrue(self.screen.cancel_skill_button.enabled)

    def test_skill_menu_scrolls_when_actor_has_many_active_skills(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle
        luna = game_state.player(1).get_character("luna")
        luna.active_skills = tuple(
            ActiveSkill(
                id=f"test_skill_{index}",
                name=f"测试技能{index}",
                description="测试技能",
                kind=SkillKind.DAMAGE,
                damage=1,
            )
            for index in range(6)
        )

        self.screen.select_battle_character(1, "luna")
        self.screen.begin_skill_menu()

        self.assertEqual(len(self.screen.skill_option_buttons), 6)
        self.assertGreater(self.screen._skill_option_content_height(), self.screen._skill_option_area_rect().height)

        self.screen.skill_option_scroll_offset = 999
        self.screen._clamp_skill_option_scroll_offset()
        self.screen._rebuild_current_skill_option_buttons()

        self.assertGreater(self.screen.skill_option_scroll_offset, 0)
        self.assertLess(self.screen.skill_option_buttons[-1].rect.y, 432 + 5 * 44)

    def test_skill_target_mode_can_click_friendly_targets(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle
        target = game_state.player(1).get_character("maker")

        self.screen.select_battle_character(1, "luna")
        self.screen.begin_skill_menu()
        self.screen.select_active_skill("arcane_bolt")
        self.screen.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {
                    "button": 1,
                    "pos": self.screen._battle_card_rect(1, target.position).center,
                },
            )
        )

        self.assertEqual(target.current_health, target.max_health - 2)
        self.assertIsNone(self.screen.battle_action_mode)

    def test_battle_detail_panel_lists_active_and_passive_effects(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle
        luna = game_state.player(1).get_character("luna")
        duran = game_state.player(1).get_character("duran")

        luna_text = "\n".join(item[0] for item in self.screen._battle_detail_items(1, luna, battle))
        duran_text = "\n".join(item[0] for item in self.screen._battle_detail_items(1, duran, battle))

        self.assertIn("职业效果", luna_text)
        self.assertIn("角色被动技能", luna_text)
        self.assertIn("角色主动技能", luna_text)
        self.assertIn("角色被动技能\n无", luna_text)
        self.assertIn("星火：对一个敌方角色造成2点伤害。", luna_text)
        self.assertIn("抵御周围四格友军", duran_text)
        self.assertNotIn("被动/职业效果", luna_text)

    def test_frozen_actor_can_skip_or_thaw_from_action_panel(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        battle.apply_status_effect(1, "luna", "frozen")
        self.screen.game_state = game_state
        self.screen.battle_session = battle

        self.screen.select_battle_character(1, "luna")

        self.assertFalse(self.screen.attack_button.enabled)
        self.assertFalse(self.screen.skill_button.enabled)
        self.assertTrue(self.screen.thaw_button.enabled)
        self.assertTrue(self.screen.skip_button.enabled)
        visible_texts = {button.text for button in self.screen._visible_battle_action_buttons()}
        self.assertIn("解冻", visible_texts)
        self.assertIn("跳过", visible_texts)
        self.assertNotIn("技能", visible_texts)

    def test_pending_ending_has_revival_action_instead_of_attack_or_skill(self) -> None:
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
        self.screen.game_state = game_state
        self.screen.battle_session = battle

        self.screen.select_battle_character(1, "ending")

        self.assertTrue(self.screen.revive_button.enabled)
        self.assertTrue(self.screen.skip_button.enabled)
        self.assertFalse(self.screen.attack_button.enabled)
        self.assertFalse(self.screen.skill_button.enabled)
        visible_texts = {button.text for button in self.screen._visible_battle_action_buttons()}
        self.assertIn("复活", visible_texts)
        self.assertIn("跳过", visible_texts)
        self.assertNotIn("攻击", visible_texts)
        self.assertNotIn("技能", visible_texts)

    def test_action_button_list_scrolls_when_many_actions_are_visible(self) -> None:
        for button in (
            self.screen.attack_button,
            self.screen.skill_button,
            self.screen.thaw_button,
            self.screen.revive_button,
            self.screen.skip_button,
            self.screen.end_round_button,
            self.screen.second_hand_button,
        ):
            button.enabled = True

        self.assertGreater(
            self.screen._battle_action_content_height(),
            self.screen._battle_action_area_rect().height,
        )
        self.screen.battle_action_scroll_offset = 999
        self.screen._clamp_battle_action_scroll_offset()

        self.assertGreater(self.screen.battle_action_scroll_offset, 0)

    def test_second_hand_button_uses_once_for_battle_second_player(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        game_state.current_turn_player_id = 2
        self.screen.game_state = game_state
        self.screen.battle_session = battle

        self.screen._sync_battle_button_states()

        self.assertTrue(self.screen.second_hand_button.enabled)

        self.screen.use_second_hand_skill()

        self.assertTrue(game_state.player(2).second_hand_skill_used)
        self.assertFalse(self.screen.second_hand_button.enabled)
        self.assertIn("后手技能", self.screen.message)

    def test_start_order_choice_buttons_resolve_before_battle_start_triggers(self) -> None:
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
        self.screen.game_state = game_state
        self.screen.battle_session = battle

        self.screen._sync_battle_button_states()

        self.assertTrue(self.screen.choose_first_button.enabled)
        self.assertTrue(self.screen.choose_second_button.enabled)
        self.assertFalse(battle.pending_death_triggers)

        self.screen.choose_start_order(False)

        self.assertEqual(battle.first_player_id, 2)
        self.assertEqual(game_state.battle_first_player_id, 2)
        self.assertFalse(self.screen.choose_first_button.enabled)
        self.assertEqual(battle.pending_death_triggers[0].kind, "mirror_copy")
        self.assertIn("选择自己后手", self.screen.message)

    def test_battle_log_overlay_opens_only_when_log_panel_is_clicked(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle

        self.screen._log_battle("第一条测试日志。")

        self.assertFalse(self.screen.battle_log_overlay_open)

        self.screen.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": self.screen._battle_log_panel_rect().center},
            )
        )

        self.assertTrue(self.screen.battle_log_overlay_open)

        self.screen.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": (12, 12)},
            )
        )

        self.assertFalse(self.screen.battle_log_overlay_open)

    def test_battle_log_keeps_newest_entries_on_top(self) -> None:
        self.screen._log_battle("第一条")
        self.screen._log_battle("第二条")

        self.assertEqual(self.screen.battle_log[:2], ["第二条", "第一条"])

    def test_battle_log_overlay_draws_full_log(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle
        for index in range(12):
            self.screen._log_battle(f"第{index + 1}条测试日志。")
        self.screen.battle_log_overlay_open = True

        surface = pygame.Surface((1120, 720))

        self.screen.draw(surface)

    def test_battle_log_row_height_uses_overlay_line_height(self) -> None:
        text = "这是一条很长的战斗日志，用来确保大日志栏内多行文字不会覆盖下一条日志。"
        width = 180
        expected_lines = len(wrap_text(text, get_font(15), width - 16))

        row_height = self.screen._battle_log_row_height(text, width, size=15, line_height=21)

        self.assertGreaterEqual(row_height, expected_lines * 21 + 5)

    def test_battle_top_bar_can_open_encyclopedia(self) -> None:
        manager = ScreenManager()
        screen = GameScreen(manager)
        battle, game_state = create_battle_session(first_player_id=1)
        screen.game_state = game_state
        screen.battle_session = battle
        manager.register("game", screen)
        manager.register("encyclopedia", DummyScreen())
        manager.switch_to("game")

        screen.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": screen.encyclopedia_button.rect.center},
            )
        )

        self.assertIsInstance(manager.current_screen, DummyScreen)

    def test_battle_encyclopedia_back_button_returns_to_battle(self) -> None:
        manager = ScreenManager()
        screen = GameScreen(manager)
        encyclopedia = EncyclopediaScreen(manager)
        battle, game_state = create_battle_session(first_player_id=1)
        screen.game_state = game_state
        screen.battle_session = battle
        manager.register("game", screen)
        manager.register("encyclopedia", encyclopedia)
        manager.switch_to("game")

        screen.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": screen.encyclopedia_button.rect.center},
            )
        )

        self.assertIs(manager.current_screen, encyclopedia)
        self.assertEqual(encyclopedia.back_button.text, "返回战斗")

        encyclopedia.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": encyclopedia.back_button.rect.center},
            )
        )

        self.assertIs(manager.current_screen, screen)

    def test_attack_animation_queues_damage_events_and_blocks_input(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle

        self.screen.select_battle_character(1, "luna")
        self.screen.begin_attack_mode()
        self.screen.attack_selected_target("kira")

        self.assertIsNotNone(self.screen.active_attack_animation)
        assert self.screen.active_attack_animation is not None
        self.assertTrue(self.screen.active_attack_animation.show_slash)
        self.assertIn((2, "kira"), {(event.player_id, event.character_id) for event in self.screen.active_attack_animation.damage_events})
        self.assertIn((2, "kira", -3), {(event.player_id, event.character_id, event.amount) for event in self.screen.active_attack_animation.health_events})

        self.screen.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": self.screen._battle_log_panel_rect().center},
            )
        )
        self.assertFalse(self.screen.battle_log_overlay_open)

        self.screen.update(1.0)
        self.assertIsNone(self.screen.active_attack_animation)

        self.screen.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": self.screen._battle_log_panel_rect().center},
            )
        )
        self.assertTrue(self.screen.battle_log_overlay_open)

    def test_critical_attack_animation_marks_damage_number(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle
        game_state.player(1).get_character("luna").passive_effect_ids = ("critical_vs_uninjured",)

        self.screen.select_battle_character(1, "luna")
        self.screen.begin_attack_mode()
        self.screen.attack_selected_target("kira")

        self.assertIsNotNone(self.screen.active_attack_animation)
        assert self.screen.active_attack_animation is not None
        self.assertTrue(any(event.critical for event in self.screen.active_attack_animation.health_events))
        self.assertTrue(any(event.critical for event in self.screen.active_attack_animation.damage_events))

    def test_settings_toggle_controls_attack_animation(self) -> None:
        settings = SettingsScreen(ScreenManager())

        settings.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": settings.animation_button.rect.center},
            )
        )

        self.assertFalse(user_settings.animations_enabled)
        self.assertEqual(settings.animation_button.text, "动画：关闭")

        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle
        self.screen.select_battle_character(1, "luna")
        self.screen.begin_attack_mode()
        self.screen.attack_selected_target("kira")

        self.assertIsNone(self.screen.active_attack_animation)
        self.assertEqual(self.screen.attack_animation_queue, [])

    def test_non_attack_skill_health_changes_show_number_without_slash(self) -> None:
        battle, game_state = create_battle_session(first_player_id=1)
        self.screen.game_state = game_state
        self.screen.battle_session = battle
        healer = game_state.player(1).get_character("luna")
        target = game_state.player(1).get_character("maker")
        target.current_health = target.max_health - 4
        healer.active_skills = (
            ActiveSkill(
                id="test_heal",
                name="测试治疗",
                description="恢复3点生命",
                kind=SkillKind.HEAL,
                heal=3,
            ),
        )

        self.screen.select_battle_character(1, "luna")
        self.screen.begin_skill_menu()
        self.screen.select_active_skill("test_heal")
        self.screen.cast_selected_skill_on_target("maker")

        self.assertIsNotNone(self.screen.active_attack_animation)
        assert self.screen.active_attack_animation is not None
        self.assertFalse(self.screen.active_attack_animation.show_slash)
        self.assertIn((1, "maker", 3), {(event.player_id, event.character_id, event.amount) for event in self.screen.active_attack_animation.health_events})


if __name__ == "__main__":
    unittest.main()
