# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Read-only public linear ticker feed and connection health.

The live socket is opt-in. This module merges Bybit public ticker snapshots
and deltas and decides when a price is allowed to be shown. It does not
submit orders, read accounts, or score a strategy. A displayed quote is not
protection from trading risk, and a live SOLUSDT or XRPUSDT quote does not
establish historical research eligibility.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
CONDITIONAL = frozenset({"SOLUSDT", "XRPUSDT"})
PUBLIC_LINEAR_URL = "wss://stream.bybit.com/v5/public/linear"
ALLOWED_OPS = frozenset({"subscribe", "unsubscribe", "ping"})
PRICE_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
SECRET_MARKERS = ("api_key", "api-key", "secret", "signature", "bearer", "passphrase")


class FeedClosed(ConnectionError):
    pass


class LiveRefused(ValueError):
    pass


@dataclass(frozen=True)
class LiveConfig:
    symbols: tuple[str, ...] = SYMBOLS
    ping_interval_ms: int = 20_000
    pong_timeout_ms: int = 10_000
    receive_stale_ms: int = 5_000
    exchange_stale_ms: int = 15_000
    exchange_future_skew_ms: int = 2_000
    backoff_steps_ms: tuple[int, ...] = (1_000, 2_000, 4_000, 8_000, 16_000)
    backoff_cap_ms: int = 30_000
    max_reconnects: int = 8
    url: str = PUBLIC_LINEAR_URL

    def __post_init__(self):
        if self.symbols != SYMBOLS:
            raise LiveRefused("the live feed is limited to the four fixed symbols")
        for name, value in (
            ("ping_interval_ms", self.ping_interval_ms),
            ("pong_timeout_ms", self.pong_timeout_ms),
            ("receive_stale_ms", self.receive_stale_ms),
            ("exchange_stale_ms", self.exchange_stale_ms),
            ("exchange_future_skew_ms", self.exchange_future_skew_ms),
            ("backoff_cap_ms", self.backoff_cap_ms),
            ("max_reconnects", self.max_reconnects),
        ):
            if type(value) is not int or value < 0:
                raise LiveRefused(f"{name} must be a nonnegative integer")
        if not self.backoff_steps_ms or any(type(item) is not int or item < 0 for item in self.backoff_steps_ms):
            raise LiveRefused("backoff steps must be nonnegative integers")
        check_public_linear_url(self.url)


def check_public_linear_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "wss" or parts.hostname != "stream.bybit.com" or parts.port not in (None, 443):
        raise LiveRefused("live feed allows only wss://stream.bybit.com/v5/public/linear")
    if parts.path != "/v5/public/linear" or parts.query or parts.fragment or parts.username:
        raise LiveRefused("live feed allows only the public linear path, with no query or credentials")


def client_message(op: str, args: list[str] | None = None, req_id: str | None = None) -> str:
    if op not in ALLOWED_OPS:
        raise LiveRefused(f"client op {op} is not a public ticker control message")
    body = {"op": op}
    if req_id is not None:
        if req_id not in SYMBOLS:
            raise LiveRefused("req_id must be one of the four fixed symbols")
        body["req_id"] = req_id
    if args is not None:
        if op not in ("subscribe", "unsubscribe"):
            raise LiveRefused("only subscribe and unsubscribe accept topic args")
        cleaned = []
        for arg in args:
            if not isinstance(arg, str) or not arg.startswith("tickers."):
                raise LiveRefused("subscribe args must be public ticker topics")
            symbol = arg.split(".", 1)[1]
            if symbol not in SYMBOLS:
                raise LiveRefused("subscribe args must name the four fixed symbols")
            cleaned.append(arg)
        body["args"] = cleaned
    encoded = json.dumps(body, separators=(",", ":"), sort_keys=True)
    lowered = encoded.lower()
    if any(marker in lowered for marker in SECRET_MARKERS) or "auth" in lowered:
        raise LiveRefused("client message looks like a credential or private call")
    return encoded


