# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Explicit 64-bit stream for proposed randomized controls.

The generator is PCG-XSH-RR (32-bit output) with a fixed odd increment.
Rejection sampling removes modulo bias. Streams are keyed by SHA-256 so
hypothesis, N, symbol, and run do not share draws.
"""

from __future__ import annotations

import hashlib

MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1


def stream_seed(label: str) -> int:
    digest = hashlib.sha256(label.encode()).digest()
    value = int.from_bytes(digest[:8], "big")
    return value or 1


class PCG32:
    def __init__(self, seed: int):
        self.inc = 0xDA3E39CB94B95BDB  # fixed odd increment
        self.state = 0
        self._step()
        self.state = (self.state + (seed & MASK64)) & MASK64
        self._step()

    def _step(self) -> int:
        old = self.state
        self.state = (old * 6364136223846793005 + self.inc) & MASK64
        xorshifted = (((old >> 18) ^ old) >> 27) & MASK32
        rot = (old >> 59) & 31
        return ((xorshifted >> rot) | (xorshifted << ((-rot) & 31))) & MASK32

    def next_u32(self) -> int:
        return self._step()

    def randrange(self, bound: int) -> int:
        if not isinstance(bound, int) or bound <= 0 or bound > MASK32:
            raise ValueError("bound must be a positive integer up to 2^32")
        # Rejection sampling on 32-bit draws.
        limit = (1 << 32) // bound * bound
        while True:
            draw = self.next_u32()
            if draw < limit:
                return draw % bound


def control_stream(hypothesis: str, n: int, symbol: str, run: int) -> PCG32:
    label = f"bybit-linear-proposed-h2br-v1|{hypothesis}|{n}|{symbol}|{run}|20261109"
    return PCG32(stream_seed(label))


def bootstrap_stream(label: str) -> PCG32:
    return PCG32(stream_seed("bybit-linear-proposed-bootstrap|" + label))
