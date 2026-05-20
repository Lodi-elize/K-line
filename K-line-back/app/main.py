from __future__ import annotations

import asyncio
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.history_range import HISTORY_RANGE_LIMITS, normalize_history_range, source_limit_for_range
from app.core.models import AnnotatedBar, Signal, SignalType
from app.core.signal_engine import SignalEngine
from app.core.stock_scope import is_mainland_hs_symbol
from app.providers.akshare_board_provider import AkshareBoardProvider
from app.providers.base import MarketDataProvider
from app.providers.mootdx_provider import MootdxProvider
from app.services.notifier import DatabaseNotifier
from app.services.scanner import ScannerService
from app.services.signal_recompute import SignalRecomputeService
from app.services.storage import Storage


storage = Storage(settings.database_path, settings.database_url)
storage.mark_interrupted_scans()
storage.prune_non_hs_stocks()
storage.reclassify_obsolete_entry_signals({SignalType.DOUBLE_LIMIT_UP_TEN_MA_PULLBACK.value})
engine = SignalEngine(settings.thresholds)
startup_maintenance_state: dict[str, object] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "message": "",
}


class UnavailableMarketDataProvider(MarketDataProvider):
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def _raise_unavailable(self) -> None:
        raise RuntimeError(f"行情源不可用：{self.reason}")

    def list_symbols(self) -> list[dict[str, str]]:
        self._raise_unavailable()

    def daily_bars(self, symbol: str, limit: int = 120):
        self._raise_unavailable()

    def intraday_bars(self, symbol: str, limit: int = 240, trade_date: str | None = None):
        self._raise_unavailable()


def create_provider() -> MarketDataProvider:
    if os.getenv("KLINE_PROVIDER", "").lower() == "fake":
        if settings.database_url:
            return UnavailableMarketDataProvider("远端数据库模式禁止启用 fake 行情源，避免测试数据写入真实数据库。")
        from app.providers.fake import FakeMarketDataProvider

        return FakeMarketDataProvider()
    try:
        return MootdxProvider()
    except Exception as exc:
        return UnavailableMarketDataProvider(str(exc))


def create_board_provider():
    if not settings.sync_concept_modules:
        return None
    if os.getenv("KLINE_PROVIDER", "").lower() == "fake":
        return None
    try:
        return AkshareBoardProvider()
    except Exception:
        return None


provider = create_provider()
board_provider = create_board_provider()
notifier = DatabaseNotifier(storage)
scanner = ScannerService(provider, storage, engine, notifier, settings.max_scan_symbols, lambda: broadcast_scan_status())
scan_status_clients: set[WebSocket] = set()
scan_status_loop: asyncio.AbstractEventLoop | None = None
signal_recompute_lock = threading.Lock()
signal_recompute_state: dict[str, object] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "total_symbols": 0,
    "processed_symbols": 0,
    "signal_count": 0,
    "message": "",
}
signal_recompute_clients: set[WebSocket] = set()
signal_recompute_loop: asyncio.AbstractEventLoop | None = None
module_sync_lock = threading.Lock()
module_sync_state: dict[str, object] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "updated_count": 0,
    "message": "",
}
module_sync_clients: set[WebSocket] = set()
module_sync_loop: asyncio.AbstractEventLoop | None = None
try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None

scheduler = BackgroundScheduler(timezone="Asia/Shanghai") if BackgroundScheduler else None


def beijing_timestamp() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0).isoformat(sep=" ")


def attach_stored_signals(symbol: str, annotated: list[AnnotatedBar]) -> list[AnnotatedBar]:
    signals_by_date = storage.signals_for_symbol_dates(symbol, (item.kline.date for item in annotated))
    if not signals_by_date:
        return annotated

    remaining = {date: list(signals) for date, signals in signals_by_date.items()}
    merged: list[AnnotatedBar] = []
    for item in annotated:
        exact_signals = remaining.pop(item.kline.date, [])
        day_signals: list[Signal] = []
        day = item.kline.date[:10]
        if item.kline.date == day:
            day_signals = remaining.pop(day, [])
        elif item == annotated[-1]:
            day_signals = remaining.pop(day, [])
        signals = [*item.signals, *exact_signals, *day_signals]
        deduped = list({(signal.trade_date, signal.signal_type.value): signal for signal in signals}.values())
        merged.append(AnnotatedBar(item.kline, item.ma5, item.ma10, item.ma20, deduped))
    return merged


