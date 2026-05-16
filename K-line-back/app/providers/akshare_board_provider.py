from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import re
from typing import Any, Callable

import pandas as pd
import requests


@dataclass(frozen=True)
class BoardMember:
    symbol: str
    board_name: str


def _stock_code(value: Any) -> str:
    return str(value or "").strip().zfill(6)


class AkshareBoardProvider:
    def __init__(self) -> None:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("akshare is not installed. Install K-line-back requirements first.") from exc
        self.ak = ak
        self._headers = self._ths_headers()

    def concept_members(
        self,
        progress: Callable[[str, int, int, int, list[BoardMember]], None] | None = None,
    ) -> list[BoardMember]:
        boards = self.ak.stock_board_concept_name_ths()
        records = boards.to_dict("records") if hasattr(boards, "to_dict") else list(boards)
        members: list[BoardMember] = []
        total = len(records)
        for index, board in enumerate(records, start=1):
            board_name = str(board.get("name") or board.get("板块名称") or "").strip()
            board_code = str(board.get("code") or "").strip()
            if not board_name or not board_code:
                continue
            try:
                stock_rows = self._ths_concept_stocks(board_code)
            except Exception:
                continue
            board_members: list[BoardMember] = []
            for row in stock_rows:
                symbol = _stock_code(row.get("代码") or row.get("code") or row.get("股票代码"))
                if symbol.startswith(("0", "3", "6", "8")):
                    member = BoardMember(symbol=symbol, board_name=board_name)
                    members.append(member)
                    board_members.append(member)
            if progress:
                progress(board_name, index, total, len(members), board_members)
        return members

    def _ths_headers(self) -> dict[str, str]:
        try:
            import py_mini_racer
            from akshare.datasets import get_ths_js

            js_code = py_mini_racer.MiniRacer()
            with open(get_ths_js("ths.js"), encoding="utf-8") as file:
                js_code.eval(file.read())
            v_code = js_code.call("v")
        except Exception:
            v_code = ""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Referer": "https://q.10jqka.com.cn/gn/",
            "Cookie": f"v={v_code}",
        }

    def _ths_concept_stocks(self, board_code: str) -> list[dict[str, Any]]:
        first_url = f"https://q.10jqka.com.cn/gn/detail/code/{board_code}/"
        first_text = self._request_ths(first_url)
        rows = self._read_stock_rows(first_text)
        page_count = self._page_count(first_text)
        for page in range(2, page_count + 1):
            page_url = f"https://q.10jqka.com.cn/gn/detail/page/{page}/ajax/1/code/{board_code}/"
            try:
                rows.extend(self._read_stock_rows(self._request_ths(page_url)))
            except Exception:
                continue
        return rows

    def _request_ths(self, url: str) -> str:
        response = requests.get(url, headers=self._headers, timeout=20)
        response.raise_for_status()
        return response.text

    def _read_stock_rows(self, html: str) -> list[dict[str, Any]]:
        tables = pd.read_html(StringIO(html))
        if not tables:
            return []
        return tables[0].to_dict("records")

    def _page_count(self, html: str) -> int:
        match = re.search(r'class="page_info">\s*\d+/(\d+)\s*<', html)
        if not match:
            return 1
        return max(1, int(match.group(1)))
