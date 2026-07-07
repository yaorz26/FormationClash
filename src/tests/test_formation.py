import unittest

from src.core import (
    DraftSession,
    FormationColumn,
    FormationError,
    FormationSession,
    GamePhase,
    Position,
)
from src.core.formation import FORMATION_POSITIONS
from src.core.game_state import create_initial_game_state
from src.data.characters import create_test_character_pool as create_character_pool


def create_completed_draft() -> tuple[FormationSession, object]:
    game_state = create_initial_game_state()
    character_pool = create_character_pool()
    draft = DraftSession(game_state, character_pool, first_player_id=1)

    for character in character_pool[:12]:
        draft.select_character(character.id)

    return FormationSession(game_state), game_state


def place_player_one_formation(session: FormationSession) -> None:
    session.place_character(1, "orion", Position(row=0, column=FormationColumn.BACK))
    session.place_character(1, "morgan", Position(row=1, column=FormationColumn.BACK))
    session.place_character(1, "duran", Position(row=1, column=FormationColumn.FRONT))
    session.place_character(1, "maker", Position(row=2, column=FormationColumn.BACK))
    session.place_character(1, "sable", Position(row=2, column=FormationColumn.FRONT))


def place_player_two_formation(session: FormationSession) -> None:
    session.place_character(2, "brant", Position(row=0, column=FormationColumn.BACK))
    session.place_character(2, "kira", Position(row=0, column=FormationColumn.FRONT))
    session.place_character(2, "iris", Position(row=1, column=FormationColumn.BACK))
    session.place_character(2, "voss", Position(row=1, column=FormationColumn.FRONT))
    session.place_character(2, "spark", Position(row=2, column=FormationColumn.BACK))
    session.place_character(2, "naya", Position(row=2, column=FormationColumn.FRONT))


class FormationSessionTests(unittest.TestCase):
    def test_formation_has_two_columns_and_three_rows(self) -> None:
        rows = {position.row for position in FORMATION_POSITIONS}
        columns = {position.column for position in FORMATION_POSITIONS}

        self.assertEqual(len(FORMATION_POSITIONS), 6)
        self.assertEqual(rows, {0, 1, 2})
        self.assertEqual(columns, {FormationColumn.FRONT, FormationColumn.BACK})

    def test_front_only_jobs_reject_back_position(self) -> None:
        session, _ = create_completed_draft()

        with self.assertRaises(FormationError):
            session.place_character(1, "duran", Position(row=0, column=FormationColumn.BACK))

        session.place_character(1, "duran", Position(row=0, column=FormationColumn.FRONT))
        self.assertEqual(
            session.game_state.player(1).get_character("duran").position,
            Position(row=0, column=FormationColumn.FRONT),
        )

    def test_occupied_position_rejects_second_character(self) -> None:
        session, _ = create_completed_draft()
        position = Position(row=0, column=FormationColumn.FRONT)

        session.place_character(1, "luna", position)

        with self.assertRaises(FormationError):
            session.place_character(1, "morgan", position)

    def test_hero_rejects_placement_into_occupied_row(self) -> None:
        session, _ = create_completed_draft()

        session.place_character(1, "luna", Position(row=0, column=FormationColumn.FRONT))

        with self.assertRaises(FormationError):
            session.place_character(1, "orion", Position(row=0, column=FormationColumn.BACK))

    def test_occupied_hero_row_rejects_later_character(self) -> None:
        session, _ = create_completed_draft()

        session.place_character(1, "orion", Position(row=0, column=FormationColumn.BACK))

        with self.assertRaises(FormationError):
            session.place_character(1, "luna", Position(row=0, column=FormationColumn.FRONT))

    def test_unplaced_characters_updates_after_placement(self) -> None:
        session, _ = create_completed_draft()

        self.assertEqual(len(session.unplaced_characters(1)), 6)

        session.place_character(1, "luna", Position(row=0, column=FormationColumn.BACK))

        self.assertEqual(len(session.unplaced_characters(1)), 5)

    def test_confirm_allows_partial_formation(self) -> None:
        session, _ = create_completed_draft()

        session.place_character(1, "luna", Position(row=0, column=FormationColumn.BACK))

        session.confirm_player_formation(1)

        self.assertEqual(session.current_player_id, 2)

    def test_confirm_rejects_empty_formation(self) -> None:
        session, _ = create_completed_draft()

        with self.assertRaises(FormationError):
            session.confirm_player_formation(1)

    def test_confirmed_formation_cannot_be_changed(self) -> None:
        session, _ = create_completed_draft()
        place_player_one_formation(session)
        session.confirm_player_formation(1)

        with self.assertRaises(FormationError):
            session.clear_character(1, "luna")

    def test_both_confirmed_formations_enter_battle_phase(self) -> None:
        session, game_state = create_completed_draft()

        place_player_one_formation(session)
        session.confirm_player_formation(1)
        self.assertEqual(session.current_player_id, 2)
        self.assertEqual(game_state.phase, GamePhase.FORMATION)

        place_player_two_formation(session)
        session.confirm_player_formation(2)

        self.assertEqual(game_state.phase, GamePhase.BATTLE)
        self.assertIsNone(game_state.current_turn_player_id)
        self.assertTrue(session.is_complete)


if __name__ == "__main__":
    unittest.main()
