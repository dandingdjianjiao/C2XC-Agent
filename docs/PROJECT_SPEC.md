# C2XC-Agent — 项目目标与架构决策（Living Spec）

最后更新：2025-12-24

> 本文件用于记录我们已对齐的**宏观目标、约束、选型与交互细节**，作为后续实现的单一事实来源（Single Source of Truth）。  
> 代码与系统运行默认全英文；仅 Web UI 的“前端静态文案”支持中英切换（默认英文）。

## 1. 目标（What / Why）

### 1.1 终极目标
- 构建一个能**自动生成催化剂配方建议**的推理系统，用于**光催化 CO₂ 还原/偶联**体系。
- 输出“配方 + 依据/证据链（precise citations）”，实验人员据此开展湿实验并回传反馈。

### 1.2 评估指标（没有硬阈值）
- **Activity（催化活性）**：沿用实验 Excel 中现有单位与数值体系（不在系统里强行统一）。
- **Selectivity（催化选择性）**：由产物比例衡量。  
  - 反馈会记录多个产物的测量值 `value_i`。系统计算：
    - `fraction_i = value_i / sum(value_all_selected_products)`
  - `fraction` 字段**必须存在**（代表实验员关心的选择性，也是系统优化目标之一）。

### 1.3 产物目标偏好
- 所有通过推荐配方得到的光催化 CO₂ 还原/偶联产物都“或多或少有意义”。
- 最高优先级目标：**高选择性 + 高活性 C₂H₄（乙烯）合成**。

### 1.4 交付偏好（非阶段化）
- 不按 MVP / 阶段式叙事拆分；目标是把本 spec 约束的能力**完整交付**。
- 实现上允许按模块推进，但不以“先做低配 MVP、后续再迭代”的方式定义完成标准。

## 2. 领域对象与可调自由度（Recipe Degrees of Freedom）

### 2.1 材料体系（固定结构）
- 体系为 **双层复合结构**：`M₁M₂–TiO₂ / Zr‑BTB`（TiO₂ 双掺杂 + Zr‑BTB MOF）。
- 记法 `M₁M₂–TiO₂` 的写法与含义没问题：这里的下标/数字表达的是**化学式语义上的原子数/原子比**（例如 `Cu₂Mo₂` 这类写法属于常规语义，不是“可随意改的参数”）。

### 2.2 必须出现的配方字段（硬要求）
每条推荐配方必须包含：
- `M1`：掺杂金属 1（元素/金属类型）
- `M2`：掺杂金属 2（元素/金属类型）
- `atomic_ratio`：`M1:M2`（原子比 / 化学式语义）
- `small_molecule_modifier`：MOF 微环境修饰小分子（类型/名称）
  - **必须包含羧基 –COOH**
  - “最好可直接购买”是偏好，但是否能用 tool 自动验证暂不强依赖；后续可加可插拔工具。

### 2.3 固定项（不可调）
- MOF **linker 固定为 BTB**（Zr‑BTB / BTB），不可调。

### 2.4 可扩展约束（不要写死）
除了上述硬要求，其他配方/实验约束（例如“必须可商业购买”“溶剂限制”等）不确定且可能变化：
- 以 **可替换配置**实现（例如 JSON / DB 配置），并在前端提供编辑入口（Settings 页面）。
  - 说明：这里指“规则/校验/默认参数”等配置的可替换性，**不预设**“候选金属范围/候选配方搜索空间”等输入侧约束（除非后续明确提出）。

## 3. 系统能力边界（必须 / 不做）

### 3.1 必须（Non‑negotiables）
- **精确引用**：所有基于文献/经验的结论必须可追溯到 chunk 级证据。
- **可追溯执行链路**：需要保存中间数据，能回放“agent 调用链路、行为逻辑、检索证据、产生输出的依据”。
- **Web UI**：实验人员可使用并反馈；UI 需要展示经验库与 trace。
- **单机单人部署**：不考虑多 worker、多实例；服务越少越好。

