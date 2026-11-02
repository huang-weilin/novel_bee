# 开发状态与历史回归

> 这份文件保留从 README 移出的开发状态、回归数据和技术细节。下载和使用请看 [README](../README.md) 与 [LOCAL.md](LOCAL.md)。

## 当前开发状态

本地网页版 + 微信小程序共用的长篇网文生成管线：编排 → 生成 → 质量门 → 结构化记忆 → 一致性校验。本地网页版可直接下载运行，不需要 Node 构建，也不需要安装数据库服务。

M3 + M3.5 已完成；M4 的 T4-0 系列、T4-1（FastAPI 共用后端 + 本地静态网页）、T4-1b（真实 LLM 3 章验收）、T4-1c（待确认原因落库与网页补登）、T4-2（小程序三类确认界面）、T4-3（网页 SSE 任务进度流）已完成。M4.6 已完成“下载即用”收尾：网页内 AI 设置、启动脚本加固、干净副本验收和下载者文档。原 M5 公网多用户方案已冻结。

当前自动化测试 243 通过、2 个 POSIX 权限/执行位测试在 Windows 跳过；ruff 干净。

历史回归数据：实时 10 章预热后 token 比 1.152（冷启动 1.531）；固定实体数下 40 章确定性回归末段比 ≤1.05，**只证明 prompt 在章节维度有界，不证明 40 章情节连续**；20 事件抽取抽检 20/20。存储生产目标为 PostgreSQL 16，本机用 SQLite 开发适配器（见 ADR-0003）；真实 PG 集成（T3-1b）待有环境后补测。此前 3 章重跑均 `final`（87/81/83），`城防图` 保持 1，R07 到期只提醒、不阻止定稿。

## 10 章回归结果（T4-0e）

2026-11-01 用 v0.5 规则 + 场景卡 + 情感债账本跑完 10 章真实 LLM；最终稿在本地 `data/pipeline10/ch01.md`–`ch10.md`（`data/` 不提交）。

- 10/10 `final`；质量分 88/83/84/85/82/81/81/79/83/84，均分 83.0；平均尝试 1.3 次，ch08 的 4 次尝试由 R02 负库存阻塞引起，不是文笔重写。
- 文风：平均 1,892 字/章、31.5 段、段长 63.6 字、句长 22.5 字、对话字数占比 22%、单句段 7%、短句多句段 14.8%。旧 3 章为段长 23–34、句长 16；六篇近期网文样本为段长 59–83、句长 20–31。10 章整体落在样本区间，v0.5 的“叙述连句”方向成立。
- 声口：沈砚短促、回避、先动作；阿棠直接、医学观察、追问；老周绕、旧伤与隐瞒；裴照客气、只答半句；柳娘公开声大、私下声低；顾七“不看时辰，只看水”；韩校尉短硬、刀与酒；陈祭司程序化官腔；小满年轻、快。遮住名字仍能大致分辨。
- 情感债：老周欠沈砚另半张图（第 1 章开，目标第 12 章，10 章时仍未还，留作后续卷）；沈砚欠阿棠一个解释（第 2 章开，第 8 章部分还，第 10 章还清）；柳娘与裴照的人情已还。第 7 章老周右腿旧伤 + 阿棠叫“爹”、第 8 章“我听见你摔了”、第 10 章回身救人是三次克制的情绪兑现。
- 长线伏笔：13 条中 9 条在 10 章内回收（初七换防、城主的旧案、城主的替身、祭典火油、老周的旧伤、裴照的立场、边军粮草、阿棠的父亲、阿棠的身份）；4 条留作后续（青铜钥匙的来历、灰衣人的旧疤与左肩旧伤、铜牌背面“初七”、名册朱批“准其离营”）。
- 暴露的问题：第 6 章 2,798 字、明显超出 1,600 字目标；第 7 章 14 段、段长 143.6 字，是密度异常；第 8 章最低分 79 且 4 次尝试，主因是账本负库存；第 5 章未知物品 `青布小包` 需人工别名到 `金疮药`；第 6/10 章 R06 由“目标章过乐观”触发；第 7 章抽取器 4,096 token 被思考块吃光，已改为统一 16,384。人工另修正了 `祭典请柬` 种子重复计数、`守城军旧部名册` 负库存和 3 处标点/现代词。

## 爽点层、原文复核与重写（T4-0h）

10 章回归证明“句子不碎、记忆不断”，但没有解决“为什么想读下一章”。T4-0h 把爽点做成生成前的必答项：

