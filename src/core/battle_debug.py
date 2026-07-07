from __future__ import annotations

from collections.abc import Sequence

from src.core.battle_errors import BattleError
from src.core.battle_results import (
    AttackResolution,
    AttackResult,
    DamageResult,
    DeathTrigger,
    DeathTriggerResult,
    EndRoundResult,
    RelocateResult,
    SecondHandResult,
    SkillResult,
    SkipResult,
    SummonRequest,
    SummonResult,
    ThawResult,
)
from src.core.models import ActiveSkill, Character, FormationColumn, GamePhase, Position, SkillKind, SkillTarget
from src.core.rules import effect_display_name, is_adverse_status_effect


class BattleDebugMixin:
    def debug_clear_position(self, player_id: int, position: Position) -> Character | None:
        player = self.game_state.player(player_id)
        character_id = player.formation.pop(position, None)
        if character_id is None:
            return None

        character = player.get_character(character_id)
        character.clear_position()
        self.remaining_moves[(player_id, character.id)] = 0
        self.pending_revivals.discard((player_id, character.id))
        self.round_skipped_ids[player_id].discard(character.id)
        self.last_damage_sources.pop((player_id, character.id), None)
        self._clear_tracking_for_character((player_id, character.id))
        self._refresh_aura_health_bonuses()
        self._check_winner()
        return character

    def debug_replace_position(self, player_id: int, position: Position, character_definition_id: str) -> Character:
        self.debug_clear_position(player_id, position)

        character = self._create_summoned_character(character_definition_id, player_id)
        player = self.game_state.player(player_id)
        player.add_character(character)
        player.place_character(character.id, position)
        self.remaining_moves[(player_id, character.id)] = character.default_move_count
        self.round_skipped_ids[player_id].discard(character.id)
        self._refresh_aura_health_bonuses()
        if self.current_player_id is None and self.game_state.phase == GamePhase.BATTLE:
            self.game_state.current_turn_player_id = self._next_player_with_moves(player_id)
        return character

    def debug_reset_move_orders(self) -> None:
        self.move_orders = {player_id: [] for player_id in self.game_state.players}
        self.round_resolved_order_slots = {player_id: set() for player_id in self.game_state.players}
        self.round_skipped_ids = {player_id: set() for player_id in self.game_state.players}

    def debug_apply_effect(self, player_id: int, character_id: str, effect_id: str) -> bool:
        character = self.game_state.player(player_id).get_character(character_id)
        if not character.is_alive or character.position is None:
            return False
        return self.apply_status_effect(player_id, character_id, effect_id)

    def debug_apply_debuff(self, player_id: int, character_id: str, effect_id: str) -> bool:
        return self.debug_apply_effect(player_id, character_id, effect_id)

    def debug_apply_buff(self, player_id: int, character_id: str, effect_id: str) -> bool:
        return self.debug_apply_effect(player_id, character_id, effect_id)

    def debug_deal_damage(self, player_id: int, character_id: str, amount: int) -> int:
        if amount <= 0:
            return 0

        character = self.game_state.player(player_id).get_character(character_id)
        if not character.is_alive or character.position is None:
            return 0

        alive_before = self._living_character_keys()
        before_health = character.current_health
        before_armor = character.armor
        character.take_damage(amount)
        self._refresh_aura_health_bonuses()
        defeated_character_keys = self._newly_defeated_keys(alive_before)
        self._queue_death_triggers(defeated_character_keys)
        if not self.pending_death_triggers and not self.pending_summons:
            self._check_winner()
        return max(0, before_health + before_armor - character.current_health - character.armor)

    def debug_heal(self, player_id: int, character_id: str, amount: int) -> int:
        if amount <= 0:
            return 0

        character = self.game_state.player(player_id).get_character(character_id)
        if not character.is_alive or character.position is None:
            return 0

        before_health = character.current_health
        character.heal(amount)
        return character.current_health - before_health

