# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Proposed, unfrozen research configuration.

Market-history strategy performance must not read this module as approval.
The hash covers the proposed constants and the deviation ids.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from bybit_research.jsonutil import canonical, sha256_bytes

HYPERGROK_PIN = "82bc645899b9581a693463b59553aa1329e021c4"
BAR_MS = 4 * 60 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
FUNDING_BOUNDARY_MS = 5000
SIGMA_WINDOW = 42
Z_ENTRY = "2.0"
Z_EXTREME = "3.0"
D_MULTIPLIER = "2"
COOLDOWN_BARS = 6
MAX_HOLD_BARS = 18
NOTIONAL = "1"
CONTROL_P_DENOMINATOR = 18
CONTROL_RUNS = 200
B1_DRAWS = 20
SEED_ROOT = 20261109
BOOTSTRAP_REPLICATES = 9999
BLOCK_BARS = 42
BLOCK_SENSITIVITY = (21, 84)
HOLM_ALPHA = "0.05"
HOLM_FAMILY = 12
PAGE_LIMIT_KLINE = 1000
PAGE_LIMIT_FUNDING = 200
MAX_FUNDING_PAGES = 40
MAX_KLINE_PAGES = 20
MAX_HTTP_REQUESTS = 400
MAX_ATTEMPTS = 4  # one try plus three retries; 403 is not retried
MIN_INTERVAL_SECONDS = "0.25"
WINDOW_REQUESTS = 20
WINDOW_SECONDS = "5"
PRIMARY_FEE = "S-inn"
PRIMARY_SLIP = "5bps"

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
CONDITIONAL_SYMBOLS = ("SOLUSDT", "XRPUSDT")
SELECTION_CANDIDATES = ("SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LTCUSDT", "LINKUSDT")
N_VALUES = (6, 18, 42)
HYPOTHESES = ("H1", "H2")

# Published rounded medians from the user-supplied ALT_SELECTION note.
# They are a comparison target for a fresh public pull, not a substitute for it.
PUBLISHED_SELECTION_RANK = ("SOLUSDT", "XRPUSDT", "LINKUSDT", "ADAUSDT", "DOGEUSDT", "LTCUSDT")
PUBLISHED_ROUNDED_MEDIANS = {
    "SOLUSDT": "1047929458",
    "XRPUSDT": "176715631",
    "LINKUSDT": "137795282",
    "ADAUSDT": "136576386",
    "DOGEUSDT": "119746736",
    "LTCUSDT": "40082590",
}


def parse_utc(text: str) -> int:
    if len(text) != 20 or not text.endswith("Z"):
        raise ValueError("UTC time must be YYYY-MM-DDTHH:MM:SSZ")
    moment = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


WARMUP_START = parse_utc("2023-12-01T00:00:00Z")
DISCOVERY_START = parse_utc("2024-01-01T00:00:00Z")
VALIDATION_START = parse_utc("2025-07-01T00:00:00Z")
HOLDOUT_START = parse_utc("2026-04-01T00:00:00Z")
HOLDOUT_END = parse_utc("2026-10-01T00:00:00Z")

SEGMENTS = (
    ("warmup", WARMUP_START, DISCOVERY_START),
    ("discovery", DISCOVERY_START, VALIDATION_START),
    ("validation", VALIDATION_START, HOLDOUT_START),
    ("holdout", HOLDOUT_START, HOLDOUT_END),
)

FEE_SCENARIOS = {"S-std": "0.00055", "S-inn": "0.00110"}
SLIP_SCENARIOS = {"2bps": "0.0002", "5bps": "0.0005", "15bps": "0.0015"}

# Current public help-center figures observed while drafting this config.
# They are conditional scenarios, not historical or personal tariffs.
FEE_SOURCES = (
    {
        "id": "S-std",
        "taker": "0.00055",
        "source": "https://www.bybit.com/en/help-center/article/Futures-Contracts-Fees-Explained",
        "note": "Non-VIP USDT perpetual taker 0.055% on the help page. The same page says listed examples are illustrative and account rates can differ.",
    },
    {
        "id": "S-inn",
        "taker": "0.00110",
        "source": "https://www.bybit.com/en/help-center/article/Trading-Fee-Structure",
        "note": "Innovation Zone non-VIP taker 0.1100% on the help page. Region and VIP status can change the rate. Not a historical tariff.",
    },
)

