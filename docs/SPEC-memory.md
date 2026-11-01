# 记忆与一致性规格 v0.1

> 状态：Draft（待评审） · 更新：2026-11-01
> 对应里程碑：M3。表结构、抽取契约、组装顺序是实现契约。

## 1. 目标

让上下文长度**不随章节数线性增长**，并让跨章硬错误（死人复活、物品超用、信息越界、伏笔状态错乱）在定稿前被拦住。

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
  notes text
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

索引：`chapters(project_id, seq)`、`characters(project_id, name)`、`foreshadowing(project_id, status)`、`quality_failures(chapter_id)`。

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
    {"name": "回魂丹", "delta": -1, "reason": "救人"}
  ],
  "info_gains": [
    {"character": "张三", "facts": ["得知城主是内奸"]}
  ],
  "foreshadowing": [
    {"action": "plant", "title": "青铜钥匙", "notes": "第 3 章首次出现"}
  ],
  "chapter_summary": "<=200 字",
  "key_events": ["事件 1", "事件 2"]
}
```

校验规则：

- Pydantic 严格校验；字段缺失/类型错误 = 抽取失败，进人工确认；
- 未知角色/物品**不自动创建**，标记 `needs_review`；
- `confidence < 0.7` 的条目只记录、不写账本；
- 所有写操作保留 `source_chapter`，可回溯。

## 4. 分级压缩

| 层级 | 内容 | 保留方式 |
|---|---|---|
| L0 | 角色状态、存活、物品账本、信息差、伏笔状态 | 全量结构化，永不压缩 |
| L1 | 未解决冲突、未回收伏笔、当前目标 | 全量或高保真摘要 |
| L2 | 最近 3 章摘要 | 每章 ≤200 字 |
| L3 | 更早章节 | 只保留 `seq + 一句话索引` |

**历史章节正文永不进入 prompt。** 只有摘要和结构化事实进入。

## 5. Context Assembler

组装顺序固定：

1. System prompt（题材、文风、禁忌、输出格式）
2. L0 结构化记忆：角色存活/状态、物品账本、信息差、伏笔
3. L1 未解决冲突与当前目标
4. L2 最近 3 章摘要
5. 本章大纲
6. 输出契约（字数、视角、章节格式）

预算（初期，按 DeepSeek 口径）：

| 项 | 目标 |
|---|---|
| 输入 token 软上限 | 8k |
| 告警阈值 | 10k |
| 硬上限 | 12k |

超限处理顺序：先砍 L3 → 再压缩 L2 到 2 章 → 最后才砍 L1；L0 不砍。

## 6. 一致性规则引擎

在章节**定稿前**运行；纯规则，零 LLM 成本。

| ID | 规则 | 判定 | 严重度 |
|---|---|---|---|
| R01 | 死亡角色出场 | 本章出场角色中 `alive=false` | blocker |
| R02 | 物品数量为负 | 使用后 `quantity < 0` | blocker |
| R03 | 信息边界越界 | 角色引用 `unknown_facts` 中的信息 | blocker |
| R04 | 伏笔状态非法 | 已回收伏笔再次“首次埋设”；未埋设直接回收 | major |
| R05 | 时间线倒退 | `story_time` 早于该角色上一事件 | major |

处理方式：

- blocker：阻止定稿，失败项注入 Writing 的修订指令；
- major：记录并提示，允许人工放行；
- 所有失败写入 `quality_failures`，供复盘。

## 7. 验收

- 连续生成 10 章，记录每章输入 token；
- 第 8–10 章平均输入 token / 第 1–3 章平均 ≤ 1.3；
- 人为构造“死亡角色在后续章节说话”，系统在定稿前拦截；
- 人为构造“物品用超”，系统拦截；
- 抽取准确率抽检：20 个事件中至少 17 个正确（≥85%）。

## 8. 待确认问题

- [ ] 抽取用主模型还是便宜模型（成本/准确率权衡）
- [ ] `known_facts` 的粒度（按事实条目还按章节）
- [ ] 角色同名/化名如何处理（M3 先不支持化名）
- [ ] `story_time` 是否强制结构化（先用自由文本）
