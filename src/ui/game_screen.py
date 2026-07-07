import pygame

from src import user_settings
from src.assets import get_font
from src.config import COLORS, WINDOW_HEIGHT, WINDOW_WIDTH
from src.core import (
    BattleError,
    BattleSession,
    Character,
    DraftSession,
    FormationColumn,
    FormationError,
    FormationSession,
    GamePhase,
    Position,
)
from src.core.game_state import create_initial_game_state
from src.core.rules import active_skill_display_text, effect_display_name
from src.data.keywords import EFFECTS_BY_ID
from src.data.jobs import JOBS
from src.data.characters import create_draft_character_pool
from src.ui.components import Button, draw_text, draw_text_fit, draw_wrapped_text, wrap_text
from src.ui.game_screen_animations import AttackAnimation, GameScreenAnimationMixin
from src.ui.game_screen_tester import GameScreenTesterMixin
from src.ui.screen_manager import ScreenManager


JOB_ORDER = {job.id: index for index, job in enumerate(JOBS)}


class GameScreen(GameScreenAnimationMixin, GameScreenTesterMixin):
    def __init__(self, screen_manager: ScreenManager) -> None:
        self.screen_manager = screen_manager
        self.game_state = create_initial_game_state()
        self.character_pool = self._create_draft_pool()
        self.draft_session = DraftSession.with_random_first_player(self.game_state, self.character_pool)
        self.formation_session: FormationSession | None = None
        self.battle_session: BattleSession | None = None
        self.selected_formation_character_id: str | None = None
        self.selected_battle_actor_id: str | None = None
        self.selected_battle_character: tuple[int, str] | None = None
        self.battle_action_mode: str | None = None
        self.selected_active_skill_id: str | None = None
        self.selected_skill_target_ids: list[str] = []
        self.draft_job_filter_id: str | None = None
        self.draft_scroll_offset = 0
        self.battle_detail_scroll_offset = 0
        self.battle_log_scroll_offset = 0
        self.battle_log_overlay_open = False
        self.battle_log_overlay_scroll_offset = 0
        self.battle_action_scroll_offset = 0
        self.skill_option_scroll_offset = 0
        self.battle_log: list[str] = []
        self.active_attack_animation: AttackAnimation | None = None
        self.attack_animation_queue: list[AttackAnimation] = []
        self.tester_open = False
        self.tester_selected_slot: tuple[int, Position] | None = None
        self.tester_replace_index = 0
        self.tester_debuff_index = 0
        self.tester_buff_index = 0
        self.tester_amount = 1
        self.tester_dropdown: str | None = None
        self.tester_dropdown_scroll_offset = 0
        self.tester_slot_rects: list[tuple[pygame.Rect, int, Position]] = []
        self.tester_action_rects: dict[str, pygame.Rect] = {}
        self.tester_selector_rects: dict[str, pygame.Rect] = {}
        self.tester_dropdown_item_rects: list[tuple[pygame.Rect, str, int]] = []
        self.tester_dropdown_rect: pygame.Rect | None = None
        self.message = self._build_initial_message()

        self.back_button = Button(
            pygame.Rect(40, WINDOW_HEIGHT - 88, 180, 52),
            "返回主页",
            lambda: self.screen_manager.switch_to("home"),
            font_size=24,
        )
        self.restart_button = Button(
            pygame.Rect(WINDOW_WIDTH - 220, WINDOW_HEIGHT - 88, 180, 52),
            "重开游戏",
            self.restart_game,
            font_size=24,
        )
        self.tester_button = Button(
            pygame.Rect(WINDOW_WIDTH - 132, 24, 92, 32),
            "修改器",
            self.open_tester,
            font_size=15,
        )
        self.encyclopedia_button = Button(
            pygame.Rect(WINDOW_WIDTH - 232, 24, 92, 32),
            "百科大全",
            self.open_encyclopedia_from_battle,
            font_size=15,
        )
        self.confirm_formation_button = Button(
            pygame.Rect(888, 552, 168, 48),
            "确认阵型",
            self.confirm_current_formation,
            font_size=23,
            enabled=False,
        )
        self.undo_draft_button = Button(
            pygame.Rect(910, 574, 126, 32),
            "撤回上次",
            self.undo_draft_pick,
            font_size=16,
            enabled=False,
        )
        self.character_buttons: list[Button] = []
        self.draft_job_filter_buttons: list[Button] = []
        self.formation_character_buttons: list[Button] = []
        self.formation_slot_buttons: list[Button] = []
        self.attack_button = Button(
            pygame.Rect(884, 432, 82, 36),
            "攻击",
            self.begin_attack_mode,
            font_size=18,
            enabled=False,
        )
        self.skill_button = Button(
            pygame.Rect(974, 432, 82, 36),
            "技能",
            self.begin_skill_menu,
            font_size=18,
            enabled=False,
        )
        self.thaw_button = Button(
            pygame.Rect(884, 476, 82, 36),
            "解冻",
            self.thaw_selected_move,
            font_size=18,
            enabled=False,
        )
        self.revive_button = Button(
            pygame.Rect(884, 476, 172, 36),
            "复活",
            self.revive_selected_move,
            font_size=18,
            enabled=False,
        )
        self.skip_button = Button(
            pygame.Rect(974, 476, 82, 36),
            "跳过",
            self.skip_selected_move,
            font_size=18,
            enabled=False,
        )
        self.end_round_button = Button(
            pygame.Rect(884, 520, 172, 36),
            "结束本轮",
            self.end_current_player_round,
            font_size=16,
            enabled=False,
        )
        self.second_hand_button = Button(
            pygame.Rect(884, 564, 172, 36),
            "后手技能",
            self.use_second_hand_skill,
            font_size=18,
            enabled=False,
        )
        self.choose_first_button = Button(
            pygame.Rect(884, 432, 172, 36),
            "选择先手",
            lambda: self.choose_start_order(True),
            font_size=18,
            enabled=False,
        )
        self.choose_second_button = Button(
            pygame.Rect(884, 476, 172, 36),
            "选择后手",
            lambda: self.choose_start_order(False),
            font_size=18,
            enabled=False,
        )
        self.skill_option_buttons: list[Button] = []
        self.cancel_skill_button = Button(
            pygame.Rect(884, 564, 172, 36),
            "取消",
            self.cancel_skill_selection,
            font_size=18,
            enabled=False,
        )
        self.sword_saint_inspire_button = Button(
            pygame.Rect(884, 432, 172, 36),
            "战士+1/+1",
            lambda: self.resolve_sword_saint_choice("inspire"),
            font_size=16,
            enabled=False,
        )
        self.sword_saint_heal_button = Button(
            pygame.Rect(884, 476, 172, 36),
            "战士恢复3",
            lambda: self.resolve_sword_saint_choice("heal"),
            font_size=16,
            enabled=False,
        )
        self._build_character_buttons()
        self._build_draft_job_filter_buttons()

    def _create_draft_pool(self) -> list[Character]:
        return create_draft_character_pool(include_arcanarch=user_settings.show_arcanarch_in_draft)

    def restart_game(self) -> None:
        self.game_state = create_initial_game_state()
        self.character_pool = self._create_draft_pool()
        self.draft_session = DraftSession.with_random_first_player(self.game_state, self.character_pool)
        self.formation_session = None
        self.battle_session = None
        self.selected_formation_character_id = None
        self.selected_battle_actor_id = None
        self.selected_battle_character = None
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.selected_skill_target_ids = []
        self.draft_job_filter_id = None
        self.draft_scroll_offset = 0
        self.battle_detail_scroll_offset = 0
        self.battle_log_scroll_offset = 0
        self.battle_log_overlay_open = False
        self.battle_log_overlay_scroll_offset = 0
        self.battle_action_scroll_offset = 0
        self.skill_option_scroll_offset = 0
        self.battle_log = []
        self.active_attack_animation = None
        self.attack_animation_queue = []
        self.tester_open = False
        self.tester_selected_slot = None
        self.tester_replace_index = 0
        self.tester_debuff_index = 0
        self.tester_buff_index = 0
        self.tester_amount = 1
        self.tester_dropdown = None
        self.tester_dropdown_scroll_offset = 0
        self.message = self._build_initial_message()
        self._build_character_buttons()
        self._build_draft_job_filter_buttons()
        self.formation_character_buttons = []
        self._build_formation_slot_buttons()

    def open_encyclopedia_from_battle(self) -> None:
        encyclopedia = self.screen_manager.get_screen("encyclopedia")
        if hasattr(encyclopedia, "set_return_screen"):
            encyclopedia.set_return_screen("game", "返回战斗")
        self.screen_manager.switch_to("encyclopedia")

    def open_tester(self) -> None:
        self.tester_open = True
        self.tester_dropdown = None
        if self.tester_selected_slot is None:
            self.tester_selected_slot = (1, Position(row=0, column=FormationColumn.FRONT))

    def quick_enter_battle(self) -> None:
        self.game_state = create_initial_game_state()
        self.character_pool = self._create_draft_pool()
        self.draft_session = DraftSession.with_random_first_player(self.game_state, self.character_pool)
        self.formation_session = None
        self.selected_formation_character_id = None
        self.selected_battle_actor_id = None
        self.selected_battle_character = None
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.selected_skill_target_ids = []

        characters_by_id = {character.id: character for character in self.character_pool}
        loadouts = {
            1: (
                ("villager", Position(row=0, column=FormationColumn.FRONT)),
                ("priest", Position(row=1, column=FormationColumn.BACK)),
                ("shield_mage", Position(row=2, column=FormationColumn.BACK)),
            ),
            2: (
                ("werewolf", Position(row=0, column=FormationColumn.FRONT)),
                ("advanced_villager", Position(row=1, column=FormationColumn.FRONT)),
                ("dual_blade_knight", Position(row=2, column=FormationColumn.FRONT)),
            ),
        }
        for player_id, entries in loadouts.items():
            player = self.game_state.player(player_id)
            for character_id, position in entries:
                character = characters_by_id[character_id]
                player.add_character(character)
                player.place_character(character.id, position)

        self.game_state.phase = GamePhase.BATTLE
        self.game_state.current_turn_player_id = None
        self._start_battle()
        self.tester_open = True
        self.tester_dropdown = None
        self.tester_selected_slot = (1, Position(row=0, column=FormationColumn.FRONT))
        self._log_battle("修改器：已快速进入测试战斗。")

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._battle_animation_active():
            return

        if self.tester_open:
            self._handle_tester_event(event)
            return

        self.tester_button.handle_event(event)
        if self.game_state.phase == GamePhase.BATTLE:
            self.encyclopedia_button.handle_event(event)
        self.back_button.handle_event(event)
        self.restart_button.handle_event(event)

        if self.game_state.phase == GamePhase.DRAFT:
            self._sync_character_button_states()
            if event.type == pygame.MOUSEWHEEL:
                self.draft_scroll_offset -= event.y * 42
                self._clamp_draft_scroll_offset()
                self._build_character_buttons()
                self._sync_character_button_states()
                return
            for button in self.draft_job_filter_buttons:
                button.handle_event(event)
            self.undo_draft_button.handle_event(event)
            character_area = self._draft_character_area()
            for button in self.character_buttons:
                if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION) and hasattr(event, "pos"):
                    if not character_area.collidepoint(event.pos):
                        button.hovered = False
                        continue
                    if not button.rect.colliderect(character_area):
                        button.hovered = False
                        continue
                button.handle_event(event)
        elif self.game_state.phase == GamePhase.FORMATION:
            self._ensure_formation_session()
            self._sync_formation_button_states()
            self.confirm_formation_button.handle_event(event)
            for button in self.formation_character_buttons:
                button.handle_event(event)
            for button in self.formation_slot_buttons:
                button.handle_event(event)
        elif self.game_state.phase == GamePhase.BATTLE:
            self._ensure_battle_session()
            if event.type == pygame.MOUSEWHEEL:
                if self.battle_log_overlay_open:
                    self.battle_log_overlay_scroll_offset -= event.y * 40
                    return
                mouse_pos = pygame.mouse.get_pos()
                if self.battle_action_mode == "skill_menu" and self._skill_option_area_rect().collidepoint(mouse_pos):
                    self.skill_option_scroll_offset -= event.y * 44
                    self._clamp_skill_option_scroll_offset()
                    self._rebuild_current_skill_option_buttons()
                elif self._battle_action_area_rect().collidepoint(mouse_pos):
                    self.battle_action_scroll_offset -= event.y * 44
                    self._clamp_battle_action_scroll_offset()
                elif self._battle_log_panel_rect().collidepoint(mouse_pos):
                    self.battle_log_scroll_offset -= event.y * 34
                elif self.selected_battle_character is not None:
                    self.battle_detail_scroll_offset -= event.y * 34
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.battle_log_overlay_open:
                    if not self._battle_log_overlay_rect().collidepoint(event.pos):
                        self.battle_log_overlay_open = False
                    return
                if self._battle_log_panel_rect().collidepoint(event.pos):
                    self._handle_battle_log_click(event.pos)
                    return
            self._sync_battle_button_states()
            if self.battle_session is not None and self.battle_session.pending_start_order_choice_player_id is not None:
                self.choose_first_button.handle_event(event)
                self.choose_second_button.handle_event(event)
                return
            if self.battle_session is not None and self.battle_session.current_sword_saint_choice() is not None:
                self.sword_saint_inspire_button.handle_event(event)
                self.sword_saint_heal_button.handle_event(event)
            elif self.battle_action_mode in ("skill_menu", "skill_target"):
                skill_area = self._skill_option_area_rect()
                for button in self.skill_option_buttons:
                    if self.battle_action_mode == "skill_menu" and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION) and hasattr(event, "pos"):
                        if not skill_area.collidepoint(event.pos) or not button.rect.colliderect(skill_area):
                            button.hovered = False
                            continue
                    button.handle_event(event)
                self.cancel_skill_button.handle_event(event)
            else:
                action_area = self._battle_action_area_rect()
                buttons = self._layout_battle_action_buttons(self._visible_battle_action_buttons())
                for button in buttons:
                    if not button.rect.colliderect(action_area):
                        button.hovered = False
                        continue
                    if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION) and hasattr(event, "pos") and not action_area.collidepoint(event.pos):
                        button.hovered = False
                        continue
                    button.handle_event(event)
            self._handle_battle_board_event(event)

    def update(self, delta_seconds: float) -> None:
        self._update_battle_animations(delta_seconds)
        if self.game_state.phase == GamePhase.DRAFT:
            self._sync_character_button_states()
        elif self.game_state.phase == GamePhase.FORMATION:
            self._ensure_formation_session()
            self._sync_formation_button_states()
        elif self.game_state.phase == GamePhase.BATTLE:
            self._ensure_battle_session()
            self._sync_battle_button_states()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(COLORS["background"])

        if self.game_state.phase == GamePhase.DRAFT:
            self._draw_draft(surface)
        elif self.game_state.phase == GamePhase.FORMATION:
            self._draw_formation(surface)
        elif self.game_state.phase == GamePhase.BATTLE:
            self._draw_battle(surface)
        elif self.game_state.phase == GamePhase.FINISHED:
            self._draw_finished(surface)

        self.back_button.draw(surface)
        self.restart_button.draw(surface)
        if self.game_state.phase == GamePhase.BATTLE:
            self.encyclopedia_button.draw(surface)
        self.tester_button.draw(surface)
        self._draw_tester_window(surface)

    def select_character(self, character_id: str) -> None:
        if self.game_state.phase != GamePhase.DRAFT:
            return

        player_id = self.draft_session.current_player_id
        if player_id is None:
            return

        character = self.draft_session.select_character(character_id)
        self.message = f"{self.game_state.player(player_id).name} 选择了 {character.name}"

        if self.game_state.phase == GamePhase.FORMATION:
            self._start_formation()

        self._sync_character_button_states()

    def undo_draft_pick(self) -> None:
        if not self.draft_session.pick_history:
            self.message = "暂无可撤回的选角。"
            return

        try:
            character = self.draft_session.retract_last_pick()
        except ValueError as error:
            self.message = str(error)
            return

        current_player_id = self.draft_session.current_player_id
        current_player_name = self.game_state.player(current_player_id).name if current_player_id is not None else "当前玩家"
        self.formation_session = None
        self.selected_formation_character_id = None
        self.formation_character_buttons = []
        self.message = f"已撤回 {character.name}，继续由 {current_player_name} 选角。"
        self._build_character_buttons()
        self._sync_character_button_states()

    def select_formation_character(self, character_id: str) -> None:
        session = self._ensure_formation_session()
        player = session.current_player
        character = player.get_character(character_id)

        self.selected_formation_character_id = character_id
        if character.position is None:
            self.message = f"已选择 {character.name}，请选择一个阵位。"
        else:
            self.message = f"已选择 {character.name}，可点击空位移动，点击原位置撤下。"
        self._sync_formation_button_states()

    def place_selected_character(self, position: Position) -> None:
        session = self._ensure_formation_session()
        player = session.current_player

        if self.selected_formation_character_id is None:
            occupant = player.character_at(position)
            if occupant is None:
                self.message = "请先选择一个角色。"
            else:
                self.select_formation_character(occupant.id)
            return

        character = player.get_character(self.selected_formation_character_id)
        if character.position == position:
            session.clear_character(player.id, character.id)
            self.message = f"{character.name} 已撤下。"
            self._sync_formation_button_states()
            return

        try:
            session.place_character(player.id, character.id, position)
        except FormationError as error:
            self.message = str(error)
            return

        self.message = f"{character.name} 已放置到 {self._position_label(position)}。"
        self._sync_formation_button_states()

    def confirm_current_formation(self) -> None:
        session = self._ensure_formation_session()
        player_id = session.current_player_id
        player = self.game_state.player(player_id)

        try:
            session.confirm_player_formation(player_id)
        except FormationError as error:
            self.message = str(error)
            return

        self.selected_formation_character_id = None
        if self.game_state.phase == GamePhase.BATTLE:
            self.message = "双方排阵完成，进入对战阶段。"
            self._start_battle()
        else:
            next_player = session.current_player
            self.message = f"{player.name} 已确认阵型。现在由 {next_player.name} 排阵。"
            self._build_formation_character_buttons()

        self._sync_formation_button_states()

    def _start_formation(self) -> None:
        self.formation_session = FormationSession(self.game_state)
        self.selected_formation_character_id = None
        self.message = "选角完成，进入排阵阶段。请选择玩家1的角色。"
        self._build_formation_character_buttons()
        self._build_formation_slot_buttons()
        self._sync_formation_button_states()

    def _ensure_formation_session(self) -> FormationSession:
        if self.formation_session is None:
            self._start_formation()
        if self.formation_session is None:
            raise RuntimeError("Formation session was not created.")
        return self.formation_session

    def _start_battle(self) -> None:
        self.battle_session = BattleSession.with_random_first_player(self.game_state)
        self.selected_battle_actor_id = None
        self.selected_battle_character = None
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.selected_skill_target_ids = []
        self.battle_log_scroll_offset = 0
        self.battle_log_overlay_open = False
        self.battle_log_overlay_scroll_offset = 0
        self.battle_action_scroll_offset = 0
        self.skill_option_scroll_offset = 0
        self.battle_log = []
        self.active_attack_animation = None
        self.attack_animation_queue = []
        if self.battle_session.pending_start_order_choice_player_id is not None:
            choice_player = self.game_state.player(self.battle_session.pending_start_order_choice_player_id)
            self._log_battle(f"对战开始前，{choice_player.name} 需要选择自己先手或后手。")
            self._sync_battle_button_states()
            return
        current_player_id = self.battle_session.current_player_id
        if current_player_id is not None:
            current_player = self.game_state.player(current_player_id)
            first_player = self.game_state.player(self.battle_session.first_player_id)
            second_player = self.game_state.player(self.game_state.opponent_id(self.battle_session.first_player_id))
            self._log_battle(
                f"对战开始，{first_player.name} 先手，{second_player.name} 获得后手技能。当前由 {current_player.name} 行动。"
            )
        self._sync_battle_button_states()

    def _ensure_battle_session(self) -> BattleSession:
        if self.battle_session is None:
            self._start_battle()
        if self.battle_session is None:
            raise RuntimeError("Battle session was not created.")
        return self.battle_session

    def _build_character_buttons(self) -> None:
        self.character_buttons = []
        card_width = 224
        card_height = 30
        x_positions = (224, 466)
        start_y = 154
        gap_y = 31

        self._clamp_draft_scroll_offset()
        for index, character in enumerate(self._visible_draft_characters()):
            column = index % 2
            row = index // 2
            rect = pygame.Rect(
                x_positions[column],
                start_y + row * gap_y - self.draft_scroll_offset,
                card_width,
                card_height,
            )
            text = f"{character.name}  {character.job.name}  {character.max_health}/{character.attack}"
            button = Button(
                rect,
                text,
                lambda character_id=character.id: self.select_character(character_id),
                font_size=12,
            )
            button.character_id = character.id
            self.character_buttons.append(button)

    def _build_draft_job_filter_buttons(self) -> None:
        self.draft_job_filter_buttons = []
        entries: list[tuple[str | None, str]] = [(None, "全部")]
        draft_job_ids = {character.job.id for character in self.character_pool}
        entries.extend((job.id, job.name) for job in JOBS if job.id in draft_job_ids and job.id != "summon")

        for index, (job_id, label) in enumerate(entries):
            rect = pygame.Rect(64, 152 + index * 32, 124, 27)
            button = Button(
                rect,
                label,
                lambda selected_job_id=job_id: self.select_draft_job_filter(selected_job_id),
                font_size=15,
            )
            button.job_id = job_id
            self.draft_job_filter_buttons.append(button)

    def select_draft_job_filter(self, job_id: str | None) -> None:
        self.draft_job_filter_id = job_id
        self.draft_scroll_offset = 0
        self._build_character_buttons()
        self._sync_character_button_states()

    def _visible_draft_characters(self) -> list[Character]:
        characters = sorted(
            self.character_pool,
            key=lambda character: (JOB_ORDER.get(character.job.id, 999), character.name, character.id),
        )
        if self.draft_job_filter_id is None:
            return characters
        return [character for character in characters if character.job.id == self.draft_job_filter_id]

    def _draft_character_area(self) -> pygame.Rect:
        return pygame.Rect(224, 154, 466, 398)

    def _draft_content_height(self) -> int:
        visible_count = len(self._visible_draft_characters())
        if visible_count == 0:
            return 0
        rows = (visible_count + 1) // 2
        return rows * 30 + max(0, rows - 1) * 1

    def _clamp_draft_scroll_offset(self) -> None:
        max_offset = max(0, self._draft_content_height() - self._draft_character_area().height)
        self.draft_scroll_offset = max(0, min(self.draft_scroll_offset, max_offset))

    def _build_formation_character_buttons(self) -> None:
        session = self._ensure_formation_session()
        self.formation_character_buttons = []
        player = session.current_player

        for index, character in enumerate(player.selected_characters):
            rect = pygame.Rect(64, 154 + index * 48, 300, 40)
            text = f"{character.name} / {character.job.name}"
            button = Button(
                rect,
                text,
                lambda character_id=character.id: self.select_formation_character(character_id),
                font_size=18,
            )
            button.character_id = character.id
            self.formation_character_buttons.append(button)

    def _build_formation_slot_buttons(self) -> None:
        self.formation_slot_buttons = []
        start_x = 470
        start_y = 160
        cell_width = 140
        cell_height = 88
        gap_x = 30
        gap_y = 24
        columns = (FormationColumn.BACK, FormationColumn.FRONT)

        for row in range(3):
            for column_index, column in enumerate(columns):
                position = Position(row=row, column=column)
                rect = pygame.Rect(
                    start_x + column_index * (cell_width + gap_x),
                    start_y + row * (cell_height + gap_y),
                    cell_width,
                    cell_height,
                )
                button = Button(
                    rect,
                    "",
                    lambda slot_position=position: self.place_selected_character(slot_position),
                    font_size=18,
                )
                button.position = position
                self.formation_slot_buttons.append(button)

    def _sync_character_button_states(self) -> None:
        draft_active = self.game_state.phase == GamePhase.DRAFT and not self.draft_session.is_complete
        for button in self.character_buttons:
            character_id = getattr(button, "character_id")
            button.enabled = draft_active and not self.draft_session.is_character_selected(character_id)
        self.undo_draft_button.enabled = draft_active and bool(self.draft_session.pick_history)

    def _sync_formation_button_states(self) -> None:
        if self.game_state.phase != GamePhase.FORMATION:
            self.confirm_formation_button.enabled = False
            return

        session = self._ensure_formation_session()
        active = session.current_player_id not in session.confirmed_player_ids
        for button in self.formation_character_buttons:
            button.enabled = active
        for button in self.formation_slot_buttons:
            button.enabled = active
        self.confirm_formation_button.enabled = active and session.is_player_formation_complete(
            session.current_player_id
        )

    def _sync_battle_button_states(self) -> None:
        self.skill_button.text = "技能"
        if self.game_state.phase != GamePhase.BATTLE or self.battle_session is None:
            for button in (
                self.attack_button,
                self.skill_button,
                self.thaw_button,
                self.revive_button,
                self.skip_button,
                self.end_round_button,
                self.second_hand_button,
                self.choose_first_button,
                self.choose_second_button,
                self.cancel_skill_button,
                self.sword_saint_inspire_button,
                self.sword_saint_heal_button,
            ):
                button.enabled = False
            self.skill_option_buttons = []
            return

        if self.battle_session.pending_start_order_choice_player_id is not None:
            choice_player_id = self.battle_session.pending_start_order_choice_player_id
            self.attack_button.enabled = False
            self.skill_button.enabled = False
            self.thaw_button.enabled = False
            self.revive_button.enabled = False
            self.skip_button.enabled = False
            self.end_round_button.enabled = False
            self.second_hand_button.enabled = False
            self.choose_first_button.enabled = self.battle_session.can_choose_start_order(choice_player_id)
            self.choose_second_button.enabled = self.battle_session.can_choose_start_order(choice_player_id)
            self.cancel_skill_button.enabled = False
            self.sword_saint_inspire_button.enabled = False
            self.sword_saint_heal_button.enabled = False
            self.skill_option_buttons = []
            return

        self.choose_first_button.enabled = False
        self.choose_second_button.enabled = False

        if self.battle_session.current_death_trigger() is not None:
            self.attack_button.enabled = False
            self.skill_button.enabled = False
            self.thaw_button.enabled = False
            self.revive_button.enabled = False
            self.skip_button.enabled = self.battle_session.can_resolve_death_trigger(None)
            self.end_round_button.enabled = False
            self.second_hand_button.enabled = False
            self.choose_first_button.enabled = False
            self.choose_second_button.enabled = False
            self.cancel_skill_button.enabled = False
            self.sword_saint_inspire_button.enabled = False
            self.sword_saint_heal_button.enabled = False
            self.skill_option_buttons = []
            return

        if self.battle_session.current_sword_saint_choice() is not None:
            self.attack_button.enabled = False
            self.skill_button.enabled = False
            self.thaw_button.enabled = False
            self.revive_button.enabled = False
            self.skip_button.enabled = False
            self.end_round_button.enabled = False
            self.second_hand_button.enabled = False
            self.choose_first_button.enabled = False
            self.choose_second_button.enabled = False
            self.cancel_skill_button.enabled = False
            options = set(self.battle_session.sword_saint_choice_options())
            self.sword_saint_inspire_button.enabled = "inspire" in options
            self.sword_saint_heal_button.enabled = "heal" in options
            self.skill_option_buttons = []
            return

        if self.battle_session.current_chase_choice() is not None:
            self.attack_button.enabled = False
            self.skill_button.enabled = False
            self.thaw_button.enabled = False
            self.revive_button.enabled = False
            self.skip_button.enabled = False
            self.end_round_button.enabled = False
            self.second_hand_button.enabled = False
            self.choose_first_button.enabled = False
            self.choose_second_button.enabled = False
            self.cancel_skill_button.enabled = False
            self.sword_saint_inspire_button.enabled = False
            self.sword_saint_heal_button.enabled = False
            self.skill_option_buttons = []
            return

        pending_followup = self.battle_session.current_followup_attack()
        current_player_id = self.battle_session.current_player_id
        selected_can_relocate = (
            current_player_id is not None
            and self.selected_battle_actor_id is not None
            and pending_followup is None
            and self.battle_session.can_relocate_character(current_player_id, self.selected_battle_actor_id)
        )
        selected_is_legal_actor = (
            current_player_id is not None
            and self.selected_battle_actor_id is not None
            and self.battle_session.can_character_move(current_player_id, self.selected_battle_actor_id)
        )
        selected_can_revive = (
            current_player_id is not None
            and self.selected_battle_actor_id is not None
            and self.battle_session.can_revive_character(current_player_id, self.selected_battle_actor_id)
        )
        selected_actor = None
        selected_is_frozen = False
        if selected_is_legal_actor and current_player_id is not None and self.selected_battle_actor_id is not None:
            selected_actor = self.game_state.player(current_player_id).get_character(self.selected_battle_actor_id)
            selected_is_frozen = selected_actor.has_status_effect("frozen")
        has_targets = False
        if selected_is_legal_actor and current_player_id is not None and not selected_is_frozen:
            has_targets = bool(
                self.battle_session.attackable_targets(current_player_id, self.selected_battle_actor_id)
            )

        has_active_skills = (
            selected_is_legal_actor
            and current_player_id is not None
            and self.selected_battle_actor_id is not None
            and any(
                self.battle_session.can_cast_skill(current_player_id, self.selected_battle_actor_id, skill.id)
                for skill in self.battle_session.active_skills(current_player_id, self.selected_battle_actor_id)
            )
        )
        self.attack_button.enabled = selected_is_legal_actor and has_targets and not selected_can_revive
        if selected_can_relocate:
            self.skill_button.text = "取消" if self.battle_action_mode == "relocate" else "位移"
            self.skill_button.enabled = True
        else:
            self.skill_button.text = "技能"
            self.skill_button.enabled = has_active_skills and not selected_is_frozen and pending_followup is None
        self.thaw_button.enabled = (
            selected_is_legal_actor
            and selected_is_frozen
            and current_player_id is not None
            and self.selected_battle_actor_id is not None
            and pending_followup is None
            and self.battle_session.can_thaw_character(current_player_id, self.selected_battle_actor_id)
        )
        self.revive_button.enabled = selected_can_revive
        self.skip_button.enabled = (
            selected_is_legal_actor
            and current_player_id is not None
            and self.selected_battle_actor_id is not None
            and self.battle_session.can_skip_move(current_player_id, self.selected_battle_actor_id)
        )
        self.end_round_button.enabled = (
            current_player_id is not None
            and pending_followup is None
            and self.battle_session.can_end_player_round(current_player_id)
        )
        self.second_hand_button.enabled = (
            current_player_id is not None
            and pending_followup is None
            and self.battle_session.can_use_second_hand_skill(current_player_id)
        )
        self.cancel_skill_button.enabled = self.battle_action_mode in ("skill_menu", "skill_target")
        self.sword_saint_inspire_button.enabled = False
        self.sword_saint_heal_button.enabled = False
        self._clamp_battle_action_scroll_offset()

    def select_battle_actor(self, character_id: str) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None:
            return

        self.select_battle_character(current_player_id, character_id)

    def select_battle_character(self, player_id: int, character_id: str) -> None:
        session = self._ensure_battle_session()
        character = self.game_state.player(player_id).get_character(character_id)
        self.selected_battle_character = (player_id, character_id)
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.selected_skill_target_ids = []
        self.battle_detail_scroll_offset = 0
        self.selected_battle_actor_id = character_id
        can_relocate = session.can_relocate_character(player_id, character_id)

        if session.current_player_id != player_id:
            self.selected_battle_actor_id = None
            self.message = f"查看 {character.name}。"
        elif not session.can_character_move(player_id, character_id) and not can_relocate:
            self.selected_battle_actor_id = None
            blockers = session.blocked_actor_names_before_choice(player_id, character_id)
            if blockers:
                self.message = f"{character.name} 暂不可行动，需先处理 {'、'.join(blockers)}。"
            elif not character.is_alive:
                self.message = f"{character.name} 已死亡。"
            else:
                self.message = f"{character.name} 本轮行动已消耗。"
        elif can_relocate and not session.can_character_move(player_id, character_id):
            self.message = f"已选择 {character.name}，仍可执行位移。"
        elif session.is_never_moved(player_id, character_id):
            self.message = f"已选择 {character.name}，该角色未进入历史顺序，可行动。"
        else:
            self.message = f"已选择 {character.name}，满足当前行动顺序。"

        self._sync_battle_button_states()

    def begin_attack_mode(self) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None or self.selected_battle_actor_id is None:
            self.message = "请先选择可行动角色。"
            return

        character = self.game_state.player(current_player_id).get_character(self.selected_battle_actor_id)
        self.battle_action_mode = "attack"
        self.message = f"{character.name} 准备攻击，请点击一个合法敌方目标。"
        self._sync_battle_button_states()

    def begin_skill_menu(self) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None or self.selected_battle_actor_id is None:
            self.message = "请先选择可行动角色。"
            return

        character = self.game_state.player(current_player_id).get_character(self.selected_battle_actor_id)
        if self.battle_action_mode == "relocate":
            self.battle_action_mode = None
            self.selected_skill_target_ids = []
            self.message = "已取消位移。"
            self._sync_battle_button_states()
            return

        if session.can_relocate_character(current_player_id, character.id):
            self.battle_action_mode = "relocate"
            self.selected_active_skill_id = None
            self.selected_skill_target_ids = []
            self.skill_option_buttons = []
            self.message = f"{character.name} 准备位移，请点击己方空位。"
            self._sync_battle_button_states()
            return

        if character.has_status_effect("frozen"):
            self.message = f"{character.name} 当前冻结，只能解冻或跳过。"
            return

        skills = session.active_skills(current_player_id, character.id)
        if not skills:
            self.message = f"{character.name} 没有可用主动技能。"
            return

        self.battle_action_mode = "skill_menu"
        self.selected_active_skill_id = None
        self.selected_skill_target_ids = []
        self.skill_option_scroll_offset = 0
        self._build_skill_option_buttons(current_player_id, character.id)
        self.message = f"选择 {character.name} 要释放的主动技能。"
        self._sync_battle_button_states()

    def thaw_selected_move(self) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None or self.selected_battle_actor_id is None:
            self.message = "请先选择被冻结的可行动角色。"
            return

        try:
            result = session.thaw_character(current_player_id, self.selected_battle_actor_id)
        except BattleError as error:
            self.message = str(error)
            return

        next_text = ""
        if result.next_player_id is not None:
            next_text = f" 现在由 {self.game_state.player(result.next_player_id).name} 行动。"
        self._log_battle(f"{result.actor_name} 执行解冻。{next_text}")
        self.selected_battle_actor_id = None
        self.selected_battle_character = None
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self._sync_battle_button_states()

    def revive_selected_move(self) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None or self.selected_battle_actor_id is None:
            self.message = "请先选择待复活角色。"
            return

        try:
            result = session.revive_character(current_player_id, self.selected_battle_actor_id)
        except BattleError as error:
            self.message = str(error)
            return

        next_text = ""
        if result.next_player_id is not None:
            next_text = f" 现在由 {self.game_state.player(result.next_player_id).name} 行动。"
        for event in result.events:
            self._log_battle(event)
        self._log_battle(f"{result.actor_name} 复活并结束本次移动。{next_text}")
        self.selected_battle_actor_id = None
        self.selected_battle_character = None
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.skill_option_buttons = []
        self._sync_battle_button_states()

    def cancel_skill_selection(self) -> None:
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.selected_skill_target_ids = []
        self.skill_option_buttons = []
        self.skill_option_scroll_offset = 0
        self.message = "已取消技能选择。"
        self._sync_battle_button_states()

    def select_active_skill(self, skill_id: str) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None or self.selected_battle_actor_id is None:
            self.message = "请先选择可行动角色。"
            return

        if not session.can_cast_skill(current_player_id, self.selected_battle_actor_id, skill_id):
            self.message = "该技能当前没有合法目标。"
            return

        skill = next(
            skill
            for skill in session.active_skills(current_player_id, self.selected_battle_actor_id)
            if skill.id == skill_id
        )
        self.battle_action_mode = "skill_target"
        self.selected_active_skill_id = skill_id
        self.selected_skill_target_ids = []
        self.skill_option_buttons = []
        self.skill_option_scroll_offset = 0
        if not session.skill_targets(current_player_id, self.selected_battle_actor_id, skill.id):
            self.cast_selected_skill_without_target()
            return
        if skill.max_targets > 1:
            self.message = f"{skill.name}：依次点击 {skill.min_targets}-{skill.max_targets} 个目标。"
        else:
            self.message = f"{skill.name}：点击一个红框目标。"
        self._sync_battle_button_states()

    def cast_selected_skill_without_target(self) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if (
            current_player_id is None
            or self.selected_battle_actor_id is None
            or self.selected_active_skill_id is None
        ):
            self.message = "请先选择主动技能。"
            return

        skill = next(
            skill
            for skill in session.active_skills(current_player_id, self.selected_battle_actor_id)
            if skill.id == self.selected_active_skill_id
        )
        before_health = self._battle_health_snapshot()
        try:
            result = session.cast_skill(
                current_player_id,
                self.selected_battle_actor_id,
                self.selected_active_skill_id,
                None,
            )
        except BattleError as error:
            self.message = str(error)
            return
        self._queue_health_change_animation(
            (current_player_id, self.selected_battle_actor_id),
            before_health,
            show_slash=self._skill_should_animate_attack(skill),
            critical_damage_keys=self._critical_damage_keys(result),
        )

        self._finish_skill_result(session, result, skill, current_player_id)

    def cast_selected_skill_on_target(self, target_id: str) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if (
            current_player_id is None
            or self.selected_battle_actor_id is None
            or self.selected_active_skill_id is None
        ):
            self.message = "请先选择主动技能。"
            return

        skill = next(
            skill
            for skill in session.active_skills(current_player_id, self.selected_battle_actor_id)
            if skill.id == self.selected_active_skill_id
        )
        target_ids: str | list[str] = target_id
        if skill.max_targets > 1:
            allows_repeat_targets = skill.id.split("__copy_", 1)[0] == "brutal_bomber_distribute"
            if target_id in self.selected_skill_target_ids and not allows_repeat_targets:
                self.message = "该目标已经选择过。"
                return
            candidate_ids = [*self.selected_skill_target_ids, target_id]
            legal_target_ids = {target.id for target in session.skill_targets(current_player_id, self.selected_battle_actor_id, skill.id)}
            if target_id not in legal_target_ids:
                self.message = "该目标不是当前技能的合法目标。"
                return

            self.selected_skill_target_ids = candidate_ids
            available_count = len(legal_target_ids)
            required_count = skill.max_targets if allows_repeat_targets else min(skill.max_targets, available_count)
            if len(candidate_ids) < required_count:
                self.message = f"已选择 {len(candidate_ids)}/{required_count} 个目标。"
                self._sync_battle_button_states()
                return
            target_ids = candidate_ids

        before_health = self._battle_health_snapshot()
        try:
            result = session.cast_skill(
                current_player_id,
                self.selected_battle_actor_id,
                self.selected_active_skill_id,
                target_ids,
            )
        except BattleError as error:
            self.message = str(error)
            return
        self._queue_health_change_animation(
            (current_player_id, self.selected_battle_actor_id),
            before_health,
            show_slash=self._skill_should_animate_attack(skill),
            critical_damage_keys=self._critical_damage_keys(result),
        )

        self._finish_skill_result(session, result, skill, current_player_id)

    def _finish_skill_result(self, session: BattleSession, result, skill, current_player_id: int) -> None:
        message = f"{result.caster_name} 使用 {result.skill_name} 指向 {result.target_name}。"
        if result.damage:
            if result.actual_target_name and result.actual_target_name != result.target_name:
                message += f" {result.actual_target_name} 承受 {result.damage} 点伤害。"
            else:
                message += f" 造成 {result.damage} 点伤害。"
        for event in result.events:
            message += f" {event}"
        if result.defeated_character_names:
            message += f" {'、'.join(result.defeated_character_names)} 死亡。"
        message = self._append_pending_or_next_text(message, session, result.winner_player_id)

        self._log_battle(message)
        if not self._sync_pending_followup_selection(session):
            self.selected_battle_actor_id = None
            self.selected_battle_character = None
            self.battle_action_mode = None
            self.selected_active_skill_id = None
            self.selected_skill_target_ids = []
            self.skill_option_buttons = []
        self._sync_battle_button_states()

    def use_second_hand_skill(self) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None:
            return

        try:
            result = session.use_second_hand_skill(current_player_id)
        except BattleError as error:
            self.message = str(error)
            return

        next_text = ""
        if result.next_player_id is not None:
            next_text = f" 下一个回合仍由 {self.game_state.player(result.next_player_id).name} 行动。"
        self._log_battle(f"{result.player_name} 使用后手技能。{next_text}")
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.skill_option_buttons = []
        self._sync_battle_button_states()

    def choose_start_order(self, choose_first: bool) -> None:
        session = self._ensure_battle_session()
        choice_player_id = session.pending_start_order_choice_player_id
        if choice_player_id is None:
            return

        try:
            result = session.choose_start_order(choice_player_id, choose_first=choose_first)
        except BattleError as error:
            self.message = str(error)
            return

        choice_text = "先手" if choose_first else "后手"
        message = (
            f"{result.player_name} 选择自己{choice_text}。"
            f"{result.first_player_name} 先手，{result.second_player_name} 获得后手技能。"
        )
        message = self._append_pending_or_next_text(message, session, None)
        self._log_battle(message)
        self.selected_battle_actor_id = None
        self.selected_battle_character = None
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.selected_skill_target_ids = []
        self.skill_option_buttons = []
        self._sync_battle_button_states()

    def skip_selected_move(self) -> None:
        session = self._ensure_battle_session()
        if session.current_death_trigger() is not None:
            if session.can_resolve_death_trigger(None):
                self.resolve_death_trigger_target(None)
            else:
                action_text = self._death_trigger_action_text(session.current_death_trigger())
                self.message = f"{action_text}需要选择一个目标。"
            return

        current_player_id = session.current_player_id
        if current_player_id is None or self.selected_battle_actor_id is None:
            self.message = "请先选择可行动角色。"
            return

        skipped_followup = session.current_followup_attack() == (current_player_id, self.selected_battle_actor_id)
        try:
            result = session.skip_move(current_player_id, self.selected_battle_actor_id)
        except BattleError as error:
            self.message = str(error)
            return

        next_text = ""
        if result.next_player_id is not None:
            next_text = f" 现在由 {self.game_state.player(result.next_player_id).name} 行动。"
        for event in result.events:
            self._log_battle(event)
        if skipped_followup:
            self._log_battle(f"{result.actor_name} 放弃剩余攻击。{next_text}")
        else:
            self._log_battle(f"{result.actor_name} 跳过本轮行动。{next_text}")
        self.selected_battle_actor_id = None
        self.selected_battle_character = None
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.skill_option_buttons = []
        self._sync_battle_button_states()

    def resolve_death_trigger_target(self, target_id: str | None) -> None:
        session = self._ensure_battle_session()
        trigger = session.current_death_trigger()
        action_text = self._death_trigger_action_text(trigger)
        before_health = self._battle_health_snapshot()
        try:
            result = session.resolve_death_trigger(target_id)
        except BattleError as error:
            self.message = str(error)
            return
        self._queue_health_change_animation(None, before_health)

        if result.skipped:
            message = f"{result.source_name} 跳过{action_text}。"
        elif action_text in ("死亡预言", "伤害预言"):
            message = f"{result.source_name} {action_text} {result.target_name}。"
        elif action_text == "攻击后治疗":
            message = f"{result.source_name} 为 {result.target_name} 恢复生命。"
        elif action_text == "镜像复制":
            message = f"{result.source_name} 复制 {result.target_name} 的技能。"
        elif result.actual_target_name and result.actual_target_name != result.target_name:
            message = f"{result.source_name} {action_text} {result.target_name}，{result.actual_target_name} 承受 {result.damage} 点伤害。"
        else:
            message = f"{result.source_name} {action_text} {result.target_name}，造成 {result.damage} 点伤害。"
        for event in result.events:
            if event not in message:
                message += f" {event}"
        if result.defeated_character_names:
            message += f" {'、'.join(result.defeated_character_names)} 死亡。"
        message = self._append_pending_or_next_text(message, session, result.winner_player_id)

        self._log_battle(message)
        if not self._sync_pending_followup_selection(session):
            self.selected_battle_actor_id = None
            self.selected_battle_character = None
            self.battle_action_mode = None
            self.selected_active_skill_id = None
            self.selected_skill_target_ids = []
            self.skill_option_buttons = []
        self._sync_battle_button_states()

    def resolve_sword_saint_choice(self, option: str) -> None:
        session = self._ensure_battle_session()
        before_health = self._battle_health_snapshot()
        try:
            result = session.resolve_sword_saint_choice(option)
        except BattleError as error:
            self.message = str(error)
            return
        self._queue_health_change_animation(None, before_health)

        message = f"{result.source_name} 选择{result.choice_name}。"
        for event in result.events:
            if event not in message:
                message += f" {event}"
        message = self._append_pending_or_next_text(message, session, result.winner_player_id)
        self._log_battle(message)
        if not self._sync_pending_followup_selection(session):
            self.selected_battle_actor_id = None
            self.selected_battle_character = None
            self.battle_action_mode = None
            self.selected_active_skill_id = None
            self.selected_skill_target_ids = []
            self.skill_option_buttons = []
        self._sync_battle_button_states()

    def resolve_chase_target(self, target_id: str) -> None:
        session = self._ensure_battle_session()
        chase_choice = session.current_chase_choice()
        source_key = chase_choice[0] if chase_choice is not None else None
        before_health = self._battle_health_snapshot()
        try:
            result = session.resolve_chase_target(target_id)
        except BattleError as error:
            self.message = str(error)
            return
        if source_key is not None:
            self._queue_health_change_animation(
                source_key,
                before_health,
                show_slash=True,
                critical_damage_keys=self._critical_damage_keys(result),
            )

        if result.actual_target_name and result.actual_target_name != result.target_name:
            message = f"{result.source_name} 追击 {result.target_name}，{result.actual_target_name} 承受 {result.damage} 点伤害。"
        else:
            message = f"{result.source_name} 追击 {result.target_name}，造成 {result.damage} 点伤害。"
        for event in result.events:
            if event not in message:
                message += f" {event}"
        if result.defeated_character_names:
            message += f" {'、'.join(result.defeated_character_names)} 死亡。"
        message = self._append_pending_or_next_text(message, session, result.winner_player_id)
        self._log_battle(message)
        if not self._sync_pending_followup_selection(session):
            self.selected_battle_actor_id = None
            self.selected_battle_character = None
            self.battle_action_mode = None
            self.selected_active_skill_id = None
            self.selected_skill_target_ids = []
            self.skill_option_buttons = []
        self._sync_battle_button_states()

    def relocate_selected_actor(self, position: Position) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None or self.selected_battle_actor_id is None:
            self.message = "请先选择可以位移的角色。"
            return

        try:
            result = session.relocate_character(current_player_id, self.selected_battle_actor_id, position)
        except BattleError as error:
            self.message = str(error)
            return

        self._log_battle(
            f"{result.actor_name} 从 {self._position_label(result.from_position)} 位移到 {self._position_label(result.to_position)}。"
        )
        self.selected_battle_character = (current_player_id, self.selected_battle_actor_id)
        self.battle_action_mode = "relocate"
        self.selected_active_skill_id = None
        self.skill_option_buttons = []
        self._sync_battle_button_states()

    def resolve_summon_position(self, position: Position) -> None:
        session = self._ensure_battle_session()
        try:
            result = session.resolve_summon(position)
        except BattleError as error:
            self.message = str(error)
            return

        message = f"{result.source_name} 在 {self._position_label(result.position)} 召唤 {result.summoned_name}。"
        for event in result.events:
            if event not in message:
                message += f" {event}"
        message = self._append_pending_or_next_text(message, session, result.winner_player_id)

        self._log_battle(message)
        self.selected_battle_actor_id = None
        self.selected_battle_character = None
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.selected_skill_target_ids = []
        self.skill_option_buttons = []
        self._sync_battle_button_states()

    def end_current_player_round(self) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None:
            return

        try:
            result = session.end_player_round(current_player_id)
        except BattleError as error:
            self.message = str(error)
            return

        consumed = "、".join(result.consumed_actor_names) if result.consumed_actor_names else "无"
        next_text = ""
        if result.next_player_id is not None:
            next_text = f" 现在由 {self.game_state.player(result.next_player_id).name} 行动。"
        self._log_battle(f"{result.player_name} 结束本轮，消耗：{consumed}。{next_text}")
        self.selected_battle_actor_id = None
        self.selected_battle_character = None
        self.battle_action_mode = None
        self.selected_active_skill_id = None
        self.skill_option_buttons = []
        self._sync_battle_button_states()

    def attack_selected_target(self, target_id: str) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None or self.selected_battle_actor_id is None:
            self.message = "请先选择一个可行动角色。"
            return

        before_health = self._battle_health_snapshot()
        try:
            result = session.attack(current_player_id, self.selected_battle_actor_id, target_id)
        except BattleError as error:
            self.message = str(error)
            return
        self._queue_health_change_animation(
            (current_player_id, self.selected_battle_actor_id),
            before_health,
            show_slash=True,
            critical_damage_keys=self._critical_damage_keys(result),
        )

        message = f"{result.attacker_name} 攻击 {result.target_name}，造成 {result.damage} 点伤害。"
        if result.actual_target_name and result.actual_target_name != result.target_name:
            message = f"{result.attacker_name} 攻击 {result.target_name}，{result.actual_target_name} 承受 {result.damage} 点伤害。"
        if result.skipped_actor_names:
            message = f"跳过 {'、'.join(result.skipped_actor_names)}。{message}"
        for event in result.events:
            message += f" {event}"
        if result.defeated_character_names:
            message += f" {'、'.join(result.defeated_character_names)} 死亡。"
        message = self._append_pending_or_next_text(message, session, result.winner_player_id)

        self._log_battle(message)
        if not self._sync_pending_followup_selection(session):
            self.selected_battle_actor_id = None
            self.selected_battle_character = None
            self.battle_action_mode = None
            self.selected_active_skill_id = None
            self.skill_option_buttons = []
        self._sync_battle_button_states()

    def _critical_damage_keys(self, result) -> set[tuple[int, str]]:
        return {
            (event.player_id, event.character_id)
            for event in getattr(result, "damage_events", ())
            if getattr(event, "critical", False)
        }

    def _build_skill_option_buttons(self, player_id: int, character_id: str) -> None:
        session = self._ensure_battle_session()
        self.skill_option_buttons = []
        self._clamp_skill_option_scroll_offset()
        for index, skill in enumerate(session.active_skills(player_id, character_id)):
            rect = pygame.Rect(884, 432 + index * 44 - self.skill_option_scroll_offset, 172, 36)
            button = Button(
                rect,
                skill.name,
                lambda skill_id=skill.id: self.select_active_skill(skill_id),
                font_size=18,
                enabled=session.can_cast_skill(player_id, character_id, skill.id),
            )
            button.skill_id = skill.id
            self.skill_option_buttons.append(button)

    def _rebuild_current_skill_option_buttons(self) -> None:
        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        if current_player_id is None or self.selected_battle_actor_id is None:
            return
        self._build_skill_option_buttons(current_player_id, self.selected_battle_actor_id)

    def _skill_option_area_rect(self) -> pygame.Rect:
        return pygame.Rect(884, 432, 172, 124)

    def _battle_action_area_rect(self) -> pygame.Rect:
        return pygame.Rect(884, 432, 172, 168)

    def _visible_battle_action_buttons(self) -> list[Button]:
        return [
            button
            for button in (
                self.attack_button,
                self.skill_button,
                self.thaw_button,
                self.revive_button,
                self.skip_button,
                self.end_round_button,
                self.second_hand_button,
            )
            if button.enabled
        ]

    def _battle_action_content_height(self, buttons: list[Button] | None = None) -> int:
        action_buttons = buttons if buttons is not None else self._visible_battle_action_buttons()
        if not action_buttons:
            return 0
        return len(action_buttons) * 36 + max(0, len(action_buttons) - 1) * 8

    def _clamp_battle_action_scroll_offset(self) -> None:
        max_offset = max(0, self._battle_action_content_height() - self._battle_action_area_rect().height)
        self.battle_action_scroll_offset = max(0, min(self.battle_action_scroll_offset, max_offset))

    def _layout_battle_action_buttons(self, buttons: list[Button]) -> list[Button]:
        area = self._battle_action_area_rect()
        self._clamp_battle_action_scroll_offset()
        for index, button in enumerate(buttons):
            button.rect = pygame.Rect(area.x, area.y + index * 44 - self.battle_action_scroll_offset, area.width, 36)
        return buttons

    def _skill_option_content_height(self) -> int:
        session = self.battle_session
        if (
            session is None
            or session.current_player_id is None
            or self.selected_battle_actor_id is None
            or self.battle_action_mode != "skill_menu"
        ):
            return 0
        skill_count = len(session.active_skills(session.current_player_id, self.selected_battle_actor_id))
        if skill_count == 0:
            return 0
        return skill_count * 36 + max(0, skill_count - 1) * 8

    def _clamp_skill_option_scroll_offset(self) -> None:
        max_offset = max(0, self._skill_option_content_height() - self._skill_option_area_rect().height)
        self.skill_option_scroll_offset = max(0, min(self.skill_option_scroll_offset, max_offset))

    def _sync_pending_followup_selection(self, session: BattleSession) -> bool:
        sword_choice = session.current_sword_saint_choice()
        if sword_choice is not None:
            player_id, character_id = sword_choice
            self.selected_battle_actor_id = character_id
            self.selected_battle_character = (player_id, character_id)
            self.battle_action_mode = None
            self.selected_active_skill_id = None
            self.selected_skill_target_ids = []
            self.skill_option_buttons = []
            return True

        chase_choice = session.current_chase_choice()
        if chase_choice is not None:
            attacker_key, _target_key = chase_choice
            player_id, character_id = attacker_key
            self.selected_battle_actor_id = character_id
            self.selected_battle_character = (player_id, character_id)
            self.battle_action_mode = "chase_target"
            self.selected_active_skill_id = None
            self.selected_skill_target_ids = []
            self.skill_option_buttons = []
            return True

        followup = session.current_followup_attack()
        if followup is None:
            return False

        player_id, character_id = followup
        character = self.game_state.player(player_id).get_character(character_id)
        self.selected_battle_actor_id = character_id
        self.selected_battle_character = (player_id, character_id)
        self.battle_action_mode = "attack"
        self.selected_active_skill_id = None
        self.selected_skill_target_ids = []
        self.skill_option_buttons = []
        self.message = f"{character.name} 准备第二次攻击，请点击一个合法敌方目标，或跳过。"
        if session.current_followup_remaining_attacks() > 1:
            self.message = f"{character.name} 准备继续攻击，剩余 {session.current_followup_remaining_attacks()} 次，请点击一个合法敌方目标，或跳过。"
        return True

    def _log_battle(self, message: str) -> None:
        self.message = message
        self.battle_log.insert(0, message)
        self.battle_log = self.battle_log[:80]
        self.battle_log_scroll_offset = 0

    def _death_trigger_action_text(self, death_trigger: object | None) -> str:
        kind = getattr(death_trigger, "kind", "damage")
        if kind == "attack_buff":
            return "死亡预言"
        if kind == "damage_prophecy":
            return "伤害预言"
        if kind in ("heal", "heal_ally"):
            return "攻击后治疗"
        if kind == "mirror_copy":
            return "镜像复制"
        return "死亡追击"

    def _death_trigger_prompt(self, death_trigger: object) -> str:
        action_text = self._death_trigger_action_text(death_trigger)
        return f"请处理 {getattr(death_trigger, 'character_name')} 的{action_text}。"

    def _followup_prompt(self, session: BattleSession, character: Character) -> str:
        remaining = session.current_followup_remaining_attacks()
        if remaining > 1:
            return f"请为 {character.name} 选择下一次攻击目标（剩余 {remaining} 次）。"
        return f"请为 {character.name} 选择第二次攻击目标。"

    def _append_pending_or_next_text(
        self,
        message: str,
        session: BattleSession,
        winner_player_id: int | None,
    ) -> str:
        if winner_player_id is not None:
            return f"{message} {self.game_state.player(winner_player_id).name} 获胜。"
        if session.current_death_trigger() is not None:
            next_trigger = session.current_death_trigger()
            if next_trigger is not None:
                return f"{message} {self._death_trigger_prompt(next_trigger)}"
        if session.current_summon_request() is not None:
            summon = session.current_summon_request()
            if summon is not None:
                return f"{message} 请为 {summon.source_name} 选择召唤空位。"
        if session.current_sword_saint_choice() is not None:
            sword_choice = session.current_sword_saint_choice()
            if sword_choice is not None:
                actor = self.game_state.player(sword_choice[0]).get_character(sword_choice[1])
                return f"{message} 请为 {actor.name} 选择剑圣效果。"
        if session.current_chase_choice() is not None:
            chase_choice = session.current_chase_choice()
            if chase_choice is not None:
                actor = self.game_state.player(chase_choice[0][0]).get_character(chase_choice[0][1])
                return f"{message} 请为 {actor.name} 选择追击目标。"
        if session.current_followup_attack() is not None:
            followup = session.current_followup_attack()
            if followup is not None:
                actor = self.game_state.player(followup[0]).get_character(followup[1])
                return f"{message} {self._followup_prompt(session, actor)}"
        next_player_id = session.current_player_id
        if next_player_id is not None:
            return f"{message} 现在由 {self.game_state.player(next_player_id).name} 行动。"
        return message

    def _handle_battle_board_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        session = self._ensure_battle_session()
        current_player_id = session.current_player_id
        summon = session.current_summon_request()
        if summon is not None:
            slot = self._battle_slot_at(event.pos)
            if slot is None:
                return
            slot_player_id, slot_position = slot
            if slot_player_id == summon.player_id and session.can_resolve_summon(slot_position):
                self.resolve_summon_position(slot_position)
            else:
                self.message = "请选择召唤方阵型中的空位。"
                self._sync_battle_button_states()
            return

        if (
            self.battle_action_mode == "relocate"
            and current_player_id is not None
            and self.selected_battle_actor_id is not None
        ):
            slot = self._battle_slot_at(event.pos)
            if slot is None:
                return
            slot_player_id, slot_position = slot
            if (
                slot_player_id == current_player_id
                and session.can_relocate_character(current_player_id, self.selected_battle_actor_id, slot_position)
            ):
                self.relocate_selected_actor(slot_position)
            else:
                self.message = "请选择己方空位进行位移。"
                self._sync_battle_button_states()
            return

        hit = self._battle_character_at(event.pos)
        if hit is None:
            return

        player_id, character_id = hit
        if session.current_death_trigger() is not None:
            if session.can_resolve_death_trigger(character_id):
                self.resolve_death_trigger_target(character_id)
            else:
                character = self.game_state.player(player_id).get_character(character_id)
                self.selected_battle_character = (player_id, character_id)
                action_text = self._death_trigger_action_text(session.current_death_trigger())
                self.message = f"{character.name} 不是{action_text}的合法目标。"
                self._sync_battle_button_states()
            return

        if session.current_chase_choice() is not None:
            if session.can_resolve_chase_target(character_id):
                self.resolve_chase_target(character_id)
            else:
                character = self.game_state.player(player_id).get_character(character_id)
                self.selected_battle_character = (player_id, character_id)
                self.message = f"{character.name} 不是当前追击的合法目标。"
                self._sync_battle_button_states()
            return

        if (
            self.battle_action_mode == "skill_target"
            and self.selected_battle_actor_id is not None
            and self.selected_active_skill_id is not None
            and current_player_id is not None
        ):
            legal_target_ids = {
                target.id
                for target in session.skill_targets(
                    current_player_id,
                    self.selected_battle_actor_id,
                    self.selected_active_skill_id,
                )
            }
            skill = next(
                skill
                for skill in session.active_skills(current_player_id, self.selected_battle_actor_id)
                if skill.id == self.selected_active_skill_id
            )
            allows_repeat_targets = skill.id.split("__copy_", 1)[0] == "brutal_bomber_distribute"
            if character_id in legal_target_ids and (allows_repeat_targets or character_id not in self.selected_skill_target_ids):
                self.cast_selected_skill_on_target(character_id)
            else:
                character = self.game_state.player(player_id).get_character(character_id)
                self.selected_battle_character = (player_id, character_id)
                self.message = f"{character.name} 不是当前技能的合法目标。"
                self._sync_battle_button_states()
            return

        if (
            self.battle_action_mode == "attack"
            and self.selected_battle_actor_id is not None
            and current_player_id is not None
            and player_id != current_player_id
        ):
            if session.can_attack(current_player_id, self.selected_battle_actor_id, character_id):
                self.attack_selected_target(character_id)
            else:
                character = self.game_state.player(player_id).get_character(character_id)
                self.selected_battle_character = (player_id, character_id)
                self.message = f"{character.name} 不是当前可攻击目标。"
                self._sync_battle_button_states()
            return

        self.select_battle_character(player_id, character_id)

    def _battle_character_at(self, position: tuple[int, int]) -> tuple[int, str] | None:
        for player_id in (1, 2):
            player = self.game_state.player(player_id)
            for slot_position, character_id in player.formation.items():
                if self._battle_card_rect(player_id, slot_position).collidepoint(position):
                    character = player.get_character(character_id)
                    if character.is_alive or (
                        self.battle_session is not None
                        and (player_id, character_id) in self.battle_session.pending_revivals
                    ):
                        return player_id, character_id
                    return None
        return None

    def _battle_slot_at(self, position: tuple[int, int]) -> tuple[int, Position] | None:
        for player_id in (1, 2):
            for row in range(3):
                for column in (FormationColumn.BACK, FormationColumn.FRONT):
                    slot_position = Position(row=row, column=column)
                    if self._battle_card_rect(player_id, slot_position).collidepoint(position):
                        return player_id, slot_position
        return None

    def _battle_card_rect(self, player_id: int, position: Position) -> pygame.Rect:
        side_x = 64 if player_id == 1 else 470
        if player_id == 1:
            column_offset = 0 if position.column == FormationColumn.BACK else 174
        else:
            column_offset = 0 if position.column == FormationColumn.FRONT else 174
        return pygame.Rect(side_x + column_offset, 172 + position.row * 96, 162, 78)

    def _selected_battle_character(self) -> tuple[int, Character] | None:
        if self.selected_battle_character is None:
            return None

        player_id, character_id = self.selected_battle_character
        return player_id, self.game_state.player(player_id).get_character(character_id)

    def _job_initial(self, character: Character) -> str:
        return character.job.name[:1] or "?"

    def _draw_hp_bar(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        current_health: int,
        max_health: int,
    ) -> None:
        pygame.draw.rect(surface, COLORS["background"], rect, border_radius=4)
        if max_health <= 0:
            return

        ratio = max(0, min(current_health / max_health, 1))
        fill_width = int(rect.width * ratio)
        if fill_width <= 0:
            return

        fill_color = COLORS["success"] if ratio > 0.35 else COLORS["danger"]
        fill_rect = pygame.Rect(rect.x, rect.y, fill_width, rect.height)
        pygame.draw.rect(surface, fill_color, fill_rect, border_radius=4)

    def _battle_status_text(self, player_id: int, character: Character) -> str:
        if self.battle_session is None:
            return ""
        character_key = (player_id, character.id)
        status_names = []
        for effect_id in sorted(character.status_effect_ids):
            if effect_id == "shield":
                stacks = self.battle_session.shield_stack_count(character_key)
                status_names.append(f"护盾{stacks}" if stacks > 1 else "护盾")
            else:
                status_names.append(effect_display_name(effect_id))
        if self.battle_session._character_has_battle_effect((player_id, character.id), "stealth"):
            status_names.append("隐匿")
        if self.battle_session._character_has_battle_effect((player_id, character.id), "immunity"):
            status_names.append("免疫")
        if character.armor > 0:
            status_names.append(f"护甲{character.armor}")
        if (player_id, character.id) in self.battle_session.pending_revivals:
            status_names.append("待复活")
        if not character.is_alive:
            base_status = "死亡"
            return "/".join((*status_names, base_status)) if status_names else base_status

        remaining = self.battle_session.remaining_move_count(player_id, character.id)
        if remaining <= 0:
            if character.id in self.battle_session.round_skipped_ids[player_id]:
                base_status = "跳过"
            else:
                base_status = "已动"
            return "/".join((*status_names, base_status)) if status_names else base_status

        if self.battle_session.current_player_id != player_id:
            base_status = "待回合"
            return "/".join((*status_names, base_status)) if status_names else base_status

        if self.battle_session.can_character_move(player_id, character.id):
            if self.battle_session.is_never_moved(player_id, character.id):
                base_status = "可动/未动"
            else:
                base_status = "可动"
            return "/".join((*status_names, base_status)) if status_names else base_status

        if self.battle_session.blocked_actor_names_before_choice(player_id, character.id):
            base_status = "顺序限制"
        else:
            base_status = "不可动"
        return "/".join((*status_names, base_status)) if status_names else base_status

    def _draw_top_bar(self, surface: pygame.Surface, title: str, description: str) -> None:
        draw_text(surface, title, (40, 24), size=31, bold=True)
        draw_text_fit(surface, description, (190, 34), WINDOW_WIDTH - 240, size=18, color=COLORS["muted"])
        pygame.draw.line(surface, COLORS["border"], (40, 76), (WINDOW_WIDTH - 40, 76), 1)

    def _battle_action_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(856, 92, 224, 530)

    def _battle_log_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(40, 526, 792, 96)

    def _battle_log_overlay_rect(self) -> pygame.Rect:
        return pygame.Rect(116, 104, 888, 488)

    def _draw_draft(self, surface: pygame.Surface) -> None:
        self._draw_top_bar(surface, "游戏界面", self._phase_status_text())

        pool_panel = pygame.Rect(40, 92, 680, 530)
        side_panel = pygame.Rect(744, 92, 336, 530)
        pygame.draw.rect(surface, COLORS["surface"], pool_panel, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], pool_panel, 2, border_radius=8)
        pygame.draw.rect(surface, COLORS["surface"], side_panel, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], side_panel, 2, border_radius=8)

        draw_text(surface, "职业筛选", (64, 114), size=22, bold=True)
        self._draw_draft_job_filters(surface)
        draw_text(surface, "角色池", (224, 114), size=27, bold=True)
        visible_count = len(self._visible_draft_characters())
        draw_text(surface, f"{visible_count} 名", (646, 120), size=18, color=COLORS["muted"])
        draw_wrapped_text(surface, self.message, (64, 580), 630, size=17, color=COLORS["muted"], line_height=21, max_lines=2)

        character_area = self._draft_character_area()
        previous_clip = surface.get_clip()
        surface.set_clip(character_area)
        for button in self.character_buttons:
            if not button.rect.colliderect(character_area):
                continue
            button.draw(surface)
            self._draw_character_pick_marker(surface, button)
        surface.set_clip(previous_clip)
        if not self.character_buttons:
            draw_text(surface, "该职业暂无角色", (266, 330), size=24, color=COLORS["muted"])
        self._draw_scrollbar(surface, character_area, self._draft_content_height(), self.draft_scroll_offset)

        self._draw_player_pick_panel(surface, 1, pygame.Rect(768, 128, 288, 204))
        self._draw_player_pick_panel(surface, 2, pygame.Rect(768, 360, 288, 204))
        self.undo_draft_button.draw(surface)

    def _draw_formation(self, surface: pygame.Surface) -> None:
        session = self._ensure_formation_session()
        player = session.current_player

        self._draw_top_bar(surface, "排阵阶段", self._phase_status_text())

        character_panel = pygame.Rect(40, 92, 360, 530)
        grid_panel = pygame.Rect(424, 92, 420, 530)
        side_panel = pygame.Rect(868, 92, 212, 530)
        pygame.draw.rect(surface, COLORS["surface"], character_panel, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], character_panel, 2, border_radius=8)
        pygame.draw.rect(surface, COLORS["surface"], grid_panel, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], grid_panel, 2, border_radius=8)
        pygame.draw.rect(surface, COLORS["surface"], side_panel, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], side_panel, 2, border_radius=8)

        draw_text(surface, f"{player.name} 角色", (64, 114), size=27, bold=True)
        for button in self.formation_character_buttons:
            button.draw(surface)
            self._draw_formation_character_marker(surface, button)

        draw_text(surface, "后排", (506, 112), size=22, color=COLORS["muted"], bold=True)
        draw_text(surface, "前排", (676, 112), size=22, color=COLORS["muted"], bold=True)
        for button in self.formation_slot_buttons:
            self._draw_formation_slot(surface, button)

        placed_count = len(player.formation)
        draw_text(surface, "布阵信息", (890, 116), size=24, bold=True)
        draw_text(surface, f"已放置 {placed_count}/6", (890, 168), size=21)
        draw_text(surface, "至少 1 名即可确认", (890, 196), size=17, color=COLORS["muted"])
        draw_text(surface, "限制", (890, 222), size=21, bold=True)
        draw_text(surface, "抵御者/斩杀者", (890, 260), size=18, color=COLORS["muted"])
        draw_text(surface, "只能前排", (890, 286), size=18, color=COLORS["muted"])
        draw_text(surface, "英雄同一行", (890, 330), size=18, color=COLORS["muted"])
        draw_text(surface, "前后不可有单位", (890, 356), size=18, color=COLORS["muted"])
        self.confirm_formation_button.draw(surface)
        draw_wrapped_text(surface, self.message, (64, 570), 310, size=16, color=COLORS["muted"], line_height=20, max_lines=2)

    def _draw_battle(self, surface: pygame.Surface) -> None:
        session = self._ensure_battle_session()

        self._draw_top_bar(surface, "对战阶段", self._phase_status_text())

        battle_panel = pygame.Rect(40, 92, 792, 420)
        log_panel = self._battle_log_panel_rect()
        action_panel = self._battle_action_panel_rect()
        pygame.draw.rect(surface, COLORS["surface"], battle_panel, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], battle_panel, 2, border_radius=8)
        pygame.draw.rect(surface, COLORS["surface"], log_panel, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], log_panel, 2, border_radius=8)
        pygame.draw.rect(surface, COLORS["surface"], action_panel, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], action_panel, 2, border_radius=8)

        self._draw_battle_board(surface, session, battle_panel)
        self._draw_battle_animations(surface)
        self._draw_battle_log(surface, log_panel)
        self._draw_battle_action_panel(surface, session, action_panel)
        self._draw_battle_log_overlay(surface)

    def _draw_finished(self, surface: pygame.Surface) -> None:
        winner_name = "未知玩家"
        if self.game_state.winner_player_id is not None:
            winner_name = self.game_state.player(self.game_state.winner_player_id).name

        self._draw_top_bar(surface, "游戏结束", f"{winner_name} 获胜")

        left_panel = pygame.Rect(40, 108, 500, 496)
        right_panel = pygame.Rect(580, 108, 500, 496)
        pygame.draw.rect(surface, COLORS["surface"], left_panel, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], left_panel, 2, border_radius=8)
        pygame.draw.rect(surface, COLORS["surface"], right_panel, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], right_panel, 2, border_radius=8)
        self._draw_final_formation(surface, 1, left_panel)
        self._draw_final_formation(surface, 2, right_panel)
        draw_wrapped_text(surface, self.message, (64, 610), 992, size=17, color=COLORS["muted"], line_height=21, max_lines=2)

    def _draw_battle_board(self, surface: pygame.Surface, session: BattleSession, rect: pygame.Rect) -> None:
        for player_id in (1, 2):
            player = self.game_state.player(player_id)
            current = session.current_player_id == player_id
            title_color = COLORS["accent"] if current else COLORS["text"]
            title_x = rect.x + 24 if player_id == 1 else rect.x + 430
            draw_text(surface, f"{player.name}{' 当前' if current else ''}", (title_x, rect.y + 18), size=24, color=title_color, bold=True)
            left_label, right_label = ("后", "前") if player_id == 1 else ("前", "后")
            draw_text(surface, left_label, (title_x + 56, rect.y + 58), size=18, color=COLORS["muted"], bold=True)
            draw_text(surface, right_label, (title_x + 230, rect.y + 58), size=18, color=COLORS["muted"], bold=True)

            for row in range(3):
                for column in (FormationColumn.BACK, FormationColumn.FRONT):
                    position = Position(row=row, column=column)
                    slot_rect = self._battle_card_rect(player_id, position)
                    character = player.character_at(position)
                    character_id = player.formation.get(position)
                    if character is None and self.battle_session is not None:
                        if character_id is not None and (player_id, character_id) in self.battle_session.pending_revivals:
                            character = player.get_character(character_id)
                    self._draw_battle_slot(surface, slot_rect, position, character, player_id)

        for player_id in (1, 2):
            self._draw_team_barrier(surface, session, player_id)

        divider_x = rect.x + rect.width // 2
        pygame.draw.line(surface, COLORS["border"], (divider_x, rect.y + 16), (divider_x, rect.bottom - 16), 2)

    def _team_barrier_rect(self, session: BattleSession, player_id: int) -> pygame.Rect | None:
        if session.team_barrier_amount(player_id) <= 0:
            return None

        player = self.game_state.player(player_id)
        protected_rects: list[pygame.Rect] = []
        for position, character_id in player.formation.items():
            character = player.get_character(character_id)
            if character.is_alive and character.position is not None:
                protected_rects.append(self._battle_card_rect(player_id, position))
        if not protected_rects:
            return None

        barrier_rect = protected_rects[0].copy()
        for protected_rect in protected_rects[1:]:
            barrier_rect.union_ip(protected_rect)
        return barrier_rect.inflate(18, 18)

    def _draw_team_barrier(self, surface: pygame.Surface, session: BattleSession, player_id: int) -> None:
        barrier_rect = self._team_barrier_rect(session, player_id)
        if barrier_rect is None:
            return

        amount = session.team_barrier_amount(player_id)
        pygame.draw.rect(surface, COLORS["info"], barrier_rect, 3, border_radius=10)
        draw_text(
            surface,
            f"屏障剩余 {amount}",
            (barrier_rect.x + 8, barrier_rect.bottom + 4),
            size=15,
            color=COLORS["info"],
            bold=True,
        )

    def _draw_battle_slot(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        position: Position,
        character,
        player_id: int,
    ) -> None:
        border_color = COLORS["border"]
        border_width = 2
        is_selected = character is not None and self.selected_battle_character == (player_id, character.id)
        if character is not None and self.battle_session is not None:
            if (
                self.battle_session.current_player_id == player_id
                and self.battle_session.can_character_move(player_id, character.id)
            ):
                border_color = COLORS["success"]
                border_width = 3
            elif character.id in self.battle_session.round_skipped_ids[player_id]:
                border_color = COLORS["danger"]

        if is_selected and border_color != COLORS["success"]:
            border_color = COLORS["accent"]
            border_width = 3

        if (
            character is not None
            and self.battle_session is not None
            and self.battle_session.current_death_trigger() is not None
            and self.battle_session.can_resolve_death_trigger(character.id)
        ):
            border_color = COLORS["danger"]
            border_width = 3

        if (
            character is not None
            and self.battle_action_mode == "attack"
            and self.selected_battle_actor_id is not None
            and self.battle_session is not None
            and self.battle_session.current_player_id is not None
            and player_id != self.battle_session.current_player_id
            and self.battle_session.can_attack(
                self.battle_session.current_player_id,
                self.selected_battle_actor_id,
                character.id,
            )
        ):
            border_color = COLORS["danger"]
            border_width = 3

        if (
            character is not None
            and self.battle_action_mode == "skill_target"
            and self.selected_battle_actor_id is not None
            and self.selected_active_skill_id is not None
            and self.battle_session is not None
            and self.battle_session.current_player_id is not None
            and character.id
            in {
                target.id
                for target in self.battle_session.skill_targets(
                    self.battle_session.current_player_id,
                    self.selected_battle_actor_id,
                    self.selected_active_skill_id,
                )
            }
        ):
            selected_skill = next(
                (
                    skill
                    for skill in self.battle_session.active_skills(
                        self.battle_session.current_player_id,
                        self.selected_battle_actor_id,
                    )
                    if skill.id == self.selected_active_skill_id
                ),
                None,
            )
            allows_repeat_targets = (
                selected_skill is not None and selected_skill.id.split("__copy_", 1)[0] == "brutal_bomber_distribute"
            )
            if allows_repeat_targets or character.id not in self.selected_skill_target_ids:
                border_color = COLORS["danger"]
                border_width = 3

        if (
            character is not None
            and self.battle_session is not None
            and self.battle_session.current_chase_choice() is not None
            and character.id in {target.id for target in self.battle_session.chase_targets()}
        ):
            border_color = COLORS["danger"]
            border_width = 3

        if (
            self.battle_action_mode == "relocate"
            and character is None
            and self.selected_battle_actor_id is not None
            and self.battle_session is not None
            and self.battle_session.current_player_id == player_id
            and self.battle_session.can_relocate_character(player_id, self.selected_battle_actor_id, position)
        ):
            border_color = COLORS["info"]
            border_width = 3

        summon = self.battle_session.current_summon_request() if self.battle_session is not None else None
        if (
            summon is not None
            and character is None
            and summon.player_id == player_id
            and self.battle_session is not None
            and self.battle_session.can_resolve_summon(position)
        ):
            border_color = COLORS["info"]
            border_width = 3

        pygame.draw.rect(surface, COLORS["surface_alt"], rect, border_radius=8)
        pygame.draw.rect(surface, border_color, rect, border_width, border_radius=8)
        if is_selected and border_color == COLORS["success"]:
            pygame.draw.rect(surface, COLORS["accent"], rect.inflate(-8, -8), 2, border_radius=6)
        draw_text(surface, f"{position.row + 1}", (rect.x + 10, rect.y + 8), size=15, color=COLORS["muted"], bold=True)

        if character is None:
            draw_text(surface, "空", (rect.x + 44, rect.y + 34), size=22, color=COLORS["muted"])
            return

        text_color = COLORS["text"] if character.is_alive else COLORS["danger"]
        name = character.name if character.is_alive else f"{character.name} 死亡"
        draw_text(surface, name, (rect.x + 28, rect.y + 9), size=17, color=text_color, bold=True)
        draw_text(surface, self._job_initial(character), (rect.right - 28, rect.y + 9), size=17, color=COLORS["accent"], bold=True)
        attack_value = character.attack
        if self.battle_session is not None:
            attack_value = self.battle_session.effective_attack((player_id, character.id))
        draw_text(surface, f"HP {character.current_health}/{character.max_health}", (rect.x + 28, rect.y + 33), size=13, color=COLORS["muted"])
        draw_text(surface, f"ATK {attack_value}", (rect.x + 92, rect.y + 33), size=13, color=COLORS["accent"])
        self._draw_hp_bar(surface, pygame.Rect(rect.x + 28, rect.y + 52, 74, 6), character.current_health, character.max_health)
        status_text = self._battle_status_text(player_id, character)
        if status_text:
            draw_text(surface, status_text, (rect.x + 28, rect.y + 60), size=12, color=COLORS["muted"])

        if self.battle_session is not None and character.is_alive:
            moves = self.battle_session.remaining_move_count(player_id, character.id)
            skipped = character.id in self.battle_session.round_skipped_ids[player_id]
            if skipped:
                draw_text(surface, "跳", (rect.right - 28, rect.y + 56), size=14, color=COLORS["danger"], bold=True)
            else:
                draw_text(surface, f"x{moves}", (rect.right - 32, rect.y + 56), size=14, color=COLORS["accent"], bold=True)

    def _draw_battle_action_panel(self, surface: pygame.Surface, session: BattleSession, rect: pygame.Rect) -> None:
        draw_text(surface, "角色详情", (rect.x + 18, rect.y + 14), size=22, bold=True)
        draw_text(surface, f"第 {self.game_state.round_number} 轮", (rect.x + 18, rect.y + 44), size=16, color=COLORS["muted"])

        if session.pending_start_order_choice_player_id is not None:
            choice_player = self.game_state.player(session.pending_start_order_choice_player_id)
            draw_wrapped_text(
                surface,
                f"{choice_player.name} 同时拥有定序王子和蚀时狼妃，请选择自己先手或后手。",
                (rect.x + 18, rect.y + 74),
                rect.width - 36,
                size=16,
                color=COLORS["accent"],
                bold=True,
                line_height=22,
                max_lines=4,
            )
            draw_wrapped_text(
                surface,
                "选择完成后才会结算游戏开始时技能。",
                (rect.x + 18, rect.y + 170),
                rect.width - 36,
                size=15,
                color=COLORS["muted"],
                line_height=21,
            )
            draw_text(surface, "开局先后手", (rect.x + 18, self.choose_first_button.rect.y - 32), size=18, color=COLORS["muted"], bold=True)
            self.choose_first_button.draw(surface)
            self.choose_second_button.draw(surface)
            return

        death_trigger = session.current_death_trigger()
        if death_trigger is not None:
            action_text = self._death_trigger_action_text(death_trigger)
            can_skip_trigger = session.can_resolve_death_trigger(None)
            target_hint = "可指定任意存活角色。"
            if getattr(death_trigger, "kind", "damage") == "mirror_copy":
                target_hint = "请选择一个其他友方角色。"
            draw_wrapped_text(
                surface,
                f"{death_trigger.character_name} 的{action_text}：点击红框目标{('，或跳过' if can_skip_trigger else '')}。",
                (rect.x + 18, rect.y + 68),
                rect.width - 36,
                size=16,
                color=COLORS["danger"],
                bold=True,
                line_height=22,
                max_lines=3,
            )
            selected = self._selected_battle_character()
            detail_rect = pygame.Rect(rect.x + 18, rect.y + 142, rect.width - 36, 154)
            if selected is None:
                draw_wrapped_text(surface, f"{action_text}{target_hint}", detail_rect.topleft, detail_rect.width, size=15, color=COLORS["muted"], line_height=20)
            else:
                self._draw_battle_detail_view(surface, detail_rect, session, selected)
            action_area = self._battle_action_area_rect()
            draw_text(surface, "强制结算", (rect.x + 18, action_area.y - 32), size=18, color=COLORS["muted"], bold=True)
            if can_skip_trigger:
                buttons = self._layout_battle_action_buttons([self.skip_button])
                for button in buttons:
                    button.draw(surface)
            return

        summon = session.current_summon_request()
        if summon is not None:
            draw_wrapped_text(
                surface,
                f"{summon.source_name} 可以召唤单位：点击己方空位。",
                (rect.x + 18, rect.y + 68),
                rect.width - 36,
                size=16,
                color=COLORS["info"],
                bold=True,
                line_height=22,
                max_lines=3,
            )
            draw_wrapped_text(
                surface,
                "召唤物会进入战斗，并按正常移动顺序行动。",
                (rect.x + 18, rect.y + 142),
                rect.width - 36,
                size=15,
                color=COLORS["muted"],
                line_height=21,
            )
            return

        sword_choice = session.current_sword_saint_choice()
        if sword_choice is not None:
            sword_saint = self.game_state.player(sword_choice[0]).get_character(sword_choice[1])
            draw_wrapped_text(
                surface,
                f"{sword_saint.name} 攻击后选择一项效果。",
                (rect.x + 18, rect.y + 68),
                rect.width - 36,
                size=16,
                color=COLORS["info"],
                bold=True,
                line_height=22,
                max_lines=3,
            )
            draw_wrapped_text(
                surface,
                "第一项整局至多触发4次；第二项为所有友方战士恢复3点生命。",
                (rect.x + 18, rect.y + 132),
                rect.width - 36,
                size=14,
                color=COLORS["muted"],
                line_height=20,
            )
            draw_text(surface, "剑圣选择", (rect.x + 18, self.sword_saint_inspire_button.rect.y - 32), size=18, color=COLORS["muted"], bold=True)
            self.sword_saint_inspire_button.draw(surface)
            self.sword_saint_heal_button.draw(surface)
            return

        chase_choice = session.current_chase_choice()
        if chase_choice is not None:
            attacker_key, _target_key = chase_choice
            attacker = self.game_state.player(attacker_key[0]).get_character(attacker_key[1])
            draw_wrapped_text(
                surface,
                f"{attacker.name} 攻击后可以追击：点击红框目标。",
                (rect.x + 18, rect.y + 68),
                rect.width - 36,
                size=16,
                color=COLORS["danger"],
                bold=True,
                line_height=22,
                max_lines=3,
            )
            target_names = "、".join(target.name for target in session.chase_targets()) or "无"
            draw_wrapped_text(
                surface,
                f"可追击：{target_names}",
                (rect.x + 18, rect.y + 132),
                rect.width - 36,
                size=14,
                color=COLORS["muted"],
                line_height=20,
            )
            return

        current_player_id = session.current_player_id
        if current_player_id is None:
            draw_text(surface, "暂无可行动角色", (rect.x + 18, rect.y + 82), size=18, color=COLORS["muted"])
            return

        current_player = self.game_state.player(current_player_id)
        draw_text(surface, f"当前 {current_player.name}", (rect.x + 18, rect.y + 68), size=17)
        draw_text_fit(surface, self._battle_order_text(session, current_player_id), (rect.x + 18, rect.y + 92), rect.width - 36, size=14, color=COLORS["muted"])

        selected = self._selected_battle_character()
        detail_rect = pygame.Rect(rect.x + 18, rect.y + 118, rect.width - 36, 176)
        if selected is None:
            draw_wrapped_text(surface, "点击任意角色查看完整属性、状态与技能。", detail_rect.topleft, detail_rect.width, size=16, color=COLORS["muted"], line_height=22)
        else:
            self._draw_battle_detail_view(surface, detail_rect, session, selected)

        action_area = self._battle_action_area_rect()
        action_label_y = action_area.y - 32
        pending_followup = session.current_followup_attack()
        if self.battle_action_mode == "skill_menu":
            draw_text(surface, "选择主动技能", (rect.x + 18, action_label_y), size=18, color=COLORS["muted"], bold=True)
            skill_area = self._skill_option_area_rect()
            self._clamp_skill_option_scroll_offset()
            previous_clip = surface.get_clip()
            surface.set_clip(skill_area)
            for button in self.skill_option_buttons:
                if button.rect.colliderect(skill_area):
                    button.draw(surface)
            surface.set_clip(previous_clip)
            content_height = self._skill_option_content_height()
            if content_height > skill_area.height:
                self._draw_scrollbar(surface, skill_area, content_height, self.skill_option_scroll_offset)
            self.cancel_skill_button.draw(surface)
            return

        if self.battle_action_mode == "skill_target":
            skill_name = "主动技能"
            target_hint = "点击红框目标"
            if current_player_id is not None and self.selected_battle_actor_id is not None and self.selected_active_skill_id is not None:
                for skill in session.active_skills(current_player_id, self.selected_battle_actor_id):
                    if skill.id == self.selected_active_skill_id:
                        skill_name = skill.name
                        if skill.max_targets > 1:
                            available_count = len(session.skill_targets(current_player_id, self.selected_battle_actor_id, skill.id))
                            allows_repeat_targets = skill.id.split("__copy_", 1)[0] == "brutal_bomber_distribute"
                            required_count = skill.max_targets if allows_repeat_targets else min(skill.max_targets, available_count)
                            target_hint = f"已选 {len(self.selected_skill_target_ids)}/{required_count}"
                        break
            draw_text(surface, f"{skill_name}：{target_hint}", (rect.x + 18, action_label_y), size=16, color=COLORS["danger"], bold=True)
            self.cancel_skill_button.draw(surface)
            return

        if self.battle_action_mode == "relocate":
            draw_text(surface, "位移：点击己方空位", (rect.x + 18, action_label_y), size=16, color=COLORS["info"], bold=True)
        elif pending_followup is not None:
            remaining = session.current_followup_remaining_attacks()
            label = f"继续攻击：剩余 {remaining} 次" if remaining > 1 else "第二次攻击：点击红框敌方"
            draw_text(surface, label, (rect.x + 18, action_label_y), size=15, color=COLORS["danger"], bold=True)
        elif self.battle_action_mode == "attack":
            draw_text(surface, "攻击模式：点击红框敌方", (rect.x + 18, action_label_y), size=16, color=COLORS["danger"], bold=True)
        else:
            draw_text(surface, "可执行移动", (rect.x + 18, action_label_y), size=18, color=COLORS["muted"], bold=True)

        action_buttons = self._layout_battle_action_buttons(self._visible_battle_action_buttons())
        if not action_buttons:
            draw_text(surface, "暂无可执行操作", (action_area.x, action_area.y + 8), size=16, color=COLORS["muted"])
            return

        previous_clip = surface.get_clip()
        surface.set_clip(action_area)
        for button in action_buttons:
            if button.rect.colliderect(action_area):
                button.draw(surface)
        surface.set_clip(previous_clip)
        content_height = self._battle_action_content_height(action_buttons)
        if content_height > action_area.height:
            self._draw_scrollbar(surface, action_area, content_height, self.battle_action_scroll_offset)

    def _draw_battle_log(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        draw_text(surface, "战斗日志", (rect.x + 18, rect.y + 12), size=20, bold=True)
        draw_text(surface, "滚动 / 点击打开", (rect.right - 128, rect.y + 16), size=13, color=COLORS["muted"])
        lines = self.battle_log if self.battle_log else [self.message]
        log_rect = pygame.Rect(rect.x + 18, rect.y + 38, rect.width - 36, rect.height - 48)
        content_height = self._battle_log_content_height(lines, log_rect.width)
        max_offset = max(0, content_height - log_rect.height)
        self.battle_log_scroll_offset = max(0, min(self.battle_log_scroll_offset, max_offset))

        previous_clip = surface.get_clip()
        surface.set_clip(log_rect)
        y = log_rect.y - self.battle_log_scroll_offset
        for line in lines:
            row_height = self._battle_log_row_height(line, log_rect.width, size=14, line_height=18)
            row_rect = pygame.Rect(log_rect.x - 4, y - 1, log_rect.width - 8, row_height)
            if row_rect.bottom >= log_rect.y and row_rect.y <= log_rect.bottom:
                draw_wrapped_text(surface, line, (log_rect.x, y), log_rect.width - 16, size=14, color=COLORS["muted"], line_height=18)
            y += row_height
            if y > log_rect.bottom + 80:
                break
        surface.set_clip(previous_clip)

        if content_height > log_rect.height:
            self._draw_scrollbar(surface, log_rect, content_height, self.battle_log_scroll_offset)

    def _battle_log_row_height(self, line: str, width: int, *, size: int = 14, line_height: int = 18) -> int:
        font = get_font(size)
        return max(line_height + 5, len(wrap_text(line, font, width - 16)) * line_height + 5)

    def _battle_log_content_height(
        self,
        lines: list[str],
        width: int,
        *,
        size: int = 14,
        line_height: int = 18,
        row_gap: int = 0,
    ) -> int:
        return sum(
            self._battle_log_row_height(line, width, size=size, line_height=line_height) + row_gap
            for line in lines
        )

    def _handle_battle_log_click(self, position: tuple[int, int]) -> None:
        self.battle_log_overlay_open = True
        self.battle_log_overlay_scroll_offset = 0

    def _draw_battle_log_overlay(self, surface: pygame.Surface) -> None:
        if not self.battle_log_overlay_open:
            return

        lines = self.battle_log if self.battle_log else [self.message]
        overlay_lines = [f"{index}. {line}" for index, line in enumerate(lines, start=1)]
        rect = self._battle_log_overlay_rect()
        pygame.draw.rect(surface, COLORS["shadow"], rect.move(8, 8), border_radius=8)
        pygame.draw.rect(surface, COLORS["surface"], rect, border_radius=8)
        pygame.draw.rect(surface, COLORS["accent"], rect, 2, border_radius=8)
        draw_text(surface, "战斗日志", (rect.x + 22, rect.y + 18), size=25, bold=True)
        draw_text(surface, "滚轮翻阅 / 点击外侧关闭", (rect.right - 220, rect.y + 24), size=15, color=COLORS["muted"])

        log_rect = pygame.Rect(rect.x + 22, rect.y + 62, rect.width - 44, rect.height - 86)
        content_height = self._battle_log_content_height(
            overlay_lines,
            log_rect.width,
            size=15,
            line_height=21,
            row_gap=2,
        )
        max_offset = max(0, content_height - log_rect.height)
        self.battle_log_overlay_scroll_offset = max(0, min(self.battle_log_overlay_scroll_offset, max_offset))

        previous_clip = surface.get_clip()
        surface.set_clip(log_rect)
        y = log_rect.y - self.battle_log_overlay_scroll_offset
        for row_text in overlay_lines:
            row_height = self._battle_log_row_height(row_text, log_rect.width, size=15, line_height=21)
            if y + row_height >= log_rect.y and y <= log_rect.bottom:
                draw_wrapped_text(surface, row_text, (log_rect.x, y), log_rect.width - 16, size=15, color=COLORS["muted"], line_height=21)
            y += row_height + 2
            if y > log_rect.bottom + 120:
                break
        surface.set_clip(previous_clip)

        if content_height > log_rect.height:
            self._draw_scrollbar(surface, log_rect, content_height, self.battle_log_overlay_scroll_offset)

    def _draw_battle_detail_view(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        session: BattleSession,
        selected: tuple[int, Character],
    ) -> None:
        player_id, character = selected
        items = self._battle_detail_items(player_id, character, session)
        content_height = self._battle_detail_content_height(items, rect.width)
        max_offset = max(0, content_height - rect.height)
        self.battle_detail_scroll_offset = max(0, min(self.battle_detail_scroll_offset, max_offset))

        previous_clip = surface.get_clip()
        surface.set_clip(rect)
        y = rect.y - self.battle_detail_scroll_offset
        for text, size, color, bold in items:
            if text == "":
                y += 6
                continue
            if y > rect.bottom:
                break
            y = draw_wrapped_text(surface, text, (rect.x, y), rect.width - 10, size=size, color=color, bold=bold, line_height=int(size * 1.32))
            y += 3
        surface.set_clip(previous_clip)

        if content_height > rect.height:
            self._draw_scrollbar(surface, rect, content_height, self.battle_detail_scroll_offset)

    def _battle_detail_items(
        self,
        player_id: int,
        character: Character,
        session: BattleSession,
    ) -> list[tuple[str, int, tuple[int, int, int] | None, bool]]:
        owner = self.game_state.player(player_id)
        position_text = self._position_label(character.position) if character.position is not None else "未上阵"
        status_text = self._battle_status_text(player_id, character) or "-"
        moves = session.remaining_move_count(player_id, character.id)
        effective_attack = session.effective_attack((player_id, character.id))
        attack_text = f"攻击 {effective_attack}"
        if effective_attack != character.attack:
            attack_text += f"（基础 {character.attack}）"
        faction_text = "、".join(character.factions) if character.factions else "无"
        items: list[tuple[str, int, tuple[int, int, int] | None, bool]] = [
            (character.name, 22, None, True),
            (f"{owner.name} / {character.job.name} / {position_text}", 14, COLORS["accent"], False),
            (f"生命 {character.current_health}/{character.max_health}   {attack_text}   护甲 {character.armor}   本轮移动 {moves}", 14, None, False),
            (f"阵营：{faction_text}", 14, COLORS["muted"], False),
            (f"状态：{status_text}", 14, COLORS["muted"], False),
        ]

        blockers = session.blocked_actor_names_before_choice(player_id, character.id)
        if blockers and session.current_player_id == player_id:
            items.append((f"顺序限制：需先处理 {'、'.join(blockers)}", 13, COLORS["danger"], False))

        items.extend(
            [
                ("", 0, None, False),
                ("职业效果", 15, None, True),
                (character.job.description, 13, COLORS["muted"], False),
                ("", 0, None, False),
                ("角色被动技能", 15, None, True),
                (self._passive_description(character), 13, COLORS["muted"], False),
                ("", 0, None, False),
                ("角色主动技能", 15, None, True),
            ]
        )

        if character.active_skills:
            for skill in character.active_skills:
                items.append((self._active_skill_description(skill), 13, COLORS["muted"], False))
        else:
            items.append(("无", 13, COLORS["muted"], False))

        if character.status_effect_ids:
            items.extend([("", 0, None, False), ("状态效果", 15, None, True)])
            for effect_id in sorted(character.status_effect_ids):
                effect = EFFECTS_BY_ID.get(effect_id)
                if effect is None:
                    items.append((effect_display_name(effect_id), 13, COLORS["muted"], False))
                elif effect_id == "shield":
                    stacks = session.shield_stack_count((player_id, character.id))
                    stack_text = f"（{stacks}层）" if stacks > 1 else ""
                    items.append((f"{effect.name}{stack_text}：{effect.description}", 13, COLORS["muted"], False))
                else:
                    items.append((f"{effect.name}：{effect.description}", 13, COLORS["muted"], False))

        return items

    def _passive_description(self, character: Character) -> str:
        description = character.passive_description.strip()
        if not description:
            return "无"
        return description

    def _active_skill_description(self, skill) -> str:
        return active_skill_display_text(skill)

    def _battle_detail_content_height(self, items: list[tuple[str, int, tuple[int, int, int] | None, bool]], width: int) -> int:
        height = 0
        for text, size, _color, bold in items:
            if text == "":
                height += 6
                continue
            font = get_font(size, bold=bold)
            height += len(wrap_text(text, font, width - 10)) * int(size * 1.32) + 3
        return height

    def _draw_scrollbar(self, surface: pygame.Surface, rect: pygame.Rect, content_height: int, scroll_offset: int) -> None:
        if content_height <= rect.height:
            return

        track = pygame.Rect(rect.right - 5, rect.y, 4, rect.height)
        thumb_height = max(28, int(rect.height * rect.height / content_height))
        max_offset = content_height - rect.height
        thumb_y = rect.y + int((rect.height - thumb_height) * scroll_offset / max_offset)
        thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_height)
        pygame.draw.rect(surface, COLORS["background"], track, border_radius=2)
        pygame.draw.rect(surface, COLORS["border"], thumb, border_radius=2)

    def _battle_order_text(self, session: BattleSession, player_id: int) -> str:
        order = session.move_orders[player_id]
        if not order:
            return "顺序：尚未形成"

        names = [self.game_state.player(player_id).get_character(character_id).name for character_id in order]
        text = "顺序：" + "-".join(names)
        if len(text) > 16:
            text = text[:15] + "..."
        return text

    def _draw_final_formation(self, surface: pygame.Surface, player_id: int, rect: pygame.Rect) -> None:
        player = self.game_state.player(player_id)
        draw_text(surface, player.name, (rect.x + 24, rect.y + 22), size=27, bold=True)

        for position, character_id in sorted(
            player.formation.items(),
            key=lambda item: (item[0].row, item[0].column.value),
        ):
            character = player.get_character(character_id)
            label = f"{self._position_label(position)}：{character.name} / {character.job.name}"
            draw_text(surface, label, (rect.x + 28, rect.y + 76 + position.row * 92 + self._column_offset(position)), size=21)

    def _draw_character_pick_marker(self, surface: pygame.Surface, button: Button) -> None:
        character_id = getattr(button, "character_id")
        if not self.draft_session.is_character_selected(character_id):
            return

        marker_rect = pygame.Rect(button.rect.right - 56, button.rect.top + 8, 42, 24)
        pygame.draw.rect(surface, COLORS["accent_dark"], marker_rect, border_radius=6)
        draw_text(surface, "已选", (marker_rect.x + 6, marker_rect.y + 2), size=16)

    def _draw_draft_job_filters(self, surface: pygame.Surface) -> None:
        for button in self.draft_job_filter_buttons:
            active = getattr(button, "job_id") == self.draft_job_filter_id
            fill_color = COLORS["accent_dark"] if active else COLORS["surface_alt"]
            border_color = COLORS["accent"] if active else COLORS["border"]
            text_color = COLORS["text"] if active else COLORS["muted"]
            pygame.draw.rect(surface, fill_color, button.rect, border_radius=8)
            pygame.draw.rect(surface, border_color, button.rect, 2, border_radius=8)
            text_surface = button.font.render(button.text, True, text_color)
            text_rect = text_surface.get_rect(center=button.rect.center)
            surface.blit(text_surface, text_rect)

    def _draw_formation_character_marker(self, surface: pygame.Surface, button: Button) -> None:
        session = self._ensure_formation_session()
        player = session.current_player
        character_id = getattr(button, "character_id")
        character = player.get_character(character_id)

        if character_id == self.selected_formation_character_id:
            pygame.draw.rect(surface, COLORS["accent"], button.rect, 3, border_radius=8)

        if character.position is None:
            return

        marker_rect = pygame.Rect(button.rect.right - 56, button.rect.top + 9, 42, 22)
        pygame.draw.rect(surface, COLORS["accent_dark"], marker_rect, border_radius=6)
        draw_text(surface, "已放", (marker_rect.x + 6, marker_rect.y + 1), size=15)

    def _draw_formation_slot(self, surface: pygame.Surface, button: Button) -> None:
        session = self._ensure_formation_session()
        player = session.current_player
        position = getattr(button, "position")
        character = player.character_at(position)

        border_color = COLORS["border"]
        if character is not None and character.id == self.selected_formation_character_id:
            border_color = COLORS["accent"]

        pygame.draw.rect(surface, COLORS["surface_alt"], button.rect, border_radius=8)
        pygame.draw.rect(surface, border_color, button.rect, 3 if border_color == COLORS["accent"] else 2, border_radius=8)

        row_label = f"第{position.row + 1}行 {self._column_label(position.column)}"
        draw_text(surface, row_label, (button.rect.x + 12, button.rect.y + 10), size=17, color=COLORS["muted"])

        if character is None:
            draw_text(surface, "空", (button.rect.x + 14, button.rect.y + 42), size=24, color=COLORS["muted"])
        else:
            draw_text(surface, character.name, (button.rect.x + 14, button.rect.y + 36), size=24, bold=True)

    def _draw_player_pick_panel(self, surface: pygame.Surface, player_id: int, rect: pygame.Rect) -> None:
        player = self.game_state.player(player_id)
        border_color = COLORS["accent"] if player_id == self.draft_session.current_player_id else COLORS["border"]

        pygame.draw.rect(surface, COLORS["surface_alt"], rect, border_radius=8)
        pygame.draw.rect(surface, border_color, rect, 2, border_radius=8)

        draw_text_fit(
            surface,
            f"{player.name} 已选 {len(player.selected_characters)}/6",
            (rect.x + 16, rect.y + 14),
            rect.width - 32,
            size=22,
            bold=True,
        )

        names = [character.name for character in player.selected_characters]
        for index in range(6):
            row_y = rect.y + 54 + index * 23
            label = names[index] if index < len(names) else "-"
            color = COLORS["text"] if index < len(names) else COLORS["muted"]
            draw_text_fit(surface, label, (rect.x + 18, row_y), rect.width - 36, size=17, color=color)

    def _phase_status_text(self) -> str:
        if self.game_state.phase == GamePhase.FINISHED:
            if self.game_state.winner_player_id is None:
                return "游戏结束"
            return f"游戏结束：{self.game_state.player(self.game_state.winner_player_id).name} 获胜"

        if self.game_state.phase == GamePhase.BATTLE:
            session = self._ensure_battle_session()
            if session.pending_start_order_choice_player_id is not None:
                choice_player = self.game_state.player(session.pending_start_order_choice_player_id)
                return f"对战阶段：{choice_player.name} 选择先后手"
            first_player = self.game_state.player(session.first_player_id)
            current_player_id = session.current_player_id
            if current_player_id is None:
                return f"对战阶段：第 {self.game_state.round_number} 轮，先手 {first_player.name}"
            current_player = self.game_state.player(current_player_id)
            return f"对战阶段：第 {self.game_state.round_number} 轮，当前 {current_player.name}，先手 {first_player.name}"

        if self.game_state.phase == GamePhase.FORMATION:
            session = self._ensure_formation_session()
            player = session.current_player
            return f"当前 {player.name} 排阵：选择角色后点击阵位，至少放置 1 名角色即可确认。"

        current_player_id = self.draft_session.current_player_id
        if current_player_id is None:
            return "选角阶段"

        current_player = self.game_state.player(current_player_id)
        first_player = self.game_state.player(self.draft_session.first_player_id)
        remaining = self.draft_session.current_step_remaining_picks
        return f"选角阶段：当前 {current_player.name}，本段剩余 {remaining} 个；先手 {first_player.name}"

    def _build_initial_message(self) -> str:
        first_player = self.game_state.player(self.draft_session.first_player_id)
        return f"{first_player.name} 获得选角先手"

    def _position_label(self, position: Position) -> str:
        return f"第{position.row + 1}行{self._column_label(position.column)}"

    def _column_label(self, column: FormationColumn) -> str:
        if column == FormationColumn.FRONT:
            return "前排"
        return "后排"

    def _column_offset(self, position: Position) -> int:
        if position.column == FormationColumn.FRONT:
            return 34
        return 0
