# 记忆与一致性规格 v0.2

> 状态：Implemented（M3 + M3.5 长线记忆 + M4 T4-0 管线接入） · 更新：2026-11-01
> 对应里程碑：M3 / M3.5。表结构、抽取契约、组装顺序是实现契约。

## 1. 目标

让上下文长度**不随章节数线性增长**，并让跨章硬错误（死人复活、物品超用、信息越界、伏笔状态错乱）在定稿前被拦住。

M3.5 追加目标：**长线伏笔和世界设定不能因为“最近 8 条”窗口而被静默遗忘**。做法不是把全部旧内容塞回 prompt，而是给伏笔登记重要度、目标回收章、最近推进章，让到期/高重要/刚推进的线优先回到上下文；世界规则单独常驻。

非目标：

- 不做 Neo4j / 图谱数据库；
- 不做向量检索；
- 不做全自动事实修正（只阻断，不改写）。

## 2. 存储

PostgreSQL 16，单实例。初期不引入 Redis / Milvus。

### 表结构（最小集）

```sql
projects (
  id uuid primary key,
  title text not null,
  genre text not null,
  target_chapters int,
  created_at timestamptz default now()
)

chapters (
  id uuid primary key,
  project_id uuid references projects(id),
  seq int not null,
  status text not null,          -- planned/trial/generating/pending/final
  title text,
  content text,
  summary text,                  -- <=200 字
  score int,
  rewrite_count int default 0,
  review_json jsonb,             -- 待确认原因；定稿/重写时清空
  created_at timestamptz default now(),
  unique(project_id, seq)
)

characters (
  id uuid primary key,
  project_id uuid references projects(id),
  name text not null,
  alive boolean default true,
  status text,                   -- 当前身份/位置/目标
  core_attributes jsonb default '{}',
  first_chapter int,
  last_chapter int,
  unique(project_id, name)
)

character_events (
  id uuid primary key,
  character_id uuid references characters(id),
  chapter_seq int not null,
  event_summary text not null,
  story_time text,               -- 故事内时间
  created_at timestamptz default now()
)

ledger_items (
  id uuid primary key,
  project_id uuid references projects(id),
  name text not null,
  quantity numeric not null default 0,
  unit text,
  updated_chapter int,
  unique(project_id, name)
)

ledger_item_aliases (
  project_id uuid references projects(id),
  alias text not null,
  canonical_name text not null,
  primary key (project_id, alias)
)

ledger_info_gap (
  id uuid primary key,
  project_id uuid references projects(id),
  character_id uuid references characters(id),
  known_facts jsonb default '[]',
  unknown_facts jsonb default '[]',
  updated_chapter int,
  unique(project_id, character_id)
)

foreshadowing (
  id uuid primary key,
  project_id uuid references projects(id),
  title text not null,
  planted_chapter int not null,
  resolved_chapter int,
  status text not null default 'planted',  -- planted/resolved/abandoned
  notes text,
  importance int not null default 1 check (importance between 1 and 5),
  target_chapter int,             -- 计划回收章，null = 未排期
  last_touched_chapter int        -- 最近推进/回收章
)

emotional_threads (
  id uuid primary key,
  project_id uuid references projects(id),
  title text not null,              -- 例如“沈砚欠阿棠一个解释”
  debt_from text not null,          -- 谁欠
  debt_to text not null,            -- 欠谁
  kind text not null default 'other', -- approval/apology/belonging/recognition/rescue/other
  setup_chapter int not null,       -- 第几章欠下
  target_payoff_chapter int,        -- 计划第几章还，null = 未排期
  status text not null default 'open', -- open/paid/abandoned
  importance int not null default 3 check (importance between 1 and 5),
  last_touched_chapter int,
  notes text,
  unique(project_id, title)
)

world_rules (
  id uuid primary key,
  project_id uuid references projects(id),
  name text not null,
  content text not null,
  importance int not null default 3 check (importance between 1 and 5),
  source_chapter int,
  updated_chapter int,
  status text not null default 'active',  -- active/deprecated
  unique(project_id, name)
)

quality_failures (
  id uuid primary key,
  chapter_id uuid references chapters(id),
  layer text not null,           -- hard_gate/score/consistency
  rule_id text not null,
  severity text not null,
  evidence text,
  resolved boolean default false,
  created_at timestamptz default now()
)

confirmations (
  id uuid primary key,
  chapter_id uuid references chapters(id),
  gate_type text not null,       -- outline/trial/quality
  decision text not null,
  created_at timestamptz default now()
)
```

