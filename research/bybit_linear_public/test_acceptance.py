# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Synthetic acceptance tests. No network and no market-history performance."""

from __future__ import annotations

import ast
import inspect
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from bybit_research.allowlist import AllowlistError, check_request
from bybit_research.collect import build_official_plan, execute
from bybit_research.config import (
    BAR_MS,
    BLOCK_BARS,
    DISCOVERY_START,
    HOLDOUT_END,
    HOLDOUT_START,
    SYMBOLS,
    WARMUP_START,
    proposed_config_hash,
)
from bybit_research.engine import (
    UNKNOWN,
    ZERO_SIGMA,
    MarketPerformanceNotAuthorized,
    buy,
    classify_funding,
    cooldown_allows,
    entry_allowed,
    entry_price,
    funding_payment,
    mtm_snapshot,
    net_pnl,
    run_book,
    run_market_performance,
    sample_std,
    sell,
    stop_fill,
    target_fill,
    z_at,
)
from bybit_research.http_client import AccessBlocked, PublicClient, RawResponse, public_url
from bybit_research.paginate import accept_kline_page, kline_windows, paginate_funding
from bybit_research.report import report_skeleton
from bybit_research.rng import control_stream, stream_seed
from bybit_research.schema import SchemaError, merge_observations, parse_kline_payload
from bybit_research.statistics import (
    evaluate_sample,
    holm,
    jackknife_se,
    market_inference,
    monte_carlo_p,
    pooled_theta,
)
from bybit_research.sufficiency import assess
from bybit_research.verify import verify_bundle


def aligned(value: int) -> int:
    return value - value % BAR_MS


def candle(open_ms, price, **overrides):
    bar = {
        "open_ms": open_ms,
        "open": Decimal(price),
        "high": Decimal(price),
        "low": Decimal(price),
        "close": Decimal(price),
    }
    bar.update(overrides)
    return bar


def series(base, closes, overrides=None):
    overrides = overrides or {}
    bars = {}
    previous = closes[0]
    for index, close in enumerate(closes):
        open_ms = base + index * BAR_MS
        bar = candle(
            open_ms,
            close,
            open=previous if index else close,
            high=max(previous if index else close, close),
            low=min(previous if index else close, close),
        )
        if index in overrides:
            bar.update(overrides[index])
        bars[open_ms] = bar
        previous = bar["close"]
    return bars


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def exchange(self, method, url, headers):
        self.calls.append({"method": method, "url": url, "headers": dict(headers)})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(responses):
    clock = Clock()
    transport = FakeTransport(responses)
    return PublicClient(transport=transport, sleep=clock.sleep, clock=clock), transport


