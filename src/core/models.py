from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GamePhase(str, Enum):
    DRAFT = "draft"
    FORMATION = "formation"
    BATTLE = "battle"
    FINISHED = "finished"


class EffectCategory(str, Enum):
    KEYWORD = "keyword"
    BUFF = "buff"
    DEBUFF = "debuff"


class FormationColumn(str, Enum):
    FRONT = "front"
    BACK = "back"


class PlacementRestriction(str, Enum):
    FRONT_ONLY = "front_only"
    ROW_PAIR_EXCLUSIVE = "row_pair_exclusive"


class SkillTarget(str, Enum):
    ANY = "any"
    ALLY = "ally"
    ENEMY = "enemy"
    SELF = "self"


class SkillKind(str, Enum):
    DAMAGE = "damage"
    STATUS = "status"
    HEAL = "heal"
    ARMOR = "armor"
    ATTACK_BUFF = "attack_buff"
    HEALTH_BUFF_RANK = "health_buff_rank"
    ATTACK = "attack"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Position:
    row: int
    column: FormationColumn

    def __post_init__(self) -> None:
        if self.row not in range(3):
            raise ValueError("Formation row must be 0, 1, or 2.")


@dataclass(frozen=True)
class Effect:
    id: str
    name: str
    category: EffectCategory
    description: str
    is_adverse: bool = False
    show_in_encyclopedia: bool = True


@dataclass(frozen=True)
class ActiveSkill:
    id: str
    name: str
    description: str
    display_text: str = ""
    kind: SkillKind = SkillKind.DAMAGE
    target: SkillTarget = SkillTarget.ANY
    damage: int = 0
    heal: int = 0
    armor: int = 0
    attack_bonus: int = 0
    health_bonus: int = 0
    attack_percent: int = 100
    target_reflect_percent: int = 0
    once_per_game: bool = False
    status_effect_id: str | None = None
    min_targets: int = 1
    max_targets: int = 1
    exclude_self: bool = False


@dataclass(frozen=True)
class Job:
    id: str
    name: str
    description: str
    effect_ids: tuple[str, ...] = ()
    placement_restrictions: tuple[PlacementRestriction, ...] = ()
    move_count_modifier: int = 0

    @property
    def default_move_count(self) -> int:
        return 1 + self.move_count_modifier

    def has_effect(self, effect_id: str) -> bool:
        return effect_id in self.effect_ids

    def has_restriction(self, restriction: PlacementRestriction) -> bool:
        return restriction in self.placement_restrictions


@dataclass(frozen=True)
class CharacterDefinition:
    id: str
    name: str
    job_id: str
    max_health: int
    attack: int
    skill_description: str
    passive_description: str = ""
    factions: tuple[str, ...] = ()
    passive_effect_ids: tuple[str, ...] = ()
    active_effect_ids: tuple[str, ...] = ()
    active_skills: tuple[ActiveSkill, ...] = ()
    placement_restrictions: tuple[PlacementRestriction, ...] = ()

    def __post_init__(self) -> None:
        if self.max_health <= 0:
            raise ValueError("Character max health must be positive.")
        if self.attack < 0:
            raise ValueError("Character attack cannot be negative.")

    def create_character(self, jobs_by_id: dict[str, Job]) -> Character:
        if self.job_id not in jobs_by_id:
            raise KeyError(f"Unknown job id for character {self.id}: {self.job_id}")

        job = jobs_by_id[self.job_id]
        return Character(
            id=self.id,
            name=self.name,
            job=job,
            base_job=job,
            base_max_health=self.max_health,
            max_health=self.max_health,
            current_health=self.max_health,
            base_attack=self.attack,
            attack=self.attack,
            skill_description=self.skill_description,
            passive_description=self.passive_description,
            factions=self.factions,
            passive_effect_ids=self.passive_effect_ids,
            base_passive_effect_ids=self.passive_effect_ids,
            active_effect_ids=self.active_effect_ids,
            base_active_effect_ids=self.active_effect_ids,
            active_skills=self.active_skills,
            base_active_skills=self.active_skills,
            placement_restrictions=self.placement_restrictions,
        )


