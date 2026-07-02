import base64
import json
import subprocess

from packages.core.capabilities import detect_capabilities
from packages.core.project import ProjectRef
from packages.core.qa import run_qa
from packages.core.visual_generation import ensure_scene_asset
from providers.registry import resolve_provider


def test_kokoro_zero_key_tts_is_auto_release_candidate(monkeypatch):
    monkeypatch.setattr(
        "packages.core.capabilities._local_tts_probe",
        lambda provider_id: provider_id == "kokoro_zh_tts",
    )
    monkeypatch.setenv("PATH", "")

    report = detect_capabilities()

    assert report.groups["tts"].best.id == "kokoro_zh_tts"
    assert report.groups["tts"].best.quality_tier == "zero_key"
    assert report.groups["tts"].best.safe_for_release is True


def test_say_is_not_release_tts_candidate(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    say = bin_dir / "say"
    say.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    say.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr("packages.core.capabilities._local_tts_probe", lambda provider_id: False)

    report = detect_capabilities()

    assert report.groups["tts"].best.id == "missing_tts"
    say_candidate = next(item for item in report.groups["tts"].candidates if item.id == "macos_say")
    assert say_candidate.configured is True
    assert say_candidate.safe_for_release is False


def test_kokoro_provider_uses_json_adapter(monkeypatch):
    audio_base64 = base64.b64encode(b"WAVDATA").decode("ascii")

    def fake_run(command, **kwargs):
        if command[-1] == "--probe":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"audio_base64": audio_base64, "duration_sec": 2.75}),
            stderr="",
        )

    monkeypatch.setattr("providers.local_zero_key_tts.subprocess.run", fake_run)

    provider = resolve_provider("kokoro", "tts")
    audio, duration = provider.synthesize({"voice": "test-voice", "text": "中文自然口播"})

    assert provider.id == "kokoro_zh_tts"
    assert audio == b"WAVDATA"
    assert duration == 2.75


def test_hyperframes_default_adapter_generates_scene_asset(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    project.path.mkdir()
    expected = project.path / "assets" / "scenes" / "s1.mp4"

    monkeypatch.setattr("packages.core.visual_generation._npx_hyperframes_available", lambda: True)

    def fake_run(command, **kwargs):
        payload = json.loads(kwargs["input"])
        assert command[-1].endswith("hyperframes_scene_cli.py")
        expected_path = payload["expected_asset_path"]
        with open(expected_path, "wb") as handle:
            handle.write(b"MP4")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"asset_path": expected_path}),
            stderr="",
        )

    monkeypatch.setattr("packages.core.visual_generation.run_subprocess", fake_run)

    scene = ensure_scene_asset(
        project,
        {
            "scene_id": "s1",
            "generator": "hyperframes",
            "expected_asset_path": "assets/scenes/s1.mp4",
            "visual_prompt": "中文短视频动态画面",
            "duration_sec": 1.0,
        },
    )

    assert expected.exists()
    assert scene["generation_status"] == "generated"
    assert scene["asset_path"] == "assets/scenes/s1.mp4"


def test_release_qa_allows_kokoro_zero_key_tts(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "kokoro_zh_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
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

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is True
    assert not any(issue.code == "RELEASE_AUDIO_IS_PREVIEW_VOICE" for issue in report.warnings)
