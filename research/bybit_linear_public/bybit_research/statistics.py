# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Proposed pooled statistics. Synthetic inputs only; no market p-value is returned.

STAT-1b uses one bootstrap standard error for every replicate.
STAT-1 recomputes a jackknife SE inside each replicate and blocks if any is zero.
Both are unapproved. Degenerate samples return p = None.
"""

from __future__ import annotations

from decimal import Decimal, getcontext

from bybit_research.config import BLOCK_BARS, HOLM_ALPHA
from bybit_research.engine import UNKNOWN
from bybit_research.rng import bootstrap_stream

getcontext().prec = 50


def block_id(entry_ms: int, origin: int, block_bars: int, bar_ms: int) -> int:
    if entry_ms < origin:
        raise ValueError("entry is before the block origin")
    return (entry_ms - origin) // (block_bars * bar_ms)


def symbol_mean(nets: list[Decimal]):
    if not nets:
        return UNKNOWN
    return sum(nets, Decimal(0)) / Decimal(len(nets))


def pooled_theta(trades: list[dict], symbols: tuple[str, ...]):
    means = []
    for symbol in symbols:
        nets = [trade["net"] for trade in trades if trade["symbol"] == symbol]
        if any(not isinstance(net, Decimal) for net in nets):
            return UNKNOWN
        value = symbol_mean(nets)
        if value is UNKNOWN:
            return UNKNOWN
        means.append(value)
    if not means:
        return UNKNOWN
    return sum(means, Decimal(0)) / Decimal(len(means))


def control_symbol_mean(run_nets: list[list[Decimal]]):
    """Mean across runs of each run's per-trade mean. A run with no trades is undefined."""
    if not run_nets:
        return UNKNOWN
    means = []
    for nets in run_nets:
        value = symbol_mean(nets)
        if value is UNKNOWN:
            return UNKNOWN
        means.append(value)
    return sum(means, Decimal(0)) / Decimal(len(means))


def jackknife_se(block_thetas: list[Decimal]):
    count = len(block_thetas)
    if count < 2:
        return None
    full = sum(block_thetas, Decimal(0)) / Decimal(count)
    omitted = []
    for index in range(count):
        rest = block_thetas[:index] + block_thetas[index + 1:]
        omitted.append(sum(rest, Decimal(0)) / Decimal(count - 1))
    centre = sum(omitted, Decimal(0)) / Decimal(count)
    ss = sum((value - centre) ** 2 for value in omitted)
    variance = (Decimal(count - 1) / Decimal(count)) * ss
    if variance == 0:
        return Decimal(0)
    return variance.sqrt()


def monte_carlo_p(t_obs: Decimal, t_star: list[Decimal]) -> Decimal:
    hits = sum(1 for value in t_star if value >= t_obs)
    return Decimal(1 + hits) / Decimal(len(t_star) + 1)


def _grouped(trades, symbols, origin, block_bars, bar_ms):
    groups = {}
    for trade in trades:
        if not isinstance(trade.get("net"), Decimal):
            return None
        ident = block_id(trade["entry_ms"], origin, block_bars, bar_ms)
        groups.setdefault(ident, []).append(trade)
    return groups


def _theta_of(groups, chosen, symbols):
    selected = []
    for ident in chosen:
        selected.extend(groups.get(ident, []))
    return pooled_theta(selected, symbols)


def _occupied(groups, symbols):
    ready = []
    for ident in sorted(groups):
        if pooled_theta(groups[ident], symbols) is UNKNOWN:
            continue
        ready.append(ident)
    return ready


