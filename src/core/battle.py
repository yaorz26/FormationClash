from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from src.core.battle_attacks import BattleAttackMixin
from src.core.battle_debug import BattleDebugMixin
from src.core.battle_effects import BattleEffectMixin
from src.core.battle_errors import BattleError
from src.core.battle_results import (
    AttackResolution,
    AttackResult,
    DamageEvent,
    DamageResult,
    DeathTrigger,
    DeathTriggerResult,
    EndRoundResult,
    RelocateResult,
    SecondHandResult,
    StartOrderChoiceResult,
    SkillResult,
    SkipResult,
    SummonRequest,
    SummonResult,
    ThawResult,
)
from src.core.battle_skills import BattleSkillMixin
from src.core.battle_turns import BattleTurnMixin
from src.core.models import GamePhase, GameState


@dataclass
class BattleSession(
    BattleDebugMixin,
    BattleSkillMixin,
    BattleAttackMixin,
    BattleEffectMixin,
    BattleTurnMixin,
):
    game_state: GameState
    first_player_id: int
    pending_start_order_choice_player_id: int | None = None
    remaining_moves: dict[tuple[int, str], int] = field(default_factory=dict)
    move_orders: dict[int, list[str]] = field(default_factory=dict)
    round_resolved_order_slots: dict[int, set[int]] = field(default_factory=dict)
    round_skipped_ids: dict[int, set[str]] = field(default_factory=dict)
    second_hand_extra_turn_player_id: int | None = None
    pending_death_triggers: list[DeathTrigger] = field(default_factory=list)
    pending_post_action_player_id: int | None = None
    pending_followup_attack: tuple[int, str] | None = None
    pending_followup_order_slot: int | None = None
    pending_followup_remaining_attacks: int = 0
    suppressed_bonus_character_keys: set[tuple[int, str]] = field(default_factory=set)
    pending_summons: list[SummonRequest] = field(default_factory=list)
    dream_mark_owners: dict[tuple[int, str], tuple[int, str]] = field(default_factory=dict)
    round_attack_modifiers: dict[tuple[int, str], int] = field(default_factory=dict)
    round_damage_taken_bonus: dict[tuple[int, str], int] = field(default_factory=dict)
    tenacity_pending_effects: dict[tuple[int, str], dict[str, bool]] = field(default_factory=dict)
    last_damage_sources: dict[tuple[int, str], tuple[int, str]] = field(default_factory=dict)
    pending_revivals: set[tuple[int, str]] = field(default_factory=set)
    attacking_character_key: tuple[int, str] | None = None
    sword_saint_inspire_counts: dict[tuple[int, str], int] = field(default_factory=dict)
    team_barriers: dict[int, int] = field(default_factory=dict)
    team_barrier_sources: dict[int, tuple[int, str]] = field(default_factory=dict)
    shield_stacks: dict[tuple[int, str], int] = field(default_factory=dict)
    pending_sword_saint_choices: list[tuple[int, str]] = field(default_factory=list)
    pending_chase_choices: list[tuple[tuple[int, str], tuple[int, str]]] = field(default_factory=list)
    temporary_undying_character_keys: set[tuple[int, str]] = field(default_factory=set)
    damage_threshold_totals: dict[tuple[int, str], int] = field(default_factory=dict)
    damage_threshold_trigger_counts: dict[tuple[int, str], int] = field(default_factory=dict)
    action_damage_events: list[DamageEvent] = field(default_factory=list)
    fearless_refund_counts: dict[tuple[int, str], int] = field(default_factory=dict)
    limited_skill_use_counts: dict[tuple[int, str, str], int] = field(default_factory=dict)
    gravity_stacks: dict[tuple[int, str], int] = field(default_factory=dict)
    enrage_sources: dict[tuple[int, str], tuple[int, str]] = field(default_factory=dict)
    round_silenced_character_keys: set[tuple[int, str]] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.game_state.phase != GamePhase.BATTLE:
            raise ValueError("Battle can only start while the game is in battle phase.")
        if self.first_player_id not in self.game_state.players:
            raise KeyError(f"Unknown battle first player id: {self.first_player_id}")
        if len(self.game_state.players) != 2:
            raise ValueError("Battle requires exactly two players.")

        self._initialize_battle_runtime()
        choice_player_id = self._start_order_choice_player_id()
        if choice_player_id is not None:
            self.pending_start_order_choice_player_id = choice_player_id
            self.game_state.battle_first_player_id = None
            self.game_state.current_turn_player_id = None
            return

        self.first_player_id = self._resolve_forced_first_player(self.first_player_id)
        self._begin_battle_after_start_order()

    def _initialize_battle_runtime(self) -> None:
        self.game_state.round_number = 1
        self.second_hand_extra_turn_player_id = None
        self.move_orders = {player_id: [] for player_id in self.game_state.players}
        self.round_resolved_order_slots = {player_id: set() for player_id in self.game_state.players}
        self.round_skipped_ids = {player_id: set() for player_id in self.game_state.players}
        self.pending_death_triggers = []
        self.pending_post_action_player_id = None
        self.pending_followup_attack = None
        self.pending_followup_order_slot = None
        self.pending_followup_remaining_attacks = 0
        self.suppressed_bonus_character_keys = set()
        self.pending_summons = []
        self.dream_mark_owners = {}
        self.round_attack_modifiers = {}
        self.round_damage_taken_bonus = {}
        self.tenacity_pending_effects = {}
        self.last_damage_sources = {}
        self.pending_revivals = set()
        self.attacking_character_key = None
        self.sword_saint_inspire_counts = {}
        self.team_barriers = {}
        self.team_barrier_sources = {}
        self.shield_stacks = {}
        self.pending_sword_saint_choices = []
        self.pending_chase_choices = []
        self.temporary_undying_character_keys = set()
        self.damage_threshold_totals = {}
        self.damage_threshold_trigger_counts = {}
        self.action_damage_events = []
        self.fearless_refund_counts = {}
        self.limited_skill_use_counts = {}
        self.gravity_stacks = {}
        self.enrage_sources = {}
        self.round_silenced_character_keys = set()

    def _begin_battle_after_start_order(self) -> None:
        self.pending_start_order_choice_player_id = None
        self.game_state.battle_first_player_id = self.first_player_id
        self.game_state.round_number = 1
        for player_id, player in self.game_state.players.items():
            player.has_second_hand_skill = player_id != self.first_player_id
            player.second_hand_skill_used = False
        self._reset_round_moves()
        self._apply_battle_start_passives()
        self._refresh_aura_health_bonuses()
        winner_player_id = self._check_winner()
        if winner_player_id is None:
            if self.pending_death_triggers:
                self.game_state.current_turn_player_id = self.pending_death_triggers[0].player_id
            else:
                self.game_state.current_turn_player_id = self._next_player_with_moves(self.first_player_id)

    def can_choose_start_order(self, player_id: int) -> bool:
        return (
            self.game_state.phase == GamePhase.BATTLE
            and self.pending_start_order_choice_player_id == player_id
            and self.game_state.current_turn_player_id is None
        )

    def choose_start_order(self, player_id: int, *, choose_first: bool) -> StartOrderChoiceResult:
        if not self.can_choose_start_order(player_id):
            raise BattleError("Invalid start order choice.")

        self.first_player_id = player_id if choose_first else self.game_state.opponent_id(player_id)
        self._begin_battle_after_start_order()
        first_player = self.game_state.player(self.first_player_id)
        second_player = self.game_state.player(self.game_state.opponent_id(self.first_player_id))
        return StartOrderChoiceResult(
            player_name=self.game_state.player(player_id).name,
            first_player_name=first_player.name,
            second_player_name=second_player.name,
            next_player_id=self.current_player_id,
            round_number=self.game_state.round_number,
        )

    def _resolve_forced_first_player(self, default_player_id: int) -> int:
        player_ids = tuple(self.game_state.players)
        force_first = {
            player_id: self._player_has_definition_effect(player_id, "force_battle_first")
            for player_id in player_ids
        }
        force_second = {
            player_id: self._player_has_definition_effect(player_id, "force_battle_second")
            for player_id in player_ids
        }

        if any(force_first[player_id] and force_second[player_id] for player_id in player_ids):
            return default_player_id

        preferred_first_players: set[int] = set()
        for player_id in player_ids:
            if force_first[player_id]:
                preferred_first_players.add(player_id)
            if force_second[player_id]:
                preferred_first_players.add(self.game_state.opponent_id(player_id))
        if len(preferred_first_players) == 1:
            return next(iter(preferred_first_players))
        return default_player_id

    def _start_order_choice_player_id(self) -> int | None:
        choice_player_ids = [
            player_id
            for player_id in self.game_state.players
            if self._player_has_definition_effect(player_id, "force_battle_first")
            and self._player_has_definition_effect(player_id, "force_battle_second")
        ]
        if len(choice_player_ids) == 1:
            return choice_player_ids[0]
        return None

    def _player_has_definition_effect(self, player_id: int, effect_id: str) -> bool:
        return any(
            effect_id in character.effective_passive_effect_ids
            for character in self.game_state.player(player_id).selected_characters
            if character.position is not None
        )

    @classmethod
    def with_random_first_player(
        cls,
        game_state: GameState,
        player_ids: Sequence[int] = (1, 2),
    ) -> BattleSession:
        return cls(
            game_state=game_state,
            first_player_id=random.choice(tuple(player_ids)),
        )
