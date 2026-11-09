# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Offline tests for the public ticker feed. No socket and no Bybit call."""

from __future__ import annotations

import json
import socket
import unittest
from pathlib import Path

import bybit_research.live_socket as live_socket
from bybit_research.cli import main
from bybit_research.live_public import (
    SYMBOLS,
    FeedClosed,
    LiveConfig,
    ManualClock,
    PublicFeed,
    client_message,
    execute_finite_live,
    render_table,
    run_feed,
    validate_live_invocation,
    check_public_linear_url,
)


def _block_network(*_args, **_kwargs):
    raise AssertionError("live tests must not open a socket")


socket.create_connection = _block_network


def tick(symbol, kind, fields, ts, cs):
    return json.dumps({
        "topic": f"tickers.{symbol}",
        "type": kind,
        "data": {"symbol": symbol, **fields},
        "ts": ts,
        "cs": cs,
    })


def ack(symbol, success=True, ret=""):
    return json.dumps({"success": success, "ret_msg": ret, "op": "subscribe", "req_id": symbol})


class ScriptTransport:
    def __init__(self, clock, steps):
        self.clock = clock
        self.steps = list(steps)
        self.sent = []
        self.connects = 0

    def connect(self):
        self.connects += 1

    def send(self, text):
        self.sent.append(json.loads(text))

    def recv(self, _timeout_ms):
        if not self.steps:
            raise FeedClosed("end of script")
        kind, payload = self.steps.pop(0)
        if kind == "advance":
            self.clock.advance(payload)
            return None
        if kind == "close":
            raise FeedClosed("peer closed")
        return payload

    def close(self):
        return None


