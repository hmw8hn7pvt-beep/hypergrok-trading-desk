# Copyright (c) 2026 Galleon Labs
# SPDX-License-Identifier: MIT
"""Offline bundle verification. It recomputes hashes and refuses a performance claim.

Verification does not contact Bybit and does not run the comparison engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from bybit_research.allowlist import PATHS, check_request
from bybit_research.collect import BANNED_FIELDS
from bybit_research.jsonutil import sha256_bytes, sha256_file


class VerifyError(RuntimeError):
    pass


def verify_bundle(bundle: str | Path) -> dict:
    root = Path(bundle)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise VerifyError("manifest.json is missing")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("host") != "api.bybit.com" or manifest.get("method") != "GET":
        raise VerifyError("manifest host or method is outside the public GET allowlist")
    if manifest.get("market_performance") != "not_executed":
        raise VerifyError("manifest claims market performance; this verifier rejects that claim")
    if manifest.get("strict_sufficient_for_primary") is True:
        raise VerifyError("manifest claims primary sufficiency; strict review has to be recomputed and is not implied by hashes")
    if manifest.get("result") == "blocked" and not (root / "blocker.json").is_file():
        raise VerifyError("blocked result has no blocker record")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise VerifyError("manifest file list is missing")
    seen = set()
    for entry in files:
        relative = entry["path"]
        if relative in seen or relative.startswith("/") or ".." in Path(relative).parts:
            raise VerifyError("manifest path is duplicated or escapes the bundle")
        seen.add(relative)
        path = root / relative
        if not path.is_file():
            raise VerifyError(f"listed file is missing: {relative}")
        if sha256_file(path) != entry["sha256"]:
            raise VerifyError(f"hash mismatch: {relative}")
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        if relative not in seen:
            raise VerifyError(f"unlisted file: {relative}")
    for meta_path in sorted((root / "raw").glob("*.meta.json")):
        meta = json.loads(meta_path.read_text())
        _check_meta(root, meta)
    if (root / "blocker.json").is_file():
        blocker = json.loads((root / "blocker.json").read_text())
        if urlsplit(blocker["url"]).hostname != "api.bybit.com":
            raise VerifyError("blocker URL is not api.bybit.com")
        body = (root / blocker["body_file"]).read_bytes()
        if sha256_bytes(body) != blocker["body_sha256"]:
            raise VerifyError("blocker body hash mismatch")
    for csv_path in (root / "normalized").rglob("*.csv") if (root / "normalized").exists() else []:
        header = csv_path.read_text().splitlines()[0].split(",")
        if BANNED_FIELDS & set(header):
            raise VerifyError(f"coverage file contains a strategy field: {csv_path.name}")
    return {
        "verification": "consistent",
        "result": manifest.get("result"),
        "market_performance": "not_executed",
        "strict_sufficient_for_primary": False,
        "file_count": len(files),
    }


def _check_meta(root: Path, meta: dict) -> None:
    parts = urlsplit(meta["url"])
    if meta.get("method") != "GET" or parts.scheme != "https" or parts.hostname != "api.bybit.com":
        raise VerifyError("captured request is not an official public GET")
    if parts.path not in PATHS:
        raise VerifyError("captured path is not allowlisted")
    check_request("GET", parts.path, meta["query"])
    body = (root / meta["body_file"]).read_bytes()
    if sha256_bytes(body) != meta["body_sha256"]:
        raise VerifyError("captured body hash mismatch")
