from __future__ import annotations

from dataclasses import dataclass

import pygame

from src.assets import get_font
from src.config import COLORS, WINDOW_HEIGHT, WINDOW_WIDTH
from src.core import CharacterDefinition, Effect, EffectCategory, Job, PlacementRestriction
from src.core.rules import active_skill_display_text
from src.data import (
    CHARACTER_DEFINITIONS,
    CHARACTER_DEFINITIONS_BY_ID,
    CHARACTER_MECHANIC_DETAILS,
    EFFECTS,
    EFFECTS_BY_ID,
    JOBS,
    JOBS_BY_ID,
    MECHANIC_ENTRIES,
    MechanicEntry,
)
from src.ui.components import Button, draw_text, draw_text_fit
from src.ui.screen_manager import ScreenManager


CATEGORIES: tuple[tuple[str, str], ...] = (
    ("characters", "角色"),
    ("keywords", "关键词"),
    ("statuses", "状态"),
    ("mechanics", "机制"),
)

JOB_ORDER = {job.id: index for index, job in enumerate(JOBS)}
TextItem = tuple[str, int, tuple[int, int, int] | None, bool]


@dataclass(frozen=True)
class EncyclopediaCard:
    title: str
    subtitle: str
    lines: tuple[str, ...]
    entry_id: str = ""


