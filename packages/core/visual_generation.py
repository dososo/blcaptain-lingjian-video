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

VISUAL_GENERATOR_TIMEOUT_SEC = 300
HOST_VISUAL_ASSET_MAX_DURATION_SEC = 12.0


def ensure_scene_asset(project: ProjectRef, scene: dict[str, Any]) -> dict[str, Any]:
    """Best-effort host generation. Failure is recorded and render falls back."""
    expected = _expected_asset_path(project, scene)
    if expected is None:
        return scene
    scene["expected_asset_path"] = str(expected.relative_to(project.path))
    if not scene.get("asset_path"):
        scene["asset_path"] = scene["expected_asset_path"]
    current = resolve_inside(project.path, project.path / str(scene["asset_path"]))
    if current.exists() and not _existing_asset_needs_host_regeneration(
        project, scene, current
    ):
        scene["generation_status"] = "existing"
        return scene
    generator = str(scene.get("generator") or "")
    argv = _generator_argv(generator)
    if not argv:
        scene["generation_status"] = "unavailable"
        return scene
    scene["asset_origin"] = _generator_origin(generator, argv)
    expected.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": "generate_visual_asset",
        "generator": scene.get("generator"),
        "scene_id": scene.get("scene_id") or scene.get("id"),
        "role": scene.get("role"),
        "on_screen_text": scene.get("on_screen_text"),
        "narration_text": scene.get("narration_text"),
        "visual_prompt": scene.get("visual_prompt") or scene.get("narration_text") or "",
        "motion_spec": scene.get("motion_spec") or scene.get("motion") or {},
        "brief": scene.get("brief") or {},
        "duration_sec": _host_visual_asset_duration(scene.get("duration_sec") or 1.0),
        "expected_asset_path": str(expected),
        "project_root": str(project.path),
        "blueprint_id": scene.get("blueprint_id") or scene.get("template_id"),
        "visual_archetype": scene.get("visual_archetype"),
        "asset_recipe_id": scene.get("asset_recipe_id"),
        "material_key": scene.get("material_key"),
        "transition_plan": scene.get("transition_plan"),
        "motion_intent": scene.get("motion_intent"),
        "motion_rule_ids": scene.get("motion_rule_ids"),
        "layout_contract": scene.get("layout_contract"),
        "caption_contract": scene.get("caption_contract"),
        "keyframes": scene.get("keyframes"),
        "director_board": scene.get("director_board"),
        "director_review_sheet": scene.get("director_review_sheet"),
        "director_review_sheet_v2": scene.get("director_review_sheet_v2"),
        "engine_policy": scene.get("engine_policy"),
        "route_reason": scene.get("route_reason"),
        "asset_strategy_v2": scene.get("asset_strategy_v2"),
        "expected_real_evidence": scene.get("expected_real_evidence"),
        "evidence_asset_refs": scene.get("evidence_asset_refs"),
        "evidence_asset_ids": scene.get("evidence_asset_ids"),
        "director_knowledge_refs": scene.get("director_knowledge_refs"),
    }
    scene["host_generation_contract"] = _host_generation_contract(scene["asset_origin"], payload)
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
    resolved_asset = resolve_inside(project.path, project.path / str(scene["asset_path"]))
    if resolved_asset.exists():
        scene["generation_status"] = "generated"
        _write_host_contract_sidecar(project, scene, resolved_asset)
    else:
        scene["generation_status"] = "missing_output"
    return scene


def _existing_asset_needs_host_regeneration(
    project: ProjectRef, scene: dict[str, Any], asset: Path
) -> bool:
    if str(scene.get("generator") or "") not in {"hyperframes", "seedance"}:
        return False
    if _host_contract_confirmed(scene.get("host_generation_contract")):
        return False
    sidecar = _read_host_contract_sidecar(project, asset)
    contract = sidecar.get("host_generation_contract")
    if _host_contract_confirmed(contract):
        scene["host_generation_contract"] = contract
        if sidecar.get("asset_origin"):
            scene["asset_origin"] = sidecar["asset_origin"]
        return False
    try:
        relative = asset.relative_to(project.path)
    except ValueError:
        return False
    parts = relative.parts
    return len(parts) >= 3 and parts[:2] == ("assets", "scenes")


def _host_contract_confirmed(contract: Any) -> bool:
    return isinstance(contract, dict) and contract.get("contract_confirmed_by_generator") is True


def _host_contract_sidecar_path(asset: Path) -> Path:
    return asset.with_name(f"{asset.name}.host_generation_contract.json")


