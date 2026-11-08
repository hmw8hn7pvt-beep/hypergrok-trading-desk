# Bybit public research

Research-only tools for a fixed four-name Bybit USDT linear study. This directory does not change desk roles, skills, or exchange-write paths. It does not place orders or read accounts.

Based on [HyperGrok Trading Desk](https://github.com/galleonlabs/hypergrok-trading-desk) v1.7.1 (`82bc645899b9581a693463b59553aa1329e021c4`) by Andrew Wilkinson and Galleon Labs. MIT license: [LICENSE](LICENSE). Credit: [ATTRIBUTION.md](ATTRIBUTION.md).

The proposed rules are not frozen. Market-history strategy performance is refused. Read [RULES_PROPOSED.md](RULES_PROPOSED.md), [DATA_SUFFICIENCY.md](DATA_SUFFICIENCY.md) and [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md) before any later performance request.

```bash
python3 -m unittest test_acceptance.py
python3 -m bybit_research collect --output /tmp/bybit-public-bundle
python3 -m bybit_research verify --bundle /tmp/bybit-public-bundle
python3 -m bybit_research sufficiency --bundle /tmp/bybit-public-bundle
python3 -m bybit_research performance
```

`collect` talks only to `https://api.bybit.com` and only through the public GET allowlist in `bybit_research/allowlist.py`. A 403 stops the run. `performance` exits 3 and writes no market result. `verify` exit 0 means the bundle hashes match; it is not a data pass or a strategy pass. `sufficiency` exits 1 while required evidence is unknown.

The recorded run on 2026-11-08T23:46:39.765Z received HTTP 403 from CloudFront before any candle, mark, funding, or identity series was saved. Strict sufficiency failed. SOLUSDT and XRPUSDT remain conditional. No symbol or period was dropped or zero-filled.
