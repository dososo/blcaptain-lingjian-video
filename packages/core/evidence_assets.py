from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any

from packages.core.project import ProjectRef

EVIDENCE_MANIFEST = Path("assets/evidence/evidence_assets.json")
EVIDENCE_CLIPS_DIR = Path("assets/evidence/clips")
OPEN_SOURCE_MIN_EVIDENCE_TYPES = 3
EVIDENCE_CLIP_DURATION_SEC = 3.0
SOURCE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
SOURCE_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
SOURCE_VIDEO_EVIDENCE_TYPES = {
    "web_recording_capture",
    "terminal_recording_capture",
    "codex_operation_recording",
    "screen_recording_capture",
}
ASSET_RECIPE_EVIDENCE_TYPES = {
    "codex_prompt_or_reconstructed_ui": {
        "codex_operation_recording",
        "screen_recording_capture",
    },
    "codex_operation_capture": {
        "codex_operation_recording",
        "screen_recording_capture",
    },
    "ffprobe_terminal_capture": {
        "terminal_recording_capture",
        "screen_recording_capture",
    },
    "github_repo_star_capture": {
        "web_recording_capture",
        "screen_recording_capture",
    },
    "qa_report_capture": {
        "terminal_recording_capture",
        "screen_recording_capture",
    },
    "readme_install_capture": {
        "web_recording_capture",
        "screen_recording_capture",
    },
    "render_manifest_capture": {
        "terminal_recording_capture",
        "screen_recording_capture",
    },
    "repo_and_cli_flash": {
        "codex_operation_recording",
        "screen_recording_capture",
        "terminal_recording_capture",
        "web_recording_capture",
    },
    "visual_asset_generation_queue": {
        "codex_operation_recording",
        "screen_recording_capture",
    },
}
EVIDENCE_MATERIALIZATION_PROFILES = {
    "open_source_project_intro",
    "product_intro",
    "tutorial_guide",
    "review_comparison",
    "ecommerce_sales",
    "douyin_product",
}
TERMINAL_TEXT_EXTENSIONS = {".log", ".txt"}


def evidence_manifest_path(project: ProjectRef) -> Path:
    return project.path / EVIDENCE_MANIFEST


