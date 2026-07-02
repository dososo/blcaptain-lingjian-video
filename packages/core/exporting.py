from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from packages.core.artifacts import read_json
from packages.core.errors import LingjianError
from packages.core.paths import resolve_inside, safe_segment
from packages.core.project import ProjectRef
from packages.core.qa import run_qa
from packages.core.rendering import latest_render_manifest

PLATFORM_EXTRA_FILES = {
    "youtube": {
        "thumbnail.png": "stub thumbnail\n",
        "description.md": "# YouTube Description\n",
        "chapters.md": "00:00 开场\n",
    },
}


@dataclass(slots=True)
class ExportPackageResult:
    export_dir: Path
    export_manifest: dict


def _ratio_dir(ratio: str) -> str:
    return safe_segment(ratio, "ratio").replace(":", "x")


def _approvals(project: ProjectRef) -> list[dict]:
    path = project.path / "artifacts" / "approvals.json"
    if not path.exists():
        return []
    return list(read_json(path).values())


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _export_root(project: ProjectRef) -> Path:
    if project.path.parent.name == "projects":
        return project.path.parent.parent / "exports"
    return project.path.parent / "exports"


def _latest_any_render_manifest(project: ProjectRef, mode: str) -> dict | None:
    render_root = project.path / "renders" / mode
    if not render_root.exists():
        return None
    for manifest_path in sorted(render_root.glob("*/render_manifest.json")):
        return read_json(manifest_path)
    return None


def _license_manifest_text(source_manifest: dict) -> str:
    lines = ["# License Manifest", "", "- renderer: ffmpeg_card"]
    inherited_llm_ids = {"claude_cli", "codex_cli", "ollama_cli", "llm_local_cli"}
    local_tts_ids = {"kokoro_zh_tts", "macos_say", "piper_cli", "espeak_ng"}
    for provider in source_manifest.get("providers", []):
        provider_id = provider.get("id")
        if provider_id in {"llm_cli", "tts_cli"}:
            lines.append(f"- {provider_id}: User supplied CLI provider")
        if provider_id in inherited_llm_ids:
            lines.append(f"- {provider_id}: Inherited CLI provider")
        if provider_id in local_tts_ids:
            lines.append(f"- {provider_id}: Local TTS provider")
        if provider_id in {"openai_compatible", "openai_compatible_tts"}:
            lines.append(f"- {provider_id}: OpenAI-compatible API provider")
        if provider_id == "volcengine_tts":
            lines.append("- volcengine_tts: Volcengine Doubao TTS API provider")
        if provider_id == "user_audio":
            lines.append("- user_audio: User supplied recorded narration")
    return "\n".join(lines) + "\n"


def export_project(
    project: ProjectRef,
    platform: str,
    language: str,
    ratio: str,
    release: bool = False,
    allow_preview_source: bool = False,
    strict: bool = False,
) -> ExportPackageResult:
    platform = safe_segment(platform, "platform")
    language = safe_segment(language, "language")
    preview_manifest = latest_render_manifest(project, platform, "preview")
    release_manifest = latest_render_manifest(project, platform, "release")
    fallback_preview_manifest = preview_manifest or _latest_any_render_manifest(project, "preview")
    fallback_release_manifest = release_manifest or _latest_any_render_manifest(project, "release")

    if release and allow_preview_source and fallback_preview_manifest is not None:
        raise LingjianError(
            "PREVIEW_ARTIFACT_NOT_RELEASABLE",
            "preview 渲染产物不能用于正式发布。",
            "请使用真实 provider 重新生成 release render。",
        )

    source_manifest = (
        fallback_release_manifest
        if release
        else fallback_preview_manifest or fallback_release_manifest
    )
    if release and source_manifest is None and fallback_preview_manifest is not None:
        if any(
            provider.get("is_mock") for provider in fallback_preview_manifest.get("providers", [])
        ):
            raise LingjianError(
                "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE",
                "mock provider 不能用于正式发布。",
                "请配置真实 LLM/TTS provider 后重试。",
            )
        raise LingjianError(
            "PREVIEW_ARTIFACT_NOT_RELEASABLE",
            "preview 渲染产物不能用于正式发布。",
            "请使用 release render 后重试。",
        )
    if source_manifest is None:
        raise LingjianError("RENDER_FAILED", "缺少可导出的渲染产物。", "请先运行 render/preview。")

    if release and any(
        provider.get("is_mock") for provider in source_manifest.get("providers", [])
    ):
        raise LingjianError(
            "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE",
            "mock provider 不能用于正式发布。",
            "请配置真实 LLM/TTS provider 后重试。",
        )

    qa_report = run_qa(project, release=release, platform=platform, strict=strict)
    if release and not qa_report.release_ready:
        raise LingjianError("QA_BLOCKING", "QA hard fail 阻止 release。", "请修复 QA 问题后重试。")

    export_dir = _export_root(project) / project.path.name / platform / language / _ratio_dir(ratio)
    export_dir.mkdir(parents=True, exist_ok=True)
    source_video = resolve_inside(project.path, project.path / source_manifest["video_path"])
    shutil.copy2(source_video, export_dir / "video.mp4")

    _write_text(
        export_dir / "captions" / "subtitles.srt",
        "1\n00:00:00,000 --> 00:00:01,000\n灵剪\n",
    )
    _write_text(
        export_dir / "captions" / "subtitles.vtt",
        "WEBVTT\n\n00:00.000 --> 00:01.000\n灵剪\n",
    )
    _write_text(export_dir / "captions" / "subtitles.ass", "[Script Info]\nTitle: LingJian\n")
    _write_text(export_dir / "source_map.json", "[]\n")
    _write_text(export_dir / "qa_report.md", "# QA Report\n")
    _write_text(
        export_dir / "license_manifest.md",
        _license_manifest_text(source_manifest),
    )
    _write_text(export_dir / "cover.png", "stub cover\n")
    _write_text(export_dir / "metadata" / "publish.md", "# 发布文案\n")
    for relative_path, content in PLATFORM_EXTRA_FILES.get(platform, {}).items():
        _write_text(export_dir / relative_path, content)
    provider_manifest = {
        "release_allowed": not any(
            provider.get("is_mock") for provider in source_manifest["providers"]
        ),
        "providers": source_manifest["providers"],
    }
    _write_text(
        export_dir / "provider_manifest.json",
        json.dumps(provider_manifest, ensure_ascii=False, indent=2),
    )
    qa_json = project.path / "artifacts" / "qa_report.json"
    if qa_json.exists():
        shutil.copy2(qa_json, export_dir / "qa_report.json")

    export_manifest = {
        "project_id": project.path.name,
        "platform": platform,
        "language": language,
        "ratio": ratio,
        "release": release,
        "approvals": _approvals(project),
    }
    _write_text(
        export_dir / "export_manifest.json",
        json.dumps(export_manifest, ensure_ascii=False, indent=2),
    )
    return ExportPackageResult(export_dir=export_dir, export_manifest=export_manifest)
