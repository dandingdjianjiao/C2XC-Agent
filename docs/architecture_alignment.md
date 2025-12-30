# C2XC-Agent 架构对齐与决策记录

> 本文档记录我们在对话中对**项目目标、架构选择、模块边界、数据/存储、UI/反馈流程、经验学习机制**等做出的关键决策与偏好。
>  
> 备注：当前仓库仅包含 `original_assets/` 下的研究资料（PDF/DOCX/XLSX），暂无实现代码，本文件用于后续开发对齐。
>
> 规范关系：`docs/PROJECT_SPEC.md` 为实施时的 **Single Source of Truth**；本文件作为“对话对齐记录/决策理由补充”。若两者冲突，以 `docs/PROJECT_SPEC.md` 为准。

---

## 0. 部署与工程约束（关键假设）

- 使用场景：**单人/小范围实验员**，单机部署。
- 部署形态：**单实例、无多 worker、无多副本/多机扩展**（因此很多并发/分布式约束可暂不考虑）。
- 服务数量偏好：**越少越好**，目标是“一个后端服务进程 + 本地文件/本地数据库文件”：
  - 知识库：LightRAG 默认本地方案（不额外起向量/图数据库服务）。
  - 经验库：Chroma 本地持久化（嵌入式使用，不额外起 Chroma server）。
  - 其它业务数据：SQLite 单文件。
- 系统内部语言：后端与 agent 默认英文；UI 静态文案支持中英切换（默认英语）。
- 模型调用：采用 **OpenAI 兼容 API**（chat + embeddings），便于替换任意模型/网关（如 Qwen 系列等）。
- 域范围：仅一个项目域（不做多项目/多 domain 切换），但数据结构可保留扩展位以便未来升级。

---

## 1. 项目目标与领域假设

### 1.1 总目标
- 构建一个“**自动生成配方建议的推理系统**”：LLM/agent 基于现有资料（文献+机制整理+历史实验数据）生成配方建议；研究人员进行湿实验验证并反馈；系统基于反馈学习并迭代改进。
- **最高级目标**：高选择性、高活性的乙烯（`C2H4`）合成。
- 说明：其它产物（如 CO/CH4/C2H6/H2 等）也有意义，因此系统应支持多产物分析与对比，但总体优化方向偏向 `C2H4`。

### 1.2 材料体系与可调参数（已确认）
- 体系为 **`M₁M₂–TiO₂ / Zr‑BTB`** 双层复合结构（上层双金属掺杂 TiO₂；下层 Zr‑BTB 2D 片层可做小分子微环境修饰）。
- `BTB linker 固定不可调`（`overview.md` 曾写“linker 可调”，已确认该处写错；后续以固定为准）。
- 每条推荐配方**必须包含**（硬 schema）：
  - `M1`：掺杂金属 1（元素/金属类型）
  - `M2`：掺杂金属 2（元素/金属类型）
  - `atomic_ratio`：`M1:M2`（原子比 / 化学式语义）
  - `small_molecule_modifier`：MOF 微环境修饰小分子（类型/名称，必须包含羧基 –COOH）
- 可调参数：
  - 掺杂金属种类：`M1, M2`
  - 掺杂原子比例：化学式语义（如 `Cu2Mo2`），TiO₂ 的 `O2` 固定不变
  - Zr‑BTB 上的小分子修饰：**必须含羧基**；“最好可直接购买”是偏好（初期不做供应链检索/自动验证工具）

### 1.3 性能指标口径（已确认）
- activity：使用实验数据表的单位（例如 `umol/g/h`）
- selectivity：产物比例意义上的“选择性”（不设硬阈值）
  - 实现口径：对实验员在反馈中**选择并填写**的产物测量值 `value_i` 计算归一化比例：
    - `fraction_i = value_i / sum(value_all_selected_products)`
  - `fraction` 字段**必须存在且需要持久化**（用于对比分析与 RB 提炼），避免每次临时重算导致口径漂移。