def envelope(rows, symbol="BTCUSDT", category="linear"):
    return json.dumps({"retCode": 0, "retMsg": "OK", "result": {"category": category, "symbol": symbol, "list": rows}, "time": 1}).encode()


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.base = aligned(1_700_000_000_000)
        self.slip = Decimal("0.0005")
        self.fee = Decimal("0.00110")

    def test_allowlist_rejects_writes_credentials_and_other_hosts(self):
        with self.assertRaises(AllowlistError):
            check_request("POST", "/v5/market/kline", {"category": "linear", "symbol": "BTCUSDT"})
        with self.assertRaises(AllowlistError):
            check_request("GET", "/v5/order/create", {"category": "linear", "symbol": "BTCUSDT"})
        with self.assertRaises(AllowlistError):
            check_request("GET", "/v5/market/kline", {"category": "linear", "symbol": "BTCUSDT", "api_key": "x"})
        with self.assertRaises(AllowlistError):
            public_url("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        url = public_url("/v5/market/kline", {"category": "linear", "symbol": "BTCUSDT", "interval": "240"})
        self.assertTrue(url.startswith("https://api.bybit.com/v5/market/kline?"))
        self.assertNotIn("api.bytick.com", url)

    def test_access_block_stops_without_retry_or_second_request(self):
        body = b'{\n    error:The Amazon CloudFront distribution is configured to block access from your country\n}'
        made, transport = client([RawResponse(403, {"server": "CloudFront", "content-type": "application/json"}, body)])
        plan = [
            {"id": "0000", "type": "http", "kind": "instrument", "role": "preflight", "path": "/v5/market/instruments-info",
             "query": {"category": "linear", "symbol": "BTCUSDT"}},
            {"id": "0001", "type": "http", "kind": "instrument", "path": "/v5/market/instruments-info",
             "query": {"category": "linear", "symbol": "ETHUSDT"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            manifest = execute(plan, directory, client=made, as_of_ms=self.base + 100 * BAR_MS)
            self.assertEqual(manifest["result"], "blocked")
            self.assertFalse(manifest["strict_sufficient_for_primary"])
            self.assertEqual(manifest["market_performance"], "not_executed")
            self.assertEqual(len(transport.calls), 1)
            self.assertEqual(set(transport.calls[0]["headers"]), {"User-Agent", "Accept"})
            blocker = json.loads((Path(directory) / "blocker.json").read_text())
            self.assertTrue(blocker["country_block"])
            self.assertEqual(blocker["http_status"], 403)
            self.assertEqual(manifest["not_attempted_plan_ids"], ["0001"])
            verified = verify_bundle(directory)
            self.assertEqual(verified["verification"], "consistent")
            report = assess(directory)
            self.assertFalse(report["strict_sufficient_for_primary"])
            self.assertTrue(all(not item["strict_sufficient"] for item in report["symbols"].values()))
            self.assertIn("survivorship", report["survivor_bias"].lower())
            with self.assertRaises(RuntimeError):
                execute(plan, directory, client=made, as_of_ms=self.base + 100 * BAR_MS, resume=True)
        with self.assertRaises(AccessBlocked):
            made2, transport2 = client([RawResponse(403, {}, body), RawResponse(200, {}, b"{}")])
            made2.get_raw("/v5/market/kline", {"category": "linear", "symbol": "BTCUSDT", "interval": "240"})
            self.assertEqual(len(transport2.calls), 1)

    def test_retries_are_bounded_and_500_can_recover(self):
        good = envelope([[str(self.base), "1", "1", "1", "1", "2", "3"]])
        made, transport = client([
            RawResponse(500, {}, b"busy"),
            RawResponse(200, {}, good),
        ])
        url, response = made.get_raw("/v5/market/kline", {"category": "linear", "symbol": "BTCUSDT", "interval": "240", "start": str(self.base), "end": str(self.base), "limit": "1"})
        self.assertEqual(response.status, 200)
        self.assertEqual(len(transport.calls), 2)
        self.assertTrue(url.startswith("https://api.bybit.com/"))
        failing, calls = client([RawResponse(500, {}, b"busy") for _ in range(4)])
        with self.assertRaises(Exception):
            failing.get_raw("/v5/market/kline", {"category": "linear", "symbol": "BTCUSDT", "interval": "240"})
        self.assertEqual(len(calls.calls), 4)

    def test_schema_order_duplicates_and_pagination(self):
        later = [str(self.base + BAR_MS), "2", "3", "1.5", "2.5", "4", "8"]
        earlier = [str(self.base), "1", "1.2", "0.9", "1.1", "3", "5"]
        rows = parse_kline_payload(json.loads(envelope([later, earlier])), symbol="BTCUSDT", category="linear", kind="last", step_ms=BAR_MS)
        self.assertEqual([row["open_ms"] for row in rows], [self.base + BAR_MS, self.base])
        kept, conflict = merge_observations(rows + [dict(rows[1])], "open_ms")
        self.assertIsNone(conflict)
        self.assertEqual(len(kept), 2)
        broken = dict(rows[0])
        broken["close"] = Decimal("9")
        _kept, conflict = merge_observations([rows[0], broken], "open_ms")
        self.assertEqual(conflict, "conflicting_duplicate")
        with self.assertRaises(SchemaError):
            parse_kline_payload(json.loads(envelope([[str(self.base), "1", "1", "2", "1", "1", "1"]])), symbol="BTCUSDT", category="linear", kind="last", step_ms=BAR_MS)
        with self.assertRaises(SchemaError):
            parse_kline_payload(json.loads(envelope([[str(self.base), "1", "1", "1", "1", "1", "1"]])), symbol="BTCUSDT", category="linear", kind="mark", step_ms=BAR_MS)
        with self.assertRaises(SchemaError):
            accept_kline_page([{"open_ms": self.base + BAR_MS}], self.base, self.base + BAR_MS, BAR_MS, limit=1)
        windows = kline_windows(WARMUP_START, HOLDOUT_END, BAR_MS)
        self.assertLessEqual(len(windows), 20)
        self.assertEqual(windows[0][0], WARMUP_START)
        self.assertEqual(windows[-1][1], HOLDOUT_END)

        fixed = self.base + 10 * BAR_MS - 1

        def stuck(start, end_inclusive, limit):
            return [{"timestamp": fixed, "rate": Decimal("0.1"), "symbol": "BTCUSDT"}]

        with self.assertRaises(SchemaError):
            paginate_funding(stuck, self.base, self.base + 10 * BAR_MS, limit=1, max_pages=5)
        pages = {"n": 0}

        def budget(start, end_inclusive, limit):
            pages["n"] += 1
            stamp = end_inclusive - pages["n"] * 1000
            return [{"timestamp": stamp, "rate": Decimal("0.01"), "symbol": "BTCUSDT"} for _ in range(limit)]

        result = paginate_funding(budget, self.base, self.base + 10_000_000, limit=2, max_pages=3)
        self.assertFalse(result["complete"])
        self.assertEqual(result["reason"], "page_budget")

    def test_missing_observation_is_unknown_not_a_flat_skip(self):
        closes = [Decimal(100)] * 80
        closes[50] = Decimal(130)
        bars = series(self.base, closes)
        self.assertIs(z_at(bars, self.base + 48 * BAR_MS, 6), ZERO_SIGMA)
        missing = dict(bars)
        del missing[self.base + 40 * BAR_MS]
        self.assertIs(z_at(missing, self.base + 50 * BAR_MS, 6), UNKNOWN)
        result = run_book(
            hypothesis="H1", n=6, symbol="BTCUSDT", candles=missing,
            segment_start=self.base + 51 * BAR_MS, segment_end=self.base + 80 * BAR_MS, clock_start=self.base,
            fee_rate=self.fee, slip=self.slip,
        )
        self.assertTrue(result["primary_blocked"])
        self.assertTrue(result["data_gaps"])
        self.assertTrue(any(trade["status"] == "unknown" for trade in result["trades"]) or result["unknowns"] or result["unresolved"])
        self.assertFalse(any(skip["reason"] == "zero_sigma" and skip["open_ms"] == self.base + 40 * BAR_MS for skip in result["skips"]))

    def test_signal_uses_no_future_close_and_enters_next_bar(self):
        closes = [Decimal(100)] * 80
        closes[50] = Decimal(130)
        for index in range(51, 80):
            closes[index] = Decimal(130)
        bars = series(self.base, closes)
        signal = self.base + 50 * BAR_MS
        before = z_at(bars, signal, 6)
        self.assertGreaterEqual(before, Decimal(2))
        self.assertLess(before, Decimal(3))
        changed = dict(bars)
        future = signal + 5 * BAR_MS
        changed[future] = candle(future, "1")
        self.assertEqual(z_at(changed, signal, 6), before)
        changed[signal] = candle(signal, "100")
        self.assertIs(z_at(changed, signal, 6), ZERO_SIGMA)
        result = self.book(bars)
        trade = result["trades"][0]
        self.assertEqual(trade["signal_open"], signal)
        self.assertEqual(trade["entry_open"], signal + BAR_MS)
        self.assertEqual(trade["side"], 1)
        self.assertGreater(trade["exit_open"], trade["entry_open"])
        self.assertEqual(trade["q"], Decimal(1) / trade["p_entry"])
        self.assertEqual(trade["exit_reason"], "queued_time")

    def test_stop_gap_stop_priority_target_gap_and_cancel(self):
        closes = [Decimal(100)] * 80
        closes[50] = Decimal(130)
        for index in range(51, 80):
            closes[index] = Decimal(130)
        gap = series(self.base, closes, {52: {"open": Decimal(10), "high": Decimal(10), "low": Decimal(9), "close": Decimal(10)}})
        stopped = self.book(gap)["trades"][0]
        self.assertEqual(stopped["exit_reason"], "stop")
        self.assertEqual(stopped["entry_open"], self.base + 51 * BAR_MS)
        self.assertEqual(stopped["exit_open"], self.base + 52 * BAR_MS)
        self.assertEqual(stopped["p_exit"], Decimal(10) * (Decimal(1) - self.slip))
        wide = series(self.base, closes, {51: {"open": Decimal(130), "high": Decimal(1000), "low": Decimal(1), "close": Decimal(130)}})
        both = run_book(
            hypothesis="H2", n=6, symbol="BTCUSDT", candles=wide,
            segment_start=self.base + 51 * BAR_MS, segment_end=self.base + 80 * BAR_MS, clock_start=self.base,
            fee_rate=self.fee, slip=self.slip,
        )["trades"][0]
        self.assertEqual(both["exit_reason"], "stop_before_target")
        self.assertEqual(both["p_exit"], stop_fill(both["side"], both["p_entry"], both["d"], wide[both["entry_open"]], self.slip))
        self.assertNotEqual(both["p_exit"], target_fill(both["side"], both["target"], wide[both["entry_open"]], self.slip))
        later = series(self.base, closes, {52: {"open": Decimal(90), "high": Decimal(90), "low": Decimal(80), "close": Decimal(85)}})
        favourable = run_book(
            hypothesis="H2", n=6, symbol="BTCUSDT", candles=later,
            segment_start=self.base + 51 * BAR_MS, segment_end=self.base + 80 * BAR_MS, clock_start=self.base,
            fee_rate=self.fee, slip=self.slip,
        )["trades"][0]
        self.assertEqual(favourable["exit_reason"], "target")
        self.assertEqual(favourable["p_exit"], Decimal(100) * (Decimal(1) + self.slip))
        self.assertGreater(favourable["p_exit"], Decimal(90))
        cancelled = series(self.base, closes, {51: {"open": Decimal(100), "high": Decimal(100), "low": Decimal(100), "close": Decimal(100)}})
        result = run_book(
            hypothesis="H2", n=6, symbol="BTCUSDT", candles=cancelled,
            segment_start=self.base + 51 * BAR_MS, segment_end=self.base + 80 * BAR_MS, clock_start=self.base,
            fee_rate=self.fee, slip=self.slip,
        )
        self.assertEqual(result["trades"], [])
        self.assertTrue(any(skip["reason"] == "open_already_through_target" for skip in result["skips"]))

    def test_fees_funding_timing_and_no_double_counting(self):
        self.assertEqual(funding_payment(1, Decimal(1), Decimal(100), Decimal("0.01")), Decimal(1))
        self.assertEqual(funding_payment(-1, Decimal(1), Decimal(100), Decimal("0.01")), Decimal(-1))
        self.assertLess(funding_payment(1, Decimal("0.5"), Decimal(80), Decimal("-0.02")), 0)
        entry, exit_open = self.base, self.base + 10 * BAR_MS
        certain, uncertain = classify_funding(
            [
                {"timestamp": entry, "rate": Decimal("0.1")},
                {"timestamp": entry + 5000, "rate": Decimal("0.1")},
                {"timestamp": entry + 5001, "rate": Decimal("0.2")},
                {"timestamp": exit_open - 5001, "rate": Decimal("0.3")},
                {"timestamp": exit_open, "rate": Decimal("0.4")},
                {"timestamp": exit_open + BAR_MS, "rate": Decimal("0.5")},
            ],
            entry, "exact", exit_open,
        )
        self.assertEqual([event["rate"] for event in certain], [Decimal("0.2"), Decimal("0.3")])
        self.assertIn(Decimal("0.1"), [event["rate"] for event in uncertain])
        closes = [Decimal(100)] * 80
        closes[50] = Decimal(130)
        for index in range(51, 80):
            closes[index] = Decimal(130)
        bars = series(self.base, closes)
        entry_open = self.base + 51 * BAR_MS
        exit_at = entry_open + 18 * BAR_MS
        events = [
            {"timestamp": entry_open, "rate": Decimal("0.01"), "mark": Decimal(130)},
            {"timestamp": entry_open + 9 * BAR_MS, "rate": Decimal("0.0001"), "mark": Decimal(130)},
        ]
        trade = self.book(bars, funding_events=events)["trades"][0]
        plain = self.book(bars)["trades"][0]
        payment = funding_payment(1, trade["q"], Decimal(130), Decimal("0.0001"))
        self.assertEqual(trade["net"], plain["net"] - payment)
        gross = trade["side"] * trade["q"] * (trade["p_exit"] - trade["p_entry"])
        fee = self.fee * trade["q"] * (trade["p_entry"] + trade["p_exit"])
        self.assertEqual(trade["net"], gross - fee - payment)
        self.assertEqual(trade["funding_uncertain_count"], 1)
        self.assertEqual(trade["p_entry"], entry_price(1, Decimal(130), self.slip))
        self.assertEqual(trade["p_exit"], sell(Decimal(130), self.slip))
        self.assertNotIn("slippage", trade)

    def test_mark_to_market_keeps_hypothetical_exit_separate(self):
        position = {"side": 1, "q": Decimal("0.01"), "p_entry": Decimal(100)}
        snap = mtm_snapshot(Decimal(5), position, Decimal(110), self.fee, self.slip, Decimal("0.25"))
        unrealized = Decimal("0.01") * (Decimal(110) - Decimal(100))
        entry_fee = self.fee * Decimal("0.01") * Decimal(100)
        self.assertEqual(snap["mtm"], Decimal(5) + unrealized - entry_fee - Decimal("0.25"))
        self.assertGreater(snap["hypothetical_exit_cost"], 0)
        self.assertNotEqual(snap["mtm"], snap["mtm"] - snap["hypothetical_exit_cost"])
        missing = mtm_snapshot(Decimal(5), position, UNKNOWN, self.fee, self.slip, Decimal(0))
        self.assertIs(missing["mtm"], UNKNOWN)
        self.assertIs(missing["hypothetical_exit_cost"], UNKNOWN)

    def test_cooldown_segment_isolation_and_counted_skips(self):
        self.assertFalse(entry_allowed(self.base, self.base + 18 * BAR_MS))
        self.assertTrue(entry_allowed(self.base, self.base + 19 * BAR_MS))
        self.assertFalse(cooldown_allows(100, 106))
        self.assertTrue(cooldown_allows(106, 106))
        closes = [Decimal(100)] * 80
        closes[50] = Decimal(130)
        for index in range(51, 80):
            closes[index] = Decimal(130)
        gap = series(self.base, closes, {51: {"open": Decimal(50), "high": Decimal(50), "low": Decimal(40), "close": Decimal(45)}})
        stopped = self.book(gap)
        signals = [trade["signal_open"] for trade in stopped["trades"]]
        forbidden = {self.base + index * BAR_MS for index in range(51, 57)}
        self.assertTrue(set(signals).isdisjoint(forbidden))
        # A bar exactly at the segment end is invisible and cannot change the book.
        wild_end = self.base + 80 * BAR_MS
        bars = series(self.base, closes)
        bars[wild_end] = candle(wild_end, "1")
        isolated = self.book(bars)
        self.assertTrue(all(trade["exit_open"] < wild_end for trade in isolated["trades"]))
        self.assertEqual(
            [trade["exit_open"] for trade in isolated["trades"]],
            [trade["exit_open"] for trade in self.book(series(self.base, closes))["trades"]],
        )
        huge = [Decimal(100)] * 80
        huge[50] = Decimal(100) * Decimal(2).exp()
        for index in range(51, 80):
            huge[index] = huge[50]
        skipped = self.book(series(self.base, huge))
        self.assertEqual(skipped["trades"], [])
        self.assertTrue(any(skip["reason"] == "long_d_ge_1" for skip in skipped["skips"]))
        drifted = self._drifted()
        rejected = run_book(
            hypothesis="H2", n=6, symbol="BTCUSDT", candles=drifted,
            segment_start=self.base + 51 * BAR_MS, segment_end=self.base + 80 * BAR_MS, clock_start=self.base,
            fee_rate=self.fee, slip=self.slip,
        )
        self.assertTrue(any(skip["reason"] == "h2_abs_z_ge_3" for skip in rejected["skips"]))
        flat = self.book(series(self.base, [Decimal(100)] * 80))
        self.assertEqual(flat["trades"], [])
        self.assertTrue(any(skip["reason"] == "zero_sigma" for skip in flat["skips"]))
        self.assertEqual(flat["unknowns"], [])

    def test_randomized_control_is_reproducible_and_outcome_independent(self):
        closes = [Decimal(100)] * 90
        closes[50] = Decimal(130)
        for index in range(51, 90):
            closes[index] = Decimal(130)
        bars = series(self.base, closes)
        kwargs = dict(
            hypothesis="H2", n=6, symbol="BTCUSDT", candles=bars, mode="control", run_index=0,
            segment_start=self.base + 51 * BAR_MS, segment_end=self.base + 90 * BAR_MS, clock_start=self.base,
            fee_rate=self.fee, slip=self.slip,
        )
        first = run_book(**kwargs)
        second = run_book(**kwargs)
        self.assertEqual(
            [(trade["signal_open"], trade["side"], trade["target"]) for trade in first["trades"]],
            [(trade["signal_open"], trade["side"], trade["target"]) for trade in second["trades"]],
        )
        self.assertTrue(first["trades"])
        trade = first["trades"][0]
        now = bars[trade["signal_open"]]["close"]
        earlier = bars[trade["signal_open"] - 6 * BAR_MS]["close"]
        self.assertEqual(trade["target"], now + Decimal(trade["side"]) * abs(now - earlier))
        mutated = dict(bars)
        mutated[trade["entry_open"] + 3 * BAR_MS] = candle(trade["entry_open"] + 3 * BAR_MS, "1")
        again = run_book(**{**kwargs, "candles": mutated})
        self.assertEqual(again["trades"][0]["signal_open"], trade["signal_open"])
        self.assertEqual(again["trades"][0]["side"], trade["side"])
        self.assertNotEqual(stream_seed("bybit-linear-proposed-h2br-v1|H2|6|BTCUSDT|0|20261109"), stream_seed("bybit-linear-proposed-h2br-v1|H2|6|BTCUSDT|1|20261109"))
        self.assertEqual(control_stream("H2", 6, "BTCUSDT", 0).randrange(18), control_stream("H2", 6, "BTCUSDT", 0).randrange(18))
        signature = inspect.signature(run_book)
        self.assertTrue({"leverage", "qty_step", "min_notional", "max_leverage"}.isdisjoint(signature.parameters))

    def test_statistics_block_degenerates_and_holm_uses_the_whole_family(self):
        self.assertIs(pooled_theta([], ("BTCUSDT",)), UNKNOWN)
        self.assertIs(pooled_theta([{"symbol": "BTCUSDT", "net": Decimal(1)}], ("BTCUSDT", "ETHUSDT")), UNKNOWN)
        self.assertEqual(jackknife_se([Decimal(0), Decimal(2)]), Decimal(1))
        self.assertEqual(monte_carlo_p(Decimal(2), [Decimal(0), Decimal(1), Decimal(3)]), Decimal("0.5"))
        one_block = evaluate_sample(
            trades=[{"symbol": "BTCUSDT", "entry_ms": self.base, "net": Decimal(1)}],
            symbols=("BTCUSDT",), origin=self.base, bar_ms=BAR_MS, label="one", replicates=10, block_bars=BLOCK_BARS,
        )
        self.assertTrue(one_block["blocked"])
        self.assertIsNone(one_block["p"])
        trades = []
        for block, net in ((0, Decimal(0)), (1, Decimal(4))):
            for symbol in ("BTCUSDT", "ETHUSDT"):
                trades.append({"symbol": symbol, "entry_ms": self.base + block * BLOCK_BARS * BAR_MS, "net": net if symbol == "BTCUSDT" else Decimal(0)})
        left = evaluate_sample(trades=trades, symbols=("BTCUSDT", "ETHUSDT"), origin=self.base, bar_ms=BAR_MS, label="pair", replicates=20, method="common_se")
        right = evaluate_sample(trades=trades, symbols=("BTCUSDT", "ETHUSDT"), origin=self.base, bar_ms=BAR_MS, label="pair", replicates=20, method="common_se")
        self.assertEqual(left, right)
        self.assertFalse(left["blocked"])
        self.assertGreater(left["se"], 0)
        nested = evaluate_sample(trades=trades, symbols=("BTCUSDT", "ETHUSDT"), origin=self.base, bar_ms=BAR_MS, label="pair-jack", replicates=30, method="replicate_jackknife")
        self.assertTrue(nested["blocked"])
        self.assertIsNone(nested["p"])
        rows = [{"id": index, "p": Decimal("0.01"), "computed": True} for index in range(11)]
        rows.append({"id": "E2-H2", "p": None, "computed": False})
        decisions = holm(rows)
        self.assertEqual(len(decisions), 12)
        self.assertFalse(decisions[-1]["reject"] if decisions[-1]["id"] == "E2-H2" else any(row["id"] == "E2-H2" and row["reject"] for row in decisions))
        self.assertTrue(any(row["id"] == "E2-H2" and row["reject"] is False for row in decisions))
        with self.assertRaises(MarketPerformanceNotAuthorized):
            market_inference()

    def test_skeleton_and_performance_refusal(self):
        skeleton = report_skeleton()
        self.assertEqual(len(skeleton["cells"]), 24)
        self.assertEqual(len(skeleton["holm_family"]), 12)
        self.assertEqual(skeleton["config_sha256"], proposed_config_hash())
        self.assertEqual(proposed_config_hash(), proposed_config_hash())
        blocked = [row for row in skeleton["holm_family"] if row["hypothesis"] == "H2" and row["endpoint"] == "E2"]
        self.assertEqual(len(blocked), 3)
        self.assertTrue(all(row["p_computed"] is False and row["p_placeholder"] == 1 for row in blocked))
        self.assertTrue(all(cell["market_performance"] == "not_executed" and cell["p"] is None for cell in skeleton["cells"]))
        with self.assertRaises(MarketPerformanceNotAuthorized):
            run_market_performance({"bundle": "market.csv"})
        from bybit_research.cli import main
        self.assertEqual(main(["performance"]), 3)
        self.assertEqual(main(["config-hash"]), 0)

    def test_plan_is_bounded_and_modules_stay_isolated(self):
        plan = build_official_plan()
        self.assertEqual(plan[0]["role"], "preflight")
        self.assertLess(len(plan), 80)
        self.assertLess(len(kline_windows(WARMUP_START, HOLDOUT_END, BAR_MS)) * 2 * len(SYMBOLS) + 40 * len(SYMBOLS) + 20, 400)
        for item in plan:
            if item["type"] == "http":
                check_request("GET", item["path"], item["query"])
        root = Path(__file__).resolve().parents[0]
        collect_tree = ast.parse((root / "bybit_research" / "collect.py").read_text())
        engine_tree = ast.parse((root / "bybit_research" / "engine.py").read_text())
        collect_imports = [node.module for node in ast.walk(collect_tree) if isinstance(node, ast.ImportFrom)]
        engine_imports = [node.module for node in ast.walk(engine_tree) if isinstance(node, ast.ImportFrom)]
        self.assertNotIn("bybit_research.engine", collect_imports)
        self.assertNotIn("bybit_research.collect", engine_imports)
        http_source = (root / "bybit_research" / "http_client.py").read_text()
        self.assertIn("ProxyHandler({})", http_source)
        self.assertIn("api.bybit.com", http_source)
        self.assertNotIn("api.bytick.com", http_source)

    def test_holdout_rows_stay_out_of_the_exploratory_file(self):
        discovery = [str(DISCOVERY_START), "1", "1", "1", "1", "2", "3"]
        holdout = [str(HOLDOUT_START), "2", "2", "2", "2", "2", "4"]
        plan = [{
            "id": "0000", "type": "klines", "kind": "last", "symbol": "BTCUSDT", "interval": "240",
            "start": DISCOVERY_START, "end": DISCOVERY_START + BAR_MS,
        }]
        # The official assembler classifies any returned candle. One request window is only the discovery slot,
        # so the fake response must stay inside that window. Split behaviour is checked with a direct writer.
        with tempfile.TemporaryDirectory() as directory:
            from bybit_research.collect import _assemble
            pages = [{
                "expect": "last",
                "symbol": "BTCUSDT",
                "rows": parse_kline_payload(json.loads(envelope([holdout, discovery])), symbol="BTCUSDT", category="linear", kind="last", step_ms=BAR_MS),
            }]
            _assemble(Path(directory), pages, as_of_ms=HOLDOUT_END + BAR_MS)
            exploratory = (Path(directory) / "normalized" / "exploratory" / "BTCUSDT_last_4h.csv").read_text().splitlines()
            holdout_file = (Path(directory) / "normalized" / "holdout" / "BTCUSDT_last_4h.csv").read_text().splitlines()
            self.assertNotIn("z", exploratory[0].split(","))
            self.assertNotIn("net", exploratory[0].split(","))
            self.assertTrue(any(str(DISCOVERY_START) in line for line in exploratory[1:]))
            self.assertFalse(any(str(HOLDOUT_START) in line for line in exploratory[1:]))
            self.assertTrue(any(str(HOLDOUT_START) in line for line in holdout_file[1:]))
            self.assertFalse(any("signal" in line for line in holdout_file))

    def book(self, bars, **kwargs):
        return run_book(
            hypothesis="H1", n=6, symbol="BTCUSDT", candles=bars,
            segment_start=self.base + 51 * BAR_MS, segment_end=self.base + 80 * BAR_MS, clock_start=self.base,
            fee_rate=self.fee, slip=self.slip, **kwargs,
        )

    def _drifted(self):
        price = Decimal(100)
        closes = []
        returns = [Decimal("0.01")] * 41 + [Decimal("0.011")]
        # 42 returns need 43 closes. Pad the earlier history flat.
        closes.extend([price] * (80 - 43))
        for ret in returns:
            price *= ret.exp()
            closes.append(price)
        while len(closes) < 80:
            closes.append(price)
        return series(self.base, closes)


if __name__ == "__main__":
    unittest.main()
