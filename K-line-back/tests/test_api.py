from __future__ import annotations

import os

os.environ["KLINE_PROVIDER"] = "fake"

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_and_config() -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    config = client.get("/api/config").json()
    assert config["thresholds"]


def test_manual_scan_and_history() -> None:
    result = client.post("/api/scan/run").json()
    assert result["status"] in {"success", "failed"}
    status = client.get("/api/scan/status").json()
    assert status is not None

    history = client.get("/api/stocks/600001/history").json()
    assert history["symbol"] == "600001"
    assert history["bars"]

    signals = client.get("/api/signals").json()
    assert isinstance(signals, list)