def redact(text: str) -> str:
    if not isinstance(text, str):
        return ""
    lowered = text.lower()
    if any(marker in lowered for marker in SECRET_MARKERS):
        return "[redacted]"
    return text[:160]


@dataclass
class SymbolBook:
    snapshot: bool = False
    fields: dict = field(default_factory=dict)
    cs: int | None = None
    exchange_ts: int | None = None
    received_ms: int | None = None
    ack_ms: int | None = None
    subscription: str = "none"  # none, awaiting_ack, awaiting_snapshot, rejected
    reset_reason: str = ""


class TransitionLog:
    def __init__(self):
        self.events = []
        self._last = {}

    def emit(self, now_ms: int, scope: str, state: str, detail: str = "") -> None:
        detail = redact(detail)
        if self._last.get(scope) == (state, detail):
            return
        self._last[scope] = (state, detail)
        self.events.append({"t_ms": now_ms, "scope": scope, "state": state, "detail": detail})


class ManualClock:
    """Monotonic milliseconds and a separate Unix wall clock.

    `time_ms` is the process clock used for receive age, ping, and the runtime
    limit. `wall_ms` is compared with Bybit's exchange timestamp. They are not
    the same quantity.
    """

    def __init__(self, start_ms: int = 0, wall_ms: int | None = None):
        self.now_ms = start_ms
        self.wall = start_ms if wall_ms is None else wall_ms

    def time_ms(self) -> int:
        return self.now_ms

    def wall_ms(self) -> int:
        return self.wall

    def sleep_ms(self, delay: int) -> None:
        self.advance(delay)

    def advance(self, delay: int) -> None:
        self.now_ms += delay
        self.wall += delay