### 1.4 机制整理的使用方式（重要约束）
- 已有“7/10 类调控机制”整理（来自资料），但**不假设完备**，且实际反应可能存在**多因素耦合**。
- 因此：
  - 机制信息用于指导思考与覆盖面检查（checklist / brainstorming scaffold），**不做“强行映射回机制”的硬任务**。
  - 不需要单独的“Mechanism Mapper”模块；专家 agent 在推理时参考机制清单即可。

### 1.5 交付偏好（开发组织方式）
- 用户偏好：**不按 MVP/阶段交付**的叙事拆分；目标是最终完成全部要求。
- 允许实现上按模块推进，但总体上以“完整交付”为目标（而非先交付低配 MVP 再扩展）。

---

## 2. 总体架构：ReCAP + 多专家 + RAG + 可追溯

### 2.1 Agent/编排形态（最小可用且不臃肿）
- **ReCAP 作为执行范式**：递归分解任务、回注父计划、动态再规划，用于长链路推理/规划。
- 多 agent 最小集合（用户原始设想 + 讨论确认）：
  - `Orchestrator (中控)`：ReCAP 递归分解、委托专家、合并结论、生成最终建议
  - `MOF 专家`：微环境/小分子修饰方向推理
  - `TiO2 掺杂专家`：双金属掺杂方向推理
  - `LightRAG`：工具（知识库检索与引用），不是独立 agent
  - `ReasoningBank`：学习/记忆模块（下节），不是额外专家 agent

> 讨论中明确：不需要将“Citation Verifier”“Recipe Generator”等拆成独立 agent；这些应作为**中控流程阶段**或**程序校验**实现。

### 2.2 Working Memory（单次轨迹内共享 note）
- 在“单次运行/单条轨迹”内维护一个全局 `RunNote`（共享工作记忆），供中控与两个专家共享读写。
- 采用“增量操作/patch”的方式更新 note，避免整段重写导致信息漂移。
- `RunNote` 内建议至少包含：
  - 已检索证据登记（kb chunks / mem items 的 registry）
  - 候选配方列表（及来源与假设）
  - 未决问题、冲突点、下一步计划

### 2.3 Trace（必须程序记录，不由 LLM 记）
- Trace 由程序自动记录：每次 LLM 调用（完整 prompt/response）、检索 query、返回的 chunks/mem、最终输出、配置版本等。
- 目标：可追溯 agent 调用链路与行为逻辑；可复盘每条建议引用的知识来源。

---

## 3. 引用（Citations）策略：知识库与经验库统一可追溯

### 3.1 引用粒度
- **精确引用到 chunk** 即可（chunk 元数据需包含 DOI；如无 DOI，允许 fallback：本地 PDF 文件名/路径；不要求页码）。

### 3.2 引用对象类型
- 知识库引用：`kb:<chunk_id>`（来自 LightRAG）
- 经验库引用：`mem:<memory_id>`（来自 Chroma/ReasoningBank）

chunk_id 规则（已定，适配两个 KB）：
- `chunk_id` 直接使用 LightRAG 内部生成并存储的 `chunk_id`（内容 hash 语义），并加 KB 命名空间前缀：
  - `chunk_id = "<kb_namespace>__<lightrag_chunk_id>"`
- 目的：避免“原理/调控性”两套 LightRAG 实例之间的 chunk_id 冲突与引用歧义。

LLM 友好的短引用（已定）：
- 每次检索结果由程序分配 `[C1] [C2] ...` 的短别名；LLM 输出只引用别名。
- 程序在落盘/trace 时将别名解析回 canonical 的 `kb:*`。

### 3.3 程序校验（非 agent）
- 最终输出中出现的 `kb:*` / `mem:*` 必须能在本次运行的检索结果或数据库中解析到实体（允许引用 archived，但 UI 需提示状态）。
- 关键建议必须带引用（至少 1 条 citation，类型不限）。

---

