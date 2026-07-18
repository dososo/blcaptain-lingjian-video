import base64
import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from apps.cli.lingjian_cli.main import app
from packages.core.approvals import approve_target
from packages.core.artifacts import read_json, write_artifact
from packages.core.capabilities import CapabilityCandidate, CapabilityGroup, CapabilityReport
from packages.core.director_contract import director_review_sheet_markdown
from packages.core.errors import LingjianError
from packages.core.hash import canonical_json_hash
from packages.core.project import init_project
from packages.core.qa import run_qa
from packages.core.rendering import render_project
from providers.registry import resolve_provider
from providers.volcengine_tts import VolcengineTTSProvider, _wav_duration_or_default

runner = CliRunner()


def _write_visuals_artifact(project, artifact: dict) -> None:
    write_artifact(project, "visuals", artifact)
    review_path = project.path / "artifacts" / "director_review_sheet.md"
    review_path.write_text(director_review_sheet_markdown(artifact), encoding="utf-8")


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
    _write_visuals_artifact(project, {"id": "visuals", "scenes": []})
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    return project


def _fake_executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_visuals_does_not_route_static_imagegen_as_release_visual(tmp_path, monkeypatch):
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
    assert scene["generator"] == "fallback_solid"
    assert scene["visual_prompt"]
    assert "一镜到底展示产品卖点" in scene["visual_prompt"]
    assert scene["motion_spec"]["main"] == "solid_card"
    assert scene["expected_asset_path"] is None
    assert scene["duration_sec"] == 2.25


def test_visuals_routes_all_missing_scenes_with_one_detected_visual_tier(
    tmp_path, monkeypatch
):
    project_path = tmp_path / "visual-consistent-route"
    project = init_project(project_path, "项目")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "第一镜"},
                {"id": "s2", "narration_text": "第二镜"},
                {"id": "s3", "narration_text": "第三镜"},
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "user_audio",
            "provider_is_mock": False,
            "segments": [
                {"scene_id": "s1", "duration_sec": 1.0},
                {"scene_id": "s2", "duration_sec": 1.0},
                {"scene_id": "s3", "duration_sec": 1.0},
            ],
        },
    )
    best = CapabilityCandidate(
        id="host_hyperframes",
        kind="visuals",
        source_type="host-plugin",
        configured=True,
        safe_for_release=False,
        label_zh="HyperFrames 样片动效",
    )
    report = CapabilityReport(
        groups={"visuals": CapabilityGroup("visuals", best, [best])},
        summary_zh="",
        next_steps=[],
    )
    monkeypatch.setattr("apps.cli.lingjian_cli.main.detect_capabilities", lambda: report)

    result = runner.invoke(app, ["visuals", str(project_path), "--ratio", "9:16", "--json"])

    assert result.exit_code == 0
    visual_plan = read_json(project.path / "artifacts" / "visual_plan.json")
    assert [scene["generator"] for scene in visual_plan["scenes"]] == [
        "hyperframes",
        "hyperframes",
        "hyperframes",
    ]


def test_visuals_uses_script_scene_duration_when_voice_is_single_full_audio(
    tmp_path, monkeypatch
):
    project_path = tmp_path / "visual-duration"
    project = init_project(project_path, "项目")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {
                    "scene_id": "s1",
                    "role": "hook",
                    "duration_sec": 6,
                    "narration_text": "第一镜完整口播。",
                    "on_screen_text": "第一重点",
                    "visual_prompt": "开场强钩子",
                },
                {
                    "scene_id": "s2",
                    "role": "pain",
                    "duration_sec": 7,
                    "narration_text": "第二镜完整口播。",
                    "on_screen_text": "第二重点",
                    "visual_prompt": "痛点放大",
                },
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "kokoro_zh_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 13.0}],
            "total_duration_sec": 13.0,
        },
    )
    monkeypatch.setenv("PATH", "")

    result = runner.invoke(app, ["visuals", str(project_path), "--ratio", "9:16", "--json"])

    assert result.exit_code == 0
    visual_plan = read_json(project.path / "artifacts" / "visual_plan.json")
    scenes = visual_plan["scenes"]
    assert [scene["duration_sec"] for scene in scenes] == [6.0, 7.0]
    assert scenes[0]["role"] == "hook"
    assert scenes[0]["on_screen_text"] == "第一重点"
    assert "视觉关键词:第一重点" in scenes[0]["visual_prompt"]


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
    _write_visuals_artifact(
        project,
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
        if Path(str(command[0])).name == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"codec_type": "audio"}]}),
                stderr="",
            )
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert (project.path / "assets" / "scenes" / "s1.png").exists()
    assert manifest["visual_real_count"] == 0
    assert manifest["scenes"][0]["render_source"] == "image"


