# 本地网页版使用说明

这是给“下载到自己电脑上用”的版本。代码、数据库、配置和 AI Key 都在你自己的电脑上；工具本身不提供云端账号，也不替你付费。你需要自己购买或申请一个 AI 接口，把 Key 填进本机。

## 1. 运行要求

- Windows 10/11，或 macOS / Linux。
- Python 3.11 或更新版本（启动脚本会检查）。
- 第一次安装依赖需要联网；之后启动不一定需要联网。
- 生成章节时需要能访问你选择的 AI 服务商。

不需要 Node.js、Docker、PostgreSQL、Redis，也不需要安装数据库。数据存在一个 SQLite 文件里。

## 2. 下载与启动

### Windows

1. 下载并解压项目（或 `git clone`）。
2. 双击 `start.bat`。
3. 第一次会自动创建 `.venv`、安装依赖；看到 `Open http://127.0.0.1:8000` 后浏览器会自动打开。
4. 关闭：在黑色窗口按 `Ctrl+C`，或直接关闭窗口。

如果提示找不到 Python：到 <https://www.python.org/downloads/> 下载 3.11+，安装时勾选 **Add python.exe to PATH**，再重新双击 `start.bat`。

### macOS / Linux

```bash
./start.sh
```

如果提示没有执行权限：

```bash
chmod +x start.sh
./start.sh
```

也可以显式指定解释器：

```bash
PYTHON=python3.12 ./start.sh
```

### 手动启动（可选）

```bash
python -m venv .venv
# Windows: .venv\Scripts\python.exe -m pip install -e .
# macOS/Linux: .venv/bin/python -m pip install -e .
.venv/bin/python -m novel_pipeline.server
```

Windows 手动命令把路径换成 `.venv\Scripts\python.exe`。

## 3. 第一次配置 AI

打开网页后，右上角点 **AI 设置**；如果是第一次，页面顶部也会出现“先配置你自己的 AI API”的引导卡。

填写四项：

| 服务商 | 模型示例 | Base URL | Key 在哪里申请 |
| --- | --- | --- | --- |
| DeepSeek | `deepseek-chat` | 留空（默认 `https://api.deepseek.com`） | <https://platform.deepseek.com/> |
| OpenAI | `gpt-4o-mini` | 留空 | <https://platform.openai.com/api-keys> |
| Anthropic | `claude-sonnet-5` | 留空 | <https://console.anthropic.com/> |
| OpenAI 兼容接口 | 按服务商文档 | **必填**，通常以 `/v1` 结尾 | 按服务商文档 |
| Anthropic 兼容接口 | 按服务商文档 | **必填** | 按服务商文档 |
| Ollama（本地） | 例如 `qwen2.5:7b` | 留空（默认 `http://localhost:11434/v1`） | 不需要 Key |

说明：

- **Key 只写入本机 `.env`**，不会上传到本工具，也不会出现在接口返回或网页回显里。
- 点“测试连接”会向所选服务商发一次很小的请求，可能产生极少量费用。
- 保存后当前进程立即生效，不需要重启。
- 如果系统里已经设置了同名环境变量（例如 `NOVEL_LLM_API_KEY`），**系统环境变量优先于 `.env`**；重启后仍以系统变量为准。
- 更换服务商后通常需要新的 Key。网页会要求你重新填写，避免把旧服务商的 Key 发给新服务商。
- 也可以手动编辑项目根目录的 `.env`。不要把 `.env` 发给别人或提交到 Git。

## 4. 使用流程

1. 左侧“新建作品”，选题材、起书名。
2. 在“写下一章”里填本章大纲：谁要做什么、谁压着他、失败失去什么、本章兑现什么。
3. 选质量模式：
   - `rules`：最快，只做规则检查，适合先跑通流程。
   - `rules+score`：规则 + AI 评分，费用较低。
   - `rules+llm`：规则 + AI 审核。
   - `full`：最严格，调用最多、费用最高（默认）。
