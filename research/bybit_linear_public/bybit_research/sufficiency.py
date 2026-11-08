# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Strict sufficiency. Unknown required evidence is a failure, not a silent pass."""

from __future__ import annotations

import json
from pathlib import Path

from bybit_research.config import (
    CONDITIONAL_SYMBOLS,
    DISCOVERY_START,
    HOLDOUT_END,
    HOLDOUT_START,
    SYMBOLS,
    VALIDATION_START,
    WARMUP_START,
    proposed_config_hash,
)
from bybit_research.jsonutil import sha256_file

PERIODS = (
    ("discovery", DISCOVERY_START, VALIDATION_START),
    ("validation", VALIDATION_START, HOLDOUT_START),
    ("holdout_coverage_only", HOLDOUT_START, HOLDOUT_END),
)

SURVIVOR_BIAS = (
    "BTCUSDT, ETHUSDT, SOLUSDT and XRPUSDT are a fixed retrospective set. "
    "SOLUSDT and XRPUSDT were the first two names in a six-name candidate list of contracts "
    "that were observable as listed when that selection note was written. Contracts that had "
    "already been closed or delisted were not candidates. This is survivorship bias. "
    "A later result, if one is ever authorized, would describe only these four names and "
    "would not estimate the historical USDT linear universe. The 822-name and 1147-name "
    "snapshots are different scopes and are not a historical universe."
)


def assess(bundle: str | Path) -> dict:
    root = Path(bundle)
    manifest = json.loads((root / "manifest.json").read_text()) if (root / "manifest.json").is_file() else {}
    blocker = json.loads((root / "blocker.json").read_text()) if (root / "blocker.json").is_file() else None
    symbols = {}
    for symbol in SYMBOLS:
        symbols[symbol] = _symbol_report(root, symbol, blocker)
    reasons = []
    if blocker is not None:
        reasons.append("access_blocked_before_required_history")
    if any(not item["strict_sufficient"] for item in symbols.values()):
        reasons.append("one_or_more_symbols_fail_the_strict_rule")
    return {
        "config_sha256": proposed_config_hash(),
        "bundle_manifest_sha256": sha256_file(root / "manifest.json") if (root / "manifest.json").is_file() else None,
        "collection_result": manifest.get("result", "missing"),
        "blocked": blocker is not None,
        "blocker": _public_blocker(blocker),
        "strict_sufficient_for_primary": False if reasons else True,
        "fail_reasons": reasons,
        "symbols": symbols,
        "survivor_bias": SURVIVOR_BIAS,
        "holdout": "Coverage files, when present, are not strategy features or returns. The holdout was not opened for analysis and is not a certified blind segment.",
        "mark_settlement": "A mark candle does not prove the mark printed at the funding settlement. Exact settlement mark remains UNKNOWN.",
        "funding_interval": "A run of funding timestamps does not by itself prove the historical funding-interval schedule.",
        "fees": "No historical or personal fee was observed. Conditional scenarios stay unapplied to market history.",
        "not_done": [
            "market-history strategy performance",
            "p-values or PASS on market history",
            "paper trading",
            "orders, leverage, margin, or account endpoints",
        ],
    }


def _symbol_report(root: Path, symbol: str, blocker) -> dict:
    observed = blocker is None and _has_series(root, symbol)
    failures = []
    if blocker is not None or not observed:
        failures.append("required_history_not_observed")
    failures.extend([
        "historical_contract_status_UNKNOWN",
        "historical_funding_interval_UNKNOWN",
        "settlement_mark_exact_UNKNOWN",
    ])
    periods = []
    for name, start, end in PERIODS:
        periods.append({
            "period": name,
            "start_ms": start,
            "end_ms": end,
            "last_4h": "NOT_OBSERVED" if not observed else "SEE_COVERAGE_FILE",
            "mark_4h": "NOT_OBSERVED" if not observed else "SEE_COVERAGE_FILE",
            "funding": "NOT_OBSERVED" if not observed else "COMPLETENESS_UNKNOWN",
            "historical_status": "UNKNOWN",
            "launch_time": "NOT_OBSERVED" if blocker is not None else "SEE_IDENTITY_FILE_IF_PRESENT",
            "strict_sufficient": False,
        })
    return {
        "symbol": symbol,
        "conditional": symbol in CONDITIONAL_SYMBOLS,
        "dropped": False,
        "strict_sufficient": False,
        "fail_reasons": failures,
        "periods": periods,
        "warmup_start_ms": WARMUP_START,
    }