索引：`chapters(project_id, seq)`、`characters(project_id, name)`、`foreshadowing(project_id, status)`、`emotional_threads(project_id, status)`、`world_rules(project_id, status)`、`quality_failures(chapter_id)`。

## 3. 记忆抽取契约

每章定稿后触发 **Memory Extractor**。输入：本章正文 + 现有结构化事实；输出严格 JSON。

```json
{
  "character_updates": [
    {
      "name": "张三",
      "alive": true,
      "status": "当前状态",
      "attributes_delta": {"key": "value"},
      "event_summary": "本章发生的关键事件",
      "story_time": "故事内时间",
      "confidence": 0.9
    }
  ],
  "item_usage": [
    {
      "name": "回魂丹",
      "delta": -1,
      "action": "consume",           // gain/consume/transfer/partial/other
      "reason": "救人"
    }
  ],
  "info_gains": [
    {"character": "张三", "facts": ["得知城主是内奸"]}
  ],
  "foreshadowing": [
    {
      "action": "plant",              // plant/advance/resolve/abandon
      "title": "青铜钥匙",
      "importance": 5,                // 1–5，5 最重要
      "target_chapter": 35,           // 计划回收章，可空
      "thread_id": null,              // 推进/回收时优先用稳定 id
      "notes": "第 3 章首次出现"
    }
  ],
  "chapter_summary": "<=200 字",
  "key_events": ["事件 1", "事件 2"]
}
```

校验规则：

- Pydantic 严格校验；字段缺失/类型错误 = 抽取失败，进人工确认；
- 未知角色/物品**不自动创建**，标记 `needs_review`；但 `蒙面人/黑衣人/守卫/宾客` 等场景泛称不算新角色，直接跳过（`generic_role`），避免每章出现一次“蒙面人”就卡成待确认；
- `confidence < 0.7` 的条目只记录、不写账本；
- `item_usage` 增加 `action`；账本已有同一物品时，“半张/半块/一角/残片/一部分”只标记 `partial`，数量不变。即使模型漏填 `action`，正数增量加上部分量词也会被识别为 `partial_item` 并跳过，避免把“半张城防图”记成第二张；
- 物品名先按账本标准名精确查，查不到再查 `ledger_item_aliases` 的一跳别名（如 `青布小包` → `金疮药`）。别名必须由人工配置，标准名必须已存在；仍查不到才进 `unknown_item`；
- 负增量会让库存小于 0 时不写账本，记 `negative_stock` 跳过；正增量仍正常记账。`adjust_ledger` 本身保留写负数的能力，供测试和人工修正；
- 情感债 `emotional_threads` 目前**只由规划层/人工登记**，抽取器不自动创建或偿还；`ScenePlan.debt_paid/debt_opened` 只是单章提示，不直接改账本；
- 抽取结果写入前做噪声上限：状态 80 字、属性 8 键/值 40 字、单组事实 5 条/条 60 字、新伏笔 2 条/章；超出部分截断或标记 `needs_review`；
- 角色属性总数封顶 8 键（跨章合并后），避免属性表无限增长；
- 同一角色已知道的事实按规范化文本去重（含包含关系），避免同义事实反复累积；
- 伏笔 `plant` 可带 `importance`（1–5）和 `target_chapter`；`target_chapter` 必须晚于当前章，否则进 `needs_review`（`target_chapter_not_future`）；
- `advance` 表示本章推进但未回收，更新 `last_touched_chapter`；`resolve`/`abandon` 必须命中 `planted` 状态的伏笔；
- `advance`/`resolve`/`abandon` 优先按 `thread_id` 匹配，缺失时才按标题精确匹配；提示词要求从【未回收伏笔】原样复制 title；
- 世界规则由设定输入/规划层/人工登记，不由正文抽取器自动创建（避免模型把普通描述当世界规则）；
- 所有写操作保留 `source_chapter`，可回溯。