4. 点“开始生成”。生成完成后：
   - **定稿**：通过质量门，记忆账本自动更新。
   - **待确认**：正文已保存，但没有写入记忆；可以登记缺失的人物/物品，改大纲后点“重写本章”。
5. 右上角“导出 TXT”导出已写章节。

第一次试用建议先用 `rules` 或 `rules+score`，确认接口和流程正常后，再考虑 `full`。

## 5. 数据、备份和升级

### 数据在哪里

默认数据库：`data/novel.db`。

所有作品、章节、人物、物品、伏笔、情感债、待确认原因都在这个文件里。首次启动会自动创建 `data/` 和表结构，不需要手动建库。

生成任务本身在内存里：服务重启会丢失“排队中/生成中”的任务，但已经写入数据库的章节不会丢。

### 备份

先停止服务（`Ctrl+C`），然后复制整个 `data/novel.db` 到安全位置。建议按日期命名，例如 `novel-2026-11-02.db`。

### 恢复

先停止服务，把备份文件复制回 `data/novel.db`，再启动。

### 升级

1. 停止服务。
2. 保留 `data/` 和 `.env`。
3. 用新版本代码替换除 `data/`、`.env` 以外的文件（重新解压或 `git pull`）。
4. 重新运行 `start.bat` / `./start.sh`。

不要覆盖 `data/`，否则会丢作品。

### 备份整个项目

如果只想整体搬走，退出程序后复制整个文件夹即可；`.venv/` 可以不复制，换电脑后重新启动会自动安装。

## 6. 端口和常见错误

### 端口被占用

```bash
# Windows
start.bat --port 8123
# macOS/Linux
./start.sh --port 8123
```

也可以在 `.env` 里设置：

```dotenv
NOVEL_SERVER_PORT=8123
```

然后访问 `http://127.0.0.1:8123`。

### 常见错误

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `Python 3.11 or newer was not found` | 没装 Python 或版本太旧 | 安装 3.11+，勾选 Add to PATH |
| `pip install` 失败 | 网络/代理问题 | 检查网络，重试；公司网络可能需要代理 |
| `AI 接口未配置` | Key 没保存或环境变量覆盖 | 打开 AI 设置重新保存；检查系统环境变量 |
| `LLM HTTP 401` / `403` | Key 无效、过期、无权限 | 到服务商后台确认 Key 和余额 |
| `LLM HTTP 404` | Base URL 或模型名不对 | 兼容接口检查 `/v1` 和模型名 |
| 连接超时 | 网络无法访问服务商 | 检查网络/代理；Ollama 确认本地服务已启动 |
| 余额不足 | 服务商账户欠费 | 充值或换 Key |
| 页面打不开 | 服务没启动/端口不对 | 看黑色窗口报错；确认地址和端口 |

## 7. 安全边界

- 服务默认只监听 `127.0.0.1`，只有本机能访问。
- **没有登录、没有多用户隔离**，不要把端口暴露到公网，也不要在路由器上做端口映射。
- AI 设置接口只接受本机 Host；通过局域网 IP 打开网页时，设置会被拒绝。需要局域网访问时，请在本机 `127.0.0.1` 配好，或手动编辑 `.env`。
- Key 只存在本机 `.env` 和当前进程环境里；不要截图、不要发群、不要提交 Git。
- 生成的正文由 AI 产生，可能有事实、逻辑或版权问题，发布前请自行判断和修改。

## 8. 卸载

先备份 `data/novel.db`，然后删除整个项目文件夹即可。没有注册表、系统服务或后台常驻进程。

## 9. 小程序（可选）

`miniprogram/` 是本地预览用的小程序，和网页共用同一个本地后端。它需要微信开发者工具，且当前没有登录和内容安全校验，不能直接公开上线。详见 [MINIPROGRAM.md](MINIPROGRAM.md)。
