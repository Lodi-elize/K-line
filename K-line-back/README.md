# K-line-back

均线信号扫描器后端。负责数据获取、均线信号计算、定时扫描、持久化和 API 输出。默认使用 SQLite，也可以通过环境变量切换到远端 MySQL。

## 当前行为

- 服务端口固定为 `9091`。
- 真实行情默认来自 `mootdx`；测试/演示可设置 `KLINE_PROVIDER=fake`。
- 远端 MySQL 模式下会拒绝 fake 行情源，避免测试数据写入真实数据库。
- 扫描只负责股票列表、日 K、均线信号和扫描状态；概念模块同步已从扫描流程中移除。
- 扫描状态通过 `WS /ws/scan/status` 推送，`GET /api/scan/status` 只用于读取最近状态。
- 概念模块同步通过 `POST /api/modules/sync` 单独触发，进度通过 `WS /ws/modules/sync` 推送。
- `klines` 表包含 `change_pct` 涨跌幅；数据源未提供时由后端按前后收盘价计算，旧记录读取时也会补算。
- 当前进场信号为“连板回踩10日线”，规则已忽略缩量条件。

## 启动

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9091
```

强制使用 fake 数据源：

```powershell
$env:KLINE_PROVIDER="fake"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9091
```

## 数据库

默认使用本地 `data/kline.db`：

```powershell
Remove-Item Env:\KLINE_DATABASE_URL -ErrorAction SilentlyContinue
```

切换到远端 MySQL 时先创建一个 `utf8mb4` 数据库，然后配置连接串：

```powershell
$env:KLINE_DATABASE_URL="mysql+pymysql://用户名:密码@主机:3306/数据库名?charset=utf8mb4"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9091
```

应用启动时会自动创建所需表。SQLite 旧数据不会自动迁移到 MySQL；需要迁移历史数据时请先导出再导入。

概念模块同步默认关闭，避免 AkShare/东方财富网络异常阻塞全市场扫描。需要同步概念模块时再开启：

```powershell
$env:KLINE_SYNC_CONCEPTS="1"
```

即使开启 `KLINE_SYNC_CONCEPTS`，概念模块也不会随全市场扫描自动同步；请使用 `/api/modules/sync` 或前端“更新模块”按钮单独触发。

## 进场信号规则

当前唯一 `entry` 级别信号是 `double_limit_up_ten_ma_pullback`，界面显示为“连板回踩10日线”。生成条件：

- `double_limit_lookback_days` 个交易日内存在连续两天涨停；
- 涨停使用 `KLine.change_pct >= limit_up_pct` 判断，当前默认 `limit_up_pct = 0.09`；
- 当前日最低价触碰/接近 MA10，容忍度为 `touch_tolerance_pct`；
- 当前日收盘没有有效跌破 MA10，容忍度为 `break_tolerance_pct`；
- 当前日自身不是涨停日；
- 当前规则不检查成交量缩量。

## 测试

```powershell
$env:PYTHONPATH=(Get-Location).Path
$env:KLINE_PROVIDER="fake"
.\.venv\Scripts\pytest -q
```

## 主要模块

- `app/core/signal_engine.py`：均线信号算法。
- `app/core/config.py`：可调阈值和中文说明。
- `app/providers/mootdx_provider.py`：mootdx 行情数据源。
- `app/providers/fake.py`：测试/演示数据源。
- `app/services/storage.py`：SQLite/MySQL 持久化。
- `app/services/scanner.py`：扫描流程。
- `app/services/notifier.py`：通知接口预留。
