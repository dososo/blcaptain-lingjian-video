import wave
from io import BytesIO
from urllib.error import HTTPError

import pytest

from packages.core.errors import LingjianError
from providers.registry import registered_providers, resolve_provider


def test_registered_providers_implement_contract():
    providers = registered_providers()
    assert providers

    for provider in providers:
        assert provider.id
        assert provider.name
        assert provider.kind in {"llm", "tts", "ocr", "web_extract"}
        assert isinstance(provider.capabilities, list)
        assert isinstance(provider.is_mock, bool)
        assert isinstance(provider.is_installed(), bool)
        assert isinstance(provider.is_configured(), bool)
        assert provider.doctor().id == provider.id
        assert provider.setup_hint()
        assert provider.license_info().name


def test_cli_provider_resolves_from_environment(tmp_path, monkeypatch):
    llm_cli = tmp_path / "fake-llm"
    llm_cli.write_text("#!/bin/sh\ncat >/dev/null\nprintf '{}'\n", encoding="utf-8")
    llm_cli.chmod(0o755)
    monkeypatch.setenv("LINGJIAN_LLM_CLI", str(llm_cli))

    provider = resolve_provider("llm_cli", "llm")

    assert provider.id == "llm_cli"
    assert provider.kind == "llm"
    assert provider.is_mock is False
    assert provider.is_installed() is True
    assert provider.is_configured() is True
    assert "CLI" in provider.license_info().name


def test_openai_compatible_provider_resolves_from_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    provider = resolve_provider("openai_compatible", "llm")

    assert provider.id == "openai_compatible"
    assert provider.kind == "llm"
    assert provider.is_mock is False
    assert provider.is_configured() is True
    assert "OpenAI-compatible" in provider.license_info().name


def test_openai_compatible_provider_maps_http_error(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    def raise_http_error(request, timeout):
        raise HTTPError(
            request.full_url,
            401,
            "unauthorized",
            {},
            BytesIO(b"bad key"),
        )

    monkeypatch.setattr("providers.openai_compatible.urlopen", raise_http_error)
    provider = resolve_provider("openai_compatible", "llm")

    with pytest.raises(LingjianError) as exc_info:
        provider.generate_script({"type": "product"})

    assert exc_info.value.error_code == "PROVIDER_AUTH_FAILED"


def test_openai_compatible_provider_rejects_thin_script(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"{\\"scenes\\":[]}"}}]}'

    monkeypatch.setattr(
        "providers.openai_compatible.urlopen",
        lambda request, timeout: FakeResponse(),
    )
    provider = resolve_provider("openai_compatible", "llm")

    with pytest.raises(LingjianError) as exc_info:
        provider.generate_script({"type": "product"})

    assert exc_info.value.error_code == "LLM_OUTPUT_TOO_THIN"


def test_openai_compatible_tts_rejects_empty_audio(monkeypatch):
    monkeypatch.setenv("OPENAI_TTS_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_TTS_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_TTS_MODEL", "tts-model")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b""

    monkeypatch.setattr(
        "providers.openai_compatible.urlopen",
        lambda request, timeout: FakeResponse(),
    )
    provider = resolve_provider("openai_compatible_tts", "tts")

    with pytest.raises(LingjianError) as exc_info:
        provider.synthesize({"voice": "alloy", "text": "真实语音文本"})

    assert exc_info.value.error_code == "TTS_OUTPUT_INVALID"


def test_openai_compatible_tts_uses_wav_duration(monkeypatch):
    monkeypatch.setenv("OPENAI_TTS_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_TTS_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_TTS_MODEL", "tts-model")
    audio_buffer = BytesIO()
    with wave.open(audio_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\0\0" * 16000)
    audio_bytes = audio_buffer.getvalue()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return audio_bytes

    monkeypatch.setattr(
        "providers.openai_compatible.urlopen",
        lambda request, timeout: FakeResponse(),
    )
    provider = resolve_provider("openai_compatible_tts", "tts")

    audio, duration = provider.synthesize({"voice": "alloy", "text": "真实语音文本"})

    assert audio == audio_bytes
    assert duration == 2.0
