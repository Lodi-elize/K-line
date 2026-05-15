from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from typing import Any

from app.core.models import AnnotatedBar, KLine, Signal


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                create table if not exists stocks (
                    symbol text primary key,
                    name text not null
                );
                create table if not exists klines (
                    symbol text not null,
                    trade_date text not null,
                    open real not null,
                    high real not null,
                    low real not null,
                    close real not null,
                    volume real not null,
                    primary key (symbol, trade_date)
                );
                create table if not exists signals (
                    id integer primary key autoincrement,
                    symbol text not null,
                    trade_date text not null,
                    signal_type text not null,
                    severity text not null,
                    title text not null,
                    description text not null,
                    close real not null,
                    ma5 real,
                    ma10 real,
                    ma20 real,
                    unique(symbol, trade_date, signal_type)
                );
                create table if not exists notification_records (
                    id integer primary key autoincrement,
                    signal_key text not null unique,
                    payload text not null,
                    created_at text default current_timestamp
                );
                create table if not exists scan_runs (
                    id integer primary key autoincrement,
                    started_at text default current_timestamp,
                    finished_at text,
                    status text not null,
                    scanned_count integer default 0,
                    signal_count integer default 0,
                    message text
                );
                """
            )

    def upsert_stocks(self, stocks: list[dict[str, str]]) -> None:
        with self.connect() as db:
            db.executemany("insert or replace into stocks(symbol, name) values(?, ?)", [(row["symbol"], row.get("name") or row["symbol"]) for row in stocks])

    def upsert_klines(self, rows: list[KLine]) -> None:
        with self.connect() as db:
            db.executemany(
                """
                insert or replace into klines(symbol, trade_date, open, high, low, close, volume)
                values(?, ?, ?, ?, ?, ?, ?)
                """,
                [(row.symbol, row.date, row.open, row.high, row.low, row.close, row.volume) for row in rows],
            )

    def upsert_signals(self, signals: list[Signal]) -> int:
        inserted = 0
        with self.connect() as db:
            for signal in signals:
                cursor = db.execute(
                    """
                    insert or ignore into signals(symbol, trade_date, signal_type, severity, title, description, close, ma5, ma10, ma20)
                    values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal.symbol,
                        signal.trade_date,
                        signal.signal_type.value,
                        signal.severity.value,
                        signal.title,
                        signal.description,
                        signal.close,
                        signal.ma5,
                        signal.ma10,
                        signal.ma20,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def record_notification(self, signal: Signal) -> None:
        key = f"{signal.symbol}:{signal.trade_date}:{signal.signal_type.value}"
        with self.connect() as db:
            db.execute("insert or ignore into notification_records(signal_key, payload) values(?, ?)", (key, json.dumps(signal.__dict__, default=str)))

    def latest_signals(self, limit: int = 200, signal_type: str | None = None, severity: str | None = None) -> list[dict[str, Any]]:
        query = "select * from signals"
        clauses: list[str] = []
        params: list[Any] = []
        if signal_type:
            clauses.append("signal_type = ?")
            params.append(signal_type)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if clauses:
            query += " where " + " and ".join(clauses)
        query += " order by trade_date desc, id desc limit ?"
        params.append(limit)
        with self.connect() as db:
            return [dict(row) for row in db.execute(query, params).fetchall()]

    def stock_search(self, keyword: str = "", limit: int = 50) -> list[dict[str, Any]]:
        pattern = f"%{keyword}%"
        with self.connect() as db:
            return [dict(row) for row in db.execute("select * from stocks where symbol like ? or name like ? order by symbol limit ?", (pattern, pattern, limit)).fetchall()]

    def klines_for_symbol(self, symbol: str, limit: int = 160) -> list[KLine]:
        with self.connect() as db:
            rows = db.execute(
                "select * from klines where symbol = ? order by trade_date desc limit ?",
                (symbol, limit),
            ).fetchall()
        return [
            KLine(row["symbol"], row["trade_date"], row["open"], row["high"], row["low"], row["close"], row["volume"])
            for row in reversed(rows)
        ]

    def latest_scan(self) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("select * from scan_runs order by id desc limit 1").fetchone()
            return dict(row) if row else None

    def start_scan(self) -> int:
        with self.connect() as db:
            cursor = db.execute("insert into scan_runs(status) values('running')")
            return int(cursor.lastrowid)

    def finish_scan(self, run_id: int, status: str, scanned_count: int, signal_count: int, message: str = "") -> None:
        with self.connect() as db:
            db.execute(
                "update scan_runs set finished_at = current_timestamp, status = ?, scanned_count = ?, signal_count = ?, message = ? where id = ?",
                (status, scanned_count, signal_count, message, run_id),
            )

    def annotated_history(self, symbol: str, annotated: list[AnnotatedBar]) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "bars": [
                {
                    "date": item.kline.date,
                    "open": item.kline.open,
                    "high": item.kline.high,
                    "low": item.kline.low,
                    "close": item.kline.close,
                    "volume": item.kline.volume,
                    "ma5": item.ma5,
                    "ma10": item.ma10,
                    "ma20": item.ma20,
                    "signals": [
                        {
                            "signal_type": signal.signal_type.value,
                            "severity": signal.severity.value,
                            "title": signal.title,
                            "description": signal.description,
                        }
                        for signal in item.signals
                    ],
                }
                for item in annotated
            ],
        }