class PublicFeed:
    """In-memory feed state. A transport calls the handlers; nothing here opens a socket."""

    def __init__(self, config: LiveConfig | None = None):
        self.config = config or LiveConfig()
        self.books = {symbol: SymbolBook() for symbol in self.config.symbols}
        self.log = TransitionLog()
        self.phase = "disconnected"
        self.stop = False
        self.shutdown = False
        self.heartbeat_failed = False
        self.ping_due_ms = 0
        self.ping_sent_ms = None
        self.backoff_index = 0
        self.reconnects = 0
        self.outbound = []
        self.need_reconnect = False
        self.resubscribe_count = {symbol: 0 for symbol in self.config.symbols}
        self.last_resubscribe_ms = {symbol: -10**12 for symbol in self.config.symbols}
        self.consecutive_unusable = {symbol: 0 for symbol in self.config.symbols}

    def on_open(self, send, now_ms: int) -> None:
        self.phase = "open"
        self.heartbeat_failed = False
        self.ping_sent_ms = None
        self.ping_due_ms = now_ms + self.config.ping_interval_ms
        self.log.emit(now_ms, "feed", "socket_open", "public linear socket open; data not yet received")
        for symbol in self.config.symbols:
            book = self.books[symbol]
            book.subscription = "awaiting_ack"
            book.snapshot = False
            book.fields = {}
            book.cs = None
            book.exchange_ts = None
            book.received_ms = None
            book.ack_ms = None
            book.reset_reason = ""
            send(client_message("subscribe", [f"tickers.{symbol}"], req_id=symbol))
            self.log.emit(now_ms, symbol, "awaiting_ack", "subscribe sent")

    def on_clock(self, send, now_ms: int, wall_ms: int | None = None) -> None:
        wall_ms = now_ms if wall_ms is None else wall_ms
        self._note_freshness(now_ms, wall_ms)
        if self.phase != "open" or self.stop:
            return
        if self.ping_sent_ms is None and now_ms >= self.ping_due_ms:
            send(client_message("ping"))
            self.ping_sent_ms = now_ms
            self.ping_due_ms = now_ms + self.config.ping_interval_ms
            self.log.emit(now_ms, "feed", "ping_sent", "public ping")
        elif self.ping_sent_ms is not None and now_ms - self.ping_sent_ms >= self.config.pong_timeout_ms:
            self.heartbeat_failed = True
            self.phase = "heartbeat_timeout"
            self.log.emit(now_ms, "feed", "heartbeat_timeout", "pong missing")
            self._clear_books("heartbeat_timeout")

    def on_message(self, payload: str, now_ms: int) -> None:
        try:
            message = json.loads(payload)
        except json.JSONDecodeError:
            self.log.emit(now_ms, "feed", "bad_payload", "message is not json")
            return
        if not isinstance(message, dict):
            self.log.emit(now_ms, "feed", "bad_payload", "message is not an object")
            return
        op = message.get("op")
        if op in ("ping", "pong") or message.get("ret_msg") == "pong":
            self._on_pong(message, now_ms)
            return
        if op == "subscribe":
            self._on_subscribe(message, now_ms)
            return
        if "topic" in message or message.get("type") in ("snapshot", "delta"):
            self._on_ticker(message, now_ms)
            return
        if op not in (None, "ping", "pong", "subscribe"):
            self.log.emit(now_ms, "feed", "ignored_op", redact(str(op)))
            return
        self.log.emit(now_ms, "feed", "bad_payload", "unrecognized public message")

    def on_disconnect(self, now_ms: int, reason: str) -> None:
        self.phase = "disconnected"
        self.ping_sent_ms = None
        self._clear_books(reason)
        self.log.emit(now_ms, "feed", "disconnected", reason)
        for symbol in self.config.symbols:
            self.log.emit(now_ms, symbol, "disconnected", reason)

    def on_shutdown(self, now_ms: int) -> None:
        self.shutdown = True
        self.stop = True
        self.phase = "disconnected"
        self._clear_books("shutdown")
        self.log.emit(now_ms, "feed", "shutdown", "foreground feed stopped")

    def fail_connect(self, now_ms: int) -> None:
        self.phase = "disconnected"
        self.log.emit(now_ms, "feed", "connect_failed", "public socket did not open")

    def next_backoff_ms(self) -> int:
        step = self.config.backoff_steps_ms[min(self.backoff_index, len(self.config.backoff_steps_ms) - 1)]
        self.backoff_index += 1
        return min(step, self.config.backoff_cap_ms)

    def note_reconnect_attempt(self) -> bool:
        """Return False when the bounded reconnect budget is exhausted."""
        self.reconnects += 1
        if self.reconnects > self.config.max_reconnects:
            self.stop = True
            return False
        return True

    def note_session_established(self) -> None:
        self.backoff_index = 0

    def status_rows(self, now_ms: int, wall_ms: int | None = None) -> list[dict]:
        wall_ms = now_ms if wall_ms is None else wall_ms
        rows = []
        for symbol in self.config.symbols:
            state, last, mark, recv_age, exch_age = self._symbol_view(symbol, now_ms, wall_ms)
            rows.append({
                "symbol": symbol,
                "role": "conditional" if symbol in CONDITIONAL else "fixed",
                "state": state,
                "last": last,
                "mark": mark,
                "recv_age_ms": recv_age,
                "exch_age_ms": exch_age,
            })
        return rows

    def feed_state(self, now_ms: int, wall_ms: int | None = None) -> str:
        wall_ms = now_ms if wall_ms is None else wall_ms
        if self.shutdown:
            return "STOPPED"
        if self.phase == "heartbeat_timeout":
            return "HEARTBEAT_TIMEOUT"
        if self.phase != "open":
            return "DISCONNECTED"
        states = [self._symbol_view(symbol, now_ms, wall_ms)[0] for symbol in self.config.symbols]
        if all(state == "LIVE" for state in states):
            return "LIVE"
        if any(state == "LIVE" for state in states):
            return "PARTIAL"
        return "UNSAFE"

    def _on_pong(self, message: dict, now_ms: int) -> None:
        op = message.get("op")
        ret = message.get("ret_msg")
        if message.get("success") is False:
            self.log.emit(now_ms, "feed", "heartbeat_rejected", redact(str(ret or "")))
            return
        if op == "pong" or ret == "pong" or op == "ping":
            self.ping_sent_ms = None
            self.log.emit(now_ms, "feed", "pong", "heartbeat acknowledged")
            return
        self.log.emit(now_ms, "feed", "bad_payload", "ping control was not a pong")

    def _on_subscribe(self, message: dict, now_ms: int) -> None:
        symbol = _ack_symbol(message)
        targets = (symbol,) if symbol else self.config.symbols
        success = message.get("success")
        if success not in (True, False):
            self.log.emit(now_ms, "feed", "bad_payload", "subscribe control has no success flag")
            return
        detail = redact(str(message.get("ret_msg") or ""))
        for name in targets:
            book = self.books[name]
            if success:
                if book.snapshot:
                    continue
                book.subscription = "awaiting_snapshot"
                book.ack_ms = now_ms
                self.log.emit(now_ms, name, "awaiting_snapshot", "subscribe acknowledged; ticker snapshot not yet received")
            else:
                book.subscription = "rejected"
                book.snapshot = False
                book.fields = {}
                book.ack_ms = None
                self.log.emit(now_ms, name, "rejected", detail or "subscribe rejected")
        if symbol is None and not success:
            self.log.emit(now_ms, "feed", "subscribe_rejected", detail or "subscribe rejected")

    def _on_ticker(self, message: dict, now_ms: int) -> None:
        topic = message.get("topic")
        if not isinstance(topic, str) or not topic.startswith("tickers."):
            self.log.emit(now_ms, "feed", "bad_payload", "ticker topic missing")
            return
        symbol = topic.split(".", 1)[1]
        if symbol not in self.books:
            self.log.emit(now_ms, "feed", "ignored_topic", symbol)
            return
        kind = message.get("type")
        data = message.get("data")
        items = _data_items(data)
        if kind not in ("snapshot", "delta") or items is None:
            self.log.emit(now_ms, symbol, "bad_payload", "ticker type or data is unusable")
            return
        ts = message.get("ts")
        if type(ts) is not int:
            self.log.emit(now_ms, symbol, "bad_payload", "exchange timestamp missing")
            return
        cs = message.get("cs")
        if cs is not None and type(cs) is not int:
            self.log.emit(now_ms, symbol, "bad_payload", "cross sequence is not an integer")
            return
        book = self.books[symbol]
        if kind == "snapshot":
            book.fields = {}
            book.snapshot = True
            book.cs = None
            book.subscription = "open"
            book.reset_reason = ""
            self.consecutive_unusable[symbol] = 0
            self.resubscribe_count[symbol] = 0
            self._merge_items(book, items, replace=True)
            book.cs = cs
            book.exchange_ts = ts
            book.received_ms = now_ms
            self.log.emit(now_ms, f"{symbol}:quote", "snapshot", "snapshot replaced the local ticker")
            self.note_session_established()
            return
        if not book.snapshot:
            self.log.emit(now_ms, symbol, "awaiting_snapshot", "delta ignored until a snapshot")
            self._request_resubscribe(symbol, now_ms, "delta without snapshot")
            return
        if cs is not None and book.cs is not None and cs < book.cs:
            self.consecutive_unusable[symbol] += 1
            self.log.emit(now_ms, f"{symbol}:sequence", "dropped_old", f"cross sequence not applied {cs}<{book.cs}")
            if self.consecutive_unusable[symbol] >= 3:
                self._request_resubscribe(symbol, now_ms, "repeated non-increasing cross sequence")
            return
        if cs is not None and book.cs is not None and cs == book.cs:
            self.log.emit(now_ms, f"{symbol}:sequence", "dropped_duplicate", f"cross sequence repeated {cs}")
            return
        if cs is None:
            self.consecutive_unusable[symbol] += 1
            self.log.emit(now_ms, f"{symbol}:sequence", "dropped_missing", "delta had no cross sequence")
            if self.consecutive_unusable[symbol] >= 3:
                self._request_resubscribe(symbol, now_ms, "deltas without a cross sequence")
            return
        self.consecutive_unusable[symbol] = 0
        self._merge_items(book, items, replace=False)
        if cs is not None:
            book.cs = cs
        book.exchange_ts = ts
        book.received_ms = now_ms
        self.log.emit(now_ms, f"{symbol}:quote", "delta", "delta merged")

    def flush(self, send) -> None:
        while self.outbound:
            send(self.outbound.pop(0))

    def _request_resubscribe(self, symbol: str, now_ms: int, reason: str) -> None:
        """Ask Bybit for a new snapshot. One old frame does not clear the book."""
        if now_ms - self.last_resubscribe_ms[symbol] < 2_000:
            return
        if self.resubscribe_count[symbol] >= 3:
            self.need_reconnect = True
            self.log.emit(now_ms, symbol, "resync_reconnect", reason)
            return
        self.resubscribe_count[symbol] += 1
        self.last_resubscribe_ms[symbol] = now_ms
        self.consecutive_unusable[symbol] = 0
        book = self.books[symbol]
        book.snapshot = False
        book.fields = {}
        book.cs = None
        book.exchange_ts = None
        book.received_ms = None
        book.subscription = "awaiting_snapshot"
        book.ack_ms = now_ms
        book.reset_reason = reason
        topic = f"tickers.{symbol}"
        self.outbound.append(client_message("unsubscribe", [topic], req_id=symbol))
        self.outbound.append(client_message("subscribe", [topic], req_id=symbol))
        self.log.emit(now_ms, symbol, "resubscribe", reason)

    def _merge_items(self, book: SymbolBook, items: list[dict], replace: bool) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in ("lastPrice", "markPrice"):
                if key not in item:
                    if replace:
                        book.fields.pop(key, None)
                    continue
                parsed = _positive_price(item[key])
                if parsed is None:
                    book.fields.pop(key, None)
                    continue
                book.fields[key] = parsed

    def _clear_books(self, reason: str) -> None:
        for book in self.books.values():
            book.snapshot = False
            book.fields = {}
            book.cs = None
            book.exchange_ts = None
            book.received_ms = None
            book.ack_ms = None
            book.subscription = "none"
            book.reset_reason = reason

    def _note_freshness(self, now_ms: int, wall_ms: int) -> None:
        for symbol in self.config.symbols:
            state = self._symbol_view(symbol, now_ms, wall_ms)[0]
            if state == "LIVE":
                self.log.emit(now_ms, symbol, "live", "fresh last and mark")
            elif state == "STALE":
                self.log.emit(now_ms, symbol, "stale", "quote exceeded the freshness limit")
            elif state == "IDLE":
                self.log.emit(now_ms, symbol, "idle", "subscription acknowledged but no ticker arrived")

    def _symbol_view(self, symbol: str, now_ms: int, wall_ms: int) -> tuple[str, str, str, str, str]:
        unavailable = ("UNAVAILABLE", "UNAVAILABLE", "-", "-")
        if self.phase != "open":
            label = "HEARTBEAT_TIMEOUT" if self.phase == "heartbeat_timeout" else "DISCONNECTED"
            return (label, *unavailable)
        book = self.books[symbol]
        if book.subscription == "rejected":
            return ("REJECTED", *unavailable)
        if book.subscription == "awaiting_ack":
            return ("AWAITING_ACK", *unavailable)
        if not book.snapshot:
            if book.ack_ms is not None and now_ms - book.ack_ms > self.config.receive_stale_ms:
                return ("IDLE", *unavailable)
            return ("AWAITING_SNAPSHOT", *unavailable)
        last = book.fields.get("lastPrice")
        mark = book.fields.get("markPrice")
        recv_age = None if book.received_ms is None else now_ms - book.received_ms
        exch_age = None if book.exchange_ts is None else wall_ms - book.exchange_ts
        fresh = (
            recv_age is not None and exch_age is not None
            and 0 <= recv_age <= self.config.receive_stale_ms
            and -self.config.exchange_future_skew_ms <= exch_age <= self.config.exchange_stale_ms
        )
        recv_text = "-" if recv_age is None else str(recv_age)
        exch_text = "-" if exch_age is None else str(exch_age)
        if not fresh:
            return ("STALE", "UNAVAILABLE", "UNAVAILABLE", recv_text, exch_text)
        if last is None or mark is None:
            return (
                "INCOMPLETE",
                last or "UNAVAILABLE",
                mark or "UNAVAILABLE",
                str(recv_age),
                str(exch_age),
            )
        return ("LIVE", last, mark, str(recv_age), str(exch_age))


