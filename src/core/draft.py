from __future__ import annotations

import random
from dataclasses import dataclass, field
from collections.abc import Sequence

from src.core.models import Character, GamePhase, GameState


DRAFT_PICK_COUNTS: tuple[int, ...] = (1, 2, 2, 2, 2, 2, 1)


@dataclass
class DraftSession:
    game_state: GameState
    character_pool: list[Character]
    first_player_id: int
    pick_counts: tuple[int, ...] = DRAFT_PICK_COUNTS
    current_step_index: int = 0
    picks_in_current_step: int = 0
    selected_character_ids: set[str] = field(default_factory=set)
    pick_history: list[tuple[int, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.game_state.phase != GamePhase.DRAFT:
            raise ValueError("Draft can only start while the game is in draft phase.")
        if self.first_player_id not in self.game_state.players:
            raise KeyError(f"Unknown first player id: {self.first_player_id}")
        if len(self.game_state.players) != 2:
            raise ValueError("Draft requires exactly two players.")

        self.game_state.draft_first_player_id = self.first_player_id
        self.game_state.current_turn_player_id = self.current_player_id

    @classmethod
    def with_random_first_player(
        cls,
        game_state: GameState,
        character_pool: list[Character],
        player_ids: Sequence[int] = (1, 2),
    ) -> DraftSession:
        return cls(
            game_state=game_state,
            character_pool=character_pool,
            first_player_id=random.choice(tuple(player_ids)),
        )

    @property
    def second_player_id(self) -> int:
        return self.game_state.opponent_id(self.first_player_id)

    @property
    def current_player_id(self) -> int | None:
        if self.is_complete:
            return None
        if self.current_step_index % 2 == 0:
            return self.first_player_id
        return self.second_player_id

    @property
    def current_pick_limit(self) -> int:
        if self.is_complete:
            return 0
        return self.pick_counts[self.current_step_index]

    @property
    def current_step_remaining_picks(self) -> int:
        return max(0, self.current_pick_limit - self.picks_in_current_step)

    @property
    def is_complete(self) -> bool:
        return self.current_step_index >= len(self.pick_counts)

    @property
    def available_characters(self) -> list[Character]:
        return [
            character
            for character in self.character_pool
            if character.id not in self.selected_character_ids
        ]

    def is_character_selected(self, character_id: str) -> bool:
        return character_id in self.selected_character_ids

    def select_character(self, character_id: str) -> Character:
        if self.is_complete:
            raise ValueError("Draft is already complete.")
        if character_id in self.selected_character_ids:
            raise ValueError(f"Character already selected: {character_id}")

        character = self._find_character(character_id)
        current_player_id = self.current_player_id
        if current_player_id is None:
            raise ValueError("No current draft player.")

        self.game_state.player(current_player_id).add_character(character)
        self.selected_character_ids.add(character_id)
        self.pick_history.append((current_player_id, character_id))
        self.picks_in_current_step += 1
        self._advance_if_needed()

        return character

    def retract_last_pick(self) -> Character:
        if not self.pick_history:
            raise ValueError("No draft pick to retract.")

        player_id, character_id = self.pick_history.pop()
        player = self.game_state.player(player_id)
        character = player.get_character(character_id)
        player.selected_characters = [
            selected_character
            for selected_character in player.selected_characters
            if selected_character.id != character_id
        ]
        self.selected_character_ids.discard(character_id)

        if self.is_complete:
            self.game_state.phase = GamePhase.DRAFT
            self.current_step_index = len(self.pick_counts) - 1
            self.picks_in_current_step = max(0, self.current_pick_limit - 1)
        elif self.picks_in_current_step > 0:
            self.picks_in_current_step -= 1
        else:
            self.current_step_index = max(0, self.current_step_index - 1)
            self.picks_in_current_step = max(0, self.current_pick_limit - 1)

        self.game_state.current_turn_player_id = self.current_player_id
        return character

    def _advance_if_needed(self) -> None:
        if self.picks_in_current_step < self.current_pick_limit:
            self.game_state.current_turn_player_id = self.current_player_id
            return

        self.current_step_index += 1
        self.picks_in_current_step = 0

        if self.is_complete:
            self.game_state.phase = GamePhase.FORMATION
            self.game_state.current_turn_player_id = None
        else:
            self.game_state.current_turn_player_id = self.current_player_id

    def _find_character(self, character_id: str) -> Character:
        for character in self.character_pool:
            if character.id == character_id:
                return character
        raise KeyError(f"Unknown draft character id: {character_id}")
