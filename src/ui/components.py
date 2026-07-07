from collections.abc import Callable

import pygame

from src.assets import get_font
from src.config import COLORS


class Button:
    def __init__(
        self,
        rect: pygame.Rect,
        text: str,
        on_click: Callable[[], None],
        *,
        font_size: int = 28,
        enabled: bool = True,
    ) -> None:
        self.rect = rect
        self.text = text
        self.on_click = on_click
        self.font = get_font(font_size, bold=True)
        self.hovered = False
        self.enabled = enabled

    def handle_event(self, event: pygame.event.Event) -> None:
        if not self.enabled:
            self.hovered = False
            return

        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.on_click()

    def draw(self, surface: pygame.Surface) -> None:
        if self.enabled:
            color = COLORS["accent"] if self.hovered else COLORS["surface_alt"]
            border_color = COLORS["accent"] if self.hovered else COLORS["border"]
            text_color = COLORS["text"]
        else:
            color = COLORS["surface"]
            border_color = COLORS["border"]
            text_color = COLORS["muted"]

        shadow_rect = self.rect.move(0, 3)
        pygame.draw.rect(surface, COLORS["shadow"], shadow_rect, border_radius=8)
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=8)

        text_surface = self.font.render(self.text, True, text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)


def draw_text(
    surface: pygame.Surface,
    text: str,
    position: tuple[int, int],
    *,
    size: int = 24,
    color: tuple[int, int, int] | None = None,
    bold: bool = False,
) -> pygame.Rect:
    font = get_font(size, bold=bold)
    text_surface = font.render(text, True, color or COLORS["text"])
    text_rect = text_surface.get_rect(topleft=position)
    surface.blit(text_surface, text_rect)
    return text_rect


def truncate_text(text: str, font: pygame.font.Font, max_width: int) -> str:
    if font.size(text)[0] <= max_width:
        return text

    suffix = "..."
    available_width = max(0, max_width - font.size(suffix)[0])
    trimmed = ""
    for character in text:
        candidate = trimmed + character
        if font.size(candidate)[0] > available_width:
            break
        trimmed = candidate
    return trimmed + suffix if trimmed else suffix


def draw_text_fit(
    surface: pygame.Surface,
    text: str,
    position: tuple[int, int],
    max_width: int,
    *,
    size: int = 24,
    color: tuple[int, int, int] | None = None,
    bold: bool = False,
) -> pygame.Rect:
    font = get_font(size, bold=bold)
    fitted_text = truncate_text(text, font, max_width)
    text_surface = font.render(fitted_text, True, color or COLORS["text"])
    text_rect = text_surface.get_rect(topleft=position)
    surface.blit(text_surface, text_rect)
    return text_rect


def wrap_text(text: str, font: pygame.font.Font, max_width: int, max_lines: int | None = None) -> list[str]:
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


def draw_wrapped_text(
    surface: pygame.Surface,
    text: str,
    position: tuple[int, int],
    max_width: int,
    *,
    size: int = 24,
    color: tuple[int, int, int] | None = None,
    bold: bool = False,
    line_height: int | None = None,
    max_lines: int | None = None,
) -> int:
    font = get_font(size, bold=bold)
    y = position[1]
    for line in wrap_text(text, font, max_width, max_lines):
        draw_text(surface, line, (position[0], y), size=size, color=color, bold=bold)
        y += line_height or int(size * 1.35)
    return y


def draw_centered_text(
    surface: pygame.Surface,
    text: str,
    center: tuple[int, int],
    *,
    size: int = 24,
    color: tuple[int, int, int] | None = None,
    bold: bool = False,
) -> pygame.Rect:
    font = get_font(size, bold=bold)
    text_surface = font.render(text, True, color or COLORS["text"])
    text_rect = text_surface.get_rect(center=center)
    surface.blit(text_surface, text_rect)
    return text_rect
