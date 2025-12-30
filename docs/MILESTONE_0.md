# Milestone 0：后端基座产品化（实施跟踪）

最后更新：2025-12-27

> 本文档用于 **实时跟踪** Milestone 0 的实施进度与关键决策。  
> 要求：后续所有 Milestone 0 的开发变更都需要同步更新本文件（包含：完成项勾选、接口变更、迁移版本、运行方式、已知问题）。
>
> 关联文档：
> - 总计划：`docs/DEVELOPMENT_PLAN.md`
> - API 契约草案：`docs/API_CONTRACT.md`
> - Spec（Single Source of Truth）：`docs/PROJECT_SPEC.md`

---

## 0) 目标与完成定义（DoD）

### 目标

- 将当前“脚本/CLI 驱动”能力升级为 **服务/API 驱动**，为 WebUI→Feedback→RB 铺路。
- 提供稳定的 `/api/v1` 接口：
  - 创建 batch/run（含 dry-run）
  - 后台串行执行 queued runs
  - 取消 batch/run（best-effort）
  - trace/events 分页查询（默认不拉 payload，按需加载）
- 建立 SQLite **迁移机制** 与 **幂等（Idempotency-Key）**，保证后续增表/演进不返工。

### 完成定义（必须全部满足）

- [x] 仅通过 API（不跑 `scripts/run_batch.py`）即可：创建 batch → 执行 run → 查询 output → 分页查看 events → 取消 queued/running。
- [x] events API 支持分页/过滤/按需 payload，不会因大 payload 卡死。
- [x] DB 有 schema_version 迁移与启动 reconcile（running 状态可收敛）。
- [x] `POST /batches` 支持 Idempotency-Key：重复请求不会重复创建 batch。
- [x] 错误语义统一（error envelope），缺依赖/缺 env 返回明确 `code` 与 `message`。
- [x] 至少有一组关键单元测试（cursor、reconcile、迁移表存在）。
- [x] `GET /runs/{run_id}/events` 在 run 不存在时返回 404（避免 UI 误判为空）。
- [x] idempotency 有自动化测试覆盖（同 key 同 body / 同 key 不同 body）。
- [x] normal-run 依赖预检更彻底：缺少 python 包或 KB 目录不存在时直接 503。
- [x] 提供 worker/queue 观测端点（queued/running 统计 + worker 是否运行）。
- [x] debug 端点默认关闭，并可通过 env 显式打开。

---

## 1) 范围（In Scope / Out of Scope）

### In Scope（Milestone 0 做）

- Backend 服务（FastAPI/等价） + OpenAPI
- 执行队列（单实例单 worker）
- Batch/Run/Cancel APIs
- Trace/Events APIs（分页、过滤、payload 延迟加载）
- SQLite migrations
- Idempotency（仅 `POST /batches`）
- 启动 reconcile（running → failed，写事件）
- 最小测试与运行文档（本文件末尾）

### Out of Scope（后续里程碑做）

- WebUI（Milestone 1）
- Feedback / Products / Presets（Milestone 2）
- ReasoningBank / Chroma（Milestone 3）
- K8s YAML 与部署细节（Milestone 5，需求后续对接）

---

## 2) 关键工程决策（Decision Log）

- 运行模型：单实例后台 worker 串行执行 queued runs（避免多写者 SQLite）。
- 状态收敛（reconcile）：服务启动时将 `runs.status=running` 标记为 `failed(server_restarted)` 并写事件，避免“永远 running”。
- trace/events：默认列表不返回 payload（`include_payload=false`），点击单条事件再加载详情。
- 幂等：对 `POST /batches` 引入 `Idempotency-Key` 表缓存响应；同 key + 不同请求体 → 409 conflict。

> 若后续推翻任何决策，必须在此处记录“为什么变更 + 对接口/数据的影响 + 迁移方案”。

---

## 3) 交付清单（实时更新）

### 3.1 API（/api/v1）

健康检查：
- [x] `GET /api/v1/healthz`
- [x] `GET /api/v1/version`

Batch/Run：
- [x] `POST /api/v1/batches`（支持 dry_run；支持 `Idempotency-Key`；normal-run 缺依赖返回 503）
- [x] `GET /api/v1/batches`
- [x] `GET /api/v1/batches/{batch_id}`
- [x] `GET /api/v1/runs?batch_id=...`
- [x] `GET /api/v1/runs/{run_id}`
- [x] `GET /api/v1/runs/{run_id}/output`

