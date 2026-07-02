import json
from pathlib import Path

from typer.testing import CliRunner

from apps.cli.lingjian_cli.main import app
from packages.core.doctor import run_doctor
from providers.registry import resolve_provider

runner = CliRunner()


def _fake_executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_capability_detection_prefers_inherited_llm_cli_and_local_tts(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "claude", "#!/bin/sh\nprintf '继承订阅脚本输出'\n")
    _fake_executable(
        bin_dir / "say",
        "#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n"
        "if [ \"$1\" = '-o' ]; then shift; out=\"$1\"; fi\nshift\ndone\n"
        "printf 'LOCAL AUDIO' > \"$out\"\n",
    )
    monkeypatch.setenv("PATH", str(bin_dir))

    result = runner.invoke(app, ["setup", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["capabilities"]["llm"]["best"]["id"] == "claude_cli"
    assert payload["capabilities"]["llm"]["best"]["source_type"] == "inherited-cli"
    assert payload["capabilities"]["tts"]["best"]["id"] == "macos_say"
    assert payload["capabilities"]["tts"]["best"]["source_type"] == "local-cli"
    assert "无需 key" in payload["summary_zh"]


def test_doctor_uses_inherited_capabilities_without_api_key(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "claude", "#!/bin/sh\nprintf '继承订阅脚本输出'\n")
    _fake_executable(bin_dir / "say", "#!/bin/sh\nprintf 'audio' > \"$3\"\n")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_TTS_API_KEY", raising=False)

    result = run_doctor(
        tool_overrides={
            "ffmpeg": True,
            "ffprobe": True,
            "ffmpeg_drawtext": True,
            "cjk_font": True,
        }
    )

    assert result.ready is True
    assert result.providers["llm"].methods[0].id == "claude_cli"
    assert result.providers["llm"].methods[0].source_type == "inherited-cli"
    assert result.providers["tts"].methods[0].id == "macos_say"
    assert result.providers["tts"].methods[0].source_type == "local-cli"
    dumped = result.model_dump_json()
    assert "OPENAI_API_KEY" not in dumped


def test_doctor_requires_ffmpeg_drawtext_for_release_ready(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "claude", "#!/bin/sh\nprintf '真实脚本文案输出'\n")
    _fake_executable(bin_dir / "say", "#!/bin/sh\nprintf 'audio' > \"$3\"\n")
    _fake_executable(bin_dir / "ffprobe", "#!/bin/sh\nexit 0\n")
    _fake_executable(
        bin_dir / "ffmpeg",
        "#!/bin/sh\nif [ \"$1\" = '-hide_banner' ] && [ \"$2\" = '-filters' ]; then\n"
        "printf '%s\\n' ' T. drawbox V->V Draw a box'\nexit 0\nfi\nexit 0\n",
    )
    monkeypatch.setenv("PATH", str(bin_dir))

    result = run_doctor(tool_overrides={"cjk_font": True})

    assert result.ready is False
    assert any(item.id == "ffmpeg_drawtext" for item in result.required)
    assert result.capabilities["render"]["safe_for_release"] is False


def test_doctor_accepts_ffmpeg_with_drawtext_filter(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "claude", "#!/bin/sh\nprintf '真实脚本文案输出'\n")
    _fake_executable(bin_dir / "say", "#!/bin/sh\nprintf 'audio' > \"$3\"\n")
    _fake_executable(bin_dir / "ffprobe", "#!/bin/sh\nexit 0\n")
    _fake_executable(
        bin_dir / "ffmpeg",
        "#!/bin/sh\nif [ \"$1\" = '-hide_banner' ] && [ \"$2\" = '-filters' ]; then\n"
        "printf '%s\\n' ' T. drawtext V->V Draw text on top of video frames'\nexit 0\nfi\n"
        "exit 0\n",
    )
    monkeypatch.setenv("PATH", str(bin_dir))

    result = run_doctor(tool_overrides={"cjk_font": True})

    assert result.ready is True
    assert result.capabilities["render"]["safe_for_release"] is True


def test_doctor_accepts_ffmpeg_drawtext_filter_help(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "claude", "#!/bin/sh\nprintf '真实脚本文案输出'\n")
    _fake_executable(bin_dir / "say", "#!/bin/sh\nprintf 'audio' > \"$3\"\n")
    _fake_executable(bin_dir / "ffprobe", "#!/bin/sh\nexit 0\n")
    _fake_executable(
        bin_dir / "ffmpeg",
        "#!/bin/sh\nif [ \"$1\" = '-hide_banner' ] && [ \"$2\" = '-h' ]; then\n"
        "printf '%s\\n' 'Filter drawtext' "
        "'Draw text on top of video frames using libfreetype library.'\nexit 0\nfi\n"
        "exit 1\n",
    )
    monkeypatch.setenv("PATH", str(bin_dir))

    result = run_doctor(tool_overrides={"cjk_font": True})

    assert result.ready is True
    assert result.capabilities["render"]["safe_for_release"] is True


def test_resolve_auto_provider_runs_inherited_cli_adapters(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "claude", "#!/bin/sh\nprintf '继承订阅生成的真实脚本文案'\n")
    _fake_executable(
        bin_dir / "say",
        "#!/bin/sh\nout=''\nwhile [ \"$#\" -gt 0 ]; do\n"
        "if [ \"$1\" = '-o' ]; then shift; out=\"$1\"; fi\nshift\ndone\n"
        "printf 'LOCAL AUDIO' > \"$out\"\n",
    )
    monkeypatch.setenv("PATH", str(bin_dir))

    llm = resolve_provider("auto", "llm")
    tts = resolve_provider("auto", "tts")

    script = llm.generate_script({"type": "product"})
    audio, duration = tts.synthesize({"voice": "v1", "text": "真实口播文本"})
    assert llm.id == "claude_cli"
    assert script["scenes"][0]["narration_text"] == "继承订阅生成的真实脚本文案"
    assert tts.id == "macos_say"
    assert audio == b"LOCAL AUDIO"
    assert duration > 0


def test_inherited_llm_adapter_parses_fenced_json_output(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(
        bin_dir / "claude",
        "#!/bin/sh\nprintf '%s\\n' '```json' "
        "'{\"scenes\":[{\"id\":\"s1\",\"narration_text\":\"解析后的真实脚本文案\"}]}' "
        "'```'\n",
    )
    monkeypatch.setenv("PATH", str(bin_dir))

    llm = resolve_provider("claude_cli", "llm")
    script = llm.generate_script({"type": "product"})

    assert script["scenes"][0]["narration_text"] == "解析后的真实脚本文案"


def test_setup_reports_missing_short_commands_without_leaking_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("PATH", "")

    result = runner.invoke(app, ["setup", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    dumped = json.dumps(payload, ensure_ascii=False)
    assert payload["capabilities"]["llm"]["best"]["source_type"] == "missing"
    assert "brew install ffmpeg" in dumped
    assert "sk-secret-value" not in dumped
    assert "***" in dumped


def test_setup_text_names_preview_and_release_modes(monkeypatch):
    monkeypatch.setenv("PATH", "")

    result = runner.invoke(app, ["setup"])

    assert result.exit_code == 0
    assert "预览档" in result.output
    assert "发布档" in result.output
    assert "下一步" in result.output


def test_credentials_status_and_forget_are_safe_without_secret_store(monkeypatch):
    monkeypatch.setattr("packages.core.credentials.shutil.which", lambda name: None)

    status = runner.invoke(app, ["credentials", "status", "--json"])
    forget = runner.invoke(app, ["credentials", "forget", "OPENAI_API_KEY", "--json"])

    assert status.exit_code == 0
    assert '"secret_store_available": false' in status.output
    assert forget.exit_code == 0
    assert "OPENAI_API_KEY" in forget.output
