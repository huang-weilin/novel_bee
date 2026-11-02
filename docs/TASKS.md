# 任务清单

> 规则：同一时间只允许一个 `[>]`。新想法先放 Backlog，不直接开工。
> 状态：`[ ]` 待办 · `[>]` 进行中 · `[x]` 完成 · `[~]` 冻结

## 当前 Sprint：M3 + M3.5 已完成；M4 T4-0 已接线；T4-0c 文风 v0.5 已确认；T4-0e 10 章回归已完成；T4-0f 账本边界已修；T4-0g 质量规则补强已完成；T4-0h 爽点层已接线；T4-0i 题材分层已接线；T4-1 FastAPI + 本地网页版已完成；T4-1b 真实 LLM 3 章产品验收通过；T4-1c 待确认项网页补登闭环已完成；T4-2 小程序三类确认界面已完成；T4-3 SSE 任务进度已完成；**M4.6 本地网页版“下载即用”收尾已完成（243 tests）**；原 T4-4 `msgSecCheck`/真机验收与 M5 公网方案冻结，等待真实小程序 AppID 或用户明确重启云端需求

- [x] T0-1 建立目录结构与参考仓库隔离
- [x] T0-2 写 `docs/PLAN.md`
- [x] T0-3 写 `docs/SPEC-quality.md` 初稿
- [x] T0-4 写 `docs/SPEC-memory.md` 初稿
- [x] T0-5 写 `docs/ADR/0001-foundation-and-licenses.md`
- [x] T0-6 用户评审并冻结 M0 规格
- [x] T0-7 初始化自研包 `src/novel_pipeline` 与最小测试

## M1 跑通 Mo-Shen（已完成）

- [x] T1-1 检查 Python 3.11+ 与 uv/pip 环境
- [x] T1-2 在 `.venvs/mo-shen` 建独立 venv，`pip install -e references/Mo-Shen`
- [x] T1-3 跑 `pytest`，20 passed，2 deselected（smoke）
- [x] T1-4 配置兼容端点，启动 `serve --port 8123 --mode quick`
- [x] T1-5 走通“试写 213 字 → 大纲确认 → 成稿 362 字”；CLI 2000 字目标实测 1969 字
- [x] T1-6 记录依赖面：Python 3.12.8 / AgentScope 2.0.11 / Mo-Shen 2.0.2；无外部数据库
- [x] T1-7 新增 `LLMConfig` 可配置 provider + 9 个单测

**M1 验收**：干净环境可启动；1 章约 2000 字（实测 1969）可读正文；确认关口可暂停/恢复。

## M2 质量层

- [x] T2-1 质量层适配器空壳：接管章节输出，只记日志
- [x] T2-2 规则引擎骨架 + Q01–Q06 程序化规则
- [x] T2-3 LLM Verifier：Q07–Q08
- [x] T2-4 四维评分器（人设/节奏/钩子/文风）
- [x] T2-5 决策与重试：pass / polish / rewrite / human_review
- [x] T2-6 用 10 章样章校准阈值，统计平均重写次数

**M2 验收**：失败项可解释；评分分布合理；重试上限能停；平均每章重写 ≤ 2。

## M3 记忆与一致性

- [x] T3-1 PostgreSQL schema 与迁移脚本（SQLite 开发适配器先行，见 ADR-0003）
- [ ] T3-1b 有 PostgreSQL 环境后跑真实迁移与仓储集成测试
- [x] T3-2 Memory Extractor（严格 JSON + Pydantic 校验）
- [x] T3-3 Context Assembler（结构化事实 + 最近 3 章摘要 + 本章大纲）
- [x] T3-4 一致性规则 R01–R05
- [x] T3-5 连续 10 章回归：token 曲线 + “死人说话”测试 + 20 事件抽取准确率

**M3 验收**：预热后 10 章 prompt token 不线性上升；40 章回归有界；阻断级问题在定稿前被拦住；抽取准确率 ≥85%。真实 PostgreSQL 集成（T3-1b）待有环境后补测。

