# 任务清单

> 规则：同一时间只允许一个 `[>]`。新想法先放 Backlog，不直接开工。
> 状态：`[ ]` 待办 · `[>]` 进行中 · `[x]` 完成 · `[~]` 冻结

## 当前 Sprint：M2 质量层（已完成；下一 Sprint：M3）

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

- [ ] T3-1 PostgreSQL schema 与迁移脚本
- [ ] T3-2 Memory Extractor（严格 JSON + Pydantic 校验）
- [ ] T3-3 Context Assembler（结构化事实 + 最近 3 章摘要 + 本章大纲）
- [ ] T3-4 一致性规则 R01–R05
- [ ] T3-5 连续 10 章回归：token 曲线 + “死人说话”测试

**M3 验收**：10 章 prompt token 不线性上升；阻断级问题在定稿前被拦住。

## M4 小程序

- [ ] T4-1 生产级 HTTP/FastAPI 包装（替换 stdlib server）
- [ ] T4-2 小程序三类确认界面：大纲/试写/质量待确认
- [ ] T4-3 SSE 流式进度
- [ ] T4-4 `msgSecCheck` 输入/输出 + “内容由 AI 生成”标识
- [ ] T4-5 端到端 3 章验收

## Backlog（冻结，不排期）

- [~] 25 条反 AI 味规则全量
- [~] Neo4j / 图谱记忆
- [~] Milvus / 向量检索
- [~] 多租户、计费、运营后台
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
