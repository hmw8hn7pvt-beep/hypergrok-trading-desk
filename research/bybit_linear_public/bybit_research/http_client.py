# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Bounded public GET client. HTTP 403 stops the caller. No proxy and no other host."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlencode, urlsplit

from bybit_research.allowlist import ORIGIN, AllowlistError, check_request
from bybit_research.config import MAX_ATTEMPTS, MAX_HTTP_REQUESTS, MIN_INTERVAL_SECONDS, WINDOW_REQUESTS, WINDOW_SECONDS

MAX_BODY = 8_000_000
USER_AGENT = "hypergrok-bybit-public-research/1.7.1"
SAFE_HEADERS = (
    "date", "content-type", "content-length", "server", "x-cache", "via",
    "x-bapi-limit", "x-bapi-limit-status", "x-bapi-limit-reset-timestamp",
)
BACKOFF_SECONDS = (1, 2, 4)


class AccessBlocked(RuntimeError):
    def __init__(self, status: int, body: bytes, url: str, headers: dict):
        super().__init__(f"HTTP {status} from the official host; collection stopped without another host")
        self.status = status
        self.body = body
        self.url = url
        self.headers = headers


class TransportError(RuntimeError):
    pass


class ApiStatus(RuntimeError):
    def __init__(self, status: int, body: bytes, url: str):
        super().__init__(f"HTTP {status} was not retried")
        self.status = status
        self.body = body
        self.url = url


class RetryExhausted(RuntimeError):
    pass


class RequestBudget(RuntimeError):
    pass


@dataclass
class RawResponse:
    status: int
    headers: dict
    body: bytes


def public_url(path: str, query: dict) -> str:
    check_request("GET", path, query)
    encoded = urlencode(sorted(query.items()))
    url = ORIGIN + path + ("?" + encoded if encoded else "")
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "api.bybit.com" or parts.username or parts.port not in (None, 443):
        raise AllowlistError("URL is not the official https api.bybit.com endpoint")
    return url


def safe_headers(headers) -> dict:
    source = {str(key).lower(): str(value) for key, value in dict(headers).items()}
    return {key: source[key] for key in SAFE_HEADERS if key in source}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AccessBlocked(code, b"", newurl, safe_headers(headers))


class UrllibTransport:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def exchange(self, method: str, url: str, headers: dict) -> RawResponse:
        if method != "GET":
            raise AllowlistError("transport accepts GET only")
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                body = response.read(MAX_BODY + 1)
                status = response.status
                header_map = response.headers
        except AccessBlocked:
            raise
        except urllib.error.HTTPError as exc:
            body = exc.read(MAX_BODY + 1)
            return RawResponse(exc.code, safe_headers(exc.headers), body)
        except OSError as exc:
            raise TransportError(type(exc).__name__) from exc
        if len(body) > MAX_BODY:
            raise TransportError("response exceeded 8 MB")
        return RawResponse(status, safe_headers(header_map), body)


class PublicClient:
    def __init__(self, transport=None, sleep=time.sleep, clock=time.monotonic, max_attempts=MAX_ATTEMPTS):
        self.transport = transport or UrllibTransport()
        self.sleep = sleep
        self.clock = clock
        self.max_attempts = max_attempts
        self.max_requests = MAX_HTTP_REQUESTS
        self.min_interval = float(Decimal(MIN_INTERVAL_SECONDS))
        self.window_limit = WINDOW_REQUESTS
        self.window_seconds = float(Decimal(WINDOW_SECONDS))
        self.sent = 0
        self._last = None
        self._window = []

    def _pace(self) -> None:
        now = self.clock()
        self._window = [stamp for stamp in self._window if now - stamp < self.window_seconds]
        if len(self._window) >= self.window_limit:
            wait = self.window_seconds - (now - self._window[0])
            if wait > 0:
                self.sleep(wait)
                now = self.clock()
                self._window = [stamp for stamp in self._window if now - stamp < self.window_seconds]
        if self._last is not None:
            gap = self.min_interval - (now - self._last)
            if gap > 0:
                self.sleep(gap)
                now = self.clock()
        self._last = now
        self._window.append(now)

    def get_raw(self, path: str, query: dict) -> tuple[str, RawResponse]:
        url = public_url(path, query)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if set(headers) - {"User-Agent", "Accept"}:
            raise AllowlistError("request headers are not allowlisted")
        attempt = 0
        while True:
            if self.sent >= self.max_requests:
                raise RequestBudget("public request budget exhausted")
            self._pace()
            self.sent += 1
            try:
                response = self.transport.exchange("GET", url, headers)
            except AccessBlocked:
                raise
            except TransportError:
                if attempt + 1 >= self.max_attempts:
                    raise RetryExhausted("transport retries exhausted") from None
                self.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                attempt += 1
                continue
            if response.status in (401, 403, 451):
                raise AccessBlocked(response.status, response.body, url, response.headers)
            if response.status == 429 or response.status >= 500:
                if attempt + 1 >= self.max_attempts:
                    raise RetryExhausted(f"HTTP {response.status} retries exhausted")
                self.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                attempt += 1
                continue
            if response.status != 200:
                raise ApiStatus(response.status, response.body, url)
            if _ret_code(response.body) == 10006:
                if attempt + 1 >= self.max_attempts:
                    raise RetryExhausted("retCode 10006 retries exhausted")
                self.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                attempt += 1
                continue
            return url, response


def _ret_code(body: bytes):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload.get("retCode")
    return None