### 3.2 不做（明确排除）
- **不做 Mechanism Mapper**：机制列表仅作为“影响因素清单/思考 checklist”，并不完备且多因素耦合，无法也不需要“映射回唯一机制”。
- **不做独立 Citation Assembler & Verifier Agent**：引用在 RAG 检索阶段就应绑定到 chunk；系统程序层做校验与持久化即可。
- **不引入 ACE 模块**：只按论文实现 RB（ReasoningBank），ACE 不纳入当前架构。

## 4. 总体架构（API + RAG + Multi‑agent + ReCAP）

### 4.1 编排范式：自研轻量 ReCAP 风格 Orchestrator
决策：**不使用** ADK / LangGraph 等重型编排框架，避免“写着写着中途换范式”或“局部用框架、局部不用”的混乱。
- 实现一个“薄层 orchestrator”（ReCAP-like）：
  - 递归分解（plan → execute → recap/merge → backtrack）
  - 每一步可调用工具（LightRAG、ReasoningBank、数据库、文件等）
  - 输出结构化结果 + 证据引用

> 原则：当前实现以**不引入任何重型编排框架**为固定前提，避免“写着写着中途换范式”或“局部用框架、局部不用”的混乱；若未来必须重审，应整体重审而不是局部替换。

### 4.2 Agent 角色（最小集合）
系统内部的“角色”是逻辑分工（不一定是独立进程）：
1) `orchestrator`：中控与递归分解/整合（主控）
2) `mof_expert`：MOF 微环境/修饰小分子/界面作用专家
3) `tio2_expert`：TiO₂ 双金属掺杂/能带/缺陷与耦合专家

LightRAG 与 ReasoningBank 都是**工具**，不是 agent。

### 4.3 共享工作记忆：RunNote（全局 Note）
为避免“每个子任务各自记忆碎片化”，在单次 run（一次推荐轨迹）内维护一个中心化的共享工作记忆：
- `RunNote` 由程序持久化，允许每次行动对其进行结构化编辑（append/replace/upsert）。
- `RunNote` 主要承载：
  - 已确定的配方约束与决策（例如 linker 固定、必须 COOH）
  - 当前候选配方列表与淘汰理由
  - 证据登记册（evidence registry：每条主张对应引用）
  - 风险与不确定性、待问实验员的问题

### 4.4 Trace（必须程序记录）
- Trace / 可回放执行链路**必须由程序自动记录**（不是让 LLM“自己记”）：
  - 每次 LLM 调用（完整输入 prompt、完整输出 response、模型/采样参数、工具调用等）
  - 每次检索（query、返回的 `kb:*` chunks / `mem:*` items、rerank 结果等）
  - 关键中间产物（候选配方、淘汰理由、对比分析报告、RB 提炼前后等）
  - 配置版本（top‑k、模板、schema_version 等）

## 5. 引用（Citation）与证据策略

### 5.1 引用粒度与格式
- **引用必须精确到 chunk**（chunk 具备 `doi` 元数据；如无 DOI，允许以本地 PDF 文件名（或路径）作为 fallback；不要求页码）。
- 两类引用 ID：
  - 文献知识库：`kb:<chunk_id>`
  - 经验库（ReasoningBank）：`mem:<id>`

chunk_id 规则（已定）：
- `chunk_id` **直接使用 LightRAG 内部生成并存储的 `chunk_id`**（内容 hash 语义），不在本项目中重新计算。
- 为避免两套 KB（原理 / 调控性）之间的引用冲突，外部可见的引用 ID 必须带 `kb_namespace` 前缀：
  - `chunk_id = "<kb_namespace>__<lightrag_chunk_id>"`
  - 引用格式：`kb:<chunk_id>`（例如 `kb:kb_modulation__chunk-<md5>`）

LLM 友好的“短引用”策略（已定）：
- 在每次检索结果中，程序为本次返回的 chunks 分配短别名：`[C1] [C2] ...`（仅对本次 action 有效）。
- LLM 在输出中只引用别名（如 `[C1]`），程序在落盘/trace 时将其解析回 canonical 的 `kb:*` 引用，并保存本次 alias→kb:* 的映射，保证可追溯与不歧义。

