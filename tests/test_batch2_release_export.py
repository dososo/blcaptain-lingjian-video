import json
import subprocess
from pathlib import Path

from packages.core.approvals import approve_target
from packages.core.artifacts import write_artifact
from packages.core.errors import LingjianError
from packages.core.exporting import export_project
from packages.core.project import init_project
from packages.core.qa import run_qa
from packages.core.rendering import STUB_VIDEO_BYTES, _release_duration, render_project


def _approved_mock_project(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    write_artifact(
        project,
        "script",
        {"id": "script", "provider_id": "mock", "provider_is_mock": True, "scenes": []},
    )
    write_artifact(
        project,
        "voice",
        {"id": "voice", "provider_id": "mock", "provider_is_mock": True, "segments": []},
    )
    write_artifact(project, "visuals", {"id": "visuals", "engine": "ffmpeg_card", "scenes": []})
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    return project


def test_preview_render_writes_preview_manifest_and_release_export_refuses_preview(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")

    assert render_result.mode == "preview"
    assert render_result.video_path.parts[-3:] == ("preview", "douyin", "video.mp4")

    try:
        export_project(project, "douyin", "zh-CN", "9:16", release=True, allow_preview_source=True)
    except LingjianError as exc:
        assert exc.error_code == "PREVIEW_ARTIFACT_NOT_RELEASABLE"
    else:
        raise AssertionError("expected PREVIEW_ARTIFACT_NOT_RELEASABLE")


def test_release_export_refuses_mock_provider(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_project(project, "douyin", "zh-CN", "9:16", mode="preview")

    try:
        export_project(project, "douyin", "zh-CN", "9:16", release=True)
    except LingjianError as exc:
        assert exc.error_code == "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE"
    else:
        raise AssertionError("expected MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE")


def test_preview_export_writes_canonical_package_with_approval_provenance(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    export_dir = package.export_dir
    assert (export_dir / "video.mp4").exists()
    assert (export_dir / "captions" / "subtitles.srt").exists()
    assert (export_dir / "captions" / "subtitles.vtt").exists()
    assert (export_dir / "captions" / "subtitles.ass").exists()
    assert (export_dir / "provider_manifest.json").exists()
    assert (export_dir / "license_manifest.md").exists()
    assert len(package.export_manifest["approvals"]) == 3


def test_export_license_manifest_records_cli_provider(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["providers"] = [
        {"id": "llm_cli", "kind": "llm", "is_mock": False},
        {"id": "tts_cli", "kind": "tts", "is_mock": False},
        {"id": "ffmpeg_card", "kind": "renderer", "is_mock": False},
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    license_text = (package.export_dir / "license_manifest.md").read_text(encoding="utf-8")
    assert "llm_cli: User supplied CLI provider" in license_text
    assert "tts_cli: User supplied CLI provider" in license_text


def test_export_license_manifest_records_openai_provider_without_secrets(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["providers"] = [
        {"id": "openai_compatible", "kind": "llm", "is_mock": False},
        {"id": "openai_compatible_tts", "kind": "tts", "is_mock": False},
        {"id": "ffmpeg_card", "kind": "renderer", "is_mock": False},
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    license_text = (package.export_dir / "license_manifest.md").read_text(encoding="utf-8")
    assert "openai_compatible: OpenAI-compatible API provider" in license_text
    assert "openai_compatible_tts: OpenAI-compatible API provider" in license_text
    assert "sk-" not in license_text
    assert "OPENAI_API_KEY" not in license_text


def test_export_license_manifest_records_inherited_cli_provider_without_commands(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["providers"] = [
        {"id": "claude_cli", "kind": "llm", "is_mock": False},
        {"id": "macos_say", "kind": "tts", "is_mock": False},
        {"id": "ffmpeg_card", "kind": "renderer", "is_mock": False},
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    license_text = (package.export_dir / "license_manifest.md").read_text(encoding="utf-8")
    assert "claude_cli: Inherited CLI provider" in license_text
    assert "macos_say: Local TTS provider" in license_text
    assert "claude -p" not in license_text
    assert "say -o" not in license_text


def test_youtube_export_writes_platform_extra_files(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_project(project, "youtube", "en-US", "16:9", mode="preview")
    package = export_project(project, "youtube", "en-US", "16:9", release=False)

    export_dir = package.export_dir
    assert (export_dir / "thumbnail.png").exists()
    assert (export_dir / "description.md").exists()
    assert (export_dir / "chapters.md").exists()


def test_qa_marks_mock_release_as_hard_failure(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    report = run_qa(project, release=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_CONTAINS_MOCK" for issue in report.hard_failures)


def test_rejects_unsafe_platform_path_segment(tmp_path):
    project = _approved_mock_project(tmp_path)

    try:
        render_project(project, "../escape", "zh-CN", "9:16", mode="preview")
    except LingjianError as exc:
        assert exc.error_code == "INVALID_PATH_SEGMENT"
    else:
        raise AssertionError("expected INVALID_PATH_SEGMENT")


def test_release_qa_checks_release_manifest_not_preview_manifest(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    write_artifact(
        project,
        "script",
        {"id": "script", "provider_id": "real_llm", "provider_is_mock": False, "scenes": []},
    )
    write_artifact(
        project,
        "voice",
        {"id": "voice", "provider_id": "real_tts", "provider_is_mock": False, "segments": []},
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"real-ish video bytes")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false},
    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: None)

    report = run_qa(project, release=True)

    assert report.release_ready is False
    assert any(issue.code == "RENDER_NOT_VERIFIABLE" for issue in report.hard_failures)


def test_release_render_requires_ffmpeg_before_writing_stub(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "script",
        {"id": "script", "provider_id": "real_llm", "provider_is_mock": False, "scenes": []},
    )
    write_artifact(
        project,
        "voice",
        {"id": "voice", "provider_id": "real_tts", "provider_is_mock": False, "segments": []},
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr("packages.core.rendering.shutil.which", lambda name: None)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release")
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_RENDER_REQUIRES_FFMPEG"
    else:
        raise AssertionError("expected RELEASE_RENDER_REQUIRES_FFMPEG")

    assert not (project.path / "renders" / "release" / "douyin" / "video.mp4").exists()


def test_release_render_uses_ffmpeg_and_writes_non_stub_video(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "真实发布字幕"}],
        },
    )
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.aiff",
                    "duration_sec": 2.0,
                }
            ],
            "total_duration_sec": 2.0,
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"REAL MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    assert result.video_path.read_bytes() == b"REAL MP4"
    assert result.video_path.read_bytes() != STUB_VIDEO_BYTES
    assert commands
    assert commands[0][0] == "ffmpeg"
    assert "真实发布字幕" in " ".join(commands[0])
    assert "-c:a" in commands[0]
    assert "aac" in commands[0]


def test_release_render_consumes_delegated_video_and_image_scene_assets(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    assets_dir = project.path / "assets" / "scenes"
    assets_dir.mkdir(parents=True)
    (assets_dir / "s1.mp4").write_bytes(b"HOST VIDEO")
    (assets_dir / "s2.png").write_bytes(b"HOST IMAGE")
    audio_path = project.path / "artifacts" / "voice_segments" / "voice.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "动态图形"},
                {"id": "s2", "narration_text": "静态图片"},
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 2.0,
                },
                {
                    "scene_id": "s2",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 3.0,
                },
            ],
            "total_duration_sec": 5.0,
        },
    )
    write_artifact(
        project,
        "visuals",
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "动态图形",
                    "duration_sec": 2.0,
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s1.mp4",
                    "subtitle_burn": False,
                },
                {
                    "scene_id": "s2",
                    "narration_text": "静态图片",
                    "duration_sec": 3.0,
                    "generator": "image-gen",
                    "asset_path": "assets/scenes/s2.png",
                    "subtitle_burn": True,
                },
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    command_text = "\n".join(" ".join(command) for command in commands)
    assert "assets/scenes/s1.mp4" in command_text
    assert "assets/scenes/s2.png" in command_text
    assert "zoompan" in command_text
    assert "concat" in command_text
    assert "-c:a" in commands[-1]
    assert manifest["visual_real_count"] == 2
    assert manifest["visual_total"] == 2
    assert [scene["render_source"] for scene in manifest["scenes"]] == ["video", "image"]


def test_release_render_falls_back_to_solid_when_delegated_asset_missing_and_qa_warns(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    audio_path = project.path / "artifacts" / "voice_segments" / "voice.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "缺少宿主产物"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 2.0,
                }
            ],
            "total_duration_sec": 2.0,
        },
    )
    write_artifact(
        project,
        "visuals",
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "缺少宿主产物",
                    "duration_sec": 2.0,
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/missing.mp4",
                    "subtitle_burn": False,
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_render_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_render_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        "packages.core.qa.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
            stderr="",
        ),
    )
    report = run_qa(project, release=True)

    assert manifest["visual_real_count"] == 0
    assert manifest["visual_total"] == 1
    assert manifest["scenes"][0]["render_source"] == "fallback_solid"
    assert report.release_ready is True
    assert any(issue.code == "RELEASE_VISUAL_IS_BLANK_CARD" for issue in report.warnings)


def test_release_render_reports_ffmpeg_filter_error_with_stderr(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "真实发布字幕"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.aiff",
                    "duration_sec": 2.0,
                }
            ],
            "total_duration_sec": 2.0,
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            8,
            stdout="",
            stderr="No such filter: 'drawtext'\n/private/path/should/not/leak\n",
        )

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release")
    except LingjianError as exc:
        assert exc.error_code == "FFMPEG_FILTER_UNAVAILABLE"
        assert "No such filter" in exc.details["ffmpeg_stderr_tail"]
        assert str(project.path) not in exc.details["ffmpeg_stderr_tail"]
    else:
        raise AssertionError("expected FFMPEG_FILTER_UNAVAILABLE")


