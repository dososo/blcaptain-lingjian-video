from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from pathlib import Path
from subprocess import TimeoutExpired
from subprocess import run as run_subprocess
from typing import Any

from packages.core.paths import resolve_inside
from packages.core.project import ProjectRef

VISUAL_GENERATOR_TIMEOUT_SEC = 90


def ensure_scene_asset(project: ProjectRef, scene: dict[str, Any]) -> dict[str, Any]:
    """Best-effort host generation. Failure is recorded and render falls back."""
    expected = _expected_asset_path(project, scene)
    if expected is None:
        return scene
    scene["expected_asset_path"] = str(expected.relative_to(project.path))
    if not scene.get("asset_path"):
        scene["asset_path"] = scene["expected_asset_path"]
    current = resolve_inside(project.path, project.path / str(scene["asset_path"]))
    if current.exists():
        scene["generation_status"] = "existing"
        return scene
    argv = _generator_argv(str(scene.get("generator") or ""))
    if not argv:
        scene["generation_status"] = "unavailable"
        return scene
    expected.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": "generate_visual_asset",
        "generator": scene.get("generator"),
        "scene_id": scene.get("scene_id") or scene.get("id"),
        "visual_prompt": scene.get("visual_prompt") or scene.get("narration_text") or "",
        "motion_spec": scene.get("motion_spec") or scene.get("motion") or {},
        "brief": scene.get("brief") or {},
        "duration_sec": scene.get("duration_sec") or 1.0,
        "expected_asset_path": str(expected),
    }
    try:
        completed = run_subprocess(
            argv,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
            timeout=VISUAL_GENERATOR_TIMEOUT_SEC,
        )
    except (OSError, TimeoutExpired):
        scene["generation_status"] = "failed"
        return scene
    if completed.returncode != 0:
        scene["generation_status"] = "failed"
        return scene
    _apply_generated_asset_path(project, scene, completed.stdout, expected)
    if resolve_inside(project.path, project.path / str(scene["asset_path"])).exists():
        scene["generation_status"] = "generated"
    else:
        scene["generation_status"] = "missing_output"
    return scene


def _expected_asset_path(project: ProjectRef, scene: dict[str, Any]) -> Path | None:
    raw = scene.get("expected_asset_path") or scene.get("asset_path")
    if isinstance(raw, str) and raw:
        return resolve_inside(project.path, project.path / raw)
    generator = str(scene.get("generator") or "")
    scene_id = str(scene.get("scene_id") or scene.get("id") or "")
    if not scene_id or generator == "fallback_solid":
        return None
    ext = ".png" if generator == "image-gen" else ".mp4"
    return resolve_inside(project.path, project.path / "assets" / "scenes" / f"{scene_id}{ext}")


def _generator_argv(generator: str) -> list[str]:
    env_map = {
        "image-gen": "LINGJIAN_HOST_IMAGEGEN_CLI",
        "hyperframes": "LINGJIAN_HOST_HYPERFRAMES_CLI",
        "remotion": "LINGJIAN_HOST_REMOTION_CLI",
    }
    command_map = {
        "image-gen": "imagegen",
        "hyperframes": "hyperframes",
        "remotion": "remotion",
    }
    env_command = os.getenv(env_map.get(generator, ""), "")
    if env_command:
        try:
            argv = shlex.split(env_command)
        except ValueError:
            return []
        return argv if argv and _command_exists(argv[0]) else []
    if generator == "hyperframes" and _npx_hyperframes_available():
        adapter = _repo_root() / "scripts" / "providers" / "hyperframes_scene_cli.py"
        return [sys.executable, str(adapter)]
    command = command_map.get(generator)
    if command and shutil.which(command):
        return [command]
    return []


def _command_exists(command: str) -> bool:
    path = Path(command)
    if path.parts and (path.is_absolute() or len(path.parts) > 1):
        return path.exists()
    return shutil.which(command) is not None


def _npx_hyperframes_available() -> bool:
    npx = shutil.which("npx")
    if not npx:
        return False
    try:
        completed = run_subprocess(
            [npx, "hyperframes", "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, TimeoutExpired):
        return False
    return completed.returncode == 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _apply_generated_asset_path(
    project: ProjectRef,
    scene: dict[str, Any],
    stdout: str,
    expected: Path,
) -> None:
    asset = expected
    try:
        decoded = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        decoded = {}
    if isinstance(decoded, dict) and isinstance(decoded.get("asset_path"), str):
        raw = Path(decoded["asset_path"])
        asset = raw if raw.is_absolute() else project.path / raw
    try:
        resolved = resolve_inside(project.path, asset)
    except Exception:
        resolved = expected
    scene["asset_path"] = str(resolved.relative_to(project.path))
