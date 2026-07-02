import base64
import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from apps.cli.lingjian_cli.main import app
from packages.core.approvals import approve_target
from packages.core.artifacts import read_json, write_artifact
from packages.core.project import init_project
from packages.core.qa import run_qa
from packages.core.rendering import render_project
from providers.registry import resolve_provider

runner = CliRunner()


def _approved_real_project(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
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
            "scenes": [{"id": "s1", "narration_text": "真实画面生成测试"}],
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
                    "duration_sec": 1.5,
                }
            ],
            "total_duration_sec": 1.5,
        },
    )
    write_artifact(project, "visuals", {"id": "visuals", "scenes": []})
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    return project


def _fake_executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_visuals_writes_executable_generation_spec(tmp_path, monkeypatch):
    project_path = tmp_path / "visual-spec"
    project = init_project(project_path, "项目")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "mock",
            "provider_is_mock": True,
            "scenes": [{"id": "s1", "narration_text": "一镜到底展示产品卖点"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "mock",
            "provider_is_mock": True,
            "segments": [{"scene_id": "s1", "duration_sec": 2.25}],
        },
    )
    monkeypatch.setenv("LINGJIAN_HOST_IMAGEGEN_READY", "1")
    monkeypatch.setenv("PATH", "")

    result = runner.invoke(app, ["visuals", str(project_path), "--ratio", "9:16", "--json"])

    assert result.exit_code == 0
    visual_plan = read_json(project.path / "artifacts" / "visual_plan.json")
    scene = visual_plan["scenes"][0]
    assert scene["generator"] == "image-gen"
    assert scene["visual_prompt"]
    assert "一镜到底展示产品卖点" in scene["visual_prompt"]
    assert scene["motion_spec"]["main"] == "kenburns_zoom_in"
    assert scene["expected_asset_path"] == "assets/scenes/s1.png"
    assert scene["duration_sec"] == 2.25


def test_render_delegates_missing_image_asset_to_host_cli_before_assembly(
    tmp_path, monkeypatch
):
    project = _approved_real_project(tmp_path)
    imagegen = _fake_executable(
        tmp_path / "fake-imagegen",
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "payload=json.load(sys.stdin)\n"
        "out=pathlib.Path(payload['expected_asset_path'])\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "out.write_bytes(b'PNG')\n"
        "print(json.dumps({'asset_path': str(out)}))\n",
    )
    monkeypatch.setenv("LINGJIAN_HOST_IMAGEGEN_CLI", str(imagegen))
    write_artifact(
        project,
        "visuals",
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "真实画面生成测试",
                    "duration_sec": 1.5,
                    "generator": "image-gen",
                    "asset_path": "assets/scenes/s1.png",
                    "expected_asset_path": "assets/scenes/s1.png",
                    "visual_prompt": "生成一张真实产品图",
                    "motion_spec": {"main": "kenburns_zoom_in", "one_main_only": True},
                    "subtitle_burn": True,
                }
            ],
        },
    )
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

    assert (project.path / "assets" / "scenes" / "s1.png").exists()
    assert manifest["visual_real_count"] == 1
    assert manifest["scenes"][0]["render_source"] == "image"


def test_release_qa_warns_when_audio_uses_preview_tts(tmp_path, monkeypatch):
    project = _approved_real_project(tmp_path)
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
    {"id": "macos_say", "kind": "tts", "is_mock": false},
    {"id": "delegated_scene_assembly", "kind": "renderer", "is_mock": false}
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
    assert any(issue.code == "RELEASE_AUDIO_IS_PREVIEW_VOICE" for issue in report.warnings)

    strict_report = run_qa(project, release=True, strict=True)

    assert strict_report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_IS_PREVIEW_VOICE"
        for issue in strict_report.hard_failures
    )


def test_volcengine_tts_provider_uses_official_http_contract(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APP_ID", "appid")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "token-secret")
    monkeypatch.setenv("VOLCENGINE_TTS_CLUSTER", "volcano_tts")
    monkeypatch.setenv("VOLCENGINE_TTS_VOICE_TYPE", "zh_female")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {"code": 3000, "data": base64.b64encode(b"WAVDATA").decode("ascii")}
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("providers.volcengine_tts.urlopen", fake_urlopen)

    provider = resolve_provider("volcengine_tts", "tts")
    audio, duration = provider.synthesize({"voice": "zh_female", "text": "发布级中文配音"})

    assert audio == b"WAVDATA"
    assert duration > 0
    assert captured["headers"]["Authorization"] == "Bearer token-secret"
    assert captured["payload"]["app"]["appid"] == "appid"
    assert captured["payload"]["audio"]["voice_type"] == "zh_female"
    assert captured["payload"]["request"]["text"] == "发布级中文配音"


def test_inherited_cli_retries_once_after_transient_failure(tmp_path, monkeypatch):
    state = tmp_path / "state.txt"
    claude = _fake_executable(
        tmp_path / "claude",
        "#!/bin/sh\n"
        f"state='{state}'\n"
        "if [ ! -f \"$state\" ]; then echo fail > \"$state\"; exit 7; fi\n"
        "printf '继承 CLI 重试后成功生成脚本'\n",
    )
    monkeypatch.setenv("PATH", str(tmp_path))

    provider = resolve_provider("claude_cli", "llm")
    script = provider.generate_script({"type": "product"})

    assert claude.exists()
    assert script["scenes"][0]["narration_text"] == "继承 CLI 重试后成功生成脚本"


def test_setup_detects_host_imagegen_cli_as_static_visual_tier(tmp_path, monkeypatch):
    imagegen = _fake_executable(
        tmp_path / "imagegen-cli",
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        "payload=json.load(sys.stdin)\n"
        "out=pathlib.Path(payload['expected_asset_path'])\n"
        "out.write_bytes(b'PNG')\n"
        "print(json.dumps({'asset_path': str(out)}))\n",
    )
    monkeypatch.setenv("LINGJIAN_HOST_IMAGEGEN_CLI", str(imagegen))
    monkeypatch.setenv("PATH", "")

    result = runner.invoke(app, ["setup", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["capabilities"]["visuals"]["best"]["id"] == "host_imagegen"
    assert payload["capabilities"]["visuals"]["best"]["safe_for_release"] is True


def test_setup_rejects_host_imagegen_cli_that_does_not_write_probe_asset(
    tmp_path, monkeypatch
):
    imagegen = _fake_executable(tmp_path / "imagegen-cli", "#!/bin/sh\nexit 0\n")
    monkeypatch.setenv("LINGJIAN_HOST_IMAGEGEN_CLI", str(imagegen))
    monkeypatch.setenv("PATH", "")

    result = runner.invoke(app, ["setup", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["capabilities"]["visuals"]["best"]["id"] == "fallback_solid"