- `ScenePlan` 新增 `opening_hook`（开篇钩子）、`reader_promise`（读者想看什么赢面）、`suppression`（谁/什么规则不公平地压制）、`payoff_tool`（用前文埋过的什么工具/信息/规则）、`payoff`（谁被打脸/得到什么/谁看见）、`payoff_type`、`bystander_reaction`、`next_hook`。
- 生成规则与输出契约要求：每章至少一次读者兑现；开篇先给一个具体的人和他眼前的具体麻烦；章末可以留更大问题，但本章要先还一笔小债；兑现不能天降；主角要有私心和代价。
- [PAYOFF.md](PAYOFF.md) 记录《没钱修什么仙》的“现实痛点→制度/资本逻辑→修仙规则→日常场景→荒诞细节→情绪释放”机制、知乎盐选的开头密度，以及每章自检表。只学机制，不复制句子/设定。
- 3 章小样《修仙界315》（本地 `data/payoff3/`，不提交）3/3 `final`（81/84/81），但 **2026-11-01 用户读了两段后否决**：“很生硬……不符合常人逻辑，也没有爽点、笑点”。技术定稿不等于故事成立。
- 之后拿到《没钱修什么仙？》第 1/2 章免费章节（`data/style_refs/`，不提交、不进生成上下文），逐段复核：原文先用一整章写“面试—被羞辱—母亲—借贷—母亲离开—穿越—70 万债”，第 2 章才给白真真和掌心符号；旧小样两段就炸死仙尊、贴封条、打脸丹王，人物没立住，爽点先到了，所以像段子。原文单句段占比 66.5%/60.3%、平均段长 31.8/36.9；旧小样 ch2 段长 144.6、13 段，信息密度过高。
- 据此重写第一章开头 `data/rewrite315/ch01.md`（不提交）：老太太、孙子、两头猪、四百八十块、一天四十六块药钱；主角有私心；制度自己说话（锦旗、“今天风大”、“个体差异”、“最终解释权”）；兑现用收据背面的“假一赔十”和会员日鸡蛋；赢了但被开除，批次号“丙-0731”接师父旧案。2,677 字、79 段、平均段长 33.9，接近原文节奏。
- Q01 从 `major` 降为 `minor`：原文单句段占比 66.5%，旧规则会把原文判成“碎片化”并强制改写，这是之前越写越密的原因之一。

## 题材分层（T4-0i）

工具不是只服务《修仙界315》这一部书。但“按题材分类”不等于复制整条管线：核心引擎共用，题材只提供策略和清单。

- 新增 `src/novel_pipeline/genre.py`：`GenreProfile` 提供 `narrative_rules`（题材专项规则）、`contract_rules`（本章硬要求）、`scene_plan_required`（场景卡必填项）、`quality_notes`（生成自检）、`extraction_focus`（抽取关注）。pipeline、记忆表、R01–R07、Q01–Q10 都不分叉。
- 内置 `default`（通用）、`xianxia_comedy`（仙侠喜剧）、`gufeng_mystery`（古风悬疑）、`urban_romance`（都市言情）。普通“仙侠”故意不映射到仙侠喜剧，旧项目行为不变；要启用策略，项目 `genre` 写别名之一。
- `ContextAssembler` 按项目题材追加【题材专项】【题材自检】【输出契约】题材条款，并把必填字段传给 `ScenePlan.to_prompt()`；场景卡缺项时在 `warnings` 里报 `scene plan missing required fields for <key>`，不阻断生成。
- 抽取器 prompt 追加“题材关注”，让“规则与收费/承诺与欠债/关键物件/人物把柄”这类事实优先进入账本。
- 细节和新增题材的方法见 [GENRES.md](GENRES.md)。当前边界：题材只影响生成与抽取 prompt，Verifier/Scorer 尚未按题材加权；题材不新增数据库表或状态机分支。

## 记忆与一致性（M3 + M3.5 + T4-0d）