人工修账入口：`python -m novel_pipeline.memory.admin --db <db> --project <书名或ID> ...` 支持 `foreshadow list/close/reschedule`、`thread list/close/reschedule`、`alias list/set/delete`。它只调用 `MemoryStore` 公共方法，不直接改数据库；给未来的 FastAPI 管理接口留同一套语义。

## 4. 分级压缩

| 层级 | 内容 | 保留方式 |
|---|---|---|
| L0 | 角色状态、存活、物品账本、信息差、世界规则、伏笔状态 | 存储全量结构化，永不因预算压缩；prompt 受固定视图上限约束（见下） |
| L1 | 未解决冲突、未回收伏笔、未还情感债、当前目标 | 高保真摘要：伏笔和情感债各最多 8 条，按“到期 → 高重要/主债 → 最近推进 → 最新”选取，其余折叠为计数 |
| L2 | 最近 3 章摘要 | 每章 ≤200 字 |
| L3 | 更早章节 | 只保留 `seq + 一句话索引` |

L0 视图上限（防抽取噪声导致无限膨胀，不属于预算降级）：

- 每角色固定显示前 2 个属性、最近 3 条已知事实；每个角色最多显示 10 条未知事实；
- 角色按“最近出场章倒序 → 存活优先 → 名字”排序，最多显示 50 个；其余折叠为计数；
- 物品按“最近更新章倒序 → 名字”排序，最多显示 50 件；其余折叠为计数；
- 世界规则最多 8 条，按重要度降序，单条截断到 60 字；超出折叠为计数；
- 伏笔最多 8 条，选取规则同 L1；显示重要度、目标章、最近推进章；更早条目折叠为计数；
- 角色状态截断到 40 字，属性值截断到 24 字，L1 伏笔备注截断到 30 字，L2 摘要截断到 100 字。

**已知边界**：视图上限只影响 prompt，存储不删除数据；被折叠的旧角色、旧物品、旧未知事实可能正是本章需要的，后续需要按章节/关键词检索或分页。40 章回归使用固定 10 角色/10 物品，因此没有触发 50/50 上限；“token 有界”只覆盖章节增长和已配置的实体显示上限，不证明所有被折叠内容都能被找回。

**长线选取规则**（`ContextAssembler._select_foreshadowing`）：

1. 只看当前章之前已埋设的伏笔；
2. 到期组：`target_chapter <= 当前章 + 3`（含已逾期）；
3. 高重要组：`importance >= 4`；
4. 最近推进组：`last_touched_chapter >= 当前章 - 2`；
5. 最新组：按埋设章倒序；
6. 按上述顺序去重取前 8 条，仍受总预算约束。

这样“第 2 章埋、第 35 章收”的线即使被 30 条新线淹没，也会在到期前、或因为高重要度重新出现在 L1。

**情感债选取规则**（`ContextAssembler._select_emotional_threads`）：与伏笔同构，只看 `status='open'` 且 `setup_chapter <= 当前章` 的债；到期组 `target_payoff_chapter <= 当前章 + 3`，高重要组 `importance >= 5`（主债），最近推进组 `last_touched_chapter >= 当前章 - 2`，最后按欠下章倒序；去重取前 8 条。与伏笔不同，情感债到期只产生 R07 minor 提醒，不强制回收——可以故意拖到读者以为没戏了再还。

