# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Bounded, resumable public collection. A 403 stops the run. No other host is tried.

This module does not import the comparison engine and does not compute strategy
features, returns, or p-values. Holdout rows are stored only as raw coverage.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from bybit_research.allowlist import check_request
from bybit_research.config import (
    BAR_MS,
    DAY_MS,
    DISCOVERY_START,
    HOLDOUT_END,
    HOLDOUT_START,
    HYPERGROK_PIN,
    MAX_FUNDING_PAGES,
    PAGE_LIMIT_FUNDING,
    SELECTION_CANDIDATES,
    SYMBOLS,
    VALIDATION_START,
    WARMUP_START,
    proposed_config_hash,
    segment_name,
)
from bybit_research.http_client import AccessBlocked, PublicClient
from bybit_research.jsonutil import dumps_pretty, sha256_bytes, sha256_file, utc_now
from bybit_research.paginate import accept_kline_page, kline_windows, paginate_funding
from bybit_research.schema import (
    SchemaError,
    coverage_gaps,
    merge_observations,
    observed_identity,
    parse_funding_payload,
    parse_instrument_payload,
    parse_kline_payload,
)

BANNED_FIELDS = {"z", "signal", "net", "pnl", "return", "feature", "p_value", "alpha"}
EXPLORATORY_SEGMENTS = {"warmup", "discovery", "validation"}


def build_official_plan() -> list[dict]:
    items = []

    def add(**item):
        item["id"] = f"{len(items):04d}"
        check_request("GET", item.get("path", "/v5/market/kline" if item["type"] != "funding" else "/v5/market/funding/history"), item.get("query", {"category": "linear", "symbol": "BTCUSDT"}))
        items.append(item)

    add(type="http", kind="instrument", role="preflight", path="/v5/market/instruments-info",
        query={"category": "linear", "symbol": "BTCUSDT"})
    for symbol in SYMBOLS:
        if symbol != "BTCUSDT":
            add(type="http", kind="instrument", role="current", path="/v5/market/instruments-info",
                query={"category": "linear", "symbol": symbol})
        add(type="http", kind="instrument_closed", role="closed_filter", path="/v5/market/instruments-info",
            query={"category": "linear", "symbol": symbol, "status": "Closed", "limit": "50"})
    for symbol in SELECTION_CANDIDATES:
        add(type="http", kind="selection_daily", path="/v5/market/kline",
            query={"category": "linear", "symbol": symbol, "interval": "D", "start": str(WARMUP_START),
                   "end": str(DISCOVERY_START - 1), "limit": "1000"})
    for symbol in SYMBOLS:
        add(type="klines", kind="last", symbol=symbol, interval="240", start=WARMUP_START, end=HOLDOUT_END)
        add(type="klines", kind="mark", symbol=symbol, interval="240", start=WARMUP_START, end=HOLDOUT_END)
        add(type="funding", symbol=symbol, start=WARMUP_START, end=HOLDOUT_END)
    _validate_plan(items)
    return items


def _validate_plan(items: list[dict]) -> None:
    if not items or items[0].get("role") != "preflight":
        raise RuntimeError("collection must start with the official-host preflight")
    hosts = set()
    for item in items:
        path = "/v5/market/funding/history" if item["type"] == "funding" else item.get("path")
        if item["type"] == "klines":
            path = "/v5/market/mark-price-kline" if item["kind"] == "mark" else "/v5/market/kline"
        if item["type"] == "http":
            check_request("GET", item["path"], item["query"])
        hosts.add(path)
    if any(not path.startswith("/v5/market/") for path in hosts):
        raise RuntimeError("plan left the public market prefix")


def execute(plan: list[dict], out_dir: str | Path, client: PublicClient | None = None, as_of_ms: int | None = None, resume: bool = False) -> dict:
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()) and not resume:
        raise FileExistsError("output directory is not empty; resume explicitly or choose a new directory")
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw"
    raw.mkdir(exist_ok=True)
    if resume and (out / "blocker.json").exists():
        raise RuntimeError("resume refused: an access block is already recorded and will not be retried")
    client = client or PublicClient()
    as_of_ms = int(as_of_ms if as_of_ms is not None else _now_ms())
    attempted, not_attempted = [], []
    pages = []
    blocked = None
    for index, item in enumerate(plan):
        if blocked is not None:
            not_attempted.append(item["id"])
            continue
        try:
            pages.extend(_run_item(item, client, raw, as_of_ms))
            attempted.append(item["id"])
        except SchemaError as exc:
            attempted.append(item["id"])
            pages.append({"slot": item["id"], "expect": item["type"], "symbol": item.get("symbol") or item.get("query", {}).get("symbol"), "error": "schema", "detail": str(exc)})
        except AccessBlocked as exc:
            blocked = _write_blocker(out, raw, exc, item)
            attempted.append(item["id"])
    error_rows = [
        {"slot": page.get("slot"), "expect": page.get("expect"), "symbol": page.get("symbol"),
         "error": page.get("error"), "detail": page.get("detail"), "retCode": page.get("retCode")}
        for page in pages if page.get("error")
    ]
    if error_rows:
        (out / "series_errors.json").write_bytes(dumps_pretty(error_rows))
    normalized = _assemble(out, pages, as_of_ms)
    manifest = _manifest(out, attempted, not_attempted, blocked, normalized, len(error_rows))
    (out / "manifest.json").write_bytes(dumps_pretty(manifest))
    _refresh_file_hashes(out, manifest)
    return manifest


