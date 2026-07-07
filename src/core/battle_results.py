from __future__ import annotations

from dataclasses import dataclass

from src.core.models import Position


@dataclass(frozen=True)
class DamageEvent:
    player_id: int
    character_id: str
    damage: int
    critical: bool = False


@dataclass(frozen=True)
class StartOrderChoiceResult:
    player_name: str
    first_player_name: str
    second_player_name: str
    next_player_id: int | None
    round_number: int


@dataclass(frozen=True)
class AttackResult:
    attacker_name: str
    target_name: str
    damage: int
    target_defeated: bool
    skipped_actor_names: tuple[str, ...]
    winner_player_id: int | None
    next_player_id: int | None
    round_number: int
    actual_target_name: str = ""
    reflected_damage: int = 0
    attacker_defeated: bool = False
    defeated_character_names: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    damage_events: tuple[DamageEvent, ...] = ()


@dataclass(frozen=True)
class SkipResult:
    actor_name: str
    next_player_id: int | None
    round_number: int
    events: tuple[str, ...] = ()


@dataclass(frozen=True)
class EndRoundResult:
    player_name: str
    consumed_actor_names: tuple[str, ...]
    next_player_id: int | None
    round_number: int


@dataclass(frozen=True)
class ThawResult:
    actor_name: str
    next_player_id: int | None
    round_number: int


@dataclass(frozen=True)
class RelocateResult:
    actor_name: str
    from_position: Position
    to_position: Position
    next_player_id: int | None
    round_number: int


@dataclass(frozen=True)
class SecondHandResult:
    player_name: str
    next_player_id: int | None
    round_number: int


@dataclass(frozen=True)
class SummonRequest:
    player_id: int
    source_name: str
    character_definition_id: str


@dataclass(frozen=True)
class SummonResult:
    source_name: str
    summoned_name: str
    position: Position
    winner_player_id: int | None
    next_player_id: int | None
    round_number: int
    events: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeathTrigger:
    player_id: int
    character_id: str
    character_name: str
    damage: int
    kind: str = "damage"
    attack_bonus: int = 0


@dataclass(frozen=True)
class DeathTriggerResult:
    source_name: str
    target_name: str
    damage: int
    skipped: bool
    winner_player_id: int | None
    next_player_id: int | None
    round_number: int
    actual_target_name: str = ""
    defeated_character_names: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    damage_events: tuple[DamageEvent, ...] = ()


@dataclass(frozen=True)
class SwordSaintChoiceResult:
    source_name: str
    choice_name: str
    winner_player_id: int | None
    next_player_id: int | None
    round_number: int
    events: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChaseResult:
    source_name: str
    target_name: str
    damage: int
    winner_player_id: int | None
    next_player_id: int | None
    round_number: int
    actual_target_name: str = ""
    defeated_character_names: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    damage_events: tuple[DamageEvent, ...] = ()


@dataclass(frozen=True)
class SkillResult:
    caster_name: str
    skill_name: str
    target_name: str
    damage: int
    status_effect_name: str
    status_applied: bool
    winner_player_id: int | None
    next_player_id: int | None
    round_number: int
    actual_target_name: str = ""
    defeated_character_names: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    damage_events: tuple[DamageEvent, ...] = ()


@dataclass(frozen=True)
class DamageResult:
    requested_target_name: str
    receiver_name: str
    damage: int
    receiver_key: tuple[int, str]
    events: tuple[str, ...]


@dataclass(frozen=True)
class AttackResolution:
    damage: int
    actual_target_name: str
    reflected_damage: int
    target_defeated: bool
    attacker_defeated: bool
    events: tuple[str, ...]
