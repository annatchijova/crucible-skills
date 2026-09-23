"""Canonical, versioned serialization for the Skill IR artifact."""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "skill-ir/v1"


def canonical_bytes(value: Any) -> bytes:
    """Return stable UTF-8 JSON bytes for the artifact payload."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_payload(value: Any) -> str:
    """Hash a payload without allowing runtime metadata into the digest."""
    return f"sha256:{hashlib.sha256(canonical_bytes(value)).hexdigest()}"


def digest_bytes(value: bytes) -> str:
    """Hash exact source bytes without normalizing their representation."""
    return f"sha256:{hashlib.sha256(value).hexdigest()}"
