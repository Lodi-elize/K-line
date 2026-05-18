from __future__ import annotations

import os
import time
from typing import Any

os.environ["KLINE_PROVIDER"] = "fake"
os.environ.pop("KLINE_DATABASE_URL", None)

from fastapi.testclient import TestClient

from app.core.history_range import HISTORY_RANGE_LIMITS, normalize_history_range, source_limit_for_range
from app.core.models import KLine, Signal, SignalSeverity, SignalType
from app.core.config import settings
from app.main import app
from app.providers.akshare_board_provider import AkshareBoardProvider
from app.providers.mootdx_provider import MootdxProvider
from app.services.storage import Storage


client = TestClient(app)


class FakeFrame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, Any]]:
        assert orient == "records"
        return self.rows


def test_health_and_config() -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    config = client.get("/api/config").json()
    assert config["thresholds"]


def test_mootdx_provider_keeps_symbol_from_own_market() -> None:
    class FakeMootdxClient:
        def stocks(self, market: int = 1) -> FakeFrame:
            if market == 0:
                return FakeFrame(
                    [
                        {"code": "000062", "name": "深圳华强"},
                        {"code": "300001", "name": "创业样例"},
                        {"code": "395001", "name": "主板Ａ股"},
                    ]
                )
            return FakeFrame(
                [
                    {"code": "000062", "name": "上证沪企"},
                    {"code": "600001", "name": "沪市样例"},
                ]
            )

    provider = MootdxProvider.__new__(MootdxProvider)
    provider.client = FakeMootdxClient()

    rows = provider.list_symbols()
    by_symbol = {row["symbol"]: row["name"] for row in rows}

    assert by_symbol["000062"] == "深圳华强"
    assert by_symbol["300001"] == "创业样例"
    assert by_symbol["600001"] == "沪市样例"
    assert "395001" not in by_symbol


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