@dataclass
class Character:
    id: str
    name: str
    job: Job
    base_job: Job
    base_max_health: int
    max_health: int
    current_health: int
    base_attack: int
    attack: int
    skill_description: str
    passive_description: str = ""
    factions: tuple[str, ...] = ()
    passive_effect_ids: tuple[str, ...] = ()
    base_passive_effect_ids: tuple[str, ...] = ()
    active_effect_ids: tuple[str, ...] = ()
    base_active_effect_ids: tuple[str, ...] = ()
    active_skills: tuple[ActiveSkill, ...] = ()
    base_active_skills: tuple[ActiveSkill, ...] = ()
    placement_restrictions: tuple[PlacementRestriction, ...] = ()
    status_effect_ids: set[str] = field(default_factory=set)
    used_active_skill_ids: set[str] = field(default_factory=set)
    used_passive_effect_ids: set[str] = field(default_factory=set)
    armor: int = 0
    aura_max_health_bonus: int = 0
    position: Position | None = None

    @property
    def is_alive(self) -> bool:
        return self.current_health > 0

    @property
    def effective_passive_effect_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.job.effect_ids, *self.passive_effect_ids)))

    @property
    def default_move_count(self) -> int:
        return self.job.default_move_count

    def take_damage(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Damage amount cannot be negative.")
        absorbed = min(self.armor, amount)
        self.armor -= absorbed
        remaining = amount - absorbed
        self.current_health = max(0, self.current_health - remaining)

    def heal(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Heal amount cannot be negative.")
        if self.is_alive:
            self.current_health = min(self.max_health, self.current_health + amount)

    def gain_health(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Health gain cannot be negative.")
        if self.is_alive:
            self.max_health += amount
            self.current_health += amount

    def gain_armor(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Armor gain cannot be negative.")
        if self.is_alive:
            self.armor += amount

    def use_active_skill(self, skill_id: str) -> None:
        self.used_active_skill_ids.add(skill_id)

    def has_used_active_skill(self, skill_id: str) -> bool:
        return skill_id in self.used_active_skill_ids

    def mark_passive_effect_used(self, effect_id: str) -> None:
        self.used_passive_effect_ids.add(effect_id)

    def has_used_passive_effect(self, effect_id: str) -> bool:
        return effect_id in self.used_passive_effect_ids

    def place_at(self, position: Position) -> None:
        self.position = position

    def clear_position(self) -> None:
        self.position = None

    def has_status_effect(self, effect_id: str) -> bool:
        return effect_id in self.status_effect_ids

    def add_status_effect(self, effect_id: str) -> None:
        self.status_effect_ids.add(effect_id)

    def remove_status_effect(self, effect_id: str) -> None:
        self.status_effect_ids.discard(effect_id)

    def reset_for_revival(self) -> None:
        self.job = self.base_job
        self.max_health = self.base_max_health
        self.current_health = self.base_max_health
        self.attack = self.base_attack
        self.passive_effect_ids = self.base_passive_effect_ids
        self.active_effect_ids = self.base_active_effect_ids
        self.active_skills = self.base_active_skills
        self.status_effect_ids.clear()
        self.used_active_skill_ids.clear()
        self.used_passive_effect_ids.clear()
        self.armor = 0
        self.aura_max_health_bonus = 0


@dataclass
class Player:
    id: int
    name: str = ""
    selected_characters: list[Character] = field(default_factory=list)
    formation: dict[Position, str] = field(default_factory=dict)
    has_second_hand_skill: bool = False
    second_hand_skill_used: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"玩家{self.id}"

    @property
    def living_characters(self) -> list[Character]:
        return [character for character in self.selected_characters if character.is_alive]

    @property
    def is_defeated(self) -> bool:
        return bool(self.selected_characters) and not self.living_characters

    def add_character(self, character: Character) -> None:
        if any(existing.id == character.id for existing in self.selected_characters):
            raise ValueError(f"Character already selected by this player: {character.id}")
        self.selected_characters.append(character)

    def get_character(self, character_id: str) -> Character:
        for character in self.selected_characters:
            if character.id == character_id:
                return character
        raise KeyError(f"Player {self.id} does not have character: {character_id}")

    def place_character(self, character_id: str, position: Position) -> None:
        character = self.get_character(character_id)

        occupied_by = self.formation.get(position)
        if occupied_by is not None and occupied_by != character_id:
            occupant = self.get_character(occupied_by)
            if occupant.is_alive:
                raise ValueError(f"Position already occupied: {position}")
            occupant.clear_position()
            self.formation.pop(position, None)

        if character.position is not None:
            self.formation.pop(character.position, None)

        character.place_at(position)
        self.formation[position] = character.id

    def character_at(self, position: Position) -> Character | None:
        character_id = self.formation.get(position)
        if character_id is None:
            return None
        character = self.get_character(character_id)
        if not character.is_alive:
            return None
        return character


@dataclass
class GameState:
    players: dict[int, Player]
    phase: GamePhase = GamePhase.DRAFT
    round_number: int = 0
    current_turn_player_id: int | None = None
    draft_first_player_id: int | None = None
    battle_first_player_id: int | None = None
    winner_player_id: int | None = None

    def player(self, player_id: int) -> Player:
        if player_id not in self.players:
            raise KeyError(f"Unknown player id: {player_id}")
        return self.players[player_id]

    def opponent_id(self, player_id: int) -> int:
        opponents = [candidate for candidate in self.players if candidate != player_id]
        if len(opponents) != 1:
            raise ValueError("Opponent lookup requires exactly two players.")
        return opponents[0]

    def set_winner(self, player_id: int) -> None:
        self.player(player_id)
        self.winner_player_id = player_id
        self.phase = GamePhase.FINISHED

    @property
    def is_finished(self) -> bool:
        return self.phase == GamePhase.FINISHED