### 5.2 引用绑定时机
- 在 RAG 检索阶段为每个 chunk/条目绑定引用信息（chunk_id/doi/source）。
- 输出时只允许引用已绑定的 `kb:*` 或 `mem:*`，程序层校验“引用存在且可追溯”。

## 6. 存储与服务形态（越少越好）

### 6.1 服务数量原则
- 单机单人：尽量**一个后端服务进程**即可。
- 组件存储尽量用“嵌入式/本地持久化”的默认方案，避免额外向量库服务（qdrant 等）。

### 6.2 三类存储分工（已定）
1) **知识库（文献）**：使用 LightRAG 的默认本地方案（包含向量检索 + 图检索）。  
   - 注意：实际存在 **两个语义不同的文献集合**（来自不同文件夹、重点不同），因此对应 **两个 LightRAG 数据库实例**（两个“工具”），供 agent 视任务选择调用或同时调用。  
2) **经验库（ReasoningBank）**：使用 Chroma（persistent）单独一套。  
3) **其他业务数据**：使用 SQLite（runs、trace、feedback、products、presets、configs、审计日志等）。

> 选择理由：避免“Chroma 存索引 / SQLite 存正文”的双写同步复杂度。

### 6.3 知识库入库与更新（只读、由外部处理）
- 本项目**不提供 Web UI 上传 PDF/入库**能力；知识库由使用者在系统外部提前处理好，并以“静态/只读”的方式供 LightRAG 检索使用。
- PDF 文档处理工具：使用 **Marker**（marker-pdf）进行 PDF → Markdown/文本提取；再由脚本构建 LightRAG 数据库（离线执行）。
- chunk 颗粒度：默认 `chunk_size = 512`（实现上保持可配置，但默认值固定为 512）。
- 多知识库实例：建议以配置项提供两个 LightRAG 数据目录，例如：
  - `LIGHTRAG_KB_PRINCIPLES_DIR`（原理类文献）
  - `LIGHTRAG_KB_MODULATION_DIR`（调控性文献）
  并在引用与 trace 中保留“来自哪个 KB”的信息，避免 chunk_id 冲突与混淆。

## 7. 经验库（ReasoningBank）设计

### 7.1 总原则
- 完全遵循论文实现 RB 的核心流程：**retrieval → extraction → consolidation**，并结合本项目领域做提示词/结构化适配。
- 经验库既支持**自动提炼写入**，也必须支持**人工增删改查**（作为最终 fallback）。
- RB 检索以“流程阶段/工具调用”的形式使用（非全局默认注入），由 orchestrator 在需要时主动触发并把检索结果拼入该步上下文。
- consolidation/维护策略：默认**保留冲突条目**（不自动裁决对错、不自动删除“互相矛盾”的经验）；仅在“近重复（near-duplicate）”场景做去重/合并。

### 7.2 存储（Chroma）
- 单 collection（例如 `reasoningbank`），通过 metadata 做隔离与过滤：
  - `role`: `global | orchestrator | mof_expert | tio2_expert`
  - `status`: `active | archived`（软删除）
  - `type`: `reasoningbank_item | manual_note`（RB 自动生成 + 人工补充/纠偏，后续可扩展）
  - `created_at`, `updated_at`
  - `schema_version`
  - `extra_json`: 扩展字段（JSON string）
- 检索默认值（可配置）：
  - `k_role = 3`（同角色）
  - `k_global = 2`（全局）
  - 合并去重后进入上下文

### 7.3 可扩展字段与上下文构建（避免写死）
为了保证“条目结构可扩展、但不让上下文拼装代码到处改”，采用两层机制：
1) **存储层**：Chroma document 里放 `content`（主文本），其他新字段全部进入 `extra_json`（或者逐步升级为显式 metadata）。  
2) **上下文层**：使用“可配置的 context template / field projection”
   - 例如：为每个 `role` 配置一个模板（Jinja/Handlebars/YAML 皆可），决定哪些字段被投影进 prompt
   - 新增字段时：只需更新模板与 UI 表单，不需要改 agent 主逻辑

