# K-line 均线信号扫描器

一个本地运行的 A 股日 K 均线信号工具。后端使用 `mootdx` 获取通达信行情数据，按 5/10/20 日均线规则计算信号；前端展示全市场扫描结果、信号筛选、历史 K 线均线图和标注点。

本项目只做行情分析和信号提示，不做交易、不下单。

## 功能

- 全市场 A 股日线扫描。
- 5 日线、10 日线、20 日线均线信号计算。
- 最新信号列表，支持按级别和信号类型筛选。
- 单只股票历史 K 线、MA5、MA10、MA20 和信号标注。
- 定时扫描任务和手动扫描接口。
- SQLite 本地缓存 K 线、扫描任务、信号和通知记录。
- 预留通知接口，当前版本只写入本地通知记录。
- 可调算法阈值带中文说明。

## 目录结构

```text
.
├── K-line-back/        # FastAPI 后端
│   ├── app/
│   │   ├── core/       # 配置、模型、均线信号算法
│   │   ├── providers/  # mootdx / fake 数据源
│   │   └── services/   # 扫描、存储、通知接口
│   └── tests/          # 后端测试
├── K-line-web/         # Vite React 前端
│   └── src/
│       ├── api/        # API 客户端
│       ├── components/ # 信号表格、K 线图
│       └── types/      # 类型与中文标签
└── README.md
```

## 环境要求

- Python 3.12 或兼容版本
- Node.js 22 或兼容版本
- npm
- 网络可访问 PyPI/npm registry

## 启动后端

```powershell
cd K-line-back
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/health
```

开发或演示时可强制使用 fake 数据源，避免依赖 mootdx 实时连通性：

```powershell
$env:KLINE_PROVIDER="fake"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 启动前端

```powershell
cd K-line-web
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

前端开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 验证

后端测试：

```powershell
cd K-line-back
$env:PYTHONPATH=(Get-Location).Path
$env:KLINE_PROVIDER="fake"
.\.venv\Scripts\pytest -q
```

前端构建：

```powershell
cd K-line-web
npm run build
```

当前已验证：

- 后端测试：`7 passed`
- 前端构建：通过

前端构建可能提示 chunk 超过 500KB，主要来自图表库 `recharts`，不影响运行。

## 信号规则

当前实现覆盖以下规则：

- 5 日线金叉：5 日均线上穿 10 日均线。
- 5 日线死叉：5 日均线下穿 10 日均线。
- 回踩 5 日线不破：价格接近 5 日均线，未有效跌破，并重新收回。
- 5 日线拐头向上/向下：通过配置的斜率阈值判断。
- 跌破 10 日线且无反抽：跌破 10 日均线后未达到反抽确认阈值。
- 跌破 20 日生命线。
- 触碰 20 日线支撑/阻力。
- 均线多头排列：MA5 > MA10 > MA20 且满足发散/上行确认。
- 均线空头排列：MA20 > MA10 > MA5 且满足发散/下行确认。

模糊规则采用偏严格过滤，宁可少报信号。

## 可调算法项

后端配置位于：

```text
K-line-back/app/core/config.py
```

主要参数：

- `touch_tolerance_pct`：均线触碰容忍度。
- `break_tolerance_pct`：回踩跌破容忍度。
- `upward_slope_pct`：上拐斜率阈值。
- `downward_slope_pct`：下拐斜率阈值。
- `slope_lookback_days`：斜率确认天数。
- `rebound_confirm_pct`：反抽确认阈值。
- `arrangement_spread_pct`：均线排列发散阈值。

这些参数会通过 `/api/config` 返回给前端，并在“可调算法项”区域展示中文说明。

## 常用 API

- `GET /api/health`：健康检查。
- `GET /api/config`：查看算法配置说明。
- `GET /api/scan/status`：查看最近一次扫描状态。
- `POST /api/scan/run`：手动触发扫描。
- `GET /api/signals`：获取最新信号。
- `GET /api/stocks?q=600`：搜索股票。
- `GET /api/stocks/{symbol}/history`：获取股票历史 K 线与信号标注。

## 当前不做的事

- 不做真实交易或下单。
- 不接外部通知渠道，只预留接口。
- 不做分钟线、tick 或实时流数据。
- 不做复杂回测。
- 不做登录、多用户和权限系统。
- 不保证每次定时任务都能实时扫完整个市场。

## 备注

`mootdx` 依赖通达信行情服务，实际扫描速度和稳定性会受网络、服务器可用性和股票数量影响。测试和本地演示建议先使用 `KLINE_PROVIDER=fake`。
