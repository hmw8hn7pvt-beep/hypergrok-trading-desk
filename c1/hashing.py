"""SHA-256. Symlink özeti metinden alınır ve dolaylıdır."""

from __future__ import annotations

import hashlib


def ozet_bayt(veri: bytes) -> str:
    return hashlib.sha256(veri).hexdigest()


def ozet_dolayli(metin: str) -> str:
    return hashlib.sha256(metin.encode("utf-8", "surrogateescape")).hexdigest()