def evaluate_sample(*, trades, symbols, origin, bar_ms, label, replicates=99, block_bars=BLOCK_BARS, method="common_se"):
    """Return a descriptive statistic result. p is None whenever the sample is degenerate."""
    groups = _grouped(trades, symbols, origin, block_bars, bar_ms)
    if groups is None:
        return _blocked(method, "non_decimal_net")
    occupied = _occupied(groups, symbols)
    theta = pooled_theta([trade for rows in groups.values() for trade in rows], symbols)
    if theta is UNKNOWN or len(occupied) < 2:
        return _blocked(method, "undefined_theta_or_too_few_blocks")
    observed_blocks = [pooled_theta(groups[ident], symbols) for ident in occupied]
    observed_jack = jackknife_se(observed_blocks)
    if observed_jack is None or observed_jack <= 0:
        return _blocked(method, "observed_jackknife_se")
    stream = bootstrap_stream(f"{label}|{method}|{block_bars}|{replicates}")
    draws = []
    thetas = []
    for _ in range(replicates):
        chosen = [occupied[stream.randrange(len(occupied))] for _ in occupied]
        draws.append(chosen)
        value = _theta_of(groups, chosen, symbols)
        if value is UNKNOWN:
            return _blocked(method, "replicate_undefined_theta")
        thetas.append(value)
    se_boot = sample_std(thetas)
    if se_boot is None or se_boot <= 0:
        return _blocked(method, "bootstrap_se")
    if method == "common_se":
        t_obs = theta / se_boot
        t_star = [(value - theta) / se_boot for value in thetas]
        return _computed(method, theta, se_boot, monte_carlo_p(t_obs, t_star), t_obs)
    if method != "replicate_jackknife":
        raise ValueError("unknown statistic method")
    t_star = []
    for chosen in draws:
        value = _theta_of(groups, chosen, symbols)
        per_block = []
        for index in range(len(chosen)):
            rest = chosen[:index] + chosen[index + 1:]
            left = _theta_of(groups, rest, symbols)
            if left is UNKNOWN:
                return _blocked(method, "replicate_jackknife_undefined")
            per_block.append(left)
        se_inner = _se_from_deleted(per_block)
        if se_inner is None or se_inner <= 0:
            return _blocked(method, "replicate_inner_se")
        t_star.append((value - theta) / se_inner)
    t_obs = theta / se_boot
    return _computed(method, theta, se_boot, monte_carlo_p(t_obs, t_star), t_obs)


def _se_from_deleted(deleted: list[Decimal]):
    count = len(deleted)
    if count < 2:
        return None
    centre = sum(deleted, Decimal(0)) / Decimal(count)
    ss = sum((value - centre) ** 2 for value in deleted)
    # The deleted values are the leave-one estimates. Use the same jackknife scale.
    variance = (Decimal(count - 1) / Decimal(count)) * ss
    if variance == 0:
        return Decimal(0)
    return variance.sqrt()


def sample_std(values: list[Decimal]):
    count = len(values)
    if count < 2:
        return None
    mean = sum(values, Decimal(0)) / Decimal(count)
    ss = sum((value - mean) ** 2 for value in values)
    variance = ss / Decimal(count - 1)
    if variance == 0:
        return Decimal(0)
    return variance.sqrt()


def _blocked(method, reason):
    return {"method": method, "blocked": True, "reason": reason, "theta": None, "se": None, "p": None, "computed": False}


def _computed(method, theta, se, p_value, t_obs):
    return {
        "method": method,
        "blocked": False,
        "reason": None,
        "theta": theta,
        "se": se,
        "t": t_obs,
        "p": p_value,
        "computed": True,
        "market": False,
    }


def holm(rows: list[dict], alpha: Decimal | None = None) -> list[dict]:
    """Step-down Holm on a predeclared family. Uncomputed tests cannot reject."""
    alpha = Decimal(HOLM_ALPHA) if alpha is None else alpha
    family = len(rows)
    order = sorted(range(family), key=lambda index: rows[index]["p"] if rows[index].get("computed") else Decimal(1))
    prefix = True
    decisions = [False] * family
    for rank, index in enumerate(order):
        row = rows[index]
        if not prefix or not row.get("computed"):
            prefix = False
            decisions[index] = False
            continue
        threshold = alpha / Decimal(family - rank)
        if row["p"] <= threshold:
            decisions[index] = True
        else:
            prefix = False
            decisions[index] = False
    output = []
    for index, row in enumerate(rows):
        output.append({**row, "reject": decisions[index], "family_size": family})
    return output


def market_inference(*_args, **_kwargs):
    from bybit_research.engine import run_market_performance
    return run_market_performance()
