from src.core.models import Job, PlacementRestriction


JOBS: tuple[Job, ...] = (
    Job(
        id="arcane",
        name="秘法者",
        description="无特殊效果。",
    ),
    Job(
        id="warrior",
        name="战士",
        description="反伤100%。",
        effect_ids=("reflect_100",),
    ),
    Job(
        id="raider",
        name="突袭者",
        description="攻击时具有免疫，可以攻击后排角色。",
        effect_ids=("attack_immunity", "backline_attack"),
    ),
    Job(
        id="guardian",
        name="守护者",
        description="同前排/后排嘲讽。",
        effect_ids=("row_taunt",),
    ),
    Job(
        id="defender",
        name="抵御者",
        description="抵御周围四格友军，反伤50%，只能放在前排。",
        effect_ids=("guard_adjacent", "reflect_50"),
        placement_restrictions=(PlacementRestriction.FRONT_ONLY,),
    ),
    Job(
        id="executor",
        name="斩杀者",
        description="反伤50%，只能放在前排。",
        effect_ids=("reflect_50",),
        placement_restrictions=(PlacementRestriction.FRONT_ONLY,),
    ),
    Job(
        id="charger",
        name="冲锋者",
        description="移动次数+1，攻击目标时对方获得反伤50%。",
        effect_ids=("target_gain_reflect_50",),
        move_count_modifier=1,
    ),
    Job(
        id="hero",
        name="英雄",
        description="同列前后不可放置单位，受伤-1，反伤50%，无法被沉默。",
        effect_ids=("damage_reduction_1", "reflect_50", "silence_immunity"),
        placement_restrictions=(PlacementRestriction.ROW_PAIR_EXCLUSIVE,),
    ),
    Job(
        id="creator",
        name="制作者",
        description="免疫不利效果。",
        effect_ids=("adverse_immunity",),
    ),
    Job(
        id="summon",
        name="召唤物",
        description="无特殊效果。",
    ),
    Job(
        id="arcanarch",
        name="帝法者",
        description="无特殊效果。",
    ),
)

JOBS_BY_ID: dict[str, Job] = {job.id: job for job in JOBS}
