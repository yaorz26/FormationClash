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


class BattleTurnMixin:
    def is_complete(self) -> bool:
        return self.game_state.phase == GamePhase.FINISHED

    @property
    def current_player_id(self) -> int | None:
        return self.game_state.current_turn_player_id

    def current_followup_attack(self) -> tuple[int, str] | None:
        return self.pending_followup_attack

    def current_followup_remaining_attacks(self) -> int:
        return self.pending_followup_remaining_attacks if self.pending_followup_attack is not None else 0

    def current_summon_request(self) -> SummonRequest | None:
        if not self.pending_summons:
            return None
        return self.pending_summons[0]

    def _has_pending_manual_choice(self) -> bool:
        return bool(self.pending_sword_saint_choices or self.pending_chase_choices)

    def available_actors(self, player_id: int) -> list[Character]:
        return [
            character
            for character in self._battle_characters(player_id)
            if self.can_character_move(player_id, character.id)
        ]

    def remaining_move_count(self, player_id: int, character_id: str) -> int:
        return self.remaining_moves.get((player_id, character_id), 0)

    def can_character_move(self, player_id: int, character_id: str) -> bool:
        if self.pending_death_triggers or self.pending_summons:
            return False
        if self._has_pending_manual_choice():
            return False
        if self.pending_followup_attack is not None and self.pending_followup_attack != (player_id, character_id):
            return False
        character = self.game_state.player(player_id).get_character(character_id)
        if not character.is_alive and (player_id, character_id) not in self.pending_revivals:
            return False
        if character.position is None:
            return False
        if self.remaining_move_count(player_id, character_id) <= 0:
            return False
        return self._is_order_legal(player_id, character_id)

    def is_never_moved(self, player_id: int, character_id: str) -> bool:
        return character_id not in self.move_orders[player_id]

    def is_actor_resolved_this_round(self, player_id: int, character_id: str) -> bool:
        return self.remaining_move_count(player_id, character_id) <= 0

    def _is_order_legal(self, player_id: int, character_id: str) -> bool:
        if self._player_ignores_move_order(player_id):
            return True
        slot_index = self._first_unresolved_slot_for_actor(player_id, character_id)
        if slot_index is None:
            return True

        return slot_index == self._order_cursor(player_id)

    def _player_ignores_move_order(self, player_id: int) -> bool:
        for character in self._battle_characters(player_id):
            if "move_order_independent" not in character.effective_passive_effect_ids:
                continue
            if "eternal_effect" not in character.effective_passive_effect_ids and not character.is_alive:
                continue
            if character.has_status_effect("silenced"):
                continue
            return True
        return False

    def blocked_actor_names_before_choice(self, player_id: int, character_id: str) -> tuple[str, ...]:
        character_slot = self._first_unresolved_slot_for_actor(player_id, character_id)
        if character_slot is None:
            return ()

        cursor = self._order_cursor(player_id)
        if character_slot <= cursor:
            return ()

        player = self.game_state.player(player_id)
        blocking_names = [
            player.get_character(blocking_id).name
            for index, blocking_id in enumerate(self.move_orders[player_id][cursor:character_slot], start=cursor)
            if index not in self.round_resolved_order_slots[player_id]
            and self._has_unresolved_order_move(player_id, blocking_id)
        ]
        return tuple(dict.fromkeys(blocking_names))

    def can_skip_move(self, player_id: int, character_id: str) -> bool:
        if self.game_state.phase != GamePhase.BATTLE:
            return False
        if self.current_player_id != player_id:
            return False
        return self.can_character_move(player_id, character_id)

    def can_revive_character(self, player_id: int, character_id: str) -> bool:
        if self.game_state.phase != GamePhase.BATTLE:
            return False
        if self.current_player_id != player_id:
            return False
        if not self._pending_revival_consumes_turn((player_id, character_id)):
            return False
        return self.can_character_move(player_id, character_id)

    def can_end_player_round(self, player_id: int) -> bool:
        return (
            self.game_state.phase == GamePhase.BATTLE
            and self.current_player_id == player_id
            and not self.pending_death_triggers
            and not self.pending_summons
            and not self._has_pending_manual_choice()
            and self.pending_followup_attack is None
        )

    def can_use_second_hand_skill(self, player_id: int) -> bool:
        if self.game_state.phase != GamePhase.BATTLE:
            return False
        if self.pending_death_triggers:
            return False
        if self.pending_summons:
            return False
        if self._has_pending_manual_choice():
            return False
        if self.pending_followup_attack is not None:
            return False
        if self.current_player_id != player_id:
            return False

        player = self.game_state.player(player_id)
        return (
            player.has_second_hand_skill
            and not player.second_hand_skill_used
            and self.second_hand_extra_turn_player_id is None
        )

    def use_second_hand_skill(self, player_id: int) -> SecondHandResult:
        if not self.can_use_second_hand_skill(player_id):
            raise BattleError("Invalid second-hand skill.")

        player = self.game_state.player(player_id)
        player.second_hand_skill_used = True
        self.second_hand_extra_turn_player_id = player_id

        return SecondHandResult(
            player_name=player.name,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
        )

    def can_thaw_character(self, player_id: int, character_id: str) -> bool:
        if self.game_state.phase != GamePhase.BATTLE:
            return False
        if self.pending_death_triggers:
            return False
        if self.pending_summons:
            return False
        if self._has_pending_manual_choice():
            return False
        if self.pending_followup_attack is not None:
            return False
        if self.current_player_id != player_id:
            return False
        if self._pending_revival_consumes_turn((player_id, character_id)):
            return False

        character = self.game_state.player(player_id).get_character(character_id)
        return character.has_status_effect("frozen") and self.can_character_move(player_id, character_id)

    def thaw_character(self, player_id: int, character_id: str) -> ThawResult:
        if not self.can_thaw_character(player_id, character_id):
            raise BattleError("Invalid thaw action.")

        character = self.game_state.player(player_id).get_character(character_id)
        self._begin_tenacity_enemy_action(player_id)
        slot_index = self._record_movement(player_id, character_id)
        character.remove_status_effect("frozen")
        self.remaining_moves[(player_id, character_id)] -= 1
        self._resolve_order_slot(player_id, slot_index)
        self._advance_turn_after_action(player_id)

        return ThawResult(
            actor_name=character.name,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
        )

    def can_relocate_character(self, player_id: int, character_id: str, position: Position | None = None) -> bool:
        if self.game_state.phase != GamePhase.BATTLE:
            return False
        if self.pending_death_triggers or self.pending_summons or self._has_pending_manual_choice() or self.pending_followup_attack is not None:
            return False
        if self.current_player_id != player_id:
            return False

        try:
            character = self.game_state.player(player_id).get_character(character_id)
        except KeyError:
            return False
        if not character.is_alive or character.position is None:
            return False
        if not self._character_has_battle_effect((player_id, character_id), "free_relocate"):
            return False
        if position is None:
            return True
        if position.row not in range(3) or position.column not in (FormationColumn.FRONT, FormationColumn.BACK):
            return False
        return self.game_state.player(player_id).character_at(position) is None

    def relocate_character(self, player_id: int, character_id: str, position: Position) -> RelocateResult:
        if not self.can_relocate_character(player_id, character_id, position):
            raise BattleError("Invalid relocation.")

        player = self.game_state.player(player_id)
        character = player.get_character(character_id)
        from_position = character.position
        if from_position is None:
            raise BattleError("Invalid relocation.")

        player.place_character(character_id, position)
        self._refresh_aura_health_bonuses()

        return RelocateResult(
            actor_name=character.name,
            from_position=from_position,
            to_position=position,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
        )

    def skip_move(self, player_id: int, character_id: str) -> SkipResult:
        if not self.can_skip_move(player_id, character_id):
            raise BattleError("Invalid skip.")

        if self.pending_followup_attack == (player_id, character_id):
            character = self.game_state.player(player_id).get_character(character_id)
            slot_index = self.pending_followup_order_slot
            if slot_index is None:
                raise BattleError("Invalid follow-up attack state.")
            self._finish_attack_move(player_id, character_id, slot_index)
            self._advance_turn_after_action(player_id)
            return SkipResult(
                actor_name=character.name,
                next_player_id=self.current_player_id,
                round_number=self.game_state.round_number,
                events=(),
            )

        character = self.game_state.player(player_id).get_character(character_id)
        events: list[str] = []
        self._begin_tenacity_enemy_action(player_id)
        slot_index = self._record_movement(player_id, character_id)
        if not self._pending_revival_consumes_turn((player_id, character_id)):
            self._revive_if_pending((player_id, character_id), events)
        self.remaining_moves[(player_id, character_id)] -= 1
        self._resolve_order_slot(player_id, slot_index)
        self.round_skipped_ids[player_id].add(character_id)
        self._advance_turn_after_skip(player_id)

        return SkipResult(
            actor_name=character.name,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
            events=tuple(events),
        )

    def revive_character(self, player_id: int, character_id: str) -> SkipResult:
        if not self.can_revive_character(player_id, character_id):
            raise BattleError("Invalid revival.")

        character = self.game_state.player(player_id).get_character(character_id)
        events: list[str] = []
        self._begin_tenacity_enemy_action(player_id)
        slot_index = self._record_movement(player_id, character_id)
        self._revive_if_pending((player_id, character_id), events)
        self.remaining_moves[(player_id, character_id)] -= 1
        self._resolve_order_slot(player_id, slot_index)
        self._advance_turn_after_action(player_id)

        return SkipResult(
            actor_name=character.name,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
            events=tuple(events),
        )

    def end_player_round(self, player_id: int) -> EndRoundResult:
        if not self.can_end_player_round(player_id):
            raise BattleError("Invalid end-round action.")

        player = self.game_state.player(player_id)
        consumed_names: list[str] = []
        for character in self._battle_characters(player_id):
            if character.is_alive and self.remaining_move_count(player_id, character.id) > 0:
                consumed_names.append(character.name)
            self.remaining_moves[(player_id, character.id)] = 0
        self.round_resolved_order_slots[player_id] = set(range(len(self.move_orders[player_id])))
        if self.second_hand_extra_turn_player_id == player_id:
            self.second_hand_extra_turn_player_id = None

        if not self._any_player_has_moves():
            self._start_next_round()
        else:
            opponent_id = self.game_state.opponent_id(player_id)
            self.game_state.current_turn_player_id = self._next_player_with_moves(opponent_id)

        return EndRoundResult(
            player_name=player.name,
            consumed_actor_names=tuple(consumed_names),
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
        )

    def skipped_actor_names_for_choice(self, player_id: int, character_id: str) -> tuple[str, ...]:
        return ()

    def _record_movement(self, player_id: int, character_id: str) -> int:
        cursor = self._order_cursor(player_id)
        slot_index = self._first_unresolved_slot_for_actor(player_id, character_id)

        if slot_index is None:
            self._insert_order_slot(player_id, cursor, character_id)
            return cursor

        if self._player_ignores_move_order(player_id):
            return slot_index
        if slot_index != cursor:
            raise BattleError("Actor does not satisfy movement order.")
        return slot_index

    def _order_cursor(self, player_id: int) -> int:
        self._normalize_round_order(player_id)
        move_order = self.move_orders[player_id]
        resolved_slots = self.round_resolved_order_slots[player_id]

        for index, character_id in enumerate(move_order):
            if index not in resolved_slots:
                return index
        return len(move_order)

    def _normalize_round_order(self, player_id: int) -> None:
        resolved_slots = self.round_resolved_order_slots[player_id]
        for index, character_id in enumerate(self.move_orders[player_id]):
            if not self._has_unresolved_order_move(player_id, character_id):
                resolved_slots.add(index)

    def _has_unresolved_order_move(self, player_id: int, character_id: str) -> bool:
        if self.remaining_move_count(player_id, character_id) <= 0:
            return False
        character = self.game_state.player(player_id).get_character(character_id)
        return character.is_alive or (player_id, character_id) in self.pending_revivals

    def _first_unresolved_slot_for_actor(self, player_id: int, character_id: str) -> int | None:
        self._normalize_round_order(player_id)
        resolved_slots = self.round_resolved_order_slots[player_id]
        for index, ordered_character_id in enumerate(self.move_orders[player_id]):
            if ordered_character_id == character_id and index not in resolved_slots:
                return index
        return None

    def _insert_order_slot(self, player_id: int, index: int, character_id: str) -> None:
        self.move_orders[player_id].insert(index, character_id)
        self.round_resolved_order_slots[player_id] = {
            slot if slot < index else slot + 1
            for slot in self.round_resolved_order_slots[player_id]
        }

    def _resolve_order_slot(self, player_id: int, slot_index: int) -> None:
        self.round_resolved_order_slots[player_id].add(slot_index)

    def _advance_turn_after_action(self, acting_player_id: int) -> None:
        self._resolve_tenacity_after_enemy_action(acting_player_id)
        if not self._any_player_has_moves():
            self._start_next_round()
            return

        if self._consume_second_hand_extra_turn(acting_player_id):
            return

        opponent_id = self.game_state.opponent_id(acting_player_id)
        next_player_id = self._next_player_with_moves(opponent_id)
        if next_player_id is None:
            next_player_id = self._next_player_with_moves(acting_player_id)
        self.game_state.current_turn_player_id = next_player_id

    def _advance_turn_after_skip(self, acting_player_id: int) -> None:
        self._resolve_tenacity_after_enemy_action(acting_player_id)
        if not self._any_player_has_moves():
            self._start_next_round()
            return

        if self._consume_second_hand_extra_turn(acting_player_id):
            return

        if self.available_actors(acting_player_id):
            self.game_state.current_turn_player_id = acting_player_id
            return

        opponent_id = self.game_state.opponent_id(acting_player_id)
        self.game_state.current_turn_player_id = self._next_player_with_moves(opponent_id)

    def _consume_second_hand_extra_turn(self, acting_player_id: int) -> bool:
        if self.second_hand_extra_turn_player_id != acting_player_id:
            return False

        self.second_hand_extra_turn_player_id = None
        if self.available_actors(acting_player_id):
            self.game_state.current_turn_player_id = acting_player_id
            return True
        return False

    def _start_next_round(self) -> None:
        self.game_state.round_number += 1
        self.second_hand_extra_turn_player_id = None
        for player_id, player in self.game_state.players.items():
            if player.has_second_hand_skill and self._player_has_alive_effect(player_id, "repeat_second_hand_each_round"):
                player.second_hand_skill_used = False
        self._reset_round_moves()
        self.game_state.current_turn_player_id = self._next_player_with_moves(self.first_player_id)

    def _reset_round_moves(self) -> None:
        self.round_attack_modifiers.clear()
        self.round_damage_taken_bonus.clear()
        self.dream_mark_owners.clear()
        self.tenacity_pending_effects.clear()
        for player_id in self.game_state.players:
            for character in self.game_state.player(player_id).selected_characters:
                character_key = (player_id, character.id)
                removed_ids: list[str] = []
                for effect_id in ("dream_mark", "weak", "enraged"):
                    if character.has_status_effect(effect_id):
                        character.remove_status_effect(effect_id)
                        removed_ids.append(effect_id)
                if character_key in self.round_silenced_character_keys and character.has_status_effect("silenced"):
                    character.remove_status_effect("silenced")
                    removed_ids.append("silenced")
                if removed_ids:
                    self._clear_tracking_for_character(character_key, removed_ids)
        self.round_silenced_character_keys.clear()
        self.remaining_moves.clear()
        for player_id in self.game_state.players:
            self.round_resolved_order_slots[player_id] = set()
            self.round_skipped_ids[player_id] = set()

        for player_id, player in self.game_state.players.items():
            for character in player.selected_characters:
                character_key = (player_id, character.id)
                character.armor = 0
                character.used_passive_effect_ids.discard("first_damage_immunity_each_round")
                if (character.is_alive or character_key in self.pending_revivals) and character.position is not None:
                    move_count = character.default_move_count
                    if self._character_has_battle_effect(character_key, "extra_move_1"):
                        move_count += 1
                    self.remaining_moves[character_key] = move_count
                else:
                    self.remaining_moves[character_key] = 0
            self._normalize_round_order(player_id)
        self._refresh_aura_health_bonuses()

    def _player_has_alive_effect(self, player_id: int, effect_id: str) -> bool:
        return any(
            character.is_alive
            and character.position is not None
            and self._character_has_battle_effect((player_id, character.id), effect_id)
            for character in self._battle_characters(player_id)
        )

    def _next_player_with_moves(self, preferred_player_id: int) -> int | None:
        if self.available_actors(preferred_player_id):
            return preferred_player_id

        opponent_id = self.game_state.opponent_id(preferred_player_id)
        if self.available_actors(opponent_id):
            return opponent_id

        return None

    def _any_player_has_moves(self) -> bool:
        return any(self.available_actors(player_id) for player_id in self.game_state.players)

    def _check_winner(self) -> int | None:
        self._resolve_isolated_character_deaths()
        defeated_players = [
            player_id
            for player_id in self.game_state.players
            if self._is_battle_player_defeated(player_id)
        ]
        if not defeated_players:
            return None

        winner_id = self.game_state.opponent_id(defeated_players[0])
        self.game_state.set_winner(winner_id)
        self.game_state.current_turn_player_id = None
        return winner_id

    def _resolve_isolated_character_deaths(self) -> None:
        for player_id in self.game_state.players:
            for character in self._battle_characters(player_id):
                character_key = (player_id, character.id)
                if not character.is_alive or not self._character_has_battle_effect(character_key, "dies_without_adjacent_ally"):
                    continue
                if character.position is None:
                    continue
                if not self._adjacent_character_keys(player_id, character.position, exclude_id=character.id):
                    self._execute_character(character_key, None)

    def _battle_characters(self, player_id: int) -> list[Character]:
        return [
            character
            for character in self.game_state.player(player_id).selected_characters
            if character.position is not None
        ]

    def _ordered_battle_character_refs(self, moving_player_id: int) -> list[tuple[int, Character]]:
        ordered_refs: list[tuple[int, Character]] = []
        player_order = (moving_player_id, self.game_state.opponent_id(moving_player_id))
        column_order = (FormationColumn.FRONT, FormationColumn.BACK)
        for player_id in player_order:
            player = self.game_state.player(player_id)
            for column in column_order:
                for row in range(3):
                    character_id = player.formation.get(Position(row=row, column=column))
                    if character_id is not None:
                        character = player.get_character(character_id)
                        ordered_refs.append((player_id, character))
        return ordered_refs

    def _is_battle_player_defeated(self, player_id: int) -> bool:
        living_characters = [character for character in self._battle_characters(player_id) if character.is_alive]
        if not living_characters:
            return bool(self._battle_characters(player_id))
        return not any(
            not self._character_has_battle_effect((player_id, character.id), "stealth")
            and not self._character_has_battle_effect((player_id, character.id), "unselectable")
            for character in living_characters
        )
