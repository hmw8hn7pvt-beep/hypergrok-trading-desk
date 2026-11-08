# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Monotonic public pagination. A window that does not advance is a hard stop."""

from __future__ import annotations

from bybit_research.config import MAX_FUNDING_PAGES, MAX_KLINE_PAGES, PAGE_LIMIT_FUNDING, PAGE_LIMIT_KLINE
from bybit_research.schema import SchemaError


def kline_windows(start: int, end: int, step: int, limit: int = PAGE_LIMIT_KLINE) -> list[tuple[int, int]]:
    if start >= end or step <= 0 or limit <= 0:
        raise SchemaError("invalid kline window")
    windows = []
    cursor = start
    while cursor < end:
        chunk_end = min(end, cursor + limit * step)
        if chunk_end <= cursor:
            raise SchemaError("kline window did not advance")
        windows.append((cursor, chunk_end))
        cursor = chunk_end
    if len(windows) > MAX_KLINE_PAGES:
        raise SchemaError("kline page plan exceeds the bound")
    return windows


def accept_kline_page(rows: list[dict], start: int, end: int, step: int, limit: int = PAGE_LIMIT_KLINE) -> None:
    slots = (end - start) // step
    if slots <= 0 or slots > limit:
        raise SchemaError("kline page window is larger than one request")
    seen = set()
    for row in rows:
        open_ms = row["open_ms"]
        if open_ms < start or open_ms >= end or (open_ms - start) % step != 0:
            raise SchemaError("kline timestamp falls outside the requested window")
        if open_ms in seen:
            raise SchemaError("duplicate timestamp inside a kline page")
        seen.add(open_ms)
    if len(rows) > slots:
        raise SchemaError("kline page returned more candles than the window has slots")
    if len(rows) == limit and slots == limit and rows and min(row["open_ms"] for row in rows) > start:
        raise SchemaError("kline page looks truncated and the missing head was not accepted")


def paginate_funding(fetch_page, start: int, end: int, limit: int = PAGE_LIMIT_FUNDING, max_pages: int = MAX_FUNDING_PAGES) -> dict:
    """fetch_page(start, end_inclusive, limit) returns parsed funding rows in any order."""
    if start >= end:
        raise SchemaError("funding range is empty")
    end_cursor = end - 1
    seen = {}
    pages = 0
    previous_oldest = None
    while True:
        pages += 1
        if pages > max_pages:
            return {"events": _ordered(seen), "complete": False, "reason": "page_budget", "pages": pages - 1}
        batch = fetch_page(start, end_cursor, limit)
        if len(batch) > limit:
            raise SchemaError("funding page exceeds the requested limit")
        if not batch:
            return {"events": _ordered(seen), "complete": True, "reason": None, "pages": pages}
        stamps = []
        for event in batch:
            timestamp = event["timestamp"]
            if timestamp < start or timestamp > end_cursor:
                raise SchemaError("funding timestamp falls outside the requested window")
            stamps.append(timestamp)
            previous = seen.get(timestamp)
            if previous is None:
                seen[timestamp] = event
            elif previous["rate"] != event["rate"]:
                raise SchemaError("conflicting funding rate for one timestamp")
        oldest = min(stamps)
        if previous_oldest is not None and oldest >= previous_oldest:
            raise SchemaError("funding pagination did not move backward")
        if len(batch) < limit or oldest <= start:
            return {"events": _ordered(seen), "complete": True, "reason": None, "pages": pages}
        next_cursor = oldest - 1
        if next_cursor >= end_cursor:
            raise SchemaError("funding end cursor did not advance")
        end_cursor = next_cursor
        previous_oldest = oldest


def _ordered(seen: dict) -> list[dict]:
    return [seen[key] for key in sorted(seen)]