- `MemoryStore`：SQLite 开发适配器，表结构与 `migrations/001_init.sql`（PostgreSQL 16）对齐；M3.5 升级脚本见 `migrations/002_long_span.sql`，情感债升级见 `migrations/003_emotional_threads.sql`，物品别名见 `migrations/004_item_aliases.sql`。
- `MemoryExtractor`：严格 JSON/Pydantic 校验；未知角色/物品不自动创建，低置信度跳过，新伏笔每章最多 2 条；支持 `advance` 和 `thread_id` 稳定匹配。`item_usage.action` 区分 gain/consume/transfer/partial；“半张/半块/一角/残片”等部分量不重复加库存。`蒙面人/守卫/宾客` 等场景泛称跳过，有名有姓的未知角色仍需确认。
- 账本边界（T4-0f）：负增量会让库存小于 0 时不写账本，记 `negative_stock` 并跳过；抽取名先按标准名查，查不到再走 `ledger_item_aliases` 的一跳别名（如 `青布小包` → `金疮药`）。别名不会自动创建物品，标准名必须先在账本里存在。
- 人工修账：`python -m novel_pipeline.memory.admin` 可列/关闭/改期伏笔与情感债、维护物品别名；只调用 `MemoryStore` 公共方法，不直接改数据库。
- `ContextAssembler`：固定顺序 system → L0 → L1 → L2(3 章) → L3 → 大纲 → 场景卡 → 契约；L0 不因预算裁剪，但有防噪声视图上限（角色 50、物品 50、未知事实 10，超出折叠为计数，存储不删除）。
- 长线伏笔：每条伏笔带 `importance`、`target_chapter`、`last_touched_chapter`；L1 按“到期 → 高重要 → 最近推进 → 最新”选取，避免第 2 章埋的线被最近 8 条挤掉。没有标签的旧线仍可能被折叠，关键线需要计划层/人工打标。
- 世界规则：`world_rules` 表常驻 L0，按重要度排序，超过 8 条/60 字折叠。
- 情感债：`emotional_threads` 记录“谁欠谁、欠什么、第几章欠下、计划第几章还、重要度、状态”；L1 按“到期 → 主债（importance=5）→ 最近推进 → 最新”选取，最多 8 条。到期只提醒（R07 minor），可以故意拖，不强制回收。
- `ConsistencyEngine`：R01 死亡角色出场、R02 负库存、R03 信息越界、R04 伏笔状态、R05 时间线倒退、R06 逾期未回收、R07 情感债到期（minor）。R06 只认可 `apply` 实际会关闭的 resolve/abandon，低置信度或错误 `thread_id` 不会造成漏报。
- `ChapterPipeline`：真实生成入口，质量门先跑；只有质量 `accept` 的稿才进入抽取/一致性。抽取若有 `needs_review`，先做 dry-run，不写半套记忆；章节保持 `pending`，人工确认后才定稿。
- 已知边界：L0 是显示上限，被折叠的旧角色/物品可能不在 prompt 中；40 章测试使用固定实体数；抽取器 prompt 仍全量列未回收伏笔；情感债只由规划层/人工登记，抽取器不会自动创建或偿还；负库存已由抽取器拦截，但直接调用 `adjust_ledger` 仍可写负数（供测试/人工修正）；别名必须人工配置，不会自动猜；数量修复只覆盖“部分量词 + 已有库存”的常见误记，不能证明所有数量抽取都正确，仍需人工抽检。

人工修账示例（`--project` 可以写书名或项目 ID；重名时必须用 ID）：

```bash
# 列出项目，拿项目 ID
python -m novel_pipeline.memory.admin --db data/novel.db projects

# 列出伏笔；关闭（默认 resolved）或改期
python -m novel_pipeline.memory.admin --db data/novel.db --project 长夜 foreshadow list
python -m novel_pipeline.memory.admin --db data/novel.db --project 长夜 foreshadow close 青铜钥匙 --chapter 12
python -m novel_pipeline.memory.admin --db data/novel.db --project 长夜 foreshadow reschedule 青铜钥匙 --target 15

# 情感债还清/放弃、改期
python -m novel_pipeline.memory.admin --db data/novel.db --project 长夜 thread close 半张图的人情
python -m novel_pipeline.memory.admin --db data/novel.db --project 长夜 thread reschedule 阿棠的误会 --target 18

# 物品别名：把抽取器写的“青布小包”记到账本里的“金疮药”
python -m novel_pipeline.memory.admin --db data/novel.db --project 长夜 alias set 青布小包 金疮药
python -m novel_pipeline.memory.admin --db data/novel.db --project 长夜 alias list
```

- 回归脚本（本地、不提交）：`data/live_m3_regression.py`、`data/live_extraction_accuracy.py`。
- 非技术审核：先读 [REVIEW.md](REVIEW.md)；自动审查可调用项目 skill `novel-review`。

## 生成管线（T4-0）

