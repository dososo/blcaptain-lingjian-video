import json
import shlex
import subprocess
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from apps.cli.lingjian_cli.main import (
    _capture_url_recording,
    _capture_url_screenshot,
    _codex_record_command_prefix,
    _director_review_response,
    _write_evidence_collection_checklist,
    app,
)
from packages.core.approvals import approve_target, validate_render_gate
from packages.core.artifacts import write_artifact
from packages.core.director_contract import director_review_sheet_markdown, profile_preset
from packages.core.errors import LingjianError
from packages.core.evidence_assets import (
    collect_evidence_assets,
    evidence_assets_for_scene,
    materialize_evidence_clips,
)
from packages.core.project import ProjectRef, init_project
from packages.core.qa import QAIssue, QAReport
from packages.core.rendering import RenderResult
from scripts.providers import terminal_record_cli

runner = CliRunner()


def _patch_evidence_recording_ffprobe(
    monkeypatch,
    *,
    has_video_stream: bool = True,
    duration_sec: float = 2.4,
) -> None:
    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )
    codec_type = "video" if has_video_stream else "audio"

    def fake_run(command, **kwargs):
        if "format=duration" in command:
            stdout = json.dumps({"format": {"duration": str(duration_sec)}})
        else:
            stdout = json.dumps({"streams": [{"codec_type": codec_type}]})
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(
        "packages.core.evidence_assets.subprocess.run",
        fake_run,
    )


def _patch_cli_recording_probe(
    monkeypatch,
    *,
    has_video_stream: bool = True,
    duration_sec: float = 2.4,
) -> None:
    status = "verifiable" if has_video_stream else "not_verifiable"
    payload = {
        "source_video_probe_status": status,
        "source_video_has_video_stream": has_video_stream,
        "source_video_probe_tool": "ffprobe",
        "source_video_probe_hint_zh": (
            "ffprobe 已确认该文件包含视频流,可作为发布级动态证据候选。"
            if has_video_stream
            else "ffprobe 未发现 video stream;该文件不能作为发布级动态视频素材。"
        ),
    }
    if has_video_stream:
        payload["source_video_duration_sec"] = duration_sec
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main._probe_video_stream",
        lambda path: dict(payload),
    )


def _write_visuals_artifact(project, artifact: dict) -> None:
    write_artifact(project, "visuals", artifact)
    review_path = project.path / "artifacts" / "director_review_sheet.md"
    review_path.write_text(director_review_sheet_markdown(artifact), encoding="utf-8")


def test_terminal_record_cli_uses_textfile_for_complex_qa_json(
    tmp_path,
    monkeypatch,
):
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        vf = command[command.index("-vf") + 1]
        textfile = Path(vf.split("textfile=", 1)[1].split(":x=", 1)[0])
        captured["vf"] = vf
        captured["text"] = textfile.read_text(encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(terminal_record_cli.subprocess, "run", fake_run)
    complex_text = (
        'stdout:\n{"hard_failures":[{"code":"RELEASE_AUDIO_ASSET_BLOCKERS_REMAIN"}],'
        '"remaining_audio_asset_blockers":[{"first_command":"uv run lj ingest audio '
        "/tmp/project --file '把音效文件拖到这里.wav' --kind sfx --json\"}]}"
    )

    terminal_record_cli._render_terminal_video(complex_text, tmp_path / "terminal.mp4")

    vf = str(captured["vf"])
    assert "textfile=" in vf
    assert "expansion=none" in vf
    assert "remaining_audio_asset_blockers" not in vf
    assert "remaining_audio_asset_blockers" in str(captured["text"])


def test_render_help_has_no_force_option():
    result = runner.invoke(app, ["render", "--help"])

    assert result.exit_code == 0
    assert "--force" not in result.output


def test_release_commands_expose_strict_option():
    assert "--strict" in runner.invoke(app, ["qa", "--help"]).output
    assert "--strict" in runner.invoke(app, ["render", "--help"]).output
    assert "--strict" in runner.invoke(app, ["export", "--help"]).output
    assert "--strict" in runner.invoke(app, ["run", "--help"]).output


def test_cli_render_release_strict_passes_strict_to_renderer(tmp_path, monkeypatch):
    project = tmp_path / "strict-render"
    project.mkdir()
    video_path = project / "renders" / "release" / "douyin" / "video.mp4"
    manifest_path = project / "renders" / "release" / "douyin" / "render_manifest.json"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"mp4")
    manifest_path.write_text("{}", encoding="utf-8")
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.validate_render_gate",
        lambda ref: None,
    )

    def fake_render_project(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return RenderResult("release", video_path, manifest_path)

    monkeypatch.setattr("apps.cli.lingjian_cli.main.render_project", fake_render_project)

    result = runner.invoke(
        app,
        [
            "render",
            str(project),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--release",
            "--strict",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["kwargs"]["mode"] == "release"
    assert seen["kwargs"]["strict"] is True


def test_ingest_audio_imports_bgm_and_sfx_into_voice_plan(tmp_path, monkeypatch):
    project = init_project(tmp_path / "audio-assets", "声音素材")
    write_artifact(project, "script", {"id": "script", "scenes": []})
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )
    _write_visuals_artifact(project, {"id": "visuals", "scenes": []})
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    bgm = tmp_path / "private-bgm.wav"
    sfx = tmp_path / "private-click.wav"
    bgm.write_bytes(b"BGM")
    sfx.write_bytes(b"SFX")
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )

    def fake_probe_run(command, **kwargs):
        assert command[0].endswith("ffprobe")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"streams": [{"codec_type": "audio"}]}),
            stderr="",
        )

    monkeypatch.setattr("apps.cli.lingjian_cli.main.subprocess.run", fake_probe_run)

    bgm_result = runner.invoke(
        app,
        [
            "ingest",
            "audio",
            str(project.path),
            "--kind",
            "bgm",
            "--file",
            str(bgm),
            "--bgm-to-voice-db",
            "-18",
            "--json",
        ],
    )
    sfx_result = runner.invoke(
        app,
        [
            "ingest",
            "audio",
            str(project.path),
            "--kind",
            "sfx",
            "--file",
            str(sfx),
            "--scene-id",
            "s1",
            "--at-sec",
            "1.25",
            "--gain-db",
            "-12",
            "--action",
            "按钮点击",
            "--purpose",
            "提示用户注意 CTA",
            "--visual-event",
            "cta_button_click",
            "--json",
        ],
    )

    assert bgm_result.exit_code == 0
    assert sfx_result.exit_code == 0
    bgm_payload = json.loads(bgm_result.output)
    sfx_payload = json.loads(sfx_result.output)
    assert bgm_payload["status"] == "audio_asset_ready"
    assert bgm_payload["kind"] == "bgm"
    assert bgm_payload["source_audio_probe_status"] == "verifiable"
    assert bgm_payload["source_audio_has_audio_stream"] is True
    assert bgm_payload["voice_reapproval_required"] is True
    assert bgm_payload["approval_command"].startswith("uv run lj approve voice ")
    assert bgm_payload["next_command_kind"] == "approve_voice"
    assert bgm_payload["next_command"] == bgm_payload["approval_command"]
    assert sfx_payload["kind"] == "sfx"
    assert sfx_payload["scene_id"] == "s1"
    assert sfx_payload["at_sec"] == 1.25
    assert sfx_payload["local_at_sec"] == 1.25
    assert sfx_payload["time_basis"] == "scene_local"
    assert sfx_payload["gain_db"] == -12.0
    assert sfx_payload["next_command_kind"] == "approve_voice"
    assert sfx_payload["next_command"] == sfx_payload["approval_command"]
    voice_plan = json.loads(
        (project.path / "artifacts" / "voice_plan.json").read_text(encoding="utf-8")
    )
    audio_assets = voice_plan["audio_assets"]
    assert audio_assets["bgm"]["path"].startswith("assets/audio/bgm-")
    assert audio_assets["bgm"]["bgm_to_voice_db"] == -18.0
    assert audio_assets["bgm"]["original_path_redacted"] is True
    assert audio_assets["sfx"][0]["path"].startswith("assets/audio/sfx-")
    assert audio_assets["sfx"][0]["scene_id"] == "s1"
    assert audio_assets["sfx"][0]["local_at_sec"] == 1.25
    assert audio_assets["sfx"][0]["time_basis"] == "scene_local"
    assert audio_assets["sfx"][0]["action"] == "按钮点击"
    assert (project.path / audio_assets["bgm"]["path"]).read_bytes() == b"BGM"
    assert (project.path / audio_assets["sfx"][0]["path"]).read_bytes() == b"SFX"
    assert str(tmp_path) not in json.dumps(voice_plan, ensure_ascii=False)
    input_assets = json.loads(
        (project.path / "assets" / "input_assets.json").read_text(encoding="utf-8")
    )
    assert input_assets[-1]["target_scene_id"] == "s1"
    assert input_assets[-1]["local_at_sec"] == 1.25
    assert input_assets[-1]["time_basis"] == "scene_local"
    gate_error = validate_render_gate(project)
    assert gate_error is not None
    assert gate_error.error_code == "APPROVAL_STALE"
    assert gate_error.details["stale"] == ["voice"]


def test_ingest_audio_guides_remaining_audio_assets_before_voice_reapproval(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "audio-recovery-flow", "声音素材恢复")
    write_artifact(project, "script", {"id": "script", "scenes": []})
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "scenes": [
                {
                    "scene_id": "s1",
                    "duration_sec": 2.0,
                    "bgm": "科技感 BGM,人声优先",
                    "sfx_points": [{"action": "按钮点击", "time_sec": 1.0}],
                }
            ],
        },
    )
    bgm = tmp_path / "private-bgm.wav"
    sfx = tmp_path / "private-click.wav"
    bgm.write_bytes(b"BGM")
    sfx.write_bytes(b"SFX")
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )

    def fake_probe_run(command, **kwargs):
        assert command[0].endswith("ffprobe")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"streams": [{"codec_type": "audio"}]}),
            stderr="",
        )

    monkeypatch.setattr("apps.cli.lingjian_cli.main.subprocess.run", fake_probe_run)

    bgm_result = runner.invoke(
        app,
        [
            "ingest",
            "audio",
            str(project.path),
            "--kind",
            "bgm",
            "--file",
            str(bgm),
            "--json",
        ],
    )

    assert bgm_result.exit_code == 0
    bgm_payload = json.loads(bgm_result.output)
    assert bgm_payload["next_command_kind"] == "ingest_audio"
    assert bgm_payload["audio_assets_remaining_before_voice_approval"] is True
    assert "approval_blocked_until_audio_assets_zh" in bgm_payload
    assert [item["kind"] for item in bgm_payload["remaining_audio_asset_blockers"]] == [
        "sfx"
    ]
    assert bgm_payload["audio_asset_next_command"] == bgm_payload["next_command"]
    assert "uv run lj ingest audio" in bgm_payload["next_command"]
    assert "--kind sfx" in bgm_payload["next_command"]
    assert "--scene-id s1" in bgm_payload["next_command"]
    assert "--at-sec 1" in bgm_payload["next_command"]
    assert "--action" in bgm_payload["next_command"]
    assert bgm_payload["approval_command"].startswith("uv run lj approve voice ")

    sfx_result = runner.invoke(
        app,
        [
            "ingest",
            "audio",
            str(project.path),
            "--kind",
            "sfx",
            "--file",
            str(sfx),
            "--scene-id",
            "s1",
            "--at-sec",
            "1",
            "--gain-db",
            "-12",
            "--action",
            "按钮点击",
            "--json",
        ],
    )

    assert sfx_result.exit_code == 0
    sfx_payload = json.loads(sfx_result.output)
    assert sfx_payload["next_command_kind"] == "approve_voice"
    assert sfx_payload["next_command"] == sfx_payload["approval_command"]
    assert "remaining_audio_asset_blockers" not in sfx_payload
    assert "audio_assets_remaining_before_voice_approval" not in sfx_payload


