---
name: new-character
description: '新增角色的端到端工作流。当用户要求新增角色、添加新英雄、设计新单位、扩展角色池时使用。涵盖需求文档格式、数据定义、机制实现、百科条目、单元测试的完整流程。'
---

# 新增角色工作流

## 核心原则

1. **数据驱动优先**：新角色优先在 `src/data/characters.py` 以数据方式定义，只有确实需要特殊行为时才修改 `src/core/battle_*.py`。
2. **不改动 BattleSession 结构**：不要为了新增机制把已拆分的 `BattleSession` 重新塞回 `battle.py`，优先放入对应 mixin。
3. **内部效果默认不显示**：新内部 effect id 如果不是用户明确要求显示的关键词，设置 `show_in_encyclopedia=False`。
4. **保持外部接口不变**：尤其是 UI 和测试正在调用的 `BattleSession` 方法。

---

## 需求文档格式约定

用户描述新角色时通常使用以下格式：

```
角色名 职业 生命 攻击 效果 阵营
```

- **`【】`** 包裹 → 整局一次的主动技能（`ActiveSkill.once_per_game=True`）
- **`（）`** 包裹 → 普通主动技能（非整局一次）
- **无括号** → 被动效果
- 技能没有明确目标限制 → 默认可选任意存活角色（不受前后排/敌我限制），前后排规则 **只影响普通攻击**
- `factions` 是阵营，如 `狼`、`龙`、`自然`、`奥术`、`圣职`

---

## 角色定义（`src/data/characters.py`）

### CharacterDefinition

```python
CharacterDefinition(
    id="角色id",           # 唯一标识，snake_case
    name="角色名",          # 显示名称
    job_id="职业id",        # 引用 JOBS_BY_ID 中的职业
    max_health=生命值,
    attack=攻击力,
    skill_description="主动技能描述",
    passive_description="被动描述",  # 没有则 ""
    factions=("阵营",),     # 没有则 ()
    passive_effect_ids=("effect_id",),  # 被动关联的效果 ID
    active_effect_ids=("effect_id",),   # 主动技能关联的效果 ID
    active_skills=(...),    # ActiveSkill 元组
)
```

### ActiveSkill

```python
ActiveSkill(
    id="技能id",
    name="技能名",
    description="简短描述",
    display_text="百科/UI显示的完整文本",
    kind=SkillKind.XXX,      # DAMAGE/HEAL/ARMOR/ATTACK_BUFF/CUSTOM 等
    target=SkillTarget.ANY,  # ANY/ALLY/ENEMY/SELF
    once_per_game=True/False,
    # 按需: damage, heal, armor, attack_bonus, health_bonus,
    #       attack_percent, target_reflect_percent, min_targets, max_targets 等
)
```

### 角色池管理

- `CHARACTER_DEFINITIONS`：正式角色池
- `TEST_CHARACTER_DEFINITIONS`：旧测试角色池，**不应混入正式选角**
- `create_draft_character_pool()`：排除 `job_id == "summon"` 的召唤物（召唤物可放在 `CHARACTER_DEFINITIONS` 中但不会进入选角）
- `create_draft_character_pool(include_arcanarch=False)`：默认排除 `job_id == "arcanarch"` 的帝法者；设置页有开关控制
- 修改器角色列表始终使用完整 `CHARACTER_DEFINITIONS`

---

## 关键词与效果（`src/data/keywords.py`）

```python
Effect(
    id="effect_id",                    # 唯一标识
    name="显示名",
    category=EffectCategory.KEYWORD,   # KEYWORD / BUFF / DEBUFF
    description="百科描述",
    is_adverse=False,                  # 是否为不利效果
    show_in_encyclopedia=True,         # 内部实现用 → False
)
```

- `EffectCategory.KEYWORD`：关键词/机制解释
- `EffectCategory.BUFF`：增益效果
- `EffectCategory.DEBUFF`：减益效果
- `is_adverse=True`：标记为不利效果（影响制作者免疫、净化等）
- 为后端实现创建的内部 effect id，设置 `show_in_encyclopedia=False`

---

## 百科条目（`src/data/encyclopedia.py`）