def _now_ms() -> int:
    from datetime import datetime, timezone
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _run_item(item, client, raw, as_of_ms) -> list[dict]:
    if item["type"] == "http":
        return [_request(item["id"], item["path"], item["query"], client, raw, expect=item["kind"])]
    if item["type"] == "klines":
        path = "/v5/market/mark-price-kline" if item["kind"] == "mark" else "/v5/market/kline"
        step = BAR_MS
        stored = []
        for window_index, (start, end) in enumerate(kline_windows(item["start"], item["end"], step)):
            query = {"category": "linear", "symbol": item["symbol"], "interval": item["interval"],
                     "start": str(start), "end": str(end - 1), "limit": "1000"}
            slot = f"{item['id']}-w{window_index:02d}"
            page = _request(slot, path, query, client, raw, expect=item["kind"], symbol=item["symbol"], window=(start, end), step=step)
            stored.append(page)
        return stored
    if item["type"] == "funding":
        stored = []

        def fetch_page(start, end_inclusive, limit):
            slot = f"{item['id']}-p{len(stored):02d}"
            query = {"category": "linear", "symbol": item["symbol"], "startTime": str(start),
                     "endTime": str(end_inclusive), "limit": str(limit)}
            page = _request(slot, "/v5/market/funding/history", query, client, raw, expect="funding", symbol=item["symbol"])
            stored.append(page)
            if page.get("error"):
                raise SchemaError(page["error"])
            return page["rows"]

        result = paginate_funding(fetch_page, item["start"], item["end"], PAGE_LIMIT_FUNDING, MAX_FUNDING_PAGES)
        if stored:
            stored[-1]["funding_complete"] = result["complete"]
            stored[-1]["funding_reason"] = result["reason"]
        return stored
    raise RuntimeError("unknown plan item")


def _request(slot, path, query, client, raw, expect, symbol=None, window=None, step=None) -> dict:
    cached = _cached(raw, slot, path, query)
    if cached is not None:
        return cached
    url, response = client.get_raw(path, query)
    meta = _write_raw(raw, slot, url, path, query, response, expect, symbol, window, step)
    return _interpret(meta, response.body)


def _cached(raw: Path, slot: str, path: str, query: dict):
    meta_path = raw / f"{slot}.meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    body = (raw / f"{slot}.body").read_bytes()
    if meta.get("body_sha256") != sha256_bytes(body) or meta.get("query") != query or meta.get("path") != path:
        raise RuntimeError("cached public response does not match its request; refusing to ignore the mismatch")
    return _interpret(meta, body)


def _write_raw(raw, slot, url, path, query, response, expect, symbol, window, step) -> dict:
    body_name = f"{slot}.body"
    (raw / body_name).write_bytes(response.body)
    meta = {
        "slot": slot, "method": "GET", "url": url, "host": "api.bybit.com", "path": path, "query": query,
        "expect": expect, "symbol": symbol, "window": list(window) if window else None, "step": step,
        "retrieved_at_utc": utc_now(), "http_status": response.status,
        "body_sha256": sha256_bytes(response.body), "body_file": f"raw/{body_name}",
        "response_headers": response.headers,
    }
    (raw / f"{slot}.meta.json").write_bytes(dumps_pretty(meta))
    return meta


def _interpret(meta, body) -> dict:
    expect, symbol, window, step = meta.get("expect"), meta.get("symbol") or meta["query"]["symbol"], meta.get("window"), meta.get("step")
    record = {"slot": meta["slot"], "expect": expect, "symbol": symbol, "window": window, "step": step, "meta": meta["slot"]}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        record["error"] = "body_not_json"
        record["detail"] = str(exc)
        return record
    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        record["error"] = "retcode"
        record["retCode"] = payload.get("retCode") if isinstance(payload, dict) else None
        return record
    try:
        if expect in ("last", "mark"):
            rows = parse_kline_payload(payload, symbol=symbol, category="linear", kind=expect, step_ms=step)
            accept_kline_page(rows, window[0], window[1], step)
            record["rows"] = rows
        elif expect == "funding":
            record["rows"] = parse_funding_payload(payload, symbol=symbol, category="linear")
        elif expect in ("instrument", "instrument_closed"):
            record["instrument"] = parse_instrument_payload(payload, symbol=symbol, category="linear")
        elif expect == "selection_daily":
            record["rows"] = parse_kline_payload(payload, symbol=symbol, category="linear", kind="last", step_ms=DAY_MS)
        else:
            raise SchemaError("unknown payload expectation")
    except (SchemaError, KeyError, TypeError, ValueError) as exc:
        record["error"] = "schema"
        record["detail"] = str(exc)
    return record