def load_evidence_assets(project: ProjectRef) -> dict[str, Any]:
    path = evidence_manifest_path(project)
    if not path.exists():
        return {
            "version": "v1",
            "assets": [],
            "evidence_types": [],
            "count": 0,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def collect_evidence_assets(project: ProjectRef, profile: str | None = None) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    _collect_input_assets(project, assets)
    _collect_known_artifacts(project, assets)
    assets = _dedupe_assets(assets)
    evidence_types = sorted(
        {str(asset.get("evidence_type")) for asset in assets if asset.get("evidence_type")}
    )
    manifest = {
        "version": "v1",
        "profile": profile,
        "assets": assets,
        "evidence_types": evidence_types,
        "count": len(assets),
        "publish_grade_note_zh": (
            "这些是可审计证据素材来源,不等于发布级动态视频画面;"
            "发布级镜头仍必须渲染为 mp4/mov/m4v/webm。"
        ),
    }
    path = evidence_manifest_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def materialize_evidence_clips(project: ProjectRef, manifest: dict[str, Any]) -> dict[str, Any]:
    assets = [dict(asset) for asset in manifest.get("assets", []) if isinstance(asset, dict)]
    if not assets:
        return manifest
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    clips_dir = project.path / EVIDENCE_CLIPS_DIR
    clips_dir.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        clip_id = _safe_clip_id(str(asset.get("id") or asset.get("evidence_type") or "evidence"))
        clip_path = clips_dir / f"{clip_id}.mp4"
        text_path = clips_dir / f"{clip_id}.txt"
        style = _evidence_clip_style(asset)
        source_video_path = _asset_source_video_path(project, asset)
        if source_video_path:
            asset["evidence_clip_path"] = _relative_if_inside(project, source_video_path)
            asset["evidence_clip_render_source"] = "source_video_capture"
            asset["evidence_visual_source"] = _source_video_visual_source(asset)
            asset["evidence_clip_style"] = style["id"]
            asset["evidence_clip_role_zh"] = style["role_zh"]
            asset["evidence_capture_note_zh"] = (
                "该证据来自真实动态视频录屏;仍需经过发布级视频/字幕/构图 QA。"
            )
            if _source_video_is_verifiable(ffprobe, source_video_path):
                asset["evidence_clip_status"] = "captured"
                asset["materialized_evidence_video"] = True
                asset["publish_grade_evidence_video"] = True
                duration_sec = _source_video_duration_sec(ffprobe, source_video_path)
                if duration_sec is not None:
                    asset["source_video_duration_sec"] = duration_sec
                    asset["evidence_clip_duration_sec"] = duration_sec
            else:
                asset["evidence_clip_status"] = "not_verifiable"
                asset["materialized_evidence_video"] = False
                asset["publish_grade_evidence_video"] = False
                asset["evidence_clip_error"] = "ffprobe 未能确认该录屏包含有效视频流。"
            continue
        source_image_path = _asset_source_image_path(project, asset)
        terminal_log_path = None if source_image_path else _asset_terminal_log_path(project, asset)
        text_path.write_text(
            _evidence_text_for_asset(project, asset, style, terminal_log_path),
            encoding="utf-8",
        )
        asset["evidence_clip_path"] = _relative_if_inside(project, clip_path)
        asset["evidence_clip_render_source"] = _evidence_clip_render_source(
            source_image_path,
            terminal_log_path,
        )
        asset["evidence_visual_source"] = _evidence_visual_source(
            source_image_path,
            terminal_log_path,
        )
        asset["evidence_clip_style"] = style["id"]
        asset["evidence_clip_role_zh"] = style["role_zh"]
        if source_image_path:
            asset["evidence_capture_note_zh"] = (
                "该证据短片基于静态截图/图片渲染为扫描动效,不是屏幕录制。"
            )
        elif terminal_log_path:
            asset["evidence_capture_note_zh"] = (
                "该证据短片基于项目日志文本渲染为终端回放,不是屏幕录制。"
            )
        else:
            asset["evidence_capture_note_zh"] = (
                "该证据短片基于文本/JSON 产物渲染为动态证据卡,不是屏幕录制。"
            )
        if not ffmpeg:
            asset["evidence_clip_status"] = "ffmpeg_unavailable"
            continue
        if source_image_path:
            command = _source_image_evidence_command(
                ffmpeg,
                source_image_path,
                text_path,
                style,
                clip_path,
            )
        elif terminal_log_path:
            command = _terminal_evidence_command(ffmpeg, text_path, style, clip_path)
        else:
            command = _text_evidence_command(ffmpeg, text_path, style, clip_path)
        try:
            completed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, TimeoutExpired):
            asset["evidence_clip_status"] = "failed"
            continue
        if completed.returncode == 0 and clip_path.exists() and clip_path.stat().st_size > 0:
            asset["evidence_clip_status"] = "generated"
            asset["materialized_evidence_video"] = True
            asset["publish_grade_evidence_video"] = False
        else:
            asset["evidence_clip_status"] = "failed"
            asset["materialized_evidence_video"] = False
            asset["publish_grade_evidence_video"] = False
            asset["evidence_clip_error"] = _stderr_tail(completed.stderr)
    updated = {
        **manifest,
        "assets": assets,
        "evidence_clip_summary": {
            "render_source": "dynamic_ffmpeg_drawtext",
            "render_sources": sorted(
                {str(asset.get("evidence_clip_render_source")) for asset in assets}
            ),
            "visual_sources": sorted(
                {str(asset.get("evidence_visual_source")) for asset in assets}
            ),
            "generated_count": sum(
                1 for asset in assets if asset.get("evidence_clip_status") == "generated"
            ),
            "total": len(assets),
            "styles": sorted({str(asset.get("evidence_clip_style")) for asset in assets}),
        },
    }
    evidence_manifest_path(project).write_text(
        json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return updated


def evidence_assets_for_scene(
    manifest: dict[str, Any],
    *,
    expected_real_evidence: list[Any] | None = None,
    asset_recipe_id: str | None = None,
    scene_id: str | None = None,
    project: ProjectRef | None = None,
) -> list[dict[str, Any]]:
    assets = [
        asset
        for asset in manifest.get("assets", [])
        if isinstance(asset, dict) and _target_scene_matches(asset, scene_id)
    ]
    assets = [
        asset
        for asset in assets
        if _publish_grade_recording_targets_scene(asset, scene_id)
    ]
    if not assets:
        return []
    expected = " ".join(str(item) for item in expected_real_evidence or [])
    if asset_recipe_id:
        expected = f"{expected} {asset_recipe_id}"
    preferred_types = _preferred_evidence_types(expected)
    selected = [
        asset
        for asset in assets
        if not preferred_types or str(asset.get("evidence_type")) in preferred_types
    ]
    if preferred_types and not selected:
        return []
    selected = _prioritize_publish_grade_evidence_assets(selected)
    return [_scene_evidence_ref(project, asset) for asset in selected[:3]]


def _scene_recovery_command_text(project: ProjectRef | None, value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return ""
    if project is None:
        return text
    candidates = {str(project.path)}
    try:
        candidates.add(str(project.path.resolve()))
    except OSError:
        pass
    for candidate in candidates:
        if candidate and candidate != "/":
            text = text.replace(candidate, "<project>")
    text = text.replace("'<project>'", "<project>")
    text = text.replace('"<project>"', "<project>")
    return text


def _scene_evidence_ref(project: ProjectRef | None, asset: dict[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "id": str(asset.get("id")),
        "evidence_type": str(asset.get("evidence_type")),
        "path": str(asset.get("path") or ""),
        "source_uri": str(asset.get("source_uri") or ""),
        "evidence_clip_path": str(asset.get("evidence_clip_path") or ""),
        "evidence_clip_status": str(asset.get("evidence_clip_status") or ""),
        "evidence_clip_render_source": str(asset.get("evidence_clip_render_source") or ""),
        "evidence_visual_source": str(asset.get("evidence_visual_source") or ""),
        "evidence_clip_style": str(asset.get("evidence_clip_style") or ""),
        "evidence_clip_role_zh": str(asset.get("evidence_clip_role_zh") or ""),
        "materialized_evidence_video": bool(asset.get("materialized_evidence_video")),
        "publish_grade_evidence_video": bool(asset.get("publish_grade_evidence_video")),
        "target_scene_id": str(asset.get("target_scene_id") or ""),
    }
    for key in (
        "role",
        "origin",
        "recording_status",
        "source_video_probe_status",
        "source_video_probe_tool",
        "source_video_probe_hint_zh",
        "recording_task_redacted",
        "task_redacted",
        "next_action_zh",
        "manual_fallback_note_zh",
        "privacy_notice_zh",
        "evidence_capture_note_zh",
        "note_zh",
    ):
        value = str(asset.get(key) or "").strip()
        if value:
            ref[key] = value
    for key in ("next_command", "manual_fallback_command"):
        value = _scene_recovery_command_text(project, asset.get(key))
        if value:
            ref[key] = value
    for key in (
        "publish_grade_visual_candidate",
        "source_video_has_video_stream",
        "original_path_redacted",
        "screen_recording_consent_required",
        "screen_recording_consent",
    ):
        value = asset.get(key)
        if isinstance(value, bool):
            ref[key] = value
    for key in ("source_video_duration_sec", "evidence_clip_duration_sec"):
        duration_sec = _positive_duration_sec(asset.get(key))
        if duration_sec is not None:
            ref[key] = duration_sec
    return ref


def _target_scene_matches(asset: dict[str, Any], scene_id: str | None) -> bool:
    target_scene_id = str(asset.get("target_scene_id") or "").strip()
    current_scene_id = str(scene_id or "").strip()
    return not target_scene_id or not current_scene_id or target_scene_id == current_scene_id


def _publish_grade_recording_targets_scene(
    asset: dict[str, Any], scene_id: str | None
) -> bool:
    if not _is_publish_grade_evidence_video(asset):
        return True
    current_scene_id = str(scene_id or "").strip()
    if not current_scene_id:
        return True
    return str(asset.get("target_scene_id") or "").strip() == current_scene_id


def _prioritize_publish_grade_evidence_assets(
    selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    priority = [
        asset
        for asset in selected
        if _is_publish_grade_evidence_video(asset)
    ]
    return _dedupe_asset_objects([*priority, *selected])


def _evidence_recovery_fields(item: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in (
        "next_action_zh",
        "next_command",
        "manual_fallback_command",
        "manual_fallback_note_zh",
        "privacy_notice_zh",
    ):
        value = str(item.get(key) or "").strip()
        if value:
            fields[key] = value
    for key in ("screen_recording_consent_required", "screen_recording_consent"):
        value = item.get(key)
        if isinstance(value, bool):
            fields[key] = value
    return fields


def _collect_input_assets(project: ProjectRef, assets: list[dict[str, Any]]) -> None:
    path = project.path / "assets" / "input_assets.json"
    if not path.exists():
        return
    try:
        input_assets = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(input_assets, list):
        return
    for index, item in enumerate(input_assets, start=1):
        if not isinstance(item, dict):
            continue
        source_uri = str(item.get("source_uri") or "")
        input_type = str(item.get("type") or "")
        role = str(item.get("role") or "")
        screenshot_requested = bool(item.get("screenshot_opt_in"))
        screenshot_path = str(item.get("screenshot_path") or "")
        recording_requested = bool(item.get("recording_opt_in"))
        recording_path = str(item.get("recording_path") or "")
        recording_evidence_type = str(item.get("recording_evidence_type") or "")
        recording_role = str(item.get("recording_role") or "")
        target_scene_id = str(item.get("target_scene_id") or "").strip()
        evidence_type = _input_evidence_type(input_type, source_uri, role)
        recovery_fields = _evidence_recovery_fields(item)
        asset = {
            "id": f"input-{index:02d}",
            "evidence_type": evidence_type,
            "source_uri": source_uri,
            "path": _relative_if_inside(project, Path(source_uri)) if source_uri else "",
            "role": role,
            "screenshot_requested": screenshot_requested,
            "recording_requested": recording_requested,
            "origin": "ingest",
            "publish_grade_visual": False,
            "publish_grade_visual_candidate": False,
            "target_scene_id": target_scene_id,
            "note_zh": "用户输入/公开来源证据,可用于画面生成参考和审计,不是动态视频资产。",
            **recovery_fields,
        }
        task_redacted = str(item.get("task_redacted") or "").strip()
        recording_task_redacted = str(
            item.get("recording_task_redacted") or task_redacted
        ).strip()
        if input_type == "video":
            duration_sec = _positive_duration_sec(item.get("source_video_duration_sec"))
            recording_status = str(item.get("recording_status") or "").strip()
            if not recording_status:
                recording_status = (
                    "captured"
                    if bool(item.get("source_video_has_video_stream"))
                    else "not_verifiable"
                )
            asset.update(
                {
                    "recording_status": recording_status,
                    "source_video_probe_status": str(
                        item.get("source_video_probe_status") or ""
                    ),
                    "source_video_has_video_stream": bool(
                        item.get("source_video_has_video_stream")
                    ),
                    "source_video_probe_hint_zh": str(
                        item.get("source_video_probe_hint_zh") or ""
                    ),
                    "source_video_probe_tool": str(
                        item.get("source_video_probe_tool") or ""
                    ),
                    "source_video_probe_error": str(
                        item.get("source_video_probe_error") or ""
                    ),
                    "publish_grade_visual_candidate": bool(
                        item.get("source_video_has_video_stream")
                    ),
                }
            )
            if duration_sec is not None:
                asset["source_video_duration_sec"] = duration_sec
                asset["evidence_clip_duration_sec"] = duration_sec
            if task_redacted:
                asset["task_redacted"] = task_redacted
            if recording_task_redacted:
                asset["recording_task_redacted"] = recording_task_redacted
        if input_type == "image":
            asset.update(
                {
                    "publish_grade_visual_candidate": False,
                    "asset_kind": str(item.get("asset_kind") or "static_image_reference"),
                    "copied_into_project": bool(item.get("copied_into_project")),
                    "original_path_redacted": bool(item.get("original_path_redacted")),
                    "next_action_zh": str(item.get("next_action_zh") or ""),
                    "evidence_capture_note_zh": (
                        "该图片只能作为参考图、封面、贴图或图生视频 source;"
                        "不能直接满足发布级动态视频镜头。"
                    ),
                }
            )
        if input_type == "terminal_command":
            asset.update(
                {
                    "command_redacted": str(item.get("command_redacted") or ""),
                    "command_status": str(item.get("command_status") or ""),
                    "command_exit_code": item.get("command_exit_code"),
                    "working_directory_redacted": bool(
                        item.get("working_directory_redacted")
                    ),
                    "evidence_capture_note_zh": (
                        "该证据来自用户授权命令输出的终端文本回放,不是屏幕录制。"
                    ),
                }
            )
        if input_type == "codex_operation":
            asset.update(
                {
                    "task_redacted": task_redacted,
                    "evidence_capture_note_zh": (
                        "该证据来自 Codex 操作录屏任务记录;只有绑定 captured 视频后,"
                        "才可作为发布级动态证据候选。"
                    ),
                }
            )
        assets.append(asset)
        if _project_file_exists(project, screenshot_path):
            assets.append(
                {
                    "id": f"input-{index:02d}-screenshot",
                    "evidence_type": "screenshot_capture",
                    "source_uri": source_uri,
                    "path": _relative_if_inside(project, project.path / screenshot_path),
                    "role": "screenshot",
                    "screenshot_status": "captured",
                    "origin": "ingest",
                    "publish_grade_visual": False,
                    "publish_grade_visual_candidate": False,
                    "target_scene_id": target_scene_id,
                    "asset_kind": "static_image_reference",
                    "next_action_zh": (
                        "截图只能作为画面参考或证据线索;"
                        "发布级镜头仍需要动态视频素材或真实视频生成器输出。"
                    ),
                    "note_zh": "URL 真实截图证据,可用于画面生成参考和审计,不是动态视频资产。",
                }
            )
        recording_file = _project_file_path(project, recording_path)
        if recording_file:
            captured_type = recording_evidence_type or "web_recording_capture"
            captured_role = recording_role or "web_recording"
            ffprobe = shutil.which("ffprobe")
            has_video_stream = _source_video_is_verifiable(ffprobe, recording_file)
            duration_sec = (
                _source_video_duration_sec(ffprobe, recording_file)
                if has_video_stream
                else None
            )
            probe_status = (
                "verifiable"
                if has_video_stream
                else ("ffprobe_unavailable" if not ffprobe else "not_verifiable")
            )
            assets.append(
                {
                    "id": f"input-{index:02d}-recording",
                    "evidence_type": captured_type,
                    "source_uri": source_uri,
                    "path": _relative_if_inside(project, recording_file),
                    "role": captured_role,
                    "recording_status": "captured" if has_video_stream else "not_verifiable",
                    "origin": "ingest",
                    "publish_grade_visual": False,
                    "publish_grade_visual_candidate": has_video_stream,
                    "target_scene_id": target_scene_id,
                    "source_video_probe_status": probe_status,
                    "source_video_has_video_stream": has_video_stream,
                    "source_video_probe_tool": "ffprobe" if ffprobe else "",
                    "source_video_probe_hint_zh": (
                        "ffprobe 已确认该录屏包含视频流,可作为发布级动态证据候选。"
                        if has_video_stream
                        else (
                            "录屏文件已落盘,但 ffprobe 未确认有效视频流;"
                            "不能作为发布级动态证据候选。"
                        )
                    ),
                    **(
                        {
                            "source_video_duration_sec": duration_sec,
                            "evidence_clip_duration_sec": duration_sec,
                        }
                        if duration_sec is not None
                        else {}
                    ),
                    **recovery_fields,
                    **(
                        {"recording_task_redacted": recording_task_redacted}
                        if recording_task_redacted
                        else {}
                    ),
                    "note_zh": _recording_note_zh(captured_type),
                }
            )


def _collect_known_artifacts(project: ProjectRef, assets: list[dict[str, Any]]) -> None:
    known = [
        ("script_artifact", project.path / "artifacts" / "script.json"),
        ("voice_plan_artifact", project.path / "artifacts" / "voice_plan.json"),
        ("visual_plan_artifact", project.path / "artifacts" / "visual_plan.json"),
        ("qa_report_artifact", project.path / "artifacts" / "qa_report.json"),
    ]
    logs_root = project.path / "logs"
    if logs_root.exists():
        for log_path in sorted(logs_root.glob("*.log")):
            known.append(("terminal_log_capture", log_path))
    for mode in ("preview", "release"):
        render_root = project.path / "renders" / mode
        if render_root.exists():
            for manifest in sorted(render_root.glob("*/render_manifest.json")):
                known.append(("render_manifest_capture", manifest))
    export_root = project.path / "exports"
    if export_root.exists():
        for manifest in sorted(export_root.glob("**/export_manifest.json")):
            known.append(("export_package_capture", manifest))
    for evidence_type, path in known:
        if not path.exists():
            continue
        assets.append(
            {
                "id": evidence_type,
                "evidence_type": evidence_type,
                "path": _relative_if_inside(project, path),
                "source_uri": "",
                "origin": "artifact",
                "publish_grade_visual": False,
                "note_zh": "灵剪流程真实落盘证据,用于画面生成参考和 QA 审计。",
            }
        )


def _dedupe_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen = set()
    for asset in assets:
        key = (
            str(asset.get("evidence_type") or ""),
            str(asset.get("path") or ""),
            str(asset.get("source_uri") or ""),
            str(asset.get("target_scene_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(asset)
    return deduped


def _dedupe_asset_objects(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen = set()
    for asset in assets:
        key = (
            str(asset.get("id") or ""),
            str(asset.get("evidence_type") or ""),
            str(asset.get("path") or ""),
            str(asset.get("source_uri") or ""),
            str(asset.get("target_scene_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(asset)
    return deduped


def _is_publish_grade_evidence_video(asset: dict[str, Any]) -> bool:
    evidence_type = str(asset.get("evidence_type") or "")
    if evidence_type not in SOURCE_VIDEO_EVIDENCE_TYPES:
        return False
    if bool(asset.get("publish_grade_evidence_video")):
        return True
    return (
        str(asset.get("evidence_clip_status") or "") == "captured"
        and bool(asset.get("materialized_evidence_video"))
    )


def _input_evidence_type(input_type: str, source_uri: str, role: str = "") -> str:
    lowered = source_uri.lower()
    role_lowered = role.lower()
    if input_type == "url" and "github.com" in lowered:
        return "github_repo"
    if input_type == "url":
        return "web_source"
    source_name = Path(source_uri).name.lower()
    if input_type == "codex_operation":
        return "codex_operation_plan"
    if input_type == "terminal_command":
        return "terminal_log_capture"
    if input_type == "text" and source_name.endswith(".log"):
        return "terminal_log_capture"
    if input_type == "text" and "readme" in source_name:
        return "readme_install_entry"
    if input_type == "text":
        return "source_text"
    if input_type == "image" and role_lowered in {"screenshot", "screen", "capture"}:
        return "screenshot_capture"
    if input_type == "image":
        return "reference_image"
    if input_type == "video" and role_lowered in {
        "terminal",
        "terminal_recording",
        "terminal_capture",
    }:
        return "terminal_recording_capture"
    if input_type == "video" and role_lowered in {"codex", "codex_operation", "codex_recording"}:
        return "codex_operation_recording"
    if input_type == "video":
        return "screen_recording_capture"
    return "user_input"


def _recording_note_zh(evidence_type: str) -> str:
    if evidence_type == "terminal_recording_capture":
        return (
            "终端真实动态录屏证据,可作为发布级画面候选;"
            "最终仍需通过视频流、字幕、构图、内容质量和人工观感 QA。"
        )
    if evidence_type == "codex_operation_recording":
        return (
            "Codex 操作真实动态录屏证据,可作为发布级画面候选;"
            "最终仍需通过视频流、字幕、构图、内容质量和人工观感 QA。"
        )
    if evidence_type == "screen_recording_capture":
        return (
            "屏幕真实动态录屏证据,可作为发布级画面候选;"
            "最终仍需通过视频流、字幕、构图、内容质量和人工观感 QA。"
        )
    return (
        "URL 真实动态录屏证据,可作为发布级画面候选;"
        "最终仍需通过视频流、字幕、构图和内容质量 QA。"
    )


def _preferred_evidence_types(expected: str) -> set[str]:
    preferred: set[str] = set()
    lowered = expected.lower()
    for recipe_id, evidence_types in ASSET_RECIPE_EVIDENCE_TYPES.items():
        if recipe_id in lowered:
            preferred.update(evidence_types)
    if preferred:
        return preferred
    if "github" in lowered:
        preferred.add("github_repo")
        preferred.add("web_recording_capture")
        preferred.add("screenshot_capture")
        preferred.add("screen_recording_capture")
    if "web" in lowered or "网页" in expected or "codex" in lowered:
        preferred.add("web_recording_capture")
        preferred.add("screenshot_capture")
    if "readme" in lowered:
        preferred.add("readme_install_entry")
        preferred.add("web_recording_capture")
        preferred.add("screen_recording_capture")
    if "terminal" in lowered or "终端" in expected:
        preferred.add("terminal_log_capture")
        preferred.add("terminal_recording_capture")
        preferred.add("screen_recording_capture")
        preferred.add("qa_report_artifact")
        preferred.add("render_manifest_capture")
    if "codex" in lowered:
        preferred.add("codex_operation_recording")
        preferred.add("screen_recording_capture")
    if "qa" in lowered:
        preferred.add("qa_report_artifact")
        preferred.add("terminal_recording_capture")
        preferred.add("screen_recording_capture")
    if "export" in lowered or "导出" in expected:
        preferred.add("export_package_capture")
    if "render_manifest" in lowered:
        preferred.add("render_manifest_capture")
        preferred.add("terminal_recording_capture")
        preferred.add("screen_recording_capture")
    return preferred


def _evidence_clip_text(
    project: ProjectRef,
    asset: dict[str, Any],
    style: dict[str, str],
) -> str:
    evidence_type = str(asset.get("evidence_type") or "evidence")
    title = _label_for_evidence_type(evidence_type)
    source = str(asset.get("source_uri") or asset.get("path") or "")
    lines = [
        f"{style['heading_zh']} | {title}",
        f"镜头策略: {style['role_zh']}",
        f"来源: {source or evidence_type}",
    ]
    snippet = _asset_snippet(project, asset)
    if snippet:
        lines.extend(snippet)
    return "\n".join(lines[:8])


def _evidence_text_for_asset(
    project: ProjectRef,
    asset: dict[str, Any],
    style: dict[str, str],
    terminal_log_path: Path | None,
) -> str:
    if terminal_log_path:
        return _terminal_replay_text(project, asset, style, terminal_log_path)
    return _evidence_clip_text(project, asset, style)


def _terminal_replay_text(
    project: ProjectRef,
    asset: dict[str, Any],
    style: dict[str, str],
    terminal_log_path: Path,
) -> str:
    evidence_type = str(asset.get("evidence_type") or "")
    header = [
        f"{style['heading_zh']} | {_label_for_evidence_type(evidence_type)}",
        f"来源: {_relative_if_inside(project, terminal_log_path)}",
    ]
    try:
        text = terminal_log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        text = ""
    body = []
    for raw_line in text.splitlines():
        line = _redact_sensitive_text(" ".join(raw_line.split()))
        if line:
            body.append(line[:72])
        if len(body) >= 8:
            break
    return "\n".join(header + body)


def _asset_snippet(project: ProjectRef, asset: dict[str, Any]) -> list[str]:
    raw_path = str(asset.get("path") or "")
    if not raw_path:
        return []
    path = project.path / raw_path
    try:
        resolved = path.resolve()
    except OSError:
        return []
    try:
        resolved.relative_to(project.path.resolve())
    except (OSError, ValueError):
        return []
    if not resolved.exists() or not resolved.is_file() or resolved.stat().st_size > 120_000:
        return []
    if resolved.suffix.lower() not in {".json", ".md", ".txt", ".log"}:
        return []
    try:
        text = resolved.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    compact = [_redact_sensitive_text(" ".join(line.split())) for line in text.splitlines()]
    return [line[:42] for line in compact if line][:5]


def _evidence_clip_filter(text_path: Path, style: dict[str, str]) -> str:
    font = _font_path()
    font_part = f"fontfile='{_escape_drawtext(font)}':" if font else ""
    textfile = _escape_drawtext(str(text_path))
    panel = style["panel_color"]
    accent = style["accent_color"]
    marker = style["marker_color"]
    return (
        f"drawbox=x=54:y=120:w=972:h=1360:color={panel}@0.84:t=fill,"
        f"drawbox=x=54:y=120:w=972:h=10:color={accent}@0.95:t=fill,"
        f"drawbox=x='54+t*180':y=120:w=180:h=10:color={marker}@0.95:t=fill,"
        "drawtext="
        f"{font_part}"
        f"textfile='{textfile}':"
        "fontcolor=white:fontsize=44:line_spacing=20:"
        "x=96:y='1380-t*170':"
        "box=1:boxcolor=0x020617@0.45:boxborderw=24"
    )


def _source_image_evidence_filter(text_path: Path, style: dict[str, str]) -> str:
    font = _font_path()
    font_part = f"fontfile='{_escape_drawtext(font)}':" if font else ""
    textfile = _escape_drawtext(str(text_path))
    accent = style["accent_color"]
    return (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "eq=contrast=1.05:saturation=0.95,"
        "drawbox=x=0:y=0:w=1080:h=1920:color=0x020617@0.18:t=fill,"
        f"drawbox=x=60:y=84:w='min(860,220+t*210)':h=8:color={accent}@0.96:t=fill,"
        "drawbox=x=54:y=1374:w=972:h=360:color=0x020617@0.74:t=fill,"
        "drawtext="
        f"{font_part}"
        f"textfile='{textfile}':"
        "fontcolor=white:fontsize=40:line_spacing=16:"
        "x=92:y=1416:"
        "box=1:boxcolor=0x020617@0.26:boxborderw=18"
    )


def _terminal_replay_filter(text_path: Path, style: dict[str, str]) -> str:
    font = _font_path()
    font_part = f"fontfile='{_escape_drawtext(font)}':" if font else ""
    textfile = _escape_drawtext(str(text_path))
    accent = style["accent_color"]
    marker = style["marker_color"]
    return (
        "drawbox=x=54:y=120:w=972:h=1320:color=0x020617@0.94:t=fill,"
        "drawbox=x=54:y=120:w=972:h=72:color=0x111827@0.98:t=fill,"
        "drawbox=x=88:y=148:w=18:h=18:color=0xef4444@0.95:t=fill,"
        "drawbox=x=120:y=148:w=18:h=18:color=0xfacc15@0.95:t=fill,"
        "drawbox=x=152:y=148:w=18:h=18:color=0x22c55e@0.95:t=fill,"
        f"drawbox=x=54:y='190+t*210':w=972:h=3:color={accent}@0.62:t=fill,"
        f"drawbox=x=80:y='260+t*160':w='min(880,180+t*240)':h=4:color={marker}@0.75:t=fill,"
        "drawtext="
        f"{font_part}"
        f"textfile='{textfile}':"
        "fontcolor=0xdbeafe:fontsize=38:line_spacing=18:"
        "x=88:y='310-t*120':"
        "box=1:boxcolor=0x020617@0.20:boxborderw=16"
    )


def _text_evidence_command(
    ffmpeg: str,
    text_path: Path,
    style: dict[str, str],
    clip_path: Path,
) -> list[str]:
    return [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x0b1020:s=1080x1920:d={EVIDENCE_CLIP_DURATION_SEC:.2f}",
        "-t",
        f"{EVIDENCE_CLIP_DURATION_SEC:.2f}",
        "-vf",
        _evidence_clip_filter(text_path, style),
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(clip_path),
    ]


def _terminal_evidence_command(
    ffmpeg: str,
    text_path: Path,
    style: dict[str, str],
    clip_path: Path,
) -> list[str]:
    return [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x020617:s=1080x1920:d={EVIDENCE_CLIP_DURATION_SEC:.2f}",
        "-t",
        f"{EVIDENCE_CLIP_DURATION_SEC:.2f}",
        "-vf",
        _terminal_replay_filter(text_path, style),
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(clip_path),
    ]


def _source_image_evidence_command(
    ffmpeg: str,
    source_image_path: Path,
    text_path: Path,
    style: dict[str, str],
    clip_path: Path,
) -> list[str]:
    return [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-i",
        str(source_image_path),
        "-t",
        f"{EVIDENCE_CLIP_DURATION_SEC:.2f}",
        "-vf",
        _source_image_evidence_filter(text_path, style),
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(clip_path),
    ]


def _evidence_clip_style(asset: dict[str, Any]) -> dict[str, str]:
    evidence_type = str(asset.get("evidence_type") or "")
    styles = {
        "github_repo": {
            "id": "github_repo_card",
            "heading_zh": "GitHub 开源入口镜头",
            "role_zh": "展示仓库来源、项目名和 Star 行动证据",
            "panel_color": "0x0b1220",
            "accent_color": "0x38bdf8",
            "marker_color": "0xfacc15",
        },
        "readme_install_entry": {
            "id": "readme_install_scroll",
            "heading_zh": "README 首用路径镜头",
            "role_zh": "展示安装入口、使用步骤和用户上手证据",
            "panel_color": "0x101827",
            "accent_color": "0x22c55e",
            "marker_color": "0xa7f3d0",
        },
        "web_source": {
            "id": "web_source_capture",
            "heading_zh": "网页来源证据镜头",
            "role_zh": "展示公开页面、链接来源和内容依据",
            "panel_color": "0x111827",
            "accent_color": "0x60a5fa",
            "marker_color": "0xfacc15",
        },
        "screenshot_capture": {
            "id": "screenshot_capture_scan",
            "heading_zh": "截图证据镜头",
            "role_zh": "展示用户提供/采集的界面截图证据,作为真实画面依据",
            "panel_color": "0x111827",
            "accent_color": "0xf472b6",
            "marker_color": "0x38bdf8",
        },
        "web_recording_capture": {
            "id": "web_recording_capture",
            "heading_zh": "网页动态录屏镜头",
            "role_zh": "展示真实网页/界面操作录屏证据,优先作为开源项目介绍的动态证据画面",
            "panel_color": "0x0f172a",
            "accent_color": "0x22c55e",
            "marker_color": "0x38bdf8",
        },
        "terminal_log_capture": {
            "id": "terminal_log_replay",
            "heading_zh": "终端回放证据镜头",
            "role_zh": "展示真实日志/命令输出证据,用于支撑操作链路",
            "panel_color": "0x020617",
            "accent_color": "0x38bdf8",
            "marker_color": "0x22c55e",
        },
        "terminal_recording_capture": {
            "id": "terminal_recording_capture",
            "heading_zh": "终端真实录屏镜头",
            "role_zh": "展示真实终端操作录屏,用于证明命令链路与结果",
            "panel_color": "0x020617",
            "accent_color": "0x22c55e",
            "marker_color": "0x38bdf8",
        },
        "codex_operation_recording": {
            "id": "codex_operation_recording",
            "heading_zh": "Codex 操作录屏镜头",
            "role_zh": "展示 Codex app 对话触发、审批和执行过程",
            "panel_color": "0x111827",
            "accent_color": "0xa78bfa",
            "marker_color": "0xf472b6",
        },
        "screen_recording_capture": {
            "id": "screen_recording_capture",
            "heading_zh": "屏幕录屏证据镜头",
            "role_zh": "展示用户提供的真实屏幕动态素材",
            "panel_color": "0x0f172a",
            "accent_color": "0x60a5fa",
            "marker_color": "0xfacc15",
        },
        "qa_report_artifact": {
            "id": "qa_status_panel",
            "heading_zh": "QA 严格门体检镜头",
            "role_zh": "展示 strict QA、ffprobe 和发布级门禁证据",
            "panel_color": "0x1f1023",
            "accent_color": "0xf97316",
            "marker_color": "0xfde68a",
        },
        "render_manifest_capture": {
            "id": "render_manifest_timeline",
            "heading_zh": "Render Manifest 时间线镜头",
            "role_zh": "展示渲染产物、字幕、转场和音轨证据",
            "panel_color": "0x0f172a",
            "accent_color": "0x818cf8",
            "marker_color": "0x38bdf8",
        },
        "export_package_capture": {
            "id": "export_package_card",
            "heading_zh": "导出包结构镜头",
            "role_zh": "展示发布包、manifest 和无泄漏证据",
            "panel_color": "0x172016",
            "accent_color": "0x84cc16",
            "marker_color": "0xfacc15",
        },
        "script_artifact": {
            "id": "script_review_card",
            "heading_zh": "脚本三审镜头",
            "role_zh": "展示脚本分镜、叙事弧和用户确认证据",
            "panel_color": "0x111827",
            "accent_color": "0x38bdf8",
            "marker_color": "0xf472b6",
        },
        "voice_plan_artifact": {
            "id": "voice_director_card",
            "heading_zh": "配音导演镜头",
            "role_zh": "展示音色、语气、时长和配音确认证据",
            "panel_color": "0x1b1630",
            "accent_color": "0xa78bfa",
            "marker_color": "0xf9a8d4",
        },
        "visual_plan_artifact": {
            "id": "visual_storyboard_card",
            "heading_zh": "画面分镜镜头",
            "role_zh": "展示导演分镜、素材策略和画面验收证据",
            "panel_color": "0x082f49",
            "accent_color": "0x06b6d4",
            "marker_color": "0xfacc15",
        },
    }
    return styles.get(
        evidence_type,
        {
            "id": "generic_evidence_card",
            "heading_zh": "灵剪证据镜头",
            "role_zh": "展示本地证据来源和可审计素材",
            "panel_color": "0x111827",
            "accent_color": "0x38bdf8",
            "marker_color": "0xfacc15",
        },
    )


def _font_path() -> str | None:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        str(Path.home() / ".cache/lingjian/fonts/NotoSansSC-Regular.otf"),
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _escape_drawtext(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace(",", "\\,")
    )


def _safe_clip_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return normalized or "evidence"


def _label_for_evidence_type(evidence_type: str) -> str:
    labels = {
        "github_repo": "GitHub 仓库",
        "web_source": "网页来源",
        "screenshot_capture": "截图证据",
        "web_recording_capture": "网页动态录屏",
        "terminal_recording_capture": "终端真实录屏",
        "codex_operation_recording": "Codex 操作录屏",
        "codex_operation_plan": "Codex 操作录屏任务",
        "screen_recording_capture": "屏幕录屏",
        "reference_image": "参考图片",
        "terminal_log_capture": "终端日志",
        "readme_install_entry": "README 安装入口",
        "qa_report_artifact": "QA 报告",
        "render_manifest_capture": "Render Manifest",
        "export_package_capture": "导出包",
        "script_artifact": "脚本产物",
        "voice_plan_artifact": "配音计划",
        "visual_plan_artifact": "画面计划",
    }
    return labels.get(evidence_type, evidence_type)


def _evidence_clip_render_source(
    source_image_path: Path | None,
    terminal_log_path: Path | None,
) -> str:
    if source_image_path:
        return "dynamic_screenshot_scan"
    if terminal_log_path:
        return "dynamic_terminal_replay"
    return "dynamic_ffmpeg_drawtext"


def _evidence_visual_source(
    source_image_path: Path | None,
    terminal_log_path: Path | None,
) -> str:
    if source_image_path:
        return "source_image"
    if terminal_log_path:
        return "terminal_transcript"
    return "text_card"


def _asset_source_image_path(project: ProjectRef, asset: dict[str, Any]) -> Path | None:
    for raw in (str(asset.get("path") or ""), str(asset.get("source_uri") or "")):
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = project.path / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(project.path.resolve())
        except (OSError, ValueError):
            continue
        if (
            resolved.exists()
            and resolved.is_file()
            and resolved.suffix.lower() in SOURCE_IMAGE_EXTENSIONS
        ):
            return resolved
    return None


def _asset_source_video_path(project: ProjectRef, asset: dict[str, Any]) -> Path | None:
    evidence_type = str(asset.get("evidence_type") or "")
    if evidence_type not in SOURCE_VIDEO_EVIDENCE_TYPES:
        return None
    raw = str(asset.get("path") or "")
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = project.path / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(project.path.resolve())
    except (OSError, ValueError):
        return None
    if (
        resolved.exists()
        and resolved.is_file()
        and resolved.suffix.lower() in SOURCE_VIDEO_EXTENSIONS
    ):
        return resolved
    return None


def _source_video_visual_source(asset: dict[str, Any]) -> str:
    evidence_type = str(asset.get("evidence_type") or "")
    return {
        "web_recording_capture": "web_recording_video",
        "terminal_recording_capture": "terminal_recording_video",
        "codex_operation_recording": "codex_operation_video",
        "screen_recording_capture": "screen_recording_video",
    }.get(evidence_type, "source_video")


def _source_video_is_verifiable(ffprobe: str | None, path: Path) -> bool:
    if not ffprobe:
        return False
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "json",
                str(path),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return any(
        isinstance(stream, dict) and stream.get("codec_type") == "video"
        for stream in payload.get("streams", [])
    )


def _source_video_duration_sec(ffprobe: str | None, path: Path) -> float | None:
    if not ffprobe:
        return None
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout or "{}")
        duration = float((payload.get("format") or {}).get("duration"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if duration <= 0:
        return None
    return round(duration, 3)


def _positive_duration_sec(value: object) -> float | None:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    if duration <= 0:
        return None
    return round(duration, 3)


def _asset_terminal_log_path(project: ProjectRef, asset: dict[str, Any]) -> Path | None:
    evidence_type = str(asset.get("evidence_type") or "")
    if evidence_type != "terminal_log_capture":
        return None
    for raw in (str(asset.get("path") or ""), str(asset.get("source_uri") or "")):
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = project.path / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(project.path.resolve())
        except (OSError, ValueError):
            continue
        if (
            resolved.exists()
            and resolved.is_file()
            and resolved.suffix.lower() in TERMINAL_TEXT_EXTENSIONS
        ):
            return resolved
    return None


def _project_file_exists(project: ProjectRef, raw_path: str) -> bool:
    return _project_file_path(project, raw_path) is not None


def _project_file_path(project: ProjectRef, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = project.path / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(project.path.resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.exists() and resolved.is_file() else None


def _redact_sensitive_text(value: str) -> str:
    redacted = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)\S+", r"\1***", value)
    redacted = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|token|secret)(\s*[:=]\s*)\S+",
        r"\1\2***",
        redacted,
    )
    redacted = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1***", redacted)
    return redacted


def _stderr_tail(stderr: str) -> str:
    lines = [line for line in (stderr or "").splitlines() if line.strip()]
    return "\n".join(lines[-4:])[:400]


def _relative_if_inside(project: ProjectRef, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project.path.resolve()))
    except (OSError, ValueError):
        return str(path)