取消：
- [x] `POST /api/v1/batches/{batch_id}/cancel`
- [x] `POST /api/v1/runs/{run_id}/cancel`

Trace/Events：
- [x] `GET /api/v1/runs/{run_id}/events`（cursor 分页 + 过滤 + include_payload）
- [x] `GET /api/v1/runs/{run_id}/events/{event_id}`（单条详情）

Evidence（为 WebUI 性能做的聚合接口；来源仍为 trace 事件）：
- [x] `GET /api/v1/runs/{run_id}/evidence`（cursor 分页 + include_content）
- [x] `GET /api/v1/runs/{run_id}/evidence/{alias}`（按 alias 取证据详情）

系统观测：
- [x] `GET /api/v1/system/worker`（worker 状态 + queue 统计）

### 3.2 SQLite 迁移

Schema versions：
- [x] v1（现有）：batches / runs / events / cancel_requests / meta
- [x] v2：idempotency_keys 表 + events 索引增强 + batches/runs status 索引

### 3.3 Worker / 执行队列

- [x] claim next queued run（原子 claim，避免未来多 worker 竞态）
- [x] 执行 dry-run（生成 placeholder output）
- [x] 执行 normal-run（需要 KB + LLM；API 创建阶段缺依赖返回 503；运行期错误写入 trace）
- [x] 取消 best-effort（batch/run cancel_requests）

### 3.4 测试

- [x] cursor 编解码（`tests/test_cursor.py`）
- [x] reconcile：启动收敛 running（`tests/test_sqlite_store_reconcile.py`）
- [x] migration：idempotency 表存在（`tests/test_sqlite_store_reconcile.py`）
- [x] idempotency：同 key 同 body 返回同 batch_id；同 key 不同 body 返回 409（`tests/test_idempotency.py`）

---

## 4) 如何运行（Milestone 0 目标态）

> 本节会随着实现推进更新为最终可用命令。

### 4.1 本地启动（API）

- 安装依赖：
  - `pip install -r requirements-dev.txt`

- 推荐：`python scripts/serve.py`
- 或：`uvicorn src.api.app:app --reload --port 8000`

可选环境变量：

- `C2XC_HOST` / `C2XC_PORT` / `C2XC_RELOAD`：控制 API 启动参数（见 `scripts/serve.py`）
- `C2XC_ENABLE_WORKER=0|1`：是否启动后台 worker（默认 1）
- `C2XC_RECONCILE_ON_STARTUP=0|1`：是否启动时 reconcile stuck running（默认 1）
- `C2XC_ENABLE_DEBUG_ENDPOINTS=0|1`：是否启用 `/api/v1/_debug/*`（默认 0）

### 4.2 快速验证（dry-run）

- `POST /api/v1/batches` with `dry_run=true`
- 轮询 `GET /api/v1/runs?batch_id=...` 与 `GET /api/v1/runs/{run_id}/events`

示例（curl）：

- 创建 dry-run batch：
  - `curl -X POST http://127.0.0.1:8000/api/v1/batches -H 'Content-Type: application/json' -d '{"user_request":"test","n_runs":1,"recipes_per_run":1,"dry_run":true}'`
- 列出 runs：
  - `curl 'http://127.0.0.1:8000/api/v1/runs?batch_id=batch_...&limit=50'`
- 查看 run events（默认不含 payload）：
  - `curl 'http://127.0.0.1:8000/api/v1/runs/run_.../events?limit=50'`
- 查看 run output：
  - `curl 'http://127.0.0.1:8000/api/v1/runs/run_.../output'`

### 4.3 验证 normal-run（需要 KB + LLM）

normal-run 依赖：

- Python 包：`openai`、`lightrag`
- 环境变量：
  - `OPENAI_API_KEY`
  - `LIGHTRAG_KB_PRINCIPLES_DIR`
  - `LIGHTRAG_KB_MODULATION_DIR`

如果缺依赖或路径不存在，`POST /api/v1/batches` 会返回 `503 dependency_unavailable`，并在 `details.missing` 中列出缺失项。

---

## 5) 已知问题（实时更新）

- `GET /api/v1/runs/{run_id}/events` 的排序为时间正序（oldest-first），便于时间线；WebUI 若希望 newest-first 需在前端反转或后续增加参数。