```python
from novel_pipeline.memory import MemoryStore
from novel_pipeline.pipeline import ChapterPipeline, GenerationRequest

store = MemoryStore("data/novel.db")
pipeline = ChapterPipeline(store)  # 默认 rules 模式，成本最低
result = pipeline.run(GenerationRequest(
    project_id="...",
    chapter_seq=1,
    outline="本章大纲",
    target_words=2000,
))
print(result.status, result.quality.decision)
```

质量/一致性/抽取都可以注入；生产接入 LLM Verifier/Scorer 时使用 `quality_mode="full"`。3 章实跑脚本是本机 `data/run_pipeline_3.py`，10 章文风/记忆回归脚本是本机 `data/run_pipeline_10.py`（`data/` 不提交）。3 章脚本登记了一笔小债（老周欠另半张图）和一笔主债（沈砚欠阿棠一个解释）；10 章结果见上一节，完整问题清单见 [REVIEW.md](REVIEW.md) 第 6 节。

## 质量门与校准

规则引擎可独立跑在任意一章正文上：

```bash
python -m novel_pipeline.quality data/m1-chapter-2000.md --mode rules --log-file data/quality.log
```

`--mode log_only` 只记录不拦截；`--mode rules` 执行 Q01–Q06 加 Q11 中文标点/格式、Q12 章节长度容差；`--mode rules+llm` 额外调用 Q07–Q10；`--mode rules+score` / `full` 再叠加四维评分。Q12 只在传入 `--target-words`（管线里来自 `GenerationRequest.target_words`）时检查，容差默认 70%–130%，只告警、不单凭长度触发修订。输出 `pass/decision/failures` JSON，当前阈值在 `config/quality.json`。

10 章校准可直接跑：

```bash
python -m novel_pipeline.quality.calibrate data/calibration --mode rules+score --revisions --output data/calibration.json
```

校准结果（2026-11-01，10 章短篇 AI 样本）：初评 9 accept / 1 polish，终评 10 accept，均分 82.7，平均重写 0，平均 polish 0.1。样本偏短，人工标注版 20 章校准待有真实稿后补做。

Verifier 校准（2026-11-02）：旧提示（温度 0.2）在 10 章校准稿上第一轮 Q09 命中 4 章、第二轮只命中 2 章却新增 Q07/Q10 误报，说明评审本身会漂移；收紧 Q07–Q10 的“不算”清单、限制每章命中数并把温度降到 0.0 后，10 章校准稿 0 条语义命中；再用 `full`（rules + Verifier + 四维评分）跑同一组 10 章，10/10 accept、均分 83.1、0 人工转交。已知坏样本仍召回 Q07×1 + Q08×2，Q09/Q10 正样本仍能命中；再用管线已接受的 16 章（`pipeline10`、`rewrite315`、`payoff3`）复跑，只剩 2 条可改可不改的解释句。细节与局限见 [SPEC-quality.md](SPEC-quality.md) 第 6 节。

## 文风：镜头感、简洁、连贯与情感节拍

[STYLE.md](STYLE.md) v0.5 是一张可执行的文风卡：动作峰值一句一个主要动作 + 一个必要结果；叙述、过渡、推理、情感段落要连句成段，允许 2–5 句、40–150 字；每场戏有“想要—阻碍—选择—代价—出口”的脊柱；段落之间用时间/空间/因果/人物桥承接；主要人物各有声口；关键物件/问题在开头、转折、结尾回指；章末落在画面/动作/未解问题。它拆的是镜头调度、句子经济、场景承接、人物声音和情感蓄力，不复制任何作家的句子，也不要求模仿某一种文风。参考样本拆解见 [STYLE-STUDY.md](STYLE-STUDY.md)。

`ContextAssembler` 默认注入“叙事镜头、连贯与人物声音要求”；可选 `ScenePlan` 场景卡承载本章的目标、阻碍、代价、情感任务、蓄力、转折、释放、余韵，以及“兑现的前文情感债 / 本章新欠下的情感债 / 谁在场或缺席”三个手工字段；`LLMChapterReviser` 的修订顺序是“先补承接（场景脊柱、因果桥、人物声口、回指），再删装饰”，不把“把所有句子改短”当成修订。`LLMVerifier` 采用“宁缺毋滥”的高置信口径：Q08 排除具体动作/对话/悬念收尾和台词里的情绪，Q09 不再把必要的因果/过渡、对话口癖、有意重复、声口/氛围/节奏/伏笔/动作锚点/空间信息误判为冗余，Q10 只删情感/关系的事后解释，不删承接、动作锚点和空间信息，也不用于打斗空间。跨章情感债另由 `emotional_threads` 账本进入 L1，R07 到期只报 minor，不改变“质量 accept 才能定稿”的主条件。

