from src.core.models import GamePhase, GameState, Player


def create_initial_game_state(
    player_one_name: str = "玩家1",
    player_two_name: str = "玩家2",
) -> GameState:
    return GameState(
        players={
            1: Player(id=1, name=player_one_name),
            2: Player(id=2, name=player_two_name),
        },
        phase=GamePhase.DRAFT,
    )
