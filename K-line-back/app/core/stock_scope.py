from __future__ import annotations


def is_mainland_hs_symbol(symbol: str | None) -> bool:
    normalized = str(symbol or "").strip().zfill(6)
    return normalized.startswith(("0", "3", "6"))


def normalize_mainland_hs_symbol(symbol: str | None) -> str | None:
    normalized = str(symbol or "").strip().zfill(6)
    return normalized if is_mainland_hs_symbol(normalized) else None