def _positive_price(value):
    if not isinstance(value, str) or not PRICE_RE.fullmatch(value):
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or number <= 0:
        return None
    return value


def _data_items(data):
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    return None


def _ack_symbol(message: dict) -> str | None:
    req = message.get("req_id")
    if req in SYMBOLS:
        return req
    text = str(message.get("ret_msg") or "")
    for symbol in SYMBOLS:
        if f"tickers.{symbol}" in text or symbol in text:
            return symbol
    return None


def render_table(feed: PublicFeed, now_ms: int, wall_ms: int | None = None) -> str:
    state = feed.feed_state(now_ms, wall_ms)
    lines = [
        "UNSAFE TO TRADE: this table is a public quote display, not an order book, a signal, or protection from trading risk.",
        "SOLUSDT and XRPUSDT are conditional. A live quote does not establish historical research eligibility.",
        "Live end-to-end access from this build is not validated. WebSocket reachability is unproven.",
        f"feed_state={state}",
        "symbol role state last mark recv_age_ms exch_age_ms",
    ]
    for row in feed.status_rows(now_ms, wall_ms):
        lines.append(
            f"{row['symbol']} {row['role']} {row['state']} {row['last']} {row['mark']} {row['recv_age_ms']} {row['exch_age_ms']}"
        )
    if state != "LIVE":
        lines.append("OLD PRICES ARE WITHHELD. Unavailable means the quote must not be treated as current.")
    return "\n".join(lines) + "\n"


