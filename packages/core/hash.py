from __future__ import annotations

import hashlib
import json
from typing import Any

IGNORED_KEYS = {"generated_at", "absolute_path", "log_path", "temp_path", "cache_path"}


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean(val) for key, val in sorted(value.items()) if key not in IGNORED_KEYS}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_clean(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
