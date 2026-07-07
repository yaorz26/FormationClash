import pygame

from src.config import FONT_CANDIDATES


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    for font_name in FONT_CANDIDATES:
        font = pygame.font.SysFont(font_name, size, bold=bold)
        if font is not None:
            return font
    return pygame.font.Font(None, size)
