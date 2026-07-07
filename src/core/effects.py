from src.core.models import Effect


def resolve_effects(effect_ids: tuple[str, ...], effects_by_id: dict[str, Effect]) -> tuple[Effect, ...]:
    missing = [effect_id for effect_id in effect_ids if effect_id not in effects_by_id]
    if missing:
        raise KeyError(f"Unknown effect ids: {', '.join(missing)}")

    return tuple(effects_by_id[effect_id] for effect_id in effect_ids)
