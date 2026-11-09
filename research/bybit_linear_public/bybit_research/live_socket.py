# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Minimal stdlib WebSocket client for the one public linear URL.

Importing this module does not open a socket. Call `open_public_socket` only
from an explicit live command. No proxy environment variables are read.
"""

from __future__ import annotations

import base64
import os
import socket
import ssl
from urllib.parse import urlsplit

try:
    from bybit_research.live_public import PUBLIC_LINEAR_URL, FeedClosed, check_public_linear_url
except ImportError:  # standalone Windows folder, not the repository package
    from live_public import PUBLIC_LINEAR_URL, FeedClosed, check_public_linear_url


class PublicSocket:
    def __init__(self, raw: socket.socket):
        self.raw = raw
        self._buffer = b""

    def send(self, text: str) -> None:
        self.raw.sendall(_client_frame(text.encode()))

    def recv(self, timeout_ms: int) -> str | None:
        self.raw.settimeout(max(timeout_ms, 1) / 1000)
        while True:
            frame = _read_frame(self)
            if frame is None:
                return None
            opcode, payload = frame
            if opcode == 0x1:
                return payload.decode()
            if opcode == 0x8:
                raise FeedClosed("server closed the public socket")
            if opcode == 0x9:
                self.raw.sendall(_client_frame(payload, opcode=0xA))
            if opcode == 0xA:
                continue

    def close(self) -> None:
        try:
            self.raw.sendall(_client_frame(b"", opcode=0x8))
        except OSError:
            pass
        self.raw.close()


def open_public_socket(url: str = PUBLIC_LINEAR_URL, timeout: float = 10.0) -> PublicSocket:
    check_public_linear_url(url)
    parts = urlsplit(url)
    raw = socket.create_connection((parts.hostname, 443), timeout)
    tls = None
    try:
        tls = ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {parts.path} HTTP/1.1\r\n"
            f"Host: {parts.hostname}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        tls.sendall(request.encode())
        header, rest = _read_headers(tls)
        status = header.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise FeedClosed("public websocket upgrade was refused")
        wrapped = PublicSocket(tls)
        wrapped._buffer = rest
        return wrapped
    except Exception:
        if tls is not None:
            tls.close()
        else:
            raw.close()
        raise


def _client_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    length = len(payload)
    if length < 126:
        head = bytes([0x80 | opcode, 0x80 | length])
    elif length < 65536:
        head = bytes([0x80 | opcode, 0x80 | 126]) + length.to_bytes(2, "big")
    else:
        head = bytes([0x80 | opcode, 0x80 | 127]) + length.to_bytes(8, "big")
    return head + mask + masked


def _read_headers(raw) -> tuple[bytes, bytes]:
    data = b""
    marker = b"\r\n\r\n"
    while marker not in data:
        chunk = raw.recv(4096)
        if not chunk:
            raise FeedClosed("public socket closed during handshake")
        data += chunk
        if len(data) > 65536:
            raise FeedClosed("public handshake exceeded 64 KiB")
    head, rest = data.split(marker, 1)
    return head, rest


def _read_frame(sock: PublicSocket):
    try:
        header = _exact(sock, 2)
    except TimeoutError:
        return None
    except FeedClosed:
        raise
    if header is None:
        return None
    first, second = header
    opcode = first & 0x0F
    masked = second & 0x80
    length = second & 0x7F
    if length == 126:
        length = int.from_bytes(_exact(sock, 2), "big")
    elif length == 127:
        length = int.from_bytes(_exact(sock, 8), "big")
    mask = _exact(sock, 4) if masked else b""
    payload = _exact(sock, length) if length else b""
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return opcode, payload


def _exact(sock: PublicSocket, size: int) -> bytes:
    while len(sock._buffer) < size:
        try:
            chunk = sock.raw.recv(4096)
        except TimeoutError:
            raise
        except socket.timeout:
            raise TimeoutError("public socket timed out") from None
        if not chunk:
            raise FeedClosed("public socket closed")
        sock._buffer += chunk
    data, sock._buffer = sock._buffer[:size], sock._buffer[size:]
    return data
