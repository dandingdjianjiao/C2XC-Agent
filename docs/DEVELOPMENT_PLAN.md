# C2XC-Agent 宏观开发计划（WebUI → Feedback → ReasoningBank → K8s）

最后更新：2025-12-27

> 目的：把当前的宏观方向落成可执行的工程计划，指导后续开发“做全做稳”，而不是追求低配 MVP。  
> 规范关系：`docs/PROJECT_SPEC.md` 是领域与约束的 Single Source of Truth；本计划不应与其冲突。  
> 接口契约：配套见 `docs/API_CONTRACT.md`（WebUI ↔ Backend 的可演进契约草案）。

---

## 0) 总体原则（Non‑negotiables）

1) **每个 milestone 都必须“做完当前 part 的完整闭环”**  
   - 包含：数据模型 + API 契约 + UI 交互 + 错误处理 + 可观测性（trace）+ 最小测试/文档。  
   - 不接受“只跑通 happy path、后面再补”的计划。

2) **可扩展性与鲁棒性优先（尤其在接口尚未完全确定时）**  
   - 所有核心资源必须有 `schema_version` 与 `extra` 扩展槽。  
   - API v1 只能新增字段，不能破坏旧字段语义；破坏性改动走 `/api/v2`。  
   - 事件/trace 必须分页、可筛选、可按需加载 payload（防止未来 trace 变大导致 UI 不可用）。

3) **证据链与可追溯是产品核心，而非“调试附属品”**  
   - KB chunk alias（如 `[C12]`）必须可点开查看原文与来源。  
   - 后端必须能回放 run 的中间步骤：计划、工具调用、模型响应、最终输出与引用解析。

4) **单机单人部署假设成立，但工程质量不降级**  
   - 单实例/单写者：可以简化并发，但状态机、取消语义、迁移、幂等等仍需严格定义。  

5) **WebUI 视觉必须“科研风格 + 2025 现代感”**  
   - 像实验平台/论文阅读器一样：信息密度高但可读；层级清晰；细节克制；默认英文 UI（静态文案可中英切换）。  
   - UI 风格从 Day1 用设计系统与 token 管住，不允许临时拼凑。

---

## 1) Milestone 0：后端基座产品化（API + 执行队列 + Trace 查询）

### 目标

- 把当前“脚本/CLI 驱动”升级为“服务/API 驱动”，确保 WebUI 可以无缝驱动 run/batch、读取 trace、取消任务。
- 为后续 Feedback/RB 的增表与演进预先建立迁移与版本化机制。

### 交付物（必须）

- Backend service（推荐 FastAPI/Starlette）
  - `/api/v1/healthz`、`/api/v1/version`（或等价）
  - OpenAPI 文档可访问（用于前后端对齐与调试）
- 执行模型（单实例后台队列）
  - `POST /batches` 创建 batch 并排队 n 个 run
  - 取消语义：`POST /runs/{id}/cancel` / `POST /batches/{id}/cancel`
  - 幂等支持（至少对 batch 创建支持 Idempotency-Key）
- Trace/events 查询 API（UI 调试核心）
  - events 列表分页、过滤（event_type / time range）
  - 支持 `include_payload=false`（列表轻量）与事件详情接口（按需加载大 payload）
- 数据库迁移机制（最少也要做）
  - `schema_version` + 启动时 migration（或独立 migrate 命令）
  - 明确“可回滚/不可回滚”的迁移策略

### 完成定义（DoD）

- UI/脚本之外的“用户入口”只依赖 API：不再要求用户直接跑 `scripts/run_batch.py` 才能创建 run。
- 任何 run 的 trace 都能被分页拉取，不会因为 `llm_request` payload 过大而卡死。
- 取消是可预测的：取消请求必定落库、可查询、可在 UI 看见，并最终体现在 run 状态与事件中。

### 风险与对策

- 风险：events payload 会爆炸（messages、chunk 内容、raw response）。  
  对策：分页 + include_payload + 事件详情拆分；必要时引入“run_evidence 表/附件存储”作为优化。

---

## 2) Milestone 1：WebUI（科研风格 + 2025 现代美观；用于推荐检查与调试）

### 目标

- 把“推荐系统”变成一个可工作的科研工作台：能创建 run、查看结果、查看证据链、回放 trace、定位失败原因。

### UI 技术与设计约束（建议固定，减少返工）

- 前端栈建议（可调整，但一旦定了就不要中途换范式）：
  - React + TypeScript（Next.js 或 Vite 二选一）
  - Tailwind + Radix/shadcn 风格组件（便于做出 2025 质感）
  - TanStack Query（数据请求/缓存）+ TanStack Virtual（虚拟列表）
  - 轻量图表（ECharts/Recharts）用于反馈与对比的小可视化（后续用）
- 设计系统（必须从 Day1 建）
  - Design tokens：颜色、字体、字号、间距、阴影、圆角、状态色（success/warn/error/neutral）
  - 主题：Light 默认 + Dark 可选（科研阅读场景强需求）
  - i18n：仅静态文案（与 spec 一致），从 Day1 预埋

### 功能范围（必须做全）

1) Runs 列表页
   - batch/run 状态、创建时间、参数快照（temperature、recipes_per_run、模型名、KB 路径等）
   - 状态轮询/刷新策略（避免疯狂请求）