def _has_series(root: Path, symbol: str) -> bool:
    exploratory = root / "normalized" / "exploratory" / f"{symbol}_last_4h.csv"
    return exploratory.is_file() and sum(1 for _ in exploratory.open()) > 1


def _public_blocker(blocker):
    if blocker is None:
        return None
    return {
        "http_status": blocker.get("http_status"),
        "url": blocker.get("url"),
        "retrieved_at_utc": blocker.get("retrieved_at_utc"),
        "body_sha256": blocker.get("body_sha256"),
        "country_block": blocker.get("country_block"),
        "note": blocker.get("note"),
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Veri yeterliliği",
        "",
        "Bu dosya piyasa geçmişi üzerinde strateji performansı değildir. Toplama, değerlendirme değildir.",
        "",
        f"- Konfigürasyon SHA-256: `{report['config_sha256']}`",
        f"- Manifest SHA-256: `{report['bundle_manifest_sha256']}`",
        f"- Toplama sonucu: `{report['collection_result']}`",
        f"- Birincil değerlendirme için katı yeterlilik: `{report['strict_sufficient_for_primary']}`",
        "",
        "## Karar",
        "",
        "Katı kural, gerekli kanıt bilinmiyorsa geçmez. Eksik gözlem sıfır işlem diye yazılmaz, vekil seri konmaz ve dönem sessizce kısaltılmaz.",
        "",
    ]
    blocker = report.get("blocker")
    if blocker:
        lines.extend([
            "## Erişim engeli",
            "",
            f"- HTTP durum: `{blocker['http_status']}`",
            f"- URL: `{blocker['url']}`",
            f"- Alım zamanı (UTC): `{blocker['retrieved_at_utc']}`",
            f"- Gövde SHA-256: `{blocker['body_sha256']}`",
            f"- Ülke engeli gözlemi: `{blocker['country_block']}`",
            f"- Not: {blocker['note']}",
            "",
            "403 sonrası başka host, proxy veya bölge uç noktası denenmedi. Dört sembolün tarihsel mum, mark, funding ve kimlik kayıtları bu koşuda gözlenmedi.",
            "",
        ])
    lines.extend(["## Semboller", ""])
    lines.append("| Sembol | Koşullu | Katı yeterlilik | Dönem gözlemi | Tarihsel statü |")
    lines.append("| --- | --- | --- | --- | --- |")
    for symbol, item in report["symbols"].items():
        lines.append(
            f"| {symbol} | {item['conditional']} | geçmedi | {item['periods'][0]['last_4h']} | UNKNOWN |"
        )
    lines.extend([
        "",
        "## Neden geçmedi",
        "",
        "- Güncel `instruments-info` bile bu koşuda alınamadıysa launch, statü ve funding aralığı gözlenmemiştir. Önceki taslaklardaki launchTime değerleri bu koşunun gözlemi değildir ve kimlik kanıtı yapılmadı.",
        "- Tarihsel statü, güncel bir anlık görüntüyle kanıtlanamaz. Bilinmeyen statü, sürekli Trading varsayımı değildir.",
        "- Mark mumunun kapanışı, funding settlement anındaki mark fiyatının aynısı diye alınmaz.",
        "- Funding zaman damgalarının dizilişi, tarihsel funding aralığının belgesi değildir.",
        "- Ücretler tarihsel veya kişisel tarife olarak gözlenmedi.",
        "",
        "## Hayatta kalma yanlılığı",
        "",
        report["survivor_bias"],
        "",
        "## Holdout",
        "",
        report["holdout"],
        "",
        "## Bu koşuda yapılmayanlar",
        "",
    ])
    for item in report["not_done"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)