def validate_live_invocation(confirm: bool, seconds) -> str | None:
    """Refuse any live socket unless the operator names a 60–120 second run."""
    if confirm is not True:
        return "Refusing to open a socket. Pass --confirm-public-network and --seconds between 60 and 120."
    if type(seconds) is not int or not 60 <= seconds <= 120:
        return "Refusing an open-ended run. --seconds must be an integer from 60 through 120."
    return None


def run_feed(feed: PublicFeed, transport, clock, status_every_ms: int = 1000, emit=None, max_runtime_ms: int | None = None) -> PublicFeed:
    """Foreground loop. The caller supplies the transport. Tests use a fake one."""
    if emit is None:
        emit = lambda _text: None
    origin = clock.time_ms()
    last_status = None

    def expired(now_ms: int) -> bool:
        if max_runtime_ms is None:
            return False
        if now_ms - origin < max_runtime_ms:
            return False
        feed.stop = True
        feed.log.emit(now_ms, "feed", "runtime_limit", f"stopped after {max_runtime_ms} ms")
        return True

    while not feed.stop:
        try:
            transport.connect()
        except FeedClosed:
            now = clock.time_ms()
            if expired(now):
                break
            feed.fail_connect(now)
            if not feed.note_reconnect_attempt():
                feed.log.emit(now, "feed", "gave_up", "reconnect budget exhausted")
                break
            clock.sleep_ms(feed.next_backoff_ms())
            continue
        now = clock.time_ms()
        if expired(now):
            break
        feed.on_open(transport.send, now)
        while not feed.stop:
            now = clock.time_ms()
            wall = clock.wall_ms()
            if expired(now):
                break
            feed.on_clock(transport.send, now, wall)
            if feed.heartbeat_failed:
                transport.close()
                feed.on_disconnect(now, "heartbeat_timeout")
                break
            try:
                incoming = transport.recv(min(1000, max(feed.ping_due_ms - clock.time_ms(), 1)))
            except FeedClosed as exc:
                feed.on_disconnect(clock.time_ms(), str(exc) or "closed")
                break
            if incoming:
                feed.on_message(incoming, clock.time_ms())
                feed.flush(transport.send)
            if feed.need_reconnect:
                feed.need_reconnect = False
                transport.close()
                feed.on_disconnect(clock.time_ms(), "resubscribe budget exhausted")
                break
            now = clock.time_ms()
            if expired(now):
                break
            if last_status is None or now - last_status >= status_every_ms:
                emit(render_table(feed, now, clock.wall_ms()))
                last_status = now
        if feed.stop:
            break
        now = clock.time_ms()
        if expired(now):
            break
        if not feed.note_reconnect_attempt():
            feed.log.emit(now, "feed", "gave_up", "reconnect budget exhausted")
            break
        clock.sleep_ms(feed.next_backoff_ms())
    transport.close()
    feed.on_shutdown(clock.time_ms())
    emit(render_table(feed, clock.time_ms(), clock.wall_ms()))
    return feed