def _period_key(date_text: str, range_value: str) -> str:
    date_part = date_text[:10]
    trade_day = datetime.fromisoformat(date_part).date()
    if range_value == "weekly":
        year, week, _ = trade_day.isocalendar()
        return f"{year}-W{week:02d}"
    if range_value == "monthly":
        return date_part[:7]
    if range_value == "hourly" and " " in date_text:
        return f"{date_text[:13]}:00"
    return date_part


def aggregate_klines(rows: list, range_value: str) -> list:
    grouped: dict[str, list] = {}
    ordered_rows = sorted(rows, key=lambda item: item.date)
    previous_close_by_period: dict[str, float] = {}
    for row in rows:
        key = _period_key(row.date, range_value)
        grouped.setdefault(key, []).append(row)
    last_close: float | None = None
    for row in ordered_rows:
        key = _period_key(row.date, range_value)
        if key not in previous_close_by_period:
            previous_close_by_period[key] = last_close or 0
        last_close = row.close

    aggregated = []
    for key, items in grouped.items():
        ordered = sorted(items, key=lambda item: item.date)
        first = ordered[0]
        last = ordered[-1]
        previous_close = previous_close_by_period.get(key)
        change_pct = round((last.close - previous_close) / previous_close, 6) if previous_close else last.change_pct
        aggregated.append(
            type(first)(
                first.symbol,
                key,
                first.open,
                max(item.high for item in ordered),
                min(item.low for item in ordered),
                last.close,
                sum(item.volume for item in ordered),
                change_pct,
            )
        )
    return aggregated


def aggregate_annotated_klines(rows: list, range_value: str) -> list[AnnotatedBar]:
    if range_value not in {"weekly", "monthly"}:
        return engine.annotate(aggregate_klines(rows, range_value))

    daily_annotated = engine.annotate(rows)
    grouped: dict[str, list[AnnotatedBar]] = {}
    for item in daily_annotated:
        grouped.setdefault(_period_key(item.kline.date, range_value), []).append(item)

    aggregated: list[AnnotatedBar] = []
    for key, items in grouped.items():
        ordered = sorted(items, key=lambda item: item.kline.date)
        first = ordered[0].kline
        last_item = ordered[-1]
        last = last_item.kline
        previous_close = next((item.kline.close for item in reversed(daily_annotated) if item.kline.date < first.date), None)
        change_pct = round((last.close - previous_close) / previous_close, 6) if previous_close else last.change_pct
        kline = type(first)(
            first.symbol,
            key,
            first.open,
            max(item.kline.high for item in ordered),
            min(item.kline.low for item in ordered),
            last.close,
            sum(item.kline.volume for item in ordered),
            change_pct,
        )
        aggregated.append(AnnotatedBar(kline, last_item.ma5, last_item.ma10, last_item.ma20, []))
    return aggregated


def attach_period_signals(symbol: str, annotated: list[AnnotatedBar], source_rows: list, range_value: str) -> list[AnnotatedBar]:
    if range_value not in {"weekly", "monthly"}:
        return attach_stored_signals(symbol, annotated)

    signals_by_date = storage.signals_for_symbol_dates(symbol, (row.date for row in source_rows))
    if not signals_by_date:
        return annotated

    signals_by_period: dict[str, list[Signal]] = {}
    for date_text, signals in signals_by_date.items():
        signals_by_period.setdefault(_period_key(date_text, range_value), []).extend(signals)

    merged: list[AnnotatedBar] = []
    for item in annotated:
        signals = [*item.signals, *signals_by_period.get(item.kline.date, [])]
        deduped = list({(signal.trade_date, signal.signal_type.value): signal for signal in signals}.values())
        merged.append(AnnotatedBar(item.kline, item.ma5, item.ma10, item.ma20, deduped))
    return merged


