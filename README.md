# 长篇小说工坊（本地版）

一个在自己电脑上运行的长篇 AI 小说生成工具：编排 → 生成 → 质量门 → 结构化记忆 → 一致性校验。网页直接打开就能用，不需要 Node 构建、Docker、PostgreSQL 或 Redis。

**当前状态**：本地网页版可用，支持下载后一键启动、网页内配置自己的 AI API、SQLite 本地存储和 TXT 导出；微信小程序是本地预览形态；公网多用户/云端版尚未实现。

## 快速开始

### Windows

1. 下载并解压项目（或 `git clone`）。
2. 双击 `start.bat`。
3. 第一次会自动创建 `.venv`、安装依赖，然后打开浏览器：<http://127.0.0.1:8000>。
4. 在网页右上角点 **AI 设置**，填自己的 AI Key。

如果提示找不到 Python：安装 [Python 3.11+](https://www.python.org/downloads/)，安装时勾选 **Add python.exe to PATH**，再运行 `start.bat`。

### macOS / Linux

```bash
./start.sh
```

没有执行权限时先运行 `chmod +x start.sh`。

### 手动启动（可选）

```bash
python -m venv .venv
# Windows
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m novel_pipeline.server
# macOS / Linux
.venv/bin/python -m pip install -e .
.venv/bin/python -m novel_pipeline.server
```

详细步骤、端口修改和常见错误见 [本地版使用说明](docs/LOCAL.md)。

## 第一次配置 AI

网页右上角 **AI 设置** → 选服务商 → 填模型和 Key → 保存（可先点“测试连接”）。

- **Key 只写在本机 `.env`**，不会上传到本工具，也不会出现在接口返回或网页回显里。
- 每个用户用自己的 AI 账号和额度；工具本身不提供 Key，也不代付费用。
- 测试连接会向服务商发一次很小的请求，可能产生极少量费用。
- 保存后立即生效，不用重启。
- 系统环境变量优先于 `.env`；如果重启后配置被覆盖，检查是否设置过同名环境变量。
- 更换服务商后通常需要新的 Key，网页会要求重新填写。

| 服务商 | 模型示例 | Base URL | Key 申请 |
| --- | --- | --- | --- |
| DeepSeek | `deepseek-chat` | 留空使用默认 | <https://platform.deepseek.com/> |
| OpenAI | `gpt-4o-mini` | 留空使用默认 | <https://platform.openai.com/api-keys> |
| Anthropic | `claude-sonnet-5` | 留空使用默认 | <https://console.anthropic.com/> |
| OpenAI 兼容 | 按服务商文档 | **必填**，通常以 `/v1` 结尾 | 按服务商文档 |
| Anthropic 兼容 | 按服务商文档 | **必填** | 按服务商文档 |
| Ollama（本地） | 例如 `qwen2.5:7b` | 默认 `http://localhost:11434/v1` | 不需要 |

也可以手动编辑项目根目录的 `.env`，模板见 `.env.example`。不要把 `.env` 发给别人或提交到 Git。

## 数据在本地

- 数据库：`data/novel.db`（SQLite，首次启动自动建表）。
- 作品、章节、人物、物品、伏笔、情感债、待确认原因都在这个文件里。
- 生成任务在内存里：重启会丢失“排队中/生成中”的任务，但已写入数据库的章节不会丢。
- **备份**：停止服务（`Ctrl+C`）后复制 `data/novel.db`。
- **恢复**：停止服务，把备份复制回 `data/novel.db`，再启动。
- **升级**：保留 `data/` 和 `.env`，替换其他文件后重新启动。不要覆盖 `data/`。

## 能做什么

- 新建作品、选择题材（题材只改变写法和自检项，不改变记忆与质量门）。
- 填章节大纲和场景卡，生成正文；网页实时显示任务进度（SSE，连接失败自动回退轮询）。
- 质量门自动判断：**定稿**、**待确认**、失败。未通过时正文仍会保存，不会丢。
- 待确认章节可以补登缺失人物/物品，改大纲后重写；已定稿章节受记忆保护。
- 查看人物、物品、未回收伏笔、未还情感债和世界规则。
- 导出整本 TXT。

## 质量模式与费用

| 模式 | 检查内容 | 调用量 |
| --- | --- | --- |
| `rules` | 规则 + 中文标点/长度检查 | 最少，适合先跑通流程 |
| `rules+score` | 规则 + AI 四维评分 | 较少 |
| `rules+llm` | 规则 + AI 审核 | 较多 |
| `full` | 规则 + AI 审核 + 四维评分（默认） | 最多、最慢、最费 token |

第一次试用建议先用 `rules` 或 `rules+score`，确认接口和流程正常后，再考虑 `full`。

## 本地版边界

- 默认只监听 `127.0.0.1`，**没有登录、没有多用户隔离**；不要暴露到公网，也不要在路由器上做端口映射。
- AI 设置接口只接受本机 Host；通过局域网 IP 打开网页时会被拒绝。需要局域网访问时，在本机 `127.0.0.1` 配好，或手动编辑 `.env`。
- SQLite 适合单机单用户；多人或远程部署需要 PostgreSQL 16（迁移脚本在 `migrations/`）。
- 小程序 `miniprogram/` 与网页共用同一套本地接口，目前没有登录和 `msgSecCheck`，只能本地预览，不能直接公开上线。
- 正文由 AI 生成，可能有事实、逻辑或版权问题；发布前请自行判断和修改。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 找不到 Python / 版本太低 | 安装 Python 3.11+，勾选 Add to PATH |
| 页面打不开 | 看启动窗口是否报错；确认访问 `http://127.0.0.1:8000` |
| AI 接口未配置 | 打开网页“AI 设置”保存 Key；检查系统环境变量是否覆盖 |
| 401 / 403 / 余额不足 | 到服务商后台检查 Key、权限和余额 |
| 404 / 连接超时 | 检查 Base URL、模型名、网络或代理；Ollama 确认本地服务已启动 |
| 端口被占用 | `start.bat --port 8123` 或 `./start.sh --port 8123` |

更多说明见 [docs/LOCAL.md](docs/LOCAL.md)。

## 文档

- [本地版使用说明](docs/LOCAL.md) — 下载、启动、配置、备份、升级、排错
- [本地版 API](docs/API.md) — 网页与小程序共用的接口
- [微信小程序（本地版）](docs/MINIPROGRAM.md) — 导入、确认关口、真机调试与限制
- [开发计划](docs/PLAN.md) — 唯一计划源
- [任务清单](docs/TASKS.md) — 当前 Sprint
- [开发状态与历史回归](docs/STATUS.md) — 从 README 移出的长文记录
- [质量层规格](docs/SPEC-quality.md)
- [记忆与一致性规格](docs/SPEC-memory.md)
- [M3.5 非技术审核指南](docs/REVIEW.md)
- [文风卡](docs/STYLE.md)
- [爽点与开篇钩子](docs/PAYOFF.md)
- [题材分层](docs/GENRES.md)
- [ADR-0001](docs/ADR/0001-foundation-and-licenses.md)
- [ADR-0002：LLM 可配置 provider](docs/ADR/0002-llm-provider-config.md)
- [ADR-0003：存储适配器](docs/ADR/0003-storage-adapter.md)

## 目录

```
docs/                 计划、规格、决策记录
migrations/           PostgreSQL 迁移脚本（生产契约）
src/novel_pipeline/   核心代码
  server/             FastAPI + 本地网页（无需前端构建）
tests/                测试
data/                 本地运行数据（不提交）
references/           参考仓库，只读，不提交
miniprogram/          微信小程序（本地预览）
start.bat / start.sh  本机一键启动
```

## 许可证

本项目使用 [MIT 许可证](LICENSE)。第三方参考仓库只用于研究思路，不包含其代码；各自许可证与用途记录在 [docs/STATUS.md](docs/STATUS.md#参考仓库与许可)。
