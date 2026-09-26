# 实验室样品检测平台

面向样品受理、任务派发、检测执行、仪器校准与报告出具的一体化实验室检测管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
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
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 样品受理 | `sample` | 样品 | 样品编号、样品名称、样品类别 |
| 委托单位 | `client` | 委托单位 | 单位编码、单位名称、单位类型 |
| 检测项目 | `project` | 检测项目 | 项目编码、项目名称、检测方法 |
| 检测任务 | `task` | 检测任务 | 任务编号、关联样品、检测项目 |
| 检测执行 | `execute` | 执行记录 | 记录编号、关联任务、前处理方式 |
| 检测结果 | `result` | 检测结果 | 结果编号、关联任务、检测值 |
| 结果复核 | `review` | 复核记录 | 复核编号、关联结果、复核项目 |
| 仪器设备 | `instrument` | 仪器设备 | 设备编号、设备名称、设备型号 |
| 校准记录 | `calibration` | 校准记录 | 校准编号、关联设备、校准方式 |
| 试剂耗材 | `reagent` | 试剂物料 | 物料编号、物料名称、规格纯度 |
| 耗材领用 | `consume` | 领用单 | 领用单号、物料名称、领用数量 |
| 环境监控 | `environment` | 环境记录 | 记录编号、监控区域、温度值 |
| 报告出具 | `report` | 检测报告 | 报告编号、关联样品、报告类型 |
| 报告变更 | `issue` | 变更记录 | 变更编号、关联报告、变更类型 |
| 质量控制 | `qc` | 质控记录 | 质控编号、质控类型、关联项目 |
| 投诉处理 | `complaint` | 投诉记录 | 投诉编号、投诉单位、投诉事由 |
| 样品流转 | `stockin` | 流转记录 | 流转编号、关联样品、流转环节 |
| 检测结算 | `settlement` | 结算单 | 结算单号、委托单位、结算周期 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 角色与权限（委托单位、样品受理、检测结算）

- 写操作要求请求头携带 `X-Operator-Role`（角色）与 `X-Operator-Name`（操作人）；
  请求头只允许 ASCII，中文值按 URL 百分号编码传输，后端统一解码。
- 角色口径见 `backend/app/services/permission.py`：业务员可登记委托单位/检测委托/结算单，
  审核员可审核单位，管理员另可暂停/终止合作与修改档案；未识别角色一律 403。
- 委托单位合作状态为已暂停/已终止，或资质编号已过期（按 `资质有效期至` 到期口径）时，
  样品受理与检测结算两个登记入口都会拦下新委托并说明原因；
  资质过期的合作单位在列表与详情统一显示「资质过期」。
- 资质编号、结算方式等档案字段只能走 `PUT /api/client/{id}` 由有权限角色修改，
  每次修改逐字段写入变更记录（时间、操作人、角色、旧值、新值），单位编码等归属字段不可改；
  已终止单位档案冻结。历史委托与结算记录不被任何入口改动。

## 测试

```bash
cd backend && python3 -m unittest discover -s tests -v
```

服务层测试只依赖标准库；`tests/e2e_check.py` 是接口级冒烟脚本，需要安装
`fastapi` 与 `httpx` 后运行（`python3 tests/e2e_check.py`）。
