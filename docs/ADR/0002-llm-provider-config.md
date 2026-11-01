# ADR-0002：LLM 接口统一为可配置 provider

- 状态：Accepted
- 日期：2026-11-01
- 决策人：项目发起人

## 背景

开发机上的 Claude Code 配置为：

```json
{
  "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
  "ANTHROPIC_AUTH_TOKEN": "sk-...",
  "ANTHROPIC_MODEL": "deepseek-v4-flash"
}
```

这不是 Anthropic 官方 key，而是 **DeepSeek 的 key 走 Anthropic 兼容端点**。因此：

- 不能把它当作 Claude 官方 key 发往 `api.anthropic.com`；
- 可以用它调用 `https://api.deepseek.com/anthropic` 的 Messages API；
- Mo-Shen 的 `anthropic` provider 不传 `base_url`，但 AgentScope 的 Anthropic SDK 会读取 `ANTHROPIC_BASE_URL`，所以设置环境变量即可复用，无需改源码。

## 决策

1. **统一用环境变量配置**，不在代码或仓库中硬编码 key。
2. `LLMConfig` 支持 6 类 provider：
   - `deepseek`、`openai`、`anthropic`（原生）
   - `openai-compatible`、`anthropic-compatible`（自定义 base_url）
   - `ollama`（本地）
3. 配置项：

   | 变量 | 作用 | 默认 |
   |---|---|---|
   | `NOVEL_LLM_PROVIDER` | provider | `deepseek` |
   | `NOVEL_LLM_MODEL` | 模型名 | provider 默认 |
   | `NOVEL_LLM_BASE_URL` | 自定义端点 | provider 默认 |
   | `NOVEL_LLM_API_KEY_ENV` | 存放 key 的环境变量名 | provider 默认 |
   | `NOVEL_LLM_API_KEY` | 直接传 key（CI 用） | 空 |
   | `NOVEL_LLM_TEMPERATURE` | 采样温度 | `0.8` |
   | `NOVEL_LLM_MAX_TOKENS` | 输出上限 | `4096` |
   | `NOVEL_LLM_TIMEOUT` | 超时秒数 | `120` |

4. **密钥只在调用时解析**：`LLMConfig` 保存的是环境变量名，`repr` 不包含密钥。
5. **提供 `to_storyagents_env()` 适配器**：把我们的配置映射成 Mo-Shen 的 `STORYAGENTS_*` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` 等变量，M1/M2 直接复用 Mo-Shen 的模型工厂。

## 本机推荐配置

```env
NOVEL_LLM_PROVIDER=anthropic-compatible
NOVEL_LLM_BASE_URL=https://api.deepseek.com/anthropic
NOVEL_LLM_MODEL=deepseek-v4-flash
NOVEL_LLM_API_KEY_ENV=ANTHROPIC_AUTH_TOKEN
```

`ANTHROPIC_AUTH_TOKEN` 已由 Claude Code 注入当前环境，不需要写入 `.env`。如果换到没有该变量的机器，再在 `.env` 里设置 `NOVEL_LLM_API_KEY` 或 `NOVEL_LLM_API_KEY_ENV`。

## 后果

正面：

- 换模型/换供应商只改环境变量；
- 本机现有 DeepSeek 额度可直接复用；
- 密钥不会进入 git；
- 兼容端点与官方端点走同一套接口。

负面：

- 不同 provider 的模型名、上下文长度、thinking 行为不同，需要按 provider 校准；
- `anthropic-compatible` 依赖 SDK 读取 `ANTHROPIC_BASE_URL`，升级 AgentScope 时需回归测试；
- 复用当前 token 会产生额外用量，需要监控成本。

## 复审触发条件

- 更换 AgentScope 版本后 `ANTHROPIC_BASE_URL` 失效；
- 需要 Anthropic 官方 thinking / prompt caching 等特性；
- 成本或额度策略变化。