def visible_annotated_bars(annotated: list[AnnotatedBar], display_limit: int, require_ma: bool = True) -> list[AnnotatedBar]:
    if not require_ma:
        return annotated[-display_limit:]
    drawable = [
        item
        for item in annotated
        if item.ma5 is not None and item.ma10 is not None and item.ma20 is not None
    ]
    return drawable[-display_limit:]


async def send_module_sync_status(websocket: WebSocket) -> None:
    await websocket.send_json(module_sync_state)


async def send_scan_status(websocket: WebSocket) -> None:
    await websocket.send_json(storage.latest_scan())


async def broadcast_scan_status_async() -> None:
    status = storage.latest_scan()
    for websocket in list(scan_status_clients):
        try:
            await websocket.send_json(status)
        except Exception:
            scan_status_clients.discard(websocket)


def broadcast_scan_status() -> None:
    if scan_status_loop is None or scan_status_loop.is_closed():
        return
    asyncio.run_coroutine_threadsafe(broadcast_scan_status_async(), scan_status_loop)


async def send_signal_recompute_status(websocket: WebSocket) -> None:
    await websocket.send_json(signal_recompute_state)


async def broadcast_signal_recompute_status_async() -> None:
    for websocket in list(signal_recompute_clients):
        try:
            await websocket.send_json(signal_recompute_state)
        except Exception:
            signal_recompute_clients.discard(websocket)


def broadcast_signal_recompute_status() -> None:
    if signal_recompute_loop is None or signal_recompute_loop.is_closed():
        return
    asyncio.run_coroutine_threadsafe(broadcast_signal_recompute_status_async(), signal_recompute_loop)


def update_signal_recompute_state(next_state: dict[str, object]) -> None:
    signal_recompute_state.update(next_state)
    broadcast_signal_recompute_status()


def run_signal_recompute_job() -> None:
    if not signal_recompute_lock.acquire(blocking=False):
        return
    update_signal_recompute_state(
        {
            "status": "running",
            "started_at": beijing_timestamp(),
            "finished_at": None,
            "total_symbols": 0,
            "processed_symbols": 0,
            "signal_count": 0,
            "message": "正在基于已有K线重算进/离场信号。",
        }
    )

    def update_progress(total_symbols: int, processed_symbols: int, signal_count: int, message: str = "") -> None:
        update_signal_recompute_state(
            {
                "total_symbols": total_symbols,
                "processed_symbols": processed_symbols,
                "signal_count": signal_count,
                "message": message or f"正在重算进/离场信号：{processed_symbols}/{total_symbols}",
            }
        )

    try:
        service = SignalRecomputeService(storage, engine, update_progress)
        result = service.recompute()
        update_signal_recompute_state(
            {
                "status": result.status,
                "finished_at": beijing_timestamp(),
                "total_symbols": result.total_symbols,
                "processed_symbols": result.processed_symbols,
                "signal_count": result.signal_count,
                "message": result.message or f"进/离场信号重算完成：{result.processed_symbols} 只，{result.signal_count} 个点。",
            }
        )
    except Exception as exc:
        update_signal_recompute_state(
            {
                "status": "failed",
                "finished_at": beijing_timestamp(),
                "message": f"进/离场信号重算失败：{exc}",
            }
        )
    finally:
        signal_recompute_lock.release()


async def broadcast_module_sync_status_async() -> None:
    for websocket in list(module_sync_clients):
        try:
            await websocket.send_json(module_sync_state)
        except Exception:
            module_sync_clients.discard(websocket)


def broadcast_module_sync_status() -> None:
    if module_sync_loop is None or module_sync_loop.is_closed():
        return
    asyncio.run_coroutine_threadsafe(broadcast_module_sync_status_async(), module_sync_loop)


def update_module_sync_state(next_state: dict[str, object]) -> None:
    module_sync_state.update(next_state)
    broadcast_module_sync_status()


