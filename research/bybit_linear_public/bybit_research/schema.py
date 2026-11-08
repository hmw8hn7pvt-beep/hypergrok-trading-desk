# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Schema, time, and unit checks for public Bybit market payloads."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from bybit_research.config import BAR_MS, DAY_MS


class SchemaError(ValueError):
    pass


def _decimal(text: str, name: str, positive=False, nonnegative=False) -> Decimal:
    if not isinstance(text, str) or text == "" or len(text) > 100:
        raise SchemaError(f"{name} must be a decimal string")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise SchemaError(f"{name} is not a decimal") from exc
    if not value.is_finite() or (positive and value <= 0) or (nonnegative and value < 0):
        raise SchemaError(f"{name} has an invalid numeric value")
    return value


def _millis(text: str, name: str) -> int:
    if not isinstance(text, str) or not text.isdigit():
        raise SchemaError(f"{name} must be a millisecond string")
    return int(text)


def _envelope(payload: dict, category: str) -> dict:
    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        raise SchemaError("retCode is not 0")
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("category") != category:
        raise SchemaError("result category does not match the request")
    return result


def _ohlc(open_px, high, low, close) -> None:
    if high < low or high < open_px or high < close or low > open_px or low > close:
        raise SchemaError("OHLC relationship is invalid")


def parse_kline_payload(payload: dict, *, symbol: str, category: str, kind: str, step_ms: int) -> list[dict]:
    result = _envelope(payload, category)
    if result.get("symbol") != symbol:
        raise SchemaError("kline symbol does not match the request")
    rows = result.get("list")
    if not isinstance(rows, list):
        raise SchemaError("kline list is missing")
    width = 7 if kind == "last" else 5
    if kind not in ("last", "mark"):
        raise SchemaError("unknown kline kind")
    parsed = []
    for row in rows:
        if not isinstance(row, list) or len(row) != width or not all(isinstance(item, str) for item in row):
            raise SchemaError(f"{kind} kline row must contain {width} strings")
        open_ms = _millis(row[0], "startTime")
        if open_ms % step_ms != 0:
            raise SchemaError("candle open is not aligned to the requested interval")
        open_px = _decimal(row[1], "open", positive=True)
        high = _decimal(row[2], "high", positive=True)
        low = _decimal(row[3], "low", positive=True)
        close = _decimal(row[4], "close", positive=True)
        _ohlc(open_px, high, low, close)
        item = {"open_ms": open_ms, "open": open_px, "high": high, "low": low, "close": close, "kind": kind}
        if kind == "last":
            item["volume"] = _decimal(row[5], "volume", nonnegative=True)
            item["turnover"] = _decimal(row[6], "turnover", nonnegative=True)
            item["volume_unit"] = "base_coin"
            item["turnover_unit"] = "quote_coin"
        else:
            item["price_unit"] = "mark_price_quote_per_contract_unproven_as_settlement_print"
        parsed.append(item)
    return parsed


def parse_funding_payload(payload: dict, *, symbol: str, category: str) -> list[dict]:
    result = _envelope(payload, category)
    rows = result.get("list")
    if not isinstance(rows, list):
        raise SchemaError("funding list is missing")
    parsed = []
    for row in rows:
        if not isinstance(row, dict) or row.get("symbol") != symbol:
            raise SchemaError("funding row symbol does not match the request")
        parsed.append({
            "timestamp": _millis(row.get("fundingRateTimestamp"), "fundingRateTimestamp"),
            "rate": _decimal(row.get("fundingRate"), "fundingRate"),
            "symbol": symbol,
        })
    return parsed


def parse_instrument_payload(payload: dict, *, symbol: str, category: str) -> dict:
    """Return the observed rows. An empty list is an observation, not invented metadata."""
    if not isinstance(payload, dict):
        raise SchemaError("instrument payload is not an object")
    if payload.get("retCode") != 0:
        return {
            "ok": False,
            "retCode": payload.get("retCode"),
            "retMsg": payload.get("retMsg") if isinstance(payload.get("retMsg"), str) else None,
        }
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("category") != category:
        raise SchemaError("instrument category does not match the request")
    rows = result.get("list")
    if not isinstance(rows, list):
        raise SchemaError("instrument list is missing")
    matched = []
    for row in rows:
        if isinstance(row, dict) and row.get("symbol") == symbol:
            matched.append(row)
    return {"ok": True, "rows": matched}


IDENTITY_FIELDS = (
    "symbol", "contractType", "status", "baseCoin", "quoteCoin", "settleCoin",
    "launchTime", "deliveryTime", "fundingInterval", "symbolType",
)


def observed_identity(row: dict) -> dict:
    observed = {}
    missing = []
    for field in IDENTITY_FIELDS:
        if field not in row:
            missing.append(field)
        else:
            observed[field] = row[field]
    launch = observed.get("launchTime")
    if isinstance(launch, str) and launch.isdigit():
        observed["launchTime_ms"] = int(launch)
    else:
        observed["launchTime_ms"] = None
    delivery = observed.get("deliveryTime")
    if isinstance(delivery, str) and delivery.isdigit():
        observed["deliveryTime_ms"] = int(delivery)
    else:
        observed["deliveryTime_ms"] = None
    observed["missing_fields"] = missing
    observed["historical_status"] = "UNKNOWN"
    observed["historical_funding_interval"] = "UNKNOWN"
    return observed


def merge_observations(rows: list[dict], identity_key: str) -> tuple[list[dict], str | None]:
    """Keep identical duplicates once. Conflicting values for the same key are unavailable."""
    kept = {}
    for row in rows:
        key = row[identity_key]
        previous = kept.get(key)
        if previous is None:
            kept[key] = row
            continue
        if previous != row:
            return [], "conflicting_duplicate"
    ordered = [kept[key] for key in sorted(kept)]
    return ordered, None


def expected_opens(start: int, end: int, step: int = BAR_MS) -> list[int]:
    if start >= end or (end - start) % step != 0 or start % step != 0:
        raise SchemaError("range is not an aligned half-open interval")
    return list(range(start, end, step))


def coverage_gaps(rows: list[dict], start: int, end: int, step: int = BAR_MS) -> list[dict]:
    present = {row["open_ms"] for row in rows}
    missing = [open_ms for open_ms in expected_opens(start, end, step) if open_ms not in present]
    return [{"open_ms": open_ms, "close_ms": open_ms + step} for open_ms in missing]


def closed_candle(open_ms: int, step: int, as_of_ms: int, end_exclusive: int) -> bool:
    close_ms = open_ms + step
    return close_ms <= as_of_ms and close_ms <= end_exclusive


def daily_step() -> int:
    return DAY_MS
