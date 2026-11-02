# 本地版 API

> 本地网页和微信小程序共用这一套 JSON 接口。当前版本没有登录，只应监听
> `127.0.0.1`。FastAPI 自带的交互文档在启动后是 `http://127.0.0.1:8000/docs`。
> 小程序的安装和使用见 [MINIPROGRAM.md](MINIPROGRAM.md)。

## 1. 启动

```bash
python -m novel_pipeline.server
# 等价于
novel-pipeline
```

常用参数：

| 参数 | 默认 | 作用 |
|---|---|---|
| `--host` | `127.0.0.1` | 监听地址；本地使用不要改成 `0.0.0.0` |
| `--port` | `8000` | 端口 |
| `--data` | `data/novel.db` | SQLite 文件 |
| `--quality-mode` | `full` | `rules` / `rules+llm` / `rules+score` / `full` |
| `--no-browser` | 关 | 不自动打开浏览器 |

环境变量同名项见 `.env.example`；命令行参数优先。

## 2. 一次生成怎么走

1. `POST /api/projects` 建作品；
2. 可选：`POST /api/projects/{id}/chapters/trial` 先要一个短试写片段，确认方向；
3. `POST /api/projects/{id}/chapters/generate` 提交一章，立即返回 `202` 和一个
   `job_id`；
4. 网页用 `GET /api/jobs/{job_id}/events` 接收 SSE 进度；小程序每 1.5 秒
   `GET /api/jobs/{job_id}` 轮询；任务完成或失败后停止；
5. `GET /api/projects/{id}` / `GET .../chapters/{seq}` 看正文和质量分；
6. 待确认章节可以带 `chapter_seq` 再提交一次，覆盖重写；已定稿章节不允许重写
   （记忆已经写入，重写会制造前后矛盾）。

任务在进程内存里排队，默认单 worker。服务重启会丢掉“进行中”的任务状态；章节
正文由 `ChapterPipeline` 写入 SQLite，不会丢。

## 3. 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 服务状态、数据路径、AI 是否配置（不返回 key） |
| `GET` | `/api/settings` | 本机 AI 配置摘要（不返回 key） |
| `POST` | `/api/settings` | 保存服务商/模型/Base URL/Key 到本机 `.env` |
| `POST` | `/api/settings/test` | 用当前表单值做一次很小的连接测试，不保存 |
| `GET` | `/api/genres` | 题材列表、场景卡字段、题材必填项、自检项 |
| `GET` | `/api/projects` | 作品列表和章节统计 |
| `POST` | `/api/projects` | 新建作品 |
| `GET` | `/api/projects/{id}` | 作品详情 + 章节列表 |
| `GET` | `/api/projects/{id}/memory` | 人物/物品/伏笔/情感债/世界规则摘要 |
| `POST` | `/api/projects/{id}/characters` | 补登人物（用于解决待确认项） |
| `POST` | `/api/projects/{id}/items` | 补登物品（用于解决待确认项） |
| `GET` | `/api/projects/{id}/chapters` | 章节列表（不含正文） |
| `GET` | `/api/projects/{id}/chapters/{seq}` | 单章正文 + `review_items` |
| `POST` | `/api/projects/{id}/chapters/generate` | 提交生成任务 |
| `POST` | `/api/projects/{id}/chapters/trial` | 提交短试写任务（不写章节/记忆） |
| `GET` | `/api/jobs/{job_id}` | 任务状态和结果（`kind` 区分 generate/trial） |
| `GET` | `/api/jobs/{job_id}/events` | 同一份任务状态的 SSE 进度流（网页用） |
| `GET` | `/api/projects/{id}/export` | 导出 TXT（默认含待确认） |

### AI 设置

`GET /api/settings` 返回摘要，不含 Key：

```json
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "base_url": "https://api.deepseek.com",
  "key_configured": true,
  "providers": [
    {
      "key": "deepseek",
      "label": "DeepSeek",
      "protocol": "openai",
      "default_model": "deepseek-chat",
      "default_base_url": "https://api.deepseek.com",
      "requires_base_url": false,
      "requires_key": true
    }
  ],
  "data_path": "data/novel.db",
  "env_path": ".env",
  "error": null
}
```

保存（同一个请求体也用于 `/api/settings/test`）：

```json
POST /api/settings
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "base_url": "https://api.deepseek.com",
  "api_key": "你的 key"
}
```

