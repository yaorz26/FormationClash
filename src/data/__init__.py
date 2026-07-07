"""Default game data catalog."""

from src.data.characters import (
    CHARACTER_DEFINITIONS,
    CHARACTER_DEFINITIONS_BY_ID,
    TEST_CHARACTER_DEFINITIONS,
    TEST_CHARACTER_DEFINITIONS_BY_ID,
    create_character_pool,
    create_draft_character_pool,
    create_test_character_pool,
)
from src.data.encyclopedia import CHARACTER_MECHANIC_DETAILS, MECHANIC_ENTRIES, MechanicEntry
from src.data.jobs import JOBS, JOBS_BY_ID
from src.data.keywords import EFFECTS, EFFECTS_BY_ID

__all__ = [
    "CHARACTER_DEFINITIONS",
    "CHARACTER_DEFINITIONS_BY_ID",
    "CHARACTER_MECHANIC_DETAILS",
    "TEST_CHARACTER_DEFINITIONS",
    "TEST_CHARACTER_DEFINITIONS_BY_ID",
    "EFFECTS",
    "EFFECTS_BY_ID",
    "JOBS",
    "JOBS_BY_ID",
    "MECHANIC_ENTRIES",
    "MechanicEntry",
    "create_character_pool",
    "create_draft_character_pool",
    "create_test_character_pool",
]