def test_storage_can_return_one_daily_kline_per_trade_day(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_klines(
        [
            KLine("600001", "2026-05-14", open=10, high=11, low=9, close=10.5, volume=100),
            KLine("600001", "2026-05-14 15:00", open=10, high=11, low=9, close=10.6, volume=101),
            KLine("600001", "2026-05-15", open=11, high=12, low=10, close=11.5, volume=200),
            KLine("600001", "2026-05-15 15:00", open=11, high=12, low=10, close=11.6, volume=201),
        ]
    )

    rows = storage.klines_for_symbol("600001", limit=22, daily_only=True)

    assert [row.date for row in rows] == ["2026-05-14 15:00", "2026-05-15 15:00"]
    assert [row.close for row in rows] == [10.6, 11.6]


def test_storage_replaces_akshare_concept_modules(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_stocks([{"symbol": "600001", "name": "样例股份"}])
    storage.upsert_concept_modules([("600001", "CPO概念"), ("600001", "半导体概念")])

    modules = storage.modules_for_symbols(["600001"])["600001"]
    assert any(module["type"] == "concept" and module["name"] == "CPO概念" for module in modules)
    assert any(module["type"] == "chain" and module["name"] == "CPO产业链" for module in modules)
    assert any(module["type"] == "chain" and module["name"] == "AI算力产业链" for module in modules)
    assert any(module["type"] == "chain" and module["name"] == "半导体产业链" for module in modules)
    assert not any(module["type"] == "signal" for module in modules)


def test_akshare_board_provider_uses_eastmoney_concept_source(monkeypatch) -> None:
    class FakeFrame:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self.rows = rows

        def to_dict(self, orient: str) -> list[dict[str, object]]:
            assert orient == "records"
            return self.rows

    class FakeAkshare:
        def stock_board_concept_name_em(self) -> FakeFrame:
            return FakeFrame(
                [
                    {"板块名称": "CPO概念", "板块代码": "BK1234"},
                    {"板块名称": "创新药", "板块代码": "BK5678"},
                ]
            )

        def stock_board_concept_cons_em(self, symbol: str) -> FakeFrame:
            rows = {
                "BK1234": [{"代码": "600001"}, {"代码": "830001"}],
                "BK5678": [{"代码": 300123.0}],
            }
            return FakeFrame(rows[symbol])

    provider = AkshareBoardProvider.__new__(AkshareBoardProvider)
    provider.ak = FakeAkshare()
    progress_calls: list[tuple[str, int, int, int]] = []

    members = provider.concept_members(
        lambda board_name, current, total, count, board_members: progress_calls.append((board_name, current, total, len(board_members)))
    )

    assert [(member.symbol, member.board_name) for member in members] == [("600001", "CPO概念"), ("300123", "创新药")]
    assert progress_calls == [("CPO概念", 1, 2, 1), ("创新药", 2, 2, 1)]


def test_storage_backfills_chain_modules_from_existing_concepts(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_stocks([{"symbol": "600001", "name": "样例股份"}])
    storage.upsert_concept_modules([("600001", "创新药概念")])

    with storage.connect() as db:
        db.execute("delete from stock_module_members where module_id in (select id from modules where type = 'chain')")
        db.execute("delete from modules where type = 'chain'")

    assert storage.backfill_chain_modules_from_concepts() > 0

    modules = storage.modules_for_symbols(["600001"])["600001"]
    assert any(module["type"] == "chain" and module["name"] == "创新药产业链" for module in modules)


def test_storage_prunes_non_hs_stocks(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_stocks(
        [
            {"symbol": "600001", "name": "沪市样例"},
            {"symbol": "000001", "name": "深市样例"},
            {"symbol": "830001", "name": "北交样例"},
        ]
    )
    storage.upsert_concept_modules([("600001", "CPO概念"), ("830001", "创新药概念")])
    storage.upsert_klines(
        [
            KLine("600001", "2026-05-15", open=10, high=11, low=9, close=10.5, volume=100),
            KLine("830001", "2026-05-15", open=10, high=11, low=9, close=10.5, volume=100),
        ]
    )
    with storage.connect() as db:
        db.execute("insert into stocks(symbol, name) values(?, ?)", ("830001", "北交残留"))
        db.execute(
            "insert into klines(symbol, trade_date, open, high, low, close, volume) values(?, ?, ?, ?, ?, ?, ?)",
            ("830001", "2026-05-15", 10, 11, 9, 10.5, 100),
        )

    assert storage.prune_non_hs_stocks() == 1
    assert all(not row["symbol"].startswith("8") for row in storage.stock_statuses())
    assert not storage.stock_search("830001")
    assert storage.klines_for_symbol("830001") == []

    module_symbols = storage.modules_for_symbols(["600001", "830001"])
    assert module_symbols["600001"]
    assert module_symbols["830001"] == []


def test_storage_write_paths_ignore_non_hs_symbols(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_stocks([{"symbol": "830001", "name": "北交样例"}, {"symbol": "600001", "name": "沪市样例"}])
    storage.set_stock_modules("830001", [("custom", "非沪深模块", "不应落库")])
    storage.upsert_concept_modules([("830001", "CPO概念")])
    storage.upsert_klines([KLine("830001", "2026-05-15", open=10, high=11, low=9, close=10, volume=100)])
    signal = Signal("830001", "2026-05-15", SignalType.DOUBLE_LIMIT_UP_TEN_MA_PULLBACK, SignalSeverity.ENTRY, "非沪深信号", "不应落库", 10, None, None, None)
    assert storage.upsert_signals([signal]) == 0
    storage.record_notification(signal)

    with storage.connect() as db:
        assert db.execute("select count(*) as count from stocks where symbol = ?", ("830001",)).fetchone()["count"] == 0
        assert db.execute("select count(*) as count from klines where symbol = ?", ("830001",)).fetchone()["count"] == 0
        assert db.execute("select count(*) as count from signals where symbol = ?", ("830001",)).fetchone()["count"] == 0
        assert db.execute("select count(*) as count from stock_module_members where symbol = ?", ("830001",)).fetchone()["count"] == 0
        assert db.execute("select count(*) as count from notification_records").fetchone()["count"] == 0
    assert storage.stock_search("830001") == []


def test_storage_reclassifies_obsolete_entry_signals(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_stocks([{"symbol": "600001", "name": "沪市样例"}])
    old_signal = Signal("600001", "2026-05-15", SignalType.GOLDEN_CROSS, SignalSeverity.ENTRY, "旧进场", "旧规则", 10, None, None, None)
    new_signal = Signal("600001", "2026-05-16", SignalType.DOUBLE_LIMIT_UP_TEN_MA_PULLBACK, SignalSeverity.ENTRY, "新进场", "新规则", 10, None, None, None)
    storage.upsert_signals([old_signal, new_signal])

    assert storage.reclassify_obsolete_entry_signals({SignalType.DOUBLE_LIMIT_UP_TEN_MA_PULLBACK.value}) == 1
    signals = {row["signal_type"]: row["severity"] for row in storage.latest_signals(limit=10)}

    assert signals["golden_cross"] == "watch"
    assert signals["double_limit_up_ten_ma_pullback"] == "entry"


def test_storage_updates_existing_signal_on_conflict(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_stocks([{"symbol": "600001", "name": "沪市样例"}])
    original = Signal("600001", "2026-05-15", SignalType.GOLDEN_CROSS, SignalSeverity.ENTRY, "旧进场", "旧规则", 10, None, None, None)
    updated = Signal("600001", "2026-05-15", SignalType.GOLDEN_CROSS, SignalSeverity.WATCH, "观察", "新规则", 10, None, None, None)
    storage.upsert_signals([original])
    storage.upsert_signals([updated])

    [signal] = storage.latest_signals(limit=1)
    assert signal["severity"] == "watch"
    assert signal["title"] == "观察"


def test_storage_loads_signals_for_history_dates(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_stocks([{"symbol": "600001", "name": "沪市样例"}])
    entry = Signal("600001", "2026-05-15", SignalType.DOUBLE_LIMIT_UP_TEN_MA_PULLBACK, SignalSeverity.ENTRY, "进场", "进场规则", 10, None, None, None)
    watch = Signal("600001", "2026-05-16 10:30", SignalType.FIVE_MA_TURN_UP, SignalSeverity.WATCH, "观察", "观察规则", 11, None, None, None)
    storage.upsert_signals([entry, watch])

    signals = storage.signals_for_symbol_dates("600001", ["2026-05-15", "2026-05-16 14:30"])

    assert [signal.title for signal in signals["2026-05-15"]] == ["进场"]
    assert [signal.title for signal in signals["2026-05-16"]] == ["观察"]


def test_storage_groups_all_three_prefix_symbols_as_chinext(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.upsert_stocks([{"symbol": "301001", "name": "创业板样例"}])

    modules = storage.modules_for_symbols(["301001"])["301001"]
    assert any(module["type"] == "market" and module["name"] == "创业板" for module in modules)
    assert not any(module["type"] == "market" and module["name"] == "其他市场" for module in modules)


def test_remote_database_connection_when_configured() -> None:
    if not settings.database_url:
        return

    storage = Storage(settings.database_path, settings.database_url)
    latest_scan = storage.latest_scan()
    modules = storage.modules()
    statuses = storage.stock_statuses(limit=20)

    assert latest_scan is None or "status" in latest_scan
    assert isinstance(modules, list)
    assert isinstance(statuses, list)
    assert all(status["symbol"].startswith(("0", "3", "6")) for status in statuses)


def test_history_range_normalization_and_limits() -> None:
    assert normalize_history_range("day") == "daily"
    assert normalize_history_range("month") == "monthly"
    assert normalize_history_range("year") == "yearly"
    assert HISTORY_RANGE_LIMITS == {"daily": 1, "monthly": 22, "yearly": 250}
    assert source_limit_for_range("daily") >= 31
    assert source_limit_for_range("monthly") >= 52
    assert source_limit_for_range("yearly") >= 280


def test_history_endpoint_uses_intraday_for_daily_and_daily_windows_for_longer_ranges() -> None:
    daily = client.get("/api/stocks/600001/history?range=daily").json()
    monthly = client.get("/api/stocks/600001/history?range=monthly").json()
    yearly = client.get("/api/stocks/600001/history?range=yearly").json()

    assert len(daily["bars"]) > 1
    assert " " in daily["bars"][0]["date"]
    assert len(monthly["bars"]) == 22
    assert 22 < len(yearly["bars"]) <= 250
    assert monthly["bars"] == yearly["bars"][-22:]