**前提**：一条旧线只有登记了 `importance`、`target_chapter` 或 `last_touched_chapter`，才能进入前三组；没有标签的旧线只能和最新线竞争。关键长线必须由计划层或人工打标，系统不会自动判断“这条线很重要”。情感债同理，主债 `importance=5` 必须由规划层或人工标记，系统不会自动判断“谁欠谁”。

**历史章节正文永不进入 prompt。** 只有摘要和结构化事实进入。

## 5. Context Assembler

组装顺序固定：

1. System prompt（题材、文风、禁忌、输出格式）
2. L0 结构化记忆：角色存活/状态、物品账本、信息差、世界规则、伏笔、情感债计数
3. L1 未解决冲突与当前目标（到期/高重要/最近推进的伏笔与情感债优先）
4. L2 最近 3 章摘要
5. L3 更早章节索引
6. 本章大纲
7. 可选场景卡 `ScenePlan`：目标、阻碍、代价、情感任务、蓄力、转折、释放、余韵，以及 `debt_paid` / `debt_opened` / `witnesses` 三个情感债手工字段
8. 输出契约（字数、视角、章节格式）

`debt_paid` / `debt_opened` / `witnesses` 仍是单章场景卡字段：写作者用它写清“本章还哪笔债、欠哪笔债、谁在场/谁缺席”。它们不会自动改 `emotional_threads` 的状态；跨章账本由规划层/人工登记，生成时从 L1 选取。

预算（初期，按 DeepSeek 口径）：

| 项 | 目标 |
|---|---|
| 输入 token 软上限 | 8k |
| 告警阈值 | 10k |
| 硬上限 | 12k |

超限处理顺序：先砍 L3 → 再压缩 L2 到 2 章 → 最后才砍 L1；L0 不因预算砍，但受 §4 的视图上限约束。

### 5.1 生成管线接入（T4-0）

`ChapterPipeline` 是真实生成入口，顺序为：

1. 用 `ContextAssembler` 组装本章上下文；
2. 调用 `ChapterWriter` 生成初稿；
3. 先跑质量层；质量 `rewrite`/`polish`/`human_review` 时，不调用抽取器，先按质量层修订；
4. 质量 `accept` 后，抽取结构化事实并跑 R01–R07；
5. 一致性 blocker → 合并为 `rewrite`，进入修订；一致性 major → `human_review`；minor（R07 情感债到期）只记录，不阻止定稿；
6. 只有质量层最终 `accept` 且一致性无 major 的稿，才进入定稿；
7. 定稿前先用 `apply(dry_run=True)` 检查 `needs_review`；有则章节保持 `pending`，**不写半套记忆**；
8. dry-run 通过后真正 `apply`，再把章节状态改为 `final`，并保留抽取器写入的摘要。

`MemoryExtractor` 与 `ConsistencyEngine` 的 `min_confidence` 必须来自同一配置；`ChapterPipeline` 在两者不一致时直接抛 `ValueError`。2026-11-01 的 3 章实跑使用 `quality_mode="full"`（规则 + Q07–Q10 + 四维评分），3 章均一次通过并定稿；人工阅读发现 1 处自动规则未覆盖的语义误记（`城防图` 数量被多加 1），说明抽取准确率仍需人工抽检和后续修正，不能把“3 章 final”当成“记忆完全正确”。

## 6. 一致性规则引擎

在章节**定稿前**运行；纯规则，零 LLM 成本。

| ID | 规则 | 判定 | 严重度 |
|---|---|---|---|
| R01 | 死亡角色出场 | 本章出场角色中 `alive=false` | blocker |
| R02 | 物品数量为负 | 使用后 `quantity < 0` | blocker |
| R03 | 信息边界越界 | 角色引用 `unknown_facts` 中的信息 | blocker |
| R04 | 伏笔状态非法 | 已回收伏笔再次“首次埋设”；未埋设直接推进/回收/放弃 | major |
| R05 | 时间线倒退 | `story_time` 早于该角色上一事件 | major |
| R06 | 伏笔逾期未回收 | `planted` 且 `target_chapter < 当前章` | major |
| R07 | 情感债到期未还 | `open` 且 `target_payoff_chapter < 当前章` | minor |

