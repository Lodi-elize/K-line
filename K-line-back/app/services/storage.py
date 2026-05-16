from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.core.models import AnnotatedBar, KLine, Signal

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def _beijing_timestamp() -> str:
    return datetime.now(BEIJING_TZ).replace(microsecond=0).isoformat(sep=" ")


def _normalized_kline(row: KLine) -> KLine | None:
    prices = [row.open, row.high, row.low, row.close]
    if any(price <= 0 for price in prices):
        return None
    return KLine(
        symbol=row.symbol,
        date=row.date,
        open=row.open,
        high=max(prices),
        low=min(prices),
        close=row.close,
        volume=row.volume,
    )


def _clean_stock_name(value: str | None, fallback: str) -> str:
    cleaned = "".join(char for char in str(value or "").replace("\ufffd", "") if char.isprintable()).strip()
    return cleaned or fallback


def _market_module(symbol: str) -> str:
    if symbol.startswith("688"):
        return "科创板"
    if symbol.startswith("300"):
        return "创业板"
    if symbol.startswith("8"):
        return "北交所"
    if symbol.startswith("6"):
        return "沪市主板"
    if symbol.startswith("0"):
        return "深市主板"
    return "其他市场"


def _module_key(module_type: str, name: str) -> str:
    return f"{module_type}:{name}"


class Row(dict[str, Any]):
    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


class StorageCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    @property
    def lastrowid(self) -> int:
        return int(self._cursor.lastrowid)

    def fetchone(self) -> Row | None:
        row = self._cursor.fetchone()
        return self._normalize(row) if row is not None else None

    def fetchall(self) -> list[Row]:
        return [self._normalize(row) for row in self._cursor.fetchall()]

    @staticmethod
    def _normalize(row: Any) -> Row:
        return Row(dict(row))


class StorageConnection:
    def __init__(self, connection: Any, dialect: str) -> None:
        self._connection = connection
        self._dialect = dialect

    def execute(self, query: str, params: Iterable[Any] = ()) -> StorageCursor:
        cursor = self._connection.cursor()
        cursor.execute(self._sql(query), tuple(params))
        return StorageCursor(cursor)

    def executemany(self, query: str, rows: Iterable[Iterable[Any]]) -> StorageCursor:
        cursor = self._connection.cursor()
        cursor.executemany(self._sql(query), [tuple(row) for row in rows])
        return StorageCursor(cursor)

    def executescript(self, script: str) -> None:
        if self._dialect == "sqlite":
            self._connection.executescript(script)
            return
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def _sql(self, query: str) -> str:
        if self._dialect == "sqlite":
            return query
        return query.replace("?", "%s")


