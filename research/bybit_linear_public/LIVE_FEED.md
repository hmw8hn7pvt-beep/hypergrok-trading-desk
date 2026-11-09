# Public live quote check

Finite, foreground, read-only display of Bybit public linear last and mark prices for BTCUSDT, ETHUSDT, SOLUSDT and XRPUSDT. No orders, accounts, strategy, or performance. The socket opens only with both `--confirm-public-network` and `--seconds` between 60 and 120.

Python 3.11 or newer is required and is not installed by this repository. There are no third-party packages. Development tests used CPython 3.12.3.

From this directory:

```text
python3 -m bybit_research live --confirm-public-network --seconds 90 --event-log live-health.jsonl
```

Stop with Ctrl+C. The process also stops by itself when `--seconds` elapses. It does not install a service or start again.

The Windows folder [windows_live/README.md](windows_live/README.md) is the self-contained instruction sheet. A zip of that runtime is produced for the operator. It does not need this repository.

A single older or duplicate ticker cross-sequence frame is dropped and the last accepted book is kept. Three such frames, or deltas with no snapshot, send one public unsubscribe and subscribe for that symbol only. After three tries the socket reconnects within the existing reconnect bound. Other symbols are left unchanged. Official ticker text names `cs` as a cross sequence and does not define it as a gapless order-book counter. The process monotonic clock is used only for receive age, ping timing, and the 60–120 second limit. A quote whose exchange timestamp is older than 15 seconds, or more than 2 seconds ahead of the wall clock, stays unavailable. The component does not set the operating-system clock. A Windows REST HTTP 200 does not prove the public WebSocket. SOLUSDT or XRPUSDT appearing in the table does not establish historical research eligibility. Stale and disconnected rows show `UNAVAILABLE` instead of an old price. The table is not a trading signal and does not protect against trading risk.

Documented socket: `wss://stream.bybit.com/v5/public/linear`. Topics: `tickers.{symbol}`. Client control messages are `subscribe` and `ping` only. See the Bybit V5 public ticker and connect pages.
