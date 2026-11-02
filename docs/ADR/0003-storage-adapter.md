# ADR-0003：PostgreSQL 为生产契约，SQLite 为本地开发适配器

- 状态：Accepted
- 日期：2026-11-01
- 关联任务：T3-1

## 背景

`SPEC-memory.md` 指定 PostgreSQL 16 + JSONB，本地用 Docker。但当前开发机：

- 没有 Docker；
- 没有 PostgreSQL 客户端或服务；
- 安装 PostgreSQL 需要管理员权限和系统级服务变更，未获用户明确授权。

M3 的记忆抽取、上下文组装、一致性规则都需要可运行的存储层，不能因环境缺失停摆。

## 决策

1. **生产契约仍是 PostgreSQL 16**：`migrations/001_init.sql` 是权威 schema，包含 `uuid / jsonb / timestamptz / numeric / boolean` 与约束、索引。
2. **本地开发/测试使用 SQLite 适配器**：`MemoryStore` 用标准库 `sqlite3`，表名、列名、唯一约束、外键关系与生产 schema 对齐；仅物理类型不同（TEXT 存 UUID/JSON，INTEGER 存布尔）。
3. **切换点隔离在 store 层**：抽取器、上下文组装器、一致性规则只依赖 `MemoryStore` 的语义接口和 dataclass，不直接拼 SQL；后续新增 `PostgresMemoryStore` 时业务代码不动。
4. SQLite 适配器开启 `PRAGMA foreign_keys = ON`，并保留 `quality_failures`、`confirmations` 等审计表。

## 后果

- 正面：M3 全链路可在本机测试；迁移脚本已提前锁定生产表结构；无额外依赖。
- 负面：PostgreSQL 特有的 JSONB 查询、UUID 类型、事务隔离、索引行为尚未在真实 PG 上验证。
- 待办：有 PostgreSQL 环境后补跑 `migrations/001_init.sql` 与仓储集成测试；在部署前不得把 SQLite 适配器当生产存储。
- 约束：新增字段/表时，必须同时改 `migrations/001_init.sql` 与 `memory/schema.py`，并在 `tests/test_memory_store.py` 覆盖。
