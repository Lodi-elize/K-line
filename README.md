# K-line 均线信号扫描器

一个 A 股日 K 均线信号工具。后端使用 `mootdx` 获取通达信行情数据，按 5/10/20 日均线规则计算信号；前端展示全市场扫描结果、模块筛选、历史 K 线均线图、箱线图和标注点。

本项目只做行情分析和信号提示，不做交易、不下单。

## 功能

- 全市场 A 股日线扫描。
- 5 日线、10 日线、20 日线均线信号计算。
- 最新股票状态列表，支持按信号级别和模块筛选。
- 单只股票历史 K 线、MA5、MA10、MA20 和信号标注。
- 概念模块、产业链模块、市场模块展示和筛选。
- 支持同花顺概念模块同步，模块更新状态通过 WebSocket 推送。
- 定时扫描任务和手动扫描接口。
- SQLite 本地缓存或 MySQL 远端存储 K 线、扫描任务、信号、模块和通知记录。
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
│   ├── Dockerfile      # 后端镜像构建
│   └── tests/          # 后端测试
├── K-line-web/         # Vite React 前端
│   └── src/
│       ├── api/        # API 客户端
│       ├── components/ # 信号表格、K 线图
│       └── types/      # 类型与中文标签
│   ├── Dockerfile      # 前端 Nginx 镜像构建
│   └── nginx.conf      # 静态站点与 API/WebSocket 反代
├── docker-compose.yml          # 服务器直接构建部署
├── docker-compose.deploy.yml   # 预构建镜像部署
├── .env.example                # 环境变量模板
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

## Docker 服务器部署

服务器已安装 Docker 时有两种部署方式：

- 推荐：本机或 CI 先构建镜像，上传到服务器后使用 `docker-compose.deploy.yml` 启动。适合小服务器，避免在服务器上构建导致负载过高。
- 简单：服务器直接使用 `docker-compose.yml` 构建并启动。适合 CPU/内存充足且网络稳定的服务器。

### 端口

- `80`：前端页面入口，必须开放。
- `8001`：后端 API 可选直连端口。页面访问不依赖公网开放 `8001`，因为前端 Nginx 会把 `/api` 和 `/ws` 反代到后端容器。
- `8000`：后端容器内部端口，不需要对公网开放。

### 环境变量

复制模板：

```bash
cp .env.example .env
vi .env
```

生产环境建议使用远端 MySQL：

```env
WEB_PORT=80
BACKEND_PORT=8001
KLINE_DATABASE_URL=mysql+pymysql://用户名:密码@数据库主机:端口/kLineDB?charset=utf8mb4
KLINE_SYNC_CONCEPTS=true
KLINE_PROVIDER=
```

说明：

- `WEB_PORT`：网页暴露端口，默认 `80`。
- `BACKEND_PORT`：后端 API 可选暴露端口，默认 `8001`；前端反代不依赖公网访问这个端口。
- `KLINE_DATABASE_URL`：MySQL 连接串。不要提交真实密码。
- `KLINE_SYNC_CONCEPTS`：是否允许概念模块同步，默认开启。
- `KLINE_PROVIDER`：留空使用真实行情；填 `fake` 只用于冒烟测试。

不要把包含真实数据库密码的 `.env` 提交到仓库。

### 推荐部署：预构建镜像上传

在本机或 CI 构建镜像：

```bash
docker build -t k-line-back:deploy ./K-line-back
docker build -t k-line-web:deploy ./K-line-web
docker save -o k-line-images.tar k-line-back:deploy k-line-web:deploy
```

上传到服务器：

```bash
scp k-line-images.tar root@服务器IP:/tmp/k-line-images.tar
scp docker-compose.deploy.yml root@服务器IP:/opt/k-line-observation/docker-compose.yml
```

在服务器上写入 `.env`：

```bash
mkdir -p /opt/k-line-observation
cd /opt/k-line-observation
vi .env
chmod 600 .env
```

在服务器加载镜像并启动：

```bash
docker load -i /tmp/k-line-images.tar
cd /opt/k-line-observation
docker compose up -d
```

清理上传包：

```bash
rm -f /tmp/k-line-images.tar
```

### 简单部署：服务器直接构建

服务器性能足够时可以直接拉代码构建：

```bash
git clone https://gitee.com/white-stranger/k-line-observation.git
cd k-line-observation
cp .env.example .env
vi .env
docker compose up -d --build
```

如果服务器已经有代码：

```bash
git pull
docker compose up -d --build
```

### 部署验证

外部访问：

```text
http://服务器IP/
http://服务器IP/api/health
```

服务器本机检查：

```bash
curl http://127.0.0.1/api/health
curl http://127.0.0.1:8001/api/health
```

返回 `{"status":"ok"}` 表示后端正常。

### 常用运维命令

查看容器：

```bash
docker compose ps
```

查看后端日志：

```bash
docker compose logs -f backend
```

查看前端 Nginx 日志：

```bash
docker compose logs -f web
```

重启服务：

```bash
docker compose restart
```

停止并移除本项目容器：

```bash
docker compose down --remove-orphans
```

手动触发全市场扫描：

```bash
curl -X POST http://127.0.0.1/api/scan/run
```

手动触发概念模块同步：

```bash
curl -X POST http://127.0.0.1/api/modules/sync
```

查看概念模块同步状态：

```bash
curl http://127.0.0.1/api/modules/sync/status
```

查看服务器负载：

```bash
uptime
docker stats
```

### 部署故障处理

如果服务器构建时负载过高，停止构建并清理本项目：

```bash
docker rm -f k-line-back k-line-web 2>/dev/null || true
docker compose -f /opt/k-line-observation/docker-compose.yml down --remove-orphans || true
rm -rf /opt/k-line-observation
rm -f /tmp/k-line-images.tar /tmp/k-line-docker-compose.yml /tmp/k-line-observation-deploy.tar.gz
```

如果 `http://服务器IP/` 可访问，但 `http://服务器IP:8001/api/health` 不通，通常是安全组没有开放 `8001`。这不影响网页正常使用。

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

- 后端测试：`10 passed`
- 前端构建：通过
- Docker 预构建镜像部署：通过

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
- `GET /api/stock-statuses`：获取全股票状态列表，支持 `severity`、`module_id`。
- `GET /api/modules`：获取市场、产业链、概念等模块。
- `POST /api/modules/sync`：手动触发概念模块同步。
- `GET /api/modules/sync/status`：查看概念模块同步状态。
- `WS /ws/modules/sync`：订阅概念模块同步进度。
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
