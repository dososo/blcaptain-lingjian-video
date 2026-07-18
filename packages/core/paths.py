from __future__ import annotations

import re
from pathlib import Path

from packages.core.errors import LingjianError

SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_.:-]+$")


def safe_segment(value: str, field: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise LingjianError(
            "INVALID_PATH_SEGMENT",
            "路径片段不安全。",
            f"请检查 {field} 参数,只能使用普通标识符。",
            {"field": field, "value": value},
        )
    if not SAFE_SEGMENT.match(value):
        raise LingjianError(
            "INVALID_PATH_SEGMENT",
            "路径片段包含不允许的字符。",
            f"请检查 {field} 参数。",
            {"field": field, "value": value},
        )
    return value


def resolve_inside(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise LingjianError(
            "PATH_OUTSIDE_PROJECT",
            "路径越过项目目录。",
            "请使用项目目录内的路径。",
            {"path": str(candidate)},
        )
    return resolved
