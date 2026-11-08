# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Public GET allowlist for official Bybit V5 market data.

Documented from https://bybit-exchange.github.io/docs/v5/market/kline
https://bybit-exchange.github.io/docs/v5/market/mark-kline
https://bybit-exchange.github.io/docs/v5/market/history-fund-rate
https://bybit-exchange.github.io/docs/v5/market/instrument
https://bybit-exchange.github.io/docs/v5/rate-limit

No private, account, position, asset, or order path is allowlisted.
"""

from __future__ import annotations

HOST = "api.bybit.com"
ORIGIN = "https://api.bybit.com"
METHOD = "GET"

# Query keys are the documented public parameters only.
PATHS = {
    "/v5/market/kline": frozenset({"category", "symbol", "interval", "start", "end", "limit"}),
    "/v5/market/mark-price-kline": frozenset({"category", "symbol", "interval", "start", "end", "limit"}),
    "/v5/market/funding/history": frozenset({"category", "symbol", "startTime", "endTime", "limit"}),
    "/v5/market/instruments-info": frozenset({"category", "symbol", "status", "limit"}),
}

FORBIDDEN_QUERY_KEYS = frozenset({
    "api_key", "apikey", "sign", "signature", "secret", "recv_window",
    "recvwindow", "key", "token", "password", "passphrase", "authorization",
})

CREDENTIAL_FRAGMENTS = ("api_key", "api-key", "secret", "bearer ", "passphrase")


class AllowlistError(PermissionError):
    pass


def check_request(method: str, path: str, query: dict) -> None:
    if method != METHOD:
        raise AllowlistError(f"method {method} is not allowlisted; only GET is allowed")
    if path not in PATHS:
        raise AllowlistError(f"path {path} is not an allowlisted public market GET")
    if not isinstance(query, dict):
        raise AllowlistError("query must be a mapping")
    unknown = set(query) - PATHS[path]
    if unknown:
        raise AllowlistError("query contains a parameter outside the documented allowlist: " + ",".join(sorted(unknown)))
    lowered = {key.lower() for key in query}
    if lowered & FORBIDDEN_QUERY_KEYS:
        raise AllowlistError("query contains a credential-like parameter")
    for value in query.values():
        if not isinstance(value, str) or value == "":
            raise AllowlistError("query values must be non-empty strings")
        folded = value.lower()
        if any(fragment in folded for fragment in CREDENTIAL_FRAGMENTS):
            raise AllowlistError("query value looks like a credential")
