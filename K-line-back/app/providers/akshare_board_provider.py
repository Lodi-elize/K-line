from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from app.core.stock_scope import is_mainland_hs_symbol

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - provided by akshare dependencies in normal installs
    requests = None
    BeautifulSoup = None


@dataclass(frozen=True)
class BoardMember:
    symbol: str
    board_name: str


BOARD_NAME_COLUMNS = ("板块名称", "name", "名称", "概念名称")
BOARD_CODE_COLUMNS = ("板块代码", "code", "代码")
STOCK_CODE_COLUMNS = ("代码", "股票代码", "symbol", "code", "证券代码")
THS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36"
    ),
}


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    if "." in text:
        left, right = text.split(".", 1)
        if left.isdigit() and not right.strip("0"):
            text = left
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) >= 6:
        return digits[-6:]
    return digits.zfill(6) if digits else ""


def _first_text(row: dict[str, Any], columns: tuple[str, ...]) -> str:
    for column in columns:
        value = row.get(column)
        if value is not None:
            text = str(value).strip()
            if text and text.lower() != "nan":
                return text
    return ""


class AkshareBoardProvider:
    def __init__(self, retry_count: int = 3, retry_delay: float = 0.8, request_interval: float = 0.08) -> None:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("akshare is not installed. Install K-line-back requirements first.") from exc
        self.ak = ak
        self.retry_count = max(1, retry_count)
        self.retry_delay = max(0, retry_delay)
        self.request_interval = max(0, request_interval)

    def concept_members(
        self,
        progress: Callable[[str, int, int, int, list[BoardMember]], None] | None = None,
    ) -> list[BoardMember]:
        boards = self._concept_boards()
        records = boards.to_dict("records") if hasattr(boards, "to_dict") else list(boards)
        members: list[BoardMember] = []
        total = len(records)
        for index, board in enumerate(records, start=1):
            board_name = _first_text(board, BOARD_NAME_COLUMNS)
            board_code = _first_text(board, BOARD_CODE_COLUMNS)
            if not board_name:
                continue
            try:
                stock_rows = self._eastmoney_concept_stocks(board_code or board_name)
            except Exception:
                continue
            board_members: list[BoardMember] = []
            for row in stock_rows:
                symbol = _stock_code(_first_text(row, STOCK_CODE_COLUMNS))
                if is_mainland_hs_symbol(symbol):
                    member = BoardMember(symbol=symbol, board_name=board_name)
                    members.append(member)
                    board_members.append(member)
            if progress:
                progress(board_name, index, total, len(members), board_members)
        return members

    def _concept_boards(self) -> Any:
        try:
            return self._call_with_retries("东方财富概念板块列表", self.ak.stock_board_concept_name_em)
        except Exception:
            if not hasattr(self.ak, "stock_board_concept_name_ths"):
                raise
            return self._call_with_retries("同花顺概念板块列表", self.ak.stock_board_concept_name_ths)

    def _eastmoney_concept_stocks(self, board_symbol: str) -> list[dict[str, Any]]:
        if board_symbol.isdigit():
            return self._ths_concept_stocks(board_symbol)
        request_interval = getattr(self, "request_interval", 0.08)
        if request_interval:
            time.sleep(request_interval)
        stocks = self._call_with_retries(
            f"东方财富概念成分股 {board_symbol}",
            lambda: self.ak.stock_board_concept_cons_em(symbol=board_symbol),
        )
        return stocks.to_dict("records") if hasattr(stocks, "to_dict") else list(stocks)

    def _ths_concept_stocks(self, board_code: str) -> list[dict[str, Any]]:
        if requests is None or BeautifulSoup is None:
            raise RuntimeError("同花顺概念备用源需要 requests 和 beautifulsoup4")

        rows: list[dict[str, Any]] = []
        total_pages = 1
        page = 1
        while page <= total_pages:
            url = (
                f"http://q.10jqka.com.cn/gn/detail/code/{board_code}/"
                if page == 1
                else f"http://q.10jqka.com.cn/gn/detail/code/{board_code}/page/{page}/"
            )
            try:
                html = self._call_with_retries(f"同花顺概念成分股 {board_code} 第 {page} 页", lambda url=url: self._get_text(url))
            except Exception:
                if rows:
                    break
                raise
            soup = BeautifulSoup(html, "lxml")
            table = soup.find("table", class_="m-table")
            if table is None:
                break
            for tr in table.find_all("tr"):
                cells = [cell.get_text(strip=True) for cell in tr.find_all("td")]
                if len(cells) >= 3:
                    rows.append({"代码": cells[1], "名称": cells[2]})
            page_info = soup.find("span", class_="page_info")
            if page_info:
                parts = page_info.get_text(strip=True).split("/")
                if len(parts) == 2 and parts[1].isdigit():
                    total_pages = int(parts[1])
            page += 1
        return rows

    def _get_text(self, url: str) -> str:
        if requests is None:
            raise RuntimeError("requests is not installed")
        response = requests.get(url, headers=THS_HEADERS, timeout=12)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        return response.text

    def _call_with_retries(self, label: str, call: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        retry_count = getattr(self, "retry_count", 3)
        retry_delay = getattr(self, "retry_delay", 0.8)
        for attempt in range(1, retry_count + 1):
            try:
                return call()
            except Exception as exc:
                last_error = exc
                if attempt >= retry_count:
                    break
                if retry_delay:
                    time.sleep(retry_delay * attempt)
        raise RuntimeError(f"{label}请求失败，已重试 {retry_count} 次：{last_error}") from last_error
