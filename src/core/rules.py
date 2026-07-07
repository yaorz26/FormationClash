from collections.abc import Iterable

from src.core.models import ActiveSkill, Character, FormationColumn, Job, PlacementRestriction, Position


ADVERSE_STATUS_EFFECT_IDS = frozenset(("bleeding", "frozen", "dream_mark", "enraged", "gravity", "weak"))
STATUS_EFFECT_NAMES = {
    "bleeding": "流血",
    "frozen": "冻结",
    "stealth": "隐匿",
    "tenacity": "坚毅",
    "cursed": "诅咒",
    "dream_mark": "摄梦",
    "silenced": "沉默",
    "shield": "护盾",
    "enraged": "激怒",
    "gravity": "重力",
    "weak": "虚弱",
}


def character_has_effect(character: Character, effect_id: str) -> bool:
    return effect_id in character.effective_passive_effect_ids or character.has_status_effect(effect_id)


def is_adverse_status_effect(effect_id: str) -> bool:
    try:
        from src.data.keywords import EFFECTS_BY_ID
    except ImportError:
        return effect_id in ADVERSE_STATUS_EFFECT_IDS

    effect = EFFECTS_BY_ID.get(effect_id)
    if effect is None:
        return effect_id in ADVERSE_STATUS_EFFECT_IDS
    return effect.is_adverse


def effect_display_name(effect_id: str) -> str:
    return STATUS_EFFECT_NAMES.get(effect_id, effect_id)


def active_skill_display_text(skill: ActiveSkill) -> str:
    text = skill.display_text or f"{skill.name}：{skill.description}"
    if skill.once_per_game and not text.startswith("限定："):
        return f"限定：{text}"
    return text


def job_allows_position(
    job: Job,
    position: Position,
    occupied_positions: Iterable[Position] = (),
) -> bool:
    if job.has_restriction(PlacementRestriction.FRONT_ONLY) and position.column != FormationColumn.FRONT:
        return False

    if job.has_restriction(PlacementRestriction.ROW_PAIR_EXCLUSIVE):
        return not any(occupied.row == position.row for occupied in occupied_positions)

    return True
