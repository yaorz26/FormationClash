from __future__ import annotations

from dataclasses import dataclass, field

from src.core.models import (
    Character,
    FormationColumn,
    GamePhase,
    GameState,
    PlacementRestriction,
    Player,
    Position,
)


FORMATION_ROWS = 3
FORMATION_COLUMNS: tuple[FormationColumn, ...] = (
    FormationColumn.FRONT,
    FormationColumn.BACK,
)
FORMATION_POSITIONS: tuple[Position, ...] = tuple(
    Position(row=row, column=column)
    for row in range(FORMATION_ROWS)
    for column in FORMATION_COLUMNS
)


class FormationError(ValueError):
    pass


@dataclass
class FormationSession:
    game_state: GameState
    current_player_id: int = 1
    confirmed_player_ids: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.game_state.phase != GamePhase.FORMATION:
            raise ValueError("Formation can only start while the game is in formation phase.")
        if self.current_player_id not in self.game_state.players:
            raise KeyError(f"Unknown formation player id: {self.current_player_id}")
        if len(self.game_state.players) != 2:
            raise ValueError("Formation requires exactly two players.")
        self.game_state.current_turn_player_id = self.current_player_id

    @property
    def is_complete(self) -> bool:
        return self.game_state.phase == GamePhase.BATTLE

    @property
    def current_player(self) -> Player:
        return self.game_state.player(self.current_player_id)

    def unplaced_characters(self, player_id: int) -> list[Character]:
        player = self.game_state.player(player_id)
        placed_ids = set(player.formation.values())
        return [
            character
            for character in player.selected_characters
            if character.id not in placed_ids
        ]

    def place_character(self, player_id: int, character_id: str, position: Position) -> None:
        if self.is_complete:
            raise FormationError("Formation is already complete.")
        if player_id in self.confirmed_player_ids:
            raise FormationError("Confirmed formation cannot be changed.")

        player = self.game_state.player(player_id)
        character = player.get_character(character_id)
        self._validate_position(position)
        self._validate_placement(player, character, position)
        player.place_character(character_id, position)

    def clear_character(self, player_id: int, character_id: str) -> None:
        if player_id in self.confirmed_player_ids:
            raise FormationError("Confirmed formation cannot be changed.")

        player = self.game_state.player(player_id)
        character = player.get_character(character_id)
        if character.position is None:
            return

        player.formation.pop(character.position, None)
        character.clear_position()

    def confirm_player_formation(self, player_id: int) -> None:
        player = self.game_state.player(player_id)
        if not self.is_player_formation_complete(player_id):
            raise FormationError("At least one character must be placed before confirming.")

        self.confirmed_player_ids.add(player_id)
        if len(self.confirmed_player_ids) == len(self.game_state.players):
            self.game_state.phase = GamePhase.BATTLE
            self.game_state.current_turn_player_id = None
            return

        next_player_id = self.game_state.opponent_id(player.id)
        self.current_player_id = next_player_id
        self.game_state.current_turn_player_id = next_player_id

    def is_player_formation_complete(self, player_id: int) -> bool:
        player = self.game_state.player(player_id)
        return bool(player.formation)

    def _validate_position(self, position: Position) -> None:
        if position not in FORMATION_POSITIONS:
            raise FormationError(f"Invalid formation position: {position}")

    def _validate_placement(self, player: Player, character: Character, position: Position) -> None:
        occupied_by = player.formation.get(position)
        if occupied_by is not None and occupied_by != character.id:
            raise FormationError("This position is already occupied.")

        if (
            self._character_has_restriction(character, PlacementRestriction.FRONT_ONLY)
            and position.column != FormationColumn.FRONT
            and not self._player_positions_count_as_front(player)
        ):
            raise FormationError(f"{character.name}只能放在前排。")

        self._validate_row_pair_exclusive(player, character, position)

    def _validate_row_pair_exclusive(
        self,
        player: Player,
        character: Character,
        position: Position,
    ) -> None:
        for occupied_position, occupied_character_id in player.formation.items():
            if occupied_character_id == character.id:
                continue
            if occupied_position.row != position.row:
                continue

            occupied_character = player.get_character(occupied_character_id)
            if (
                self._character_has_restriction(character, PlacementRestriction.ROW_PAIR_EXCLUSIVE)
                or self._character_has_restriction(occupied_character, PlacementRestriction.ROW_PAIR_EXCLUSIVE)
            ):
                raise FormationError("英雄同一行的前后格不可放置其他单位。")

    def _character_has_restriction(self, character: Character, restriction: PlacementRestriction) -> bool:
        return character.job.has_restriction(restriction) or restriction in character.placement_restrictions

    def _player_positions_count_as_front(self, player: Player) -> bool:
        return any(
            "all_positions_front" in player.get_character(character_id).effective_passive_effect_ids
            for character_id in player.formation.values()
        )