def _read_host_contract_sidecar(project: ProjectRef, asset: Path) -> dict[str, Any]:
    sidecar = _host_contract_sidecar_path(asset)
    try:
        resolved = resolve_inside(project.path, sidecar)
    except Exception:
        return {}
    if not resolved.exists():
        return {}
    try:
        decoded = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _write_host_contract_sidecar(
    project: ProjectRef,
    scene: dict[str, Any],
    asset: Path,
) -> None:
    contract = scene.get("host_generation_contract")
    if not _host_contract_confirmed(contract):
        return
    try:
        relative_asset = asset.relative_to(project.path)
        sidecar = resolve_inside(project.path, _host_contract_sidecar_path(asset))
    except Exception:
        return
    payload = {
        "asset_path": str(relative_asset),
        "asset_origin": scene.get("asset_origin"),
        "host_generation_contract": contract,
    }
    try:
        sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return


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
        "seedance": "LINGJIAN_HOST_SEEDANCE_CLI",
    }
    command_map = {
        "image-gen": "imagegen",
        "hyperframes": "hyperframes",
        "remotion": "remotion",
        "seedance": "seedance",
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
    if generator == "seedance" and _seedance_available():
        adapter = _repo_root() / "scripts" / "providers" / "seedance_scene_cli.py"
        return [sys.executable, str(adapter)]
    command = command_map.get(generator)
    if command and shutil.which(command):
        return [command]
    return []


def _generator_origin(generator: str, argv: list[str]) -> str:
    if generator == "hyperframes" and argv and argv[-1].endswith("hyperframes_scene_cli.py"):
        return "lingjian_hyperframes_director"
    if generator == "seedance" and argv and argv[-1].endswith("seedance_scene_cli.py"):
        return "lingjian_seedance_generator"
    if generator in {"hyperframes", "remotion", "image-gen", "seedance"}:
        return "external_visual_generator"
    return "unknown"


def _seedance_available() -> bool:
    """seedance 适配器 --probe:有 ARK key(环境变量或钥匙串)返回 0。"""
    adapter = _repo_root() / "scripts" / "providers" / "seedance_scene_cli.py"
    if not adapter.exists():
        return False
    try:
        completed = run_subprocess(
            [sys.executable, str(adapter), "--probe"],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, TimeoutExpired):
        return False
    return completed.returncode == 0


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


def _host_visual_asset_duration(duration: Any) -> float:
    try:
        value = float(duration)
    except (TypeError, ValueError):
        value = 1.0
    return max(min(value, HOST_VISUAL_ASSET_MAX_DURATION_SEC), 0.8)


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
    if isinstance(decoded, dict) and isinstance(decoded.get("host_generation_contract"), dict):
        decoded_contract = decoded["host_generation_contract"]
        existing = scene.get("host_generation_contract")
        base_contract = existing if isinstance(existing, dict) else {}
        scene["host_generation_contract"] = {
            **base_contract,
            **decoded_contract,
            "contract_confirmed_by_generator": (
                decoded_contract.get("contract_confirmed_by_generator") is True
            ),
        }
    try:
        resolved = resolve_inside(project.path, asset)
    except Exception:
        resolved = expected
    scene["asset_path"] = str(resolved.relative_to(project.path))


def _host_generation_contract(origin: str, payload: dict[str, Any]) -> dict[str, Any]:
    transition_plan = payload.get("transition_plan")
    transition_family = (
        transition_plan.get("family")
        if isinstance(transition_plan, dict)
        else None
    )
    motion_intent = payload.get("motion_intent")
    motion_rule_ids = payload.get("motion_rule_ids")
    if not isinstance(motion_rule_ids, list) and isinstance(motion_intent, dict):
        motion_rule_ids = motion_intent.get("motion_rule_ids")
    evidence_refs = payload.get("evidence_asset_refs")
    keyframes = _payload_keyframes(payload)
    keyframe_states = [_keyframe_state_text(item) for item in keyframes]
    keyframe_state_count = len({state for state in keyframe_states if state})
    return {
        "adapter": origin,
        "blueprint_id": payload.get("blueprint_id"),
        "visual_archetype": payload.get("visual_archetype"),
        "asset_recipe_id": payload.get("asset_recipe_id"),
        "material_key": payload.get("material_key"),
        "layout_signature": _layout_signature(payload),
        "transition_family": transition_family,
        "motion_rule_ids": motion_rule_ids if isinstance(motion_rule_ids, list) else [],
        "keyframe_count": len(keyframes),
        "keyframe_state_count": keyframe_state_count,
        "evidence_ref_count": len(evidence_refs) if isinstance(evidence_refs, list) else 0,
        "evidence_media_count": _evidence_media_count(evidence_refs),
        "contract_confirmed_by_generator": False,
    }


def _payload_keyframes(payload: dict[str, Any]) -> list[Any]:
    direct = payload.get("keyframes") or payload.get("keyframe_beats")
    if isinstance(direct, list):
        return [item for item in direct if item is not None]
    board = payload.get("director_board")
    if isinstance(board, dict):
        board_keyframes = board.get("keyframes") or board.get("keyframe_beats")
        if isinstance(board_keyframes, list):
            return [item for item in board_keyframes if item is not None]
    for key in ("director_review_sheet_v2", "director_review_sheet"):
        sheet = payload.get(key)
        if isinstance(sheet, dict):
            sheet_keyframes = sheet.get("keyframes") or sheet.get("keyframe_beats")
            if isinstance(sheet_keyframes, list):
                return [item for item in sheet_keyframes if item is not None]
    return []


def _keyframe_state_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("state", "description", "visual_state", "action", "beat"):
            text = str(value.get(key) or "").strip()
            if text:
                return " ".join(text.lower().split())
    if isinstance(value, str):
        return " ".join(value.strip().lower().split())
    return ""


def _layout_signature(payload: dict[str, Any]) -> str:
    for key in ("layout_signature", "layout_id", "layout_class"):
        value = payload.get(key)
        if value:
            return str(value)
    layout = payload.get("layout_contract")
    if isinstance(layout, dict):
        for key in ("layout_signature", "layout_id", "layout_class", "template_id"):
            value = layout.get(key)
            if value:
                return str(value)
    return str(payload.get("visual_archetype") or "")


def _evidence_media_count(evidence_refs: Any) -> int:
    if not isinstance(evidence_refs, list):
        return 0
    count = 0
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            continue
        raw = str(
            ref.get("media_path")
            or ref.get("evidence_clip_path")
            or ref.get("path")
            or ""
        )
        if Path(raw).suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".mp4",
            ".mov",
            ".m4v",
            ".webm",
        }:
            count += 1
    return count
