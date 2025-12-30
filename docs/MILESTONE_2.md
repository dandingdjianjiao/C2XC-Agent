# Milestone 2：Feedback（产物目录 + Presets + Run 反馈表单）

最后更新：2025-12-27

> 本文档用于实时跟踪 Milestone 2 的实施进度与关键决策。  
> 关联文档：
> - 总计划：`docs/DEVELOPMENT_PLAN.md`
> - Spec（Single Source of Truth）：`docs/PROJECT_SPEC.md`
> - API 契约：`docs/API_CONTRACT.md`（以当前实现为准，向后兼容演进）

---

## 0) 关键决策（冻结）

- 产物目录：主流程 **不允许自由输入产物名称**，必须从 `products` 下拉选择（避免误写与口径漂移）
- 反馈约束：每个 `run_id` **最多 1 条 feedback**（允许编辑更新，使用 upsert）
- 去重：`feedback.products[].product_id` **不允许重复**
- fraction：由服务端计算并 **持久化**
  - `fraction_i = value_i / sum(value_selected_products)`
  - 若 `sum(value)=0`，则所有 `fraction` 记录为 `0`，并由 UI 明确提示
- 软删除：products/presets 使用 `status=active|archived`（不做硬删除，避免历史引用断裂）

---

## 1) 范围（In Scope / Out of Scope）

### In Scope（Milestone 2 做）

- SQLite 增表：`products`、`product_presets`、`product_preset_products`、`feedback`、`feedback_products`
- Backend API：
  - Products：`GET/POST/PUT /products`
  - Presets：`GET/POST/PUT /product_presets`
  - Run Feedback：`GET/PUT /runs/{run_id}/feedback`
- WebUI：
  - Run 详情页新增 `Feedback` tab（填写/编辑 feedback）
  - Settings 页面：维护 Products 与 Presets

### Out of Scope（后续里程碑做）

- Comparison report（历史对比集计算与展示）
- 保存 feedback 后触发 RB 学习（Milestone 3）
- RB 回滚/重学（Milestone 3）

---

## 2) 交付清单（实时更新）

- [x] DB schema_version 升级到 3（新增 Feedback/Products/Presets 表）
- [x] Products API（list/create/update）
- [x] Presets API（list/create/update）
- [x] Run Feedback API（get/upsert；服务端计算 fraction 并落库）
- [x] WebUI：Settings（Products/Presets）+ RunDetail Feedback tab
- [x] 最小测试：feedback fraction、sum=0、重复 product_id 校验

---

## 3) 如何运行（Milestone 2 当前可用）

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

