# AI 小说生成管线

面向微信小程序的长篇网文生成管线：编排 → 生成 → 质量门 → 结构化记忆 → 一致性校验。

当前状态：**M2 已完成**（质量适配器 + Q01–Q08 + 四维评分 + 重试控制 + 10 章校准），下一步 M3 记忆与一致性。

## 文档

- [开发计划](docs/PLAN.md) — 唯一计划源
- [任务清单](docs/TASKS.md) — 当前 Sprint
- [质量层规格](docs/SPEC-quality.md)
- [记忆与一致性规格](docs/SPEC-memory.md)
- [ADR-0001](docs/ADR/0001-foundation-and-licenses.md)
- [ADR-0002：LLM 可配置 provider](docs/ADR/0002-llm-provider-config.md)

## 目录

```
docs/                 计划、规格、决策记录
src/novel_pipeline/   自研代码（M2 起）
tests/                测试
data/                 本地运行数据（不提交）
references/           参考仓库，只读，不提交
```

## 参考仓库与许可

| 仓库 | 许可证 | 用途 |
|---|---|---|
| [Mo-Shen](https://github.com/wwxxzz666/Mo-Shen) | MIT | 编排/确认关口/小程序参考 |
| [NovelFactory](https://github.com/Jason-ship/langgraph) | MIT | 评分阈值参考 |
| [Novel-factory](https://github.com/YoRengzh/Novel-factory) | Apache-2.0 | 账本/体检参考 |
| [xt-webnovel-writing](https://github.com/xiaotiewinner/xt-webnovel-writing) | 无 | 仅借鉴问题类别 |
| [my-novel-agent](https://github.com/lazyayuan/my-novel-agent) | 无 | 仅借鉴压缩策略 |

`references/` 已被 gitignore；无许可证仓库的代码、prompt、条款原文不得复制进本项目。

## 模型配置

AI 接口通过环境变量配置，不在代码里硬编码 key。复制 `.env.example` 为 `.env` 后按需修改：

| 变量 | 作用 |
|---|---|
| `NOVEL_LLM_PROVIDER` | `deepseek` / `openai` / `anthropic` / `openai-compatible` / `anthropic-compatible` / `ollama` |
| `NOVEL_LLM_MODEL` | 模型名 |
| `NOVEL_LLM_BASE_URL` | 自定义端点（兼容 provider 必填） |
| `NOVEL_LLM_API_KEY_ENV` | 存放 key 的环境变量名 |
| `NOVEL_LLM_API_KEY` | 直接传 key（CI 用，优先） |

本机 Claude Code 的 `ANTHROPIC_AUTH_TOKEN` 实际是 DeepSeek key，走 `https://api.deepseek.com/anthropic`。复用时配置：

```env
NOVEL_LLM_PROVIDER=anthropic-compatible
NOVEL_LLM_BASE_URL=https://api.deepseek.com/anthropic
NOVEL_LLM_MODEL=deepseek-v4-flash
NOVEL_LLM_API_KEY_ENV=ANTHROPIC_AUTH_TOKEN
```

`LLMConfig.to_storyagents_env()` 会把上述配置映射成 Mo-Shen 需要的 `STORYAGENTS_*` 环境变量。

## 质量门

规则引擎可独立跑在任意一章正文上：

```bash
python -m novel_pipeline.quality data/m1-chapter-2000.md --mode rules --log-file data/quality.log
```

`--mode log_only` 只记录不拦截；`--mode rules` 执行 Q01–Q06；`--mode rules+llm` 额外调用 Q07–Q08；`--mode rules+score` / `full` 再叠加四维评分。输出 `pass/decision/failures` JSON，当前阈值在 `config/quality.json`。

10 章校准可直接跑：

```bash
python -m novel_pipeline.quality.calibrate data/calibration --mode rules+score --revisions --output data/calibration.json
```

校准结果（2026-11-01，10 章短篇 AI 样本）：初评 9 accept / 1 polish，终评 10 accept，均分 82.7，平均重写 0，平均 polish 0.1。样本偏短，人工标注版 20 章校准待有真实稿后补做。

## 下一步

M3：PostgreSQL 记忆表、Memory Extractor、Context Assembler、R01–R05 一致性规则。见 `docs/TASKS.md`。