## M3.5 长线记忆

- [x] T3-6 伏笔元数据：`importance` / `target_chapter` / `last_touched_chapter`，SQLite 旧库迁移 + PG 002
- [x] T3-7 上下文选取：到期/高重要/最近推进/最新四组优先，L0 增加世界规则常驻
- [x] T3-8 Extractor：`advance`、`thread_id` 匹配、plant 元数据、过期目标进 `needs_review`
- [x] T3-9 R06 逾期未回收 + 长线召回/世界规则/迁移测试
- [x] T3-10 非技术审核包：`docs/REVIEW.md` + 项目 skill `novel-review`
- [x] T3-11 独立审核修复：R06 低置信度/`thread_id` 假阴性；补到期/最近推进/abandon 测试；补文档边界

**M3.5 验收**：第 2 章埋、第 35 章收的线，在新增 30 条线后第 21/34/36 章仍进 L1；低重要度但到期/最近推进的线也能进 L1；R06 在目标章不报、逾期报 major、回收后不报，且低置信度/`thread_id` 冲突不误判；世界规则常驻且有条数/字数上限；固定实体数下 40 章 token 仍有界；M3.5 验收时 138 tests。T4-0 接入后 149 tests；T4-0c 场景卡/Q09/Q10 后 155 tests；T4-0b/T4-0d 后 160 tests；T4-0e 后 161 tests（新增 token 预算守卫）；T4-0h 后 162 tests（爽点卡字段/契约断言）；T4-0i 后 173 tests；T4-0f 后 182 tests；T4-0g 后 189 tests（Q11/Q12、target_words 贯通、校准测试）；T4-1 后 206 tests（env 加载、FastAPI、任务轮询、重写限制、导出）；T4-1b 后 207 tests（thinking-only 输出自动提高上限重试）；T4-1c 后 212 tests（review_json 持久化/清空、补登人物与物品、校验/404）；T4-2 后 223 tests（试写任务/接口、trial_text 注入、小程序静态检查/页面注册/导航目标/JS 语法）；T4-3 后 224 tests（SSE 终态事件、404、网页 JS 语法）。

## M4 产品链路（本地网页 + 小程序）

