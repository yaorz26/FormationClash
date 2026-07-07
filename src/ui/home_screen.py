import pygame

from src.config import COLORS, WINDOW_HEIGHT, WINDOW_WIDTH
from src.ui.components import Button, draw_text
from src.ui.screen_manager import ScreenManager


class HomeScreen:
    def __init__(self, screen_manager: ScreenManager) -> None:
        self.screen_manager = screen_manager
        button_width = 280
        button_height = 64
        start_x = (WINDOW_WIDTH - button_width) // 2
        start_y = 232
        gap = 94

        self.buttons = [
            Button(
                pygame.Rect(start_x, start_y, button_width, button_height),
                "开始游戏",
                lambda: self.screen_manager.switch_to("game"),
            ),
            Button(
                pygame.Rect(start_x, start_y + gap, button_width, button_height),
                "百科大全",
                self.open_encyclopedia,
            ),
            Button(
                pygame.Rect(start_x, start_y + gap * 2, button_width, button_height),
                "设置",
                lambda: self.screen_manager.switch_to("settings"),
            ),
        ]

    def open_encyclopedia(self) -> None:
        encyclopedia = self.screen_manager.get_screen("encyclopedia")
        if hasattr(encyclopedia, "set_return_screen"):
            encyclopedia.set_return_screen("home", "返回主页")
        self.screen_manager.switch_to("encyclopedia")

    def handle_event(self, event: pygame.event.Event) -> None:
        for button in self.buttons:
            button.handle_event(event)

    def update(self, delta_seconds: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(COLORS["background"])

        draw_text(surface, "Fight", (48, 24), size=34, bold=True)
        draw_text(surface, "双人选角、布阵与回合对战", (150, 36), size=18, color=COLORS["muted"])
        pygame.draw.line(surface, COLORS["border"], (48, 76), (WINDOW_WIDTH - 48, 76), 1)

        panel_rect = pygame.Rect(300, 174, 520, 392)
        pygame.draw.rect(surface, COLORS["surface"], panel_rect, border_radius=8)
        pygame.draw.rect(surface, COLORS["border"], panel_rect, 2, border_radius=8)

        for button in self.buttons:
            button.draw(surface)

        draw_text(
            surface,
            "可玩流程：选角 / 排阵 / 对战 / 百科",
            (32, WINDOW_HEIGHT - 46),
            size=20,
            color=COLORS["muted"],
        )
