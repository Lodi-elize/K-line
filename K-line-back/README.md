# K-line-back

均线信号扫描器后端。负责数据获取、均线信号计算、定时扫描、持久化和 API 输出。默认使用 SQLite，也可以通过环境变量切换到远端 MySQL。

## 启动

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

强制使用 fake 数据源：

```powershell
$env:KLINE_PROVIDER="fake"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 数据库

默认使用本地 `data/kline.db`：

```powershell
Remove-Item Env:\KLINE_DATABASE_URL -ErrorAction SilentlyContinue
```

切换到远端 MySQL 时先创建一个 `utf8mb4` 数据库，然后配置连接串：

```powershell
$env:KLINE_DATABASE_URL="mysql+pymysql://用户名:密码@主机:3306/数据库名?charset=utf8mb4"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

应用启动时会自动创建所需表。SQLite 旧数据不会自动迁移到 MySQL；需要迁移历史数据时请先导出再导入。

概念模块同步默认关闭，避免 AkShare/东方财富网络异常阻塞全市场扫描。需要同步概念模块时再开启：

```powershell
$env:KLINE_SYNC_CONCEPTS="1"
```

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
