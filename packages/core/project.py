from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ProjectRef:
    path: Path
    name: str

    def __post_init__(self) -> None:
        self.path = self.path.resolve()


def _artifact_flags(project_path: Path) -> dict[str, bool]:
    artifacts = project_path / "artifacts"
    return {
        "script": (artifacts / "script.json").exists(),
        "voice": (artifacts / "voice_plan.json").exists(),
        "visuals": (artifacts / "visual_plan.json").exists(),
    }


def _derive_state(project_path: Path) -> str:
    flags = _artifact_flags(project_path)
    if flags["visuals"]:
        return "visuals_review"
    if flags["voice"]:
        return "voice_review"
    if flags["script"]:
        return "script_review"
    if (project_path / "assets" / "input_assets.json").exists():
        return "input_ready"
    return "created"


def _write_index(project_path: Path) -> None:
    db_dir = project_path / ".lingjian"
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_dir / "index.sqlite")
    try:
        conn.execute(
            "create table if not exists status (key text primary key, value text not null)"
        )
        conn.execute(
            "insert or replace into status(key, value) values ('state', ?)",
            (_derive_state(project_path),),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_approval_secret(project_path: Path) -> None:
    path = project_path / ".lingjian" / "approval_secret"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(os.urandom(32).hex(), encoding="utf-8")
    path.chmod(0o600)


def init_project(project_path: Path, name: str) -> ProjectRef:
    project_path.mkdir(parents=True, exist_ok=True)
    for rel in ["assets", "artifacts", "history", "previews", "renders", "logs"]:
        (project_path / rel).mkdir(parents=True, exist_ok=True)
    (project_path / "project.yaml").write_text(f"name: {name}\n", encoding="utf-8")
    (project_path / "manifest.json").write_text(
        json.dumps({"name": name, "state": "created"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _ensure_approval_secret(project_path)
    _write_index(project_path)
    return ProjectRef(project_path, name)


def reindex_project(project_path: Path) -> None:
    _write_index(project_path)


def status_project(project_path: Path) -> dict[str, Any]:
    return {"state": _derive_state(project_path), "artifacts": _artifact_flags(project_path)}
