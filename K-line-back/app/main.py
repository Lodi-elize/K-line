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
from app.providers.mootdx_provider import MootdxProvider
from app.services.notifier import DatabaseNotifier
from app.services.scanner import ScannerService
from app.services.storage import Storage


storage = Storage(settings.database_path, settings.database_url)
storage.mark_interrupted_scans()
storage.prune_non_hs_stocks()
storage.reclassify_obsolete_entry_signals({SignalType.DOUBLE_LIMIT_UP_TEN_MA_PULLBACK.value})
storage.sync_market_modules_for_all_stocks()
storage.backfill_chain_modules_from_concepts()
engine = SignalEngine(settings.thresholds)


def create_provider():
    if os.getenv("KLINE_PROVIDER", "").lower() == "fake":
        from app.providers.fake import FakeMarketDataProvider

        return FakeMarketDataProvider()
    return MootdxProvider()


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
scanner = ScannerService(provider, storage, engine, notifier, settings.max_scan_symbols, board_provider)
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


async def send_module_sync_status(websocket: WebSocket) -> None:
    await websocket.send_json(module_sync_state)


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
                    "message": f"正在同步东财概念模块：{current}/{total}，当前：{board_name}，已写入数据库。",
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    global module_sync_loop
    module_sync_loop = asyncio.get_running_loop()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
    threading.Thread(target=scanner.run_scan, args=(run_id,), daemon=True).start()
    return {"status": "running", "scanned_count": 0, "signal_count": 0, "message": "扫描已在后台启动。"}


@app.get("/api/signals")
def latest_signals(
    limit: int = Query(200, ge=1, le=1000),
    signal_type: str | None = None,
    severity: str | None = None,
) -> list[dict[str, object]]:
    return storage.latest_signals(limit=limit, signal_type=signal_type, severity=severity)


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


@app.get("/api/stocks")
def stocks(q: str = "", limit: int = Query(50, ge=1, le=200)) -> list[dict[str, object]]:
    return storage.stock_search(keyword=q, limit=limit)


@app.get("/api/stocks/{symbol}/history")
def stock_history(symbol: str, range: str = Query("daily")) -> dict[str, object]:
    if not is_mainland_hs_symbol(symbol):
        return storage.annotated_history(symbol, [])
    normalized_range = normalize_history_range(range)
    source_limit = source_limit_for_range(normalized_range)
    rows = storage.klines_for_symbol(symbol, limit=source_limit, daily_only=normalized_range != "daily")
    if normalized_range == "daily":
        latest_trade_date = rows[-1].date if rows else None
        intraday_rows = provider.intraday_bars(symbol, limit=240, trade_date=latest_trade_date)
        if intraday_rows:
            annotated = [AnnotatedBar(item.kline, item.ma5, item.ma10, item.ma20, []) for item in engine.annotate(intraday_rows)]
            return storage.annotated_history(symbol, attach_stored_signals(symbol, annotated))

    if not rows:
        rows = provider.daily_bars(symbol, limit=source_limit)
        storage.upsert_klines(rows)
    annotated = engine.annotate(rows)
    return storage.annotated_history(symbol, attach_stored_signals(symbol, annotated[-HISTORY_RANGE_LIMITS[normalized_range]:]))
