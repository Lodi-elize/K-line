from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.stock_scope import is_mainland_hs_symbol


@dataclass(frozen=True)
class BoardMember:
    symbol: str
    board_name: str


BOARD_NAME_COLUMNS = ("板块名称", "name", "名称", "概念名称")
BOARD_CODE_COLUMNS = ("板块代码", "code", "代码")
STOCK_CODE_COLUMNS = ("代码", "股票代码", "symbol", "code", "证券代码")


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
    def __init__(self) -> None:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("akshare is not installed. Install K-line-back requirements first.") from exc
        self.ak = ak

    def concept_members(
        self,
        progress: Callable[[str, int, int, int, list[BoardMember]], None] | None = None,
    ) -> list[BoardMember]:
        boards = self.ak.stock_board_concept_name_em()
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

    def _eastmoney_concept_stocks(self, board_symbol: str) -> list[dict[str, Any]]:
        stocks = self.ak.stock_board_concept_cons_em(symbol=board_symbol)
        return stocks.to_dict("records") if hasattr(stocks, "to_dict") else list(stocks)