## 4. 知识库：LightRAG（本地默认方案）

### 4.1 选型结论
- 采用 **LightRAG** 作为成熟的知识库/RAG 方案。
- 单人单机/单实例：优先使用 LightRAG 的**默认本地存储方案**，不引入额外服务进程。
  - 备注：后续如需更强的图/向量后端（Neo4j/Qdrant/PGVector 等）再评估迁移；当前以“少服务、易部署”为先。
 - 备注：文献资产存在两个重点不同的文件夹，因此对应 **两个 LightRAG 数据库实例**，作为两个语义不同的检索工具供 agent 使用（并在 trace/引用中标记来源 KB）。

### 4.2 处理要求
- 可做文本处理与 chunk 化（允许 OCR/抽取增强）。
- 输出必须引用到具体 chunk（含 DOI 或 fallback 标识）。
  - chunk 颗粒度默认：`chunk_size = 512`（保持可配置，默认 512）。

### 4.3 入库与更新（只读）
- 知识库由使用者在系统外部提前处理好，本项目不提供 Web UI 上传 PDF/入库能力；LightRAG 在应用内以“只读检索”方式使用。

---

## 5. 经验库（Memory）：仅用 ReasoningBank（RB），不引入 ACE

### 5.1 选型结论
- **不实现 ACE 模块**。
  - 理由：ACE 在本项目中容易退化为“另一套检索-注入”机制，与 RB 形式重叠；稳定规约已稳定，无需学习型 playbook。
- **ReasoningBank 严格按论文实现**，但做本领域适配（尤其是实验反馈信号与对比分析）。
  - RB 核心流程：`retrieval → extraction → consolidation`（按论文），其中 extraction 的输入重点来自“实验反馈 + 对比分析报告 + 实验员 pros/cons”。

### 5.2 经验库存储：Chroma 单 collection
- 经验库用 **Chroma**（本地持久化，单 collection，metadata 过滤）。
- 不做 “SQLite 存正文 + Chroma 存索引” 的双写同步；**Chroma 是经验条目的唯一真值源**。
- collection 设计：
  - `id`: UUID（Chroma doc id）
  - `document`: memory item 主文本（通常是 content）
  - `metadata`：
    - `status`: `active|archived`（软删除）
    - `role`: `global|mof_expert|tio2_expert|orchestrator`（隔离检索）
    - `type`: `reasoningbank_item|manual_note`（RB 自动生成 + 人工编辑补充都允许；后续可扩展）
    - `schema_version`
    - `extra_json`: JSON string（扩展字段全部放这里，避免写死结构）

### 5.3 RB 检索与隔离策略
- RB 检索作为“流程阶段/工具”供 agent 自主使用（非默认注入）。
- 角色隔离检索：两路合并
  - `role=global`：`k_global=2`
  - `role=current_role`：`k_role=3`
- agent 若使用 RB 条目，需在输出中引用对应 `mem:<id>`。

### 5.4 可扩展字段与上下文构建（不写死）
为了满足“经验库条目结构未来可扩展，但不希望每加一个字段都要改 agent 拼上下文的代码”的偏好：

1) **存储层**：Chroma 的 `document` 存主文本（通常为 content），其余字段进入 `extra_json`（或逐步升级为显式 metadata）。  
2) **上下文层**：使用“可配置的 context template / field projection”
   - 按 `role` 配置“投影模板”（模板语言可选：Jinja/Handlebars/YAML 等），决定哪些字段被拼进 prompt
   - 新增字段时：优先只改 UI 表单 + 模板配置，而不是改 agent 主流程逻辑

> 这条原则应推广到整个项目：尽量用“配置驱动的投影与渲染”，而不是写死字段结构。

### 5.5 人工编辑与兜底
- 经验条目允许在 Web UI 做 `CRUD`，作为纠偏与维护入口。
- 删除为软删除（`archived`）。
- UI 编辑历史要记录（见 SQLite `mem_edit_log`）。

---