### 7.4 人工编辑与审计
- UI 允许对经验条目进行增/删/改（删为软删除：`status=archived`）。
- SQLite 记录 `mem_edit_log`：保存 before/after 快照、操作者、时间、原因（可选）。

### 7.5 引用（经验库也要可引用）
- 经验检索结果必须带 `mem:<id>`，并在 UI/trace 中可点开查看全文与来源。

## 8. 反馈（Feedback）+ 历史对比（Comparison）+ RB 提炼

### 8.0 Run / Queue（批量提交与排队执行）
- 允许用户一次性提交 `n` 个 run（`1..5`）：系统将**同一份请求输入**重复执行 `n` 次并排队（单机单人场景：默认串行执行即可）。
- 用户为每个 run 设置 `recipes_per_run`，范围 `1..3`（最大值为 3）；agent 单次运行内必须输出**对应数目**的配方，并在输出结构里标明排序与取舍理由。
- 每个 run 的请求输入、`n`、`recipes_per_run`、模型/配置快照都必须进入 trace，确保可复盘。
- 多样化策略：批量 run 的差异主要通过采样参数（例如 temperature）实现；**不做**“强制多样化”的提示词约束，也**不做**程序级去重/重试。若出现重复配方，视为模型对该配方更有信心的信号之一。
- 队列控制（必须）：
  - Cancel queued：取消尚未开始的 run
  - Cancel running：取消正在运行的 run（允许 best‑effort：在当前 LLM/工具调用结束后尽快停止后续步骤，并将状态标记为 canceled）

### 8.1 反馈输入（实验员填写）
- `score`：浮点数（满分 10 仅作为前端提示，不强校验范围）。
- `pros` / `cons` / `other`：自由文本（用于 RB 成功/失败经验提炼）。
- `products[]`：产物测量列表（可增删多行）
  - `product_id`：从系统产品目录下拉选择（不允许手输名称）
  - `value`：实验测量值（activity 相关数值，单位随 Excel）
  - `fraction`：由系统计算并持久化（选择性）

反馈条目约束（重要）：
- 每个 run **最多只有 1 条 feedback**（不做多条复现记录）。
- 但允许对该 feedback 做“更新/编辑”，并触发：
  - 重新生成对比报告（可沿用或修改对比策略）。
  - 回滚/删除该 feedback 上一次生成的 RB 经验，并按最新内容重新学习（以保证经验与反馈一致）。
    - 要求：一次 RB 提炼可能产生 `add / remove(archive) / update` 三类 memory 变更；系统必须记录这些变更的“delta”，以便完整回退到提炼前状态，再用新 feedback 重新提炼。
    - 回滚语义（已确认）：**严格回滚**。即便实验员在 UI 中对这些 `mem:*` 条目做过人工编辑，feedback 更新触发回滚时仍以“回退到上一次提炼前的状态”为准（人工编辑会被覆盖/撤销），然后再用新 feedback 重新提炼。

### 8.2 产物目录（Product Catalog）
为避免误写/格式问题：
- 产品名称不允许自由输入（主流程用下拉）。
- 提供专门页面维护“产物列表”（增删改）。
- `product_id` 使用 UUID。
- 不需要 `unit_default` 字段（单位属于活性/测量维度，不必绑定到产物）。
- 产物也支持软删除（避免历史 run 引用断裂）。

### 8.3 Preset（产物集合预设）
- Preset 是一个“产物集合”的快捷选择（忽略数值，仅保存产物集合）。
- 保存时默认名字 = 用户选择的几个产物名拼接；用户可改名。
- UI 以下拉方式选择 preset。

### 8.4 历史对比分析：三种来源（可组合）
对比集（baseline/compare set）支持三选一（或组合）：
1) 用户指定一个或几个历史推荐 run
2) 用户手动输入经验（例如文献最好结果、平均值等，文本即可）
3) 系统自动：找到“同类产物集合”的历史数据 → 计算平均值与最大值（需存在已反馈历史）

