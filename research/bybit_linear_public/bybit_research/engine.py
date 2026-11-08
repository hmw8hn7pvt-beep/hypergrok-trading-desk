# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Deterministic offline comparison engine.

`run_book` evaluates an in-memory synthetic or caller-supplied series.
`run_market_performance` always refuses. Nothing in this module reads a
collected market bundle.
"""

from __future__ import annotations

from decimal import Decimal, getcontext

from bybit_research.config import (
    BAR_MS,
    COOLDOWN_BARS,
    D_MULTIPLIER,
    FUNDING_BOUNDARY_MS,
    MAX_HOLD_BARS,
    SIGMA_WINDOW,
    Z_ENTRY,
    Z_EXTREME,
    primary_fee_rate,
    primary_slip,
)
from bybit_research.rng import control_stream

getcontext().prec = 50

Z_ENTER = Decimal(Z_ENTRY)
Z_REJECT = Decimal(Z_EXTREME)
D_MULT = Decimal(D_MULTIPLIER)


class Unknown:
    def __repr__(self):
        return "UNKNOWN"


class ZeroSigma:
    def __repr__(self):
        return "ZERO_SIGMA"


UNKNOWN = Unknown()
ZERO_SIGMA = ZeroSigma()


class MarketPerformanceNotAuthorized(RuntimeError):
    pass


def run_market_performance(*_args, **_kwargs):
    raise MarketPerformanceNotAuthorized(
        "Real-market strategy performance is refused. Review RULES_PROPOSED and "
        "DATA_SUFFICIENCY first. This build has no approval switch, emits no market "
        "p-value, and does not open the holdout for strategy features or returns."
    )


def sample_std(values: list[Decimal]) -> Decimal:
    count = len(values)
    if count != SIGMA_WINDOW:
        raise ValueError("sigma requires the fixed 42-return window")
    mean = sum(values, Decimal(0)) / Decimal(count)
    ss = sum((value - mean) ** 2 for value in values)
    variance = ss / Decimal(count - 1)
    if variance == 0:
        return Decimal(0)
    return variance.sqrt()


def close_of(candles: dict, open_ms: int):
    bar = candles.get(open_ms)
    if bar is None:
        return UNKNOWN
    return bar["close"]


def sigma_at(candles: dict, open_ms: int):
    returns = []
    for offset in range(SIGMA_WINDOW):
        right = open_ms - (SIGMA_WINDOW - 1 - offset) * BAR_MS
        left = right - BAR_MS
        earlier, later = close_of(candles, left), close_of(candles, right)
        if earlier is UNKNOWN or later is UNKNOWN:
            return UNKNOWN
        returns.append((later / earlier).ln())
    return sample_std(returns)


def z_at(candles: dict, open_ms: int, n: int):
    sigma = sigma_at(candles, open_ms)
    if sigma is UNKNOWN:
        return UNKNOWN
    if sigma == 0:
        return ZERO_SIGMA
    now, then = close_of(candles, open_ms), close_of(candles, open_ms - n * BAR_MS)
    if now is UNKNOWN or then is UNKNOWN:
        return UNKNOWN
    return (now / then).ln() / (sigma * Decimal(n).sqrt())


def buy(reference: Decimal, slip: Decimal) -> Decimal:
    return reference * (Decimal(1) + slip)


def sell(reference: Decimal, slip: Decimal) -> Decimal:
    return reference * (Decimal(1) - slip)


def entry_price(side: int, open_px: Decimal, slip: Decimal) -> Decimal:
    return buy(open_px, slip) if side == 1 else sell(open_px, slip)


def stop_price(side: int, p_entry: Decimal, distance: Decimal) -> Decimal:
    if side == 1:
        return p_entry * (Decimal(1) - distance)
    return p_entry * (Decimal(1) + distance)


def stop_reference(side: int, stop: Decimal, open_px: Decimal) -> Decimal:
    if side == 1:
        return open_px if open_px < stop else stop
    return open_px if open_px > stop else stop


def stop_fill(side: int, p_entry: Decimal, distance: Decimal, bar: dict, slip: Decimal):
    stop = stop_price(side, p_entry, distance)
    triggered = bar["low"] <= stop if side == 1 else bar["high"] >= stop
    if not triggered:
        return None
    reference = stop_reference(side, stop, bar["open"])
    return sell(reference, slip) if side == 1 else buy(reference, slip)


def target_reached_at_open(side: int, open_px: Decimal, target: Decimal) -> bool:
    return open_px >= target if side == 1 else open_px <= target


def target_fill(side: int, target: Decimal, bar: dict, slip: Decimal):
    triggered = bar["high"] >= target if side == 1 else bar["low"] <= target
    if not triggered:
        return None
    # A favourable gap still fills at the target, then adverse slippage.
    return sell(target, slip) if side == 1 else buy(target, slip)


def funding_payment(side: int, quantity: Decimal, mark: Decimal, rate: Decimal) -> Decimal:
    """Positive means the position pays. Long pays when the rate is positive."""
    return side * quantity * mark * rate


def net_pnl(side: int, quantity: Decimal, p_entry: Decimal, p_exit: Decimal, fee_rate: Decimal, funding: Decimal) -> Decimal:
    gross = side * quantity * (p_exit - p_entry)
    fee = fee_rate * quantity * (p_entry + p_exit)
    return gross - fee - funding


def classify_funding(events: list[dict], entry_open: int, exit_kind: str, exit_open: int) -> tuple[list[dict], list[dict]]:
    if exit_kind == "exact":
        primary_lo = entry_open + FUNDING_BOUNDARY_MS
        primary_hi = exit_open - FUNDING_BOUNDARY_MS
        near_lo = entry_open - FUNDING_BOUNDARY_MS
        near_hi = exit_open + FUNDING_BOUNDARY_MS
    elif exit_kind == "intrabar":
        primary_lo = entry_open + FUNDING_BOUNDARY_MS
        primary_hi = exit_open
        near_lo = entry_open - FUNDING_BOUNDARY_MS
        near_hi = exit_open + BAR_MS + FUNDING_BOUNDARY_MS
    else:
        raise ValueError("exit kind must be exact or intrabar")
    certain, uncertain = [], []
    for event in events:
        tau = event["timestamp"]
        if primary_lo < tau < primary_hi:
            certain.append(event)
        elif near_lo <= tau <= near_hi:
            uncertain.append(event)
    return certain, uncertain


def cashflow(side: int, quantity: Decimal, events: list[dict]) -> tuple[object, list[dict], list[dict]]:
    payment = Decimal(0)
    known, unknown_marks = [], []
    for event in events:
        mark = event.get("mark")
        if not isinstance(mark, Decimal):
            unknown_marks.append(event)
            continue
        payment += funding_payment(side, quantity, mark, event["rate"])
        known.append(event)
    if unknown_marks:
        return UNKNOWN, known, unknown_marks
    return payment, known, []


def entry_allowed(entry_open: int, segment_end: int) -> bool:
    return entry_open + MAX_HOLD_BARS * BAR_MS < segment_end


def cooldown_allows(signal_open: int, cooldown_open) -> bool:
    return cooldown_open is None or signal_open >= cooldown_open


def mtm_snapshot(closed_net: Decimal, position: dict | None, mark, fee_rate: Decimal, slip: Decimal, funding_so_far: Decimal) -> dict:
    if position is None:
        return {"mtm": closed_net, "hypothetical_exit_cost": Decimal(0), "mark": mark}
    if not isinstance(mark, Decimal):
        return {"mtm": UNKNOWN, "hypothetical_exit_cost": UNKNOWN, "mark": UNKNOWN}
    side, quantity, p_entry = position["side"], position["q"], position["p_entry"]
    unrealized = side * quantity * (mark - p_entry)
    entry_fee = fee_rate * quantity * p_entry
    mtm = closed_net + unrealized - entry_fee - funding_so_far
    exit_reference = sell(mark, slip) if side == 1 else buy(mark, slip)
    slip_cost = side * quantity * (mark - exit_reference)
    exit_fee = fee_rate * quantity * exit_reference
    return {"mtm": mtm, "hypothetical_exit_cost": slip_cost + exit_fee, "mark": mark}


def _distance(sigma: Decimal, n: int) -> Decimal:
    return D_MULT * sigma * Decimal(n).sqrt()


def _invalidated(mode: str, hypothesis: str, side: int, z_signal: Decimal, z_now) -> bool:
    if z_now is UNKNOWN:
        return UNKNOWN
    if z_now is ZERO_SIGMA:
        return False
    if hypothesis == "H1":
        return side * z_now < 0
    if mode == "strategy":
        sign = Decimal(1) if z_signal > 0 else Decimal(-1)
        return sign * z_now >= Z_REJECT
    return side * z_now <= -Z_REJECT


def _decide(candles, open_ms, hypothesis, n, mode, rng):
    sigma = sigma_at(candles, open_ms)
    if sigma is UNKNOWN:
        return "unknown", "lookback_missing"
    if sigma == 0:
        return "skip", "zero_sigma"
    distance = _distance(sigma, n)
    if mode == "control":
        then_open = open_ms - n * BAR_MS
        if hypothesis == "H2" and (close_of(candles, open_ms) is UNKNOWN or close_of(candles, then_open) is UNKNOWN):
            return "unknown", "control_level_missing"
        if rng.randrange(18) != 0:
            return "none", None
        side = 1 if rng.randrange(2) == 0 else -1
        if side == 1 and distance >= 1:
            return "skip", "long_d_ge_1"
        target = None
        if hypothesis == "H2":
            now, earlier = close_of(candles, open_ms), close_of(candles, then_open)
            move = now - earlier
            if move == 0:
                return "skip", "h2_control_zero_move"
            target = now + Decimal(side) * abs(move)
        z_signal = z_at(candles, open_ms, n)
        return "entry", _order(hypothesis, n, side, sigma, distance, z_signal, target, open_ms)
    z_value = z_at(candles, open_ms, n)
    if z_value is UNKNOWN:
        return "unknown", "lookback_missing"
    if z_value is ZERO_SIGMA:
        return "skip", "zero_sigma"
    if hypothesis == "H1":
        if z_value >= Z_ENTER:
            side = 1
        elif z_value <= -Z_ENTER:
            side = -1
        else:
            return "none", None
        target = None
    elif hypothesis == "H2":
        if z_value >= Z_ENTER:
            side = -1
        elif z_value <= -Z_ENTER:
            side = 1
        else:
            return "none", None
        if abs(z_value) >= Z_REJECT:
            return "skip", "h2_abs_z_ge_3"
        target = close_of(candles, open_ms - n * BAR_MS)
        if target is UNKNOWN:
            return "unknown", "target_level_missing"
    else:
        raise ValueError("hypothesis must be H1 or H2")
    if side == 1 and distance >= 1:
        return "skip", "long_d_ge_1"
    return "entry", _order(hypothesis, n, side, sigma, distance, z_value, target, open_ms)


def _order(hypothesis, n, side, sigma, distance, z_signal, target, signal_open):
    return {
        "hypothesis": hypothesis,
        "n": n,
        "side": side,
        "sigma": sigma,
        "d": distance,
        "z_signal": z_signal if isinstance(z_signal, Decimal) else None,
        "target": target,
        "signal_open": signal_open,
    }


def _finalize(position, exit_open, p_exit, reason, exit_kind, events, fee_rate):
    certain, uncertain = classify_funding(events, position["entry_open"], exit_kind, exit_open)
    payment, _known, missing_marks = cashflow(position["side"], position["q"], certain)
    uncertain_missing = [event for event in uncertain if not isinstance(event.get("mark"), Decimal)]
    net = UNKNOWN if payment is UNKNOWN else net_pnl(
        position["side"], position["q"], position["p_entry"], p_exit, fee_rate, payment
    )
    return {
        **position,
        "exit_open": exit_open,
        "p_exit": p_exit,
        "exit_reason": reason,
        "exit_kind": exit_kind,
        "funding_primary": payment,
        "funding_uncertain_count": len(uncertain),
        "funding_exact_mark_missing": bool(missing_marks),
        "funding_uncertain_mark_missing": bool(uncertain_missing),
        "net": net,
        "status": "unknown" if net is UNKNOWN else "closed",
    }


def run_book(*, hypothesis, n, symbol, candles, segment_start, segment_end, clock_start,
             funding_events=None, fee_rate=None, slip=None, mode="strategy", run_index=0,
             mark_at_close=None, record_mtm=False):
    if hypothesis not in ("H1", "H2") or n not in (6, 18, 42) or mode not in ("strategy", "control"):
        raise ValueError("unsupported book request")
    if slip is None:
        slip = primary_slip()
    if fee_rate is None:
        fee_rate = primary_fee_rate()
    fee_rate, slip = Decimal(fee_rate), Decimal(slip)
    if fee_rate < 0 or slip < 0 or slip >= 1:
        raise ValueError("fee and slippage must be non-negative and slippage must be below 1")
    if clock_start > segment_start or segment_start >= segment_end:
        raise ValueError("segment bounds are inconsistent")
    if any(value % BAR_MS for value in (clock_start, segment_start, segment_end)):
        raise ValueError("bounds must be 4h aligned")
    visible = {open_ms: bar for open_ms, bar in candles.items() if clock_start <= open_ms < segment_end}
    for open_ms, bar in visible.items():
        if bar["high"] < bar["low"] or bar["high"] < max(bar["open"], bar["close"]) or bar["low"] > min(bar["open"], bar["close"]):
            raise ValueError("candle OHLC is inconsistent")
    events = funding_events or []
    rng = control_stream(hypothesis, n, symbol, run_index) if mode == "control" else None
    grid = list(range(clock_start, segment_end, BAR_MS))
    gaps = [open_ms for open_ms in grid if open_ms not in visible]
    primary_blocked = bool(gaps)
    data_gaps = [{"type": "data_gap", "open_ms": open_ms} for open_ms in gaps]
    unknowns, skips, trades, snapshots = [], [], [], []
    position = None
    pending_entry = None
    pending_exit = None
    cooldown_open = None
    unresolved = False
    closed_net = Decimal(0)

    def remember_unknown(open_ms, reason):
        nonlocal primary_blocked
        primary_blocked = True
        unknowns.append({"open_ms": open_ms, "reason": reason, "symbol": symbol})

    for open_ms in grid:
        bar = visible.get(open_ms)
        exited_intrabar = False
        if unresolved:
            continue
        if pending_exit is not None:
            if bar is None or position is None:
                remember_unknown(open_ms, "missing_exit_fill")
                if position is not None:
                    trades.append({**position, "status": "unknown", "net": UNKNOWN, "exit_reason": "unknown_gap", "exit_open": None})
                unresolved = True
                position = None
                pending_exit = None
                continue
            trade = _finalize(position, open_ms, exit_price_at_open(position, bar, slip), "queued_" + pending_exit, "exact", events, fee_rate)
            trades.append(trade)
            if trade["net"] is UNKNOWN:
                primary_blocked = True
            else:
                closed_net += trade["net"]
            cooldown_open = open_ms + COOLDOWN_BARS * BAR_MS
            position = None
            pending_exit = None
        if pending_entry is not None and position is None:
            if bar is None:
                remember_unknown(open_ms, "missing_entry_bar")
                unresolved = True
                pending_entry = None
                continue
            target = pending_entry["target"]
            if target is not None and target_reached_at_open(pending_entry["side"], bar["open"], target):
                skips.append({"open_ms": open_ms, "reason": "open_already_through_target", "signal_open": pending_entry["signal_open"], "symbol": symbol})
                pending_entry = None
            else:
                p_entry = entry_price(pending_entry["side"], bar["open"], slip)
                position = {**pending_entry, "symbol": symbol, "entry_open": open_ms, "p_entry": p_entry, "q": Decimal(1) / p_entry, "status": "open"}
                pending_entry = None
        if position is not None and position["status"] == "open":
            if bar is None:
                remember_unknown(open_ms, "missing_bar_while_open")
                trades.append({**position, "status": "unknown", "net": UNKNOWN, "exit_reason": "unknown_gap", "exit_open": None})
                position = None
                unresolved = True
                continue
            stopped = stop_fill(position["side"], position["p_entry"], position["d"], bar, slip)
            targeted = target_fill(position["side"], position["target"], bar, slip) if position["target"] is not None else None
            if stopped is not None or targeted is not None:
                if stopped is not None:
                    reason = "stop_before_target" if targeted is not None else "stop"
                    price = stopped
                else:
                    reason, price = "target", targeted
                trade = _finalize(position, open_ms, price, reason, "intrabar", events, fee_rate)
                trades.append(trade)
                if trade["net"] is UNKNOWN:
                    primary_blocked = True
                else:
                    closed_net += trade["net"]
                cooldown_open = open_ms + COOLDOWN_BARS * BAR_MS
                position = None
                exited_intrabar = True
        if record_mtm and not unresolved:
            mark = UNKNOWN if mark_at_close is None else mark_at_close(open_ms)
            certain_now, _uncertain_now = ([], [])
            funding_so_far = Decimal(0)
            if position is not None:
                certain_now, _uncertain_now = classify_funding(events, position["entry_open"], "exact", open_ms + BAR_MS)
                payment, _known, missing = cashflow(position["side"], position["q"], certain_now)
                funding_so_far = UNKNOWN if payment is UNKNOWN or missing else payment
            snap = mtm_snapshot(closed_net, position, mark, fee_rate, slip, funding_so_far if isinstance(funding_so_far, Decimal) else Decimal(0))
            if funding_so_far is UNKNOWN:
                snap = {"mtm": UNKNOWN, "hypothetical_exit_cost": snap["hypothetical_exit_cost"], "mark": mark}
            snapshots.append({"open_ms": open_ms, **snap})
        if exited_intrabar or unresolved or position is not None:
            if position is not None and not exited_intrabar:
                if open_ms == position["entry_open"] + (MAX_HOLD_BARS - 1) * BAR_MS:
                    pending_exit = "time"
                else:
                    z_now = z_at(visible, open_ms, n)
                    if z_now is UNKNOWN:
                        remember_unknown(open_ms, "unknown_invalidation_input")
                        trades.append({**position, "status": "unknown", "net": UNKNOWN, "exit_reason": "unknown_invalidation", "exit_open": None})
                        position = None
                        unresolved = True
                    elif _invalidated(mode, hypothesis, position["side"], position["z_signal"], z_now) is True:
                        pending_exit = "invalidation"
            continue
        if open_ms + BAR_MS < segment_start:
            continue
        entry_open = open_ms + BAR_MS
        if not entry_allowed(entry_open, segment_end) or not cooldown_allows(open_ms, cooldown_open):
            continue
        if bar is None:
            remember_unknown(open_ms, "missing_signal_bar")
            continue
        kind, payload = _decide(visible, open_ms, hypothesis, n, mode, rng)
        if kind == "unknown":
            remember_unknown(open_ms, payload)
        elif kind == "skip":
            skips.append({"open_ms": open_ms, "reason": payload, "symbol": symbol})
        elif kind == "entry":
            pending_entry = payload
    if position is not None:
        remember_unknown(grid[-1] if grid else segment_end, "position_open_at_segment_end")
        trades.append({**position, "status": "unknown", "net": UNKNOWN, "exit_reason": "segment_end_still_open", "exit_open": None})
        primary_blocked = True
    return {
        "symbol": symbol,
        "hypothesis": hypothesis,
        "n": n,
        "mode": mode,
        "run_index": run_index,
        "trades": trades,
        "skips": skips,
        "unknowns": unknowns,
        "data_gaps": data_gaps,
        "snapshots": snapshots,
        "primary_blocked": primary_blocked or unresolved or any(trade["status"] != "closed" for trade in trades),
        "unresolved": unresolved,
        "uses_bars_at_or_after_segment_end": False,
    }


def exit_price_at_open(position, bar, slip: Decimal) -> Decimal:
    return sell(bar["open"], slip) if position["side"] == 1 else buy(bar["open"], slip)