## 6. 其他数据存储：SQLite（本地单文件）

### 6.1 SQLite 存什么
- Trace：每次运行的计划树、步骤、工具调用、返回结果、引用列表（`chunk_id`/`mem_id`）、配置版本等。
- 实验反馈（feedback）：产物数据、评分、优缺点分析等。
- 对比分析报告（comparison_report）。
- 经验库编辑历史（mem_edit_log）：对某个 `mem_id` 的变更前/后快照、操作者、时间、原因等（不存为主数据，只做审计/追溯）。

### 6.2 可扩展性原则（全项目通用）
- 数据结构避免“写死列”：
  - 最小内核字段固定（id、关键文本/数值）
  - 其余走 JSON 扩展字段（或多行表）
- top‑k、模板、过滤规则、字段渲染规则等都应做成“配置”，存 SQLite 并允许 UI 修改。

---

## 7. Web UI：英文运行 + UI 文案中英切换

### 7.1 语言策略（已确认）
- 系统内部（后端、agent、数据内容）默认英文运行。
- 仅前端组件的静态 UI 文案支持中英切换，默认 **英语**。
- 动态内容（agent 输出、数据记录等）原样展示（通常为英文）。

### 7.2 UI 必需能力（已确认）
- 展示配方建议与引用（kb chunks 与 mem items 可点击）。
- 展示经验库（Chroma）：
  - 列表/筛选（role/status/type）
  - 详情页（查看引用关系、来源 run）
  - 编辑/软删除，并写入 edit log
- 展示 trace/调用链路（用于追溯与复盘）。
- 反馈录入（下节）。
- Settings 页面（系统配置）：
  - Products 管理（产物目录）：仅用于 feedback 产物选择与同类分组
  - Product Presets 管理：仅用于 feedback 表单快捷选择
  - RB 参数与模板（k 值、字段投影模板等）
  - Comparison 默认策略（method3 默认开关等）
  - UI 语言切换（仅静态文案）

---

## 8. 反馈与历史对比分析（Comparison Set）

### 8.1 反馈字段（已确认）
- 运行层（run）：
  - 支持一次提交 `n` 个 run（`1..5`）：系统将同一份请求输入重复执行 `n` 次并排队（单机默认串行即可）。
  - 用户为每个 run 设置 `recipes_per_run`，范围 `1..3`（最大值为 3）；agent 单次运行内必须输出对应数目的配方。
  - 每个 run 的请求输入、`n`、`recipes_per_run`、模型/配置快照必须进入 trace（便于复盘）。
  - 多样化策略：批量 run 的差异主要通过采样参数（例如 temperature）实现；不做“强制多样化”的提示词约束，也不做程序级去重/重试；重复配方允许存在。
  - 队列控制：支持 Cancel queued + Cancel running（Cancel running 允许 best‑effort：在当前 LLM/工具调用结束后尽快停止后续步骤）。
- `score`: **float**（0–10 仅作为 UI 提示，不强校验）
- 文本：`pros` / `cons` / `other`
- 产物测量值：动态多行（见 8.2）
  - 每行：`product_id`（下拉选择）+ `value`（浮点数）
  - 系统计算并持久化：`fraction`（选择性口径，见 1.3）
  - 单位：沿用 Excel 的单位体系；单位不绑定到产物定义上（可作为 feedback 级字段或系统配置）

反馈约束（重要）：
- 每个 run **最多只有 1 条 feedback**（但允许更新/编辑）。
- feedback 更新后，需要支持“回滚/删除该 feedback 上一次生成的 RB 经验并重新学习”，且允许沿用或修改对比策略后再提炼。
  - 一次 RB 提炼可能产生 `add / remove(archive) / update` 三类 memory 变更；必须记录变更 delta 以便完整回退后再重新学习。
  - 回滚语义：严格回滚（即便 UI 中对相关 mem 条目做过人工编辑，也会被回退覆盖），然后再用新 feedback 重新提炼。