同类定义（硬规则）：
- “同类”要求产物列表**完全匹配**（多产物列表的集合相等；不是“交集不为空”）。
- 计算用 `product_signature_key = "|".join(sorted(product_uuid_list))`（可读性优先，不哈希）。

边缘规则（已对齐）：
- 方法 3 的均值来源：同类的**全部历史**（与用户是否额外选择条目无关）。
- 方法 3 的 best：同类历史中 `score` 最高的一条（并取其详细数据作对比）。
- 如果用户额外选择（方法 1）：
  - 若未启用方法 3：均值按用户选择条目计算，且这些条目都参与详细对比。
  - 若启用方法 3：均值仍按同类全部历史；对比包含“同类 best + 用户选的条目详细数据”。
- 无历史数据：提示用户优先用方法 2 手动输入；若历史>=2 条，可计算平均值/最大值并提示将使用。

### 8.5 RB 提炼（从反馈生成经验条目）
- 用 `pros` 触发“成功经验提炼”提示词；用 `cons` 触发“失败经验提炼”提示词；`other` 作为补充。
- RB 提炼输入应包含：
  - 本次推荐配方与输出（结构化）
  - 反馈测量（含 fraction）
  - 对比报告（avg/best/deltas）
  - 实验员分析文本（pros/cons/other）
- 提炼出的经验条目写入 Chroma（带 `source_run_id` 等溯源信息），供后续检索引用 `mem:<id>`。

## 9. 模型与接口约束（可替换）

### 9.1 LLM/Embedding 接口
- 统一使用 **OpenAI compatible** 的 API 形态（便于用户替换任意模型服务）。
- embedding 同理；可通过 LlamaIndex 等扩展适配不同 embedding provider（待实现时再定）。
- 当前默认倾向：Qwen 系列（但必须保持可配置）。

## 10. UI 多语言（仅前端静态文案）
- 系统“数据/agent 输出/后端日志”默认全英文，不做翻译。
- 仅 UI 组件的静态文案（JS/TS 文件里写死的按钮/提示/标题）提供中英切换；默认英文。

### 10.1 Settings（系统配置页，需提供）
系统需要一个 Settings 页面，用于编辑/维护已明确的可配置项（不扩展到未提出的“候选金属范围”等）：
1) Products 管理（产物目录）：增/改/软删  
   - 仅用于 feedback 的产物选择与“同类分组（产物集合完全匹配）”，不参与 run 输入或配方生成。
2) Product Presets 管理（产物集合预设）：增/改/软删  
   - 仅用于 feedback 表单快捷选择产物集合。
3) ReasoningBank 参数与模板：例如 `k_role/k_global`、字段投影模板/版本（按 role）
4) Comparison 默认策略：method3 默认是否开启、历史不足时提示/行为等（不改变已对齐的边缘规则，只是默认 UI 行为）
5) UI 语言切换：仅影响前端静态文案（默认英文）

## 11. 参考资产位置（Repo 现状）
- 现阶段仅有研究资料，位于 `original_assets/`：
  - 文献 PDF（原理类 / 调控性类）
  - 架构组件参考（ReCAP/RB/ACE 论文 PDF）
  - 实验数据 `original_assets/实验数据.xlsx`
  - 结构描述与微环境分类 docx

## 12. 工程实现参考（对齐既有项目）
- 前后端封装与工程组织可参考既有项目：`/home/syk/projects/DES-recommendation`（agent 逻辑不同，但工程落地方式相近）。
- 参考的原则：
  - 可借鉴其前后端目录结构、启动方式、配置管理、API 组织与 UI 组件选型等。
  - 但不得为了“对齐旧项目”而牺牲本 spec 中已确定的更强约束（例如：精确引用、trace 全量记录、RB 回滚重学、对比策略边缘规则等）。

## 13. 部署（k3s + Helm Controller，后期完成）
- DES 项目使用 Docker/Compose 做容器化；本项目最终部署目标为 k3s 环境。
- 交付形态偏好：使用 k3s 的 helm-controller 安装/升级（提供 Helm Chart + 镜像）。
- 该部分可放在实现后期完成，但相关配置应从一开始就保持“可容器化/可配置”，避免最后大改。
