# AI 接手交接文档

本文档用于把当前项目交接给新的 AI 工具或新的开发者。目标是让接手方不依赖历史对话，也能快速理解项目结构、规则约定、已实现机制、测试方式和当前待办。

## 1. 项目概览

- 项目是一个本地 Python + Pygame 双人战棋/卡牌式对战游戏。
- 入口文件是 `main.py`，应用主类在 `src/app.py`。
- 当前主要玩法流程为：主页 -> 选角 -> 排阵 -> 战斗 -> 结算；另有百科大全、设置、测试/修改器相关能力。
- 需求文档集中在 `require/`：
  - `require.md`：基础规则、最初关键词与角色/职业说明。
  - `require2.md`：界面与后续优化需求。
  - `require3.md`：攻击、受伤、死亡、依次结算等关键流程。
  - `newCharacter.md`、`newCharacter2.md`、`newCharacter3.md`：新增角色、关键词和机制解释。
  - `tester.md`：测试/修改器能力。
  - `bug.md`：当前或最近的修复项。
  - `development_process.md`：阶段化开发记录。
- 用户通常用中文描述需求，交付文档和解释也应优先使用中文。

## 2. 运行与测试

- 依赖很少，`requirements.txt` 当前只有 `pygame==2.6.1`。
- 推荐使用项目已有虚拟环境运行：

```powershell
.\.venv\Scripts\python.exe -B main.py
```

