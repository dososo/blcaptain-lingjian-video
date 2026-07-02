from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from packages.core.paths import resolve_inside
from packages.core.project import ProjectRef
from packages.core.rendering import STUB_VIDEO_BYTES, latest_render_manifest

FFPROBE_TIMEOUT_SEC = 20


def _latest_any_render_manifest(project: ProjectRef, mode: str) -> dict | None:
    render_root = project.path / "renders" / mode
    if not render_root.exists():
        return None
    for manifest_path in sorted(render_root.glob("*/render_manifest.json")):
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return None


@dataclass(slots=True)
class QAIssue:
    code: str
    severity: str
    message_zh: str


@dataclass(slots=True)
class QAReport:
    hard_failures: list[QAIssue] = field(default_factory=list)
    warnings: list[QAIssue] = field(default_factory=list)
    info: list[QAIssue] = field(default_factory=list)

    @property
    def release_ready(self) -> bool:
        return not self.hard_failures


def _media_streams_are_verifiable(path: Path) -> tuple[bool, bool]:
    if not shutil.which("ffprobe"):
        return False, False
    try:
        completed = subprocess.run(
            [
                "ffprobe",
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
            timeout=FFPROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return False, False
    if completed.returncode != 0:
        return False, False
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return False, False
    stream_types = {
        stream.get("codec_type")
        for stream in payload.get("streams", [])
        if isinstance(stream, dict)
    }
    return "video" in stream_types, "audio" in stream_types


def _check_release_video_body(project: ProjectRef, manifest: dict, report: QAReport) -> None:
    video_path = resolve_inside(project.path, project.path / manifest.get("video_path", ""))
    if not video_path.exists():
        report.hard_failures.append(
            QAIssue("RENDER_NOT_VERIFIABLE", "hard", "release 视频文件不存在或不可验证。")
        )
        return
    if video_path.read_bytes() == STUB_VIDEO_BYTES:
        report.hard_failures.append(
            QAIssue("RELEASE_VIDEO_IS_STUB", "hard", "release 视频不能是离线 stub。")
        )
    has_video, has_audio = _media_streams_are_verifiable(video_path)
    if not has_video:
        report.hard_failures.append(
            QAIssue("RENDER_NOT_VERIFIABLE", "hard", "ffprobe 未能确认有效视频流。")
        )
    if not has_audio:
        report.hard_failures.append(
            QAIssue("RELEASE_AUDIO_MISSING", "hard", "ffprobe 未能确认 release 音频流。")
        )


def run_qa(project: ProjectRef, release: bool = False, platform: str = "douyin") -> QAReport:
    report = QAReport()
    release_manifest = latest_render_manifest(
        project, platform, "release"
    ) or _latest_any_render_manifest(project, "release")
    preview_manifest = latest_render_manifest(
        project, platform, "preview"
    ) or _latest_any_render_manifest(project, "preview")
    manifest = release_manifest if release and release_manifest is not None else preview_manifest
    if not release:
        manifest = preview_manifest or release_manifest
    if manifest is None:
        report.hard_failures.append(QAIssue("RENDER_MISSING", "hard", "缺少渲染产物。"))
    elif release and any(provider.get("is_mock") for provider in manifest.get("providers", [])):
        report.hard_failures.append(
            QAIssue("RELEASE_CONTAINS_MOCK", "hard", "release 包不能包含 mock provider。")
        )
    elif release:
        _check_release_video_body(project, manifest, report)
    report.info.append(QAIssue("QA_STUB", "info", "Batch 2 最小 QA 已执行。"))

    artifacts = project.path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "qa_report.json").write_text(
        json.dumps(
            {
                "hard_failures": [asdict(issue) for issue in report.hard_failures],
                "warnings": [asdict(issue) for issue in report.warnings],
                "info": [asdict(issue) for issue in report.info],
                "release_ready": report.release_ready,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (artifacts / "qa_report.md").write_text(
        f"# QA Report\n\nrelease_ready: {str(report.release_ready).lower()}\n",
        encoding="utf-8",
    )
    return report