- [x] T4-0 将质量层/记忆层接入真实生成管线：`ChapterPipeline` 串起上下文组装 → 生成 → 质量/一致性 → 抽取 → 定稿；质量未 accept 不抽取，`needs_review` 先 dry-run 不写半套记忆；`extractor`/`consistency` 共用 `min_confidence`。3 章实跑均 `final`（82/84/85 分），但发现 1 处 `城防图` 数量误记。
- [x] T4-0b 处理 3 章实跑暴露的记忆误记：`item_usage` 增加 `action`；账本已有物品时“半张/半块/一角/残片/一部分”标记 `partial`，正数增量 + 部分量词也会被识别为 `partial_item` 跳过；`蒙面人/黑衣人/守卫/宾客` 等场景泛称跳过（`generic_role`），有名有姓的未知角色仍进 `needs_review`。3 章重跑后 `城防图` 保持 1，`needs_review` 全 0。
- [x] T4-0c 镜头感、简洁、连贯与情感节拍：`docs/STYLE.md` v0.5；读六本近期网文免费章节并写 `docs/STYLE-STUDY.md`；生成提示注入“动作峰值一句一拍、叙述段落连句成段、场景脊柱、人物声口、关键物件回指、题材语域”；新增可选 `ScenePlan` 场景卡（含 `debt_paid` / `debt_opened` / `witnesses` 情感债钩子）；Q09“冗余/解释性重复”、Q10“过度明确/留白不足”进入 Verifier，且不再鼓励把文本改碎。六篇原创样片（古风悬疑/都市轻喜剧/仙侠/朝堂/科幻/都市言情）平均段长 59–83 字、平均句长 20–31 字，用户已确认方向；样片仍暴露言情场景易退回“短对话乒乓”、复杂设定偶发时间/物件归属小错。
- [x] T4-0d 跨章情感债账本：新增 `emotional_threads` 表与 SQLite/PG 迁移（001 新装 + 003 升级），字段 `title / debt_from / debt_to / kind / setup_chapter / target_payoff_chapter / status / importance / last_touched_chapter / notes`；`MemoryStore` CRUD；L1 按“到期 → 主债（importance=5）→ 最近推进 → 最新”选取，最多 8 条；L0 只显示未还计数。到期做 R07 minor 提醒，不做 blocker——情感债可以故意拖，拖到读者以为没戏了再还；`ConsistencyReport` 只在 major/blocker 时转人工。仍只支持规划层/人工登记，抽取器不自动创建或偿还。
- [x] T4-0e 10 章文风/记忆回归：用 v0.5 规则 + 场景卡 + 情感债账本跑 10 章真实 LLM。10/10 `final`，质量分 88/83/84/85/82/81/81/79/83/84（均分 83.0）；平均 1,892 字/章、段长 63.6、句长 22.5、单句段 7%，进入近期网文样本区间（段长 59–83、句长 20–31）。9/13 条伏笔在 10 章内回收，4 条留给后续；情感债 3 笔已还、1 笔目标第 12 章（10 章时仍未还）；人物声口可区分。回归中 5 处停下：ch05 未知物品别名、ch06 R06、ch07 抽取器 token 预算、ch08 R02 负库存、ch10 R06；token 预算已修为 16384，其余账本边界见 T4-0f。`full` Verifier 当时仍在 Q08/Q09 过触发，本轮用 `rules+score`，已在 T4-0g 单独校准。脚本为本地 `data/run_pipeline_10.py`（不提交）。
- [x] T4-0h 爽点层：`ScenePlan` 增加 `opening_hook` / `reader_promise` / `suppression` / `payoff_tool` / `payoff` / `payoff_type` / `bystander_reaction` / `next_hook` 8 个字段；生成规则/输出契约要求“每章至少一次读者兑现”“开篇先给具体的人的具体麻烦”“先还一笔小债再留新问题”；新增 `docs/PAYOFF.md`。3 章原创仙侠喜剧小样《修仙界315》技术上都 `final`（81/84/81），但用户读了两段后否决：“很生硬……不符合常人逻辑，也没有爽点、笑点”。随后拿到《没钱修什么仙？》第 1/2 章免费章节逐段复核：原文先用一整章立人物和债，旧小样两段就完成典礼—死亡—贴封条—打脸，人物没立住，爽点先到了；旧小样 ch2 段长 144.6、13 段，信息密度过高。据此重写 `data/rewrite315/ch01.md`（不提交），2,677 字、79 段、平均段长 33.9；Q01 从 major 降为 minor，避免把原文的短段节奏误判成碎片化。用户已确认“是你写的、不是已有作品、我觉得挺不错”，方向成立；第二章 `data/rewrite315/ch02.md`（2,941 字/114 段/段长 25.8，医馆同批次假药案）已获用户确认；第三章 `data/rewrite315/ch03.md` 已写（3,011 字/118 段/段长 25.5，认证机构公开纠错案），用户暂不细读、按通过处理。
- [x] T4-0i 题材分层：新增 `GenreProfile`（`narrative_rules` / `contract_rules` / `scene_plan_required` / `quality_notes` / `extraction_focus`），内置 `default` / `xianxia_comedy` / `gufeng_mystery` / `urban_romance`；pipeline、记忆表、R01–R07、Q01–Q10 不分叉。`ContextAssembler` 按项目 `genre` 注入【题材专项】【题材自检】和契约条款，`ScenePlan.to_prompt(required)` 支持题材必填字段与缺失警告；抽取器 prompt 增加“题材关注”；普通“仙侠”仍走 `default`，旧项目行为不变。新增 `docs/GENRES.md`；173 tests，ruff 干净。
- [x] T4-0f 记忆账本边界：`item_usage` 负增量会让库存小于 0 时不写账本，记 `negative_stock` 并跳过（例如库存 0 消耗 1、库存 1 交出 2）；新增 `ledger_item_aliases` 表和一跳别名解析（`青布小包` → `金疮药`），未知标准名仍进 `needs_review`；新增 `python -m novel_pipeline.memory.admin`，可列/关闭/改期伏笔与情感债、维护物品别名，不再靠本地脚本直接改库。SQLite schema、PG `001`/`004_item_aliases.sql`、`MemoryStore`、抽取器和 9 个新测试同步；182 tests，ruff 干净。
- [x] T4-0g 质量规则补强：新增 Q11 中文标点/格式（汉字紧邻的半角 `, . ! ? ; :`、`...`、`--`，以及包住中文的直引号；英文/数字/代码上下文不误报）和 Q12 章节长度容差（目标 70%–130%，minor 告警，`ChapterInput.target_words` 从 `GenerationRequest` 贯通到规则引擎与 CLI）；校准 `full` Verifier 的 Q07–Q10：旧提示两轮结果漂移，收紧“不算”清单、限制 Q08/Q09 各 ≤2 条、Q10 ≤1 条、总量 ≤4 条并把温度降到 0.0 后，10 章校准稿 0 条语义命中，`full` 复跑 10/10 accept、均分 83.1、0 人工转交；坏样本仍召回 Q07×1 + Q08×2，Q09/Q10 正样本仍命中；16 章已接受稿仅 2 条可改可不改的命中。189 tests，ruff 干净。
- [x] T4-1 生产级 FastAPI + 本地网页版：新增 `src/novel_pipeline/server`（app/schemas/jobs/`__main__` + static）；作品/章节/生成任务/任务轮询/质量结果/待确认重写/导出/记忆摘要接口；单 worker 后台任务，每请求独立 SQLite 连接，避免跨线程共享连接；`.env` 自动加载且不覆盖 shell/CI 变量；`python -m novel_pipeline.server`、`novel-pipeline`、`start.bat`/`start.sh` 三种入口；默认只监听 `127.0.0.1`，无登录并文档警告；新增 `docs/API.md`；206 tests，ruff 干净。
- [x] T4-1b 本地网页端到端 3 章产品级验收：真实 LLM，经与页面相同的 HTTP 接口跑通“建作品→大纲→质量结果→待确认→重写→导出”，3 章均 `final`（87/82/88），导出 3/3；ch02 因新角色 `马师兄` 待确认、补登后重写，ch03 因新物品 `投诉台账` 待确认、补登后重写。过程中发现修订调用可能只返回 thinking blocks，`LLMClient` 现自动把输出上限翻倍重试一次（16,384→32,768），仍失败才转人工。页面本身只做了静态资源和接口冒烟，未做自动化浏览器点击；本项验收证据是 HTTP 端到端，不是“页面每台电脑都好看”。
- [x] T4-1c 待确认项补登闭环：`chapters.review_json` 保存待确认原因（SQLite `_migrate_chapter_columns` 自动加列，PG `005_chapter_review.sql`）；单章详情返回 `review_items`；新增 `POST /api/projects/{id}/characters` 与 `/items`，可补登缺失人物/物品；本地网页在待确认章节下展示原因并直接登记，登记后提示重写。定稿/重写时 `review_json` 清空；记忆仍只在定稿时写入。212 tests，ruff 干净。
- [x] T4-2 小程序三类确认界面：`miniprogram/` 无构建完成首页/新建/作品/大纲/试写/章节六页；新增 `POST /chapters/trial` 与 `JobManager.submit_trial`，试写真实调用模型写短片段，不跑质量门、不存章节、不写记忆；确认后 `trial_text` 作为方向提示注入正式生成，提示词要求不照抄；章节页轮询任务、展示质量失败项、补登人物/物品、重写/下一章/导出；`project.config.json` 用游客 AppID + `urlCheck:false` 供本地 http 调试；新增 `docs/MINIPROGRAM.md`；223 tests，ruff 干净。
- [x] T4-3 SSE 任务进度：新增 `GET /api/jobs/{job_id}/events`，0.5 秒检查一次任务状态，状态变化才推送，空闲 10 秒发 keep-alive，终态发 `event: end`；网页用 `EventSource`，连接失败自动回退轮询；小程序继续轮询（无 EventSource）。这是任务进度流，不是逐 token 正文流；224 tests，ruff 干净。
- [ ] T4-4 `msgSecCheck` 输入/输出 + “内容由 AI 生成”标识：AI 标识已加到网页阅读区和小程序章节/试写页；`msgSecCheck` 需要真实小程序 AppID、secret 和登录用户的 openid，当前游客 AppID 无法完成合规检查，尚未接入。
- [ ] T4-5 小程序端到端 3 章验收（T4-0 已完成本机管线 3 章实跑，不等同于产品级验收）

