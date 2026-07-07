from __future__ import annotations

from dataclasses import dataclass

import pygame

from src import user_settings
from src.assets import get_font
from src.config import COLORS, WINDOW_HEIGHT, WINDOW_WIDTH
from src.core import DamageEvent, GamePhase, Position, SkillKind


ATTACK_ANIMATION_DURATION = 0.72
ATTACK_FLASH_DURATION = 0.34
ATTACK_DAMAGE_NUMBER_DELAY = 0.26


@dataclass
class HealthChangeEvent:
    player_id: int
    character_id: str
    amount: int
    critical: bool = False


@dataclass
class AttackAnimation:
    source_key: tuple[int, str] | None
    health_events: tuple[HealthChangeEvent, ...]
    show_slash: bool = False
    elapsed: float = 0.0

    @property
    def damage_events(self) -> tuple[DamageEvent, ...]:
        return tuple(
            DamageEvent(event.player_id, event.character_id, -event.amount, critical=event.critical)
            for event in self.health_events
            if event.amount < 0
        )


class GameScreenAnimationMixin:
    def _skill_should_animate_attack(self, skill) -> bool:
        base_skill_id = skill.id.split("__copy_", 1)[0]
        return skill.kind == SkillKind.ATTACK or base_skill_id in {"lang_qi_flurry", "artisan_overcharge"}

    def _battle_animation_active(self) -> bool:
        return self.active_attack_animation is not None or bool(self.attack_animation_queue)

    def _battle_health_snapshot(self) -> dict[tuple[int, str], int]:
        snapshot: dict[tuple[int, str], int] = {}
        for player_id, player in self.game_state.players.items():
            for character in player.selected_characters:
                if character.position is not None:
                    snapshot[(player_id, character.id)] = character.current_health
        return snapshot

    def _queue_health_change_animation(
        self,
        source_key: tuple[int, str] | None,
        before_health: dict[tuple[int, str], int],
        *,
        show_slash: bool = False,
        critical_damage_keys: set[tuple[int, str]] | None = None,
    ) -> None:
        if not user_settings.animations_enabled:
            return
        if self.game_state.phase != GamePhase.BATTLE:
            return
        if show_slash and (source_key is None or self._battle_character_position(source_key[0], source_key[1]) is None):
            show_slash = False

        health_events = self._health_change_events(before_health, critical_damage_keys or set())
        if not health_events and not show_slash:
            return
        animation = AttackAnimation(source_key=source_key, health_events=health_events, show_slash=show_slash)
        if self.active_attack_animation is None:
            self.active_attack_animation = animation
        else:
            self.attack_animation_queue.append(animation)

    def _health_change_events(
        self,
        before_health: dict[tuple[int, str], int],
        critical_damage_keys: set[tuple[int, str]],
    ) -> tuple[HealthChangeEvent, ...]:
        events: list[HealthChangeEvent] = []
        after_health = self._battle_health_snapshot()
        for key, before in before_health.items():
            if key not in after_health:
                continue
            amount = after_health[key] - before
            if amount == 0:
                continue
            player_id, character_id = key
            if self._battle_character_position(player_id, character_id) is None:
                continue
            events.append(
                HealthChangeEvent(
                    player_id=player_id,
                    character_id=character_id,
                    amount=amount,
                    critical=amount < 0 and key in critical_damage_keys,
                )
            )
        return tuple(events)

    def _battle_character_position(self, player_id: int, character_id: str) -> Position | None:
        try:
            character = self.game_state.player(player_id).get_character(character_id)
        except KeyError:
            return None
        return character.position

    def _update_battle_animations(self, delta_seconds: float) -> None:
        if not user_settings.animations_enabled:
            self.active_attack_animation = None
            self.attack_animation_queue = []
            return

        if self.active_attack_animation is None:
            if self.attack_animation_queue:
                self.active_attack_animation = self.attack_animation_queue.pop(0)
            return

        self.active_attack_animation.elapsed += delta_seconds
        if self.active_attack_animation.elapsed < ATTACK_ANIMATION_DURATION:
            return

        if self.attack_animation_queue:
            self.active_attack_animation = self.attack_animation_queue.pop(0)
        else:
            self.active_attack_animation = None

    def _draw_battle_animations(self, surface: pygame.Surface) -> None:
        animation = self.active_attack_animation
        if animation is None:
            return

        progress = max(0.0, min(animation.elapsed / ATTACK_ANIMATION_DURATION, 1.0))
        if animation.show_slash and animation.source_key is not None:
            self._draw_attack_slash(surface, animation.source_key, progress)
        for health_event in animation.health_events:
            self._draw_health_flash(surface, health_event, animation.elapsed)
            self._draw_health_change_number(surface, health_event, animation.elapsed)

    def _draw_attack_slash(
        self,
        surface: pygame.Surface,
        source_key: tuple[int, str],
        progress: float,
    ) -> None:
        if progress > 0.46:
            return
        position = self._battle_character_position(source_key[0], source_key[1])
        if position is None:
            return

        rect = self._battle_card_rect(source_key[0], position)
        fade = 1.0 - progress / 0.46
        alpha = max(0, min(230, int(230 * fade)))
        if alpha <= 0:
            return

        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        center_y = rect.centery
        if source_key[0] == 1:
            base_x = rect.right + 14
            main_start = (base_x - 12, center_y - 28)
            main_end = (base_x + 30, center_y + 20)
            glow_start = (base_x - 2, center_y - 32)
            glow_end = (base_x + 22, center_y + 18)
        else:
            base_x = rect.x - 14
            main_start = (base_x + 12, center_y - 28)
            main_end = (base_x - 30, center_y + 20)
            glow_start = (base_x + 2, center_y - 32)
            glow_end = (base_x - 22, center_y + 18)

        pygame.draw.line(overlay, (255, 246, 198, alpha), main_start, main_end, 7)
        pygame.draw.line(overlay, (232, 174, 64, int(alpha * 0.82)), glow_start, glow_end, 4)
        pygame.draw.line(
            overlay,
            (255, 255, 255, int(alpha * 0.72)),
            (main_start[0], main_start[1] + 8),
            (main_end[0], main_end[1] - 8),
            2,
        )
        surface.blit(overlay, (0, 0))

    def _draw_health_flash(self, surface: pygame.Surface, health_event: HealthChangeEvent, elapsed: float) -> None:
        if health_event.amount >= 0:
            return
        if elapsed > ATTACK_FLASH_DURATION:
            return
        position = self._battle_character_position(health_event.player_id, health_event.character_id)
        if position is None:
            return

        rect = self._battle_card_rect(health_event.player_id, position)
        fade = 1.0 - elapsed / ATTACK_FLASH_DURATION
        alpha = max(0, min(130, int(130 * fade)))
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (214, 88, 66, alpha), rect, border_radius=8)
        pygame.draw.rect(overlay, (255, 218, 204, min(220, alpha + 60)), rect.inflate(4, 4), 3, border_radius=10)
        surface.blit(overlay, (0, 0))

    def _draw_health_change_number(self, surface: pygame.Surface, health_event: HealthChangeEvent, elapsed: float) -> None:
        if elapsed < ATTACK_DAMAGE_NUMBER_DELAY:
            return
        position = self._battle_character_position(health_event.player_id, health_event.character_id)
        if position is None:
            return

        number_duration = ATTACK_ANIMATION_DURATION - ATTACK_DAMAGE_NUMBER_DELAY
        progress = max(0.0, min((elapsed - ATTACK_DAMAGE_NUMBER_DELAY) / number_duration, 1.0))
        alpha = max(0, min(255, int(255 * (1.0 - progress))))
        if alpha <= 0:
            return

        rect = self._battle_card_rect(health_event.player_id, position)
        font = get_font(21, bold=True)
        text = f"+{health_event.amount}" if health_event.amount > 0 else str(health_event.amount)
        critical_color = (255, 232, 64)
        color = COLORS["success"] if health_event.amount > 0 else (critical_color if health_event.critical else COLORS["danger"])
        text_surface = font.render(text, True, color)
        text_surface.set_alpha(alpha)
        y = rect.y + 16 - int(28 * progress)
        if health_event.player_id == 1:
            x = rect.right + 8
        else:
            x = rect.x - text_surface.get_width() - 8
        surface.blit(text_surface, (x, y))
        if health_event.critical:
            critical_font = get_font(17, bold=True)
            critical_surface = critical_font.render("暴击", True, critical_color)
            critical_surface.set_alpha(alpha)
            critical_y = y - 22
            if health_event.player_id == 1:
                critical_x = rect.right + 8
            else:
                critical_x = rect.x - critical_surface.get_width() - 8
            surface.blit(critical_surface, (critical_x, critical_y))