### 角色机制解释

```python
CHARACTER_MECHANIC_DETAILS: dict[str, tuple[str, ...]] = {
    "角色id": (
        "角色名：机制解释第一行。",
        "角色名：机制解释第二行。",
    ),
}
```

### 百科显示约定

- 角色详情简洁展示：职业效果一行 → 被动一行（无则"无"）→ 主动技能每行一个
- 角色机制解释显示在角色详情中，不出现在战斗详情栏
- 百科关键词只包含需求文档明确给出的关键词；内部 effect id 设 `show_in_encyclopedia=False`
- 机制解释栏目收纳角色外的名词/规则/流程解释

---

## 战斗机制实现（`src/core/battle_*.py`）

按功能领域选择对应 mixin 文件：

| 文件 | 负责内容 |
|------|----------|
| `battle_attacks.py` | 攻击目标选择、攻击/受伤结算、反伤、暴击、追击、剑圣选择 |
| `battle_skills.py` | 主动技能可用性、目标校验、释放流程、自定义技能 |
| `battle_effects.py` | 死亡触发、对战开始被动、光环、召唤、强制选择队列 |
| `battle_turns.py` | 回合、移动顺序、跳过、解冻、后手技能 |
| `battle_debug.py` | 测试/修改器相关战斗操作 |
| `battle_results.py` | 结果 dataclass（AttackResult、SkillResult、DamageEvent 等） |
| `battle_errors.py` | 战斗异常定义 |

### 关键结算流程

**受伤结算顺序**（`_resolve_damage()`）：
1. 免疫 → 2. 护盾 → 3. 屏障 → 4. 抵御 → 5. 流血/受伤修正 → 6. 实际扣血 + 受伤触发

- 免疫在抵御之前：有免疫的角色不会被抵御者替其承伤
- 伤害为 0 不消耗护盾，也不触发"受到伤害后"效果
- 受伤 -50% 与受伤 -1 同时存在时：各自按原伤害分别计算

**死亡结算**：
- 死亡检测与触发在完整攻击/技能流程结束后进行，非每段中途插入（除非机制明确要求强制插入）
- 结算顺序：当前移动方 > 另一玩家方；前排 > 后排；上方 > 下方

**反伤与抵御**：
- 反伤走完整"造成伤害流程"（`_resolve_damage()`）
- 攻击被抵御的角色时，反伤来源仍是原始被攻击角色（非抵御者）
- 直接击杀目标也产生反伤；反伤判断使用攻击上下文中的目标效果

### 强制选择队列

`pending_death_triggers` 承担多种强制目标选择：

| kind | 说明 |
|------|------|
| `damage` | 造成伤害选择 |
| `attack_buff` | 攻击增益选择 |
| `damage_prophecy` | 预言伤害选择 |
| `heal` | 治疗选择 |
| `mirror_copy` | 镜像复制（不可跳过） |

- 剑圣选择和只狼追击不走此队列，分别使用 `pending_sword_saint_choices` 与 `pending_chase_choices`

### 特殊机制注意事项

- **沉默**：职业效果不受沉默影响；角色自身被动/主动技能受沉默影响。实现上在沉默判断前放行 `character.job.effect_ids`
- **嘲讽**："排"指前排/后排（竖着的 3 个位置）。同排嘲讽 = 同一前排或同一后排，非横行
- **抵御范围**：周围四格
- **无法被抵御**：伤害不会被抵御效果转移
- **复活**：清空所有非光环状态，恢复初始生命值/上限/攻击力/技能状态/职业配置，再重算光环加成
- **光环效果**：先获得先结算。如苍翾鹤沉默光环（攻击时产生）vs 战斗机甲光环（开局时产生）：先战斗机甲→再被沉默→攻击结束后恢复

---

## 测试（`src/tests/`）

### 测试文件对应

| 测试文件 | 覆盖范围 |
|----------|----------|
| `test_battle_rules.py` | 基础战斗规则 |
| `test_new_characters.py` | `newCharacter.md`、`newCharacter2.md` 角色机制 |
| `test_new_character3.py` | `newCharacter3.md` 角色机制 |
| `test_encyclopedia_screen.py` | 百科 UI 与显示规则 |
| `test_battle_ui_layout.py` | 战斗界面布局和交互 |
| `test_tester_modifier.py` | 修改器能力 |

