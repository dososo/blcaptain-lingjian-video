from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.core.errors import LingjianError
from packages.core.project import ProjectRef, reindex_project

ARTIFACT_FILES = {
    "script": Path("artifacts/script.json"),
    "voice": Path("artifacts/voice_plan.json"),
    "visuals": Path("artifacts/visual_plan.json"),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_project_path(project: ProjectRef, candidate: Path) -> Path:
    root = project.path.resolve()
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise LingjianError(
            "PATH_OUTSIDE_PROJECT",
            "路径越过项目目录。",
            "请把文件放在项目目录内后重试。",
            {"path": str(candidate)},
        )
    return resolved


def artifact_path(project: ProjectRef, target: str) -> Path:
    if target not in ARTIFACT_FILES:
        raise LingjianError("INVALID_ARGUMENT", "未知 artifact 类型。", "请检查 target 参数。")
    return project.path / ARTIFACT_FILES[target]


def _snapshot_history(project: ProjectRef, target: str, current_path: Path) -> None:
    if not current_path.exists():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    history_dir = project.path / "history" / target
    history_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current_path, history_dir / f"{stamp}.json")


def write_artifact(
    project: ProjectRef,
    target: str,
    data: dict[str, Any],
    explicit_path: Path | None = None,
) -> Path:
    path = explicit_path or artifact_path(project, target)
    safe_project_path(project, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _snapshot_history(project, target, path)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    reindex_project(project.path)
    return path