RB 提炼策略（按论文但适配领域）：
- 用 `pros` 走“成功经验提炼模板”
- 用 `cons` 走“失败经验提炼模板”
- 可将对比分析报告摘要作为提炼上下文的一部分

### 8.2 产物目录（Product Catalog）与输入方式
目标：避免误写/格式问题，且支撑“同类=产物列表完全匹配”分组。

- 产物不能手动输入字符串；反馈页每一行产物通过下拉从“产物目录”选择。
- 产物目录可在独立页面维护（Manage Products）：
  - `product_id`: UUID
  - `name`: 英文显示名
  - `status`: active/archived（软删除，历史可追溯）
- unit 不绑定在产物上（unit 属于 measurement/feedback 语义）。

### 8.3 产物集合 preset（用户可保存）
- feedback 页面提供 preset 下拉。
- 用户可将“当前选择的产物集合（忽略数值）”保存为 preset，并命名：
  - 默认名：按当前选择的产物名拼接生成（过长可截断，UI 可编辑）
- preset 内容为一组 `product_id` 列表（可存显示顺序，仅 UI 用）。
- 新增产物采用简化流程：必须先去 Manage Products 新增，再回到反馈页选择（选项 A）。

### 8.4 同类分组：产物列表完全匹配
- “同类”按产物集合严格匹配（不是交集不为空）。
- 使用 `product_signature_key` 表示产物集合：
  - `product_signature_key = sorted(product_uuid_list).join('|')`
  - 顺序无关；不做 hash（已选 A，便于调试与可读）。

### 8.5 历史对比分析：三种来源 + 边缘规则（已确认）
对比分析支持三种来源，可组合使用：

1) 方法 1：用户指定一个或多个历史推荐（runs/feedback）
2) 方法 2：用户手动输入基准（可选文本或结构化数值；作为可选补充）
3) 方法 3：系统自动选择同类历史数据（必须有已反馈历史数据才触发）

边缘规则（关键）：
- 若启用方法 3：
  - `auto_pool = 同 product_signature_key 的所有历史反馈`
  - `avg`：从 `auto_pool` 计算（与方法 1 用户选择无关）
  - `best`：`auto_pool` 中 **score 最大**那条（其详细数据作为对比对象）
  - 对比对象 = `{current} + {best} + {selected_pool(method1)} + {manual_baselines(method2 可选)}`
- 若不启用方法 3：
  - 若用户选了方法 1：`avg` 由用户选择的条目计算；并对这些条目逐条对比
  - 若无历史数据/用户未选：提示用户优先采用方法 2（手动基准）
- 触发提示（约束）：
  - 若同类历史数据不足（例如 `auto_pool < 2`），则 method3 无法计算均值，应提示用户优先采用方法 2 或补充方法 1 指定对照。

对比报告落 SQLite（comparison_report），并作为 RB 提炼上下文的一部分（帮助提炼“相对历史 avg/best 的优缺点”）。

---

## 9. LLM/Embedding/API 偏好

- 采用 **OpenAI 兼容接口**（chat + embeddings），用户可通过兼容方式替换任意模型（如 Qwen 系列等）。
- 嵌入模型/维度等信息应记录在配置中，便于更换与重建索引。
- **不引入 LangGraph / Google ADK**（避免“写一半换框架/混用”导致结构漂移）。采用自研薄 ReCAP orchestrator（状态机/递归回注），所有能力模块化、可替换。

---

## 10. 当前未决项（开发时再细化）
- 系统中“哪些参数/字段可配置、是否提供 UI 编辑入口”只对已明确的模块做（例如：产物目录/产物 preset、RB top‑k、字段投影模板、对比策略参数等）；不预设“金属/比例候选范围”等未提出的约束。
- 经验条目字段（extra_json）中有哪些字段参与检索/渲染：由配置决定，后续按使用情况迭代。
- 经验条目的更高级合并/去重策略（保持“冲突都保留”，仅近重复去重）。