def sync_concept_modules() -> None:
    if not module_sync_lock.acquire(blocking=False):
        return
    update_module_sync_state(
        {
            "status": "running",
            "started_at": beijing_timestamp(),
            "finished_at": None,
            "updated_count": 0,
            "message": "概念模块同步中。",
        }
    )
    try:
        board = AkshareBoardProvider()
        def update_progress(board_name: str, current: int, total: int, count: int, board_members: list[object]) -> None:
            storage.upsert_concept_modules([(member.symbol, member.board_name) for member in board_members])
            update_module_sync_state(
                {
                    "updated_count": count,
                    "message": f"正在同步真实概念模块：{current}/{total}，当前：{board_name}，已写入数据库。",
                }
            )

        members = board.concept_members(update_progress)
        backfilled_count = storage.backfill_chain_modules_from_concepts()
        update_module_sync_state(
            {
                "status": "success",
                "finished_at": beijing_timestamp(),
                "updated_count": len(members),
                "message": f"概念模块同步完成，更新 {len(members)} 条归属关系，回填 {backfilled_count} 条产业链关系。",
            }
        )
    except Exception as exc:
        update_module_sync_state(
            {
                "status": "failed",
                "finished_at": beijing_timestamp(),
                "message": f"概念模块同步失败：{exc}",
            }
        )
    finally:
        module_sync_lock.release()

def start_scheduler() -> None:
    if scheduler and not scheduler.running:
        scheduler.add_job(scanner.run_scan, "cron", day_of_week="mon-fri", hour=18, minute=0, id="daily_scan", replace_existing=True)
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)