本机对照样本（`data/` 不提交）：旧稿 `data/pipeline3/` 与 v0.5 六篇原创样片 `data/style_lab/`（古风悬疑、都市轻喜剧、仙侠、朝堂、科幻、都市言情）。六篇平均段长 59–83 字、平均句长 20–31 字，旧 3 章为 23–34 字 / 16 字；用户已确认方向。样片仍暴露两个问题：言情场景第一次生成会退回“短对话乒乓”（06 初稿 34 段、23 段对话段，人工合并为 15 段）；复杂设定下会出现时间/物件归属小错。它们只用于判断文风方向，不替代产品验收。

## 模型环境变量（技术参考）

网页里可以用“AI 设置”完成配置；以下变量用于手动配置或 CI。AI 接口通过环境变量配置，不在代码里硬编码 key。

| 变量 | 作用 |
|---|---|
| `NOVEL_LLM_PROVIDER` | `deepseek` / `openai` / `anthropic` / `openai-compatible` / `anthropic-compatible` / `ollama` |
| `NOVEL_LLM_MODEL` | 模型名 |
| `NOVEL_LLM_BASE_URL` | 自定义端点（兼容 provider 必填） |
| `NOVEL_LLM_API_KEY_ENV` | 存放 key 的环境变量名 |
| `NOVEL_LLM_API_KEY` | 直接传 key（优先于 `NOVEL_LLM_API_KEY_ENV`） |

本机 Claude Code 的 `ANTHROPIC_AUTH_TOKEN` 实际是 DeepSeek key，走 `https://api.deepseek.com/anthropic`。复用时配置：

```env
NOVEL_LLM_PROVIDER=anthropic-compatible
NOVEL_LLM_BASE_URL=https://api.deepseek.com/anthropic
NOVEL_LLM_MODEL=deepseek-v4-flash
NOVEL_LLM_API_KEY_ENV=ANTHROPIC_AUTH_TOKEN
```

`LLMConfig.to_storyagents_env()` 会把上述配置映射成 Mo-Shen 需要的 `STORYAGENTS_*` 环境变量。

## 参考仓库与许可

| 仓库 | 许可证 | 用途 |
|---|---|---|
| [Mo-Shen](https://github.com/wwxxzz666/Mo-Shen) | MIT | 编排/确认关口/小程序参考 |
| [NovelFactory](https://github.com/Jason-ship/langgraph) | MIT | 评分阈值参考 |
| [Novel-factory](https://github.com/YoRengzh/Novel-factory) | Apache-2.0 | 账本/体检参考 |
| [xt-webnovel-writing](https://github.com/xiaotiewinner/xt-webnovel-writing) | 无 | 仅借鉴问题类别 |
| [my-novel-agent](https://github.com/lazyayuan/my-novel-agent) | 无 | 仅借鉴压缩策略 |

`references/` 已被 gitignore；无许可证仓库的代码、prompt、条款原文不得复制进本项目。

## 下一步

旧 3 章《修仙界315》不再作为主方向继续磨。用户已认可重写第一、二章的方向；题材分层（T4-0i）也已接线：核心管线共用，题材只提供 prompt 策略、场景卡必填项和抽取关注，内置仙侠喜剧/古风悬疑/都市言情。第二章 `data/rewrite315/ch02.md`（医馆同批次假药案）已获确认。第三章 `data/rewrite315/ch03.md` 已按同一 profile 写完：把冲突从医馆推到认证机构，许青用公开登记页和《认证异议办理须知》第七条逼出盖章的更正公告，但公告只写“暂停使用”，经办人彭子期查无此人，老陶的旧案继续压着。第三章已写，用户暂不细读、按通过处理，问题后续回头改；爽点卡、代价和指标见 [PAYOFF.md](PAYOFF.md) 第 10.7 节。

技术侧 T4-0f（负库存、物品别名、人工关闭/改期入口）与 T4-0g（Q11 中文标点/格式、Q12 章节长度容差、`full` Verifier 的 Q08/Q09 校准）已完成。Verifier 收紧后，10 章校准稿 0 条语义误报，管线已接受的 16 章只剩 2 条可改可不改的命中，`full` 可用于下一轮 10 章试跑；题材质量加权（Verifier/Scorer）仍先不开，避免样本不足时把规则调坏。之后进入本地下载版收尾、小程序三类确认界面、SSE 进度、`msgSecCheck` 与 AI 标识、3 章产品级验收。见 [TASKS.md](TASKS.md)。
