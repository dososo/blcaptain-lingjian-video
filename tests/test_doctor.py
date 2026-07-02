from packages.core.doctor import run_doctor


def test_doctor_reports_required_missing_as_not_ready_without_leaking_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    result = run_doctor(
        tool_overrides={"ffmpeg": False, "ffprobe": True, "cjk_font": True},
        provider_overrides={
            "llm": [
                {
                    "id": "openai_compatible",
                    "type": "openai_compatible",
                    "configured": True,
                    "is_mock": False,
                    "config": {"api_key": "sk-secret-value", "base_url": "https://api.example.com"},
                }
            ],
            "tts": [],
        },
    )

    dumped = result.model_dump_json()
    assert result.ready is False
    assert result.exit_code != 0
    assert any(item.id == "ffmpeg" for item in result.required)
    assert "sk-secret-value" not in dumped
    assert "***" in dumped


def test_doctor_treats_cli_provider_as_real_without_requiring_api_key():
    result = run_doctor(
        tool_overrides={"ffmpeg": True, "ffprobe": True, "ffmpeg_drawtext": True, "cjk_font": True},
        provider_overrides={
            "llm": [
                {
                    "id": "local-llm-cli",
                    "type": "cli",
                    "configured": True,
                    "is_mock": False,
                    "probe_ok": True,
                    "command": "llm",
                }
            ],
            "tts": [
                {
                    "id": "local-tts-cli",
                    "type": "cli",
                    "configured": True,
                    "is_mock": False,
                    "probe_ok": True,
                    "command": "tts",
                }
            ],
        },
    )

    assert result.ready is True
    assert result.exit_code == 0
    assert result.providers["llm"].usable_real is True
    assert result.providers["tts"].usable_real is True
    assert not any(item.id == "openai_api_key" for item in result.required)


def test_doctor_reads_cli_provider_from_environment_without_api_key(monkeypatch):
    monkeypatch.setenv("LINGJIAN_LLM_CLI", "true")
    monkeypatch.setenv("LINGJIAN_TTS_CLI", "true")
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
    assert result.providers["llm"].usable_real is True
    assert result.providers["tts"].usable_real is True


def test_doctor_does_not_count_mock_or_codex_host_as_release_ready():
    result = run_doctor(
        tool_overrides={"ffmpeg": True, "ffprobe": True, "ffmpeg_drawtext": True, "cjk_font": True},
        provider_overrides={
            "llm": [
                {"id": "mock-cli", "type": "cli", "configured": True, "is_mock": True},
                {"id": "codex-host", "type": "codex_host", "configured": True, "is_mock": False},
            ],
            "tts": [{"id": "mock-tts", "type": "mock", "configured": True, "is_mock": True}],
        },
    )

    assert result.ready is False
    assert result.providers["llm"].usable_real is False
    assert result.providers["tts"].usable_real is False
    assert any(item.id == "real_llm_provider" for item in result.required)
    assert any(item.id == "real_tts_provider" for item in result.required)


def test_doctor_redacts_key_by_config_key_name():
    result = run_doctor(
        tool_overrides={"ffmpeg": True, "ffprobe": True, "ffmpeg_drawtext": True, "cjk_font": True},
        provider_overrides={
            "llm": [
                {
                    "id": "openai_compatible",
                    "type": "openai_compatible",
                    "configured": True,
                    "is_mock": False,
                    "config": {"api_key": "plain-value", "token": "another-plain-value"},
                }
            ],
            "tts": [{"id": "cli-tts", "type": "cli", "configured": True, "probe_ok": True}],
        },
    )

    dumped = result.model_dump_json()
    assert "plain-value" not in dumped
    assert "another-plain-value" not in dumped
    assert "***" in dumped


def test_openai_compatible_requires_model_for_release_ready():
    result = run_doctor(
        tool_overrides={"ffmpeg": True, "ffprobe": True, "ffmpeg_drawtext": True, "cjk_font": True},
        provider_overrides={
            "llm": [
                {
                    "id": "openai_compatible",
                    "type": "openai_compatible",
                    "configured": True,
                    "is_mock": False,
                    "config": {"api_key": "sk-test", "base_url": "https://api.example.com"},
                }
            ],
            "tts": [{"id": "cli-tts", "type": "cli", "configured": True, "probe_ok": True}],
        },
    )

    assert result.providers["llm"].usable_real is False
    assert any(item.id == "real_llm_provider" for item in result.required)