DEVIATIONS = (
    {"id": "D1", "title": "PLAN_DRAFT constants supersede READINESS TBD fields"},
    {"id": "D2", "title": "H2-BR-mirror-v1 proposed control target"},
    {"id": "D3", "title": "Per-variant per-symbol PCG stream including seed root 20261109"},
    {"id": "D4", "title": "Control entries are not filtered by the hypothesis z thresholds"},
    {"id": "D5", "title": "Funding within 5000 ms of a modelled fill is uncertain"},
    {"id": "D6", "title": "Modelled fill time is the 4h bar open; intrabar stop time is unresolved"},
    {"id": "D7", "title": "Missing inputs are UNKNOWN and block a positive primary result"},
    {"id": "D8", "title": "Primary fee scenario is S-inn until historical zone provenance exists"},
    {"id": "D9", "title": "Index series is not collected"},
    {"id": "D10", "title": "Leverage, quantity step, and minimum notional are not statistic inputs"},
    {"id": "D11", "title": "PostOnly is not modelled"},
    {"id": "D12", "title": "Holdout files are coverage only and are not a certified blind test"},
    {"id": "D13", "title": "Two explicit unapproved bootstrap readings; neither is a market result"},
    {"id": "D14", "title": "Configured B=9999 is not executed on market history"},
    {"id": "D15", "title": "SOLUSDT and XRPUSDT stay conditional and are not dropped"},
    {"id": "D16", "title": "Closed-status queries are per fixed symbol, not a full venue catalogue"},
    {"id": "D17", "title": "HTTP 403 stops the run with no retry and no other host"},
    {"id": "D18", "title": "December 2023 4h bars are the warmup window"},
    {"id": "D19", "title": "An entry on the first segment bar may use the prior close as its signal"},
    {"id": "D20", "title": "A gap while a position is open leaves that position UNKNOWN"},
    {"id": "D21", "title": "A control run with zero trades has an undefined mean"},
    {"id": "D22", "title": "Degenerate samples produce no p-value"},
    {"id": "D23", "title": "A mark candle is not treated as the funding-settlement mark"},
    {"id": "D24", "title": "Invalidation may be evaluated on the entry bar close"},
    {"id": "D25", "title": "Literal per-replicate studentization blocks when any inner SE is zero"},
)


def segment_name(open_ms: int) -> str:
    for name, start, end in SEGMENTS:
        if start <= open_ms < end:
            return name
    return "outside"


def proposed_config() -> dict:
    return {
        "schema": "bybit-linear-udar4-proposed-1",
        "status": "proposed_not_frozen",
        "market_performance_authorized": False,
        "hypergrok_pin": HYPERGROK_PIN,
        "symbols": list(SYMBOLS),
        "conditional_symbols": list(CONDITIONAL_SYMBOLS),
        "selection_candidates": list(SELECTION_CANDIDATES),
        "hypotheses": list(HYPOTHESES),
        "n": list(N_VALUES),
        "bar_ms": BAR_MS,
        "segments_utc": [
            {"name": name, "start_ms": start, "end_ms": end} for name, start, end in SEGMENTS
        ],
        "sigma_window": SIGMA_WINDOW,
        "sigma_ddof": 1,
        "z_entry": Z_ENTRY,
        "z_extreme": Z_EXTREME,
        "d_multiplier": D_MULTIPLIER,
        "cooldown_bars": COOLDOWN_BARS,
        "max_hold_bars": MAX_HOLD_BARS,
        "notional_usdt": NOTIONAL,
        "notional_meaning": "normalization_only",
        "primary_fee_scenario": PRIMARY_FEE,
        "fee_scenarios": FEE_SCENARIOS,
        "primary_slip_scenario": PRIMARY_SLIP,
        "slip_scenarios": SLIP_SCENARIOS,
        "funding_boundary_ms": FUNDING_BOUNDARY_MS,
        "control": {
            "algorithm": "H2-BR-mirror-v1",
            "p_denominator": CONTROL_P_DENOMINATOR,
            "runs": CONTROL_RUNS,
            "seed_root": SEED_ROOT,
            "b1_draws": B1_DRAWS,
            "h2_e2": "blocked_pending_user_acceptance",
        },
        "inference": {
            "holm_family": HOLM_FAMILY,
            "alpha": HOLM_ALPHA,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "block_bars": BLOCK_BARS,
            "block_sensitivity": list(BLOCK_SENSITIVITY),
            "primary_segment": "uncertified_holdout_candidate",
            "market_p_values": False,
        },
        "deviation_ids": [item["id"] for item in DEVIATIONS],
    }


def proposed_config_hash() -> str:
    return sha256_bytes(canonical(proposed_config()))


def primary_fee_rate() -> Decimal:
    return Decimal(FEE_SCENARIOS[PRIMARY_FEE])


def primary_slip() -> Decimal:
    return Decimal(SLIP_SCENARIOS[PRIMARY_SLIP])