- 只写 `NOVEL_LLM_PROVIDER`、`NOVEL_LLM_MODEL`、`NOVEL_LLM_BASE_URL`、
  `NOVEL_LLM_API_KEY` 四个键，保留 `.env` 其他行和注释。
- 当前服务商不变时，`api_key` 留空表示保留旧 Key；更换服务商时必须填新 Key。
- 保存后更新当前进程环境，立即生效，不需要重启。系统环境变量仍优先于 `.env`。
- 响应和错误都不会包含 Key。
- 测试连接只发一次很小的请求；成功返回 `{"ok": true, "message": "连接成功", ...}`，
  失败返回 `200` + `{"ok": false, "message": "脱敏后的中文原因"}`。
- 设置接口只接受本机 Host（`127.0.0.1` / `localhost` / `::1`）；通过局域网 IP
  访问时返回 `403`。小程序不调用这些接口。

### 新建作品

```json
POST /api/projects
{"title": "修仙界315", "genre": "xianxia_comedy", "target_chapters": 120}
```

`genre` 可以是内置 key（`xianxia_comedy` / `gufeng_mystery` / `urban_romance`）、
中文题材名，或自定义字符串；匹配不到时走 `default`，不会报错。

### 提交一章

```json
POST /api/projects/{id}/chapters/generate
{
  "outline": "许青去物业退装修押金，前台用一张《退款流转单》把他支去三个窗口。他今天必须拿回钱交房租；失败就会失去住处。本章兑现：他逼前台在登记页上写下受理时间。结尾留更大的问题：盖章的人查无此人。",
  "title": "退款流转单",
  "target_words": 2000,
  "pov": "第三人称",
  "style_constraints": "克制、具体物件、少形容词；人物声口区分。",
  "character_brief": "许青，社区调解员，怕丢工作；前台小周，嘴甜但怕担责。",
  "quality_mode": "full",
  "scene_plan": {
    "opening_hook": "许青第三次来退押金，前台换了一张新表。",
    "reader_promise": "让前台当场写下受理时间。",
    "suppression": "退款流程本身：三个窗口互相推。",
    "stakes": "今天拿不到钱就交不上房租。",
    "payoff_tool": "前文埋过的登记页照片。",
    "payoff": "前台在登记页写下时间，旁边办业务的老人看见。",
    "next_hook": "盖章的经办人查无此人。"
  }
}
```

返回：

```json
{
  "id": "job-uuid",
  "project_id": "project-uuid",
  "chapter_seq": 1,
  "status": "queued",
  "message": "排队中",
  "progress": 5,
  "result": null,
  "error": null
}
```

`chapter_seq` 不传时自动取下一章。传了只允许重写 `pending`（待确认）章节。

可选字段 `trial_text`（最多 2000 字）：把确认过的试写片段传给正式生成，作为
叙述视角、语气和人物关系的方向参考。提示词明确要求不要照抄原句；它不会替代
本章大纲。

### 试写（不写章节、不写记忆）

```json
POST /api/projects/{id}/chapters/trial
{
  "outline": "本章大纲，和正式生成相同",
  "title": "可选",
  "target_words": 500,
  "pov": "第三人称",
  "style_constraints": "克制、具体物件。",
  "character_brief": "许青，社区调解员。",
  "scene_plan": {"opening_hook": "……"}
}
```

字段和正式生成基本一致，但 `target_words` 范围是 200–1200。返回同样是 `202`
加一个任务，`kind` 为 `trial`。任务完成后的结果：

```json
{
  "status": "trial",
  "project_id": "project-uuid",
  "chapter_seq": 4,
  "content": "试写片段正文……",
  "chars": 486,
  "target_words": 500,
  "context_tokens": 8123
}
```

试写只读上下文并调用一次写作模型，不跑质量门、不保存章节、不写记忆。确认方向
后，客户端把这段文字作为 `trial_text` 提交正式生成。新章节不传 `chapter_seq`；
重新试写已有 `pending` 章节时才传。

### 任务状态

| `status` | 含义 |
|---|---|
| `queued` | 排队中 |
| `running` | 写作/质量门/记忆检查中 |
| `done` | 结束；看 `result.status` 是 `final` 还是 `pending` |
| `failed` | 失败；看 `error` |