- 完整单元测试命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; .\.venv\Scripts\python.exe -B -m unittest discover -s src\tests
```

- 常用聚焦测试：

```powershell
.\.venv\Scripts\python.exe -B -m unittest src.tests.test_battle_rules
.\.venv\Scripts\python.exe -B -m unittest src.tests.test_new_characters
.\.venv\Scripts\python.exe -B -m unittest src.tests.test_new_character3
.\.venv\Scripts\python.exe -B -m unittest src.tests.test_tester_modifier
```

- 最近一次已知完整测试状态：实现 `newCharacter3.md` 中无畏、狂暴炸弹师、重力/虚弱/激怒、章鱼等新角色与机制后，完整测试为 `180 tests OK`。
- 本工作区当前不是 git 仓库，`git status` 会失败；不要依赖 git diff 来判断变更。

## 3. 代码结构

### UI 层

- `src/ui/home_screen.py`：主页。
- `src/ui/game_screen.py`：选角、排阵、战斗主界面，大量交互逻辑在这里。
- `src/ui/game_screen_animations.py`：战斗动画队列、生命变化数字、刀光绘制等表现层逻辑；通过 `GameScreenAnimationMixin` 混入主界面。
- `src/ui/game_screen_tester.py`：战斗修改器窗口、修改器下拉框和修改器事件处理；通过 `GameScreenTesterMixin` 混入主界面。
- `src/ui/encyclopedia_screen.py`：百科大全。
- `src/ui/settings_screen.py`：设置页。
- `src/ui/components.py`：按钮、滚动区域等基础组件。
- `src/ui/screen_manager.py`：界面切换。

### 核心规则层

- `src/core/models.py`：核心数据模型，例如 `GameState`、`Player`、`Character`、`ActiveSkill`、`Job`、`Position`。
- `src/core/draft.py`：选角流程。
- `src/core/formation.py`：排阵流程与位置限制。
- `src/core/battle.py`：`BattleSession` 编排类，保存战斗状态并组合多个 mixin。
- `src/core/battle_attacks.py`：攻击目标选择、攻击结算、受伤结算、反伤、暴击、追击、剑圣选择等。
- `src/core/battle_skills.py`：主动技能可用性、目标校验、释放流程、各类自定义技能。
- `src/core/battle_effects.py`：死亡触发、对战开始被动、光环、召唤、强制选择队列、通用效果判断。
- `src/core/battle_turns.py`：回合、移动顺序、跳过、解冻、后手技能。
- `src/core/battle_debug.py`：测试/修改器相关战斗操作。
- `src/core/battle_results.py`：各种结果 dataclass。
- `src/core/battle_errors.py`：战斗异常。

### 数据层

- `src/data/characters.py`：正式角色、测试角色、召唤物、主动技能定义。
- `src/data/jobs.py`：职业定义、职业效果和站位限制。
- `src/data/keywords.py`：关键词、buff、debuff、内部效果定义。
- `src/data/encyclopedia.py`：百科额外条目、角色机制解释等。

### 测试层

- `src/tests/test_battle_rules.py`：基础战斗规则。
- `src/tests/test_new_characters.py`：`newCharacter.md`、`newCharacter2.md` 中大量角色机制。
- `src/tests/test_new_character3.py`：`newCharacter3.md` 相关机制。
- `src/tests/test_encyclopedia_screen.py`：百科 UI 与显示规则。
- `src/tests/test_battle_ui_layout.py`：战斗界面布局和部分交互。
- `src/tests/test_tester_modifier.py`：修改器能力。

## 4. 数据与文档约定

- 角色文档常用格式：

```text
角色名 职业 生命 攻击 效果 阵营
```

- `【】` 表示整局一次的主动技能，通常对应 `ActiveSkill.once_per_game=True`。
- `（）` 表示主动技能，但通常不是整局一次。
- 没有括号包裹的效果默认视为被动效果。
- 如果技能没有明确目标限制，则默认可以选择任意存活角色，不受前排/后排攻击规则限制，也不限制敌我；前后排规则只影响普通攻击。
- `factions` 是阵营，例如 `狼`、`龙`、`自然`、`奥术`、`圣职`。
- `CHARACTER_DEFINITIONS` 是正式角色池。
- `TEST_CHARACTER_DEFINITIONS` 是旧测试角色池，不应混入正式选角池。
- `create_draft_character_pool()` 会排除 `job_id == "summon"` 的召唤物；召唤物可以放在 `CHARACTER_DEFINITIONS` 中，但不会进入选角。
- `create_draft_character_pool(include_arcanarch=False)` 默认也会排除 `job_id == "arcanarch"` 的帝法者。设置页有“选角帝法者：显示/隐藏”开关，新一局选角池按该设置生成；测试/修改器角色列表始终使用完整 `CHARACTER_DEFINITIONS`。
- 新增角色时通常需要同时考虑：
  - `src/data/characters.py`：角色与主动技能定义。
  - `src/data/keywords.py`：新关键词、buff、debuff 或内部效果 id。
  - `src/core/battle_*.py`：实际机制实现。
  - `src/data/encyclopedia.py`：机制解释或额外百科条目。
  - `src/tests/`：至少补对应规则测试。

## 5. 百科与关键词显示约定

- 百科角色详情应简洁展示：
  - 职业效果一行。
  - 角色被动技能一行；没有则写“无”。
  - 主动技能若干行；一行一个主动技能。
  - 角色机制解释可以显示在角色详情中，但不需要出现在战斗详情栏。
- 百科中显示的关键词应只包含需求文档中明确给出的关键词；为了后端实现创建的内部 effect id，通常应设置 `show_in_encyclopedia=False`。
- 当前百科还有一个机制解释栏目，用于收纳角色外的名词解释、规则解释、流程解释等。
- 战斗界面右侧详情栏需要显示完整属性、状态、被动、主动技能效果；内容较长时允许滚动。

## 6. 关键战斗规则

### 攻击结算

根据 `require3.md`，攻击造成伤害结算流程为：

1. 确定攻击者与被攻击目标。
2. 验证目标合法性。
3. 计算攻击者攻击力，例如攻击时攻击力增加。
4. 计算基础伤害，例如暴击、攻击造成 200% 攻击力伤害。
5. 使用基础伤害与被攻击目标进入受伤结算流程。
6. 造成反伤。
7. 攻击结束。

当一段攻击造成多段伤害时，按描述顺序依次结算每段伤害。当被攻击目标为多个时，对每个目标依次执行后续步骤。

### 受伤结算

当前规则以 `require3.md` 为准：

1. 先计算免疫。
2. 再计算护盾；护盾在免疫之后、屏障和抵御之前结算。
3. 再计算屏障。
4. 再计算抵御；抵御会把后续受伤角色转移为抵御者。
5. 再计算流血、受伤 +1、受伤 -1、受伤 -50%、受伤 +50% 等修正。
6. 最后实际扣血，并计算受伤触发效果。

注意：免疫在抵御之前。因此具有免疫的角色不会被抵御者替其承伤，而是直接免疫伤害。
护盾层数保存在 `BattleSession.shield_stacks`，角色状态中仍保留 `shield` 用于显示和效果判断。伤害为 0 的伤害不会消耗护盾，也不会触发“受到伤害后”效果。
受伤 -50% 与受伤 -1 同时存在时，二者都按进入减伤前的原伤害分别计算；若还有“受伤不小于 1”的效果，则最终正伤害不低于 1。

### 死亡结算

- 死亡检测与死亡触发应在一个完整攻击流程或技能释放流程结束后进行，而不是每段中途立即插入，除非该机制明确设计为强制插入选择。
- 依次结算顺序为：当前移动玩家方 > 另一玩家方；前排 > 后排；上方 > 下方。
- 相关排序工具可参考 `_ordered_battle_character_refs`。

### 反伤与抵御

- 反伤应该走“造成伤害流程”，也就是会进入 `_resolve_damage()` 并计算免疫、屏障、抵御、受伤修正等。
- 曾修复过的问题：攻击被抵御的角色时，反伤来源仍应是原始被攻击角色，而不是抵御者；抵御只转移受伤结算，不转移攻击结算。
- 直接击杀目标也会产生反伤。反伤效果判断使用攻击上下文中的目标效果，不因目标刚死亡而消失。
- 对“击杀后”类效果，当前实现保留攻击主要伤害结算后、反伤前的攻击者存活时点；例如纵火者击杀带反伤目标时，即使随后被反伤击杀，纵火仍会触发。

### 抵御与嘲讽

- “排”指前排/后排，每排是显示上竖着的 3 个位置。
- 守护者同排嘲讽中的“同排”是同一个前排或同一个后排，不是显示上的横行。
- 抵御者抵御范围为周围四格。
- 若一个角色被多个不同角色抵御，每个抵御者都会受伤。
- “无法被抵御”表示伤害不会被抵御效果转移。

### 移动与回合

- 历史移动顺序保存在 `move_orders` 和 `round_resolved_order_slots`。
- 跳过会消耗一次移动。
- 冻结角色不能攻击或放技能，但可以选择解冻，也可以正常跳过回合。
- 阵法家效果 `move_order_independent` 表示不受历史移动顺序约束，但仍受移动次数、回合归属等限制。
- 后手技能相关逻辑在 `battle_turns.py`，蚀时狼妃存活且未被沉默时会让拥有后手技能的一方在每个新轮次重置后手技能使用状态。
- 如果同一方场上同时拥有定序王子和蚀时狼妃，`BattleSession` 会先进入 `pending_start_order_choice_player_id` 状态；UI 右侧栏显示“选择先手/选择后手”。调用 `choose_start_order()` 后，才会执行“游戏开始时”被动，例如镜像复制。
- 职业效果不受沉默影响；角色自身被动、主动技能仍受沉默影响。实现上 `_character_has_battle_effect()` 与攻击上下文反伤判断会在沉默前放行 `character.job.effect_ids`。

## 7. 强制选择队列

- `pending_death_triggers` 名字仍保留为“死亡触发”，但现在实际承担多种强制目标选择：
  - `damage`
  - `attack_buff`
  - `damage_prophecy`
  - `heal`
  - `mirror_copy`
- UI 文案在 `game_screen.py` 中按 kind 映射，例如 `mirror_copy` 显示为“镜像复制”。
- `resolve_death_trigger()` 在 `battle_effects.py` 中处理这些强制选择。
- 某些强制选择可跳过，某些不可跳过；例如镜像复制不能传 `None` 跳过。
- 剑圣选择和只狼追击不是走 `pending_death_triggers`，而是分别使用 `pending_sword_saint_choices` 与 `pending_chase_choices`。

## 8. 镜像技能当前实现

- 镜像的技能是：对战开始时，选择一个其他友方角色，获得其所有技能。
- 当前实现不是自动复制，而是在对战开始时插入一个强制选角色结算。
- `_apply_battle_start_passives()` 会为镜像加入 `DeathTrigger(kind="mirror_copy")`。
- `death_trigger_targets()` 对 `mirror_copy` 特判：只能选其他存活友方角色。
- `can_resolve_death_trigger(None)` 对 `mirror_copy` 返回 `False`，即不能跳过。
- 复制内容包括目标角色的角色被动、主动效果 id 和主动技能；不复制职业效果。
- 因为镜像复制发生在对战开始被动之后，所以复制到的“对战开始时”效果不会再触发。
- 所有镜像复制结算完后，回合应恢复到正常先手玩家。

## 9. 已实现的重要机制索引

- 老王八：首回合为其他友方角色提供免疫；自身全体嘲讽、无法被抵御、只能前排。
- 苍翾鹤：必须攻击攻击力最低的敌方角色，并无视嘲讽；可以攻击后排；攻击时清除目标加成。
- 猎龙者：只能杀死龙；攻击非龙目标时会给目标临时不死，避免杀死。
- 不死/临时不死：应阻止强制死亡，并保持生命至少为 1。
- 吸血鬼：攻击流血目标时暴击，攻击后按造成伤害回血。
- 血法师：存活时，敌方角色的流血不视为不利效果；免疫不利效果和净化等逻辑要用上下文判断。
- 阵法家：不受历史移动顺序约束。
- 复仇吹笛者：释放前检查所有可选敌人是否已迷惑；若是则改为对所有迷惑敌人造成伤害，且不需要再指定目标。
- 工匠：先 -3 生命；如果因此死亡，不继续攻击。
- 调皮的猴子：在友方前排所有空位召唤香蕉。
- 战斗牧师：攻击后插入治疗目标选择。
- 狼人预言家：自身以任意方式造成伤害后累计伤害量，每累计 6 点插入一次 +3 攻击目标选择，每局至多 2 次。
- 冰川：攻击后冻结目标。
- 蜘蛛：造成伤害后让受到伤害的角色减少等量生命上限。
- 护盾法师：创建队伍屏障，屏障在抵御之前吸收伤害。
- 只狼：追击选择单独排队，不走死亡触发队列。
- 剑圣：攻击后的二选一手动结算单独排队。
- 帝法者：新增职业 `arcanarch`，职业效果为无；百科职业顺序放在召唤物之后。
- 复活通用规则：永恒狼骨、终焉以及后续默认复活角色，复活时应清空所有非光环状态，并恢复初始生命值、生命上限、攻击力、技能使用状态、基础职业与基础技能配置；之后再重新计算光环生命加成。
- 终焉：`ending_after_attack` 使其攻击后失去 1 点生命上限并 +2 攻击；`eternal_revival` 负责死亡后待复活；`revive_skip_turn` 表示待复活的终焉在自己的移动按钮栏显示“复活”。点击“复活”会复活并消耗本次移动，不能攻击或放技能；点击“跳过”不会复活，待复活状态保留到后续可行动轮次。
- 太阳守卫：同排嘲讽、受伤 -50%、受到正数伤害后获得一层护盾。护盾是可叠层 buff，修改器施加护盾会增加层数。
- 定序王子 + 蚀时狼妃：单独存在时分别强制先手/后手；同一方同时拥有时，由该方在对战界面刚进入时选择自己先手或后手，然后再结算游戏开始时技能。
- 无畏：攻击不具有自身嘲讽效果（同排嘲讽/全体嘲讽）的敌方角色后，返还 1 次移动次数；每局至多返还 3 次。
- 狂暴炸弹师：主动技能需要执行 8 次目标选择，允许同一角色被重复选择；结算时按角色聚合为一次伤害，所以受伤修正只结算一次。选择敌方角色时不套普通攻击前后排限制，但要经过嘲讽过滤。
- 重力：以层数记录在 `BattleSession.gravity_stacks`；每层使自身攻击时目标额外获得反伤 50%。净化或清除重力时必须同步清理层数。
- 虚弱：状态 `weak`，任何计算攻击力时最终攻击力再乘 50%，在每轮开始时清除。
- 激怒：状态 `enraged`，来源记录在 `BattleSession.enrage_sources`。被激怒角色攻击或选择技能目标时强制以施加激怒的“挑衅”为目标；多目标技能必须先选挑衅，再选其他合法目标。激怒在每轮开始时清除。
- 挑衅：主动技能给敌方角色施加本回合激怒；自身受到该激怒角色造成的伤害 -50%。
- 导师：存活时，敌人杀死导师友方单位后，杀死者获得 1 层重力；主动技能给目标及其周围同阵营友方角色各 1 层重力。
- 章鱼：主动技能插入召唤触手；触手召唤完成后当前行动权保持在召唤方，使触手可以立即移动。

## 10. UI 约定与易踩坑

- 所有界面的标题应尽量小，并与描述放在顶栏，以减少对主体内容的占位。
- 选角和百科中角色应按职业排序，且左侧有职业筛选。
- 角色过多时，选角界面必须有滚动，不应超出框外。
- 战斗日志应可滚动；点击小日志区域应打开一个完整的大日志栏用于翻阅，而不是展开单条日志。
- 日志文字超出一行时不能覆盖下一行，需要按实际文本高度排版。
- 不要主动弹出大日志栏。
- 战斗界面角色卡应显示攻击力。
- 右侧玩家的前排应显示在左边，左侧玩家的前排应显示在右边，使双方前排相对。
- 修改器中的十二阵位也要遵守双方前排相对：左侧玩家后排在左、前排在右；右侧玩家前排在左、后排在右。
- 战斗右侧行动按钮采用“可用才显示”的动态列表：普通可行动角色显示攻击/跳过，有可用主动技能才显示技能，被冻结才显示解冻，待复活终焉才显示复活。按钮过多时使用行动按钮栏滚动。
- 前端避免灰色背景，整体视觉应更精致，但不要改动规则语义。

### 动画系统

- 全局动画开关在 `src/user_settings.py`，设置页 `SettingsScreen` 通过“动画：开启/关闭”按钮切换。
- 战斗表现层动画在 `src/ui/game_screen_animations.py` 中维护，当前有 `AttackAnimation` 队列；播放期间 `GameScreen.handle_event()` 会忽略输入，避免动画中重复点击按钮造成状态错乱。
- `AttackResult`、`SkillResult`、`ChaseResult`、`DeathTriggerResult` 现在都有 `damage_events` 字段，元素是 `DamageEvent(player_id, character_id, damage, critical=False)`。
- `DamageEvent` 在 `_resolve_damage()` 实际造成正数伤害时记录，因此可以覆盖普通攻击、抵御后的实际承伤者、反伤、溅射、剧毒等走受伤流程的伤害。
- UI 动画现在以动作前后的场上角色当前生命快照为准，生成 `HealthChangeEvent`。负数显示红色，正数显示绿色；攻击类动作额外显示刀光。
- 暴击攻击产生的 `DamageEvent.critical=True` 会传到 `HealthChangeEvent.critical`，动画中伤害数字改为亮黄色并额外显示“暴击”。反伤、剧毒等非本次暴击攻击伤害不应误标为暴击。
- 不要用日志文本解析生命变化动画。新增会改变生命的玩家按钮操作时，应在 UI 动作前后调用生命快照并排入动画。
- 如果新增一种“用户指定目标后进行攻击”的流程，应排入带刀光的生命变化动画，或复用已有的攻击/追击入口。

## 11. 测试/修改器上下文

- 修改器来自 `require/tester.md`，相关代码主要在 `battle_debug.py` 和 `game_screen.py`。
- UI 层修改器代码已拆到 `src/ui/game_screen_tester.py`；核心调试能力仍在 `src/core/battle_debug.py`。
- 修改器应能便捷选择角色、debuff、buff，之前已加入下拉或类似选择控件。
- 修改器可施加 debuff，也可施加 buff。
- 修改器改动容易影响 UI 测试和战斗状态，请补充或运行 `test_tester_modifier.py`。

## 12. 接手开发建议

1. 先读最新用户打开或指定的需求文件，例如 `require/bug.md` 或 `require/newCharacter3.md`。
2. 再用 `rg` 搜索相关角色 id、技能 id、effect id，确认已有实现位置。
3. 新角色优先以数据驱动方式加入 `characters.py`，只有确实需要特殊行为时再改 `battle_*.py`。
4. 新内部效果 id 如果不是用户明确要求显示的关键词，默认不要在百科关键词列表显示。
5. 改战斗规则时优先补单元测试，再跑对应聚焦测试，最后跑完整测试。
6. 改 UI 时注意滚动、长文本换行、左右玩家镜像显示和战斗详情栏。
7. 不要为了新增机制把已经拆开的 `BattleSession` 重新塞回 `battle.py`；优先放入对应 mixin。
8. 尽量保持外部接口不变，尤其是 UI 和测试正在调用的 `BattleSession` 方法。

## 13. 当前待确认事项

- 项目中存在 `__pycache__` 文件，但它们不是源代码；接手时可以忽略。
- 因当前工作区不是 git 仓库，交接时无法依靠提交历史追踪来源，需要以需求文档、测试和源码为准。
