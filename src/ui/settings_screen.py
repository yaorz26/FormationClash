import pygame

from src.config import COLORS, WINDOW_HEIGHT, WINDOW_WIDTH
from src import user_settings
from src.ui.components import Button, draw_text, draw_text_fit
from src.ui.screen_manager import ScreenManager


class SettingsScreen:
    def __init__(self, screen_manager: ScreenManager) -> None:
        self.screen_manager = screen_manager
        self.back_button = Button(
            pygame.Rect(40, WINDOW_HEIGHT - 88, 180, 52),
            "返回主页",
            lambda: self.screen_manager.switch_to("home"),
            font_size=24,
        )
        self.animation_button = Button(
            pygame.Rect(80, 178, 180, 42),
            "",
            self.toggle_animations,
            font_size=18,
        )
        self.arcanarch_button = Button(
            pygame.Rect(80, 238, 220, 42),
            "",
            self.toggle_arcanarch_in_draft,
            font_size=17,
        )
        self._sync_animation_button_text()
        self._sync_arcanarch_button_text()

    def handle_event(self, event: pygame.event.Event) -> None:
        self.back_button.handle_event(event)
        self.animation_button.handle_event(event)
        self.arcanarch_button.handle_event(event)

    def update(self, delta_seconds: float) -> None:
        self._sync_animation_button_text()
        self._sync_arcanarch_button_text()

    def toggle_animations(self) -> None:
        user_settings.toggle_animations()
        self._sync_animation_button_text()

    def toggle_arcanarch_in_draft(self) -> None:
        user_settings.toggle_arcanarch_in_draft()
        self._sync_arcanarch_button_text()

    def _sync_animation_button_text(self) -> None:
        self.animation_button.text = f"动画：{'开启' if user_settings.animations_enabled else '关闭'}"

    def _sync_arcanarch_button_text(self) -> None:
        state = "显示" if user_settings.show_arcanarch_in_draft else "隐藏"
        self.arcanarch_button.text = f"选角帝法者：{state}"

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(COLORS["background"])

        draw_text(surface, "设置", (48, 24), size=31, bold=True)
        draw_text_fit(surface, "基础选项会在后续阶段逐步接入。", (190, 34), WINDOW_WIDTH - 240, size=18, color=COLORS["muted"])
        pygame.draw.line(surface, COLORS["border"], (48, 76), (WINDOW_WIDTH - 48, 76), 1)

        content_rect = pygame.Rect(48, 96, WINDOW_WIDTH - 96, 526)
        pygame.draw.rect(surface, COLORS["surface"], content_rect, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], content_rect, 2, border_radius=8)

        draw_text(surface, "表现设置", (80, 134), size=28, bold=True)
        self.animation_button.draw(surface)
        draw_text(surface, "关闭后战斗动作将立即结算，不播放刀光和伤害提示。", (286, 188), size=18, color=COLORS["muted"])
        draw_text(surface, "选角设置", (80, 212), size=22, bold=True)
        self.arcanarch_button.draw(surface)
        draw_text(surface, "开启后，新一局选角会加入帝法者；修改器始终显示全部角色。", (320, 248), size=17, color=COLORS["muted"])
        draw_text(surface, "更多音量 / 窗口 / 帧率选项会在后续阶段接入。", (80, 316), size=22, color=COLORS["muted"])

        self.back_button.draw(surface)
