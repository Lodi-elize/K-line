from __future__ import annotations

import os
import time

os.environ["KLINE_PROVIDER"] = "fake"

from fastapi.testclient import TestClient

from app.core.models import KLine
from app.main import app
from app.services.storage import Storage


client = TestClient(app)


def test_health_and_config() -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    config = client.get("/api/config").json()
    assert config["thresholds"]


def test_manual_scan_and_history() -> None:
    result = client.post("/api/scan/run").json()
    assert result["status"] in {"running", "success", "failed"}
    status = None
    for _ in range(20):
        status = client.get("/api/scan/status").json()
        if status and status["status"] != "running":
            break
        time.sleep(0.1)
    assert status is not None
    assert status["status"] in {"success", "failed"}
    assert status["started_at"].endswith("+08:00")
    assert status["finished_at"].endswith("+08:00")

    history = client.get("/api/stocks/600001/history").json()
    assert history["symbol"] == "600001"
    assert history["name"]
    assert history["bars"]

    signals = client.get("/api/signals").json()
    assert isinstance(signals, list)

    statuses = client.get("/api/stock-statuses").json()
    assert statuses
    assert {"symbol", "name", "severity", "title"} <= set(statuses[0])
    assert statuses[0]["modules"]
    module_types = {module["type"] for module in statuses[0]["modules"]}
    assert "signal" not in module_types

    modules = client.get("/api/modules").json()
    assert modules
    assert {"id", "name", "type", "stock_count"} <= set(modules[0])
    filtered_statuses = client.get(f"/api/stock-statuses?module_id={modules[0]['id']}").json()
    assert filtered_statuses
    assert all(any(module["name"] == modules[0]["name"] for module in status["modules"]) for status in filtered_statuses)

    sync_status = client.get("/api/modules/sync/status").json()
    assert sync_status["status"] in {"idle", "running", "success", "failed"}


def test_storage_normalizes_kline_ohlc(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_klines([KLine("600001", "2026-05-15", open=10, high=8, low=12, close=11, volume=100)])

    rows = storage.klines_for_symbol("600001", limit=1)
    assert rows[0].high == 12
    assert rows[0].low == 8


def test_storage_replaces_akshare_concept_modules(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_stocks([{"symbol": "600001", "name": "样例股份"}])
    storage.replace_concept_modules([("600001", "人工智能")])

    modules = storage.modules_for_symbols(["600001"])["600001"]
    assert any(module["type"] == "concept" and module["name"] == "人工智能" for module in modules)
    assert not any(module["type"] == "signal" for module in modules)