def write_event_log(feed: PublicFeed, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for event in feed.log.events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


class WallClock:
    def __init__(self):
        import time
        self._time = time
        self._origin = time.monotonic()

    def time_ms(self) -> int:
        return int((self._time.monotonic() - self._origin) * 1000)

    def wall_ms(self) -> int:
        return int(self._time.time() * 1000)

    def sleep_ms(self, delay: int) -> None:
        self._time.sleep(max(delay, 0) / 1000)


class SocketTransport:
    def __init__(self, opener):
        self._opener = opener
        self._socket = None

    def connect(self):
        self._socket = self._opener(PUBLIC_LINEAR_URL)

    def send(self, text: str) -> None:
        self._socket.send(text)

    def recv(self, timeout_ms: int):
        return self._socket.recv(timeout_ms)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None


def default_transport():
    try:
        from bybit_research.live_socket import open_public_socket
    except ImportError:
        from live_socket import open_public_socket
    return SocketTransport(open_public_socket)


def execute_finite_live(argv=None, transport_factory=None, clock=None) -> int:
    """Parse a finite live check. The default factory is the only network path."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(prog="bybit-public-live")
    parser.add_argument("--confirm-public-network", action="store_true")
    parser.add_argument("--seconds", type=int)
    parser.add_argument("--event-log")
    parser.add_argument("--receive-stale-ms", type=int, default=5_000)
    parser.add_argument("--exchange-stale-ms", type=int, default=15_000)
    parser.add_argument("--exchange-future-skew-ms", type=int, default=2_000)
    parser.add_argument("--ping-interval-ms", type=int, default=20_000)
    parser.add_argument("--pong-timeout-ms", type=int, default=10_000)
    parser.add_argument("--max-reconnects", type=int, default=8)
    args = parser.parse_args(argv)
    refusal = validate_live_invocation(args.confirm_public_network, args.seconds)
    if refusal:
        sys.stderr.write(refusal + "\n")
        return 2
    try:
        config = LiveConfig(
            receive_stale_ms=args.receive_stale_ms,
            exchange_stale_ms=args.exchange_stale_ms,
            exchange_future_skew_ms=args.exchange_future_skew_ms,
            ping_interval_ms=args.ping_interval_ms,
            pong_timeout_ms=args.pong_timeout_ms,
            max_reconnects=args.max_reconnects,
        )
    except LiveRefused as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    clock = clock or WallClock()
    transport = (transport_factory or default_transport)()
    feed = PublicFeed(config)
    sys.stdout.write(
        "Finite public read only. No orders. Ctrl+C stops early. "
        f"Automatic stop after {args.seconds} seconds. Nothing is installed or left running.\n"
    )
    try:
        run_feed(feed, transport, clock, max_runtime_ms=args.seconds * 1000, emit=sys.stdout.write)
    except KeyboardInterrupt:
        feed.on_shutdown(clock.time_ms())
        transport.close()
        sys.stdout.write("Stopped by Ctrl+C. Prices are withheld.\n")
    if args.event_log:
        write_event_log(feed, args.event_log)
    return 0
