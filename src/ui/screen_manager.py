from typing import Protocol

import pygame


class Screen(Protocol):
    def handle_event(self, event: pygame.event.Event) -> None:
        ...

    def update(self, delta_seconds: float) -> None:
        ...

    def draw(self, surface: pygame.Surface) -> None:
        ...


class ScreenManager:
    def __init__(self) -> None:
        self._screens: dict[str, Screen] = {}
        self._current_name = ""

    def register(self, name: str, screen: Screen) -> None:
        self._screens[name] = screen

    def switch_to(self, name: str) -> None:
        if name not in self._screens:
            raise KeyError(f"Unknown screen: {name}")
        self._current_name = name

    def get_screen(self, name: str) -> Screen:
        if name not in self._screens:
            raise KeyError(f"Unknown screen: {name}")
        return self._screens[name]

    @property
    def current_screen(self) -> Screen:
        return self._screens[self._current_name]

    def handle_event(self, event: pygame.event.Event) -> None:
        self.current_screen.handle_event(event)

    def update(self, delta_seconds: float) -> None:
        self.current_screen.update(delta_seconds)

    def draw(self, surface: pygame.Surface) -> None:
        self.current_screen.draw(surface)
