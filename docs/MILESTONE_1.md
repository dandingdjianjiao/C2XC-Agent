# Milestone 1：WebUI（科研风格 + 2025 现代美观；用于推荐检查与调试）

最后更新：2025-12-27

> 本文档用于实时跟踪 Milestone 1 的实施进度与关键决策。  
> 关联文档：
> - 总计划：`docs/DEVELOPMENT_PLAN.md`
> - API 契约草案：`docs/API_CONTRACT.md`
> - Spec（Single Source of Truth）：`docs/PROJECT_SPEC.md`

---

## 0) 关键决策（冻结）

- 前端框架：Vite + React + TypeScript（目录：`frontend/`）
- UI 设计骨架：Tailwind（token + light/dark 预埋）
- i18n：仅静态文案中英切换（默认英文；预埋）
- Evidence 展示：采用显式聚合 API（`/runs/{run_id}/evidence`），避免 UI 从 events 里聚合大 payload

---

## 1) 范围（In Scope / Out of Scope）

### In Scope（Milestone 1 做）

- Runs 列表页：查看 batch/run 状态，创建 batch（支持 dry-run）
- Run 详情页：Output（结构化渲染）、Evidence（alias → chunk viewer）、Trace（events 时间线 + 详情）
- 取消：Cancel run（best-effort）
- 设计系统骨架：theme tokens + light/dark；静态文案 i18n 骨架

### Out of Scope（后续里程碑做）

- Feedback / Products / Presets（Milestone 2）
- ReasoningBank / Chroma（Milestone 3）
- 鉴权/多用户/多实例（后续）

---

## 2) 交付清单（实时更新）

### 2.1 Frontend 工程基座

- [x] `frontend/`（Vite + React + TS）
- [x] Tailwind 接入 + design tokens（CSS vars）
- [x] Theme（light/dark）预埋 + localStorage 持久化
- [x] i18n（静态文案 en/zh）预埋 + localStorage 持久化

### 2.2 UI 页面（最小闭环）

- [x] Runs 页面：创建 batch（支持 dry_run）、列出 batches、展开查看 runs、跳转 run 详情
- [x] Run 详情：状态/时间/error 展示
- [x] Output：结构化渲染 recipes + JSON 复制
- [x] Evidence：alias 列表 + 详情内容查看器
- [x] Trace：events 列表 + 详情查看（payload）
- [x] LLM/agent 调用前确认弹窗（所有 normal-run 触发点必须确认）
- [x] Cancel batch（best-effort）
- [x] Retry / Re-run（“同参数再跑一次”交互）

### 2.3 后端配套（为 UI 提供性能友好接口）

- [x] Evidence 聚合 API：
  - [x] `GET /api/v1/runs/{run_id}/evidence?limit=&cursor=&include_content=false`
  - [x] `GET /api/v1/runs/{run_id}/evidence/{alias}`

---

## 3) 如何运行（Milestone 1 当前可用）

### 3.1 Backend

- `pip install -r requirements-dev.txt`
- `python scripts/serve.py`

### 3.2 Frontend

- `cd frontend`
- `npm install`
- `npm run dev`

默认：
- WebUI：`http://127.0.0.1:5173`
- Backend：`http://127.0.0.1:8000`

---

## 4) 已知问题 / 下一步

- 当前 UI 主要用于 Milestone 1 调试链路；后续会补齐更精细的筛选、虚拟列表、搜索高亮等“科研阅读体验”细节。