def _write_blocker(out: Path, raw: Path, exc: AccessBlocked, item: dict) -> dict:
    body_path = raw / "blocker.body"
    body_path.write_bytes(exc.body or b"")
    blocker = {
        "http_status": exc.status,
        "url": exc.url,
        "host": "api.bybit.com",
        "plan_id": item.get("id"),
        "retrieved_at_utc": utc_now(),
        "body_sha256": sha256_bytes(exc.body or b""),
        "body_file": "raw/blocker.body",
        "response_headers": exc.headers,
        "country_block": b"block access from your country" in (exc.body or b""),
        "note": "Stopped on HTTP 401, 403, 451, or a redirect. No alternate host, proxy, or region endpoint was requested.",
    }
    (out / "blocker.json").write_bytes(dumps_pretty(blocker))
    return blocker


def _assemble(out: Path, pages: list[dict], as_of_ms: int) -> list[str]:
    written = []
    by_key = {}
    for page in pages:
        if page.get("error") or "rows" not in page:
            continue
        if page["expect"] not in ("last", "mark"):
            continue
        by_key.setdefault((page["symbol"], page["expect"]), []).extend(page["rows"])
    for (symbol, kind), rows in sorted(by_key.items()):
        kept, conflict = merge_observations(rows, "open_ms")
        if conflict:
            (out / f"{symbol}-{kind}-conflict.txt").write_text(conflict + "\n")
            continue
        closed = [row for row in kept if row["open_ms"] + BAR_MS <= as_of_ms and row["open_ms"] < HOLDOUT_END]
        exploratory = [row for row in closed if segment_name(row["open_ms"]) in EXPLORATORY_SEGMENTS]
        holdout = [row for row in closed if segment_name(row["open_ms"]) == "holdout"]
        written.append(_write_candles(out, out / "normalized" / "exploratory" / f"{symbol}_{kind}_4h.csv", exploratory, kind))
        written.append(_write_candles(out, out / "normalized" / "holdout" / f"{symbol}_{kind}_4h.csv", holdout, kind))
        gaps = coverage_gaps(closed, WARMUP_START, HOLDOUT_END, BAR_MS)
        (out / "normalized" / f"{symbol}_{kind}_gaps.json").write_bytes(dumps_pretty({"missing_slots": len(gaps), "gaps": gaps[:50], "truncated_gap_list": len(gaps) > 50}))
        written.append(f"normalized/{symbol}_{kind}_gaps.json")
    return [item for item in written if item]


def _write_candles(out: Path, path: Path, rows: list[dict], kind: str) -> str:
    fields = ["open_ms", "open", "high", "low", "close", "segment"]
    if kind == "last":
        fields[5:5] = ["volume", "turnover", "volume_unit", "turnover_unit"]
    else:
        fields.append("price_unit")
    if BANNED_FIELDS & set(fields):
        raise RuntimeError("refusing to write strategy fields into a coverage file")
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        record = {
            "open_ms": row["open_ms"],
            "open": format(row["open"], "f"),
            "high": format(row["high"], "f"),
            "low": format(row["low"], "f"),
            "close": format(row["close"], "f"),
            "segment": segment_name(row["open_ms"]),
        }
        if kind == "last":
            record.update({
                "volume": format(row["volume"], "f"),
                "turnover": format(row["turnover"], "f"),
                "volume_unit": row["volume_unit"],
                "turnover_unit": row["turnover_unit"],
            })
        else:
            record["price_unit"] = row["price_unit"]
        writer.writerow(record)
    path.write_text(buffer.getvalue())
    return path.relative_to(out).as_posix()


def _manifest(out, attempted, not_attempted, blocked, normalized, series_error_count=0) -> dict:
    files = []
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append({"path": path.relative_to(out).as_posix(), "sha256": sha256_file(path)})
    return {
        "schema": "bybit-linear-public-research-1",
        "hypergrok_pin": HYPERGROK_PIN,
        "config_sha256": proposed_config_hash(),
        "host": "api.bybit.com",
        "method": "GET",
        "result": "blocked" if blocked else "collected",
        "strict_sufficient_for_primary": False,
        "market_performance": "not_executed",
        "attempted_plan_ids": attempted,
        "not_attempted_plan_ids": not_attempted,
        "blocked": blocked is not None,
        "series_error_count": series_error_count,
        "normalized_files": normalized,
        "files": files,
        "generated_at_utc": utc_now(),
        "coverage_is_not_evaluation": True,
    }


def _refresh_file_hashes(out: Path, manifest: dict) -> None:
    # The manifest lists every other file. It is hashed by the verifier separately.
    files = []
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append({"path": path.relative_to(out).as_posix(), "sha256": sha256_file(path)})
    manifest["files"] = files
    (out / "manifest.json").write_bytes(dumps_pretty(manifest))


def observed_rows_from_identity(row: dict) -> dict:
    return observed_identity(row)