def run_startup_maintenance() -> None:
    startup_maintenance_state.update(
        {
            "status": "running",
            "started_at": beijing_timestamp(),
            "finished_at": None,
            "message": "启动维护任务运行中。",
        }
    )
    try:
        market_count = storage.sync_market_modules_for_all_stocks()
        chain_count = storage.backfill_chain_modules_from_concepts()
        startup_maintenance_state.update(
            {
                "status": "success",
                "finished_at": beijing_timestamp(),
                "message": f"启动维护任务完成，市场模块同步 {market_count} 只股票，产业链回填 {chain_count} 条。",
            }
        )
    except Exception as exc:
        startup_maintenance_state.update(
            {
                "status": "failed",
                "finished_at": beijing_timestamp(),
                "message": f"启动维护任务失败，已跳过：{exc}",
            }
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    global module_sync_loop, scan_status_loop
    module_sync_loop = asyncio.get_running_loop()
    scan_status_loop = module_sync_loop
    start_scheduler()
    threading.Thread(target=run_startup_maintenance, daemon=True).start()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config() -> dict[str, object]:
    return {"thresholds": settings.thresholds.as_documented_items(), "scan_cron": settings.scan_cron}


@app.get("/api/scan/status")
def scan_status() -> dict[str, object] | None:
    return storage.latest_scan()


@app.post("/api/scan/run")
def run_scan() -> dict[str, object]:
    latest = storage.latest_scan()
    if latest and latest.get("status") == "running":
        return {
            "status": "running",
            "scanned_count": latest.get("scanned_count", 0),
            "signal_count": latest.get("signal_count", 0),
            "message": "扫描正在运行，请稍后刷新进度。",
    }
    run_id = storage.start_scan()
    broadcast_scan_status()
    threading.Thread(target=scanner.run_scan, args=(run_id,), daemon=True).start()
    return {"status": "running", "scanned_count": 0, "signal_count": 0, "message": "扫描已在后台启动。"}


@app.get("/api/signals")
def latest_signals(
    limit: int = Query(200, ge=1, le=1000),
    signal_type: str | None = None,
    severity: str | None = None,
) -> list[dict[str, object]]:
    return storage.latest_signals(limit=limit, signal_type=signal_type, severity=severity)


@app.get("/api/signals/recompute/status")
def signal_recompute_status() -> dict[str, object]:
    return signal_recompute_state


@app.post("/api/signals/recompute")
def run_signal_recompute() -> dict[str, object]:
    if signal_recompute_state.get("status") == "running" or signal_recompute_lock.locked():
        return signal_recompute_state
    threading.Thread(target=run_signal_recompute_job, daemon=True).start()
    return {
        "status": "running",
        "started_at": beijing_timestamp(),
        "finished_at": None,
        "total_symbols": 0,
        "processed_symbols": 0,
        "signal_count": 0,
        "message": "进/离场信号重算已在后台启动。",
    }


@app.get("/api/stock-statuses")
def stock_statuses(
    limit: int = Query(10000, ge=1, le=10000),
    signal_type: str | None = None,
    severity: str | None = None,
    module_id: int | None = Query(None, ge=1),
) -> list[dict[str, object]]:
    return storage.stock_statuses(limit=limit, signal_type=signal_type, severity=severity, module_id=module_id)


@app.get("/api/modules")
def modules() -> list[dict[str, object]]:
    return storage.modules()


@app.get("/api/modules/sync/status")
def module_sync_status() -> dict[str, object]:
    return module_sync_state


@app.post("/api/modules/sync")
def run_module_sync() -> dict[str, object]:
    if module_sync_state.get("status") == "running":
        return module_sync_state
    threading.Thread(target=sync_concept_modules, daemon=True).start()
    return {
        "status": "running",
        "started_at": beijing_timestamp(),
        "finished_at": None,
        "updated_count": 0,
        "message": "概念模块同步已在后台启动。",
    }


@app.websocket("/ws/modules/sync")
async def module_sync_websocket(websocket: WebSocket) -> None:
    global module_sync_loop
    module_sync_loop = asyncio.get_running_loop()
    await websocket.accept()
    module_sync_clients.add(websocket)
    try:
        await websocket.send_json(module_sync_state)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        module_sync_clients.discard(websocket)
    except Exception:
        module_sync_clients.discard(websocket)


@app.websocket("/ws/scan/status")
async def scan_status_websocket(websocket: WebSocket) -> None:
    global scan_status_loop
    scan_status_loop = asyncio.get_running_loop()
    await websocket.accept()
    scan_status_clients.add(websocket)
    try:
        await send_scan_status(websocket)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        scan_status_clients.discard(websocket)
    except Exception:
        scan_status_clients.discard(websocket)


@app.websocket("/ws/signals/recompute/status")
async def signal_recompute_status_websocket(websocket: WebSocket) -> None:
    global signal_recompute_loop
    signal_recompute_loop = asyncio.get_running_loop()
    await websocket.accept()
    signal_recompute_clients.add(websocket)
    try:
        await send_signal_recompute_status(websocket)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        signal_recompute_clients.discard(websocket)
    except Exception:
        signal_recompute_clients.discard(websocket)


@app.get("/api/stocks")
def stocks(q: str = "", limit: int = Query(50, ge=1, le=200)) -> list[dict[str, object]]:
    return storage.stock_search(keyword=q, limit=limit)


@app.get("/api/stocks/{symbol}/history")
def stock_history(symbol: str, range: str = Query("daily")) -> dict[str, object]:
    if not is_mainland_hs_symbol(symbol):
        return storage.annotated_history(symbol, [])
    normalized_range = normalize_history_range(range)
    source_limit = source_limit_for_range(normalized_range)
    rows = storage.klines_for_symbol(symbol, limit=source_limit, daily_only=True)
    if normalized_range == "hourly":
        latest_trade_date = rows[-1].date if rows else None
        try:
            intraday_rows = provider.intraday_bars(symbol, limit=240, trade_date=latest_trade_date)
        except Exception:
            intraday_rows = []
        if intraday_rows:
            hourly_rows = aggregate_klines(intraday_rows, "hourly")
            annotated = [AnnotatedBar(item.kline, item.ma5, item.ma10, item.ma20, []) for item in engine.annotate(hourly_rows)]
            visible = visible_annotated_bars(annotated, HISTORY_RANGE_LIMITS["hourly"], require_ma=False)
            return storage.annotated_history(symbol, attach_stored_signals(symbol, visible))

    if not rows:
        try:
            rows = provider.daily_bars(symbol, limit=source_limit)
            storage.upsert_klines(rows)
        except Exception:
            rows = []
    if normalized_range == "hourly":
        normalized_range = "daily"
    annotated = aggregate_annotated_klines(rows, normalized_range)
    display_limit = HISTORY_RANGE_LIMITS[normalized_range]
    visible = visible_annotated_bars(annotated, display_limit)
    return storage.annotated_history(symbol, attach_period_signals(symbol, visible, rows, normalized_range))
