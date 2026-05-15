# K-line-back

均线信号扫描器后端。负责数据获取、均线信号计算、定时扫描、SQLite 持久化和 API 输出。

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
- `app/services/storage.py`：SQLite 持久化。
- `app/services/scanner.py`：扫描流程。
- `app/services/notifier.py`：通知接口预留。