R06 只把“`apply` 实际会关闭”的 `resolve`/`abandon` 视为本章已回收：低置信度（默认 `<0.7`）跳过，有效 `thread_id` 优先于标题，只匹配 `planted` 状态的线程。`ConsistencyEngine` 的 `min_confidence` 必须与 `MemoryExtractor` 一致（默认 0.7）。

R07 只提醒，不要求回收：情感债可以故意拖，拖到读者以为没戏了再还；它不会触发 `human_review`，也不会阻止定稿。`ConsistencyReport.decision` 只有在存在 major/blocker 时才返回 `human_review`/`rewrite`。

处理方式：

- blocker：阻止定稿，失败项注入 Writing 的修订指令；
- major：记录并提示，允许人工放行；
- minor：只记录（R07），不进入修订、不阻止定稿；
- 所有失败写入 `quality_failures`，供复盘。

## 7. 验收

- 连续生成 10 章，记录每章输入 token；
- 第 1–3 章为预热期（填充 L2 摘要、触发首轮抽取），不参与增长判定；
- 第 8–10 章平均输入 token / 第 4–6 章平均 ≤ 1.3；
- 40 章确定性回归：在固定角色/物品/伏笔数量的测试数据下，第 38–40 章平均 / 第 35–37 章平均 ≤ 1.05，**只证明生成 prompt 的 token 在章节维度有界，不证明 40 章情节连续，也不证明被折叠实体的可检索性**；
- 冷启动比值（8–10 / 1–3）单独记录，不作为通过条件：分母缺少 L2/L3 与抽取事实，天然偏高；
- 人为构造“死亡角色在后续章节说话”，系统在定稿前拦截；
- 人为构造“物品用超”，系统拦截；
- 抽取准确率抽检：20 个事件中至少 17 个正确（≥85%）。
- M3.5 长线召回：第 2 章埋、第 35 章收的伏笔，在新增 30 条线后，第 21 章（高重要）、第 34 章（到期前）、第 36 章（逾期）仍必须出现在 L1；
- M3.5 到期/最近推进：低重要度但 3 章内到期的线、或最近 2 章推进过的线，即使不在最新 8 条内，也必须进入 L1；
- M3.5 到期提醒：R06 在目标章不报，超过目标章报 major，回收后不再报；低置信度的 resolve/abandon、或 `thread_id` 与标题指向不同线程时，不得把未实际关闭的线当作已回收；
- M3.5 世界规则：高重要规则常驻 L0，超过 8 条折叠，单条超过 60 字截断。
- T4-0 管线：质量 `accept` 后才会抽取/一致性；R01 blocker 能触发一次重写并最终定稿；抽取失败保持 `pending`；抽取含未知角色/物品时 dry-run 不写记忆；`extractor`/`consistency` 的 `min_confidence` 不一致时拒绝构造。
- T4-0b 数量与泛称：账本已有 1 张 `城防图`、正文只出现“半张城防图”时，`partial_item` 跳过，数量仍为 1；`蒙面人` 等场景泛称跳过，不把整章卡成 `pending`；有名有姓的未知角色仍进 `needs_review`。
- T4-0d 情感债：第 2 章登记、目标第 35 章的 `importance=5` 主债，在 30 条新债之后第 21/34/36 章仍进 L1；`paid` 后不再显示；R07 在目标章不报、逾期报 minor、`paid` 后不报，且不阻止定稿。

2026-11-01 实测（DeepSeek 兼容端点，`deepseek-v4-flash`）：

