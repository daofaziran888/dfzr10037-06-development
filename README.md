# 知谱工坊 · 元数据知识图谱与智能探查平台

面向元数据实体抽取、关系建模、知识图谱构建、图谱搜索、实体链接、消岐融合、路径推理、子图探查与图谱演化追踪的元数据知识图谱与智能探查平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 实体抽取 | `entity_extract` | 实体定义 | 实体编号、实体类型、数据来源 |
| 关系建模 | `relation_model` | 关系类型 | 关系编号、关系名、主体类型 |
| 图谱构建 | `graph_build` | 构建任务 | 任务编号、数据范围、图类型 |
| 图谱搜索 | `graph_search` | 搜索模板 | 模板编号、搜索类型、查询语法 |
| 实体链接 | `entity_link` | 链接规则 | 规则编号、源实体、目标实体 |
| 消岐融合 | `disambig` | 消岐配置 | 配置编号、歧义类型、候选实体 |
| 路径推理 | `path_reason` | 推理任务 | 任务编号、起始实体、目标实体 |
| 子图探查 | `subgraph_exp` | 探查配置 | 配置编号、探查种子、扩展策略 |
| 图谱演化 | `graph_evolve` | 演化记录 | 记录编号、变更类型、影响实体 |
| 质量审计 | `quality_audit` | 审计报告 | 报告编号、审计范围、实体准确率 |
| 元数据标注 | `metadata_tag` | 标注任务 | 任务编号、标注对象、标注类型 |
| 分类体系 | `taxonomy` | 分类树 | 分类编号、分类名称、父分类 |
| 查询缓存 | `query_cache` | 缓存条目 | 条目编号、查询模板、结果哈希 |
| 图谱索引 | `graph_index` | 索引配置 | 索引编号、目标属性、索引类型 |
| 数据血缘 | `data_lineage` | 血缘链路 | 链路编号、上游实体、下游实体 |
| 推荐引擎 | `reco_engine` | 推荐规则 | 规则编号、推荐场景、源实体 |
| 实体归并 | `entity_merge` | 归并任务 | 任务编号、源实体、目标实体 |
| 批量导入 | `batch_load` | 导入任务 | 任务编号、数据文件、目标图谱 |
| 图谱报告 | `report_gen` | 图谱报表 | 报告编号、报告类型、数据范围 |
| 图谱比对 | `graph_compare` | 比对任务 | 任务编号、基准图、对比图 |
| 定时任务 | `schedule_job` | 调度作业 | 作业编号、任务类型、关联图谱 |
| 治理看板 | `govern_dash` | 治理指标 | 指标编号、指标名称、评估对象 |

## 可复核质量指标（治理看板）

`/govern_dash` 是治理看板的专用页面，除原有指标台账外，还展示两轮质量审计样本的
分层聚合指标。取样数据在 `backend/app/quality_seed.py`：第 1 轮只抽 10 个重叠实体，
第 2 轮扩围到 10 个重叠 + 5 个新增实体。

- **分子/分母**：分子是判定为错连的关系条数，分母是抽检关系条数；两者随指标一起返回。
- **图谱版本**：每个指标、每条错连明细都带 `graph_version`（R1 `kg-2026Q3-v3`，
  R2 `kg-2026Q4-v4`），可用 `/api/quality/evidence` 逐条回查。
- **两种口径**：同口径只取两轮共同抽到的实体，改善率 20% → 10%（改善）；扩围全量
  因为新增样本大量错连，错连率 20% → 33.33%（恶化）。后者的分子分母构成不同，
  接口标记为 `not_comparable`，不给出改善率。
- **样本缺失保护**：基线样本不可取得时，`/api/quality/compare` 返回
  `status=baseline_missing`、`improvement_rate=null`，并明确记录被拦截的
  「全量错连率直接相减」算法；不会把全量变化折算成改善率。
- **整改派发**：只有带明细编号的错连进入整改清单（本轮 47 条），未落明细的
  3 条只登记不派发。同步后写入 `quality_audit` 模块，进入既有「指派整改」流程。
- **受理回执**：按「轮次 + 口径」留存快照，新口径重算不影响旧范围回执；样本缺失后
  回执显示「原样本不可取得」，保留受理时快照且不给改善结论。

主要接口：

| 接口 | 用途 |
| --- | --- |
| `GET /api/quality/dashboard` | 看板取数（新口径、旧口径、两轮比较、回执） |
| `GET /api/quality/metrics?round=2&scope=expanded\|overlap` | 单轮分层指标 |
| `GET /api/quality/compare?baseline=1&current=2` | 同口径比较与趋势冲突判断 |
| `GET /api/quality/evidence?round=2&stratum=all` | 错连明细回查 |
| `GET /api/quality/remediation?round=2&scope=...` | 整改清单预览 |
| `POST /api/quality/remediation/sync?round=2&scope=...` | 同步取样结果并留存回执 |
| `GET /api/quality/receipts/{receipt_id}` | 已受理范围核对 |
| `POST /api/quality/samples/availability` | 标记/恢复样本可用性，验证口径降级 |

后端测试：`cd backend && .venv/bin/python -m pytest tests -q`。

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

领域：数据工程
子方向：数据分析与数据应用