def test_release_qa_warns_when_audio_uses_preview_tts(tmp_path, monkeypatch):
    project = _approved_real_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    visual_plan_sha256 = canonical_json_hash({"id": "visuals", "scenes": []})
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_plan_sha256": visual_plan_sha256,
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "macos_say", "kind": "tts", "is_mock": False},
                    {
                        "id": "delegated_scene_assembly",
                        "kind": "renderer",
                        "is_mock": False,
                    },
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
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "api-key-secret")
    monkeypatch.setenv("VOLCENGINE_TTS_RESOURCE_ID", "seed-tts-2.0")
    monkeypatch.setenv("VOLCENGINE_TTS_VOICE_TYPE", "zh_female_vv_uranus_bigtts")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            audio_chunk = json.dumps(
                {"code": 0, "data": base64.b64encode(b"WAVDATA").decode("ascii")}
            )
            final_chunk = json.dumps({"code": 20000000, "message": "ok"})
            return f"{audio_chunk}{final_chunk}".encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("providers.volcengine_tts.urlopen", fake_urlopen)

    provider = resolve_provider("volcengine_tts", "tts")
    audio, duration = provider.synthesize({"voice": "zh_female", "text": "发布级中文配音"})

    assert audio == b"WAVDATA"
    assert duration > 0
    assert captured["headers"]["x-api-key"] == "api-key-secret"
    assert captured["headers"]["x-api-resource-id"] == "seed-tts-2.0"
    assert captured["payload"]["req_params"]["speaker"] == "zh_female"
    assert captured["payload"]["req_params"]["text"] == "发布级中文配音"
    assert captured["payload"]["req_params"]["audio_params"]["format"] == "wav"
    assert captured["payload"]["req_params"]["audio_params"]["sample_rate"] == 24000
    assert provider.voice_settings("zh_female") == {
        "resource_id": "seed-tts-2.0",
        "voice_type": "zh_female",
        "audio_format": "wav",
        "sample_rate": 24000,
        "track_strategy": "continuous_full_track",
    }


def test_volcengine_streaming_wav_duration_uses_actual_data_size():
    sample_rate = 24000
    byte_rate = sample_rate * 2
    pcm = b"\x00\x00" * sample_rate * 2
    wav = (
        b"RIFF"
        + (0xFFFFFFFF).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + sample_rate.to_bytes(4, "little")
        + byte_rate.to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + (0xFFFFFFFF).to_bytes(4, "little")
        + pcm
    )

    assert _wav_duration_or_default(wav) == 2.0


def test_volcengine_voice_options_skip_unavailable_candidates(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "api-key-secret")
    monkeypatch.setenv("VOLCENGINE_TTS_VOICE_CANDIDATES", "bad:不可用,good:可用音色")

    def fake_post_tts_v3(text, voice):
        if voice == "bad":
            raise LingjianError(
                "PROVIDER_API_FAILED",
                "音色不可用。",
                "请换一个音色。",
                {"provider": "volcengine_tts"},
            )
        return b"WAVDATA"

    monkeypatch.setattr("providers.volcengine_tts._post_tts_v3", fake_post_tts_v3)

    options = VolcengineTTSProvider().discover_voice_options("试听文本", limit=2)

    assert [option["voice_id"] for option in options] == [
        "good",
        "zh_female_vv_uranus_bigtts",
    ]
    assert options[0]["label_zh"] == "可用音色"
    assert options[0]["audio_bytes"] == b"WAVDATA"


def test_volcengine_default_voice_options_offer_two_female_three_male(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "api-key-secret")
    monkeypatch.delenv("VOLCENGINE_TTS_VOICE_TYPE", raising=False)
    monkeypatch.delenv("VOLCENGINE_TTS_VOICE_CANDIDATES", raising=False)

    requested: list[str] = []

    def fake_post_tts_v3(text, voice):
        requested.append(voice)
        return b"WAVDATA"

    monkeypatch.setattr("providers.volcengine_tts._post_tts_v3", fake_post_tts_v3)

    options = VolcengineTTSProvider().discover_voice_options("试听文本", limit=5)

    assert [option["voice_id"] for option in options] == [
        "zh_female_vv_uranus_bigtts",
        "zh_female_qingxinnvsheng_uranus_bigtts",
        "zh_male_yangguangqingnian_uranus_bigtts",
        "zh_male_yuanboxiaoshu_uranus_bigtts",
        "zh_male_qingshuangnanda_uranus_bigtts",
    ]
    assert [option["label_zh"] for option in options] == [
        "默认女声",
        "清新女声",
        "阳光青年男声",
        "渊博小叔男声",
        "清爽男大",
    ]
    assert requested == [option["voice_id"] for option in options]


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
    assert payload["capabilities"]["visuals"]["best"]["id"] == "fallback_solid"
    imagegen_candidate = next(
        item
        for item in payload["capabilities"]["visuals"]["candidates"]
        if item["id"] == "host_imagegen"
    )
    assert imagegen_candidate["configured"] is True
    assert imagegen_candidate["safe_for_release"] is False
    assert "静态参考图" in imagegen_candidate["label_zh"]


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


