"""Deterministic identifier generation.

All record identifiers are UUIDv5 values derived from a fixed namespace and
a stable key, so the same persona, parameters, and seed always produce the
same identifiers.
"""

from __future__ import annotations

import uuid

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/vitalforge/vitalforge")


def stable_id(*parts: str) -> str:
    """Return a deterministic UUIDv5 string for the given key parts."""
    return str(uuid.uuid5(_NAMESPACE, ":".join(parts)))
