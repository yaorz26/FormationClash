import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.config import WINDOW_SIZE
from src.core import EffectCategory
from src.data import CHARACTER_DEFINITIONS, CHARACTER_MECHANIC_DETAILS, EFFECTS, JOBS, JOBS_BY_ID, MECHANIC_ENTRIES
from src.ui.encyclopedia_screen import CATEGORIES, EncyclopediaScreen
from src.ui.screen_manager import ScreenManager


class EncyclopediaScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        pygame.init()
        self.screen = EncyclopediaScreen(ScreenManager())

    def tearDown(self) -> None:
        pygame.quit()

    def test_cards_are_built_from_game_data(self) -> None:
        character_cards = self.screen._cards_for_category("characters")
        keyword_cards = self.screen._cards_for_category("keywords")
        status_cards = self.screen._cards_for_category("statuses")
        mechanic_cards = self.screen._cards_for_category("mechanics")

        self.assertNotIn("jobs", {category_id for category_id, _label in CATEGORIES})
        self.assertEqual(len(character_cards), len(CHARACTER_DEFINITIONS))
        self.assertEqual(len(self.screen._character_browser_rows()), len(JOBS))
        self.assertEqual(
            len(keyword_cards),
            len([
                effect
                for effect in EFFECTS
                if effect.category == EffectCategory.KEYWORD and effect.show_in_encyclopedia
            ]),
        )
        self.assertEqual(
            len(status_cards),
            len([effect for effect in EFFECTS if effect.category != EffectCategory.KEYWORD]),
        )
        self.assertEqual(len(mechanic_cards), len(MECHANIC_ENTRIES))

    def test_character_cards_show_stats_and_active_skills(self) -> None:
        prophet_card = next(card for card in self.screen._cards_for_category("characters") if card.title == "预言家")

        self.assertEqual(prophet_card.entry_id, "prophet")
        self.assertIn("秘法者", prophet_card.subtitle)
        self.assertIn("HP 4", prophet_card.subtitle)
        self.assertIn("ATK 1", prophet_card.subtitle)
        self.assertIn("奥术", prophet_card.subtitle)
        self.assertIn("职业效果：无特殊效果。", prophet_card.lines)
        self.assertIn("角色被动：无", prophet_card.lines)
        self.assertIn("角色主动：限定：预言：使一名角色+3攻击力", prophet_card.lines)

        werewolf_card = next(card for card in self.screen._cards_for_category("characters") if card.title == "狼人")
        self.assertIn("角色被动：对战开始时，如果所有友方角色都为狼，获得+2攻击力", werewolf_card.lines)

    def test_keyword_cards_hide_internal_character_effects(self) -> None:
        keyword_titles = {card.title for card in self.screen._cards_for_category("keywords")}

        self.assertEqual(
            keyword_titles,
            {"反伤X%", "免疫", "XX嘲讽", "抵御XX角色", "沉默", "XX溅射", "护甲", "净化", "消灭", "召唤", "暴击", "剧毒", "永恒", "限定：", "追击", "屏障", "无法被选中"},
        )
        self.assertNotIn("反伤100%", keyword_titles)
        self.assertNotIn("攻击后排", keyword_titles)
        self.assertNotIn("攻击吸血", keyword_titles)
        self.assertNotIn("死亡追击", keyword_titles)

    def test_character_browser_groups_characters_by_job_and_toggles(self) -> None:
        self.screen.character_job_expanded_ids = {job.id for job in JOBS}
        rows = self.screen._character_browser_rows()
        job_rows = [(index, entry_id) for index, (kind, entry_id, _depth) in enumerate(rows) if kind == "job"]

        self.assertEqual([entry_id for _index, entry_id in job_rows], [job.id for job in JOBS])
        for job_index, (start_index, job_id) in enumerate(job_rows):
            end_index = job_rows[job_index + 1][0] if job_index + 1 < len(job_rows) else len(rows)
            visible_character_ids = [
                entry_id
                for kind, entry_id, _depth in rows[start_index + 1 : end_index]
                if kind == "character"
            ]
            expected_character_ids = [
                character.id
                for character in sorted(
                    (character for character in CHARACTER_DEFINITIONS if character.job_id == job_id),
                    key=lambda character: (character.name, character.id),
                )
            ]
            self.assertEqual(visible_character_ids, expected_character_ids)

        self.screen.character_job_expanded_ids = set()
        surface = pygame.Surface(WINDOW_SIZE)
        self.screen.draw(surface)
        raider_rect = next(rect for rect, key in self.screen.entry_list_hit_rects if key == "job:raider")
        self.screen.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": raider_rect.center})
        )

        self.assertEqual(self.screen.selected_character_job_id, "raider")
        self.assertIsNone(self.screen.selected_character_browser_id)
        self.assertIn("raider", self.screen.character_job_expanded_ids)
        self.assertTrue(any("攻击时具有免疫" in text for text, _size, _color, _bold in self.screen._selected_character_browser_items()))

        self.screen.draw(surface)
        raider_character_ids = {
            character.id for character in CHARACTER_DEFINITIONS if character.job_id == "raider"
        }
        raider_character_rect, raider_character_key = next(
            (rect, key)
            for rect, key in self.screen.entry_list_hit_rects
            if key.startswith("character:") and key.removeprefix("character:") in raider_character_ids
        )
        self.screen.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": raider_character_rect.center})
        )

        self.assertEqual(self.screen.selected_character_browser_id, raider_character_key.removeprefix("character:"))
        self.assertIsNone(self.screen.selected_character_job_id)

        raider_rect = next(rect for rect, key in self.screen.entry_list_hit_rects if key == "job:raider")
        self.screen.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": raider_rect.center})
        )

        self.assertNotIn("raider", self.screen.character_job_expanded_ids)
        self.assertEqual(self.screen.selected_character_job_id, "raider")

    def test_mechanics_category_contains_document_explanations(self) -> None:
        mechanic_cards = self.screen._cards_for_category("mechanics")
        mechanic_titles = {card.title for card in mechanic_cards}

        self.assertIn("隐匿", mechanic_titles)
        self.assertIn("光环效果", mechanic_titles)
        self.assertTrue(any("新增角色我将以以下格式输入" in line for card in mechanic_cards for line in card.lines))

    def test_status_category_filters_buff_debuff_and_adverse_effects(self) -> None:
        filter_labels = {button.text for button in self.screen.status_filter_buttons}

        self.assertTrue({"Buff", "Debuff", "不利效果"}.issubset(filter_labels))

        self.screen.select_category("statuses")
        self.screen.select_status_filter("buff")
        self.assertEqual({card.title for card in self.screen._cards_for_category("statuses")}, {"隐匿", "坚毅", "不死", "护盾"})

        self.screen.select_status_filter("debuff")
        debuff_titles = {card.title for card in self.screen._cards_for_category("statuses")}
        self.assertTrue({"流血", "冻结", "诅咒", "摄梦", "沉默"}.issubset(debuff_titles))

        self.screen.select_status_filter("adverse")
        adverse_titles = {card.title for card in self.screen._cards_for_category("statuses")}
        self.assertEqual(adverse_titles, {"流血", "冻结", "摄梦", "激怒", "重力", "虚弱"})
        self.assertNotIn("诅咒", adverse_titles)
        self.assertNotIn("沉默", adverse_titles)

    def test_keyword_and_mechanic_categories_use_clickable_left_index(self) -> None:
        surface = pygame.Surface(WINDOW_SIZE)

        self.screen.select_category("keywords")
        self.screen.draw(surface)

        self.assertIsNone(self.screen.selected_keyword_id)
        self.assertTrue(self.screen.entry_list_hit_rects)
        first_keyword_rect, first_keyword_id = self.screen.entry_list_hit_rects[0]
        self.screen.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": first_keyword_rect.center})
        )

        self.assertEqual(self.screen.selected_keyword_id, first_keyword_id)
        self.assertIsNotNone(self.screen._selected_entry_card())

        self.screen.select_category("mechanics")
        self.screen.draw(surface)

        self.assertIsNone(self.screen.selected_mechanic_index)
        self.assertTrue(self.screen.entry_list_hit_rects)
        first_mechanic_rect, first_mechanic_id = self.screen.entry_list_hit_rects[0]
        self.screen.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": first_mechanic_rect.center})
        )

        self.assertEqual(self.screen.selected_mechanic_index, int(first_mechanic_id))
        self.assertIsNotNone(self.screen._selected_entry_card())

    def test_character_browser_click_shows_detail_with_mechanic_explanation(self) -> None:
        surface = pygame.Surface(WINDOW_SIZE)
        self.screen.character_job_expanded_ids = {"warrior"}
        hunter_rect = None
        max_offset = max(0, self.screen._entry_list_content_height() - self.screen._entry_list_rect().height)
        for offset in range(0, max_offset + 43, 42):
            self.screen.entry_list_scroll_offset = min(offset, max_offset)
            self.screen.draw(surface)
            hunter_rect = next((rect for rect, key in self.screen.entry_list_hit_rects if key == "character:hunter"), None)
            if hunter_rect is not None:
                break
        self.assertIsNotNone(hunter_rect)
        assert hunter_rect is not None
        self.screen.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": hunter_rect.center})
        )

        self.assertEqual(self.screen.selected_character_browser_id, "hunter")
        self.assertIsNone(self.screen.selected_character_job_id)
        detail_lines = [
            text
            for text, _size, _color, _bold in self.screen._selected_character_browser_items()
        ]
        self.assertTrue(any("职业效果：" in line for line in detail_lines))
        self.assertTrue(any("角色被动技能：" in line for line in detail_lines))
        self.assertTrue(any(CHARACTER_MECHANIC_DETAILS["hunter"][0] in line for line in detail_lines))

        self.screen.draw(surface)

    def test_category_button_switches_content_and_resets_scroll(self) -> None:
        self.screen.scroll_offset = 120
        statuses_button = next(
            button for button in self.screen.category_buttons if button.category_id == "statuses"
        )

        self.screen.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": statuses_button.rect.center})
        )

        self.assertEqual(self.screen.active_category_id, "statuses")
        self.assertEqual(self.screen.scroll_offset, 0)

    def test_all_categories_draw_without_error(self) -> None:
        surface = pygame.Surface(WINDOW_SIZE)

        for category_id, _ in CATEGORIES:
            self.screen.select_category(category_id)
            self.screen.draw(surface)


if __name__ == "__main__":
    unittest.main()