def test_split_full_track_by_whisper_snaps_to_sentence_boundaries():
    """P1-3 回归:整段 whisper 时间轴切分各镜——镜边界吸附句边界、cue 平移镜内相对。"""
    from apps.cli.lingjian_cli.main import _split_full_track_by_whisper

    scenes = [
        {"scene_id": "s1", "text": "做短视频最难的"},
        {"scene_id": "s2", "text": "从来不是剪辑"},
        {"scene_id": "s3", "text": "是不知道下一镜拍什么"},
    ]
    full_cues = [
        {"text": "做短视频", "start_sec": 0.0, "end_sec": 1.4},
        {"text": "最难的", "start_sec": 1.4, "end_sec": 2.9},
        {"text": "从来不是剪辑", "start_sec": 2.9, "end_sec": 5.1},
        {"text": "是不知道", "start_sec": 5.1, "end_sec": 6.6},
        {"text": "下一镜拍什么", "start_sec": 6.6, "end_sec": 8.0},
    ]
    durations, per_scene = _split_full_track_by_whisper(scenes, full_cues, 8.0)

    assert abs(sum(durations) - 8.0) < 0.05  # 时长守恒
    assert abs(durations[0] - 2.9) < 0.6  # 镜1末吸附到句边界 ~2.9,不是纯字数估
    for cues in per_scene:
        prev = -0.001
        for cue in cues:
            assert cue["start_sec"] >= 0.0  # 镜内相对
            assert cue["start_sec"] >= prev - 0.001  # 单调
            assert cue["end_sec"] > cue["start_sec"]
            assert cue["timing_basis"] == "whisper_full_track_split"
            prev = cue["end_sec"]
        if cues:
            assert cues[0]["start_sec"] < 0.6  # 每镜首 cue 从 ~0 起


def test_split_full_track_by_whisper_returns_none_without_cues():
    """无 cues 时返回 None,调用方回退字数估(兜底路径不破坏)。"""
    from apps.cli.lingjian_cli.main import _split_full_track_by_whisper

    scenes = [{"scene_id": "s1", "text": "abc"}, {"scene_id": "s2", "text": "def"}]
    assert _split_full_track_by_whisper(scenes, [], 5.0) is None
    one_cue = [{"text": "x", "start_sec": 0, "end_sec": 1}]
    assert _split_full_track_by_whisper([], one_cue, 5.0) is None


def test_voiceless_voice_plan_is_text_card_narrative(tmp_path):
    """P1-4 回归:无旁白模式产出 voiceless voice_plan(非 mock、文字卡字幕、无 TTS)。"""
    from apps.cli.lingjian_cli.main import _write_voiceless_voice_plan
    from packages.core.artifacts import artifact_path, read_json, write_artifact
    from packages.core.project import ProjectRef

    ref = ProjectRef(tmp_path, tmp_path.name)
    write_artifact(
        ref,
        "script",
        {
            "id": "script",
            "scenes": [
                {"id": "s1", "on_screen_text": "镊子夹起花纹"},
                {"id": "s2", "on_screen_text": "放上蓝晒纸,晒太阳"},
            ],
        },
    )
    _write_voiceless_voice_plan(ref)
    vp = read_json(artifact_path(ref, "voice"))
    assert vp["voiceover"] is False
    assert vp["provider_is_mock"] is False  # 有意无旁白,不是 mock 冒充
    assert vp["provider_id"] == "voiceless"
    assert len(vp["segments"]) == 2
    assert all(s["duration_sec"] >= 2.5 for s in vp["segments"])  # 文字卡阅读最短时长
    assert all(s.get("caption_cues") for s in vp["segments"])  # 文字卡字幕承担叙事
    assert vp["total_duration_sec"] == sum(s["duration_sec"] for s in vp["segments"])
