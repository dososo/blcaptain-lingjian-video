import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from apps.cli.lingjian_cli.main import _setup_user_guidance, app
from packages.core.capabilities import detect_capabilities
from packages.core.doctor import run_doctor
from providers.registry import resolve_provider

runner = CliRunner()


def _fake_executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_capability_detection_prefers_inherited_llm_cli_and_kokoro_tts(tmp_path, monkeypatch):
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
    monkeypatch.setenv("LINGJIAN_KOKORO_TTS_READY", "1")

    result = runner.invoke(app, ["setup", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["capabilities"]["llm"]["best"]["id"] == "claude_cli"
    assert payload["capabilities"]["llm"]["best"]["source_type"] == "inherited-cli"
    assert payload["capabilities"]["tts"]["best"]["id"] == "kokoro_zh_tts"
    assert payload["capabilities"]["tts"]["best"]["source_type"] == "local-cli"
    assert payload["capabilities"]["tts"]["best"]["quality_tier"] == "zero_key"
    assert "已具备发布级能力" in payload["summary_zh"]
    assert "Claude Code CLI" in payload["summary_zh"]
    assert "样片/辅助能力" in payload["summary_zh"]
    assert "Kokoro 中文本地 TTS" in payload["summary_zh"]


def test_doctor_uses_inherited_capabilities_without_api_key(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "claude", "#!/bin/sh\nprintf '继承订阅脚本输出'\n")
    _fake_executable(bin_dir / "say", "#!/bin/sh\nprintf 'audio' > \"$3\"\n")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("LINGJIAN_KOKORO_TTS_READY", "1")
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

    assert result.ready is False
    assert any(item.id == "publish_tts_provider" for item in result.required)
    assert result.providers["llm"].methods[0].id == "claude_cli"
    assert result.providers["llm"].methods[0].source_type == "inherited-cli"
    assert result.providers["tts"].methods[0].id == "kokoro_zh_tts"
    assert result.providers["tts"].methods[0].source_type == "local-cli"
    dumped = result.model_dump_json()
    # 只查真密钥值不泄露;变量名 OPENAI_API_KEY 出现在「可选 provider 配置提示」里是正常的,非泄露。
    assert "sk-" not in dumped


def test_doctor_marks_volcengine_tts_as_publish_tier(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "claude", "#!/bin/sh\nprintf '真实脚本文案输出'\n")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "secret-token")
    monkeypatch.setenv("LINGJIAN_HOST_REMOTION_READY", "1")
    monkeypatch.setenv("LINGJIAN_HOST_REMOTION_PUBLISH_READY", "1")

    result = run_doctor(
        tool_overrides={
            "ffmpeg": True,
            "ffprobe": True,
            "ffmpeg_drawtext": True,
            "cjk_font": True,
        }
    )

    volcengine = next(
        method for method in result.providers["tts"].methods if method.id == "volcengine_tts"
    )
    assert result.ready is True
    assert volcengine.safe_for_release is True
    assert volcengine.quality_tier == "publish"
    assert not any(item.id == "local_tts_release_notice" for item in result.optional)
    assert "secret-token" not in result.model_dump_json()


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
    monkeypatch.setenv("LINGJIAN_KOKORO_TTS_READY", "1")

    result = run_doctor(tool_overrides={"cjk_font": True})

    assert result.ready is False
    assert any(item.id == "ffmpeg_drawtext" for item in result.required)
    assert result.capabilities["render"]["safe_for_release"] is False


def test_doctor_reports_ffmpeg_drawtext_ready_but_still_requires_publish_tts(
    tmp_path, monkeypatch
):
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
    monkeypatch.setenv("LINGJIAN_KOKORO_TTS_READY", "1")

    result = run_doctor(tool_overrides={"cjk_font": True})

    assert result.ready is False
    assert result.capabilities["render"]["safe_for_release"] is True
    assert any(item.id == "publish_tts_provider" for item in result.required)


def test_doctor_reports_ffmpeg_drawtext_filter_help_but_still_requires_publish_tts(
    tmp_path, monkeypatch
):
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
    monkeypatch.setenv("LINGJIAN_KOKORO_TTS_READY", "1")

    result = run_doctor(tool_overrides={"cjk_font": True})

    assert result.ready is False
    assert result.capabilities["render"]["safe_for_release"] is True
    assert any(item.id == "publish_tts_provider" for item in result.required)


def test_resolve_provider_runs_inherited_llm_and_explicit_say_adapter(tmp_path, monkeypatch):
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
    tts = resolve_provider("say", "tts")

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
    assert payload["user_guidance"]["version"] == "v1"
    assert "先解决发布级配音" in payload["user_guidance"]["single_next_action_zh"]
    assert "doctor --json" in " ".join(payload["user_guidance"]["do_not_zh"])


def test_setup_text_names_preview_and_release_modes(monkeypatch):
    monkeypatch.setenv("PATH", "")

    result = runner.invoke(app, ["setup"])

    assert result.exit_code == 0
    assert "预览档" in result.output
    assert "发布档" in result.output
    assert "已继承" in result.output
    assert "已具备" in result.output
    assert "必须补齐" in result.output
    assert "可选增强" in result.output
    assert "下一步" in result.output
    assert "当前只做一步" in result.output
    assert "先解决发布级配音" in result.output
    assert "npx skills add heygen-com/hyperframes" in result.output


def test_setup_user_guidance_moves_to_requirements_when_capabilities_ready():
    guidance = _setup_user_guidance(
        {
            "capabilities": {
                "tts": {"best": {"quality_tier": "publish", "safe_for_release": True}},
                "visuals": {"best": {"safe_for_release": True}},
                "render": {"best": {"safe_for_release": True}},
                "llm": {"best": {"safe_for_release": True}},
            }
        }
    )

    assert "能力已够进入需求澄清" in guidance["single_next_action_zh"]
    assert "内容依据" in guidance["single_next_action_zh"]
    assert any(
        "展示完整导演分镜确认单 v2" in item
        for item in guidance["first_use_workflow_zh"]
    )


def test_capability_detection_reports_visual_generation_tier(monkeypatch):
    monkeypatch.setenv("LINGJIAN_HOST_HYPERFRAMES_READY", "1")
    monkeypatch.setenv("PATH", "")

    result = runner.invoke(app, ["setup", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    host_hyperframes = next(
        candidate
        for candidate in payload["capabilities"]["visuals"]["candidates"]
        if candidate["id"] == "host_hyperframes"
    )
    assert payload["capabilities"]["visuals"]["best"]["id"] == "fallback_solid"
    assert host_hyperframes["source_type"] == "host-plugin"
    assert host_hyperframes["configured"] is True
    assert host_hyperframes["safe_for_release"] is False


def test_capability_detection_requires_publish_ready_visual_generator(monkeypatch):
    monkeypatch.setenv("LINGJIAN_HOST_HYPERFRAMES_READY", "1")
    monkeypatch.setenv("LINGJIAN_HOST_HYPERFRAMES_PUBLISH_READY", "1")
    monkeypatch.setenv("PATH", "")

    result = runner.invoke(app, ["setup", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    host_hyperframes = next(
        candidate
        for candidate in payload["capabilities"]["visuals"]["candidates"]
        if candidate["id"] == "host_hyperframes"
    )
    assert host_hyperframes["configured"] is True
    assert host_hyperframes["safe_for_release"] is True


def test_capability_detection_probes_full_host_visual_cli_argv(tmp_path, monkeypatch):
    adapter = tmp_path / "adapter.py"
    adapter.write_text("print('ok')\n", encoding="utf-8")
    seen: list[list[str]] = []

    def fake_probe(argv, generator):
        seen.append(argv)
        return generator == "hyperframes"

    monkeypatch.setattr("packages.core.capabilities._host_visual_cli_probe", fake_probe)
    report = detect_capabilities(
        env={"LINGJIAN_HOST_HYPERFRAMES_CLI": f"{sys.executable} {adapter}"},
        path_lookup=lambda name: None,
    )

    candidate = next(
        item
        for item in report.groups["visuals"].candidates
        if item.id == "host_hyperframes"
    )
    assert seen == [[sys.executable, str(adapter)]]
    assert candidate.configured is True
    assert candidate.safe_for_release is True
    assert report.groups["visuals"].best.id == "host_hyperframes"


def test_doctor_accepts_hyperframes_director_as_publish_visual(
    tmp_path, monkeypatch
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "llm", "#!/bin/sh\nprintf 'llm'\n")
    _fake_executable(bin_dir / "tts", "#!/bin/sh\nprintf 'tts'\n")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("LINGJIAN_LLM_CLI", "llm")
    monkeypatch.setenv("LINGJIAN_TTS_CLI", "tts")
    monkeypatch.setenv("LINGJIAN_HOST_HYPERFRAMES_READY", "1")
    monkeypatch.setenv("LINGJIAN_HOST_HYPERFRAMES_PUBLISH_READY", "1")

    hyperframes_visual = run_doctor(
        tool_overrides={
            "ffmpeg": True,
            "ffprobe": True,
            "ffmpeg_drawtext": True,
            "cjk_font": True,
        }
    )

    assert not any(item.id == "publish_visual_provider" for item in hyperframes_visual.required)


def test_doctor_blocks_sample_hyperframes_as_publish_visual(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "llm", "#!/bin/sh\nprintf 'llm'\n")
    _fake_executable(bin_dir / "tts", "#!/bin/sh\nprintf 'tts'\n")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("LINGJIAN_LLM_CLI", "llm")
    monkeypatch.setenv("LINGJIAN_TTS_CLI", "tts")
    monkeypatch.setenv("LINGJIAN_HOST_HYPERFRAMES_READY", "1")

    result = run_doctor(
        tool_overrides={
            "ffmpeg": True,
            "ffprobe": True,
            "ffmpeg_drawtext": True,
            "cjk_font": True,
        }
    )

    assert any(item.id == "publish_visual_provider" for item in result.required)


def test_doctor_exposes_remotion_opt_in_candidate_without_counting_it_ready(
    tmp_path, monkeypatch
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "llm", "#!/bin/sh\nprintf 'llm'\n")
    _fake_executable(bin_dir / "tts", "#!/bin/sh\nprintf 'tts'\n")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("LINGJIAN_LLM_CLI", "llm")
    monkeypatch.setenv("LINGJIAN_TTS_CLI", "tts")
    monkeypatch.delenv("LINGJIAN_HOST_REMOTION_READY", raising=False)
    monkeypatch.delenv("LINGJIAN_HOST_REMOTION_PUBLISH_READY", raising=False)

    result = run_doctor(
        tool_overrides={
            "ffmpeg": True,
            "ffprobe": True,
            "ffmpeg_drawtext": True,
            "cjk_font": True,
            "host_remotion": False,
            "host_remotion_publish": False,
        }
    )

    remotion = next(
        item
        for item in result.capabilities["visuals"]["candidates"]
        if item["id"] == "host_remotion"
    )
    assert remotion["source_type"] == "host-plugin"
    assert remotion["configured"] is False
    assert remotion["safe_for_release"] is False
    assert "Remotion" in remotion["label_zh"]
    assert any(item.id == "publish_visual_provider" for item in result.required)


def test_doctor_optional_notice_describes_host_visual_delegation(monkeypatch):
    monkeypatch.setenv("PATH", "")

    result = run_doctor(
        tool_overrides={
            "ffmpeg": True,
            "ffprobe": True,
            "ffmpeg_drawtext": True,
            "cjk_font": True,
            "host_hyperframes": False,
        },
        provider_overrides={
            "llm": [
                {
                    "id": "real_llm",
                    "type": "cli",
                    "configured": True,
                    "is_mock": False,
                    "probe_ok": True,
                    "command": "",
                }
            ],
            "tts": [
                {
                    "id": "real_tts",
                    "type": "cli",
                    "configured": True,
                    "is_mock": False,
                    "probe_ok": True,
                    "command": "",
                }
            ],
        },
    )

    notice = next(item for item in result.optional if item.id == "host_visual_delegation_notice")
    assert "不 import" in notice.message_zh


def test_credentials_status_and_forget_are_safe_without_secret_store(monkeypatch):
    monkeypatch.setattr("packages.core.credentials.shutil.which", lambda name: None)

    status = runner.invoke(app, ["credentials", "status", "--json"])
    forget = runner.invoke(app, ["credentials", "forget", "OPENAI_API_KEY", "--json"])

    assert status.exit_code == 0
    assert '"secret_store_available": false' in status.output
    assert forget.exit_code == 0
    assert "OPENAI_API_KEY" in forget.output


def test_credential_naming_macos_store_matches_program_read(monkeypatch):
    """回归:docs/ONBOARDING.md 存的命名必须与 read_credential 读的命名一致。

    历史 Blocker:docs 用 account 不带前缀、code 用 account 带前缀 → 存了读不到。
    标准 = service = account = "lingjian:<NAME>"。此测试锁死命名,防再次漂移。
    """
    from packages.core import credentials as cred

    calls = {}

    def _fake_run(argv, **kwargs):
        calls["argv"] = argv

        class _R:
            returncode = 0
            stdout = "the-secret"
            stderr = ""

        return _R()

    monkeypatch.setattr(
        cred, "detect_secret_store", lambda: cred.CredentialBackend("macos-keychain", True)
    )
    monkeypatch.setattr(cred.subprocess, "run", _fake_run)
    value = cred.read_credential("VOLCENGINE_ARK_API_KEY")
    assert value == "the-secret"
    # service(-s) 与 account(-a) 都必须是 lingjian:<NAME>
    argv = calls["argv"]
    assert argv[argv.index("-s") + 1] == "lingjian:VOLCENGINE_ARK_API_KEY"
    assert argv[argv.index("-a") + 1] == "lingjian:VOLCENGINE_ARK_API_KEY"


def test_credential_naming_linux_uses_prefixed_service_and_account(monkeypatch):
    """回归:Linux secret-tool 的 service 与 account 都必须带 lingjian: 前缀(对齐标准)。"""
    from packages.core import credentials as cred

    calls = {}

    def _fake_run(argv, **kwargs):
        calls["argv"] = argv

        class _R:
            returncode = 0
            stdout = "the-secret"
            stderr = ""

        return _R()

    monkeypatch.setattr(
        cred, "detect_secret_store", lambda: cred.CredentialBackend("secret-service", True)
    )
    monkeypatch.setattr(cred.subprocess, "run", _fake_run)
    cred.read_credential("VOLCENGINE_TTS_API_KEY")
    argv = calls["argv"]
    assert argv[argv.index("service") + 1] == "lingjian:VOLCENGINE_TTS_API_KEY"
    assert argv[argv.index("account") + 1] == "lingjian:VOLCENGINE_TTS_API_KEY"


def test_onboarding_doc_store_commands_use_prefixed_naming():
    """回归(锁文档存侧):docs/ONBOARDING.md 里的存 key 命令必须带 lingjian: 前缀。

    历史 Blocker 出在【文档存的命名漂移】(read 侧有前缀、doc 侧漏前缀 → 存了读不到)。
    仅锁 read 侧挡不住有人把文档前缀删掉,故这里直接解析 ONBOARDING.md 命令字符串。
    """
    import re
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[1] / "docs" / "ONBOARDING.md").read_text(
        encoding="utf-8"
    )

    # macOS: security add-generic-password 的 -a/-s 必须是 lingjian:VOLCENGINE_*_API_KEY
    macos_lines = [ln for ln in doc.splitlines() if "add-generic-password" in ln]
    assert macos_lines, "ONBOARDING.md 缺 macOS 存 key 命令"
    for ln in macos_lines:
        for flag in ("-a", "-s"):
            m = re.search(rf'{flag}\s+"?(lingjian:VOLCENGINE_\w+_API_KEY)"?', ln)
            assert m, f"macOS 存 key 命令 {flag} 未带 lingjian: 前缀:{ln.strip()}"

    # Linux: secret-tool store 的 service/account 必须是 lingjian:VOLCENGINE_*_API_KEY
    linux_lines = [ln for ln in doc.splitlines() if "secret-tool store" in ln]
    assert linux_lines, "ONBOARDING.md 缺 Linux 存 key 命令"
    for ln in linux_lines:
        for attr in ("service", "account"):
            m = re.search(rf"{attr}\s+(lingjian:VOLCENGINE_\w+_API_KEY)", ln)
            assert m, f"Linux 存 key 命令 {attr} 未带 lingjian: 前缀:{ln.strip()}"

    # 防漂移:不得出现漏前缀的裸命名(如 -a VOLCENGINE_TTS_API_KEY)
    assert not re.search(
        r'-[as]\s+"?VOLCENGINE_\w+_API_KEY', doc
    ), "ONBOARDING.md 出现漏 lingjian: 前缀的裸 account/service 命名"
