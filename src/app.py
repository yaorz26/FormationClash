import pygame

from src.config import APP_TITLE, FPS, WINDOW_SIZE
from src.ui.encyclopedia_screen import EncyclopediaScreen
from src.ui.game_screen import GameScreen
from src.ui.home_screen import HomeScreen
from src.ui.screen_manager import ScreenManager
from src.ui.settings_screen import SettingsScreen


class GameApp:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption(APP_TITLE)

        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.screen_manager = ScreenManager()
        self._register_screens()

    def _register_screens(self) -> None:
        self.screen_manager.register("home", HomeScreen(self.screen_manager))
        self.screen_manager.register("encyclopedia", EncyclopediaScreen(self.screen_manager))
        self.screen_manager.register("game", GameScreen(self.screen_manager))
        self.screen_manager.register("settings", SettingsScreen(self.screen_manager))
        self.screen_manager.switch_to("home")

    def run(self) -> None:
        while self.running:
            delta_seconds = self.clock.tick(FPS) / 1000

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    self.screen_manager.handle_event(event)

            self.screen_manager.update(delta_seconds)
            self.screen_manager.draw(self.screen)
            pygame.display.flip()

        pygame.quit()
