# Public live quote check

Finite, foreground, read-only display of Bybit public linear last and mark prices for BTCUSDT, ETHUSDT, SOLUSDT and XRPUSDT. No orders, accounts, strategy, or performance. The socket opens only with both `--confirm-public-network` and `--seconds` between 60 and 120.

Python 3.11 or newer is required and is not installed by this repository. There are no third-party packages. Development tests used CPython 3.12.3.

From this directory:

```text
python3 -m bybit_research live --confirm-public-network --seconds 90 --event-log live-health.jsonl
```

Stop with Ctrl+C. The process also stops by itself when `--seconds` elapses. It does not install a service or start again.

The Windows folder [windows_live/README.md](windows_live/README.md) is the self-contained instruction sheet. A zip of that runtime is produced for the operator. It does not need this repository.

Live end-to-end access was not run from the Cloud Agent VM. A Windows REST HTTP 200 does not prove the public WebSocket. SOLUSDT or XRPUSDT appearing in the table does not establish historical research eligibility. Stale and disconnected rows show `UNAVAILABLE` instead of an old price. The table is not a trading signal and does not protect against trading risk.

Documented socket: `wss://stream.bybit.com/v5/public/linear`. Topics: `tickers.{symbol}`. Client control messages are `subscribe` and `ping` only. See the Bybit V5 public ticker and connect pages.