`result` 是 `PipelineResult.to_dict()`：正文、质量报告（分数、维度、失败项）、
一致性报告、抽取/写入结果、尝试次数和备注。`result.status` 为 `final` 表示
质量门 accept 且记忆已写入；`pending` 表示正文保存了，但质量门未 accept 或抽取
需要人工看，**记忆没有写入**。

### 任务进度（SSE）

网页通过 `GET /api/jobs/{job_id}/events` 订阅进度。事件体就是任务状态的 JSON，
和 `GET /api/jobs/{job_id}` 相同：

```
data: {"id":"job-uuid","status":"running","message":"正在写作并跑质量门","progress":20,...}

data: {"id":"job-uuid","status":"done","message":"已定稿","progress":100,...}

event: end
data: {}
```

任务结束（`done` / `failed`）后服务端发送 `event: end` 并关闭连接；空闲时每
10 秒发送 `: keep-alive` 注释。当前是**任务进度流**，不是逐 token 的正文流：
写作调用仍是阻塞的，正文在任务完成后一次性拿到。小程序没有 `EventSource`，
继续用 1.5 秒轮询；网页在不支持 `EventSource` 或连接失败时也会自动回退到轮询。

### 待确认章节：补登人物/物品

章节详情里的 `review_items` 保存了“正文已写、记忆没写”的具体原因。常见两类：

```json
[
  {"kind": "character", "name": "马师兄", "reason": "unknown_character", "detail": {"status": "外门弟子"}},
  {"kind": "item", "name": "投诉台账", "reason": "unknown_item", "detail": {"delta": 1}}
]
```

在网页里可以直接登记；用 API 时：

```json
POST /api/projects/{id}/characters
{"name": "马师兄", "status": "外门弟子", "core_attributes": {"身份": "外门弟子"}, "first_chapter": 2}

POST /api/projects/{id}/items
{"name": "投诉台账", "quantity": 1, "unit": "本", "updated_chapter": 3}
```

登记只解决“记忆里没有这个实体”，不会自动改正文。之后必须带 `chapter_seq` 再提交
一次重写；重写会重新抽取、检查并尝试写入记忆。`review_items` 里也可能出现伏笔、
情报、情感债等条目，当前网页只展示原因；这些需要改大纲或正文后重写。

`kind=info_gain` 且 `reason=unknown_character` 时，同样可以先用
`POST /characters` 登记该人物，再重写。

### 场景卡

字段与 `novel_pipeline.planning.SCENE_FIELD_LABELS` 一致；`GET /api/genres`
会给出每个题材的必填字段。不填必填项不会报错，生成提示会要求模型自己在心里
补全，但填了通常更稳定。当前 UI 为所有字段提供输入框，必填项带 `*`。

## 4. 质量模式

| 模式 | 做什么 | 适用 |
|---|---|---|
| `rules` | Q01–Q06、Q11、Q12 程序化规则 | 最快，调流程 |
| `rules+llm` | 再加 Q07–Q10 Verifier | 看语义问题 |
| `rules+score` | 规则 + 四维评分 | 平衡成本 |
| `full` | 全部 + Verifier + 评分 | 默认，最严 |

`full` 每章比 `rules` 多两次 LLM 调用（Verifier、Scorer），加上抽取器和一致性
检查，成本和等待时间明显更高。Q12 只是长度告警，不单独阻止定稿。

## 5. 错误

| HTTP | 场景 |
|---|---|
| `400` | AI 未配置；设置值非法；请求本身能解析但无法生成 |
| `403` | 通过非本机 Host 调用 AI 设置接口 |
| `404` | 作品/章节/任务不存在 |
| `409` | 同一作品已有任务在跑；或试图重写已定稿章节 |
| `422` | 参数校验失败（大纲为空、字数越界等） |

错误体是 `{"detail": "中文说明"}`；422 的 `detail` 是字段错误数组。

## 6. 安全边界

- 本地服务没有登录，默认只监听回环地址；
- AI Key 可以通过网页写入本机 `.env`，但所有响应都不返回 Key；设置接口只接受
  本机 Host，局域网访问会被拒绝；
- 不要把 `--host 0.0.0.0` 直接暴露到公网；远程部署必须加认证网关；
- 生产多用户/多进程需要 PostgreSQL 16 和真正的任务队列，当前 SQLite + 进程内
  任务表只适合单机单用户。