## M4.6 本地网页版“下载即用”（已完成）

目标：下载 ZIP 或 clone → 双击 `start.bat` / 运行 `./start.sh` → 浏览器打开 `127.0.0.1:8000` → 网页内配置自己的 AI API → 建作品/试写/生成/导出。数据库、配置和 key 全部留在本机；不需要 Node、Docker、PostgreSQL、Redis 或云服务。

- [x] T4-6a 设置后端：`server/settings.py` 读取/校验/保存配置；只管理四个 `NOVEL_LLM_*` 键；保留 `.env` 其他行和注释；原子写入；POSIX 600；系统环境变量优先；换服务商必须重填 key，防止旧 key 误发新服务商
- [x] T4-6b 设置接口：`GET /api/settings`、`POST /api/settings`、`POST /api/settings/test`；响应/错误均不含 key；设置接口仅接受回环 Host，局域网访问返回 403；`GET /api/health` 复用同一套读取逻辑
- [x] T4-6c 连接测试：`LLMClient.ping()` 发一次小请求，HTTP 2xx 即成功；失败消息脱敏并截断；测试超时上限 30 秒
- [x] T4-6d 设置前端：顶栏“AI 设置”、首次引导卡、原生 `<dialog>` 表单；provider 默认值联动；key 密码框不回填；保存后刷新健康状态并清空 key；未配置时阻止生成并打开设置
- [x] T4-6e 启动与打包：`start.bat`/`start.sh` 实际检查 Python 3.11+、自动建 venv/装依赖/复制 `.env`、参数透传；依赖加上限；`.gitattributes` 固定 LF/CRLF；`.env.example` 增加可直接填写的 key 行；`.env` 解析去 BOM
- [x] T4-6f 文档：README 改为下载者视角；新增 `docs/LOCAL.md`（启动/配置/数据/备份/升级/排错/安全边界）与 `docs/STATUS.md`（历史状态与回归记录）；更新 API/MINIPROGRAM/PLAN/TASKS
- [x] T4-6g 测试：新增 `tests/test_settings.py`（写入/保留注释/换服务商/非法值/脱敏/403/权限）与 `tests/test_local_distribution.py`（启动脚本/`.env.example`/gitignore/包数据/JS/bash 语法）；更新服务端静态断言；全量 243 passed / 2 skipped，ruff 干净
- [x] T4-6h 干净副本验收：无 `.venv`/`.env`/`data/novel.db` 的副本可启动、显示首次配置引导、保存配置、建作品、生成 `rules` 章节、导出、重启后数据仍在
- [x] T4-6i 提交与发布：MIT 许可证已加入；代码已推送到 GitHub `huang-weilin/novel_bee` 的 `master`，clone 后全量测试通过；本地 Claude 助手文件已从 Git 历史移除且未上传；tag/Release 可选，尚未创建

