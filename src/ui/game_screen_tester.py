from __future__ import annotations

import pygame

from src.config import COLORS, WINDOW_HEIGHT, WINDOW_WIDTH
from src.core import Character, EffectCategory, FormationColumn, GamePhase, Position
from src.data import CHARACTER_DEFINITIONS
from src.data.keywords import EFFECTS
from src.data.jobs import JOBS
from src.ui.components import draw_text, draw_text_fit, draw_wrapped_text


JOB_NAME_BY_ID = {job.id: job.name for job in JOBS}


class GameScreenTesterMixin:
    def _handle_tester_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.tester_dropdown is not None:
                self.tester_dropdown = None
            else:
                self.tester_open = False
            return
        if event.type == pygame.MOUSEWHEEL:
            if self.tester_dropdown is not None:
                self.tester_dropdown_scroll_offset -= event.y * 30
                self._clamp_tester_dropdown_scroll_offset()
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if not self._tester_window_rect().collidepoint(event.pos):
            self.tester_open = False
            self.tester_dropdown = None
            return

        if self.tester_dropdown is not None:
            for item_rect, dropdown_id, index in self.tester_dropdown_item_rects:
                if dropdown_id == self.tester_dropdown and item_rect.collidepoint(event.pos):
                    self._select_tester_dropdown_item(dropdown_id, index)
                    return
            if self.tester_dropdown_rect is not None and self.tester_dropdown_rect.collidepoint(event.pos):
                return
            selector_rect = self.tester_selector_rects.get(self.tester_dropdown)
            if selector_rect is not None and selector_rect.collidepoint(event.pos):
                self.tester_dropdown = None
                self.tester_dropdown_scroll_offset = 0
                return
            self.tester_dropdown = None

        for rect, player_id, position in self.tester_slot_rects:
            if rect.collidepoint(event.pos):
                self.tester_selected_slot = (player_id, position)
                return

        for action, rect in self.tester_action_rects.items():
            if not rect.collidepoint(event.pos):
                continue
            self._run_tester_action(action)
            return

    def _run_tester_action(self, action: str) -> None:
        if action == "close":
            self.tester_open = False
            self.tester_dropdown = None
            return

        if action in ("replace_dropdown", "debuff_dropdown", "buff_dropdown"):
            self._toggle_tester_dropdown(action.replace("_dropdown", ""))
            return

        if action == "quick_battle":
            self.quick_enter_battle()
            return

        if action == "replace_prev":
            self.tester_replace_index = (self.tester_replace_index - 1) % len(CHARACTER_DEFINITIONS)
            self.tester_dropdown = None
            return
        if action == "replace_next":
            self.tester_replace_index = (self.tester_replace_index + 1) % len(CHARACTER_DEFINITIONS)
            self.tester_dropdown = None
            return
        debuffs = self._tester_debuff_effects()
        if action == "debuff_prev" and debuffs:
            self.tester_debuff_index = (self.tester_debuff_index - 1) % len(debuffs)
            self.tester_dropdown = None
            return
        if action == "debuff_next" and debuffs:
            self.tester_debuff_index = (self.tester_debuff_index + 1) % len(debuffs)
            self.tester_dropdown = None
            return
        buffs = self._tester_buff_effects()
        if action == "buff_prev" and buffs:
            self.tester_buff_index = (self.tester_buff_index - 1) % len(buffs)
            self.tester_dropdown = None
            return
        if action == "buff_next" and buffs:
            self.tester_buff_index = (self.tester_buff_index + 1) % len(buffs)
            self.tester_dropdown = None
            return
        if action == "amount_minus_5":
            self.tester_amount = max(1, self.tester_amount - 5)
            return
        if action == "amount_minus_1":
            self.tester_amount = max(1, self.tester_amount - 1)
            return
        if action == "amount_plus_1":
            self.tester_amount += 1
            return
        if action == "amount_plus_5":
            self.tester_amount += 5
            return

        session = self.battle_session if self.game_state.phase == GamePhase.BATTLE else None
        if session is None:
            self.message = "修改器仅在战斗阶段可用。"
            return

        if action == "reset_order":
            session.debug_reset_move_orders()
            self._log_battle("修改器：已重置所有角色的移动顺序。")
            self._sync_battle_button_states()
            return

        if self.tester_selected_slot is None:
            self.message = "请先在修改器中选择一个阵位。"
            return

        player_id, position = self.tester_selected_slot
        position_text = f"{self.game_state.player(player_id).name} {self._position_label(position)}"
        if action == "clear":
            cleared = session.debug_clear_position(player_id, position)
            if cleared is None:
                self._log_battle(f"修改器：{position_text} 已是空位。")
            else:
                self._log_battle(f"修改器：已清空 {position_text} 的 {cleared.name}。")
            self.selected_battle_actor_id = None
            self.selected_battle_character = None
            self._sync_battle_button_states()
            return

        if action == "replace":
            definition = CHARACTER_DEFINITIONS[self.tester_replace_index]
            character = session.debug_replace_position(player_id, position, definition.id)
            self._log_battle(f"修改器：{position_text} 替换为 {character.name}。")
            self.selected_battle_character = (player_id, character.id)
            self.selected_battle_actor_id = character.id if session.current_player_id == player_id else None
            self._sync_battle_button_states()
            return

        target = self._tester_selected_character()
        if target is None:
            self.message = "该阵位为空，无法对角色执行此操作。"
            return

        target_player_id, target_character = target
        before_health = self._battle_health_snapshot()
        if action == "apply_debuff" and debuffs:
            effect = debuffs[self.tester_debuff_index % len(debuffs)]
            applied = session.debug_apply_debuff(target_player_id, target_character.id, effect.id)
            result = "成功" if applied else "失败"
            self._log_battle(f"修改器：对 {target_character.name} 施加 {effect.name}，{result}。")
        elif action == "apply_buff" and buffs:
            effect = buffs[self.tester_buff_index % len(buffs)]
            applied = session.debug_apply_buff(target_player_id, target_character.id, effect.id)
            result = "成功" if applied else "失败"
            self._log_battle(f"修改器：对 {target_character.name} 施加 {effect.name}，{result}。")
        elif action == "damage":
            dealt = session.debug_deal_damage(target_player_id, target_character.id, self.tester_amount)
            self._log_battle(f"修改器：对 {target_character.name} 造成 {dealt} 点伤害。")
        elif action == "heal":
            healed = session.debug_heal(target_player_id, target_character.id, self.tester_amount)
            self._log_battle(f"修改器：为 {target_character.name} 恢复 {healed} 点生命。")
        self._queue_health_change_animation(None, before_health)

        self._sync_battle_button_states()

    def _draw_tester_window(self, surface: pygame.Surface) -> None:
        if not self.tester_open:
            return

        rect = self._tester_window_rect()
        self.tester_slot_rects = []
        self.tester_action_rects = {}
        self.tester_selector_rects = {}
        self.tester_dropdown_item_rects = []
        self.tester_dropdown_rect = None

        pygame.draw.rect(surface, COLORS["shadow"], rect.move(8, 8), border_radius=8)
        pygame.draw.rect(surface, COLORS["surface"], rect, border_radius=8)
        pygame.draw.rect(surface, COLORS["accent"], rect, 2, border_radius=8)
        draw_text(surface, "战斗修改器", (rect.x + 24, rect.y + 18), size=25, bold=True)
        draw_text(surface, "选择阵位后执行操作", (rect.x + 170, rect.y + 26), size=15, color=COLORS["muted"])
        self._draw_tester_button(surface, "close", pygame.Rect(rect.right - 68, rect.y + 18, 44, 30), "关闭")

        if self.game_state.phase != GamePhase.BATTLE or self.battle_session is None:
            draw_wrapped_text(surface, "当前不在战斗阶段。进入战斗后可以查看十二个阵位并修改角色状态。", (rect.x + 34, rect.y + 84), rect.width - 68, size=18, color=COLORS["muted"], line_height=25)
            self._draw_tester_button(surface, "quick_battle", pygame.Rect(rect.x + 34, rect.y + 150, 156, 34), "快速进战斗")
            return

        self._draw_tester_slots(surface, pygame.Rect(rect.x + 24, rect.y + 62, 550, rect.height - 92))
        self._draw_tester_controls(surface, pygame.Rect(rect.x + 596, rect.y + 62, rect.width - 620, rect.height - 92))
        self._draw_tester_dropdown(surface)

    def _draw_tester_slots(self, surface: pygame.Surface, area: pygame.Rect) -> None:
        draw_text(surface, "十二阵位", (area.x, area.y), size=19, bold=True)
        slot_width = 124
        slot_height = 54
        gap_x = 12
        gap_y = 10
        side_gap = 22
        start_y = area.y + 34
        for player_index, player_id in enumerate((1, 2)):
            player = self.game_state.player(player_id)
            side_x = area.x + player_index * (slot_width * 2 + gap_x + side_gap)
            draw_text(surface, player.name, (side_x, start_y), size=16, color=COLORS["accent"], bold=True)
            columns = (
                (FormationColumn.BACK, FormationColumn.FRONT)
                if player_id == 1
                else (FormationColumn.FRONT, FormationColumn.BACK)
            )
            for row in range(3):
                for column_index, column in enumerate(columns):
                    position = Position(row=row, column=column)
                    rect = pygame.Rect(
                        side_x + column_index * (slot_width + gap_x),
                        start_y + 28 + row * (slot_height + gap_y),
                        slot_width,
                        slot_height,
                    )
                    selected = self.tester_selected_slot == (player_id, position)
                    border_color = COLORS["accent"] if selected else COLORS["border"]
                    pygame.draw.rect(surface, COLORS["surface_alt"], rect, border_radius=7)
                    pygame.draw.rect(surface, border_color, rect, 2 if selected else 1, border_radius=7)
                    draw_text(surface, f"第{row + 1}行{self._column_label(column)}", (rect.x + 8, rect.y + 6), size=12, color=COLORS["muted"])
                    character = player.character_at(position)
                    name = character.name if character is not None else "空位"
                    color = COLORS["text"] if character is not None else COLORS["muted"]
                    draw_text_fit(surface, name, (rect.x + 8, rect.y + 28), rect.width - 16, size=16, color=color, bold=character is not None)
                    self.tester_slot_rects.append((rect, player_id, position))

    def _draw_tester_controls(self, surface: pygame.Surface, area: pygame.Rect) -> None:
        selected_text = "未选择阵位"
        selected_character = self._tester_selected_character()
        if self.tester_selected_slot is not None:
            player_id, position = self.tester_selected_slot
            selected_text = f"{self.game_state.player(player_id).name} / {self._position_label(position)}"
        draw_text(surface, "操作", (area.x, area.y), size=19, bold=True)
        draw_text_fit(surface, selected_text, (area.x, area.y + 30), area.width, size=15, color=COLORS["accent"])
        if selected_character is None:
            draw_text(surface, "目标：空位", (area.x, area.y + 54), size=14, color=COLORS["muted"])
        else:
            _player_id, character = selected_character
            draw_text_fit(surface, f"目标：{character.name}  HP {character.current_health}/{character.max_health}", (area.x, area.y + 54), area.width, size=14, color=COLORS["muted"])

        y = area.y + 82
        self._draw_tester_button(surface, "clear", pygame.Rect(area.x, y, 108, 30), "清空阵位")
        self._draw_tester_button(surface, "reset_order", pygame.Rect(area.x + 118, y, 142, 30), "重置移动顺序")

        y += 42
        definition = CHARACTER_DEFINITIONS[self.tester_replace_index % len(CHARACTER_DEFINITIONS)]
        draw_text(surface, "替换角色", (area.x, y), size=15, bold=True)
        row_y = y + 22
        self._draw_tester_button(surface, "replace_prev", pygame.Rect(area.x, row_y, 28, 28), "<")
        self._draw_tester_selector(surface, "replace", pygame.Rect(area.x + 34, row_y, 150, 28), definition.name)
        self._draw_tester_button(surface, "replace_next", pygame.Rect(area.x + 190, row_y, 28, 28), ">")
        self._draw_tester_button(surface, "replace", pygame.Rect(area.x + 226, row_y, 96, 28), "替换")

        y += 62
        debuffs = self._tester_debuff_effects()
        buffs = self._tester_buff_effects()
        debuff = debuffs[self.tester_debuff_index % len(debuffs)] if debuffs else None
        buff = buffs[self.tester_buff_index % len(buffs)] if buffs else None
        draw_text(surface, "状态", (area.x, y), size=15, bold=True)
        row_y = y + 22
        draw_text(surface, "Debuff", (area.x, row_y + 6), size=12, color=COLORS["muted"], bold=True)
        self._draw_tester_button(surface, "debuff_prev", pygame.Rect(area.x + 58, row_y, 26, 28), "<", enabled=bool(debuffs))
        self._draw_tester_selector(surface, "debuff", pygame.Rect(area.x + 90, row_y, 118, 28), debuff.name if debuff is not None else "无", enabled=bool(debuffs))
        self._draw_tester_button(surface, "debuff_next", pygame.Rect(area.x + 214, row_y, 26, 28), ">", enabled=bool(debuffs))
        self._draw_tester_button(surface, "apply_debuff", pygame.Rect(area.x + 250, row_y, 72, 28), "施加", enabled=selected_character is not None and bool(debuffs))

        row_y += 36
        draw_text(surface, "Buff", (area.x, row_y + 6), size=12, color=COLORS["muted"], bold=True)
        self._draw_tester_button(surface, "buff_prev", pygame.Rect(area.x + 58, row_y, 26, 28), "<", enabled=bool(buffs))
        self._draw_tester_selector(surface, "buff", pygame.Rect(area.x + 90, row_y, 118, 28), buff.name if buff is not None else "无", enabled=bool(buffs))
        self._draw_tester_button(surface, "buff_next", pygame.Rect(area.x + 214, row_y, 26, 28), ">", enabled=bool(buffs))
        self._draw_tester_button(surface, "apply_buff", pygame.Rect(area.x + 250, row_y, 72, 28), "施加", enabled=selected_character is not None and bool(buffs))

        y += 102
        draw_text(surface, "数值", (area.x, y), size=15, bold=True)
        amount_y = y + 22
        self._draw_tester_button(surface, "amount_minus_5", pygame.Rect(area.x, amount_y, 36, 28), "-5")
        self._draw_tester_button(surface, "amount_minus_1", pygame.Rect(area.x + 42, amount_y, 36, 28), "-1")
        pygame.draw.rect(surface, COLORS["surface_alt"], pygame.Rect(area.x + 84, amount_y, 62, 28), border_radius=7)
        draw_text_fit(surface, str(self.tester_amount), (area.x + 100, amount_y + 5), 36, size=14, bold=True)
        self._draw_tester_button(surface, "amount_plus_1", pygame.Rect(area.x + 152, amount_y, 36, 28), "+1")
        self._draw_tester_button(surface, "amount_plus_5", pygame.Rect(area.x + 194, amount_y, 36, 28), "+5")
        self._draw_tester_button(surface, "damage", pygame.Rect(area.x, y + 58, 108, 30), "造成伤害", enabled=selected_character is not None)
        self._draw_tester_button(surface, "heal", pygame.Rect(area.x + 118, y + 58, 108, 30), "恢复生命", enabled=selected_character is not None)

    def _draw_tester_selector(
        self,
        surface: pygame.Surface,
        selector_id: str,
        rect: pygame.Rect,
        text: str,
        *,
        enabled: bool = True,
    ) -> None:
        action = f"{selector_id}_dropdown"
        self.tester_action_rects[action] = rect
        self.tester_selector_rects[selector_id] = rect
        is_open = self.tester_dropdown == selector_id
        fill_color = COLORS["surface_alt"] if enabled else COLORS["surface"]
        border_color = COLORS["accent"] if enabled or is_open else COLORS["border"]
        text_color = COLORS["text"] if enabled else COLORS["muted"]
        pygame.draw.rect(surface, fill_color, rect, border_radius=7)
        pygame.draw.rect(surface, border_color, rect, 2 if is_open else 1, border_radius=7)
        draw_text_fit(surface, text, (rect.x + 8, rect.y + 6), rect.width - 28, size=13, color=text_color, bold=True)
        draw_text(surface, "v", (rect.right - 18, rect.y + 5), size=13, color=text_color, bold=True)

    def _draw_tester_dropdown(self, surface: pygame.Surface) -> None:
        if self.tester_dropdown is None:
            return
        anchor = self.tester_selector_rects.get(self.tester_dropdown)
        if anchor is None:
            return

        entries = self._tester_dropdown_entries(self.tester_dropdown)
        if not entries:
            return

        window_rect = self._tester_window_rect()
        row_height = 28
        dropdown_height = min(196, len(entries) * row_height)
        dropdown_y = anchor.bottom + 4
        if dropdown_y + dropdown_height > window_rect.bottom - 16:
            dropdown_y = anchor.y - dropdown_height - 4
        dropdown_y = max(window_rect.y + 16, dropdown_y)
        rect = pygame.Rect(anchor.x, dropdown_y, max(anchor.width, 188), dropdown_height)
        self.tester_dropdown_rect = rect
        self._clamp_tester_dropdown_scroll_offset()

        pygame.draw.rect(surface, COLORS["shadow"], rect.move(5, 5), border_radius=7)
        pygame.draw.rect(surface, COLORS["surface"], rect, border_radius=7)
        pygame.draw.rect(surface, COLORS["accent"], rect, 2, border_radius=7)

        previous_clip = surface.get_clip()
        surface.set_clip(rect)
        y = rect.y - self.tester_dropdown_scroll_offset
        selected_index = self._tester_dropdown_selected_index(self.tester_dropdown)
        for index, label in entries:
            item_rect = pygame.Rect(rect.x + 2, y, rect.width - 4, row_height)
            if item_rect.bottom >= rect.y and item_rect.y <= rect.bottom:
                if index == selected_index:
                    pygame.draw.rect(surface, COLORS["accent_dark"], item_rect, border_radius=5)
                elif item_rect.collidepoint(pygame.mouse.get_pos()):
                    pygame.draw.rect(surface, COLORS["surface_alt"], item_rect, border_radius=5)
                draw_text_fit(surface, label, (item_rect.x + 8, item_rect.y + 6), item_rect.width - 16, size=13)
                self.tester_dropdown_item_rects.append((item_rect, self.tester_dropdown, index))
            y += row_height
        surface.set_clip(previous_clip)

        content_height = len(entries) * row_height
        if content_height > rect.height:
            self._draw_scrollbar(surface, rect, content_height, self.tester_dropdown_scroll_offset)

    def _tester_dropdown_entries(self, dropdown_id: str) -> list[tuple[int, str]]:
        if dropdown_id == "replace":
            return [
                (index, f"{definition.name} / {JOB_NAME_BY_ID.get(definition.job_id, definition.job_id)}")
                for index, definition in enumerate(CHARACTER_DEFINITIONS)
            ]
        if dropdown_id == "debuff":
            return [(index, effect.name) for index, effect in enumerate(self._tester_debuff_effects())]
        if dropdown_id == "buff":
            return [(index, effect.name) for index, effect in enumerate(self._tester_buff_effects())]
        return []

    def _tester_dropdown_selected_index(self, dropdown_id: str) -> int:
        if dropdown_id == "replace":
            return self.tester_replace_index
        if dropdown_id == "debuff":
            return self.tester_debuff_index
        if dropdown_id == "buff":
            return self.tester_buff_index
        return 0

    def _select_tester_dropdown_item(self, dropdown_id: str, index: int) -> None:
        if dropdown_id == "replace":
            self.tester_replace_index = index
        elif dropdown_id == "debuff":
            self.tester_debuff_index = index
        elif dropdown_id == "buff":
            self.tester_buff_index = index
        self.tester_dropdown = None
        self.tester_dropdown_scroll_offset = 0

    def _toggle_tester_dropdown(self, dropdown_id: str) -> None:
        if self.tester_dropdown == dropdown_id:
            self.tester_dropdown = None
            self.tester_dropdown_scroll_offset = 0
            return
        self.tester_dropdown = dropdown_id
        self.tester_dropdown_scroll_offset = 0
        self._clamp_tester_dropdown_scroll_offset()

    def _clamp_tester_dropdown_scroll_offset(self) -> None:
        if self.tester_dropdown is None:
            self.tester_dropdown_scroll_offset = 0
            return
        entries = self._tester_dropdown_entries(self.tester_dropdown)
        row_height = 28
        visible_height = 196
        if self.tester_dropdown_rect is not None:
            visible_height = self.tester_dropdown_rect.height
        max_offset = max(0, len(entries) * row_height - visible_height)
        self.tester_dropdown_scroll_offset = max(0, min(self.tester_dropdown_scroll_offset, max_offset))

    def _draw_tester_button(
        self,
        surface: pygame.Surface,
        action: str,
        rect: pygame.Rect,
        text: str,
        *,
        enabled: bool = True,
    ) -> None:
        self.tester_action_rects[action] = rect
        fill_color = COLORS["surface_alt"] if enabled else COLORS["surface"]
        border_color = COLORS["accent"] if enabled else COLORS["border"]
        text_color = COLORS["text"] if enabled else COLORS["muted"]
        pygame.draw.rect(surface, fill_color, rect, border_radius=7)
        pygame.draw.rect(surface, border_color, rect, 1, border_radius=7)
        draw_text_fit(surface, text, (rect.x + 8, rect.y + 7), rect.width - 16, size=13, color=text_color, bold=True)

    def _tester_selected_character(self) -> tuple[int, Character] | None:
        if self.tester_selected_slot is None:
            return None
        player_id, position = self.tester_selected_slot
        character = self.game_state.player(player_id).character_at(position)
        if character is None:
            return None
        return player_id, character

    def _tester_debuff_effects(self):
        return [effect for effect in EFFECTS if effect.category == EffectCategory.DEBUFF]

    def _tester_buff_effects(self):
        return [effect for effect in EFFECTS if effect.category == EffectCategory.BUFF]

    def _tester_window_rect(self) -> pygame.Rect:
        return pygame.Rect(78, 86, WINDOW_WIDTH - 156, WINDOW_HEIGHT - 138)