def test_ingest_audio_rejects_unverifiable_audio_before_voice_plan_write(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "bad-audio-assets", "坏声音素材")
    write_artifact(project, "script", {"id": "script", "scenes": []})
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )
    bad_audio = tmp_path / "private-bgm.wav"
    bad_audio.write_bytes(b"not an audio stream")
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )

    def fake_probe_run(command, **kwargs):
        assert command[0] == "/usr/bin/ffprobe"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"streams": [{"codec_type": "video"}]}),
            stderr="",
        )

    monkeypatch.setattr("apps.cli.lingjian_cli.main.subprocess.run", fake_probe_run)

    result = runner.invoke(
        app,
        [
            "ingest",
            "audio",
            str(project.path),
            "--kind",
            "bgm",
            "--file",
            str(bad_audio),
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error_code"] == "INPUT_AUDIO_NOT_VERIFIABLE"
    assert payload["source_audio_probe_status"] == "not_verifiable"
    voice_plan = json.loads(
        (project.path / "artifacts" / "voice_plan.json").read_text(encoding="utf-8")
    )
    assert "audio_assets" not in voice_plan
    assert not (project.path / "assets" / "audio").exists()


def test_cli_approve_visuals_requires_director_review_sheet(tmp_path):
    project = init_project(tmp_path / "missing-review", "项目")
    visual_plan = {
        "id": "visuals",
        "scenes": [
            {
                "scene_id": "s1",
                "narration_text": "需要先展示完整画面确认单。",
            }
        ],
    }
    write_artifact(project, "visuals", visual_plan)

    result = runner.invoke(
        app,
        ["approve", "visuals", str(project.path), "--approved-by", "tester", "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["error_code"] == "DIRECTOR_REVIEW_SHEET_REQUIRED"
    assert payload["current_step"] == "visuals"
    assert payload["director_review_artifact"] == "artifacts/director_review_sheet.md"
    assert payload["director_review_regenerated"] is True
    assert "director_review_markdown" in payload
    assert (
        project.path / "artifacts" / "director_review_sheet.md"
    ).read_text(encoding="utf-8") == director_review_sheet_markdown(visual_plan)


def test_script_command_writes_director_contract(tmp_path):
    project = init_project(tmp_path / "script-contract", "项目")

    result = runner.invoke(
        app,
        [
            "script",
            str(project.path),
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--duration",
            "45",
            "--style",
            "tech_minimal",
            "--profile",
            "shipinhao_knowledge",
            "--provider",
            "mock",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((project.path / "artifacts" / "script.json").read_text())
    assert payload["style"] == "tech_minimal"
    assert payload["profile"] == "shipinhao_knowledge"
    assert payload["hook_library"]
    assert "Hook→痛点→方案→证明→CTA" in payload["plan_summary"]
    assert payload["style_lock"]["label_zh"] == "科技极简"


def test_script_command_infers_open_source_project_profile_from_input(tmp_path):
    project = init_project(tmp_path / "script-open-source-profile", "项目")
    assets_dir = project.path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "input_assets.json").write_text(
        json.dumps(
            [
                {
                    "type": "text",
                    "text": "我要做灵剪是什么的开源项目介绍,让观众关注 GitHub 并 star。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "script",
            str(project.path),
            "--type",
            "video",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--provider",
            "mock",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((project.path / "artifacts" / "script.json").read_text())
    assert payload["profile"] == "open_source_project_intro"
    assert "GitHub repo" in payload["profile_preset"]["required_evidence"]


def test_script_command_passes_input_source_brief_to_real_llm_prompt(tmp_path, monkeypatch):
    project = init_project(tmp_path / "script-source-brief", "项目")
    assets_dir = project.path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "input_assets.json").write_text(
        json.dumps(
            [
                {
                    "type": "text",
                    "text": (
                        "从用户第一次下载安装灵剪开始,端到端展示 doctor、脚本、配音、"
                        "分镜、QA 和导出,禁止使用录屏素材。"
                    ),
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    prompt_path = tmp_path / "prompt.txt"
    claude = bin_dir / "claude"
    claude.write_text(
        "#!/bin/sh\n"
        f"printf '%s' \"$2\" > {shlex.quote(str(prompt_path))}\n"
        "printf '%s' "
        "'{\"scenes\":[{\"id\":\"s1\",\"narration_text\":\"首次下载安装到导出候选\"}]}'\n",
        encoding="utf-8",
    )
    claude.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    result = runner.invoke(
        app,
        [
            "script",
            str(project.path),
            "--type",
            "tutorial",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--provider",
            "claude",
            "--json",
        ],
    )

    assert result.exit_code == 0
    prompt = prompt_path.read_text(encoding="utf-8")
    payload = json.loads((project.path / "artifacts" / "script.json").read_text())
    assert "第一次下载安装灵剪" in prompt
    assert "禁止使用录屏素材" in prompt
    assert payload["provider_id"] == "claude_cli"
    assert payload["source_brief"]["items"][0]["type"] == "text"
    assert "doctor、脚本、配音" in payload["source_brief"]["items"][0]["content"]


def test_visuals_command_writes_scene_director_contract_and_remotion_notice(tmp_path):
    project = init_project(tmp_path / "visual-contract", "项目")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "scenes": [
                {
                    "id": "s1",
                    "role": "hook",
                    "narration_text": "第一秒先抓住注意力。",
                    "duration_sec": 2.0,
                }
            ],
        },
    )

    result = runner.invoke(
        app,
        [
            "visuals",
            str(project.path),
            "--engine",
            "remotion",
            "--style",
            "tech_minimal",
            "--profile",
            "shipinhao_knowledge",
            "--json",
        ],
    )

    assert result.exit_code == 0
    result_payload = json.loads(result.output)
    payload = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    review_md = project.path / "artifacts" / "director_review_sheet.md"
    scene = payload["scenes"][0]
    assert result_payload["director_review_artifact"] == "artifacts/director_review_sheet.md"
    assert "导演分镜确认单 v2" in result_payload["director_review_markdown"]
    assert "镜头目标:" in result_payload["director_review_markdown"]
    assert review_md.exists()
    review_text = review_md.read_text(encoding="utf-8")
    required_review_labels = [
        "镜头编号:",
        "镜头目标:",
        "叙事作用:",
        "口播文本:",
        "屏幕短文案:",
        "画面内容:",
        "素材来源:",
        "素材状态:",
        "Profile 证据要求:",
        "引擎路由:",
        "构图:",
        "主体区域:",
        "字幕区域:",
        "遮罩/避让规则:",
        "视觉元素:",
        "色彩/氛围:",
        "主运动:",
        "辅助运动:",
        "转场:",
        "关键帧:",
        "入场动画:",
        "出场动画:",
        "BGM 情绪:",
        "音效点:",
        "字幕切分:",
        "字幕位置/大小:",
        "禁止项:",
        "QA 检查点:",
        "这一镜批准前你要看:",
    ]
    for label in required_review_labels:
        assert label in review_text
    assert "未声明s:" not in review_text
    assert "0.0s:" in review_text
    assert payload["style"] == "tech_minimal"
    assert payload["profile"] == "shipinhao_knowledge"
    assert scene["generator"] == "remotion"
    assert scene["template_id"] == "hook_codex_prompt"
    assert scene["layout_contract"]["safeBottomY"]
    assert "layout_contract" in scene["non_replaceable_fields"]
    assert scene["director_board"]["composition"]
    assert scene["director_board"]["subtitle_strategy"]["position"] == "底部安全区"
    assert scene["director_review_sheet"]["asset_status"]["publish_grade_visual"] is True
    assert scene["director_review_sheet_v2"] == scene["director_review_sheet"]
    assert scene["director_review_sheet_v2"]["version"] == "v2"
    assert scene["director_review_sheet"]["caption_region"]["safeBottomY"]
    assert scene["engine_policy"]["selected_engine"] == "remotion"
    assert scene["engine_policy"]["remotion_license_required"] is True
    assert "Remotion" in scene["route_reason"]
    assert scene["asset_strategy_v2"]["accepted_asset_formats"] == [
        "mp4",
        "mov",
        "m4v",
        "webm",
    ]
    assert scene["director_knowledge_refs"]["caption_rule"] == "bottom_safe_area_cjk"
    assert scene["caption_contract"]["position"] == "底部安全区"
    assert payload["director_router_summary"]["routes"][0]["selected_engine"] == "remotion"
    assert payload["director_knowledge_base_v1"]["version"] == "v1"
    assert payload["director_review_sheet_v2"]["markdown_artifact"] == (
        "artifacts/director_review_sheet.md"
    )
    assert payload["director_review_sheet_v2"]["scenes"][0]["scene_id"] == "s1"
    assert payload["asset_diagnosis_summary"]["non_publish_grade_count"] == 0
    assert len(scene["keyframe_beats"]) == 3
    assert any("remotion.pro" in notice for notice in payload["cost_notices"])


def test_visuals_auto_routes_hyperframes_remotion_and_user_video_by_scene(
    tmp_path,
    monkeypatch,
):
    project = init_project(tmp_path / "visual-mixed-router", "项目")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "profile": "knowledge_explainer",
            "scenes": [
                {
                    "id": "s1",
                    "role": "hook",
                    "narration_text": "一句话触发灵剪,开源项目介绍直接进入视频生产。",
                    "duration_sec": 2.0,
                },
                {
                    "id": "s2",
                    "role": "proof",
                    "narration_text": "严格 QA、ffprobe 和 render manifest 都会留下证据。",
                    "duration_sec": 2.0,
                },
                {
                    "id": "s3",
                    "role": "cta",
                    "narration_text": "最后引导观众关注项目并点 Star。",
                    "duration_sec": 2.0,
                },
            ],
        },
    )
    asset_dir = project.path / "assets" / "scenes"
    asset_dir.mkdir(parents=True)
    (asset_dir / "s3.mp4").write_bytes(b"USER_VIDEO")
    monkeypatch.setenv("LINGJIAN_HOST_HYPERFRAMES_READY", "1")
    monkeypatch.setenv("LINGJIAN_HOST_REMOTION_READY", "1")

    result = runner.invoke(
        app,
        [
            "visuals",
            str(project.path),
            "--style",
            "tech_minimal",
            "--profile",
            "knowledge_explainer",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    scenes = payload["scenes"]
    assert [scene["generator"] for scene in scenes] == [
        "hyperframes",
        "remotion",
        "user-asset",
    ]
    assert scenes[0]["engine_policy"]["selected_engine"] == "hyperframes"
    assert scenes[1]["blueprint_id"] == "proof_ffprobe_dashboard"
    assert scenes[1]["engine_policy"]["selected_engine"] == "remotion"
    assert scenes[1]["engine_policy"]["remotion_license_required"] is True
    assert "Remotion" in scenes[1]["route_reason"]
    assert scenes[2]["engine_policy"]["selected_engine"] == "user_video"
    assert scenes[2]["asset_path"] == "assets/scenes/s3.mp4"
    assert payload["director_router_summary"]["routes"][0]["selected_engine"] == "hyperframes"
    assert payload["director_router_summary"]["routes"][1]["selected_engine"] == "remotion"
    assert payload["director_router_summary"]["routes"][2]["selected_engine"] == "user_video"
    assert any("remotion.pro" in notice for notice in payload["cost_notices"])


def test_visuals_command_inherits_script_profile_when_default_is_used(tmp_path):
    project = init_project(tmp_path / "visual-inherit-profile", "项目")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "profile": "open_source_project_intro",
            "scenes": [
                {
                    "id": "s1",
                    "role": "proof",
                    "narration_text": "灵剪会留下 QA 和导出证据。",
                    "duration_sec": 2.0,
                }
            ],
        },
    )

    result = runner.invoke(
        app,
        [
            "visuals",
            str(project.path),
            "--engine",
            "hyperframes",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    scene = payload["scenes"][0]
    assert payload["profile"] == "open_source_project_intro"
    assert "GitHub repo" in scene["asset_strategy_v2"]["required_evidence"]
    assert scene["director_knowledge_refs"]["profile"] == "open_source_project_intro"


def test_visuals_command_profile_matrix_shows_required_evidence_in_review_sheet(tmp_path):
    profiles = [
        "product_intro",
        "open_source_project_intro",
        "tutorial_guide",
        "review_comparison",
        "ecommerce_sales",
        "knowledge_explainer",
    ]
    for profile in profiles:
        project = init_project(tmp_path / profile, f"{profile} 项目")
        write_artifact(
            project,
            "script",
            {
                "id": "script",
                "profile": profile,
                "scenes": [
                    {
                        "id": "s1",
                        "role": "proof",
                        "narration_text": "这一镜需要把内容证据讲清楚。",
                        "duration_sec": 2.0,
                    }
                ],
            },
        )

        result = runner.invoke(
            app,
            [
                "visuals",
                str(project.path),
                "--engine",
                "hyperframes",
                "--json",
            ],
        )

        assert result.exit_code == 0
        preset = profile_preset(profile)
        required_evidence = preset["required_evidence"]
        payload = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
        scene = payload["scenes"][0]
        review_text = (project.path / "artifacts" / "director_review_sheet.md").read_text(
            encoding="utf-8"
        )
        assert payload["profile"] == profile
        assert payload["profile_required_evidence"] == required_evidence
        assert scene["asset_strategy_v2"]["required_evidence"] == required_evidence
        assert "Profile 证据要求:" in review_text
        assert required_evidence[0] in review_text


def test_materialize_evidence_clips_writes_dynamic_manifest(tmp_path, monkeypatch):
    project = init_project(tmp_path / "materialized-evidence", "项目")
    artifact = project.path / "artifacts" / "qa_report.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps({"release_ready": True, "checks": ["ffprobe", "strict"]}),
        encoding="utf-8",
    )
    manifest = {
        "version": "v1",
        "assets": [
            {
                "id": "qa",
                "evidence_type": "qa_report_artifact",
                "path": "artifacts/qa_report.json",
            }
        ],
        "evidence_types": ["qa_report_artifact"],
    }
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        output = project.path / "assets" / "evidence" / "clips" / "qa.mp4"
        output.write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffmpeg",
    )
    monkeypatch.setattr("packages.core.evidence_assets.subprocess.run", fake_run)

    updated = materialize_evidence_clips(project, manifest)

    asset = updated["assets"][0]
    assert asset["evidence_clip_status"] == "generated"
    assert asset["materialized_evidence_video"] is True
    assert asset["publish_grade_evidence_video"] is False
    assert asset["evidence_clip_path"] == "assets/evidence/clips/qa.mp4"
    assert asset["evidence_clip_render_source"] == "dynamic_ffmpeg_drawtext"
    assert asset["evidence_clip_style"] == "qa_status_panel"
    assert asset["evidence_clip_role_zh"] == "展示 strict QA、ffprobe 和发布级门禁证据"
    assert updated["evidence_clip_summary"]["generated_count"] == 1
    assert updated["evidence_clip_summary"]["render_sources"] == ["dynamic_ffmpeg_drawtext"]
    assert updated["evidence_clip_summary"]["visual_sources"] == ["text_card"]
    assert updated["evidence_clip_summary"]["styles"] == ["qa_status_panel"]
    assert any("drawtext" in str(part) for part in commands[0])
    text_file = project.path / "assets" / "evidence" / "clips" / "qa.txt"
    assert "QA 严格门体检镜头" in text_file.read_text(encoding="utf-8")
    assert "QA 报告" in text_file.read_text(encoding="utf-8")
    assert "release_ready" in text_file.read_text(encoding="utf-8")


def test_materialize_evidence_clips_uses_type_specific_styles(tmp_path, monkeypatch):
    project = init_project(tmp_path / "typed-evidence", "项目")
    readme = project.path / "README.md"
    render_manifest = project.path / "renders" / "release" / "douyin" / "render_manifest.json"
    readme.write_text("# 灵剪\n\n用 Codex app 一句话触发。", encoding="utf-8")
    render_manifest.parent.mkdir(parents=True, exist_ok=True)
    render_manifest.write_text(
        json.dumps({"video_path": "renders/release/douyin/video.mp4"}),
        encoding="utf-8",
    )
    manifest = {
        "version": "v1",
        "assets": [
            {
                "id": "readme",
                "evidence_type": "readme_install_entry",
                "path": "README.md",
            },
            {
                "id": "render",
                "evidence_type": "render_manifest_capture",
                "path": "renders/release/douyin/render_manifest.json",
            },
        ],
        "evidence_types": ["readme_install_entry", "render_manifest_capture"],
    }

    def fake_run(command, **kwargs):
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffmpeg",
    )
    monkeypatch.setattr("packages.core.evidence_assets.subprocess.run", fake_run)

    updated = materialize_evidence_clips(project, manifest)

    styles = {asset["id"]: asset["evidence_clip_style"] for asset in updated["assets"]}
    assert styles == {
        "readme": "readme_install_scroll",
        "render": "render_manifest_timeline",
    }
    assert updated["evidence_clip_summary"]["styles"] == [
        "readme_install_scroll",
        "render_manifest_timeline",
    ]
    readme_text = (
        project.path / "assets" / "evidence" / "clips" / "readme.txt"
    ).read_text(encoding="utf-8")
    render_text = (
        project.path / "assets" / "evidence" / "clips" / "render.txt"
    ).read_text(encoding="utf-8")
    assert "README 首用路径镜头" in readme_text
    assert "Render Manifest 时间线镜头" in render_text
    assert readme_text != render_text


def test_materialize_evidence_clips_uses_source_screenshot_pixels(tmp_path, monkeypatch):
    project = init_project(tmp_path / "screenshot-evidence", "项目")
    screenshot = project.path / "assets" / "github-screen.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"png")
    manifest = {
        "version": "v1",
        "assets": [
            {
                "id": "github-screen",
                "evidence_type": "screenshot_capture",
                "path": "assets/github-screen.png",
            }
        ],
        "evidence_types": ["screenshot_capture"],
    }
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffmpeg",
    )
    monkeypatch.setattr("packages.core.evidence_assets.subprocess.run", fake_run)

    updated = materialize_evidence_clips(project, manifest)

    asset = updated["assets"][0]
    assert asset["evidence_clip_status"] == "generated"
    assert asset["materialized_evidence_video"] is True
    assert asset["publish_grade_evidence_video"] is False
    assert asset["evidence_clip_render_source"] == "dynamic_screenshot_scan"
    assert asset["evidence_visual_source"] == "source_image"
    assert asset["evidence_capture_note_zh"] == (
        "该证据短片基于静态截图/图片渲染为扫描动效,不是屏幕录制。"
    )
    assert asset["evidence_clip_style"] == "screenshot_capture_scan"
    assert asset["evidence_clip_role_zh"] == "展示用户提供/采集的界面截图证据,作为真实画面依据"
    assert updated["evidence_clip_summary"]["styles"] == ["screenshot_capture_scan"]
    assert updated["evidence_clip_summary"]["render_sources"] == ["dynamic_screenshot_scan"]
    assert updated["evidence_clip_summary"]["visual_sources"] == ["source_image"]
    assert str(screenshot) in commands[0]
    assert "-loop" in commands[0]
    assert "color=c=0x0b1020" not in " ".join(commands[0])


def test_materialize_evidence_clips_renders_terminal_log_replay(tmp_path, monkeypatch):
    project = init_project(tmp_path / "terminal-evidence", "项目")
    terminal_log = project.path / "logs" / "release.log"
    terminal_log.write_text(
        "\n".join(
            [
                "uv run lj qa ./project --release --strict --json",
                "VOLCENGINE_TTS_API_KEY=real-secret",
                "Authorization: Bearer abc.def.ghi",
                "release_ready=true hard_failures=[]",
            ]
        ),
        encoding="utf-8",
    )
    manifest = {
        "version": "v1",
        "assets": [
            {
                "id": "terminal",
                "evidence_type": "terminal_log_capture",
                "path": "logs/release.log",
            }
        ],
        "evidence_types": ["terminal_log_capture"],
    }
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffmpeg",
    )
    monkeypatch.setattr("packages.core.evidence_assets.subprocess.run", fake_run)

    updated = materialize_evidence_clips(project, manifest)

    asset = updated["assets"][0]
    assert asset["evidence_clip_status"] == "generated"
    assert asset["materialized_evidence_video"] is True
    assert asset["publish_grade_evidence_video"] is False
    assert asset["evidence_clip_render_source"] == "dynamic_terminal_replay"
    assert asset["evidence_visual_source"] == "terminal_transcript"
    assert asset["evidence_clip_style"] == "terminal_log_replay"
    assert asset["evidence_capture_note_zh"] == (
        "该证据短片基于项目日志文本渲染为终端回放,不是屏幕录制。"
    )
    assert updated["evidence_clip_summary"]["render_sources"] == ["dynamic_terminal_replay"]
    assert updated["evidence_clip_summary"]["visual_sources"] == ["terminal_transcript"]
    assert "-loop" not in commands[0]
    assert any("color=c=0x020617" in str(part) for part in commands[0])
    text = (project.path / "assets" / "evidence" / "clips" / "terminal.txt").read_text(
        encoding="utf-8"
    )
    assert "uv run lj qa" in text
    assert "real-secret" not in text
    assert "abc.def.ghi" not in text
    assert "VOLCENGINE_TTS_API_KEY=***" in text
    assert "Authorization: Bearer ***" in text


def test_cli_ingest_command_captures_terminal_log_without_secret_leak(
    tmp_path,
    monkeypatch,
):
    project = init_project(tmp_path / "command-evidence", "项目")
    command = f"{sys.executable} -c \"print('API_KEY=real-secret')\""

    result = runner.invoke(
        app,
        [
            "ingest",
            "command",
            str(project.path),
            "--command",
            command,
            "--role",
            "terminal",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "real-secret" not in result.output
    payload = json.loads(result.output)
    assert payload["command_status"] == "captured"
    assert payload["command_exit_code"] == 0
    log_path = project.path / payload["log_path"]
    assert log_path.exists()
    log_text = log_path.read_text(encoding="utf-8")
    assert "real-secret" not in log_text
    assert "API_KEY=***" in log_text
    input_assets_text = (project.path / "assets" / "input_assets.json").read_text(
        encoding="utf-8"
    )
    assert "real-secret" not in input_assets_text
    input_assets = json.loads(input_assets_text)
    assert input_assets[0]["type"] == "terminal_command"
    assert input_assets[0]["source_uri"].startswith("logs/terminal-")
    assert input_assets[0]["working_directory_redacted"] is True
    manifest = collect_evidence_assets(ProjectRef(project.path, project.name))
    asset = manifest["assets"][0]
    assert asset["evidence_type"] == "terminal_log_capture"
    assert asset["path"].startswith("logs/terminal-")
    assert asset["command_status"] == "captured"
    assert asset["command_exit_code"] == 0
    assert asset["working_directory_redacted"] is True
    assert "real-secret" not in asset["command_redacted"]

    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffmpeg",
    )
    monkeypatch.setattr("packages.core.evidence_assets.subprocess.run", fake_run)
    updated = materialize_evidence_clips(ProjectRef(project.path, project.name), manifest)
    replay_asset = updated["assets"][0]
    assert replay_asset["evidence_clip_status"] == "generated"
    assert replay_asset["evidence_clip_render_source"] == "dynamic_terminal_replay"
    replay_text = (
        project.path
        / "assets"
        / "evidence"
        / "clips"
        / f"{replay_asset['id']}.txt"
    ).read_text(encoding="utf-8")
    assert "real-secret" not in replay_text
    assert "API_KEY=***" in replay_text
    assert commands


def test_cli_ingest_command_preserves_nonzero_exit_as_terminal_evidence(tmp_path):
    project = init_project(tmp_path / "command-fail-evidence", "项目")
    command = f"{sys.executable} -c \"import sys; print('TOKEN=bad-secret'); sys.exit(7)\""

    result = runner.invoke(
        app,
        [
            "ingest",
            "command",
            str(project.path),
            "--command",
            command,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "bad-secret" not in result.output
    payload = json.loads(result.output)
    assert payload["command_status"] == "captured_nonzero_exit"
    assert payload["command_exit_code"] == 7
    log_text = (project.path / payload["log_path"]).read_text(encoding="utf-8")
    assert "bad-secret" not in log_text
    assert "TOKEN=***" in log_text
    manifest = collect_evidence_assets(ProjectRef(project.path, project.name))
    assert manifest["assets"][0]["evidence_type"] == "terminal_log_capture"


def test_cli_ingest_command_records_terminal_video_when_cli_configured(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "command-recording-evidence", "项目")
    recorder = tmp_path / "fake-terminal-recorder"
    recorder.write_text("#!/bin/sh\nprintf mp4 > \"$2\"\n", encoding="utf-8")
    recorder.chmod(0o755)
    monkeypatch.setenv("LINGJIAN_TERMINAL_RECORD_CLI", str(recorder))
    _patch_cli_recording_probe(monkeypatch)
    command = f"{sys.executable} -c \"print('TOKEN=real-secret')\""

    result = runner.invoke(
        app,
        [
            "ingest",
            "command",
            str(project.path),
            "--command",
            command,
            "--role",
            "terminal",
            "--record",
            "--scene-id",
            "s4",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "real-secret" not in result.output
    payload = json.loads(result.output)
    assert payload["recording_status"] == "captured"
    assert payload["recording_path"].startswith("assets/evidence/videos/terminal-")
    assert payload["publish_grade_visual_candidate"] is True
    assert payload["source_video_probe_status"] == "verifiable"
    assert payload["source_video_duration_sec"] == 2.4
    run_command = f"uv run lj run {shlex.quote(str(project.path))} --release --json"
    assert payload["next_action_zh"].startswith("已获得可验证的终端动态录屏")
    assert payload["next_command"] == run_command
    assert (project.path / payload["recording_path"]).exists()
    input_assets = json.loads((project.path / "assets" / "input_assets.json").read_text())
    assert input_assets[0]["recording_opt_in"] is True
    assert input_assets[0]["recording_evidence_type"] == "terminal_recording_capture"
    assert input_assets[0]["target_scene_id"] == "s4"
    assert input_assets[0]["source_video_duration_sec"] == 2.4
    assert input_assets[0]["next_command"] == run_command
    _patch_evidence_recording_ffprobe(monkeypatch)
    manifest = collect_evidence_assets(ProjectRef(project.path, project.name))
    by_type = {asset["evidence_type"]: asset for asset in manifest["assets"]}
    assert by_type["terminal_log_capture"]["path"].startswith("logs/terminal-")
    input_asset = next(asset for asset in manifest["assets"] if asset["id"] == "input-01")
    assert input_asset["next_command"] == run_command
    recording_asset = by_type["terminal_recording_capture"]
    assert recording_asset["path"] == payload["recording_path"]
    assert recording_asset["role"] == "terminal_recording"
    assert recording_asset["recording_status"] == "captured"
    assert recording_asset["source_video_probe_status"] == "verifiable"
    assert recording_asset["source_video_duration_sec"] == 2.4
    assert recording_asset["evidence_clip_duration_sec"] == 2.4
    assert recording_asset["publish_grade_visual_candidate"] is True
    assert recording_asset["target_scene_id"] == "s4"
    assert recording_asset["next_command"] == run_command


def test_cli_ingest_command_records_terminal_video_with_default_adapter(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "command-recording-default", "项目")
    monkeypatch.delenv("LINGJIAN_TERMINAL_RECORD_CLI", raising=False)
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.shutil.which",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None,
    )

    def fake_run(command, **kwargs):
        if len(command) > 1 and str(command[1]).endswith("terminal_record_cli.py"):
            output = Path(command[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"mp4")
            return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="TOKEN=real-secret\n",
            stderr="",
        )

    monkeypatch.setattr("apps.cli.lingjian_cli.main.subprocess.run", fake_run)
    _patch_cli_recording_probe(monkeypatch)

    result = runner.invoke(
        app,
        [
            "ingest",
            "command",
            str(project.path),
            "--command",
            f"{sys.executable} -c \"print('TOKEN=real-secret')\"",
            "--role",
            "terminal",
            "--record",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "real-secret" not in result.output
    payload = json.loads(result.output)
    assert payload["recording_status"] == "captured"
    assert payload["recording_tool"] == "terminal-output-video"
    assert payload["recording_path"].startswith("assets/evidence/videos/terminal-")
    assert payload["publish_grade_visual_candidate"] is True
    assert (project.path / payload["recording_path"]).exists()


def test_cli_ingest_command_recording_probe_failure_is_not_publish_candidate(
    tmp_path,
    monkeypatch,
):
    project = init_project(tmp_path / "command-recording-probe-failed", "项目")
    recorder = tmp_path / "fake-terminal-recorder"
    recorder.write_text("#!/bin/sh\nprintf not-video > \"$2\"\n", encoding="utf-8")
    recorder.chmod(0o755)
    monkeypatch.setenv("LINGJIAN_TERMINAL_RECORD_CLI", str(recorder))
    _patch_cli_recording_probe(monkeypatch, has_video_stream=False)

    result = runner.invoke(
        app,
        [
            "ingest",
            "command",
            str(project.path),
            "--command",
            f"{sys.executable} -c \"print('ok')\"",
            "--role",
            "terminal",
            "--record",
            "--scene-id",
            "s4",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["recording_status"] == "not_verifiable"
    assert payload["publish_grade_visual_candidate"] is False
    assert payload["source_video_probe_status"] == "not_verifiable"
    assert payload["next_action_zh"].startswith("还没有形成可发布的终端动态录屏")
    assert "uv run lj ingest video" in payload["next_command"]
    assert "--role terminal_recording" in payload["next_command"]
    assert "--scene-id s4" in payload["next_command"]
    input_assets = json.loads((project.path / "assets" / "input_assets.json").read_text())
    assert input_assets[0]["target_scene_id"] == "s4"
    assert input_assets[0]["next_command"] == payload["next_command"]
    _patch_evidence_recording_ffprobe(monkeypatch, has_video_stream=False)
    manifest = collect_evidence_assets(ProjectRef(project.path, project.name))
    by_type = {asset["evidence_type"]: asset for asset in manifest["assets"]}
    input_asset = next(asset for asset in manifest["assets"] if asset["id"] == "input-01")
    assert input_asset["next_command"] == payload["next_command"]
    recording_asset = by_type["terminal_recording_capture"]
    assert recording_asset["recording_status"] == "not_verifiable"
    assert recording_asset["source_video_probe_status"] == "not_verifiable"
    assert recording_asset["source_video_has_video_stream"] is False
    assert recording_asset["publish_grade_visual_candidate"] is False
    assert recording_asset["next_command"] == payload["next_command"]


def test_cli_ingest_command_recording_unavailable_does_not_fake_asset(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "command-recording-unavailable", "项目")
    monkeypatch.delenv("LINGJIAN_TERMINAL_RECORD_CLI", raising=False)
    monkeypatch.setattr("apps.cli.lingjian_cli.main.shutil.which", lambda name: None)

    result = runner.invoke(
        app,
        [
            "ingest",
            "command",
            str(project.path),
            "--command",
            f"{sys.executable} -c \"print('ok')\"",
            "--record",
            "--scene-id",
            "s4",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["recording_status"] == "unavailable"
    assert "recording_path" not in payload
    assert payload["next_action_zh"].startswith("还没有形成可发布的终端动态录屏")
    assert "uv run lj ingest video" in payload["next_command"]
    assert "--role terminal_recording" in payload["next_command"]
    assert "--scene-id s4" in payload["next_command"]
    input_assets = json.loads((project.path / "assets" / "input_assets.json").read_text())
    assert input_assets[0]["recording_opt_in"] is True
    assert "recording_path" not in input_assets[0]
    assert input_assets[0]["target_scene_id"] == "s4"
    assert input_assets[0]["next_command"] == payload["next_command"]
    manifest = collect_evidence_assets(ProjectRef(project.path, project.name))
    evidence_types = {asset["evidence_type"] for asset in manifest["assets"]}
    assert "terminal_log_capture" in evidence_types
    assert "terminal_recording_capture" not in evidence_types
    input_asset = next(asset for asset in manifest["assets"] if asset["id"] == "input-01")
    assert input_asset["next_command"] == payload["next_command"]


def test_cli_ingest_codex_records_operation_video_when_cli_configured(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "codex-operation-recording", "项目")
    recorder = tmp_path / "fake-codex-recorder"
    recorder.write_text("#!/bin/sh\nprintf mp4 > \"$2\"\n", encoding="utf-8")
    recorder.chmod(0o755)
    monkeypatch.setenv("LINGJIAN_CODEX_RECORD_CLI", str(recorder))
    _patch_cli_recording_probe(monkeypatch)

    result = runner.invoke(
        app,
        [
            "ingest",
            "codex",
            str(project.path),
            "--task",
            "展示 lingjian-video 进入分镜三审 TOKEN=real-secret",
            "--scene-id",
            "s1",
            "--allow-screen-recording",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "real-secret" not in result.output
    payload = json.loads(result.output)
    assert payload["recording_status"] == "captured"
    assert payload["recording_path"].startswith("assets/evidence/videos/codex_operation-")
    assert payload["publish_grade_visual_candidate"] is True
    assert payload["source_video_probe_status"] == "verifiable"
    assert payload["source_video_duration_sec"] == 2.4
    assert payload["next_command"] == f"uv run lj run {project.path} --release --json"
    assert payload["screen_recording_consent_required"] is True
    assert payload["screen_recording_consent"] is True
    assert "当前屏幕没有私密信息" in payload["privacy_notice_zh"]
    assert "重新运行灵剪主线" in payload["next_action_zh"]
    assert (project.path / payload["recording_path"]).exists()
    input_assets = json.loads((project.path / "assets" / "input_assets.json").read_text())
    assert input_assets[0]["type"] == "codex_operation"
    assert input_assets[0]["recording_opt_in"] is True
    assert input_assets[0]["screen_recording_consent"] is True
    assert input_assets[0]["screen_recording_consent_required"] is True
    assert "当前屏幕没有私密信息" in input_assets[0]["privacy_notice_zh"]
    assert input_assets[0]["recording_evidence_type"] == "codex_operation_recording"
    assert input_assets[0]["target_scene_id"] == "s1"
    assert input_assets[0]["recording_task_redacted"].endswith("TOKEN=***")
    assert input_assets[0]["source_video_duration_sec"] == 2.4
    assert input_assets[0]["next_command"] == f"uv run lj run {project.path} --release --json"
    assert "real-secret" not in json.dumps(input_assets, ensure_ascii=False)
    _patch_evidence_recording_ffprobe(monkeypatch)
    manifest = collect_evidence_assets(ProjectRef(project.path, project.name))
    by_type = {asset["evidence_type"]: asset for asset in manifest["assets"]}
    assert by_type["codex_operation_plan"]["task_redacted"].endswith("TOKEN=***")
    recording_asset = by_type["codex_operation_recording"]
    assert recording_asset["path"] == payload["recording_path"]
    assert recording_asset["role"] == "codex_recording"
    assert recording_asset["recording_task_redacted"].endswith("TOKEN=***")
    assert "real-secret" not in json.dumps(recording_asset, ensure_ascii=False)
    assert recording_asset["recording_status"] == "captured"
    assert recording_asset["source_video_probe_status"] == "verifiable"
    assert recording_asset["source_video_duration_sec"] == 2.4
    assert recording_asset["evidence_clip_duration_sec"] == 2.4
    assert recording_asset["publish_grade_visual_candidate"] is True
    assert recording_asset["target_scene_id"] == "s1"
    assert recording_asset["next_command"] == payload["next_command"]
    assert recording_asset["screen_recording_consent_required"] is True
    assert recording_asset["screen_recording_consent"] is True
    assert "当前屏幕没有私密信息" in recording_asset["privacy_notice_zh"]
    materialized = materialize_evidence_clips(ProjectRef(project.path, project.name), manifest)
    scene_refs = evidence_assets_for_scene(
        materialized,
        expected_real_evidence=["Codex app 操作画面"],
        asset_recipe_id="codex_prompt_or_reconstructed_ui",
        scene_id="s1",
        project=ProjectRef(project.path, project.name),
    )
    assert len(scene_refs) == 1
    scene_ref = scene_refs[0]
    assert scene_ref["evidence_type"] == "codex_operation_recording"
    assert scene_ref["target_scene_id"] == "s1"
    assert scene_ref["recording_status"] == "captured"
    assert scene_ref["source_video_probe_status"] == "verifiable"
    assert scene_ref["source_video_has_video_stream"] is True
    assert scene_ref["source_video_duration_sec"] == 2.4
    assert scene_ref["evidence_clip_duration_sec"] == 2.4
    assert scene_ref["screen_recording_consent_required"] is True
    assert scene_ref["screen_recording_consent"] is True
    assert "当前屏幕没有私密信息" in scene_ref["privacy_notice_zh"]
    assert scene_ref["recording_task_redacted"].endswith("TOKEN=***")
    assert scene_ref["next_command"] == "uv run lj run <project> --release --json"
    assert str(project.path) not in json.dumps(scene_ref, ensure_ascii=False)
    assert "real-secret" not in json.dumps(scene_ref, ensure_ascii=False)


def test_cli_ingest_video_records_redacted_task_intent_for_manual_codex_recording(
    tmp_path, monkeypatch
):
    project = tmp_path / "手动Codex录屏项目"
    source_video = tmp_path / "codex.mp4"
    source_video.write_bytes(b"mp4")
    runner.invoke(app, ["init", str(project), "--name", "手动Codex录屏项目", "--json"])
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"streams":[{"codec_type":"video"}],"format":{"duration":"4.2"}}',
            stderr="",
        )

    monkeypatch.setattr("apps.cli.lingjian_cli.main.subprocess.run", fake_run)

    result = runner.invoke(
        app,
        [
            "ingest",
            "video",
            str(project),
            "--file",
            str(source_video),
            "--role",
            "codex_recording",
            "--scene-id",
            "s3",
            "--task",
            "展示宿主插件生成每镜动态资产 TOKEN=real-secret",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "real-secret" not in result.output
    payload = json.loads(result.output)
    assert payload["recording_task_redacted"].endswith("TOKEN=***")
    assert payload["screen_recording_consent_required"] is True
    assert payload["screen_recording_consent"] is True
    assert "用户已提供本地屏幕录屏文件" in payload["privacy_notice_zh"]
    input_assets = json.loads(
        (project / "assets" / "input_assets.json").read_text(encoding="utf-8")
    )
    assert input_assets[0]["recording_task_redacted"].endswith("TOKEN=***")
    assert input_assets[0]["screen_recording_consent_required"] is True
    assert input_assets[0]["screen_recording_consent"] is True
    assert "用户已提供本地屏幕录屏文件" in input_assets[0]["privacy_notice_zh"]
    assert "real-secret" not in json.dumps(input_assets, ensure_ascii=False)
    manifest = collect_evidence_assets(ProjectRef(project, project.name))
    asset = manifest["assets"][0]
    assert asset["evidence_type"] == "codex_operation_recording"
    assert asset["recording_task_redacted"].endswith("TOKEN=***")
    assert asset["target_scene_id"] == "s3"
    assert asset["source_video_duration_sec"] == 4.2
    assert asset["screen_recording_consent_required"] is True
    assert asset["screen_recording_consent"] is True
    assert "用户已提供本地屏幕录屏文件" in asset["privacy_notice_zh"]
    assert "real-secret" not in json.dumps(asset, ensure_ascii=False)


def test_cli_ingest_codex_without_consent_records_task_only(tmp_path, monkeypatch):
    project = init_project(tmp_path / "codex-operation-no-consent", "项目")
    recorder = tmp_path / "fake-codex-recorder"
    recorder.write_text("#!/bin/sh\nprintf mp4 > \"$2\"\n", encoding="utf-8")
    recorder.chmod(0o755)
    monkeypatch.setenv("LINGJIAN_CODEX_RECORD_CLI", str(recorder))
    _patch_cli_recording_probe(monkeypatch)

    result = runner.invoke(
        app,
        [
            "ingest",
            "codex",
            str(project.path),
            "--task",
            "展示灵剪进入能力门诊 TOKEN=real-secret",
            "--scene-id",
            "s1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "real-secret" not in result.output
    payload = json.loads(result.output)
    assert payload["recording_status"] == "pending_user_consent"
    assert payload["recording_opt_in"] is False
    assert payload["screen_recording_consent"] is False
    assert "--allow-screen-recording" in payload["next_command"]
    assert "TOKEN=***" in payload["next_command"]
    assert payload["screen_recording_consent_required"] is True
    assert "当前屏幕没有私密信息" in payload["privacy_notice_zh"]
    assert payload["manual_fallback_command"].startswith("uv run lj ingest video ")
    assert "--role codex_recording" in payload["manual_fallback_command"]
    assert "--scene-id s1" in payload["manual_fallback_command"]
    assert "当前只登记了 Codex 操作录屏任务" in payload["next_action_zh"]
    assert "recording_path" not in payload
    input_assets = json.loads((project.path / "assets" / "input_assets.json").read_text())
    assert input_assets[0]["recording_opt_in"] is False
    assert input_assets[0]["screen_recording_consent"] is False
    assert "--allow-screen-recording" in input_assets[0]["next_command"]
    assert input_assets[0]["screen_recording_consent_required"] is True
    assert "--scene-id s1" in input_assets[0]["manual_fallback_command"]
    assert "real-secret" not in json.dumps(input_assets, ensure_ascii=False)
    assert "recording_path" not in input_assets[0]
    manifest = collect_evidence_assets(ProjectRef(project.path, project.name))
    by_type = {asset["evidence_type"]: asset for asset in manifest["assets"]}
    evidence_types = set(by_type)
    assert "codex_operation_plan" in evidence_types
    assert "codex_operation_recording" not in evidence_types
    plan_asset = by_type["codex_operation_plan"]
    assert plan_asset["screen_recording_consent_required"] is True
    assert plan_asset["screen_recording_consent"] is False
    assert "当前屏幕没有私密信息" in plan_asset["privacy_notice_zh"]
    assert "--allow-screen-recording" in plan_asset["next_command"]
    assert "--scene-id s1" in plan_asset["manual_fallback_command"]
    assert "real-secret" not in json.dumps(plan_asset, ensure_ascii=False)


def test_evidence_checklist_rebuilds_codex_commands_from_current_scenes(tmp_path):
    project = init_project(tmp_path / "stale-evidence-checklist", "项目")
    visual_plan = {
        "evidence_collection_checklist_v1": {
            "items": [
                {
                    "scene_id": "s1",
                    "suggested_commands": [
                        {
                            "label_zh": "旧命令",
                            "command": "uv run lj ingest codex old --json",
                            "note_zh": "旧说明",
                        }
                    ],
                }
            ]
        },
        "scenes": [
            {
                "scene_id": "s1",
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "director_review_sheet_v2": {"scene_number": 1},
                "asset_diagnosis": {
                    "asset_status": "blocked_missing_matching_evidence_video",
                    "missing_evidence_types": [
                        "codex_operation_recording",
                        "screen_recording_capture",
                    ],
                    "missing_evidence_action_zh": "录制 Codex app 触发过程。",
                    "next_action_zh": "请录制 Codex app 触发过程。",
                },
            }
        ],
    }

    markdown = _write_evidence_collection_checklist(project, visual_plan)

    assert "--allow-screen-recording" in markdown
    assert "确认当前屏幕可被录制且没有隐私内容" in markdown
    assert "uv run lj ingest codex old --json" not in markdown
    checklist_item = visual_plan["evidence_collection_checklist_v1"]["items"][0]
    assert checklist_item["screen_recording_consent_required"] is True
    assert "当前屏幕没有私密信息" in checklist_item["privacy_notice_zh"]
    assert checklist_item["manual_fallback_command"].startswith(
        "uv run lj ingest video "
    )
    assert "--task" in checklist_item["manual_fallback_command"]
    assert "展示在 Codex app 中一句话触发 lingjian-video" in checklist_item[
        "manual_fallback_command"
    ]
    assert "--role codex_recording" in checklist_item["manual_fallback_command"]


def test_director_review_recovery_persists_refreshed_evidence_checklist(tmp_path):
    project = init_project(tmp_path / "stale-evidence-checklist-persisted", "项目")
    visual_plan = {
        "id": "visuals",
        "evidence_collection_checklist_v1": {
            "items": [
                {
                    "scene_id": "s1",
                    "suggested_commands": [
                        {
                            "label_zh": "旧命令",
                            "command": "uv run lj ingest codex old --json",
                            "note_zh": "旧说明",
                        }
                    ],
                }
            ]
        },
        "scenes": [
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "narration_text": "一句话触发灵剪。",
                "visual_prompt": "Codex app 里一句话触发灵剪。",
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "director_review_sheet_v2": {
                    "scene_number": 1,
                    "narration_text": "一句话触发灵剪。",
                    "visual_content": "Codex app 里一句话触发灵剪。",
                },
                "asset_diagnosis": {
                    "asset_status": "blocked_missing_matching_evidence_video",
                    "missing_evidence_types": [
                        "codex_operation_recording",
                        "screen_recording_capture",
                    ],
                    "missing_evidence_action_zh": "录制 Codex app 触发过程。",
                    "next_action_zh": "请录制 Codex app 触发过程。",
                },
            }
        ],
    }
    write_artifact(project, "visuals", visual_plan)

    response = _director_review_response(project, regenerate_from_visual_plan=True)

    assert response is not None
    persisted = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    commands = [
        command["command"]
        for item in persisted["evidence_collection_checklist_v1"]["items"]
        for command in item["suggested_commands"]
    ]
    checklist_item = persisted["evidence_collection_checklist_v1"]["items"][0]
    assert any("--allow-screen-recording" in command for command in commands)
    assert all("uv run lj ingest codex old --json" not in command for command in commands)
    assert checklist_item["screen_recording_consent_required"] is True
    assert "当前屏幕没有私密信息" in checklist_item["privacy_notice_zh"]
    assert checklist_item["manual_fallback_command"].startswith(
        "uv run lj ingest video "
    )
    assert "--task" in checklist_item["manual_fallback_command"]
    assert "展示在 Codex app 中一句话触发 lingjian-video" in checklist_item[
        "manual_fallback_command"
    ]


def test_cli_ingest_codex_recording_unavailable_does_not_fake_asset(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "codex-operation-unavailable", "项目")
    monkeypatch.delenv("LINGJIAN_CODEX_RECORD_CLI", raising=False)
    monkeypatch.setattr("apps.cli.lingjian_cli.main.shutil.which", lambda name: None)

    result = runner.invoke(
        app,
        [
            "ingest",
            "codex",
            str(project.path),
            "--task",
            "展示灵剪导出包",
            "--allow-screen-recording",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["recording_status"] == "unavailable"
    assert "recording_path" not in payload
    assert payload["screen_recording_consent_required"] is True
    assert payload["screen_recording_consent"] is True
    assert "当前屏幕没有私密信息" in payload["privacy_notice_zh"]
    assert payload["manual_fallback_command"].startswith("uv run lj ingest video ")
    assert "--role codex_recording" in payload["manual_fallback_command"]
    assert "--task" in payload["manual_fallback_command"]
    assert "展示灵剪导出包" in payload["manual_fallback_command"]
    assert payload["next_command"] == payload["manual_fallback_command"]
    input_assets = json.loads((project.path / "assets" / "input_assets.json").read_text())
    assert input_assets[0]["type"] == "codex_operation"
    assert input_assets[0]["recording_opt_in"] is True
    assert input_assets[0]["screen_recording_consent"] is True
    assert input_assets[0]["screen_recording_consent_required"] is True
    assert input_assets[0]["next_command"] == payload["manual_fallback_command"]
    assert input_assets[0]["manual_fallback_command"] == payload["manual_fallback_command"]
    assert "recording_path" not in input_assets[0]
    manifest = collect_evidence_assets(ProjectRef(project.path, project.name))
    by_type = {asset["evidence_type"]: asset for asset in manifest["assets"]}
    evidence_types = set(by_type)
    assert "codex_operation_plan" in evidence_types
    assert "codex_operation_recording" not in evidence_types
    plan_asset = by_type["codex_operation_plan"]
    assert plan_asset["screen_recording_consent_required"] is True
    assert plan_asset["screen_recording_consent"] is True
    assert plan_asset["next_command"] == payload["manual_fallback_command"]
    assert plan_asset["manual_fallback_command"] == payload["manual_fallback_command"]


def test_cli_ingest_codex_recording_probe_failure_records_recovery_metadata(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "codex-operation-probe-failed", "项目")
    recorder = tmp_path / "fake-codex-recorder"
    recorder.write_text("#!/bin/sh\nprintf not-video > \"$2\"\n", encoding="utf-8")
    recorder.chmod(0o755)
    monkeypatch.setenv("LINGJIAN_CODEX_RECORD_CLI", str(recorder))
    _patch_cli_recording_probe(monkeypatch, has_video_stream=False)

    result = runner.invoke(
        app,
        [
            "ingest",
            "codex",
            str(project.path),
            "--task",
            "展示灵剪导出包 TOKEN=real-secret",
            "--scene-id",
            "s2",
            "--allow-screen-recording",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "real-secret" not in result.output
    payload = json.loads(result.output)
    assert payload["recording_status"] == "not_verifiable"
    assert payload["publish_grade_visual_candidate"] is False
    assert payload["source_video_has_video_stream"] is False
    assert payload["screen_recording_consent_required"] is True
    assert payload["screen_recording_consent"] is True
    assert "当前屏幕没有私密信息" in payload["privacy_notice_zh"]
    assert payload["manual_fallback_command"].startswith("uv run lj ingest video ")
    assert "--role codex_recording" in payload["manual_fallback_command"]
    assert "--scene-id s2" in payload["manual_fallback_command"]
    assert "--task" in payload["manual_fallback_command"]
    assert "TOKEN=***" in payload["manual_fallback_command"]
    assert payload["next_command"] == payload["manual_fallback_command"]
    input_assets = json.loads((project.path / "assets" / "input_assets.json").read_text())
    assert input_assets[0]["recording_task_redacted"].endswith("TOKEN=***")
    assert input_assets[0]["screen_recording_consent_required"] is True
    assert input_assets[0]["manual_fallback_command"] == payload["manual_fallback_command"]
    assert "real-secret" not in json.dumps(input_assets, ensure_ascii=False)
    _patch_evidence_recording_ffprobe(monkeypatch, has_video_stream=False)
    manifest = collect_evidence_assets(ProjectRef(project.path, project.name))
    by_type = {asset["evidence_type"]: asset for asset in manifest["assets"]}
    recording_asset = by_type["codex_operation_recording"]
    assert recording_asset["recording_status"] == "not_verifiable"
    assert recording_asset["screen_recording_consent_required"] is True
    assert recording_asset["screen_recording_consent"] is True
    assert recording_asset["next_command"] == payload["manual_fallback_command"]
    assert recording_asset["manual_fallback_command"] == payload["manual_fallback_command"]
    assert "real-secret" not in json.dumps(recording_asset, ensure_ascii=False)
    scene_refs = evidence_assets_for_scene(
        manifest,
        expected_real_evidence=["Codex app 操作画面"],
        asset_recipe_id="codex_prompt_or_reconstructed_ui",
        scene_id="s2",
        project=ProjectRef(project.path, project.name),
    )
    assert len(scene_refs) == 1
    assert scene_refs[0]["recording_status"] == "not_verifiable"
    assert scene_refs[0]["next_command"].startswith("uv run lj ingest video <project>")
    assert scene_refs[0]["manual_fallback_command"].startswith(
        "uv run lj ingest video <project>"
    )
    assert "TOKEN=***" in scene_refs[0]["manual_fallback_command"]
    assert str(project.path) not in json.dumps(scene_refs, ensure_ascii=False)
    assert "real-secret" not in json.dumps(scene_refs, ensure_ascii=False)


def test_codex_record_command_prefix_uses_macos_screencapture_adapter(monkeypatch):
    monkeypatch.delenv("LINGJIAN_CODEX_RECORD_CLI", raising=False)
    monkeypatch.setattr("apps.cli.lingjian_cli.main.sys.platform", "darwin")
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"screencapture", "ffprobe"} else None,
    )

    command = _codex_record_command_prefix()

    assert command[0] == sys.executable
    assert command[-1].endswith("scripts/providers/macos_screen_record_cli.py")


def test_visuals_collects_open_source_evidence_without_binding_mismatched_assets(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "visual-evidence-assets", "项目")
    readme = tmp_path / "README.md"
    readme.write_text("# 灵剪\n\n安装入口和 GitHub star CTA。", encoding="utf-8")
    ingest = runner.invoke(
        app,
        ["ingest", "text", str(project.path), "--file", str(readme), "--json"],
    )
    assert ingest.exit_code == 0
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "profile": "open_source_project_intro",
            "scenes": [
                {
                    "id": "s1",
                    "role": "proof",
                    "narration_text": "灵剪把脚本、配音、画面和 QA 留成证据。",
                    "duration_sec": 2.0,
                }
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "volcengine_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )

    def fake_run(command, **kwargs):
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffmpeg",
    )
    monkeypatch.setattr("packages.core.evidence_assets.subprocess.run", fake_run)

    result = runner.invoke(app, ["visuals", str(project.path), "--engine", "hyperframes", "--json"])

    assert result.exit_code == 0
    evidence_path = project.path / "assets" / "evidence" / "evidence_assets.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    scene = payload["scenes"][0]
    assert "readme_install_entry" in evidence["evidence_types"]
    assert "script_artifact" in evidence["evidence_types"]
    assert "voice_plan_artifact" in evidence["evidence_types"]
    assert payload["evidence_assets"]["count"] >= 3
    assert scene["evidence_asset_refs"] == []
    assert scene["generator"] == "hyperframes"
    assert scene["asset_path"].startswith("assets/scenes/")
    assert scene["asset_diagnosis"]["asset_status"] == (
        "blocked_missing_matching_evidence_video"
    )
    assert scene["asset_diagnosis"]["publish_grade_visual"] is False
    assert scene["asset_diagnosis"]["missing_evidence_types"] == [
        "terminal_recording_capture",
        "screen_recording_capture",
    ]
    assert scene["evidence_video_refs"] == []


def test_visuals_does_not_route_web_recording_to_unmatched_evidence_scene(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "visual-web-recording-mismatch", "项目")
    video = project.path / "assets" / "web_recordings" / "github.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"mp4")
    input_assets = project.path / "assets" / "input_assets.json"
    input_assets.parent.mkdir(parents=True, exist_ok=True)
    input_assets.write_text(
        json.dumps(
            [
                {
                    "type": "url",
                    "source_uri": "https://github.com/dososo/blcaptain-lingjian-video",
                    "recording_path": "assets/web_recordings/github.mp4",
                    "recording_evidence_type": "web_recording_capture",
                    "recording_role": "github_repo_scroll",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "profile": "open_source_project_intro",
            "scenes": [
                {
                    "id": "s1",
                    "role": "proof",
                    "narration_text": "严格 QA 和 ffprobe 证据让结果可复核。",
                    "duration_sec": 2.0,
                },
                {
                    "id": "s2",
                    "role": "pain",
                    "narration_text": "普通用户卡在素材、配音和发布级质量门之间。",
                    "duration_sec": 2.0,
                }
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "volcengine_tts",
            "provider_is_mock": False,
            "segments": [
                {"scene_id": "s1", "duration_sec": 2.0},
                {"scene_id": "s2", "duration_sec": 2.0},
            ],
        },
    )
    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffprobe",
    )
    monkeypatch.setattr(
        "packages.core.evidence_assets._source_video_is_verifiable",
        lambda ffprobe, path: True,
    )

    result = runner.invoke(app, ["visuals", str(project.path), "--engine", "hyperframes", "--json"])

    assert result.exit_code == 0
    result_payload = json.loads(result.output)
    payload = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    checklist_md = project.path / "artifacts" / "evidence_collection_checklist.md"
    scene = payload["scenes"][0]
    pain_scene = payload["scenes"][1]
    assert result_payload["evidence_collection_checklist_artifact"] == (
        "artifacts/evidence_collection_checklist.md"
    )
    assert "真实动态证据素材采集清单 v1" in result_payload[
        "evidence_collection_checklist_markdown"
    ]
    assert checklist_md.exists()
    checklist_text = checklist_md.read_text(encoding="utf-8")
    assert "QA/strict" in checklist_text
    assert "推荐采集命令" in checklist_text
    assert "uv run lj ingest command" in checklist_text
    assert "--record --scene-id s1 --json" in checklist_text
    assert payload["evidence_collection_checklist_v1"]["total"] == 1
    checklist_item = payload["evidence_collection_checklist_v1"]["items"][0]
    assert "uv run lj ingest video" in checklist_item["manual_fallback_command"]
    assert "--role terminal_recording" in checklist_item["manual_fallback_command"]
    assert "--scene-id s1" in checklist_item["manual_fallback_command"]
    assert "--task" in checklist_item["manual_fallback_command"]
    commands = [
        item["command"]
        for item in checklist_item["suggested_commands"]
    ]
    assert any(
        "uv run lj ingest command" in command
        and "uv run lj qa" in command
        and "--record --scene-id s1 --json" in command
        for command in commands
    )
    assert any(
        "uv run lj ingest video" in command
        and "--role terminal_recording" in command
        and "--scene-id s1" in command
        and "--task" in command
        and command.endswith("--json")
        for command in commands
    )
    assert scene["asset_recipe_id"] == "qa_report_capture"
    assert not any(
        ref["evidence_type"] == "web_recording_capture"
        and ref["evidence_clip_status"] == "captured"
        for ref in scene["evidence_video_refs"]
    )
    assert scene["generator"] == "hyperframes"
    assert scene["asset_path"] == "assets/scenes/s1.mp4"
    assert scene.get("asset_origin") != "evidence_dynamic_clip"
    assert scene["asset_diagnosis"]["asset_status"] == (
        "blocked_missing_matching_evidence_video"
    )
    assert scene["asset_diagnosis"]["publish_grade_visual"] is False
    assert scene["asset_diagnosis"]["missing_evidence_types"] == [
        "terminal_recording_capture",
        "screen_recording_capture",
    ]
    assert "QA/strict" in scene["asset_diagnosis"]["missing_evidence_action_zh"]
    assert scene["engine_policy"]["publish_grade_candidate"] is False
    assert scene["asset_strategy_v2"]["current_asset_status"] == (
        "blocked_missing_matching_evidence_video"
    )
    assert scene["director_review_sheet_v2"]["asset_status"]["asset_status"] == (
        "blocked_missing_matching_evidence_video"
    )
    assert pain_scene["asset_recipe_id"]
    assert pain_scene["generator"] == "hyperframes"
    assert pain_scene["asset_path"] == "assets/scenes/s2.mp4"
    assert pain_scene["asset_diagnosis"]["asset_status"] == "pending_dynamic_generation"
    assert payload["asset_diagnosis_summary"]["non_publish_grade_count"] == 1
    assert "第 1 镜" in payload["asset_diagnosis_summary"]["single_next_action_zh"]


def test_visuals_requires_codex_recording_for_open_source_hook_scene(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "visual-codex-hook-evidence", "项目")
    video = project.path / "assets" / "web_recordings" / "github.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"mp4")
    input_assets = project.path / "assets" / "input_assets.json"
    input_assets.parent.mkdir(parents=True, exist_ok=True)
    input_assets.write_text(
        json.dumps(
            [
                {
                    "type": "url",
                    "source_uri": "https://github.com/dososo/blcaptain-lingjian-video",
                    "recording_path": "assets/web_recordings/github.mp4",
                    "recording_evidence_type": "web_recording_capture",
                    "recording_role": "github_repo_scroll",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "profile": "open_source_project_intro",
            "scenes": [
                {
                    "id": "s1",
                    "role": "hook",
                    "narration_text": "在 Codex 里一句话,灵剪就把短视频生产线拉起来。",
                    "duration_sec": 2.0,
                }
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "volcengine_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )
    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffprobe",
    )
    monkeypatch.setattr(
        "packages.core.evidence_assets._source_video_is_verifiable",
        lambda ffprobe, path: True,
    )

    result = runner.invoke(app, ["visuals", str(project.path), "--engine", "hyperframes", "--json"])

    assert result.exit_code == 0
    result_payload = json.loads(result.output)
    payload = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    checklist_md = project.path / "artifacts" / "evidence_collection_checklist.md"
    scene = payload["scenes"][0]
    assert result_payload["evidence_collection_checklist_artifact"] == (
        "artifacts/evidence_collection_checklist.md"
    )
    assert "Codex app" in result_payload["evidence_collection_checklist_markdown"]
    assert checklist_md.exists()
    checklist_text = checklist_md.read_text(encoding="utf-8")
    assert "一句话触发 lingjian-video" in checklist_text
    assert "推荐采集命令" in checklist_text
    assert "uv run lj ingest codex" in checklist_text
    assert "--scene-id s1 --json" in checklist_text
    assert payload["evidence_collection_checklist_v1"]["total"] == 1
    commands = [
        item["command"]
        for item in payload["evidence_collection_checklist_v1"]["items"][0][
            "suggested_commands"
        ]
    ]
    assert any(
        "uv run lj ingest codex" in command
        and "--task" in command
        and "--scene-id s1 --json" in command
        for command in commands
    )
    assert any(
        "uv run lj ingest video" in command
        and "--role codex_recording" in command
        and "--scene-id s1" in command
        and "--task" in command
        and "展示在 Codex app 中一句话触发 lingjian-video" in command
        and command.endswith("--json")
        for command in commands
    )
    assert scene["asset_recipe_id"] == "codex_prompt_or_reconstructed_ui"
    assert scene["generator"] == "hyperframes"
    assert scene["asset_diagnosis"]["asset_status"] == (
        "blocked_missing_matching_evidence_video"
    )
    assert scene["asset_diagnosis"]["missing_evidence_types"] == [
        "codex_operation_recording",
        "screen_recording_capture",
    ]
    assert "Codex app" in scene["asset_diagnosis"]["missing_evidence_action_zh"]
    assert scene["director_review_sheet_v2"]["asset_status"]["asset_status"] == (
        "blocked_missing_matching_evidence_video"
    )
    assert payload["asset_diagnosis_summary"]["non_publish_grade_count"] == 1
    assert "第 1 镜" in payload["asset_diagnosis_summary"]["single_next_action_zh"]


def test_visuals_respects_project_no_recording_boundary(tmp_path):
    project = init_project(tmp_path / "visual-no-recording-boundary", "项目")
    input_assets = project.path / "assets" / "input_assets.json"
    input_assets.parent.mkdir(parents=True, exist_ok=True)
    input_assets.write_text(
        json.dumps(
            [
                {
                    "type": "text",
                    "text": (
                        "不使用录屏素材。没有视频素材时,画面先走动态图形流程、"
                        "状态卡片、界面示意和检查清单。"
                    ),
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {
                    "id": "s1",
                    "role": "proof",
                    "narration_text": "最后检查字幕、声音、画面和导出文件能不能正式发。",
                    "subtitle_text": "发布前检查",
                    "visual_beat": "检查墙全屏展开,字幕、声音、画面和导出文件四项依次通过或阻断。",
                    "duration_sec": 5,
                }
            ],
        },
    )

    result = runner.invoke(
        app,
        [
            "visuals",
            str(project.path),
            "--engine",
            "hyperframes",
            "--ratio",
            "16:9",
            "--platform",
            "douyin_xiaohongshu",
            "--profile",
            "product_intro",
            "--json",
        ],
    )

    assert result.exit_code == 0
    result_payload = json.loads(result.output)
    payload = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    scene = payload["scenes"][0]
    assert payload["ratio"] == "16:9"
    assert payload["profile_preset"]["ratio"] == "16:9"
    assert payload["profile_preset"]["platform"] == "douyin_xiaohongshu"
    assert payload["profile_preset"]["recording_assets_allowed"] is False
    assert not any("录屏" in item for item in payload["profile_preset"]["visual_types"])
    assert scene["visual_prompt"].startswith("为横屏短视频生成一镜全屏画面。")
    assert "竖屏短视频" not in scene["visual_prompt"]
    assert scene["brief"]["profile"]["ratio"] == "16:9"
    assert scene["brief"]["profile"]["platform"] == "douyin_xiaohongshu"
    assert scene["brief"]["profile"]["recording_assets_allowed"] is False
    assert not any("录屏" in item for item in scene["brief"]["profile"]["visual_types"])
    assert scene["on_screen_text"] == "发布前检查"
    assert scene["director_board"]["visual_content"] == (
        "检查墙全屏展开,字幕、声音、画面和导出文件四项依次通过或阻断。"
    )
    assert scene["director_review_sheet_v2"]["visual_content"] == (
        "检查墙全屏展开,字幕、声音、画面和导出文件四项依次通过或阻断。"
    )
    assert "持续运动" in scene["director_board"]["keyframes"][1]["state"]
    assert scene["director_board"]["transition"]["semantic"] == (
        "服务当前脚本节拍,转场动作必须对应本镜画面语义。"
    )
    assert "发布前检查" in scene["director_board"]["transition"]["in"]
    assert "发布前检查" in scene["director_board"]["audio_sfx_notes"]["sfx"]
    assert scene["director_review_sheet_v2"]["transition"]["semantic"] == (
        "服务当前脚本节拍,转场动作必须对应本镜画面语义。"
    )
    assert scene["layout_contract"]["quiet_text_zone"]["y"] == 880
    assert scene["asset_recipe_id"] == "no_recording_dynamic_graphics"
    assert scene["director_board"]["asset_recipe_id"] == "no_recording_dynamic_graphics"
    assert scene["requires_real_evidence_asset"] is False
    assert "qa_report_capture" not in scene["expected_real_evidence"]
    assert "screen_recording_capture" not in scene["expected_real_evidence"]
    assert scene["recording_policy"]["recording_assets_allowed"] is False
    assert scene["asset_diagnosis"]["asset_status"] == (
        "pending_no_recording_dynamic_generation"
    )
    assert scene["asset_diagnosis"]["asset_recipe_id"] == "no_recording_dynamic_graphics"
    assert scene["asset_diagnosis"]["publish_grade_visual"] is False
    assert scene["asset_strategy_v2"]["recording_assets_allowed"] is False
    assert "动态图形" in scene["asset_diagnosis"]["source_zh"]
    assert "不要求录屏" in scene["asset_diagnosis"]["next_action_zh"]
    assert payload["evidence_collection_checklist_v1"]["total"] == 0
    assert "当前没有待采集的匹配证据素材" in result_payload[
        "evidence_collection_checklist_markdown"
    ]
    assert "--allow-screen-recording" not in result_payload[
        "evidence_collection_checklist_markdown"
    ]


def test_script_profile_preset_honors_ratio_and_no_recording_boundary(tmp_path):
    project = init_project(tmp_path / "script-no-recording-ratio", "项目")
    input_assets = project.path / "assets" / "input_assets.json"
    input_assets.parent.mkdir(parents=True, exist_ok=True)
    input_assets.write_text(
        json.dumps(
            [
                {
                    "type": "text",
                    "text": (
                        "画幅:16:9 横屏。不使用屏幕录制素材,不录屏。"
                        "没有视频素材时走动态图形、界面示意和项目 artifact 示意。"
                    ),
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "script",
            str(project.path),
            "--type",
            "product",
            "--platform",
            "douyin_xiaohongshu",
            "--language",
            "zh-CN",
            "--ratio",
            "16:9",
            "--duration",
            "60",
            "--provider",
            "mock",
            "--profile",
            "product_intro",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((project.path / "artifacts" / "script.json").read_text())
    preset = payload["profile_preset"]
    assert preset["ratio"] == "16:9"
    assert preset["platform"] == "douyin_xiaohongshu"
    assert preset["duration_sec"] == 60
    assert preset["scene_count"] == len(payload["scenes"])
    assert preset["recording_assets_allowed"] is False
    assert not any("录屏" in item for item in preset["visual_types"])
    assert "产品界面示意" in preset["visual_types"]


def test_visuals_ignores_scene_bound_evidence_video_for_other_scene(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "visual-ignores-other-scene-evidence", "项目")
    readme = tmp_path / "README.md"
    readme.write_text("# 灵剪\n\n安装入口和 GitHub star CTA。", encoding="utf-8")
    ingest_text = runner.invoke(
        app,
        ["ingest", "text", str(project.path), "--file", str(readme), "--json"],
    )
    assert ingest_text.exit_code == 0
    source_video = tmp_path / "github-recording.mp4"
    source_video.write_bytes(b"mp4")
    ingest_video = runner.invoke(
        app,
        [
            "ingest",
            "video",
            str(project.path),
            "--file",
            str(source_video),
            "--role",
            "screen_recording",
            "--scene-id",
            "s2",
            "--json",
        ],
    )
    assert ingest_video.exit_code == 0
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "profile": "open_source_project_intro",
            "scenes": [
                {
                    "id": "s1",
                    "role": "proof",
                    "narration_text": "灵剪展示 GitHub 仓库和 README 首用路径。",
                    "duration_sec": 2.0,
                }
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "volcengine_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )

    def fake_run(command, **kwargs):
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffmpeg",
    )
    monkeypatch.setattr(
        "packages.core.evidence_assets._source_video_is_verifiable",
        lambda ffprobe, path: True,
    )
    monkeypatch.setattr("packages.core.evidence_assets.subprocess.run", fake_run)

    result = runner.invoke(app, ["visuals", str(project.path), "--engine", "hyperframes", "--json"])

    assert result.exit_code == 0
    payload = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    scene = payload["scenes"][0]
    assert payload["profile"] == "open_source_project_intro"
    assert scene["generator"] == "hyperframes"
    assert scene.get("asset_origin") != "evidence_dynamic_clip"
    assert scene["asset_diagnosis"]["asset_status"] == (
        "blocked_missing_matching_evidence_video"
    )
    assert scene["asset_diagnosis"]["missing_evidence_types"] == [
        "terminal_recording_capture",
        "screen_recording_capture",
    ]
    assert all(
        ref.get("target_scene_id") != "s2"
        for ref in scene["evidence_asset_refs"]
    )
    assert payload["asset_diagnosis_summary"]["non_publish_grade_count"] == 1


def test_evidence_assets_for_scene_excludes_unbound_publish_grade_recordings():
    manifest = {
        "assets": [
            {
                "id": "codex-s1",
                "evidence_type": "codex_operation_recording",
                "path": "assets/evidence/videos/codex-s1.mp4",
                "evidence_clip_path": "assets/evidence/videos/codex-s1.mp4",
                "evidence_clip_status": "captured",
                "publish_grade_evidence_video": True,
                "target_scene_id": "s1",
            },
            {
                "id": "codex-unbound",
                "evidence_type": "codex_operation_recording",
                "path": "assets/evidence/videos/codex-unbound.mp4",
                "evidence_clip_path": "assets/evidence/videos/codex-unbound.mp4",
                "evidence_clip_status": "captured",
                "publish_grade_evidence_video": True,
            },
        ]
    }

    refs = evidence_assets_for_scene(
        manifest,
        expected_real_evidence=["codex_operation_recording"],
        scene_id="s3",
    )

    assert refs == []


def test_evidence_assets_for_scene_rejects_scene_bound_type_mismatched_recording():
    manifest = {
        "assets": [
            {
                "id": "web-s1",
                "evidence_type": "web_recording_capture",
                "path": "assets/evidence/videos/web-s1.mp4",
                "evidence_clip_path": "assets/evidence/videos/web-s1.mp4",
                "evidence_clip_status": "captured",
                "publish_grade_evidence_video": True,
                "target_scene_id": "s1",
            }
        ]
    }

    refs = evidence_assets_for_scene(
        manifest,
        expected_real_evidence=["终端 QA strict 检查"],
        asset_recipe_id="qa_report_capture",
        scene_id="s1",
    )

    assert refs == []


def test_evidence_assets_for_scene_only_prioritizes_publish_grade_within_matching_type():
    manifest = {
        "assets": [
            {
                "id": "web-s1",
                "evidence_type": "web_recording_capture",
                "path": "assets/evidence/videos/web-s1.mp4",
                "evidence_clip_path": "assets/evidence/videos/web-s1.mp4",
                "evidence_clip_status": "captured",
                "publish_grade_evidence_video": True,
                "target_scene_id": "s1",
            },
            {
                "id": "terminal-s1",
                "evidence_type": "terminal_recording_capture",
                "path": "assets/evidence/videos/terminal-s1.mp4",
                "evidence_clip_path": "assets/evidence/videos/terminal-s1.mp4",
                "evidence_clip_status": "captured",
                "target_scene_id": "s1",
            },
        ]
    }

    refs = evidence_assets_for_scene(
        manifest,
        expected_real_evidence=["终端 QA strict 检查"],
        asset_recipe_id="qa_report_capture",
        scene_id="s1",
    )

    assert [ref["id"] for ref in refs] == ["terminal-s1"]
    assert {ref["evidence_type"] for ref in refs} == {"terminal_recording_capture"}


def test_visuals_routes_product_profile_to_user_evidence_video(tmp_path, monkeypatch):
    project = init_project(tmp_path / "product-evidence-video", "项目")
    source_video = tmp_path / "product-ui.mp4"
    source_video.write_bytes(b"mp4")
    ingest = runner.invoke(
        app,
        [
            "ingest",
            "video",
            str(project.path),
            "--file",
            str(source_video),
            "--role",
            "screen_recording",
            "--scene-id",
            "s1",
            "--json",
        ],
    )
    assert ingest.exit_code == 0
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "profile": "product_intro",
            "scenes": [
                {
                    "id": "s1",
                    "role": "proof",
                    "narration_text": "用户看到真实产品界面和核心工作流。",
                    "duration_sec": 2.0,
                }
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "volcengine_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )

    def fake_run(command, **kwargs):
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffmpeg",
    )
    monkeypatch.setattr(
        "packages.core.evidence_assets._source_video_is_verifiable",
        lambda ffprobe, path: True,
    )
    monkeypatch.setattr("packages.core.evidence_assets.subprocess.run", fake_run)

    result = runner.invoke(app, ["visuals", str(project.path), "--engine", "hyperframes", "--json"])

    assert result.exit_code == 0
    payload = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    scene = payload["scenes"][0]
    assert payload["profile"] == "product_intro"
    assert scene["generator"] == "user-asset"
    assert scene["asset_origin"] == "evidence_dynamic_clip"
    assert scene["generation_status"] == "evidence_clip"
    assert scene["asset_path"].startswith("assets/evidence/videos/screen_recording-")
    assert any(
        ref["evidence_clip_status"] == "captured"
        and ref["evidence_visual_source"] == "screen_recording_video"
        and ref["materialized_evidence_video"] is True
        and ref["publish_grade_evidence_video"] is True
        for ref in scene["evidence_video_refs"]
    )


def test_run_release_defaults_to_strict_quality_gate(tmp_path, monkeypatch):
    project = init_project(tmp_path / "release-default-strict", "项目")
    input_file = tmp_path / "input.txt"
    input_file.write_text("灵剪发布级验收。", encoding="utf-8")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "发布级验收"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "user_audio",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 1.0}],
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "发布级验收",
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s1.mp4",
                }
            ],
        },
    )
    (project.path / "artifacts" / "evidence_collection_checklist.md").write_text(
        "# 真实动态证据素材采集清单\n\n请补第 1 镜录屏。\n",
        encoding="utf-8",
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    video_path = project.path / "renders" / "release" / "douyin" / "video.mp4"
    manifest_path = project.path / "renders" / "release" / "douyin" / "render_manifest.json"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"mp4")
    manifest_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.run_doctor",
        lambda: SimpleNamespace(required=[]),
    )
    seen_render: dict[str, object] = {}

    def fake_render_project(*args, **kwargs):
        seen_render["args"] = args
        seen_render["kwargs"] = kwargs
        return RenderResult("release", video_path, manifest_path)

    monkeypatch.setattr("apps.cli.lingjian_cli.main.render_project", fake_render_project)

    def fake_run_qa(*args, **kwargs):
        assert kwargs["release"] is True
        assert kwargs["strict"] is True
        return QAReport(
            hard_failures=[
                QAIssue(
                    "RELEASE_VISUAL_IS_TEMPLATE_LOOP",
                    "hard",
                    "样片模板不能发布。",
                )
            ]
        )

    monkeypatch.setattr("apps.cli.lingjian_cli.main.run_qa", fake_run_qa)

    result = runner.invoke(
        app,
        [
            "run",
            str(project.path),
            "--input-file",
            str(input_file),
            "--release",
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert seen_render["kwargs"]["mode"] == "release"
    assert seen_render["kwargs"]["strict"] is True
    assert '"status": "qa_blocking"' in result.output
    assert "RELEASE_VISUAL_IS_TEMPLATE_LOOP" in result.output


def test_run_release_stops_on_strict_render_caption_timing_failure(tmp_path, monkeypatch):
    project = init_project(tmp_path / "release-strict-caption-fail", "项目")
    input_file = tmp_path / "input.txt"
    input_file.write_text("灵剪发布级字幕验收。", encoding="utf-8")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "发布级字幕验收"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "user_audio",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 1.0}],
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "发布级字幕验收",
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s1.mp4",
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.run_doctor",
        lambda: SimpleNamespace(required=[]),
    )
    seen_render: dict[str, object] = {}

    def fake_render_project(*args, **kwargs):
        seen_render["args"] = args
        seen_render["kwargs"] = kwargs
        raise LingjianError(
            "RELEASE_CAPTION_TIMING_NOT_READY",
            "release strict 渲染发现字幕 timing 仍不可发布。",
            "请补齐 voice_plan caption_cues。",
            {
                "render_manifest": "renders/release/douyin/render_manifest.json",
                "blockers": [
                    {
                        "scene_id": "s1",
                        "release_blocker_code": "RELEASE_CAPTION_TIMING_IS_ESTIMATED",
                    }
                ],
            },
        )

    monkeypatch.setattr("apps.cli.lingjian_cli.main.render_project", fake_render_project)
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.run_qa",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("QA must not run after strict render failure")
        ),
    )

    result = runner.invoke(
        app,
        [
            "run",
            str(project.path),
            "--input-file",
            str(input_file),
            "--release",
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert seen_render["kwargs"]["mode"] == "release"
    assert seen_render["kwargs"]["strict"] is True
    payload = json.loads(result.output)
    assert payload["error_code"] == "RELEASE_CAPTION_TIMING_NOT_READY"
    assert payload["blockers"][0]["release_blocker_code"] == (
        "RELEASE_CAPTION_TIMING_IS_ESTIMATED"
    )


def test_run_release_self_check_repair_returns_to_visual_review(tmp_path, monkeypatch):
    project = init_project(tmp_path / "release-self-check", "项目")
    input_file = tmp_path / "input.txt"
    input_file.write_text("灵剪发布级验收。", encoding="utf-8")
    audio_path = project.path / "artifacts" / "voice_segments" / "voice.wav"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"audio")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "role": "hook", "narration_text": "发布级验收"}],
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
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/voice.wav",
                    "duration_sec": 1.0,
                }
            ],
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "scenes": [
                {
                    "scene_id": "s1",
                    "role": "hook",
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s1.mp4",
                    "motion_intent": {"main_motion_intent": "注意力钩子推进"},
                }
            ],
        },
    )
    (project.path / "artifacts" / "evidence_collection_checklist.md").write_text(
        "# 真实动态证据素材采集清单\n\n请补第 1 镜录屏。\n",
        encoding="utf-8",
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    video_path = project.path / "renders" / "release" / "douyin" / "video.mp4"
    manifest_path = project.path / "renders" / "release" / "douyin" / "render_manifest.json"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"mp4")
    manifest_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.run_doctor",
        lambda: SimpleNamespace(required=[]),
    )
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.render_project",
        lambda *args, **kwargs: RenderResult("release", video_path, manifest_path),
    )
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.run_qa",
        lambda *args, **kwargs: QAReport(
            hard_failures=[
                QAIssue(
                    "RELEASE_VISUAL_LAYOUT_CONTRACT_MISSING",
                    "hard",
                    "缺少 layout contract。",
                )
            ]
        ),
    )

    result = runner.invoke(
        app,
        [
            "run",
            str(project.path),
            "--input-file",
            str(input_file),
            "--release",
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "awaiting_approval"
    assert payload["current_step"] == "visuals"
    assert "<用户>" not in payload["next_command"]
    assert "--approved-by '你的名字'" in payload["next_command"]
    visual_plan = json.loads((project.path / "artifacts" / "visual_plan.json").read_text())
    assert visual_plan["post_render_self_check"]["attempts"]
    assert visual_plan["scenes"][0]["layout_contract"]["safeBottomY"]
    approvals = json.loads((project.path / "artifacts" / "approvals.json").read_text())
    assert "visuals" not in approvals


def test_run_release_missing_tts_action_links_volcengine(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.run_doctor",
        lambda: SimpleNamespace(
            required=[SimpleNamespace(id="publish_tts_provider")]
        ),
    )

    result = runner.invoke(
        app,
        [
            "run",
            str(tmp_path / "needs-tts"),
            "--release",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "https://console.volcengine.com/speech/new/setting/activate" in result.output
    assert "https://console.volcengine.com/speech/new/setting/apikeys" in result.output
    assert "VOLCENGINE_TTS_API_KEY" in result.output
    assert "APP ID" not in result.output
    assert "Access Token" not in result.output
    assert "Cluster ID" not in result.output


def test_run_release_existing_voice_and_visual_artifacts_skip_generic_provider_gap(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "resume-release", "恢复发布")
    assets_dir = project.path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "input_assets.json").write_text(
        json.dumps(
            [{"type": "text", "source_uri": "inline", "text": "已有内容依据。"}],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "full.wav").write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "恢复发布流程"}],
        },
    )
    write_artifact(
        project,
        "voice",
            {
                "id": "voice",
                "provider_id": "volcengine_tts",
                "provider_is_mock": False,
                "full_audio_path": "artifacts/voice_segments/full.wav",
                "segments": [
                    {
                        "scene_id": "s1",
                        "duration_sec": 2.0,
                        "caption_cues": [
                            {
                                "text": "恢复发布流程",
                                "start_sec": 0.0,
                                "end_sec": 2.0,
                                "source": "voice_duration_aligned",
                                "timing_basis": "real_segment_duration",
                            }
                        ],
                    }
                ],
                "total_duration_sec": 2.0,
            },
        )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "恢复发布流程",
                    "director_review_sheet_v2": {"visual_content": "旧确认单。"},
                }
            ],
        },
    )
    checklist_path = project.path / "artifacts" / "evidence_collection_checklist.md"
    checklist_path.write_text(
        "# 真实动态证据素材采集清单\n\n请补第 1 镜录屏。\n",
        encoding="utf-8",
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    write_artifact(
        project,
        "visuals",
        {
            "id": "visuals",
            "asset_diagnosis_summary": {
                "non_publish_grade_count": 2,
                "single_next_action_zh": "请先补第 1 镜 Codex app 触发录屏。",
            },
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "恢复发布流程",
                    "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                    "bgm": "科技感 BGM,人声优先",
                    "sfx_points": ["Codex 输入框聚焦提示音"],
                    "asset_diagnosis": {
                        "asset_status": "blocked_missing_matching_evidence_video",
                        "missing_evidence_types": ["codex_operation_recording"],
                        "missing_evidence_action_zh": (
                            "录制 Codex app 里一句话触发 lingjian-video 的对话过程。"
                        ),
                        "next_action_zh": "请先录制第 1 镜 Codex app 触发过程。",
                    },
                    "director_review_sheet_v2": {
                        "scene_number": 1,
                        "visual_content": "已变更的确认单。",
                    },
                },
                {
                    "scene_id": "s2",
                    "narration_text": "恢复发布流程第二镜",
                    "asset_recipe_id": "visual_asset_generation_queue",
                    "asset_diagnosis": {
                        "asset_status": "blocked_missing_matching_evidence_video",
                        "missing_evidence_types": ["codex_operation_recording"],
                        "missing_evidence_action_zh": (
                            "录制宿主插件生成动态视频资产的队列过程。"
                        ),
                        "next_action_zh": "后续还要录制第 2 镜宿主资产生成过程。",
                    },
                    "director_review_sheet_v2": {
                        "scene_number": 2,
                        "visual_content": "宿主插件生成每镜动态视频资产。",
                    },
                },
            ],
        },
    )
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.run_doctor",
        lambda: SimpleNamespace(
            required=[
                SimpleNamespace(id="publish_tts_provider"),
                SimpleNamespace(id="publish_visual_provider"),
            ]
        ),
    )

    result = runner.invoke(app, ["run", str(project.path), "--release", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["error_code"] == "DIRECTOR_REVIEW_SHEET_STALE"
    assert payload["current_step"] == "visuals"
    assert payload["director_review_artifact"] == "artifacts/director_review_sheet.md"
    assert "director_review_markdown" in payload
    assert "evidence_collection_checklist_markdown" in payload
    assert payload["next_command_kind"] == "collect_evidence"
    assert payload["next_command"].startswith("uv run lj ingest codex ")
    assert "--scene-id s1" in payload["next_command"]
    assert "--allow-screen-recording" in payload["next_command"]
    alternative_commands = [
        item.get("command", "") for item in payload["alternative_next_commands"]
    ]
    assert any(
        command.startswith("uv run lj ingest video ")
        and "--role codex_recording" in command
        and "--scene-id s1" in command
        for command in alternative_commands
    )
    assert payload["screen_recording_consent_required"] is True
    assert "当前屏幕没有私密信息" in payload["privacy_notice_zh"]
    assert payload["manual_fallback_command"].startswith("uv run lj ingest video ")
    assert "--role codex_recording" in payload["manual_fallback_command"]
    assert "--scene-id s1" in payload["manual_fallback_command"]
    blockers = payload["remaining_evidence_blockers"]
    assert [blocker["scene_id"] for blocker in blockers] == ["s1", "s2"]
    assert blockers[0]["first_command"].startswith("uv run lj ingest codex ")
    assert "--scene-id s1" in blockers[0]["first_command"]
    assert blockers[0]["screen_recording_consent_required"] is True
    assert "--scene-id s1" in blockers[0]["manual_fallback_command"]
    assert blockers[1]["asset_recipe_id"] == "visual_asset_generation_queue"
    assert "--scene-id s2" in blockers[1]["first_command"]
    assert blockers[1]["screen_recording_consent_required"] is True
    assert "--scene-id s2" in blockers[1]["manual_fallback_command"]
    audio_blockers = payload["remaining_audio_asset_blockers"]
    assert [blocker["kind"] for blocker in audio_blockers] == ["bgm", "sfx"]
    assert audio_blockers[0]["scene_ids"] == ["s1"]
    assert "uv run lj ingest audio" in audio_blockers[0]["first_command"]
    assert "--kind bgm" in audio_blockers[0]["first_command"]
    assert audio_blockers[1]["scene_id"] == "s1"
    assert "uv run lj ingest audio" in audio_blockers[1]["first_command"]
    assert "--kind sfx" in audio_blockers[1]["first_command"]
    assert "--scene-id s1" in audio_blockers[1]["first_command"]
    assert "--action" in audio_blockers[1]["first_command"]
    assert payload["audio_asset_next_action_zh"].startswith("分镜已声明需要 BGM")
    assert "当前 next_command" in payload["audio_asset_blocked_until_resolved_zh"]
    assert payload["approval_command"].startswith("uv run lj approve visuals ")
    assert "<用户>" not in payload["next_command"]
    assert "--approved-by '你的名字'" in payload["approval_command"]
    assert "approval_blocked_until_evidence_zh" in payload
    assert "DOCTOR_NOT_READY" not in result.output


def test_render_stale_voice_and_visuals_exposes_reapproval_commands_with_evidence_next_step(
    tmp_path,
):
    project = init_project(tmp_path / "stale-voice-visuals-evidence", "多审批过期")
    write_artifact(project, "script", {"id": "script", "scenes": []})
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )
    visual_plan = {
        "id": "visuals",
        "asset_diagnosis_summary": {
            "non_publish_grade_count": 1,
            "single_next_action_zh": "请录制第 1 镜 Codex app 触发过程。",
        },
        "evidence_collection_checklist_v1": {
            "items": [
                {
                    "scene_id": "s1",
                    "scene_number": 1,
                    "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                    "expected_evidence_types": [
                        "codex_operation_recording",
                        "screen_recording_capture",
                    ],
                    "next_action_zh": "请录制第 1 镜 Codex app 触发过程。",
                    "screen_recording_consent_required": True,
                    "manual_fallback_command": (
                        "uv run lj ingest video "
                        f"{project.path} --file '把录屏文件拖到这里.mp4' "
                        "--role codex_recording --scene-id s1 --json"
                    ),
                    "suggested_commands": [
                        {
                            "label_zh": "优先:记录 Codex app 操作录屏任务",
                            "command": (
                                "uv run lj ingest codex "
                                f"{project.path} --task '展示触发过程' "
                                "--allow-screen-recording --scene-id s1 --json"
                            ),
                            "note_zh": "运行前请确认当前屏幕可被录制。",
                        },
                        {
                            "label_zh": "兜底:把你手动录好的视频绑定到这一镜",
                            "command": (
                                "uv run lj ingest video "
                                f"{project.path} "
                                "--file '把录屏文件拖到这里.mp4' "
                                "--role codex_recording --scene-id s1 --json"
                            ),
                            "note_zh": "不授权录屏时手动导入。",
                        },
                    ],
                }
            ]
        },
        "director_review_sheet_v2": {
            "scenes": [
                {
                    "scene_id": "s1",
                    "scene_number": 1,
                    "narrative_function": "Hook",
                    "narration_text": "旧镜头",
                    "visual_content": "旧确认单。",
                }
            ]
        },
    }
    _write_visuals_artifact(project, visual_plan)
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
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
                    "duration_sec": 2.0,
                    "caption_cues": [
                        {
                            "text": "旧配音计划补字幕",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "source": "voice_duration_aligned",
                        }
                    ],
                }
            ],
        },
    )
    updated_visual_plan = {
        **visual_plan,
        "director_review_sheet_v2": {
            "scenes": [
                {
                    "scene_id": "s1",
                    "scene_number": 1,
                    "narrative_function": "Hook",
                    "narration_text": "新镜头",
                    "visual_content": "当前确认单。",
                }
            ]
        },
    }
    _write_visuals_artifact(project, updated_visual_plan)

    result = runner.invoke(
        app,
        [
            "render",
            str(project.path),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["error_code"] == "APPROVAL_STALE"
    assert payload["stale"] == ["voice", "visuals"]
    assert payload["next_command_kind"] == "collect_evidence"
    assert payload["next_command"].startswith("uv run lj ingest codex ")
    assert payload["voice_reapproval_required"] is True
    assert payload["visuals_reapproval_required"] is True
    assert payload["voice_approval_command"].startswith("uv run lj approve voice ")
    assert payload["visuals_approval_command"].startswith("uv run lj approve visuals ")
    assert payload["approval_command"] == payload["visuals_approval_command"]
    assert payload["stale_approval_targets"] == ["voice", "visuals"]
    assert [
        item["target"] for item in payload["stale_approval_commands"]
    ] == ["voice", "visuals"]
    assert all(
        "--approved-by '你的名字'" in item["command"]
        for item in payload["stale_approval_commands"]
    )
    assert all(
        item["approval_command"] == item["command"]
        for item in payload["stale_approval_commands"]
    )
    assert "voice_plan 已变更" in payload["voice_reapproval_message_zh"]
    assert payload["screen_recording_consent_required"] is True
    assert "lj ingest video" in payload["manual_fallback_command"]


def test_render_voice_only_stale_returns_voice_review_with_post_voice_evidence(
    tmp_path,
):
    project = init_project(tmp_path / "stale-voice-only-evidence", "配音过期")
    write_artifact(project, "script", {"id": "script", "scenes": []})
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )
    visual_plan = {
        "id": "visuals",
        "asset_diagnosis_summary": {
            "non_publish_grade_count": 1,
            "single_next_action_zh": "请录制第 1 镜 Codex app 触发过程。",
        },
        "evidence_collection_checklist_v1": {
            "items": [
                {
                    "scene_id": "s1",
                    "scene_number": 1,
                    "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                    "expected_evidence_types": [
                        "codex_operation_recording",
                        "screen_recording_capture",
                    ],
                    "next_action_zh": "请录制第 1 镜 Codex app 触发过程。",
                    "screen_recording_consent_required": True,
                    "manual_fallback_command": (
                        "uv run lj ingest video "
                        f"{project.path} --file '把录屏文件拖到这里.mp4' "
                        "--role codex_recording --scene-id s1 --json"
                    ),
                    "suggested_commands": [
                        {
                            "label_zh": "优先:记录 Codex app 操作录屏任务",
                            "command": (
                                "uv run lj ingest codex "
                                f"{project.path} --task '展示触发过程' "
                                "--allow-screen-recording --scene-id s1 --json"
                            ),
                            "note_zh": "运行前请确认当前屏幕可被录制。",
                        },
                        {
                            "label_zh": "兜底:把你手动录好的视频绑定到这一镜",
                            "command": (
                                "uv run lj ingest video "
                                f"{project.path} "
                                "--file '把录屏文件拖到这里.mp4' "
                                "--role codex_recording --scene-id s1 --json"
                            ),
                            "note_zh": "不授权录屏时手动导入。",
                        },
                    ],
                }
            ]
        },
        "director_review_sheet_v2": {
            "scenes": [
                {
                    "scene_id": "s1",
                    "scene_number": 1,
                    "narrative_function": "Hook",
                    "narration_text": "当前镜头",
                    "visual_content": "当前确认单。",
                }
            ]
        },
    }
    _write_visuals_artifact(project, visual_plan)
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
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
                    "duration_sec": 2.0,
                    "caption_cues": [
                        {
                            "text": "旧配音计划补字幕",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "source": "voice_duration_aligned",
                        }
                    ],
                }
            ],
        },
    )

    result = runner.invoke(
        app,
        [
            "render",
            str(project.path),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["error_code"] == "APPROVAL_STALE"
    assert payload["current_step"] == "voice"
    assert payload["artifact"] == "artifacts/voice_plan.json"
    assert payload["stale"] == ["voice"]
    assert payload["next_command"].startswith("uv run lj approve voice ")
    assert payload["approval_command"] == payload["next_command"]
    assert payload["voice_approval_command"] == payload["next_command"]
    assert payload["voice_reapproval_required"] is True
    assert "visuals_reapproval_required" not in payload
    assert payload["stale_approval_targets"] == ["voice"]
    assert payload["stale_approval_commands"][0]["target"] == "voice"
    assert payload["stale_approval_commands"][0]["approval_command"] == payload["next_command"]
    assert payload["post_voice_current_step"] == "visuals"
    assert payload["post_voice_next_command_kind"] == "collect_evidence"
    assert "lj ingest codex" in payload["post_voice_next_command"]
    assert payload["post_voice_screen_recording_consent_required"] is True
    assert "manual_fallback_command" in payload["post_voice_privacy_notice_zh"]
    assert "lj ingest video" in payload["post_voice_manual_fallback_command"]
    blocker = payload["post_voice_remaining_evidence_blockers"][0]
    assert blocker["scene_id"] == "s1"
    assert blocker["screen_recording_consent_required"] is True
    assert "lj ingest video" in blocker["manual_fallback_command"]


def test_render_stale_director_review_returns_current_review_sheet(tmp_path):
    project = init_project(tmp_path / "stale-review-render", "过期确认单")
    write_artifact(project, "script", {"id": "script", "scenes": []})
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "volcengine_tts",
            "provider_is_mock": False,
            "segments": [],
        },
    )
    original_visual_plan = {
        "id": "visuals",
        "visual_total": 1,
        "director_review_sheet_v2": {
            "scenes": [
                {
                    "scene_id": "s1",
                    "scene_number": 1,
                    "narrative_function": "Hook",
                    "narration_text": "旧镜头",
                    "visual_content": "旧确认单。",
                }
            ]
        },
    }
    _write_visuals_artifact(project, original_visual_plan)
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    current_visual_plan = {
        "id": "visuals",
        "visual_total": 1,
        "director_review_sheet_v2": {
            "scenes": [
                {
                    "scene_id": "s1",
                    "scene_number": 1,
                    "narrative_function": "Hook",
                    "narration_text": "新镜头",
                    "visual_content": "当前确认单。",
                }
            ]
        },
    }
    write_artifact(project, "visuals", current_visual_plan)

    result = runner.invoke(
        app,
        [
            "render",
            str(project.path),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["error_code"] == "DIRECTOR_REVIEW_SHEET_STALE"
    assert payload["current_step"] == "visuals"
    assert payload["director_review_regenerated"] is True
    assert "当前确认单" in payload["director_review_markdown"]
    assert "旧确认单" not in payload["director_review_markdown"]
    assert (
        project.path / "artifacts" / "director_review_sheet.md"
    ).read_text(encoding="utf-8") == director_review_sheet_markdown(current_visual_plan)
    assert payload["next_command"].startswith("uv run lj approve visuals ")
    assert payload["approval_command"].startswith("uv run lj approve visuals ")
    assert "<用户>" not in payload["next_command"]
    assert "--approved-by '你的名字'" in payload["next_command"]


def test_doctor_json_is_parseable():
    result = runner.invoke(app, ["doctor", "--json"])

    assert result.output.strip().startswith("{")
    assert "error_code" not in result.output


def test_cli_gate_flow_returns_stable_error_codes(tmp_path):
    project = tmp_path / "cli项目"
    input_file = tmp_path / "input.txt"
    input_file.write_text("灵剪是一款面向中文创作者的视频生产工作台。", encoding="utf-8")

    assert runner.invoke(app, ["init", str(project), "--name", "CLI项目", "--json"]).exit_code == 0
    assert (
        runner.invoke(
            app,
            ["ingest", "text", str(project), "--file", str(input_file), "--json"],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(app, ["extract", str(project), "--provider", "mock", "--json"]).exit_code == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "script",
                str(project),
                "--type",
                "product",
                "--platform",
                "douyin",
                "--language",
                "zh-CN",
                "--ratio",
                "9:16",
                "--duration",
                "45",
                "--provider",
                "mock",
                "--json",
            ],
        ).exit_code
        == 0
    )

    blocked = runner.invoke(
        app,
        [
            "render",
            str(project),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
    )
    assert blocked.exit_code == 1
    assert '"error_code": "APPROVAL_REQUIRED"' in blocked.output

    assert (
        runner.invoke(
            app,
            ["approve", "script", str(project), "--approved-by", "tester", "--json"],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["voice", str(project), "--provider", "mock", "--voice", "v1", "--json"],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["approve", "voice", str(project), "--approved-by", "tester", "--json"],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(app, ["visuals", str(project), "--engine", "ffmpeg_card", "--json"]).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["approve", "visuals", str(project), "--approved-by", "tester", "--json"],
        ).exit_code
        == 0
    )

    rendered = runner.invoke(
        app,
        [
            "render",
            str(project),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
    )
    assert rendered.exit_code == 0
    assert '"status": "rendered"' in rendered.output

    preview = runner.invoke(
        app,
        [
            "preview",
            str(project),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
    )
    assert preview.exit_code == 0
    assert '"mode": "preview"' in preview.output

    qa = runner.invoke(app, ["qa", str(project), "--json"])
    assert qa.exit_code == 0
    assert '"release_ready": true' in qa.output

    release = runner.invoke(
        app,
        [
            "export",
            str(project),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--release",
            "--json",
        ],
    )
    assert release.exit_code == 1
    assert '"error_code": "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE"' in release.output

    preview_export = runner.invoke(
        app,
        [
            "export",
            str(project),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
    )
    assert preview_export.exit_code == 0
    assert '"export_dir"' in preview_export.output

    assert (
        runner.invoke(
            app,
            [
                "script",
                str(project),
                "--type",
                "product",
                "--platform",
                "douyin",
                "--language",
                "zh-CN",
                "--ratio",
                "9:16",
                "--duration",
                "45",
                "--provider",
                "mock",
                "--json",
            ],
        ).exit_code
        == 0
    )
    stale = runner.invoke(
        app,
        [
            "render",
            str(project),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
    )
    assert stale.exit_code == 1
    assert '"error_code": "APPROVAL_STALE"' in stale.output


def test_lj_run_pauses_at_script_review_without_yes(tmp_path):
    project = tmp_path / "run暂停项目"
    input_file = tmp_path / "input.txt"
    input_file.write_text("灵剪需要把素材变成可审计短视频。", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "run",
            str(project),
            "--name",
            "Run暂停项目",
            "--input-file",
            str(input_file),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "awaiting_approval"
    assert payload["current_step"] == "script"
    assert "approve script" in payload["next_command"]
    assert "<用户>" not in payload["next_command"]
    assert "--approved-by '你的名字'" in payload["next_command"]
    assert (project / "artifacts" / "script.json").exists()
    assert not (project / "artifacts" / "approvals.json").exists()


def test_lj_run_visual_pause_returns_full_director_review_sheet(tmp_path):
    project = init_project(tmp_path / "run-visual-review", "Run画面审阅")
    assets_dir = project.path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "input_assets.json").write_text(
        json.dumps(
            [{"type": "text", "text": "灵剪是一套可审计的中文短视频导演系统。"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "scenes": [
                {
                    "id": "s1",
                    "role": "hook",
                    "narration_text": "第一秒展示灵剪如何把需求变成视频。",
                    "duration_sec": 2.0,
                }
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_is_mock": True,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")

    result = runner.invoke(app, ["run", str(project.path), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "awaiting_approval"
    assert payload["current_step"] == "visuals"
    assert payload["director_review_artifact"] == "artifacts/director_review_sheet.md"
    assert "导演分镜确认单 v2" in payload["director_review_markdown"]
    required_review_labels = [
        "镜头编号:",
        "镜头目标:",
        "叙事作用:",
        "口播文本:",
        "屏幕短文案:",
        "画面内容:",
        "素材来源:",
        "素材状态:",
        "Profile 证据要求:",
        "引擎路由:",
        "构图:",
        "主体区域:",
        "字幕区域:",
        "遮罩/避让规则:",
        "视觉元素:",
        "色彩/氛围:",
        "主运动:",
        "辅助运动:",
        "转场:",
        "关键帧:",
        "入场动画:",
        "出场动画:",
        "BGM 情绪:",
        "音效点:",
        "字幕切分:",
        "字幕位置/大小:",
        "禁止项:",
        "QA 检查点:",
        "这一镜批准前你要看:",
    ]
    for label in required_review_labels:
        assert label in payload["director_review_markdown"]
    assert (project.path / "artifacts" / "director_review_sheet.md").exists()


def test_lj_qa_json_includes_evidence_recovery_metadata(tmp_path):
    project = init_project(tmp_path / "qa-evidence-recovery", "QA evidence recovery")
    write_artifact(
        project,
        "visuals",
        {
            "id": "visuals",
            "evidence_collection_checklist_v1": {
                "items": [
                    {
                        "scene_id": "s1",
                        "scene_number": 1,
                        "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                        "expected_evidence_types": ["codex_operation_recording"],
                        "next_action_zh": "请录制第 1 镜 Codex app 触发过程。",
                        "screen_recording_consent_required": True,
                        "privacy_notice_zh": "请确认当前屏幕没有私密信息。",
                        "manual_fallback_command": (
                            "uv run lj ingest video /tmp/project --file '把录屏文件拖到这里.mp4' "
                            "--role codex_recording --scene-id s1 --json"
                        ),
                        "suggested_commands": [
                            {
                                "label_zh": "优先:记录 Codex app 操作录屏任务",
                                "command": (
                                    "uv run lj ingest codex /tmp/project --task '展示触发过程' "
                                    "--scene-id s1 --allow-screen-recording --json"
                                ),
                            }
                        ],
                    }
                ]
            },
        },
    )
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
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "real_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["qa", str(project.path), "--release", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    blocker = payload["metadata"]["remaining_evidence_blockers"][0]
    assert blocker["scene_id"] == "s1"
    assert blocker["screen_recording_consent_required"] is True
    assert "--scene-id s1" in blocker["manual_fallback_command"]


def test_lj_qa_json_includes_stale_approval_recovery_metadata(tmp_path, monkeypatch):
    project = init_project(tmp_path / "qa-stale-approval", "QA stale approval")
    write_artifact(project, "script", {"id": "script", "scenes": []})
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
        },
    )
    visual_plan = {"id": "visuals", "engine": "ffmpeg_card", "scenes": []}
    write_artifact(project, "visuals", visual_plan)
    review_path = project.path / "artifacts" / "director_review_sheet.md"
    review_path.write_text(director_review_sheet_markdown(visual_plan), encoding="utf-8")
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
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
                    "duration_sec": 2.0,
                    "caption_cues": [
                        {
                            "text": "审批后新增字幕",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "source": "voice_duration_aligned",
                        }
                    ],
                }
            ],
        },
    )
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
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "real_tts", "kind": "tts", "is_mock": False},
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

    result = runner.invoke(app, ["qa", str(project.path), "--release", "--strict", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert any(
        issue["code"] == "RELEASE_APPROVALS_STALE"
        for issue in payload["hard_failures"]
    )
    assert payload["metadata"]["approval_gate_error_code"] == "APPROVAL_STALE"
    assert payload["metadata"]["stale_approval_targets"] == ["voice"]
    command = payload["metadata"]["stale_approval_commands"][0]["command"]
    assert command.startswith("uv run lj approve voice ")
    assert "--approved-by '你的名字'" in command
    assert payload["metadata"]["voice_reapproval_required"] is True


def test_lj_run_yes_completes_preview_flow_with_real_approvals(tmp_path):
    project = tmp_path / "run自动项目"
    input_file = tmp_path / "input.txt"
    input_file.write_text("灵剪需要一条命令完成预览档验证。", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "run",
            str(project),
            "--name",
            "Run自动项目",
            "--input-file",
            str(input_file),
            "--yes",
            "--approved-by",
            "ci",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "exported"
    assert payload["mode"] == "preview"
    assert payload["qa"]["release_ready"] is True
    assert (project / "renders" / "preview" / "douyin" / "video.mp4").exists()
    assert (project / "artifacts" / "approvals.json").exists()
    approvals = json.loads((project / "artifacts" / "approvals.json").read_text(encoding="utf-8"))
    assert set(approvals) == {"script", "voice", "visuals"}
    assert payload["export_dir"]


def test_lj_run_accepts_user_recorded_voice_audio(tmp_path):
    project = tmp_path / "run用户录音项目"
    input_file = tmp_path / "input.txt"
    input_file.write_text("灵剪使用用户录好的口播音频。", encoding="utf-8")
    audio_file = tmp_path / "narration.mp3"
    audio_file.write_bytes(b"USER AUDIO")

    result = runner.invoke(
        app,
        [
            "run",
            str(project),
            "--name",
            "Run用户录音",
            "--input-file",
            str(input_file),
            "--voice-audio-file",
            str(audio_file),
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 0
    voice_payload = json.loads(
        (project / "artifacts" / "voice_plan.json").read_text(encoding="utf-8")
    )
    assert voice_payload["provider_id"] == "user_audio"
    assert voice_payload["provider_is_mock"] is False
    assert voice_payload["segments"][0]["caption_cues"][0]["source"] == (
        "voice_duration_aligned"
    )
    assert (project / "artifacts" / "voice_segments" / "user_audio.mp3").read_bytes() == (
        b"USER AUDIO"
    )


def test_cli_resolves_mock_provider_aliases_as_mock(tmp_path):
    project = tmp_path / "provider项目"
    runner.invoke(app, ["init", str(project), "--name", "Provider项目", "--json"])

    result = runner.invoke(
        app,
        [
            "script",
            str(project),
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--provider",
            "mock_llm",
            "--json",
        ],
    )

    assert result.exit_code == 0
    script_json = (project / "artifacts" / "script.json").read_text(encoding="utf-8")
    assert '"provider_is_mock": true' in script_json


def test_cli_script_uses_configured_real_cli_provider(tmp_path, monkeypatch):
    project = tmp_path / "real脚本项目"
    llm_cli = tmp_path / "fake-llm"
    llm_cli.write_text(
        "#!/bin/sh\n"
        "cat >/dev/null\n"
        "printf '%s' '{\"scenes\":[{\"id\":\"s1\",\"narration_text\":\"真实 CLI 文案\"}]}'\n",
        encoding="utf-8",
    )
    llm_cli.chmod(0o755)
    monkeypatch.setenv("LINGJIAN_LLM_CLI", str(llm_cli))
    runner.invoke(app, ["init", str(project), "--name", "Real Script", "--json"])

    result = runner.invoke(
        app,
        [
            "script",
            str(project),
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--provider",
            "llm_cli",
            "--json",
        ],
    )

    assert result.exit_code == 0
    script_json = (project / "artifacts" / "script.json").read_text(encoding="utf-8")
    assert '"provider_id": "llm_cli"' in script_json
    assert '"provider_is_mock": false' in script_json
    assert "真实 CLI 文案" in script_json


def test_cli_script_rejects_thin_real_cli_output(tmp_path, monkeypatch):
    project = tmp_path / "thin脚本项目"
    llm_cli = tmp_path / "fake-thin-llm"
    llm_cli.write_text(
        "#!/bin/sh\n"
        "cat >/dev/null\n"
        "printf '%s' '{\"scenes\":[]}'\n",
        encoding="utf-8",
    )
    llm_cli.chmod(0o755)
    monkeypatch.setenv("LINGJIAN_LLM_CLI", str(llm_cli))
    runner.invoke(app, ["init", str(project), "--name", "Thin Script", "--json"])

    result = runner.invoke(
        app,
        [
            "script",
            str(project),
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--provider",
            "llm_cli",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert '"error_code": "LLM_OUTPUT_TOO_THIN"' in result.output


def test_cli_voice_uses_configured_real_cli_provider(tmp_path, monkeypatch):
    project = tmp_path / "real语音项目"
    tts_cli = tmp_path / "fake-tts"
    tts_cli.write_text(
        "#!/bin/sh\n"
        "cat >/dev/null\n"
        "printf '%s' '{\"audio_base64\":\"UkVBTCBBVURJTw==\",\"duration_sec\":2.5}'\n",
        encoding="utf-8",
    )
    tts_cli.chmod(0o755)
    monkeypatch.setenv("LINGJIAN_TTS_CLI", str(tts_cli))
    runner.invoke(app, ["init", str(project), "--name", "Real Voice", "--json"])

    result = runner.invoke(
        app,
        [
            "voice",
            str(project),
            "--provider",
            "tts_cli",
            "--voice",
            "v1",
            "--json",
        ],
    )

    assert result.exit_code == 0
    voice_json = (project / "artifacts" / "voice_plan.json").read_text(encoding="utf-8")
    assert '"provider_id": "tts_cli"' in voice_json
    assert '"provider_is_mock": false' in voice_json
    assert '"duration_sec": 2.5' in voice_json
    assert (project / "artifacts" / "voice_segments" / "s1.wav").read_bytes() == b"REAL AUDIO"


def test_cli_voice_synthesizes_one_segment_per_script_scene(tmp_path, monkeypatch):
    project_path = tmp_path / "multi-scene-voice"
    project = init_project(project_path, "Multi Scene Voice")
    calls: list[dict] = []

    class FakeTTSProvider:
        id = "fake_tts"
        is_mock = False

        def synthesize(self, payload: dict):
            calls.append(payload)
            index = len(calls)
            return f"AUDIO-{index}".encode(), float(index)

    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "第一镜口播。"},
                {"id": "s2", "narration_text": "第二镜口播。"},
            ],
        },
    )
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main._resolve_tts_provider",
        lambda provider: FakeTTSProvider(),
    )

    result = runner.invoke(
        app,
        [
            "voice",
            str(project_path),
            "--provider",
            "fake_tts",
            "--voice",
            "voice-a",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((project_path / "artifacts" / "voice_plan.json").read_text())
    assert [call["text"] for call in calls] == ["第一镜口播。", "第二镜口播。"]
    assert [call["scene_id"] for call in calls] == ["s1", "s2"]
    assert [segment["scene_id"] for segment in payload["segments"]] == ["s1", "s2"]
    assert [segment["duration_sec"] for segment in payload["segments"]] == [1.0, 2.0]
    assert [segment["voice_id"] for segment in payload["segments"]] == ["voice-a", "voice-a"]
    assert payload["segments"][0]["caption_cues"][0]["source"] == "voice_duration_aligned"
    assert payload["segments"][0]["caption_cues"][0]["timing_basis"] == "real_segment_duration"
    assert payload["segments"][0]["caption_cues"][-1]["end_sec"] == 1.0
    assert payload["segments"][1]["caption_cues"][-1]["end_sec"] == 2.0
    assert payload["segments"][0]["provider_voice_settings"] == {
        "provider_id": "fake_tts",
        "voice_id": "voice-a",
        "settings_source": "provider_voice_id_fallback",
    }
    assert payload["segments"][1]["provider_voice_settings"] == {
        "provider_id": "fake_tts",
        "voice_id": "voice-a",
        "settings_source": "provider_voice_id_fallback",
    }
    assert payload["total_duration_sec"] == 3.0
    assert payload["full_audio_path"] == "artifacts/voice_segments/full.wav"
    assert (project_path / "artifacts" / "voice_segments" / "s1.wav").read_bytes() == b"AUDIO-1"
    assert (project_path / "artifacts" / "voice_segments" / "s2.wav").read_bytes() == b"AUDIO-2"
    assert (project_path / "artifacts" / "voice_segments" / "full.wav").read_bytes() == (
        b"AUDIO-1AUDIO-2"
    )


def test_cli_voice_backfills_existing_voice_plan_caption_cues_without_resynthesizing(
    tmp_path,
    monkeypatch,
):
    project_path = tmp_path / "old-voice-plan-captions"
    project = init_project(project_path, "Old Voice Plan Captions")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "第一镜说明灵剪会拆脚本。"},
                {"id": "s2", "narration_text": "第二镜展示真实 QA 证据。"},
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
            "voice_id": "voice-a",
            "segments": [
                {"scene_id": "s1", "duration_sec": 2.0},
                {"scene_id": "s2", "duration_sec": 3.0},
            ],
            "total_duration_sec": 5.0,
        },
    )
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main._resolve_tts_provider",
        lambda provider: (_ for _ in ()).throw(AssertionError("must not synthesize")),
    )

    result = runner.invoke(
        app,
        [
            "voice",
            str(project_path),
            "--provider",
            "real_tts",
            "--voice",
            "voice-a",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["voice_caption_repair"]["repaired_scene_ids"] == ["s1", "s2"]
    voice_plan = json.loads((project_path / "artifacts" / "voice_plan.json").read_text())
    assert voice_plan["timed_caption_repair"]["requires_voice_reapproval"] is True
    assert [
        segment["caption_cues"][0]["source"]
        for segment in voice_plan["segments"]
    ] == ["voice_duration_aligned", "voice_duration_aligned"]
    assert voice_plan["segments"][1]["caption_cues"][-1]["end_sec"] == 3.0


def test_run_pauses_for_voice_reapproval_after_backfilling_existing_voice_plan(
    tmp_path,
):
    project_path = tmp_path / "run-old-voice-plan-captions"
    project = init_project(project_path, "Run Old Voice Plan Captions")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "旧配音计划补字幕节奏。"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "voice_id": "voice-a",
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
            "total_duration_sec": 2.0,
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "旧配音计划补字幕节奏。",
                    "generator": "user-asset",
                    "duration_sec": 2.0,
                }
            ],
        },
    )
    approve_target(project, "visuals", "tester")
    input_file = tmp_path / "input.txt"
    input_file.write_text("灵剪旧配音计划字幕回填测试。", encoding="utf-8")

    result = runner.invoke(
        app,
        ["run", str(project_path), "--input-file", str(input_file), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "awaiting_approval"
    assert payload["current_step"] == "voice"
    assert payload["voice_caption_repair"]["repaired_scene_ids"] == ["s1"]
    voice_plan = json.loads((project_path / "artifacts" / "voice_plan.json").read_text())
    assert voice_plan["segments"][0]["caption_cues"][0]["source"] == "voice_duration_aligned"
    gate_error = validate_render_gate(project)
    assert gate_error is not None
    assert gate_error.error_code == "APPROVAL_STALE"
    assert gate_error.details["stale"] == ["voice"]


def test_run_voice_caption_repair_response_includes_pending_evidence_blockers(
    tmp_path,
):
    project_path = tmp_path / "run-old-voice-plan-with-evidence-blockers"
    project = init_project(project_path, "Run Old Voice Plan With Evidence Blockers")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "旧配音计划补字幕节奏。"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "voice_id": "voice-a",
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
            "total_duration_sec": 2.0,
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "asset_diagnosis_summary": {
                "non_publish_grade_count": 1,
                "single_next_action_zh": "请录制 Codex app 触发过程。",
            },
            "evidence_collection_checklist_v1": {
                "items": [
                    {
                        "scene_id": "s1",
                        "scene_number": 1,
                        "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                        "expected_evidence_types": [
                            "codex_operation_recording",
                            "screen_recording_capture",
                        ],
                        "next_action_zh": "请录制 Codex app 触发过程。",
                        "screen_recording_consent_required": True,
                        "manual_fallback_command": (
                            "uv run lj ingest video "
                            f"{project_path} --file '把录屏文件拖到这里.mp4' "
                            "--role codex_recording --scene-id s1 --json"
                        ),
                        "suggested_commands": [
                            {
                                "label_zh": "优先:记录 Codex app 操作录屏任务",
                                "command": (
                                    "uv run lj ingest codex "
                                    f"{project_path} --task '展示触发过程' "
                                    "--allow-screen-recording --scene-id s1 --json"
                                ),
                                "note_zh": "运行前请确认当前屏幕可被录制。",
                            },
                            {
                                "label_zh": "兜底:把你手动录好的视频绑定到这一镜",
                                "command": (
                                    "uv run lj ingest video "
                                    f"{project_path} "
                                    "--file '把录屏文件拖到这里.mp4' "
                                    "--role codex_recording --scene-id s1 --json"
                                ),
                                "note_zh": "不授权录屏时手动导入。",
                            },
                        ],
                    }
                ]
            },
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "旧配音计划补字幕节奏。",
                    "generator": "user-asset",
                    "duration_sec": 2.0,
                    "bgm": "轻节奏 BGM,人声优先",
                    "sfx_points": ["字幕节奏修复完成提示音"],
                }
            ],
        },
    )
    approve_target(project, "visuals", "tester")
    input_file = tmp_path / "input.txt"
    input_file.write_text("灵剪旧配音计划字幕回填测试。", encoding="utf-8")

    result = runner.invoke(
        app,
        ["run", str(project_path), "--input-file", str(input_file), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["current_step"] == "voice"
    assert "lj approve voice" in payload["next_command"]
    assert payload["post_voice_next_command_kind"] == "collect_evidence"
    assert "lj ingest codex" in payload["post_voice_next_command"]
    assert payload["post_voice_screen_recording_consent_required"] is True
    assert "manual_fallback_command" in payload["post_voice_privacy_notice_zh"]
    assert "lj ingest video" in payload["post_voice_manual_fallback_command"]
    blockers = payload["post_voice_remaining_evidence_blockers"]
    assert blockers[0]["scene_id"] == "s1"
    assert blockers[0]["screen_recording_consent_required"] is True
    assert "lj ingest video" in blockers[0]["manual_fallback_command"]
    audio_blockers = payload["post_voice_remaining_audio_asset_blockers"]
    assert [blocker["kind"] for blocker in audio_blockers] == ["bgm", "sfx"]
    assert "uv run lj ingest audio" in audio_blockers[0]["first_command"]
    assert "--kind bgm" in audio_blockers[0]["first_command"]
    assert "uv run lj ingest audio" in audio_blockers[1]["first_command"]
    assert "--kind sfx" in audio_blockers[1]["first_command"]
    assert "--scene-id s1" in audio_blockers[1]["first_command"]
    assert payload["post_voice_audio_asset_next_action_zh"].startswith(
        "分镜已声明需要 BGM"
    )
    assert "remaining_audio_asset_blockers" in payload[
        "post_voice_audio_asset_blocked_until_resolved_zh"
    ]


def test_cli_voice_uses_continuous_full_track_when_provider_prefers_it(tmp_path, monkeypatch):
    project_path = tmp_path / "continuous-voice"
    project = init_project(project_path, "Continuous Voice")
    calls: list[dict] = []

    class FakeContinuousTTSProvider:
        id = "volcengine_tts"
        is_mock = False
        prefer_continuous_full_track = True

        def synthesize(self, payload: dict):
            calls.append(payload)
            return b"AUDIO-FULL", 6.0

        def resolve_voice_id(self, voice: str):
            return voice

        def voice_label(self, voice: str):
            return "固定女声"

        def voice_settings(self, voice: str):
            return {
                "voice_type": voice,
                "sample_rate": 24000,
                "track_strategy": "continuous_full_track",
            }

    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "第一镜口播。"},
                {"id": "s2", "narration_text": "第二镜更长口播。"},
            ],
        },
    )
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main._resolve_tts_provider",
        lambda provider: FakeContinuousTTSProvider(),
    )

    result = runner.invoke(
        app,
        [
            "voice",
            str(project_path),
            "--provider",
            "volcengine_tts",
            "--voice",
            "voice-a",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((project_path / "artifacts" / "voice_plan.json").read_text())
    assert len(calls) == 1
    assert calls[0]["track"] == "full"
    assert calls[0]["voice"] == "voice-a"
    assert "第一镜口播" in calls[0]["text"]
    assert "第二镜更长口播" in calls[0]["text"]
    assert payload["total_duration_sec"] == 6.0
    assert payload["provider_voice_settings"]["track_strategy"] == "continuous_full_track"
    assert [segment["voice_id"] for segment in payload["segments"]] == ["voice-a", "voice-a"]
    assert all(
        segment["provider_voice_settings"]["track_strategy"] == "continuous_full_track"
        for segment in payload["segments"]
    )
    assert all(segment["caption_cues"] for segment in payload["segments"])
    assert payload["segments"][0]["caption_cues"][0]["source"] == "voice_duration_aligned"
    assert payload["segments"][1]["caption_cues"][-1]["end_sec"] == round(
        payload["segments"][1]["duration_sec"], 3
    )
    assert payload["segments"][0]["audio_path"] == "artifacts/voice_segments/s1.wav"
    assert "audio_path" not in payload["segments"][1]
    assert round(sum(segment["duration_sec"] for segment in payload["segments"]), 6) == 6.0
    assert (
        project_path / "artifacts" / "voice_segments" / "full.wav"
    ).read_bytes() == b"AUDIO-FULL"


def test_cli_voice_concatenates_streaming_wav_segments(tmp_path, monkeypatch):
    project_path = tmp_path / "streaming-wav-voice"
    project = init_project(project_path, "Streaming Wav Voice")

    def streaming_wav(seconds: int) -> bytes:
        sample_rate = 24000
        byte_rate = sample_rate * 2
        pcm = b"\x00\x00" * sample_rate * seconds
        return (
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

    class FakeTTSProvider:
        id = "fake_tts"
        is_mock = False

        def synthesize(self, payload: dict):
            seconds = 1 if payload["scene_id"] == "s1" else 2
            return streaming_wav(seconds), float(seconds)

    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "第一镜口播。"},
                {"id": "s2", "narration_text": "第二镜口播。"},
            ],
        },
    )
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main._resolve_tts_provider",
        lambda provider: FakeTTSProvider(),
    )

    result = runner.invoke(
        app,
        [
            "voice",
            str(project_path),
            "--provider",
            "fake_tts",
            "--voice",
            "voice-a",
            "--json",
        ],
    )

    assert result.exit_code == 0
    with wave.open(str(project_path / "artifacts" / "voice_segments" / "full.wav"), "rb") as wav:
        assert wav.getframerate() == 24000
        assert wav.getnframes() == 24000 * 3