## Backlog（冻结，不排期）

- [~] 25 条反 AI 味规则全量
- [~] Neo4j / 图谱记忆
- [~] Milvus / 向量检索
- [~] **M5 公网多用户方案（冻结）**：登录、多租户隔离、云 PostgreSQL、配额/计费、运营后台、`msgSecCheck` 双端合规、云端部署
- [~] 自训练模型
- [~] 第三方开发流程 skill

## 完成记录

| 日期 | 任务 | 结果 |
|---|---|---|
| 2026-11-01 | T0-1 ~ T0-5 | 骨架、计划、两份规格、ADR 初稿 |
| 2026-11-01 | T0-7 | 建立 venv，`pytest` 冒烟测试通过（1 passed） |
| 2026-11-01 | T1-1 ~ T1-6 | Mo-Shen 20 测试通过；CLI 2000 字目标实测 1969 字；serve 确认关口全链路通过 |
| 2026-11-01 | T1-7 | `LLMConfig` 完成，9 个单测通过；支持兼容端点与 key env 映射 |
| 2026-11-01 | T2-1 | `QualityAdapter` 完成：`log_only` 透传并记录章节哈希/字数；`rules` 模式已接线 |
| 2026-11-01 | T2-2 | Q01–Q06 规则引擎完成；22 个测试通过；M1 样章报出 Q01（单句段占比 46%），进入 polish |
| 2026-11-01 | T2-3 | Q07–Q08 Verifier 完成；Anthropic/OpenAI 双协议客户端；40 个测试通过；M1 样章 0 命中，构造正样本命中 Q07+Q08；思考型模型 max_tokens 调到 4096 |
| 2026-11-01 | T2-4 | 四维评分器完成；55 个测试通过；实测 M1 样章 85 分、坏样本 38 分，权重 30/25/25/20 |
| 2026-11-01 | T2-5 | `QualityLoop` 完成：rewrite 上限 3、polish 上限 2，超限转 `human_review`；64 个测试通过 |
| 2026-11-01 | T2-6 | 10 章校准完成（`rules+score` + 自动修订）：初评 9 accept / 1 polish，ch09 报 Q01+Q06，修订 1 次后 accept；终评 10/10 accept，均分 82.7，平均重写 0，平均 polish 0.1，无人工转交/错误；78 个测试通过，ruff 干净 |
| 2026-11-01 | M2 完成 | 8 条规则 + 四维评分 + 重试/人工兜底全链路可用；校准集为 10 章短篇 AI 样本，人工标注版 20 章校准留待有真实稿后补做 |
| 2026-11-01 | T3-1 | PostgreSQL 16 迁移脚本 `migrations/001_init.sql` + SQLite `MemoryStore`；当时 9 张表、外键、唯一约束、审计表齐全（T4-0d 后为 10 张）；87 个测试通过，ruff 干净；真实 PG 集成测试因本机无 Docker/PG 暂缓（T3-1b） |
| 2026-11-01 | T3-2 | Pydantic 严格校验的 Memory Extractor；未知角色/物品进 `needs_review`，confidence<0.7 跳过，伏笔 plant/resolve/abandon 校验；真实模型抽取 M1 样章成功，4 个角色更新、1 组信息增益、5 个伏笔（1 个重复 plant 被拦）；10 个抽取测试通过 |
| 2026-11-01 | T3-3 | `ContextAssembler` 固定顺序 system→L0→L1→L2→L3→大纲→输出契约；L0 永不裁剪，超软上限按 L3→L2(2章)→L1 降级；L3 默认最多 30 条；10 章最小设定冷启动比 1.71、预热后 1.08，10 角色设定回归比 1.20；10 个上下文测试通过 |
| 2026-11-01 | T3-4 | R01–R05 确定性规则：死亡角色动作/说话、负库存、信息越界、伏笔状态非法、时间线倒退；R01 排除“张三死后”式提及；R04/R05 需抽取 payload；6 个规则测试通过 |
| 2026-11-01 | T3-5 | 10 章实时回归（10 角色/10 物品/10 伏笔）：预热后 token 比 1.152，冷启动 1.531；0 抽取错误、0 blocker/major；R01/R02/R03 注入均拦截；20 事件抽取抽检 20/20；40 章确定性回归末段比 ≤1.05、最后 5 章波动 ≤5；121 测试通过，ruff 干净 |
| 2026-11-01 | M3 完成 | 存储/抽取/上下文/R01–R05/回归全部完成；L0 增加防噪声视图上限（状态 40 字、属性 2 项、已知事实 3 条、伏笔 8 条）；冷启动 1.531 超过原 1.3 目标，按“预热后增长”判定并记录原因；真实 PG 集成与人工标注 20 章抽取校准列为待办 |
| 2026-11-01 | M3.5 完成 | 伏笔加重要度/目标回收章/最近推进章；L1 按“到期→高重要→最近推进→最新”选取，长线不再只靠最近 8 条；新增 world_rules 表与常驻上下文；R06 逾期 major；旧 SQLite 自动补列；新增 `docs/REVIEW.md` 与 `novel-review` skill；132 测试通过，ruff 干净；未重跑真实 LLM 回归 |
| 2026-11-01 | T3-11 审核修复 | 独立审核发现 R06 会把低置信度/`thread_id` 与标题冲突的 resolve 当成已回收；改为只按 `apply` 实际会关闭的线程抑制，补低置信度/id 冲突/abandon/到期优先/最近推进测试；138 测试通过；文档补充库级能力、L0 实体上限、未打标签旧线等边界 |
| 2026-11-01 | T4-0 管线接线 | `ChapterPipeline` 接入生成、质量、一致性、抽取、修订与定稿；质量未 accept 不抽取；`apply(dry_run=True)` 防半套写入；L0 实体视图上限 50/50/10；3 章真实 LLM 实跑均 final（82/84/85 分，一次通过）；149 tests；人工发现 `城防图` 数量误记，列为 T4-0b |
| 2026-11-01 | T4-0b/T4-0d | 数量误记修复：`partial_item` + 泛称 `generic_role`；情感债表/CRUD/L1 选取/R07 minor；160 tests；3 章重跑均 final（87/81/83），`城防图` 保持 1，R07 到期只提醒不阻止定稿 |
| 2026-11-01 | T4-0c v0.5 | 六本近期网文免费章节拆解 + v0.5 文风卡；六篇原创样片覆盖古风悬疑/都市轻喜剧/仙侠/朝堂/科幻/都市言情，用户确认方向；样片仍暴露言情场景短对话乒乓、复杂设定连续性小错；10 章回归启动 |
| 2026-11-01 | T4-0e | 10 章真实 LLM 回归全部 `final`（均分 83.0）；段长 63.6/句长 22.5/单句段 7%；9/13 伏笔回收、3/4 情感债还清；5 处人工处理暴露负库存/别名/目标章/预算边界；161 tests，ruff 干净 |
| 2026-11-01 | T4-0h | 爽点卡 8 字段接入 `ScenePlan`/生成契约；新增 `docs/PAYOFF.md`；3 章《修仙界315》技术 `final`（81/84/81），但被用户否决“生硬、不符合常人逻辑、无爽点/笑点”；拿到原文第 1/2 章复核后重写 `data/rewrite315/ch01.md`（2,677 字/79 段/段长 33.9）；用户确认重写方向成立；Q01 降为 minor；162 tests，ruff 干净 |
| 2026-11-01 | T4-0i | 题材分层接线：共享 pipeline/记忆/一致性/质量门，题材只提供生成规则、契约条款、场景卡必填、自检清单和抽取关注；内置仙侠喜剧/古风悬疑/都市言情；普通“仙侠”仍走 default；新增 `docs/GENRES.md`；173 tests，ruff 干净 |
| 2026-11-01 | 试读稿 ch02/ch03 | 第二章 `data/rewrite315/ch02.md` 获用户确认；第三章 `ch03.md` 按仙侠喜剧 profile 写完，把冲突从医馆推到认证机构：公开登记页证明送检样品与销售批次不符，用《认证异议办理须知》第七条逼出盖章更正公告；代价是 50 块加急费、公告只“暂停使用”、经办人查无此人；3,011 字/118 段/段长 25.5，零连续重合；用户暂不细读，按通过处理 |
| 2026-11-02 | T4-0f | 抽取器对负库存改为 `negative_stock` 跳过，不再写负数；新增 `ledger_item_aliases` 与一跳别名解析，抽取名先查标准名再查别名；新增本地管理 CLI，可关闭/改期伏笔和情感债、维护别名；SQLite schema、PG 001/004、模型、store、extractor 和 9 个测试同步；182 tests，ruff 干净 |
| 2026-11-02 | T4-0g | 新增 Q11 中文标点/格式（汉字紧邻半角标点/直引号，英文上下文不误报）和 Q12 章节长度容差（目标 70%–130%，minor，`target_words` 贯通 `ChapterInput`/pipeline/CLI）；Verifier Q07–Q10 收紧“不算”清单、限制每章命中数、温度降到 0.0；10 章校准稿 0 条语义误报，坏样本仍召回 Q07+Q08×2，16 章已接受稿仅 2 条；189 tests，ruff 干净 |
| 2026-11-02 | T4-1 | FastAPI + 本地网页版：作品/章节/任务/质量结果/待确认重写/导出/记忆摘要 API；单 worker 后台任务；无构建静态页；`start.bat`/`start.sh`/`novel-pipeline` 入口；`.env` 自动加载；默认只听 127.0.0.1；新增 `docs/API.md`；206 tests，ruff 干净；真实 LLM 的 3 章产品验收列为 T4-1b |
| 2026-11-02 | T4-1b | 真实 LLM 经本地 HTTP API 跑通 3 章：待确认→补登人物/物品→重写→`final`（87/82/88）→导出 3/3；修复 thinking-only 输出（输出上限翻倍重试一次）；207 tests，ruff 干净 |
| 2026-11-02 | T4-1c | 待确认原因持久化到 `chapters.review_json`；单章详情返回 `review_items`；新增补登人物/物品接口和网页登记表单；定稿/重写清空待确认项；212 tests，ruff 干净 |
| 2026-11-02 | T4-2 | 小程序三类确认界面 + 真实试写：`POST /chapters/trial` 短片段不写章节/记忆，确认后 `trial_text` 注入正式生成；`miniprogram/` 六页无构建，章节页可轮询/补登/重写/导出；`docs/MINIPROGRAM.md`；223 tests，ruff 干净 |
| 2026-11-02 | T4-3 | 网页 SSE 任务进度：`GET /api/jobs/{job_id}/events` 推送状态 JSON、keep-alive、终态 `event: end`；`EventSource` 失败回退轮询；小程序仍轮询；非逐 token 正文流；224 tests，ruff 干净 |
| 2026-11-02 | M4.6 本地下载即用 | 网页 AI 设置（只写本地 `.env`、不回显 key、回环 Host 限制、连接测试、换服务商必须重填 key）；启动脚本实际检查 Python 3.11+；依赖上限与 `.gitattributes`；README 重排 + LOCAL/STATUS 文档；干净副本启动/配置/生成/导出/重启验收；243 passed / 2 skipped，ruff 干净；尚未提交/发布 |
| 2026-11-02 | M5 冻结 | 用户要求先保证本地网页版可用、数据库全在本地、每人自购自配 AI API；公网登录/多租户/云数据库/配额/计费移入冻结 Backlog |
| 2026-11-02 | 许可证与 GitHub 发布 | 用户选择 MIT 并授权提交/推送；新增 `LICENSE`，README 加 ZIP 下载入口；本地 Claude 助手文件从 Git 历史移除并加入 `.gitignore`；推送 `master` 到 `huang-weilin/novel_bee`，clone 后 243 passed / 2 skipped；tag/Release 尚未创建 |