class LiveFeedTests(unittest.TestCase):
    def setUp(self):
        self.clock = ManualClock(1_000_000)
        self.config = LiveConfig(ping_interval_ms=1_000, pong_timeout_ms=500, receive_stale_ms=5_000, exchange_stale_ms=5_000, max_reconnects=1)
        self.feed = PublicFeed(self.config)

    def open_feed(self):
        sent = []
        self.feed.on_open(sent.append, self.clock.time_ms())
        return sent

    def test_url_and_client_messages_stay_on_the_public_topic(self):
        check_public_linear_url("wss://stream.bybit.com/v5/public/linear")
        for blocked in (
            "wss://stream-testnet.bybit.com/v5/public/linear",
            "wss://stream.bybit.tr/v5/public/linear",
            "wss://stream.bybit.com/v5/private",
            "wss://stream.bybit.com/v5/trade",
            "wss://stream.bybit.com/v5/public/linear?api_key=secret",
            "wss://api.bybit.com/v5/public/linear",
        ):
            with self.assertRaises(Exception):
                check_public_linear_url(blocked)
        with self.assertRaises(Exception):
            client_message("auth", ["key"])
        with self.assertRaises(Exception):
            client_message("subscribe", ["orderbook.1.BTCUSDT"])
        ping = json.loads(client_message("ping"))
        self.assertEqual(ping, {"op": "ping"})
        self.assertNotIn("api_key", client_message("subscribe", ["tickers.BTCUSDT"], req_id="BTCUSDT"))

    def test_ack_is_not_a_healthy_quote_and_idle_stays_unavailable(self):
        self.open_feed()
        now = self.clock.time_ms()
        self.feed.on_message(ack("BTCUSDT"), now)
        row = self.feed.status_rows(now)[0]
        self.assertEqual(row["state"], "AWAITING_SNAPSHOT")
        self.assertEqual(row["last"], "UNAVAILABLE")
        self.assertNotEqual(self.feed.feed_state(now), "LIVE")
        self.clock.advance(5_001)
        self.feed.on_clock(lambda _text: None, self.clock.time_ms())
        row = self.feed.status_rows(self.clock.time_ms())[0]
        self.assertEqual(row["state"], "IDLE")
        self.assertEqual(row["last"], "UNAVAILABLE")
        self.assertEqual(row["mark"], "UNAVAILABLE")

    def test_snapshot_delta_missing_and_reset(self):
        self.open_feed()
        now = self.clock.time_ms()
        self.feed.on_message(ack("BTCUSDT"), now)
        self.feed.on_message(tick("BTCUSDT", "delta", {"lastPrice": "9", "markPrice": "9"}, now, 2), now)
        self.assertEqual(self.feed.status_rows(now)[0]["state"], "AWAITING_SNAPSHOT")
        self.feed.on_message(tick("BTCUSDT", "snapshot", {"lastPrice": "10", "markPrice": "11"}, now, 5), now)
        row = self.feed.status_rows(now)[0]
        self.assertEqual((row["state"], row["last"], row["mark"]), ("LIVE", "10", "11"))
        self.feed.on_message(tick("BTCUSDT", "delta", {"markPrice": "12"}, now, 6), now)
        row = self.feed.status_rows(now)[0]
        self.assertEqual((row["last"], row["mark"]), ("10", "12"))
        self.feed.on_message(tick("BTCUSDT", "snapshot", {"lastPrice": "", "markPrice": "0.00"}, now, 7), now)
        row = self.feed.status_rows(now)[0]
        self.assertEqual(row["state"], "INCOMPLETE")
        self.assertEqual(row["last"], "UNAVAILABLE")
        self.assertEqual(row["mark"], "UNAVAILABLE")
        self.feed.on_message(tick("BTCUSDT", "snapshot", {"lastPrice": "20", "markPrice": "21"}, now, 8), now)
        self.feed.on_message(tick("BTCUSDT", "delta", {"lastPrice": "22"}, now, 8), now)
        row = self.feed.status_rows(now)[0]
        self.assertEqual(row["state"], "AWAITING_SNAPSHOT")
        self.assertEqual(row["last"], "UNAVAILABLE")
        self.assertNotIn("20", render_table(self.feed, now))

    def test_stale_disconnect_and_partial_rejection(self):
        self.open_feed()
        now = self.clock.time_ms()
        for symbol in SYMBOLS:
            self.feed.on_message(ack(symbol), now)
        self.feed.on_message(tick("BTCUSDT", "snapshot", {"lastPrice": "100", "markPrice": "101"}, now, 1), now)
        self.feed.on_message(json.dumps({"success": False, "ret_msg": "api_key leaked", "op": "subscribe", "req_id": "SOLUSDT"}), now)
        self.clock.advance(5_001)
        later = self.clock.time_ms()
        self.feed.on_clock(lambda _text: None, later)
        rows = {row["symbol"]: row for row in self.feed.status_rows(later)}
        self.assertEqual(rows["BTCUSDT"]["state"], "STALE")
        self.assertEqual(rows["BTCUSDT"]["last"], "UNAVAILABLE")
        self.assertNotIn("100", render_table(self.feed, later))
        self.assertEqual(rows["SOLUSDT"]["state"], "REJECTED")
        self.assertNotIn("api_key", json.dumps(self.feed.log.events))
        self.assertEqual(self.feed.feed_state(later), "UNSAFE")
        fresh = now
        self.feed.on_message(tick("ETHUSDT", "snapshot", {"lastPrice": "30", "markPrice": "31"}, fresh, 1), fresh)
        # ETH exchange time is older than the freshness window at `later`, so it is stale too.
        self.assertEqual(self.feed.status_rows(later)[1]["state"], "STALE")
        self.feed.on_disconnect(later, "peer closed")
        self.feed.phase = "open"
        self.feed.on_message(tick("BTCUSDT", "delta", {"lastPrice": "999", "markPrice": "999"}, later, 3), later)
        self.assertEqual(self.feed.status_rows(later)[0]["last"], "UNAVAILABLE")

    def test_partial_live_symbol_keeps_only_its_own_price(self):
        self.open_feed()
        now = self.clock.time_ms()
        self.feed.on_message(ack("BTCUSDT"), now)
        self.feed.on_message(json.dumps({"success": False, "ret_msg": "topic rejected", "op": "subscribe", "req_id": "ETHUSDT"}), now)
        self.feed.on_message(tick("BTCUSDT", "snapshot", {"lastPrice": "50", "markPrice": "51"}, now, 1), now)
        rows = {row["symbol"]: row for row in self.feed.status_rows(now)}
        self.assertEqual(rows["BTCUSDT"]["state"], "LIVE")
        self.assertEqual(rows["ETHUSDT"]["state"], "REJECTED")
        self.assertEqual(rows["ETHUSDT"]["last"], "UNAVAILABLE")
        self.assertEqual(self.feed.feed_state(now), "PARTIAL")

    def test_heartbeat_failure_clears_prices_and_backoff_is_bounded(self):
        clock = self.clock
        transport = ScriptTransport(clock, [
            ("msg", ack("BTCUSDT")),
            ("msg", tick("BTCUSDT", "snapshot", {"lastPrice": "77", "markPrice": "78"}, clock.time_ms(), 1)),
            ("advance", 1_000),
            ("advance", 500),
        ])
        text = []
        run_feed(self.feed, transport, clock, status_every_ms=10**9, emit=text.append, max_runtime_ms=60_000)
        ops = [item["op"] for item in transport.sent]
        self.assertIn("ping", ops)
        self.assertNotIn("auth", ops)
        self.assertTrue(any(item.get("args") == ["tickers.BTCUSDT"] for item in transport.sent))
        rendered = "".join(text)
        self.assertNotIn("77", rendered.split("feed_state=STOPPED")[-1] if "STOPPED" in rendered else rendered)
        self.assertIn("UNAVAILABLE", rendered)
        self.assertLessEqual(max(self.config.backoff_steps_ms), self.config.backoff_cap_ms)
        states = [event["state"] for event in self.feed.log.events]
        self.assertEqual(states.count("heartbeat_timeout"), 1)
        self.assertEqual(states.count("pong"), 0)

    def test_bad_payload_and_duplicate_transitions(self):
        self.open_feed()
        now = self.clock.time_ms()
        self.feed.on_message("not-json", now)
        self.feed.on_message("not-json", now)
        self.feed.on_message(json.dumps({"op": "subscribe", "req_id": "XRPUSDT"}), now)
        bad = [event for event in self.feed.log.events if event["state"] == "bad_payload"]
        json_bad = [event for event in bad if event["detail"] == "message is not json"]
        self.assertEqual(len(json_bad), 1)
        self.assertEqual(len(bad), 2)
        self.assertEqual(self.feed.books["XRPUSDT"].subscription, "awaiting_ack")

    def test_process_clock_is_not_subtracted_from_exchange_unix_time(self):
        # Windows health log: socket_open t_ms=2437, snapshot t_ms=2638, stale t_ms=2695.
        # Those are monotonic milliseconds since process start, not Unix time.
        clock = ManualClock(2437, wall_ms=1_762_650_000_000)
        feed = PublicFeed(LiveConfig(
            receive_stale_ms=5_000, exchange_stale_ms=15_000, exchange_future_skew_ms=2_000,
        ))
        feed.on_open(lambda _text: None, clock.time_ms())
        exchange_ts = clock.wall_ms() - 80
        feed.on_message(ack("BTCUSDT"), clock.time_ms())
        feed.on_message(tick("BTCUSDT", "snapshot", {"lastPrice": "100", "markPrice": "101"}, exchange_ts, 1), clock.time_ms())
        clock.advance(258)
        now = clock.time_ms()
        self.assertEqual(now, 2695)
        broken_age = now - exchange_ts
        self.assertLess(broken_age, -1_000_000_000)
        row = feed.status_rows(now, clock.wall_ms())[0]
        self.assertEqual(row["state"], "LIVE")
        self.assertEqual(row["last"], "100")
        self.assertEqual(row["mark"], "101")
        self.assertLess(int(row["exch_age_ms"]), 15_000)

    def test_old_or_future_exchange_time_stays_unavailable(self):
        wall = 1_762_650_000_000
        clock = ManualClock(0, wall_ms=wall)
        feed = PublicFeed(LiveConfig(exchange_stale_ms=15_000, exchange_future_skew_ms=2_000, receive_stale_ms=5_000))
        feed.on_open(lambda _text: None, 0)
        feed.on_message(ack("BTCUSDT"), 0)
        feed.on_message(tick("BTCUSDT", "snapshot", {"lastPrice": "100", "markPrice": "101"}, wall - 20_000, 1), 0)
        old = feed.status_rows(0, wall)[0]
        self.assertEqual(old["state"], "STALE")
        self.assertEqual(old["last"], "UNAVAILABLE")
        self.assertEqual(old["exch_age_ms"], "20000")
        feed.on_message(tick("BTCUSDT", "snapshot", {"lastPrice": "100", "markPrice": "101"}, wall + 60_000, 2), 0)
        ahead = feed.status_rows(0, wall)[0]
        self.assertEqual(ahead["state"], "STALE")
        self.assertEqual(ahead["last"], "UNAVAILABLE")
        self.assertEqual(ahead["exch_age_ms"], "-60000")

    def test_finite_run_shuts_down_without_a_socket(self):
        clock = ManualClock(0)
        transport = ScriptTransport(clock, [("advance", 60_000)])

        code = execute_finite_live(
            ["--confirm-public-network", "--seconds", "60"],
            transport_factory=lambda: transport,
            clock=clock,
        )
        self.assertEqual(code, 0)
        self.assertEqual(transport.connects, 1)
        self.assertTrue(all(item["op"] in {"subscribe", "ping"} for item in transport.sent))
        self.assertTrue(all(arg.startswith("tickers.") for item in transport.sent for arg in item.get("args", [])))

    def test_cli_refuses_network_without_an_explicit_finite_window(self):
        self.assertIsNotNone(validate_live_invocation(False, 90))
        self.assertIsNotNone(validate_live_invocation(True, 10))
        self.assertIsNotNone(validate_live_invocation(True, 121))
        self.assertIsNone(validate_live_invocation(True, 90))
        self.assertEqual(main(["live"]), 2)
        self.assertEqual(main(["live", "--confirm-public-network", "--seconds", "30"]), 2)
        self.assertIn("def open_public_socket", Path(live_socket.__file__).read_text())


class FiniteShutdownTests(unittest.TestCase):
    def test_runtime_limit_hides_prices(self):
        clock = ManualClock(0)
        feed = PublicFeed(LiveConfig(ping_interval_ms=10_000, pong_timeout_ms=10_000, max_reconnects=3))
        transport = ScriptTransport(clock, [("advance", 500)] * 30)
        output = []
        run_feed(feed, transport, clock, status_every_ms=10**9, emit=output.append, max_runtime_ms=2_000)
        self.assertTrue(feed.shutdown)
        final = output[-1]
        self.assertIn("feed_state=STOPPED", final)
        self.assertIn("UNAVAILABLE", final)
        self.assertTrue(any(event["state"] == "runtime_limit" for event in feed.log.events))


if __name__ == "__main__":
    unittest.main()