class EncyclopediaScreen:
    def __init__(self, screen_manager: ScreenManager) -> None:
        self.screen_manager = screen_manager
        self.active_category_id = "characters"
        self.status_filter_id = "all"
        self.scroll_offset = 0
        self.entry_list_scroll_offset = 0
        self.entry_detail_scroll_offset = 0
        self.selected_keyword_id: str | None = None
        self.selected_mechanic_index: int | None = None
        self.selected_character_browser_id: str | None = None
        self.selected_character_job_id: str | None = None
        self.character_job_expanded_ids: set[str] = set()
        self.entry_list_hit_rects: list[tuple[pygame.Rect, str]] = []
        self.return_screen_name = "home"
        self.back_button = Button(
            pygame.Rect(40, WINDOW_HEIGHT - 88, 180, 52),
            "返回主页",
            self.go_back,
            font_size=24,
        )
        self.category_buttons = self._build_category_buttons()
        self.status_filter_buttons = self._build_status_filter_buttons()

    def set_return_screen(self, screen_name: str, button_text: str | None = None) -> None:
        self.return_screen_name = screen_name
        self.back_button.text = button_text or ("返回战斗" if screen_name == "game" else "返回主页")

    def go_back(self) -> None:
        self.screen_manager.switch_to(self.return_screen_name)

    def handle_event(self, event: pygame.event.Event) -> None:
        self.back_button.handle_event(event)
        for button in self.category_buttons:
            button.handle_event(event)
        if self.active_category_id == "characters":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_entry_list_click(event.pos)
        elif self.active_category_id == "statuses":
            for button in self.status_filter_buttons:
                button.handle_event(event)
        elif self.active_category_id in ("keywords", "mechanics"):
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_entry_list_click(event.pos)

        if event.type == pygame.MOUSEWHEEL:
            if self.active_category_id in ("characters", "keywords", "mechanics"):
                mouse_pos = pygame.mouse.get_pos()
                if self._entry_list_rect().collidepoint(mouse_pos):
                    self.entry_list_scroll_offset -= event.y * 42
                    self._clamp_entry_list_scroll_offset()
                elif self._entry_detail_rect().collidepoint(mouse_pos):
                    self.entry_detail_scroll_offset -= event.y * 42
                    self._clamp_entry_detail_scroll_offset()
            else:
                self.scroll_offset -= event.y * 42
                self._clamp_scroll_offset()

    def update(self, delta_seconds: float) -> None:
        self._clamp_scroll_offset()
        self._clamp_entry_list_scroll_offset()
        self._clamp_entry_detail_scroll_offset()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(COLORS["background"])

        self._draw_top_bar(surface, "百科大全", "角色、关键词、状态与机制说明")

        self._draw_category_tabs(surface)
        self._draw_content(surface)
        self.back_button.draw(surface)

    def select_category(self, category_id: str) -> None:
        if category_id not in {category[0] for category in CATEGORIES}:
            return
        self.active_category_id = category_id
        self.scroll_offset = 0
        self.entry_list_scroll_offset = 0
        self.entry_detail_scroll_offset = 0
        self.selected_keyword_id = None
        self.selected_mechanic_index = None
        self.selected_character_browser_id = None
        self.selected_character_job_id = None
        if category_id == "statuses":
            self.status_filter_id = "all"

    def select_status_filter(self, filter_id: str) -> None:
        if filter_id not in {"all", "buff", "debuff", "adverse"}:
            return
        self.status_filter_id = filter_id
        self.scroll_offset = 0

    def _build_category_buttons(self) -> list[Button]:
        buttons: list[Button] = []
        start_x = 48
        y = 86
        width = 132
        gap = 14
        for index, (category_id, label) in enumerate(CATEGORIES):
            rect = pygame.Rect(start_x + index * (width + gap), y, width, 42)
            button = Button(
                rect,
                label,
                lambda selected_id=category_id: self.select_category(selected_id),
                font_size=21,
            )
            button.category_id = category_id
            buttons.append(button)
        return buttons

    def _build_status_filter_buttons(self) -> list[Button]:
        buttons: list[Button] = []
        entries = (
            ("all", "全部"),
            ("buff", "Buff"),
            ("debuff", "Debuff"),
            ("adverse", "不利效果"),
        )
        for index, (filter_id, label) in enumerate(entries):
            rect = pygame.Rect(72, 208 + index * 32, 124, 27)
            button = Button(
                rect,
                label,
                lambda selected_id=filter_id: self.select_status_filter(selected_id),
                font_size=14,
            )
            button.filter_id = filter_id
            buttons.append(button)
        return buttons

    def _draw_category_tabs(self, surface: pygame.Surface) -> None:
        for button in self.category_buttons:
            active = getattr(button, "category_id") == self.active_category_id
            fill_color = COLORS["accent_dark"] if active else COLORS["surface_alt"]
            border_color = COLORS["accent"] if active else COLORS["border"]
            text_color = COLORS["text"] if active else COLORS["muted"]
            pygame.draw.rect(surface, fill_color, button.rect, border_radius=8)
            pygame.draw.rect(surface, border_color, button.rect, 2, border_radius=8)
            text_surface = button.font.render(button.text, True, text_color)
            text_rect = text_surface.get_rect(center=button.rect.center)
            surface.blit(text_surface, text_rect)

    def _draw_top_bar(self, surface: pygame.Surface, title: str, description: str) -> None:
        draw_text(surface, title, (48, 24), size=31, bold=True)
        draw_text_fit(surface, description, (190, 34), WINDOW_WIDTH - 240, size=18, color=COLORS["muted"])
        pygame.draw.line(surface, COLORS["border"], (48, 76), (WINDOW_WIDTH - 48, 76), 1)

    def _draw_content(self, surface: pygame.Surface) -> None:
        content_rect = pygame.Rect(48, 146, WINDOW_WIDTH - 96, 476)
        pygame.draw.rect(surface, COLORS["surface"], content_rect, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], content_rect, 2, border_radius=8)

        label = self._category_label(self.active_category_id)
        count = len(self._cards_for_category(self.active_category_id))
        if self.active_category_id == "characters":
            self._draw_character_browser(surface, content_rect)
            return
        if self.active_category_id in ("keywords", "mechanics"):
            self._draw_entry_browser(surface, content_rect)
            return

        title_x = 224 if self.active_category_id == "statuses" else content_rect.x + 22
        draw_text(surface, f"{label}  {count}", (title_x, content_rect.y + 18), size=25, bold=True)

        if self.active_category_id == "statuses":
            draw_text(surface, "状态筛选", (72, 176), size=18, bold=True)
            self._draw_status_filters(surface)

        card_area = self._visible_card_area()
        previous_clip = surface.get_clip()
        surface.set_clip(card_area)
        self._draw_cards(surface, card_area)
        surface.set_clip(previous_clip)
        self._draw_scrollbar(surface, card_area)

    def _draw_cards(self, surface: pygame.Surface, area: pygame.Rect) -> None:
        cards = self._cards_for_category(self.active_category_id)
        if not cards:
            draw_text(surface, "暂无条目", (area.x, area.y), size=22, color=COLORS["muted"])
            return

        column_gap = 16
        row_gap = 14
        column_count = self._column_count_for_category(self.active_category_id)
        card_width = area.width if column_count == 1 else (area.width - column_gap) // 2
        card_height = self._card_height_for_category(self.active_category_id)
        for index, card in enumerate(cards):
            column = index % column_count
            row = index // column_count
            rect = pygame.Rect(
                area.x + column * (card_width + column_gap),
                area.y + row * (card_height + row_gap) - self.scroll_offset,
                card_width,
                card_height,
            )
            if rect.bottom < area.y or rect.y > area.bottom:
                continue
            self._draw_card(surface, rect, card)

    def _draw_status_filters(self, surface: pygame.Surface) -> None:
        for button in self.status_filter_buttons:
            active = getattr(button, "filter_id") == self.status_filter_id
            fill_color = COLORS["accent_dark"] if active else COLORS["surface_alt"]
            border_color = COLORS["accent"] if active else COLORS["border"]
            text_color = COLORS["text"] if active else COLORS["muted"]
            pygame.draw.rect(surface, fill_color, button.rect, border_radius=7)
            pygame.draw.rect(surface, border_color, button.rect, 2 if active else 1, border_radius=7)
            text_surface = button.font.render(button.text, True, text_color)
            text_rect = text_surface.get_rect(center=button.rect.center)
            surface.blit(text_surface, text_rect)

    def _draw_card(self, surface: pygame.Surface, rect: pygame.Rect, card: EncyclopediaCard) -> None:
        pygame.draw.rect(surface, COLORS["surface_alt"], rect, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], rect, 1, border_radius=8)
        draw_text(surface, card.title, (rect.x + 14, rect.y + 10), size=21, bold=True)
        draw_text(surface, card.subtitle, (rect.x + 14, rect.y + 38), size=15, color=COLORS["accent"])

        previous_clip = surface.get_clip()
        surface.set_clip(pygame.Rect(rect.x + 8, rect.y + 8, rect.width - 16, rect.height - 16).clip(previous_clip))
        y = rect.y + 64
        for line in card.lines:
            max_lines = None if self.active_category_id == "mechanics" else 2
            y = self._draw_wrapped_text(surface, line, rect.x + 14, y, rect.width - 28, max_lines=max_lines)
            if y > rect.bottom - 16:
                break
        surface.set_clip(previous_clip)

    def _draw_scrollbar(self, surface: pygame.Surface, area: pygame.Rect) -> None:
        content_height = self._content_height()
        if content_height <= area.height:
            return

        track = pygame.Rect(area.right + 8, area.y, 6, area.height)
        thumb_height = max(38, int(area.height * area.height / content_height))
        max_offset = content_height - area.height
        thumb_y = area.y + int((area.height - thumb_height) * self.scroll_offset / max_offset)
        thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_height)
        pygame.draw.rect(surface, COLORS["background"], track, border_radius=3)
        pygame.draw.rect(surface, COLORS["border"], thumb, border_radius=3)

    def _draw_wrapped_text(
        self,
        surface: pygame.Surface,
        text: str,
        x: int,
        y: int,
        max_width: int,
        *,
        max_lines: int | None = None,
    ) -> int:
        font_size = 14
        line_height = 18
        font = get_font(font_size)
        lines = self._wrap_text(text, font, max_width, max_lines)
        for line in lines:
            draw_text(surface, line, (x, y), size=font_size, color=COLORS["text"])
            y += line_height
        return y + 2

    def _wrap_text(
        self,
        text: str,
        font: pygame.font.Font,
        max_width: int,
        max_lines: int | None = None,
    ) -> list[str]:
        if not text:
            return []

        lines: list[str] = []
        current = ""
        for character in text:
            candidate = current + character
            if current and font.size(candidate)[0] > max_width:
                lines.append(current)
                current = character
                if max_lines is not None and len(lines) == max_lines:
                    break
            else:
                current = candidate

        if (max_lines is None or len(lines) < max_lines) and current:
            lines.append(current)

        if max_lines is not None and len(lines) == max_lines:
            consumed = "".join(lines)
            if len(consumed) < len(text):
                while lines[-1] and font.size(lines[-1] + "...")[0] > max_width:
                    lines[-1] = lines[-1][:-1]
                lines[-1] = (lines[-1] + "...") if lines[-1] else "..."
        return lines

    def _draw_entry_browser(self, surface: pygame.Surface, content_rect: pygame.Rect) -> None:
        entries = self._entry_browser_cards(self.active_category_id)
        title = "关键词目录" if self.active_category_id == "keywords" else "机制目录"
        draw_text(surface, f"{self._category_label(self.active_category_id)}  {len(entries)}", (content_rect.x + 22, content_rect.y + 18), size=25, bold=True)
        draw_text(surface, title, (content_rect.x + 22, content_rect.y + 62), size=18, bold=True)

        list_rect = self._entry_list_rect()
        detail_rect = self._entry_detail_rect()
        self.entry_list_hit_rects = []
        self._clamp_entry_list_scroll_offset()
        self._clamp_entry_detail_scroll_offset()

        pygame.draw.rect(surface, COLORS["surface_alt"], list_rect, border_radius=7)
        pygame.draw.rect(surface, COLORS["border"], list_rect, 1, border_radius=7)
        pygame.draw.rect(surface, COLORS["surface_alt"], detail_rect, border_radius=7)
        pygame.draw.rect(surface, COLORS["border"], detail_rect, 1, border_radius=7)

        row_height = 34
        previous_clip = surface.get_clip()
        surface.set_clip(list_rect)
        y = list_rect.y + 8 - self.entry_list_scroll_offset
        selected_key = self._selected_entry_key()
        for key, card in entries:
            row_rect = pygame.Rect(list_rect.x + 8, y, list_rect.width - 16, 28)
            if row_rect.bottom >= list_rect.y and row_rect.y <= list_rect.bottom:
                active = key == selected_key
                fill = COLORS["accent_dark"] if active else COLORS["surface"]
                border = COLORS["accent"] if active else COLORS["border"]
                pygame.draw.rect(surface, fill, row_rect, border_radius=6)
                pygame.draw.rect(surface, border, row_rect, 1, border_radius=6)
                draw_text_fit(surface, card.title, (row_rect.x + 8, row_rect.y + 5), row_rect.width - 16, size=13)
                self.entry_list_hit_rects.append((row_rect, key))
            y += row_height
        surface.set_clip(previous_clip)

        list_content_height = max(0, len(entries) * row_height + 16)
        if list_content_height > list_rect.height:
            self._draw_scrollbar_with_offset(surface, list_rect, list_content_height, self.entry_list_scroll_offset)

        selected_card = self._selected_entry_card()
        if selected_card is None:
            return

        items = [
            (selected_card.title, 24, None, True),
            (selected_card.subtitle, 15, COLORS["accent"], False),
            ("", 0, None, False),
            *[(line, 15, COLORS["text"], False) for line in selected_card.lines],
        ]
        content_height = self._text_items_height(items, detail_rect.width - 30)
        max_offset = max(0, content_height - (detail_rect.height - 24))
        self.entry_detail_scroll_offset = max(0, min(self.entry_detail_scroll_offset, max_offset))

        detail_content_rect = pygame.Rect(detail_rect.x + 16, detail_rect.y + 14, detail_rect.width - 30, detail_rect.height - 24)
        previous_clip = surface.get_clip()
        surface.set_clip(detail_content_rect)
        y = detail_content_rect.y - self.entry_detail_scroll_offset
        for text, size, color, bold in items:
            if text == "":
                y += 8
                continue
            font = get_font(size, bold=bold)
            line_height = int(size * 1.35)
            for line in self._wrap_text(text, font, detail_content_rect.width - 8):
                if y + line_height >= detail_content_rect.y and y <= detail_content_rect.bottom:
                    draw_text(surface, line, (detail_content_rect.x, y), size=size, color=color, bold=bold)
                y += line_height
            y += 4
        surface.set_clip(previous_clip)

        if content_height > detail_content_rect.height:
            self._draw_scrollbar_with_offset(
                surface,
                detail_content_rect,
                content_height,
                self.entry_detail_scroll_offset,
            )

    def _draw_character_browser(self, surface: pygame.Surface, content_rect: pygame.Rect) -> None:
        entries = self._character_browser_rows()
        draw_text(
            surface,
            f"角色  {len(CHARACTER_DEFINITIONS)}",
            (content_rect.x + 22, content_rect.y + 18),
            size=25,
            bold=True,
        )
        draw_text(surface, "角色目录", (content_rect.x + 22, content_rect.y + 62), size=18, bold=True)

        list_rect = self._entry_list_rect()
        detail_rect = self._entry_detail_rect()
        self.entry_list_hit_rects = []
        self._clamp_entry_list_scroll_offset()
        self._clamp_entry_detail_scroll_offset()

        pygame.draw.rect(surface, COLORS["surface_alt"], list_rect, border_radius=7)
        pygame.draw.rect(surface, COLORS["border"], list_rect, 1, border_radius=7)
        pygame.draw.rect(surface, COLORS["surface_alt"], detail_rect, border_radius=7)
        pygame.draw.rect(surface, COLORS["border"], detail_rect, 1, border_radius=7)

        row_height = 34
        previous_clip = surface.get_clip()
        surface.set_clip(list_rect)
        y = list_rect.y + 8 - self.entry_list_scroll_offset
        selected_key = self._selected_character_browser_key()
        for kind, entry_id, depth in entries:
            key = f"{kind}:{entry_id}"
            row_rect = pygame.Rect(list_rect.x + 8, y, list_rect.width - 16, 28)
            if row_rect.bottom >= list_rect.y and row_rect.y <= list_rect.bottom:
                active = key == selected_key
                fill = COLORS["accent_dark"] if active else COLORS["surface"]
                border = COLORS["accent"] if active else COLORS["border"]
                pygame.draw.rect(surface, fill, row_rect, border_radius=6)
                pygame.draw.rect(surface, border, row_rect, 1, border_radius=6)
                label = self._character_browser_label(kind, entry_id)
                x_offset = 8 + depth * 18
                draw_text_fit(surface, label, (row_rect.x + x_offset, row_rect.y + 5), row_rect.width - x_offset - 8, size=13)
                self.entry_list_hit_rects.append((row_rect, key))
            y += row_height
        surface.set_clip(previous_clip)

        list_content_height = max(0, len(entries) * row_height + 16)
        if list_content_height > list_rect.height:
            self._draw_scrollbar_with_offset(surface, list_rect, list_content_height, self.entry_list_scroll_offset)

        items = self._selected_character_browser_items()
        if not items:
            return

        content_height = self._text_items_height(items, detail_rect.width - 30)
        max_offset = max(0, content_height - (detail_rect.height - 24))
        self.entry_detail_scroll_offset = max(0, min(self.entry_detail_scroll_offset, max_offset))

        detail_content_rect = pygame.Rect(detail_rect.x + 16, detail_rect.y + 14, detail_rect.width - 30, detail_rect.height - 24)
        previous_clip = surface.get_clip()
        surface.set_clip(detail_content_rect)
        y = detail_content_rect.y - self.entry_detail_scroll_offset
        for text, size, color, bold in items:
            if text == "":
                y += 8
                continue
            font = get_font(size, bold=bold)
            line_height = int(size * 1.35)
            for line in self._wrap_text(text, font, detail_content_rect.width - 8):
                if y + line_height >= detail_content_rect.y and y <= detail_content_rect.bottom:
                    draw_text(surface, line, (detail_content_rect.x, y), size=size, color=color, bold=bold)
                y += line_height
            y += 4
        surface.set_clip(previous_clip)

        if content_height > detail_content_rect.height:
            self._draw_scrollbar_with_offset(
                surface,
                detail_content_rect,
                content_height,
                self.entry_detail_scroll_offset,
            )

    def _character_browser_rows(self) -> list[tuple[str, str, int]]:
        rows: list[tuple[str, str, int]] = []
        for job in JOBS:
            rows.append(("job", job.id, 0))
            if job.id not in self.character_job_expanded_ids:
                continue
            rows.extend(("character", character.id, 1) for character in self._characters_for_job(job.id))
        return rows

    def _characters_for_job(self, job_id: str) -> list[CharacterDefinition]:
        return sorted(
            (character for character in CHARACTER_DEFINITIONS if character.job_id == job_id),
            key=lambda character: (character.name, character.id),
        )

    def _character_browser_label(self, kind: str, entry_id: str) -> str:
        if kind == "job":
            job = JOBS_BY_ID[entry_id]
            prefix = "-" if entry_id in self.character_job_expanded_ids else "+"
            return f"{prefix} {job.name}"
        character = CHARACTER_DEFINITIONS_BY_ID[entry_id]
        return character.name

    def _selected_character_browser_key(self) -> str | None:
        if self.selected_character_browser_id is not None:
            return f"character:{self.selected_character_browser_id}"
        if self.selected_character_job_id is not None:
            return f"job:{self.selected_character_job_id}"
        return None

    def _selected_character_browser_items(self) -> list[TextItem]:
        if self.selected_character_browser_id is not None:
            character = CHARACTER_DEFINITIONS_BY_ID.get(self.selected_character_browser_id)
            return self._character_detail_items(character) if character is not None else []
        if self.selected_character_job_id is not None:
            job = JOBS_BY_ID.get(self.selected_character_job_id)
            return self._job_detail_items(job) if job is not None else []
        return []

    def _job_detail_items(self, job: Job) -> list[TextItem]:
        card = self._job_card(job)
        return [
            (card.title, 24, None, True),
            (card.subtitle, 15, COLORS["accent"], False),
            ("", 0, None, False),
            *[(line, 15, COLORS["text"], False) for line in card.lines],
        ]

    def _entry_browser_cards(self, category_id: str) -> list[tuple[str, EncyclopediaCard]]:
        if category_id == "keywords":
            return [
                (effect.id, self._effect_card(effect))
                for effect in EFFECTS
                if effect.category == EffectCategory.KEYWORD and effect.show_in_encyclopedia
            ]
        if category_id == "mechanics":
            return [
                (str(index), self._mechanic_card(entry))
                for index, entry in enumerate(MECHANIC_ENTRIES)
            ]
        return []

    def _selected_entry_key(self) -> str | None:
        if self.active_category_id == "keywords":
            return self.selected_keyword_id
        if self.active_category_id == "mechanics" and self.selected_mechanic_index is not None:
            return str(self.selected_mechanic_index)
        return None

    def _selected_entry_card(self) -> EncyclopediaCard | None:
        selected_key = self._selected_entry_key()
        if selected_key is None:
            return None
        for key, card in self._entry_browser_cards(self.active_category_id):
            if key == selected_key:
                return card
        return None

    def _handle_entry_list_click(self, position: tuple[int, int]) -> None:
        for rect, key in self.entry_list_hit_rects:
            if not rect.collidepoint(position):
                continue
            if self.active_category_id == "characters":
                self._select_character_browser_key(key)
            elif self.active_category_id == "keywords":
                self.selected_keyword_id = key
            elif self.active_category_id == "mechanics":
                self.selected_mechanic_index = int(key)
            self.entry_detail_scroll_offset = 0
            return

    def _select_character_browser_key(self, key: str) -> None:
        if key.startswith("job:"):
            job_id = key.removeprefix("job:")
            if job_id in self.character_job_expanded_ids:
                self.character_job_expanded_ids.remove(job_id)
            else:
                self.character_job_expanded_ids.add(job_id)
            self.selected_character_job_id = job_id
            self.selected_character_browser_id = None
            self._clamp_entry_list_scroll_offset()
        elif key.startswith("character:"):
            self.selected_character_browser_id = key.removeprefix("character:")
            self.selected_character_job_id = None

    def _text_items_height(self, items: list[TextItem], width: int) -> int:
        height = 0
        for text, size, _color, bold in items:
            if text == "":
                height += 8
                continue
            font = get_font(size, bold=bold)
            height += len(self._wrap_text(text, font, width - 8)) * int(size * 1.35) + 4
        return height

    def _cards_for_category(self, category_id: str) -> list[EncyclopediaCard]:
        if category_id == "characters":
            characters = sorted(
                CHARACTER_DEFINITIONS,
                key=lambda character: (JOB_ORDER.get(character.job_id, 999), character.name, character.id),
            )
            return [self._character_card(character) for character in characters]
        if category_id == "jobs":
            return [self._job_card(job) for job in JOBS]
        if category_id == "keywords":
            return [
                self._effect_card(effect)
                for effect in EFFECTS
                if effect.category == EffectCategory.KEYWORD and effect.show_in_encyclopedia
            ]
        if category_id == "statuses":
            return [
                self._effect_card(effect)
                for effect in EFFECTS
                if effect.category != EffectCategory.KEYWORD and self._status_matches_filter(effect)
            ]
        if category_id == "mechanics":
            return [self._mechanic_card(entry) for entry in MECHANIC_ENTRIES]
        return []

    def _status_matches_filter(self, effect: Effect) -> bool:
        if self.status_filter_id == "buff":
            return effect.category == EffectCategory.BUFF
        if self.status_filter_id == "debuff":
            return effect.category == EffectCategory.DEBUFF
        if self.status_filter_id == "adverse":
            return effect.category == EffectCategory.DEBUFF and effect.is_adverse
        return True

    def _character_card(self, character: CharacterDefinition) -> EncyclopediaCard:
        job = JOBS_BY_ID[character.job_id]
        faction_text = f"   阵营 {'、'.join(character.factions)}" if character.factions else ""
        lines = [
            f"职业效果：{job.description}",
            f"角色被动：{self._passive_description(character)}",
        ]
        if character.active_skills:
            lines.extend(f"角色主动：{self._active_skill_description(skill)}" for skill in character.active_skills)
        else:
            lines.append("角色主动：无")
        return EncyclopediaCard(
            title=character.name,
            subtitle=f"{job.name}   HP {character.max_health}   ATK {character.attack}{faction_text}",
            lines=tuple(lines),
            entry_id=character.id,
        )

    def _passive_description(self, character: CharacterDefinition) -> str:
        description = character.passive_description.strip()
        if not description:
            return "无"
        return description

    def _active_skill_description(self, skill) -> str:
        return active_skill_display_text(skill)

    def _job_card(self, job: Job) -> EncyclopediaCard:
        effect_names = "、".join(EFFECTS_BY_ID[effect_id].name for effect_id in job.effect_ids if effect_id in EFFECTS_BY_ID)
        restrictions = "、".join(self._placement_restriction_text(restriction) for restriction in job.placement_restrictions)
        lines = (
            job.description,
            f"职业效果：{effect_names or '无'}",
            f"放置限制：{restrictions or '无'}",
        )
        return EncyclopediaCard(
            title=job.name,
            subtitle=f"默认移动 {job.default_move_count}",
            lines=lines,
        )

    def _effect_card(self, effect: Effect) -> EncyclopediaCard:
        category_name = self._effect_category_text(effect)
        adverse_text = " / 不利效果" if effect.is_adverse else ""
        return EncyclopediaCard(
            title=effect.name,
            subtitle=f"{category_name}{adverse_text}",
            lines=(effect.description,),
        )

    def _mechanic_card(self, entry: MechanicEntry) -> EncyclopediaCard:
        return EncyclopediaCard(
            title=entry.title,
            subtitle=entry.subtitle,
            lines=entry.lines,
        )

    def _character_detail_items(self, character: CharacterDefinition) -> list[TextItem]:
        job = JOBS_BY_ID[character.job_id]
        faction_text = "、".join(character.factions) if character.factions else "无"
        items: list[TextItem] = [
            (character.name, 28, None, True),
            (f"{job.name}   HP {character.max_health}   ATK {character.attack}   阵营 {faction_text}", 16, COLORS["accent"], False),
            ("", 0, None, False),
            (f"职业效果：{job.description}", 15, COLORS["muted"], False),
            (f"角色被动技能：{self._passive_description(character)}", 15, COLORS["muted"], False),
        ]

        if character.active_skills:
            items.extend(
                (f"角色主动技能：{self._active_skill_description(skill)}", 15, COLORS["muted"], False)
                for skill in character.active_skills
            )
        else:
            items.append(("角色主动技能：无", 15, COLORS["muted"], False))

        mechanic_lines = CHARACTER_MECHANIC_DETAILS.get(character.id, ())
        if mechanic_lines:
            items.extend([("", 0, None, False), ("机制解释", 17, None, True)])
            items.extend((line, 14, COLORS["muted"], False) for line in mechanic_lines)

        return items

    def _placement_restriction_text(self, restriction: PlacementRestriction) -> str:
        if restriction == PlacementRestriction.FRONT_ONLY:
            return "只能前排"
        if restriction == PlacementRestriction.ROW_PAIR_EXCLUSIVE:
            return "同一行前后不可有单位"
        return restriction.value

    def _effect_category_text(self, effect: Effect) -> str:
        if effect.category == EffectCategory.KEYWORD:
            return "关键词"
        if effect.category == EffectCategory.BUFF:
            return "Buff"
        if effect.category == EffectCategory.DEBUFF:
            return "Debuff"
        return effect.category.value

    def _category_label(self, category_id: str) -> str:
        return dict(CATEGORIES).get(category_id, "百科")

    def _visible_card_area(self) -> pygame.Rect:
        if self.active_category_id in ("characters", "statuses"):
            return pygame.Rect(224, 208, WINDOW_WIDTH - 296, 390)
        return pygame.Rect(72, 208, WINDOW_WIDTH - 144, 390)

    def _entry_list_rect(self) -> pygame.Rect:
        return pygame.Rect(72, 236, 260, 362)

    def _entry_detail_rect(self) -> pygame.Rect:
        return pygame.Rect(356, 208, WINDOW_WIDTH - 428, 390)

    def _column_count_for_category(self, category_id: str) -> int:
        if category_id in ("mechanics", "keywords"):
            return 1
        return 2

    def _card_height_for_category(self, category_id: str) -> int:
        if category_id == "characters":
            return 176
        if category_id == "mechanics":
            return 226
        return 118

    def _content_height(self) -> int:
        if self.active_category_id in ("keywords", "mechanics"):
            return 0
        cards = self._cards_for_category(self.active_category_id)
        if not cards:
            return 0

        column_count = self._column_count_for_category(self.active_category_id)
        rows = (len(cards) + column_count - 1) // column_count
        card_height = self._card_height_for_category(self.active_category_id)
        return rows * card_height + max(0, rows - 1) * 14

    def _clamp_scroll_offset(self) -> None:
        max_offset = max(0, self._content_height() - self._visible_card_area().height)
        self.scroll_offset = max(0, min(self.scroll_offset, max_offset))

    def _entry_list_content_height(self) -> int:
        if self.active_category_id == "characters":
            return max(0, len(self._character_browser_rows()) * 34 + 16)
        return max(0, len(self._entry_browser_cards(self.active_category_id)) * 34 + 16)

    def _clamp_entry_list_scroll_offset(self) -> None:
        if self.active_category_id not in ("characters", "keywords", "mechanics"):
            self.entry_list_scroll_offset = 0
            return
        max_offset = max(0, self._entry_list_content_height() - self._entry_list_rect().height)
        self.entry_list_scroll_offset = max(0, min(self.entry_list_scroll_offset, max_offset))

    def _clamp_entry_detail_scroll_offset(self) -> None:
        if self.active_category_id not in ("characters", "keywords", "mechanics"):
            self.entry_detail_scroll_offset = 0
            return
        if self.active_category_id == "characters":
            items = self._selected_character_browser_items()
            if not items:
                self.entry_detail_scroll_offset = 0
                return
            detail_rect = self._entry_detail_rect()
            content_width = detail_rect.width - 30
            content_height = self._text_items_height(items, content_width)
            max_offset = max(0, content_height - (detail_rect.height - 24))
            self.entry_detail_scroll_offset = max(0, min(self.entry_detail_scroll_offset, max_offset))
            return
        selected_card = self._selected_entry_card()
        if selected_card is None:
            self.entry_detail_scroll_offset = 0
            return
        items = [
            (selected_card.title, 24, None, True),
            (selected_card.subtitle, 15, COLORS["accent"], False),
            ("", 0, None, False),
            *[(line, 15, COLORS["text"], False) for line in selected_card.lines],
        ]
        detail_rect = self._entry_detail_rect()
        content_width = detail_rect.width - 30
        content_height = self._text_items_height(items, content_width)
        max_offset = max(0, content_height - (detail_rect.height - 24))
        self.entry_detail_scroll_offset = max(0, min(self.entry_detail_scroll_offset, max_offset))

    def _draw_scrollbar_with_offset(
        self,
        surface: pygame.Surface,
        area: pygame.Rect,
        content_height: int,
        scroll_offset: int,
    ) -> None:
        if content_height <= area.height:
            return

        track = pygame.Rect(area.right - 5, area.y, 4, area.height)
        thumb_height = max(30, int(area.height * area.height / content_height))
        max_offset = content_height - area.height
        thumb_y = area.y + int((area.height - thumb_height) * scroll_offset / max_offset)
        thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_height)
        pygame.draw.rect(surface, COLORS["background"], track, border_radius=2)
        pygame.draw.rect(surface, COLORS["border"], thumb, border_radius=2)