### 运行测试

```powershell
# 完整测试（当前基线: 180 tests OK）
$env:PYTHONDONTWRITEBYTECODE='1'; .\.venv\Scripts\python.exe -B -m unittest discover -s src\tests

# 聚焦测试
.\.venv\Scripts\python.exe -B -m unittest src.tests.test_new_characters
.\.venv\Scripts\python.exe -B -m unittest src.tests.test_new_character3
```

- 新增角色必须补充对应规则测试
- 改动战斗规则优先补单元测试 → 聚焦测试 → 完整测试

---

## UI 约定（`src/ui/`）

### 文件分工

| 文件 | 负责内容 |
|------|----------|
| `game_screen.py` | 选角、排阵、战斗主界面与交互逻辑 |
| `game_screen_animations.py` | 战斗动画队列、生命变化数字、刀光（`GameScreenAnimationMixin`） |
| `game_screen_tester.py` | 修改器窗口/控件/事件（`GameScreenTesterMixin`） |
| `components.py` | 按钮、滚动区域等基础组件 |
| `encyclopedia_screen.py` | 百科大全 |
| `settings_screen.py` | 设置页 |

### 易踩坑点

- 标题应尽量小，与描述放在顶栏
- 选角和百科中角色按职业排序，左侧有职业筛选
- 角色过多时必须有滚动
- 战斗日志可滚动；点击小日志打开大日志栏翻阅
- 不要主动弹出大日志栏
- 战斗界面角色卡须显示攻击力
- 双方前排相对：右侧玩家前排显示在左边，左侧玩家前排显示在右边
- 行动按钮"可用才显示"动态列表；按钮过多时滚动
- 避免灰色背景，整体视觉精致但不改规则语义

### 动画系统

- 全局开关在 `src/user_settings.py`，设置页切换
- `AttackAnimation` 队列播放期间 `handle_event()` 忽略输入
- `DamageEvent` 在 `_resolve_damage()` 实际造成正数伤害时记录
- UI 动画以动作前后生命快照生成 `HealthChangeEvent`：负数红色，正数绿色；攻击动作显示刀光
- 暴击伤害数字亮黄色 + "暴击"文字；反伤/剧毒等非本次暴击不误标
- 不要用日志文本解析生命变化动画
- 新增"指定目标后攻击"流程须排入带刀光的生命变化动画

---

## 新增角色检查清单

每新增一个角色，确认以下文件是否需要修改：

- [ ] `src/data/characters.py` — CharacterDefinition + ActiveSkill 定义
- [ ] `src/data/keywords.py` — 新 Effect（关键词/buff/debuff）
- [ ] `src/data/encyclopedia.py` — CHARACTER_MECHANIC_DETAILS、百科条目
- [ ] `src/core/battle_attacks.py` — 攻击/受伤/反伤特殊逻辑
- [ ] `src/core/battle_skills.py` — 自定义技能释放逻辑
- [ ] `src/core/battle_effects.py` — 光环/死亡触发/召唤/强制选择
- [ ] `src/core/battle_turns.py` — 移动/回合特殊规则
- [ ] `src/tests/` — 至少一个聚焦测试方法

---

## 参考：技能类型 (SkillKind)

| 值 | 说明 |
|----|------|
| `DAMAGE` | 直接伤害技能 |
| `STATUS` | 施加状态技能 |
| `HEAL` | 治疗技能 |
| `ARMOR` | 护甲技能 |
| `ATTACK_BUFF` | 攻击增益技能 |
| `HEALTH_BUFF_RANK` | 同排生命增益 |
| `ATTACK` | 增强攻击技能 |
| `CUSTOM` | 自定义技能（需在 battle_skills.py 中实现） |

## 参考：技能目标 (SkillTarget)

| 值 | 说明 |
|----|------|
| `ANY` | 任意角色 |
| `ALLY` | 友方角色 |
| `ENEMY` | 敌方角色 |
| `SELF` | 自身 |
