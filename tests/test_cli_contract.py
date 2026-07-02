import json

from typer.testing import CliRunner

from apps.cli.lingjian_cli.main import app

runner = CliRunner()


def test_render_help_has_no_force_option():
    result = runner.invoke(app, ["render", "--help"])

    assert result.exit_code == 0
    assert "--force" not in result.output


def test_release_commands_expose_strict_option():
    assert "--strict" in runner.invoke(app, ["qa", "--help"]).output
    assert "--strict" in runner.invoke(app, ["export", "--help"]).output
    assert "--strict" in runner.invoke(app, ["run", "--help"]).output


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
    assert (project / "artifacts" / "script.json").exists()
    assert not (project / "artifacts" / "approvals.json").exists()


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
    voice_json = (project / "artifacts" / "voice_plan.json").read_text(encoding="utf-8")
    assert '"provider_id": "user_audio"' in voice_json
    assert '"provider_is_mock": false' in voice_json
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
    voice_json = (project / "artifacts" / "voice_plan.json").read_text(encoding="utf-8")
    assert '"provider_id": "user_audio"' in voice_json
    assert '"provider_is_mock": false' in voice_json
    assert '"source_type": "user-recorded-audio"' in voice_json
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


def test_cli_ingest_url_and_image_contracts(tmp_path):
    project = tmp_path / "asset项目"
    image_file = tmp_path / "screen.png"
    image_file.write_text("stub", encoding="utf-8")
    runner.invoke(app, ["init", str(project), "--name", "Asset项目", "--json"])

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