2) Run 详情页（核心）
   - Final output：配方结构化渲染（不是只展示 JSON），支持复制/下载
   - Evidence：alias 列表 + source + chunk 内容查看器（支持搜索/高亮引用）
   - Trace：事件时间线/树形视图，支持筛选、分页、按需加载 payload
   - 错误定位：run_failed/格式错误/引用缺失时给出“下一步如何修复”的提示

3) 取消与重试的交互
   - 可取消 queued/running（best-effort）
   - 可重新运行同一 request（建议支持“用同参数再跑一次”，便于调试）

### 完成定义（DoD）

- 用 UI 能完成：创建 run → 查看 recipes → 点开引用 chunk → 查看关键 trace → 定位失败原因 → 取消/重跑。
- UI 具备“科研风格的专业感”：排版、信息层级、交互细节（loading/empty/error states）都完整，不是 demo 拼图。

---

## 3) Milestone 2：Feedback（WebUI 内建；确定 RB 的稳定输入契约）

### 目标

- 把实验员反馈落库并稳定化：它既是 UI 功能，也是 RB 的上游输入契约。

### 交付物（必须）

- 数据模型（SQLite 增表）
  - `products`：产物目录（UUID；UI 下拉；禁止自由输入）
  - `product_presets`：常用产物集合（UI 下拉 preset）
  - `feedback`：每个 run 最多 1 条（强约束）
  - `feedback_products`：反馈的产物测量行
  - 所有表都预留 `schema_version` / `extra` 扩展槽（或等价实现）
- 业务规则（后端强校验）
  - `fraction` 必须计算并持久化：`value_i / sum(value_selected_products)`
  - run_id → feedback 1:1（最多 1 条）
- UI（Run 详情页扩展）
  - 可创建/编辑 feedback
  - 产品行增删、即时校验、自动计算 fraction
  - 产物目录与 preset 的 Settings 管理页

### 完成定义（DoD）

- feedback 的口径不会漂移：保存后再次打开与导出一致（fraction 已持久化）。
- 数据结构“可作为 RB 输入”且稳定：有 schema_version、有扩展槽、有明确更新语义（PUT upsert）。

---

## 4) Milestone 3：ReasoningBank（Chroma + 可引用 + 严格回滚重学）

### 目标

- 实现 spec 要求的 RB：`retrieval → extraction → consolidation`，并把“回滚重学”作为硬语义。

### 分解与交付物（每个子阶段也要闭环）

1) RB‑Browse（可浏览/可引用）
   - Chroma persistent collection
   - UI：mem 列表/详情/搜索；支持软删除（archive）
   - 引用：`mem:<id>` 可在 UI 与 trace 中点开

2) RB‑Learn（从 feedback 提炼）
   - 从 `feedback +（可选）comparison_report + run trace` 提炼出 memory items
   - 所有 mem 条目记录来源：`source_run_id` 等溯源信息

3) RB‑Consolidate（合并/去重/冲突策略）
   - 默认保留冲突；仅 near-duplicate 合并
   - consolidation 逻辑版本化（strategy_version）

4) RB‑Rollback（严格回滚重学）
   - 记录 delta：一次学习产生 add/update/archive 的变更集
   - feedback 更新触发：先严格回滚到提炼前状态，再按新反馈重学

### 完成定义（DoD）

- 端到端闭环成立：Run → Feedback → RB 学习 → 下一次 Run 能检索到 mem 并引用（trace 可回放）。
- 回滚语义可验证：更新 feedback 后，RB 能回退并重学，且 delta 与审计记录完整。

---

## 5) Milestone 4：Container Ready（为 K8s 做准备；K8s 细节后续对接）

### 目标

- 把系统做成“可容器化、可运维”的形态，确保未来对接 K8s 时只需要补部署编排细节。

### 交付物（必须）

- Backend/Frontend Dockerfile（多阶段构建、最小镜像、非 root 用户）
- 运行时参数 12-factor 化
  - OPENAI 兼容配置、KB 路径、SQLite 路径、Chroma 持久化路径等全部可通过 env/config 注入
- 数据持久化与目录约定文档
  - SQLite / LightRAG working_dir（只读 or 预构建）/ Chroma 的挂载点清晰
- 启动自检与失败提示
  - KB 目录不存在、缺少 API key、schema 不匹配等情况给出明确错误，不允许“静默坏掉”

### 完成定义（DoD）

- 在单机 docker 环境即可跑起完整闭环（UI+API+持久化），并能在重启后保持数据一致。

---

## 6) Milestone 5：K8s（需求后续对接）

> 具体拓扑、鉴权、Ingress、PVC、资源配额等后续对接后再细化。  
> 本计划保证前序里程碑已经把“健康检查、配置注入、持久化路径、单实例语义”准备好。

---

## 7) 执行建议：如何防止“做着做着又变成 MVP”

- 每个 milestone 开始前先冻结该阶段的：  
  1) API contract（`docs/API_CONTRACT.md` 对应段落）  
  2) DB schema_version 与迁移策略  
  3) UI 信息架构与设计 token  
- 每个 milestone 结束必须输出：  
  - “验收用操作路径”（点击/调用步骤）  
  - “错误场景演示”（至少 2 个：例如 KB 未配置、取消 run、无引用输出校验失败）  
  - “后续扩展点清单”（通过 schema_version/extra 体现）  