def test_run_default_voice_does_not_send_test_voice_to_real_provider(tmp_path, monkeypatch):
    project_path = tmp_path / "run-default-voice"
    input_path = tmp_path / "input.txt"
    payload_path = tmp_path / "tts-payload.json"
    tts_cli = tmp_path / "fake-tts"
    tts_cli.write_text(
        "#!/bin/sh\n"
        f"cat > '{payload_path}'\n"
        "printf '%s' '{\"audio_base64\":\"UkVBTCBBVURJTw==\",\"duration_sec\":2.5}'\n",
        encoding="utf-8",
    )
    tts_cli.chmod(0o755)
    input_path.write_text("默认音色不应传测试值", encoding="utf-8")
    monkeypatch.setenv("LINGJIAN_TTS_CLI", str(tts_cli))
    project = init_project(project_path, "Run Voice")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "默认音色不应传测试值"}],
        },
    )
    approve_target(project, "script", "tester")

    result = runner.invoke(
        app,
        [
            "run",
            str(project_path),
            "--input-file",
            str(input_path),
            "--voice-provider",
            "tts_cli",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["voice"] == ""
    assert payload["voice"] != "test-voice"


def test_run_pauses_for_volcengine_voice_choice_before_formal_voice(tmp_path, monkeypatch):
    project_path = tmp_path / "run-volcengine-voice-choice"
    input_path = tmp_path / "input.txt"
    input_path.write_text("需要先让用户选择音色", encoding="utf-8")
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "api-key-secret")
    monkeypatch.setenv("VOLCENGINE_TTS_VOICE_CANDIDATES", "voice-a:自然女声")

    def fake_post_tts_v3(text, voice):
        return b"WAVDATA"

    monkeypatch.setattr("providers.volcengine_tts._post_tts_v3", fake_post_tts_v3)
    project = init_project(project_path, "Voice Choice")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "需要先让用户选择音色"}],
        },
    )
    approve_target(project, "script", "tester")

    result = runner.invoke(
        app,
        [
            "run",
            str(project_path),
            "--input-file",
            str(input_path),
            "--voice-provider",
            "volcengine_tts",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "awaiting_voice_choice"
    assert payload["artifact"] == "artifacts/voice_options.json"
    assert payload["options"][0]["voice_id"] == "voice-a"
    assert (project_path / "artifacts" / "voice_options" / "option_1.wav").exists()
    assert not (project_path / "artifacts" / "voice_plan.json").exists()


def test_cli_voice_accepts_user_recorded_audio_file(tmp_path):
    project = tmp_path / "user音频项目"
    audio = tmp_path / "narration.m4a"
    audio.write_bytes(b"USER RECORDED AUDIO")
    runner.invoke(app, ["init", str(project), "--name", "User Voice", "--json"])

    result = runner.invoke(
        app,
        [
            "voice",
            str(project),
            "--provider",
            "auto",
            "--voice",
            "user",
            "--audio-file",
            str(audio),
            "--json",
        ],
    )

    assert result.exit_code == 0
    voice_payload = json.loads(
        (project / "artifacts" / "voice_plan.json").read_text(encoding="utf-8")
    )
    assert voice_payload["provider_id"] == "user_audio"
    assert voice_payload["provider_is_mock"] is False
    assert voice_payload["source_type"] == "user-recorded-audio"
    assert voice_payload["segments"][0]["caption_cues"][0]["source"] == (
        "voice_duration_aligned"
    )
    assert (project / "artifacts" / "voice_segments" / "user_audio.m4a").read_bytes() == (
        b"USER RECORDED AUDIO"
    )


def test_cli_voice_rejects_empty_real_cli_audio(tmp_path, monkeypatch):
    project = tmp_path / "empty语音项目"
    tts_cli = tmp_path / "fake-empty-tts"
    tts_cli.write_text(
        "#!/bin/sh\n"
        "cat >/dev/null\n"
        "printf '%s' '{\"audio_base64\":\"\",\"duration_sec\":1}'\n",
        encoding="utf-8",
    )
    tts_cli.chmod(0o755)
    monkeypatch.setenv("LINGJIAN_TTS_CLI", str(tts_cli))
    runner.invoke(app, ["init", str(project), "--name", "Empty Voice", "--json"])

    result = runner.invoke(
        app,
        [
            "voice",
            str(project),
            "--provider",
            "tts_cli",
            "--voice",
            "v1",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert '"error_code": "TTS_OUTPUT_INVALID"' in result.output


def test_cli_script_uses_openai_compatible_provider(tmp_path, monkeypatch):
    project = tmp_path / "openai脚本项目"
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return (
                '{"choices":[{"message":{"content":"'
                '{\\"scenes\\":[{\\"id\\":\\"s1\\",'
                '\\"narration_text\\":\\"OpenAI CLI-free 文案\\"}]}'
                '"}}]}'
            ).encode("utf-8")

    monkeypatch.setattr(
        "providers.openai_compatible.urlopen",
        lambda request, timeout: FakeResponse(),
    )
    runner.invoke(app, ["init", str(project), "--name", "OpenAI Script", "--json"])

    result = runner.invoke(
        app,
        [
            "script",
            str(project),
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--provider",
            "openai_compatible",
            "--json",
        ],
    )

    assert result.exit_code == 0
    script_json = (project / "artifacts" / "script.json").read_text(encoding="utf-8")
    assert '"provider_id": "openai_compatible"' in script_json
    assert '"provider_is_mock": false' in script_json
    assert "OpenAI CLI-free 文案" in script_json


def test_cli_voice_uses_openai_compatible_tts_provider(tmp_path, monkeypatch):
    project = tmp_path / "openai语音项目"
    monkeypatch.setenv("OPENAI_TTS_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_TTS_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_TTS_MODEL", "tts-model")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"OPENAI AUDIO"

    monkeypatch.setattr(
        "providers.openai_compatible.urlopen",
        lambda request, timeout: FakeResponse(),
    )
    runner.invoke(app, ["init", str(project), "--name", "OpenAI Voice", "--json"])

    result = runner.invoke(
        app,
        [
            "voice",
            str(project),
            "--provider",
            "openai_compatible_tts",
            "--voice",
            "alloy",
            "--json",
        ],
    )

    assert result.exit_code == 0
    voice_json = (project / "artifacts" / "voice_plan.json").read_text(encoding="utf-8")
    assert '"provider_id": "openai_compatible_tts"' in voice_json
    assert '"provider_is_mock": false' in voice_json
    assert (project / "artifacts" / "voice_segments" / "s1.wav").read_bytes() == b"OPENAI AUDIO"


def test_cli_rejects_unknown_provider(tmp_path):
    project = tmp_path / "unknown项目"
    runner.invoke(app, ["init", str(project), "--name", "Unknown项目", "--json"])

    result = runner.invoke(
        app,
        [
            "script",
            str(project),
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--provider",
            "not-a-provider",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert '"error_code": "PROVIDER_NOT_CONFIGURED"' in result.output


def test_cli_ingest_url_and_image_contracts(tmp_path, monkeypatch):
    project = tmp_path / "asset项目"
    image_file = tmp_path / "screen.png"
    image_file.write_text("stub", encoding="utf-8")
    runner.invoke(app, ["init", str(project), "--name", "Asset项目", "--json"])
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main._capture_url_screenshot",
        lambda ref, url: {"screenshot_status": "unavailable"},
    )

    url_result = runner.invoke(
        app,
        [
            "ingest",
            "url",
            str(project),
            "--url",
            "https://example.com/article",
            "--screenshot",
            "--json",
        ],
    )
    assert url_result.exit_code == 0
    assert '"is_untrusted_input": true' in url_result.output
    assert '"screenshot_opt_in": true' in url_result.output
    assert '"screenshot_status": "unavailable"' in url_result.output

    image_result = runner.invoke(
        app,
        [
            "ingest",
            "image",
            str(project),
            "--file",
            str(image_file),
            "--role",
            "screenshot",
            "--json",
        ],
    )
    assert image_result.exit_code == 0
    assert '"role": "screenshot"' in image_result.output
    assert str(image_file) not in image_result.output
    assert '"original_path_redacted": true' in image_result.output
    assert '"publish_grade_visual_candidate": false' in image_result.output
    input_assets = json.loads((project / "assets" / "input_assets.json").read_text())
    image_item = input_assets[-1]
    assert image_item["source_uri"].startswith("assets/reference_images/screenshot-")
    assert image_item["source_uri"].endswith(".png")
    assert image_item["original_path_redacted"] is True
    assert image_item["publish_grade_visual_candidate"] is False
    assert (project / image_item["source_uri"]).read_text(encoding="utf-8") == "stub"
    manifest = collect_evidence_assets(ProjectRef(project, project.name))
    image_asset = next(
        asset
        for asset in manifest["assets"]
        if asset["evidence_type"] == "screenshot_capture"
    )
    assert image_asset["path"] == image_item["source_uri"]
    assert image_asset["asset_kind"] == "static_image_reference"
    assert image_asset["publish_grade_visual_candidate"] is False


def test_collect_evidence_assets_marks_screenshot_inputs(tmp_path):
    project = init_project(tmp_path / "screenshot-input", "项目")
    screenshot = project.path / "assets" / "screen.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"png")
    (project.path / "assets" / "input_assets.json").write_text(
        json.dumps(
            [
                {
                    "type": "image",
                    "source_uri": str(screenshot),
                    "role": "screenshot",
                },
                {
                    "type": "url",
                    "source_uri": "https://example.com",
                    "screenshot_opt_in": True,
                    "is_untrusted_input": True,
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manifest = collect_evidence_assets(project)

    by_type = {asset["evidence_type"]: asset for asset in manifest["assets"]}
    assert by_type["screenshot_capture"]["role"] == "screenshot"
    assert by_type["screenshot_capture"]["path"] == "assets/screen.png"
    assert by_type["screenshot_capture"]["asset_kind"] == "static_image_reference"
    assert by_type["screenshot_capture"]["publish_grade_visual_candidate"] is False
    assert by_type["web_source"]["screenshot_requested"] is True
    assert by_type["web_source"]["publish_grade_visual_candidate"] is False


def test_cli_ingest_url_captures_screenshot_asset(tmp_path, monkeypatch):
    project = tmp_path / "url截图项目"
    runner.invoke(app, ["init", str(project), "--name", "URL截图项目", "--json"])

    def fake_capture(ref, url):
        screenshot = ref.path / "assets" / "web_screenshots" / "url-test.png"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot.write_bytes(b"png")
        return {
            "screenshot_status": "captured",
            "screenshot_path": "assets/web_screenshots/url-test.png",
            "screenshot_tool": "playwright",
            "asset_kind": "static_image_reference",
            "publish_grade_visual_candidate": False,
            "screenshot_note_zh": (
                "网页截图只能作为画面参考或证据线索;"
                "发布级镜头仍需要动态视频素材或真实视频生成器输出。"
            ),
        }

    monkeypatch.setattr("apps.cli.lingjian_cli.main._capture_url_screenshot", fake_capture)

    result = runner.invoke(
        app,
        [
            "ingest",
            "url",
            str(project),
            "--url",
            "https://github.com/dososo/blcaptain-lingjian-video",
            "--screenshot",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"screenshot_status": "captured"' in result.output
    assert '"screenshot_path": "assets/web_screenshots/url-test.png"' in result.output
    assert '"publish_grade_visual_candidate": false' in result.output
    assert '"asset_kind": "static_image_reference"' in result.output
    manifest = collect_evidence_assets(ProjectRef(project, project.name))
    by_id = {asset["id"]: asset for asset in manifest["assets"]}
    assert by_id["input-01"]["evidence_type"] == "github_repo"
    assert by_id["input-01-screenshot"]["evidence_type"] == "screenshot_capture"
    assert by_id["input-01-screenshot"]["path"] == "assets/web_screenshots/url-test.png"
    assert by_id["input-01-screenshot"]["source_uri"] == (
        "https://github.com/dososo/blcaptain-lingjian-video"
    )
    assert by_id["input-01-screenshot"]["asset_kind"] == "static_image_reference"
    assert by_id["input-01-screenshot"]["publish_grade_visual_candidate"] is False
    assert "发布级镜头仍需要动态视频素材" in by_id["input-01-screenshot"]["next_action_zh"]


def test_cli_ingest_url_captures_recording_asset(tmp_path, monkeypatch):
    project = tmp_path / "url录屏项目"
    runner.invoke(app, ["init", str(project), "--name", "URL录屏项目", "--json"])

    def fake_record(ref, url):
        recording = ref.path / "assets" / "web_recordings" / "url-test.mp4"
        recording.parent.mkdir(parents=True, exist_ok=True)
        recording.write_bytes(b"mp4")
        return {
            "recording_status": "captured",
            "recording_path": "assets/web_recordings/url-test.mp4",
            "recording_tool": "fake-recorder",
            "source_video_probe_status": "verifiable",
            "source_video_has_video_stream": True,
            "publish_grade_visual_candidate": True,
        }

    monkeypatch.setattr("apps.cli.lingjian_cli.main._capture_url_recording", fake_record)

    result = runner.invoke(
        app,
        [
            "ingest",
            "url",
            str(project),
            "--url",
            "https://github.com/dososo/blcaptain-lingjian-video",
            "--record",
            "--scene-id",
            "s2",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"recording_status": "captured"' in result.output
    assert '"recording_path": "assets/web_recordings/url-test.mp4"' in result.output
    assert '"target_scene_id": "s2"' in result.output
    payload = json.loads(result.output)
    run_command = f"uv run lj run {shlex.quote(str(project))} --release --json"
    assert payload["next_action_zh"].startswith("已获得可验证的网页动态录屏")
    assert payload["next_command"] == run_command
    input_assets = json.loads(
        (project / "assets" / "input_assets.json").read_text(encoding="utf-8")
    )
    assert input_assets[0]["target_scene_id"] == "s2"
    assert input_assets[0]["next_command"] == run_command
    _patch_evidence_recording_ffprobe(monkeypatch)
    manifest = collect_evidence_assets(ProjectRef(project, project.name))
    by_id = {asset["id"]: asset for asset in manifest["assets"]}
    recording = by_id["input-01-recording"]
    assert recording["evidence_type"] == "web_recording_capture"
    assert recording["path"] == "assets/web_recordings/url-test.mp4"
    assert recording["recording_status"] == "captured"
    assert recording["source_video_probe_status"] == "verifiable"
    assert recording["publish_grade_visual_candidate"] is True
    assert recording["target_scene_id"] == "s2"
    assert recording["next_command"] == run_command
    refs_for_s1 = evidence_assets_for_scene(
        manifest,
        expected_real_evidence=["github_repo_star_capture"],
        scene_id="s1",
        project=ProjectRef(project, project.name),
    )
    refs_for_s2 = evidence_assets_for_scene(
        manifest,
        expected_real_evidence=["github_repo_star_capture"],
        scene_id="s2",
        project=ProjectRef(project, project.name),
    )
    assert not any(ref["evidence_type"] == "web_recording_capture" for ref in refs_for_s1)
    assert any(ref["evidence_type"] == "web_recording_capture" for ref in refs_for_s2)
    matched_ref = next(
        ref for ref in refs_for_s2 if ref["evidence_type"] == "web_recording_capture"
    )
    assert matched_ref["next_command"] == "uv run lj run <project> --release --json"
    assert str(project) not in json.dumps(matched_ref, ensure_ascii=False)


def test_cli_ingest_url_appends_without_overwriting_existing_assets(
    tmp_path, monkeypatch
):
    project = tmp_path / "url追加项目"
    input_file = tmp_path / "input.md"
    input_file.write_text("灵剪开源产品介绍内容依据。", encoding="utf-8")
    runner.invoke(app, ["init", str(project), "--name", "URL追加项目", "--json"])
    text_result = runner.invoke(
        app,
        ["ingest", "text", str(project), "--file", str(input_file), "--json"],
    )
    assert text_result.exit_code == 0

    def fake_record(ref, url):
        slug = "readme" if "readme" in url else "star"
        recording = ref.path / "assets" / "web_recordings" / f"{slug}.mp4"
        recording.parent.mkdir(parents=True, exist_ok=True)
        recording.write_bytes(b"mp4")
        return {
            "recording_status": "captured",
            "recording_path": f"assets/web_recordings/{slug}.mp4",
            "recording_tool": "fake-recorder",
            "source_video_probe_status": "verifiable",
            "source_video_has_video_stream": True,
            "publish_grade_visual_candidate": True,
        }

    monkeypatch.setattr("apps.cli.lingjian_cli.main._capture_url_recording", fake_record)

    readme_result = runner.invoke(
        app,
        [
            "ingest",
            "url",
            str(project),
            "--url",
            "https://github.com/dososo/blcaptain-lingjian-video#readme",
            "--record",
            "--scene-id",
            "s2",
            "--json",
        ],
    )
    star_result = runner.invoke(
        app,
        [
            "ingest",
            "url",
            str(project),
            "--url",
            "https://github.com/dososo/blcaptain-lingjian-video/stargazers",
            "--record",
            "--scene-id",
            "s5",
            "--json",
        ],
    )

    assert readme_result.exit_code == 0
    assert star_result.exit_code == 0
    input_assets = json.loads((project / "assets" / "input_assets.json").read_text())
    assert [asset["type"] for asset in input_assets] == ["text", "url", "url"]
    assert input_assets[1]["target_scene_id"] == "s2"
    assert input_assets[2]["target_scene_id"] == "s5"
    _patch_evidence_recording_ffprobe(monkeypatch)
    manifest = collect_evidence_assets(ProjectRef(project, project.name))
    refs_for_s2 = evidence_assets_for_scene(
        manifest,
        expected_real_evidence=["readme_install_capture"],
        scene_id="s2",
    )
    refs_for_s5 = evidence_assets_for_scene(
        manifest,
        expected_real_evidence=["github_repo_star_capture"],
        scene_id="s5",
    )
    assert any(ref["path"] == "assets/web_recordings/readme.mp4" for ref in refs_for_s2)
    assert any(ref["path"] == "assets/web_recordings/star.mp4" for ref in refs_for_s5)


def test_capture_url_screenshot_uses_playwright_cli(tmp_path, monkeypatch):
    project = init_project(tmp_path / "playwright-capture", "项目")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"png")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.delenv("LINGJIAN_WEB_SCREENSHOT_CLI", raising=False)
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.shutil.which",
        lambda name: "/usr/bin/playwright" if name == "playwright" else None,
    )
    monkeypatch.setattr("apps.cli.lingjian_cli.main.subprocess.run", fake_run)

    result = _capture_url_screenshot(project, "https://example.com")

    assert result["screenshot_status"] == "captured"
    assert result["screenshot_tool"] == "playwright"
    assert result["screenshot_path"].startswith("assets/web_screenshots/url-")
    assert result["asset_kind"] == "static_image_reference"
    assert result["publish_grade_visual_candidate"] is False
    assert "发布级镜头仍需要动态视频素材" in result["screenshot_note_zh"]
    assert (project.path / result["screenshot_path"]).exists()
    assert commands[0][:2] == ["/usr/bin/playwright", "screenshot"]
    assert "--viewport-size" in commands[0]
    assert "1080,1920" in commands[0]


def test_capture_url_recording_uses_custom_cli(tmp_path, monkeypatch):
    project = init_project(tmp_path / "web-recording", "项目")
    recorder = tmp_path / "fake-recorder"
    recorder.write_text("#!/bin/sh\nprintf mp4 > \"$2\"\n", encoding="utf-8")
    recorder.chmod(0o755)

    monkeypatch.setenv("LINGJIAN_WEB_RECORD_CLI", str(recorder))
    _patch_cli_recording_probe(monkeypatch)

    result = _capture_url_recording(project, "https://example.com")

    assert result["recording_status"] == "captured"
    assert result["recording_tool"] == "fake-recorder"
    assert result["recording_path"].startswith("assets/web_recordings/url-")
    assert result["publish_grade_visual_candidate"] is True
    assert result["source_video_probe_status"] == "verifiable"
    assert (project.path / result["recording_path"]).exists()


def test_capture_url_recording_uses_default_hyperframes_adapter(tmp_path, monkeypatch):
    project = init_project(tmp_path / "web-recording-default", "项目")
    monkeypatch.delenv("LINGJIAN_WEB_RECORD_CLI", raising=False)
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"npx", "ffmpeg"} else None,
    )

    def fake_record(command, **kwargs):
        assert command[0] == sys.executable
        assert command[-3].endswith("hyperframes_web_record_cli.py")
        Path(command[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    monkeypatch.setattr("apps.cli.lingjian_cli.main.subprocess.run", fake_record)
    _patch_cli_recording_probe(monkeypatch)

    result = _capture_url_recording(project, "https://example.com")

    assert result["recording_status"] == "captured"
    assert result["recording_tool"] == "hyperframes-capture-scroll"
    assert result["recording_path"].startswith("assets/web_recordings/url-")
    assert result["publish_grade_visual_candidate"] is True
    assert result["source_video_probe_status"] == "verifiable"
    assert (project.path / result["recording_path"]).exists()


def test_capture_url_recording_probe_failure_is_not_captured(tmp_path, monkeypatch):
    project = init_project(tmp_path / "web-recording-probe-failed", "项目")
    recorder = tmp_path / "fake-recorder"
    recorder.write_text("#!/bin/sh\nprintf not-video > \"$2\"\n", encoding="utf-8")
    recorder.chmod(0o755)

    monkeypatch.setenv("LINGJIAN_WEB_RECORD_CLI", str(recorder))
    _patch_cli_recording_probe(monkeypatch, has_video_stream=False)

    result = _capture_url_recording(project, "https://example.com")

    assert result["recording_status"] == "not_verifiable"
    assert result["recording_path"].startswith("assets/web_recordings/url-")
    assert result["publish_grade_visual_candidate"] is False
    assert result["source_video_probe_status"] == "not_verifiable"
    assert (project.path / result["recording_path"]).exists()


def test_cli_ingest_url_screenshot_failure_does_not_fake_asset(tmp_path, monkeypatch):
    project = tmp_path / "url截图失败项目"
    runner.invoke(app, ["init", str(project), "--name", "URL截图失败项目", "--json"])
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main._capture_url_screenshot",
        lambda ref, url: {
            "screenshot_status": "failed",
            "screenshot_error": "browser missing",
            "screenshot_hint_zh": "网页截图未成功落盘;不会把该 URL 伪装成已截图。",
        },
    )

    result = runner.invoke(
        app,
        [
            "ingest",
            "url",
            str(project),
            "--url",
            "https://example.com/article",
            "--screenshot",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"screenshot_status": "failed"' in result.output
    manifest = collect_evidence_assets(ProjectRef(project, project.name))
    assert [asset["evidence_type"] for asset in manifest["assets"]] == ["web_source"]
    assert manifest["assets"][0]["screenshot_requested"] is True


def test_cli_ingest_url_recording_failure_does_not_fake_asset(tmp_path, monkeypatch):
    project = tmp_path / "url录屏失败项目"
    runner.invoke(app, ["init", str(project), "--name", "URL录屏失败项目", "--json"])
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main._capture_url_recording",
        lambda ref, url: {
            "recording_status": "failed",
            "recording_error": "recorder missing",
            "recording_hint_zh": "网页录屏未成功落盘;不会把该 URL 伪装成已录屏。",
        },
    )

    result = runner.invoke(
        app,
        [
            "ingest",
            "url",
            str(project),
            "--url",
            "https://example.com/article",
            "--record",
            "--scene-id",
            "s3",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"recording_status": "failed"' in result.output
    payload = json.loads(result.output)
    assert payload["next_action_zh"].startswith("还没有形成可发布的网页动态录屏")
    assert "uv run lj ingest video" in payload["next_command"]
    assert "--role web_recording" in payload["next_command"]
    assert "--scene-id s3" in payload["next_command"]
    assert "把网页录屏文件拖到这里.mp4" in payload["next_command"]
    input_assets = json.loads(
        (project / "assets" / "input_assets.json").read_text(encoding="utf-8")
    )
    assert input_assets[0]["target_scene_id"] == "s3"
    assert input_assets[0]["next_command"] == payload["next_command"]
    manifest = collect_evidence_assets(ProjectRef(project, project.name))
    assert [asset["evidence_type"] for asset in manifest["assets"]] == ["web_source"]
    assert manifest["assets"][0]["recording_requested"] is True


def test_materialize_evidence_clips_uses_captured_web_recording(tmp_path, monkeypatch):
    project = init_project(tmp_path / "web-recording-evidence", "项目")
    recording = project.path / "assets" / "web_recordings" / "github.mp4"
    recording.parent.mkdir(parents=True, exist_ok=True)
    recording.write_bytes(b"mp4")
    manifest = {
        "version": "v1",
        "assets": [
            {
                "id": "input-01-recording",
                "evidence_type": "web_recording_capture",
                "path": "assets/web_recordings/github.mp4",
                "source_uri": "https://github.com/dososo/blcaptain-lingjian-video",
            }
        ],
        "evidence_types": ["web_recording_capture"],
        "count": 1,
    }
    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )

    def fake_run(command, **kwargs):
        assert command[0] == "/usr/bin/ffprobe"
        if "format=duration" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"format":{"duration":"2.4"}}',
                stderr="",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"streams":[{"codec_type":"video"}]}',
            stderr="",
        )

    monkeypatch.setattr("packages.core.evidence_assets.subprocess.run", fake_run)

    updated = materialize_evidence_clips(project, manifest)

    asset = updated["assets"][0]
    assert asset["evidence_clip_status"] == "captured"
    assert asset["materialized_evidence_video"] is True
    assert asset["publish_grade_evidence_video"] is True
    assert asset["evidence_clip_path"] == "assets/web_recordings/github.mp4"
    assert asset["evidence_clip_render_source"] == "source_video_capture"
    assert asset["evidence_visual_source"] == "web_recording_video"
    assert asset["source_video_duration_sec"] == 2.4
    assert asset["evidence_clip_duration_sec"] == 2.4
    assert updated["evidence_clip_summary"]["render_sources"] == ["source_video_capture"]


def test_cli_ingest_video_copies_terminal_recording_without_original_path(tmp_path):
    project = tmp_path / "终端录屏项目"
    source_video = tmp_path / "private-terminal.mov"
    source_video.write_bytes(b"mov")
    runner.invoke(app, ["init", str(project), "--name", "终端录屏项目", "--json"])

    result = runner.invoke(
        app,
        [
            "ingest",
            "video",
            str(project),
            "--file",
            str(source_video),
            "--role",
            "terminal_recording",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert str(source_video) not in result.output
    assert '"original_path_redacted": true' in result.output
    input_assets = json.loads(
        (project / "assets" / "input_assets.json").read_text(encoding="utf-8")
    )
    item = input_assets[0]
    assert item["type"] == "video"
    assert item["role"] == "terminal_recording"
    assert item["source_uri"].startswith("assets/evidence/videos/terminal_recording-")
    assert item["source_uri"].endswith(".mov")
    assert str(source_video) not in json.dumps(input_assets, ensure_ascii=False)
    assert (project / item["source_uri"]).read_bytes() == b"mov"

    manifest = collect_evidence_assets(ProjectRef(project, project.name))
    asset = manifest["assets"][0]
    assert asset["evidence_type"] == "terminal_recording_capture"
    assert asset["path"] == item["source_uri"]


def test_cli_ingest_video_records_verifiable_probe_status(tmp_path, monkeypatch):
    project = tmp_path / "可验证录屏项目"
    source_video = tmp_path / "screen.mp4"
    source_video.write_bytes(b"mp4")
    runner.invoke(app, ["init", str(project), "--name", "可验证录屏项目", "--json"])
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"streams":[{"codec_type":"video"}],"format":{"duration":"3.25"}}'
            ),
            stderr="",
        )

    monkeypatch.setattr("apps.cli.lingjian_cli.main.subprocess.run", fake_run)

    result = runner.invoke(
        app,
        [
            "ingest",
            "video",
            str(project),
            "--file",
            str(source_video),
            "--role",
            "screen_recording",
            "--scene-id",
            "s2",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"source_video_probe_status": "verifiable"' in result.output
    assert '"source_video_has_video_stream": true' in result.output
    assert '"recording_status": "captured"' in result.output
    assert '"publish_grade_visual_candidate": true' in result.output
    payload = json.loads(result.output)
    assert payload["recording_status"] == "captured"
    assert payload["next_action_zh"].startswith("已收到可验证的视频素材")
    run_command = f"uv run lj run {shlex.quote(str(project))} --release --json"
    assert payload["next_command"] == run_command
    input_assets = json.loads(
        (project / "assets" / "input_assets.json").read_text(encoding="utf-8")
    )
    assert input_assets[0]["source_video_probe_status"] == "verifiable"
    assert input_assets[0]["recording_status"] == "captured"
    assert input_assets[0]["source_video_duration_sec"] == 3.25
    assert input_assets[0]["publish_grade_visual_candidate"] is True
    assert input_assets[0]["target_scene_id"] == "s2"
    assert input_assets[0]["next_command"] == run_command
    manifest = collect_evidence_assets(ProjectRef(project, project.name))
    asset = manifest["assets"][0]
    assert asset["source_video_probe_status"] == "verifiable"
    assert asset["recording_status"] == "captured"
    assert asset["source_video_has_video_stream"] is True
    assert asset["source_video_duration_sec"] == 3.25
    assert asset["evidence_clip_duration_sec"] == 3.25
    assert asset["source_video_probe_tool"] == "ffprobe"
    assert asset["publish_grade_visual_candidate"] is True
    assert asset["target_scene_id"] == "s2"
    assert asset["next_command"] == run_command
    assert asset["next_action_zh"].startswith("已收到可验证的视频素材")


def test_cli_ingest_video_records_unverifiable_probe_status(tmp_path, monkeypatch):
    project = tmp_path / "坏录屏项目"
    source_video = tmp_path / "bad.mp4"
    source_video.write_bytes(b"not video")
    runner.invoke(app, ["init", str(project), "--name", "坏录屏项目", "--json"])
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="Invalid data")

    monkeypatch.setattr("apps.cli.lingjian_cli.main.subprocess.run", fake_run)

    result = runner.invoke(
        app,
        [
            "ingest",
            "video",
            str(project),
            "--file",
            str(source_video),
            "--role",
            "screen_recording",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"source_video_probe_status": "not_verifiable"' in result.output
    assert '"source_video_has_video_stream": false' in result.output
    assert '"recording_status": "not_verifiable"' in result.output
    assert '"publish_grade_visual_candidate": false' in result.output
    payload = json.loads(result.output)
    assert payload["recording_status"] == "not_verifiable"
    assert payload["next_action_zh"].startswith("这个视频还不能作为发布级动态素材候选")
    assert "uv run lj ingest video" in payload["next_command"]
    assert "--role screen_recording" in payload["next_command"]
    assert "换成可验证视频.mp4" in payload["next_command"]
    input_assets = json.loads(
        (project / "assets" / "input_assets.json").read_text(encoding="utf-8")
    )
    assert input_assets[0]["source_video_probe_status"] == "not_verifiable"
    assert input_assets[0]["recording_status"] == "not_verifiable"
    assert input_assets[0]["publish_grade_visual_candidate"] is False
    assert "换成可验证视频.mp4" in input_assets[0]["next_command"]
    manifest = collect_evidence_assets(ProjectRef(project, project.name))
    asset = manifest["assets"][0]
    assert asset["source_video_probe_status"] == "not_verifiable"
    assert asset["recording_status"] == "not_verifiable"
    assert asset["source_video_has_video_stream"] is False
    assert asset["source_video_probe_error"] == "Invalid data"
    assert asset["publish_grade_visual_candidate"] is False
    assert "换成可验证视频.mp4" in asset["next_command"]
    assert asset["next_action_zh"].startswith("这个视频还不能作为发布级动态素材候选")


def test_materialize_evidence_clips_uses_captured_terminal_and_codex_video(tmp_path, monkeypatch):
    project = init_project(tmp_path / "operation-recording-evidence", "项目")
    terminal_video = project.path / "assets" / "evidence" / "videos" / "terminal.mp4"
    codex_video = project.path / "assets" / "evidence" / "videos" / "codex.mp4"
    terminal_video.parent.mkdir(parents=True, exist_ok=True)
    terminal_video.write_bytes(b"terminal")
    codex_video.write_bytes(b"codex")
    manifest = {
        "version": "v1",
        "assets": [
            {
                "id": "terminal",
                "evidence_type": "terminal_recording_capture",
                "path": "assets/evidence/videos/terminal.mp4",
                "source_uri": "assets/evidence/videos/terminal.mp4",
            },
            {
                "id": "codex",
                "evidence_type": "codex_operation_recording",
                "path": "assets/evidence/videos/codex.mp4",
                "source_uri": "assets/evidence/videos/codex.mp4",
            },
        ],
        "evidence_types": ["codex_operation_recording", "terminal_recording_capture"],
        "count": 2,
    }
    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )

    def fake_run(command, **kwargs):
        assert command[0] == "/usr/bin/ffprobe"
        if "format=duration" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"format":{"duration":"2.4"}}',
                stderr="",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"streams":[{"codec_type":"video"}]}',
            stderr="",
        )

    monkeypatch.setattr("packages.core.evidence_assets.subprocess.run", fake_run)

    updated = materialize_evidence_clips(project, manifest)

    by_type = {asset["evidence_type"]: asset for asset in updated["assets"]}
    assert by_type["terminal_recording_capture"]["evidence_clip_status"] == "captured"
    assert by_type["terminal_recording_capture"]["materialized_evidence_video"] is True
    assert by_type["terminal_recording_capture"]["publish_grade_evidence_video"] is True
    assert by_type["terminal_recording_capture"]["source_video_duration_sec"] == 2.4
    assert by_type["terminal_recording_capture"]["evidence_clip_duration_sec"] == 2.4
    assert by_type["terminal_recording_capture"]["evidence_visual_source"] == (
        "terminal_recording_video"
    )
    assert by_type["codex_operation_recording"]["evidence_clip_status"] == "captured"
    assert by_type["codex_operation_recording"]["materialized_evidence_video"] is True
    assert by_type["codex_operation_recording"]["publish_grade_evidence_video"] is True
    assert by_type["codex_operation_recording"]["source_video_duration_sec"] == 2.4
    assert by_type["codex_operation_recording"]["evidence_clip_duration_sec"] == 2.4
    assert by_type["codex_operation_recording"]["evidence_visual_source"] == "codex_operation_video"
    assert updated["evidence_clip_summary"]["render_sources"] == ["source_video_capture"]


def test_materialize_evidence_clips_rejects_unverifiable_recording(tmp_path, monkeypatch):
    project = init_project(tmp_path / "bad-recording-evidence", "项目")
    recording = project.path / "assets" / "evidence" / "videos" / "terminal.mp4"
    recording.parent.mkdir(parents=True, exist_ok=True)
    recording.write_bytes(b"not-video")
    manifest = {
        "version": "v1",
        "assets": [
            {
                "id": "terminal",
                "evidence_type": "terminal_recording_capture",
                "path": "assets/evidence/videos/terminal.mp4",
                "source_uri": "assets/evidence/videos/terminal.mp4",
            }
        ],
        "evidence_types": ["terminal_recording_capture"],
        "count": 1,
    }
    monkeypatch.setattr(
        "packages.core.evidence_assets.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )
    monkeypatch.setattr(
        "packages.core.evidence_assets.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout='{"streams":[{"codec_type":"audio"}]}',
            stderr="",
        ),
    )

    updated = materialize_evidence_clips(project, manifest)

    asset = updated["assets"][0]
    assert asset["evidence_clip_status"] == "not_verifiable"
    assert asset["materialized_evidence_video"] is False
    assert asset["publish_grade_evidence_video"] is False
    assert "ffprobe" in asset["evidence_clip_error"]


def test_cli_ingest_video_rejects_unsupported_format(tmp_path):
    project = tmp_path / "视频格式项目"
    source_video = tmp_path / "capture.gif"
    source_video.write_bytes(b"gif")
    runner.invoke(app, ["init", str(project), "--name", "视频格式项目", "--json"])

    result = runner.invoke(
        app,
        [
            "ingest",
            "video",
            str(project),
            "--file",
            str(source_video),
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert '"error_code": "INPUT_VIDEO_UNSUPPORTED_FORMAT"' in result.output


def test_collect_evidence_assets_collects_project_terminal_logs(tmp_path):
    project = init_project(tmp_path / "terminal-input", "项目")
    terminal_log = project.path / "logs" / "release.log"
    terminal_log.write_text("uv run lj render --release", encoding="utf-8")

    manifest = collect_evidence_assets(project)

    by_type = {asset["evidence_type"]: asset for asset in manifest["assets"]}
    assert by_type["terminal_log_capture"]["path"] == "logs/release.log"
    assert by_type["terminal_log_capture"]["origin"] == "artifact"


def test_cli_export_all_platforms_uses_existing_release_guard(tmp_path):
    project = tmp_path / "all平台项目"
    input_file = tmp_path / "input.txt"
    input_file.write_text("灵剪是一款面向中文创作者的视频生产工作台。", encoding="utf-8")

    runner.invoke(app, ["init", str(project), "--name", "All平台项目", "--json"])
    runner.invoke(app, ["ingest", "text", str(project), "--file", str(input_file), "--json"])
    runner.invoke(
        app,
        [
            "script",
            str(project),
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--provider",
            "mock",
            "--json",
        ],
    )
    runner.invoke(app, ["approve", "script", str(project), "--approved-by", "tester", "--json"])
    runner.invoke(app, ["voice", str(project), "--provider", "mock", "--voice", "v1", "--json"])
    runner.invoke(app, ["approve", "voice", str(project), "--approved-by", "tester", "--json"])
    runner.invoke(app, ["visuals", str(project), "--engine", "ffmpeg_card", "--json"])
    runner.invoke(app, ["approve", "visuals", str(project), "--approved-by", "tester", "--json"])
    runner.invoke(
        app,
        [
            "render",
            str(project),
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
    )

    result = runner.invoke(
        app,
        [
            "export",
            str(project),
            "--all-platforms",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"exports"' in result.output


def _init_extracted_project(tmp_path: Path) -> Path:
    """初始化一个已 ingest+extract 的项目,供脚本关测试。"""
    project = tmp_path / "hostproj"
    init_project(project, "宿主自产测试")
    (project / "sources").mkdir(parents=True, exist_ok=True)
    src = project / "sources" / "brief.txt"
    src.write_text("灵剪是一个可审计的短视频生产 skill,一句话进,每一关都能审。", encoding="utf-8")
    runner.invoke(app, ["ingest", "text", str(project), "--file", str(src), "--json"])
    runner.invoke(app, ["extract", str(project), "--json"])
    return project


_SCRIPT_ARGS = [
    "--type", "product", "--platform", "douyin", "--language", "zh-CN",
    "--ratio", "9:16", "--duration", "30", "--style", "vox_cut",
    "--profile", "product_intro",
]


def test_script_emit_contract_writes_brief_for_host_authoring(tmp_path):
    project = _init_extracted_project(tmp_path)
    result = runner.invoke(
        app, ["script", str(project), *_SCRIPT_ARGS, "--emit-contract", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "contract_emitted"
    contract = json.loads(
        (project / "artifacts" / "script_contract.json").read_text(encoding="utf-8")
    )
    # 契约必须带风格锁 + 钩子库,宿主才能按稿创作对得上风格
    assert "style_lock" in contract and "hook_library" in contract
    assert "authoring_note_zh" in contract
    # emit-contract 不产脚本
    assert not (project / "artifacts" / "script.json").exists()


def test_script_from_file_writes_host_authored_script(tmp_path):
    project = _init_extracted_project(tmp_path)
    authored = project / "authored.json"
    authored.write_text(
        json.dumps(
            {
                "scenes": [
                    {"id": "s1", "narration_text": "你说一句话,它就出一条能直接发的短视频。"},
                    {"id": "s2", "narration_text": "但每一关都摆给你审,不是黑箱摇骰子。"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["script", str(project), *_SCRIPT_ARGS, "--from-file", str(authored), "--json"]
    )
    assert result.exit_code == 0, result.output
    script = json.loads(
        (project / "artifacts" / "script.json").read_text(encoding="utf-8")
    )
    # 宿主自产:非 mock,provider 记为 host_authored,场景保真
    assert script["provider_id"] == "host_authored"
    assert script["provider_is_mock"] is False
    assert len(script["scenes"]) == 2
    assert "一句话" in script["scenes"][0]["narration_text"]


def test_script_from_file_rejects_thin_scenes(tmp_path):
    project = _init_extracted_project(tmp_path)
    thin = project / "thin.json"
    thin.write_text(json.dumps({"scenes": []}, ensure_ascii=False), encoding="utf-8")
    result = runner.invoke(
        app, ["script", str(project), *_SCRIPT_ARGS, "--from-file", str(thin), "--json"]
    )
    # 校验门:空/过薄脚本必须被挡下,不写产物
    assert result.exit_code != 0
    assert not (project / "artifacts" / "script.json").exists()


def test_run_script_provider_host_pauses_for_authoring(tmp_path):
    project = tmp_path / "runhost"
    src = tmp_path / "brief.txt"
    src.write_text("灵剪:一句话进,每一关都能审的短视频。", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "run", str(project), "--name", "聚合宿主自产",
            "--input-file", str(src), "--script-provider", "host",
            "--style", "vox_cut", "--profile", "product_intro", "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "awaiting_host_authoring"
    assert payload["artifact"] == "artifacts/script_contract.json"
    # 暂停待宿主自产:不 fork 外部 CLI,不写占位脚本
    assert (project / "artifacts" / "script_contract.json").exists()
    assert not (project / "artifacts" / "script.json").exists()