class Storage:
    def __init__(self, database_path: Path, database_url: str | None = None) -> None:
        self.database_path = database_path
        self.database_url = database_url
        self.dialect = "mysql" if database_url and database_url.startswith(("mysql://", "mysql+pymysql://")) else "sqlite"
        if self.dialect == "sqlite":
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[StorageConnection]:
        connection = self._connect_raw()
        try:
            yield StorageConnection(connection, self.dialect)
            connection.commit()
        finally:
            connection.close()

    def _connect_raw(self) -> Any:
        if self.dialect == "sqlite":
            connection = sqlite3.connect(self.database_path)
            connection.row_factory = sqlite3.Row
            return connection

        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError("使用 MySQL 需要先安装 PyMySQL：pip install -r requirements.txt") from exc

        parsed = urlparse(self.database_url or "")
        query = parse_qs(parsed.query)
        return pymysql.connect(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            database=parsed.path.lstrip("/"),
            charset=query.get("charset", ["utf8mb4"])[0],
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )

    @property
    def _insert_ignore(self) -> str:
        return "insert or ignore" if self.dialect == "sqlite" else "insert ignore"

    def _upsert_stocks_sql(self) -> str:
        if self.dialect == "sqlite":
            return "insert or replace into stocks(symbol, name) values(?, ?)"
        return """
            insert into stocks(symbol, name) values(?, ?)
            on duplicate key update name = values(name)
        """

    def _upsert_modules_sql(self, values_sql: str) -> str:
        conflict_sql = (
            """
            on conflict(module_key) do update set
                name = excluded.name,
                type = excluded.type,
                description = excluded.description,
                source = excluded.source
            """
            if self.dialect == "sqlite"
            else """
            on duplicate key update
                name = values(name),
                type = values(type),
                description = values(description),
                source = values(source)
            """
        )
        return f"insert into modules(module_key, name, type, description, source) {values_sql} {conflict_sql}"

    def _upsert_members_sql(self) -> str:
        if self.dialect == "sqlite":
            return """
                insert into stock_module_members(symbol, module_id, score, reason, updated_at)
                values(?, ?, 1, ?, ?)
                on conflict(symbol, module_id) do update set
                    score = excluded.score,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
            """
        return """
            insert into stock_module_members(symbol, module_id, score, reason, updated_at)
            values(?, ?, 1, ?, ?)
            on duplicate key update
                score = values(score),
                reason = values(reason),
                updated_at = values(updated_at)
        """

    def _upsert_klines_sql(self) -> str:
        if self.dialect == "sqlite":
            return """
                insert or replace into klines(symbol, trade_date, open, high, low, close, volume)
                values(?, ?, ?, ?, ?, ?, ?)
            """
        return """
            insert into klines(symbol, trade_date, open, high, low, close, volume)
            values(?, ?, ?, ?, ?, ?, ?)
            on duplicate key update
                open = values(open),
                high = values(high),
                low = values(low),
                close = values(close),
                volume = values(volume)
        """

    def _init_schema(self) -> None:
        autoincrement = "integer primary key autoincrement" if self.dialect == "sqlite" else "integer primary key auto_increment"
        symbol_text = "text" if self.dialect == "sqlite" else "varchar(16)"
        date_text = "text" if self.dialect == "sqlite" else "varchar(16)"
        key_text = "text" if self.dialect == "sqlite" else "varchar(255)"
        type_text = "text" if self.dialect == "sqlite" else "varchar(64)"
        name_text = "text" if self.dialect == "sqlite" else "varchar(255)"
        description_text = "text" if self.dialect == "sqlite" else "varchar(1000)"
        with self.connect() as db:
            db.executescript(
                f"""
                create table if not exists stocks (
                    symbol {symbol_text} primary key,
                    name {name_text} not null
                );
                create table if not exists klines (
                    symbol {symbol_text} not null,
                    trade_date {date_text} not null,
                    open real not null,
                    high real not null,
                    low real not null,
                    close real not null,
                    volume real not null,
                    primary key (symbol, trade_date)
                );
                create table if not exists signals (
                    id {autoincrement},
                    symbol {symbol_text} not null,
                    trade_date {date_text} not null,
                    signal_type {type_text} not null,
                    severity {type_text} not null,
                    title {name_text} not null,
                    description {description_text} not null,
                    close real not null,
                    ma5 real,
                    ma10 real,
                    ma20 real,
                    unique(symbol, trade_date, signal_type)
                );
                create table if not exists notification_records (
                    id {autoincrement},
                    signal_key {key_text} not null unique,
                    payload text not null,
                    created_at {key_text}
                );
                create table if not exists scan_runs (
                    id {autoincrement},
                    started_at {key_text},
                    finished_at {key_text},
                    status {type_text} not null,
                    scanned_count integer default 0,
                    signal_count integer default 0,
                    message text
                );
                create table if not exists modules (
                    id {autoincrement},
                    module_key {key_text} not null unique,
                    name {name_text} not null,
                    type {type_text} not null,
                    description {description_text} not null default '',
                    source {type_text} not null default 'system'
                );
                create table if not exists stock_module_members (
                    symbol {symbol_text} not null,
                    module_id integer not null,
                    score real default 1,
                    reason {description_text} not null default '',
                    updated_at {key_text},
                    primary key (symbol, module_id),
                    foreign key (module_id) references modules(id)
                );
                """
            )
            self._init_indexes(db)

    def _init_indexes(self, db: StorageConnection) -> None:
        indexes = [
            ("idx_signals_symbol_severity_date_id", "signals", "symbol, severity, trade_date, id"),
            ("idx_klines_symbol_date", "klines", "symbol, trade_date"),
            ("idx_stock_module_members_module_symbol", "stock_module_members", "module_id, symbol"),
        ]
        for name, table, columns in indexes:
            try:
                if self.dialect == "sqlite":
                    db.execute(f"create index if not exists {name} on {table}({columns})")
                else:
                    db.execute(f"create index {name} on {table}({columns})")
            except Exception:
                continue

    def upsert_stocks(self, stocks: list[dict[str, str]]) -> None:
        rows = [
            (row["symbol"], _clean_stock_name(row.get("name"), row["symbol"]))
            for row in stocks
            if row.get("symbol")
        ]
        with self.connect() as db:
            db.executemany(self._upsert_stocks_sql(), rows)
        self.sync_market_modules_for_symbols([symbol for symbol, _ in rows])

    def set_stock_modules(self, symbol: str, modules: list[tuple[str, str, str]], source: str = "system") -> None:
        timestamp = _beijing_timestamp()
        keys = [_module_key(module_type, name) for module_type, name, _ in modules]
        with self.connect() as db:
            for module_type, name, description in modules:
                db.execute(
                    self._upsert_modules_sql("values(?, ?, ?, ?, ?)"),
                    (_module_key(module_type, name), name, module_type, description, source),
                )
            if keys:
                placeholders = ",".join("?" for _ in keys)
                module_rows = db.execute(f"select id, name from modules where module_key in ({placeholders})", keys).fetchall()
                db.execute(
                    f"""
                    delete from stock_module_members
                    where symbol = ?
                      and module_id in (select id from modules where source = ? and module_key not in ({placeholders}))
                    """,
                    [symbol, source, *keys],
                )
                db.executemany(
                    self._upsert_members_sql(),
                    [(symbol, row["id"], f"自动归入{row['name']}", timestamp) for row in module_rows],
                )
            else:
                db.execute(
                    "delete from stock_module_members where symbol = ? and module_id in (select id from modules where source = ?)",
                    (symbol, source),
                )

    def sync_market_modules(self, symbol: str) -> None:
        self.set_stock_modules(
            symbol,
            [("market", _market_module(symbol), "按股票代码前缀自动划分市场模块。")],
        )

    def sync_market_modules_for_symbols(self, symbols: list[str]) -> None:
        if not symbols:
            return
        timestamp = _beijing_timestamp()
        module_specs: dict[str, tuple[str, str, str]] = {}
        memberships: list[tuple[str, str]] = []
        for symbol in symbols:
            specs = [("market", _market_module(symbol), "按股票代码前缀自动划分市场模块。")]
            for module_type, name, description in specs:
                key = _module_key(module_type, name)
                module_specs[key] = (module_type, name, description)
                memberships.append((symbol, key))

        with self.connect() as db:
            db.executemany(
                self._upsert_modules_sql("values(?, ?, ?, ?, 'system')"),
                [(key, name, module_type, description) for key, (module_type, name, description) in module_specs.items()],
            )
            symbols = sorted({symbol for symbol, _ in memberships})
            symbol_placeholders = ",".join("?" for _ in symbols)
            db.execute(
                f"""
                delete from stock_module_members
                where symbol in ({symbol_placeholders})
                  and module_id in (select id from modules where source = 'system' and type = 'market')
                """,
                symbols,
            )
            module_rows = db.execute(
                f"select id, module_key, name from modules where module_key in ({','.join('?' for _ in module_specs)})",
                list(module_specs.keys()),
            ).fetchall()
            module_by_key = {row["module_key"]: row for row in module_rows}
            db.executemany(
                self._upsert_members_sql(),
                [
                    (symbol, module_by_key[key]["id"], f"自动归入{module_by_key[key]['name']}", timestamp)
                    for symbol, key in memberships
                    if key in module_by_key
                ],
            )

    def replace_concept_modules(self, members: list[tuple[str, str]]) -> None:
        timestamp = _beijing_timestamp()
        normalized = [(symbol, board_name.strip()) for symbol, board_name in members if symbol and board_name.strip()]
        with self.connect() as db:
            db.execute("delete from stock_module_members where module_id in (select id from modules where source = 'akshare' and type = 'concept')")
            if not normalized:
                return
            concept_names = sorted({board_name for _, board_name in normalized})
            db.executemany(
                self._upsert_modules_sql("values(?, ?, 'concept', 'AkShare 东方财富概念板块。', 'akshare')"),
                [(_module_key("concept", name), name) for name in concept_names],
            )
            module_rows = db.execute(
                f"select id, name from modules where type = 'concept' and source = 'akshare' and name in ({','.join('?' for _ in concept_names)})",
                concept_names,
            ).fetchall()
            module_by_name = {row["name"]: row["id"] for row in module_rows}
            db.executemany(
                f"""
                {self._insert_ignore} into stock_module_members(symbol, module_id, score, reason, updated_at)
                values(?, ?, 1, ?, ?)
                """,
                [
                    (symbol, module_by_name[board_name], f"AkShare 概念板块：{board_name}", timestamp)
                    for symbol, board_name in normalized
                    if board_name in module_by_name
                ],
            )

    def upsert_concept_modules(self, members: list[tuple[str, str]], source: str = "akshare") -> None:
        timestamp = _beijing_timestamp()
        normalized = [(symbol, board_name.strip()) for symbol, board_name in members if symbol and board_name.strip()]
        if not normalized:
            return
        concept_names = sorted({board_name for _, board_name in normalized})
        with self.connect() as db:
            db.executemany(
                self._upsert_modules_sql("values(?, ?, 'concept', '同花顺概念板块。', ?)"),
                [(_module_key("concept", name), name, source) for name in concept_names],
            )
            module_rows = db.execute(
                f"select id, name from modules where type = 'concept' and source = ? and name in ({','.join('?' for _ in concept_names)})",
                [source, *concept_names],
            ).fetchall()
            module_by_name = {row["name"]: row["id"] for row in module_rows}
            db.executemany(
                self._upsert_members_sql(),
                [
                    (symbol, module_by_name[board_name], f"同花顺概念板块：{board_name}", timestamp)
                    for symbol, board_name in normalized
                    if board_name in module_by_name
                ],
            )

    def upsert_klines(self, rows: list[KLine]) -> None:
        normalized_rows = [item for row in rows if (item := _normalized_kline(row)) is not None]
        with self.connect() as db:
            db.executemany(
                self._upsert_klines_sql(),
                [(row.symbol, row.date, row.open, row.high, row.low, row.close, row.volume) for row in normalized_rows],
            )

    def upsert_signals(self, signals: list[Signal]) -> int:
        inserted = 0
        with self.connect() as db:
            for signal in signals:
                cursor = db.execute(
                    f"""
                    {self._insert_ignore} into signals(symbol, trade_date, signal_type, severity, title, description, close, ma5, ma10, ma20)
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
            db.execute(
                f"{self._insert_ignore} into notification_records(signal_key, payload, created_at) values(?, ?, ?)",
                (key, json.dumps(signal.__dict__, default=str), _beijing_timestamp()),
            )

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

    def stock_statuses(
        self,
        limit: int = 10000,
        signal_type: str | None = None,
        severity: str | None = None,
        module_id: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if signal_type:
            clauses.append("latest_signal.signal_type = ?")
            params.append(signal_type)
        if severity:
            if severity == "normal":
                clauses.append("latest_signal.id is null")
            else:
                clauses.append("latest_signal.severity = ?")
                params.append(severity)
        if module_id:
            clauses.append(
                """
                exists (
                    select 1
                    from stock_module_members member
                    where member.symbol = stocks.symbol
                      and member.module_id = ?
                )
                """
            )
            params.append(module_id)
        query = """
            select
                stocks.symbol,
                stocks.name,
                latest_signal.id,
                coalesce(latest_signal.trade_date, latest_kline.trade_date, '') as trade_date,
                coalesce(latest_signal.signal_type, 'normal') as signal_type,
                coalesce(latest_signal.severity, 'normal') as severity,
                coalesce(latest_signal.title, '通常') as title,
                coalesce(latest_signal.description, '当前没有进场或离场信号。') as description,
                coalesce(latest_signal.close, latest_kline.close) as close,
                latest_signal.ma5,
                latest_signal.ma10,
                latest_signal.ma20
            from stocks
            left join signals latest_signal
                on latest_signal.symbol = stocks.symbol
               and latest_signal.severity in ('entry', 'exit')
               and latest_signal.id = (
                    select candidate.id
                    from signals candidate
                    where candidate.symbol = stocks.symbol
                      and candidate.severity in ('entry', 'exit')
                    order by candidate.trade_date desc, candidate.id desc
                    limit 1
               )
            left join klines latest_kline
                on latest_kline.symbol = stocks.symbol
               and latest_kline.trade_date = (
                    select max(candidate.trade_date)
                    from klines candidate
                    where candidate.symbol = stocks.symbol
               )
        """
        if clauses:
            query += " where " + " and ".join(clauses)
        query += """
            order by
                case when latest_signal.id is null then 1 else 0 end,
                latest_signal.trade_date desc,
                latest_signal.id desc,
                stocks.symbol asc
            limit ?
        """
        params.append(limit)
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(query, params).fetchall()]
        for row in rows:
            row["name"] = _clean_stock_name(row.get("name"), row["symbol"])
        modules_by_symbol = self.modules_for_symbols([row["symbol"] for row in rows])
        for row in rows:
            row["modules"] = modules_by_symbol.get(row["symbol"], [])
        return rows

    def modules(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                select
                    module.id,
                    module.module_key,
                    module.name,
                    module.type,
                    module.description,
                    module.source,
                    count(member.symbol) as stock_count
                from modules module
                left join stock_module_members member on member.module_id = module.id
                group by module.id, module.module_key, module.name, module.type, module.description, module.source
                order by
                    case module.type
                        when 'market' then 1
                        when 'industry' then 2
                        when 'concept' then 3
                        when 'custom' then 4
                        else 9
                    end,
                    module.name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def modules_for_symbols(self, symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not symbols:
            return {}
        placeholders = ",".join("?" for _ in symbols)
        with self.connect() as db:
            rows = db.execute(
                f"""
                select member.symbol, module.name, module.type, module.source, member.score, member.reason
                from stock_module_members member
                join modules module on module.id = member.module_id
                where member.symbol in ({placeholders})
                order by
                    case module.type
                        when 'market' then 1
                        when 'industry' then 2
                        when 'concept' then 3
                        when 'custom' then 4
                        else 9
                    end,
                    module.name
                """,
                symbols,
            ).fetchall()
        result: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
        for row in rows:
            result[row["symbol"]].append(
                {
                    "name": row["name"],
                    "type": row["type"],
                    "source": row["source"],
                    "score": row["score"],
                    "reason": row["reason"],
                }
            )
        return result

    def stock_search(self, keyword: str = "", limit: int = 50) -> list[dict[str, Any]]:
        pattern = f"%{keyword}%"
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("select * from stocks where symbol like ? or name like ? order by symbol limit ?", (pattern, pattern, limit)).fetchall()]
        for row in rows:
            row["name"] = _clean_stock_name(row.get("name"), row["symbol"])
        return rows

    def stock_name(self, symbol: str) -> str:
        with self.connect() as db:
            row = db.execute("select name from stocks where symbol = ? limit 1", (symbol,)).fetchone()
        return _clean_stock_name(row["name"] if row else None, symbol)

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
            cursor = db.execute("insert into scan_runs(started_at, status) values(?, 'running')", (_beijing_timestamp(),))
            return int(cursor.lastrowid)

    def finish_scan(self, run_id: int, status: str, scanned_count: int, signal_count: int, message: str = "") -> None:
        with self.connect() as db:
            db.execute(
                "update scan_runs set finished_at = ?, status = ?, scanned_count = ?, signal_count = ?, message = ? where id = ?",
                (_beijing_timestamp(), status, scanned_count, signal_count, message, run_id),
            )

    def update_scan_progress(self, run_id: int, scanned_count: int, signal_count: int, message: str = "") -> None:
        with self.connect() as db:
            db.execute(
                "update scan_runs set scanned_count = ?, signal_count = ?, message = ? where id = ?",
                (scanned_count, signal_count, message, run_id),
            )

    def mark_interrupted_scans(self, message: str = "服务重启，扫描已中断。") -> None:
        with self.connect() as db:
            db.execute(
                "update scan_runs set finished_at = ?, status = 'failed', message = ? where status = 'running'",
                (_beijing_timestamp(), message),
            )

    def annotated_history(self, symbol: str, annotated: list[AnnotatedBar]) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "name": self.stock_name(symbol),
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