- 10 章实时回归（10 角色/10 物品/10 伏笔）：预热后比值 1.152；冷启动比值 1.531；
- 40 章确定性回归：38–40 / 35–37 比值 ≤ 1.05，最后 5 章 token 波动 ≤ 5；
- 抽取准确率：2 章、20 个标注事件，修正提示词后 20/20（另一次 19/20）；收紧提示词前为 16/20；
- R01/R02/R03 注入检查均拦截；0 抽取错误、0 blocker、0 major；
- M3.5 确定性测试：长线召回、到期/最近推进选取、R06 边界、世界规则、旧库迁移、固定实体数下 40 章 token 有界全部通过；加上 T4-0 管线测试，全量 149 tests；T4-0c 场景卡/Q09/Q10 后 155 tests；T4-0b/T4-0d 后 160 tests；T4-0e 后 161 tests（新增 token 预算守卫）；T4-0h 后 **162 tests**（爽点卡字段与契约断言）；T4-0f 后 182 tests；T4-0g 后 **189 tests**（Q11/Q12、`target_words` 贯通与校准测试）；
- T4-0 管线实跑（2026-11-01）：3 章 `quality_mode="full"`，状态均为 `final`，质量分 82/84/85，均一次通过；`needs_review` 为 0；章节摘要均已写入；
- T4-0b/T4-0d 实跑（2026-11-01）：同一 3 章大纲，质量分 87/81/83，均 `final`；第 1 章 `城防图` 数量保持 1（`partial_item` 跳过），`needs_review` 全 0；第 1/2/3 章上下文分别显示 1/2/2 条情感债；第 3 章 R07 报“老周欠沈砚另半张图”到期，但 `decision=accept`，章节正常定稿；
- T4-0e 10 章实跑（2026-11-01）：`rules+score`，10/10 `final`，质量分 88/83/84/85/82/81/81/79/83/84（均分 83.0）；平均 1,892 字、段长 63.6、句长 22.5、单句段 7%；9/13 伏笔回收，4 条留给后续；3 笔情感债已还、1 笔按计划延后；5 处停下（ch05 别名、ch06 R06、ch07 token 预算、ch08 R02 负库存、ch10 R06），token 预算统一修为 16384；`full` 未用于本轮；
- 局限：T4-0e 只跑了一轮 10 章、一个题材，真实 20–40 章情节/回收率评审仍未做；ch06 超长、ch07 段落过密仍需 T4-0g；负库存、别名、人工还债已由 T4-0f 补上拦截/别名表/本地管理 CLI，但别名仍需人工配置，账本仍需人工抽检；世界规则目前由设定输入/人工登记，不自动抽取；情感债也只由规划层/人工登记，抽取器不会自动创建或偿还；未打标签的旧线可能被折叠；L0 有 50 角色/50 物品/10 未知事实的显示上限，被折叠的关键旧实体可能找不到；抽取器 prompt 仍全量列未回收伏笔，长跑时需再收紧；数量规则只覆盖“部分量词 + 已有库存”的常见误记，不能证明所有数量抽取都正确。

## 8. 待确认问题

- [ ] 抽取用主模型还是便宜模型（成本/准确率权衡）
- [ ] `known_facts` 的粒度（按事实条目还按章节）
- [ ] 角色同名/化名如何处理（M3 先不支持化名）
- [ ] `story_time` 是否强制结构化（先用自由文本）
- [ ] 世界规则是否要从正文自动抽取，还是只由设定输入/规划层登记（M3.5 先选后者）
- [ ] 规划层如何批量设置 `target_chapter`/`importance`（M3.5 先支持单条手动/抽取登记）
- [ ] 情感债如何批量登记、如何从正文自动识别“这句算还了哪笔债”（当前只支持规划层/人工登记，R07 只提醒到期）
- [ ] 抽取器 prompt 的全量未回收伏笔列表是否也要按到期/重要度截断（当前生成 prompt 有界，抽取 prompt 仍可能增长）