def test_release_duration_uses_voice_plan_total_duration(tmp_path):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [],
            "total_duration_sec": 7.25,
        },
    )

    assert _release_duration(project) == 7.25


def test_release_duration_falls_back_when_voice_duration_missing(tmp_path):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "mock",
            "provider_is_mock": True,
            "segments": [],
        },
    )

    assert _release_duration(project) == 3.0


def test_preview_real_without_ffmpeg_falls_back_to_stub(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    monkeypatch.setattr("packages.core.rendering.shutil.which", lambda name: None)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview", real_preview=True)

    assert result.video_path.read_bytes() == STUB_VIDEO_BYTES


def test_preview_real_uses_ffmpeg_when_available(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"REAL PREVIEW MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview", real_preview=True)

    assert result.video_path.read_bytes() == b"REAL PREVIEW MP4"
    assert commands


def test_release_qa_rejects_stub_and_unverifiable_video(tmp_path):
    project = _approved_mock_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(STUB_VIDEO_BYTES)
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false},
    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )

    report = run_qa(project, release=True)

    assert report.release_ready is False
    assert {issue.code for issue in report.hard_failures} >= {
        "RELEASE_VIDEO_IS_STUB",
        "RENDER_NOT_VERIFIABLE",
    }


def test_release_qa_rejects_release_without_audio_stream(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false},
    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        "packages.core.qa.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"streams":[{"codec_type":"video"}]}',
            stderr="",
        ),
    )

    report = run_qa(project, release=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_AUDIO_MISSING" for issue in report.hard_failures)


def test_release_qa_accepts_when_ffprobe_confirms_video_and_audio(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false},
    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        "packages.core.qa.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
            stderr="",
        ),
    )

    report = run_qa(project, release=True)

    assert report.release_ready is True


def test_release_qa_timeout_marks_video_not_verifiable(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false},
    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffprobe")

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout"))

    monkeypatch.setattr("packages.core.qa.subprocess.run", timeout_run)

    report = run_qa(project, release=True)

    assert report.release_ready is False
    assert any(issue.code == "RENDER_NOT_VERIFIABLE" for issue in report.hard_failures)
