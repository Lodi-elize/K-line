from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.signal_engine import SignalEngine
from app.providers.fake import FakeMarketDataProvider
from app.providers.mootdx_provider import MootdxProvider
from app.services.notifier import DatabaseNotifier
from app.services.scanner import ScannerService
from app.services.storage import Storage


storage = Storage(settings.database_path)
engine = SignalEngine(settings.thresholds)


def create_provider():
    if os.getenv("KLINE_PROVIDER", "").lower() == "fake":
        return FakeMarketDataProvider()
    try:
        return MootdxProvider()
    except Exception:
        return FakeMarketDataProvider()


provider = create_provider()
notifier = DatabaseNotifier(storage)
scanner = ScannerService(provider, storage, engine, notifier, settings.max_scan_symbols)
try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None

scheduler = BackgroundScheduler(timezone="Asia/Shanghai") if BackgroundScheduler else None

def start_scheduler() -> None:
    if scheduler and not scheduler.running:
        scheduler.add_job(scanner.run_scan, "cron", day_of_week="mon-fri", hour=18, minute=0, id="daily_scan", replace_existing=True)
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
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
    return scanner.run_scan().__dict__


@app.get("/api/signals")
def latest_signals(
    limit: int = Query(200, ge=1, le=1000),
    signal_type: str | None = None,
    severity: str | None = None,
) -> list[dict[str, object]]:
    return storage.latest_signals(limit=limit, signal_type=signal_type, severity=severity)


@app.get("/api/stocks")
def stocks(q: str = "", limit: int = Query(50, ge=1, le=200)) -> list[dict[str, object]]:
    return storage.stock_search(keyword=q, limit=limit)


@app.get("/api/stocks/{symbol}/history")
def stock_history(symbol: str, limit: int = Query(160, ge=30, le=300)) -> dict[str, object]:
    rows = storage.klines_for_symbol(symbol, limit=limit)
    if not rows:
        rows = provider.daily_bars(symbol, limit=limit)
        storage.upsert_klines(rows)
    return storage.annotated_history(symbol, engine.annotate(rows))
