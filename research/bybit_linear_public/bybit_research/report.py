# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Report skeleton. Cells stay descriptive and market performance stays unexecuted."""

from __future__ import annotations

from bybit_research.config import HYPOTHESES, N_VALUES, SYMBOLS, proposed_config_hash


def report_skeleton() -> dict:
    cells = []
    for hypothesis in HYPOTHESES:
        for n in N_VALUES:
            for symbol in SYMBOLS:
                cells.append({
                    "hypothesis": hypothesis,
                    "n": n,
                    "symbol": symbol,
                    "role": "descriptive",
                    "market_performance": "not_executed",
                    "p": None,
                    "pass": None,
                    "conditional_symbol": symbol in ("SOLUSDT", "XRPUSDT"),
                })
    family = []
    for hypothesis in HYPOTHESES:
        for n in N_VALUES:
            for endpoint in ("E1", "E2"):
                blocked = hypothesis == "H2" and endpoint == "E2"
                family.append({
                    "id": f"{endpoint}-{hypothesis}-N{n}",
                    "endpoint": endpoint,
                    "hypothesis": hypothesis,
                    "n": n,
                    "status": "blocked_pending_h2_control_acceptance" if blocked else "not_executed",
                    "p_computed": False,
                    "p_placeholder": 1 if blocked else None,
                    "placeholder_is_not_a_computed_p": blocked,
                })
    if len(cells) != 24 or len(family) != 12:
        raise RuntimeError("report skeleton lost its predeclared shape")
    return {
        "config_sha256": proposed_config_hash(),
        "cells": cells,
        "pooled_equal_symbol": "not_executed",
        "holm_family": family,
        "exploratory_segments": ["discovery", "validation"],
        "holdout_segment": "unopened_for_strategy_analysis",
        "blind_certification": "not_certified",
        "inferential_market_status": "not_run",
        "notional": "1 USDT is normalization only. It is not an order size, a balance, or capital.",
        "portfolio_disclaimer": "No portfolio, liquidation, margin, or executable-fill claim is made.",
        "fees": "S-std and S-inn are conditional public scenarios, not historical or personal tariffs.",
        "survivor_bias": (
            "The four names are a fixed retrospective set. SOLUSDT and XRPUSDT were ranked inside "
            "six contracts that were still listed when that selection note was written. Closed or "
            "delisted contracts were not in that candidate set."
        ),
    }
