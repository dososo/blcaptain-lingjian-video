from __future__ import annotations

from packages.core.capabilities import best_provider_id
from providers.base import Provider
from providers.cli import CliProvider
from providers.inherited_cli import InheritedLLMProvider, LocalTTSProvider
from providers.mock.base import MockProvider
from providers.openai_compatible import OpenAICompatibleLLMProvider, OpenAICompatibleTTSProvider
from providers.volcengine_tts import VolcengineTTSProvider


def registered_providers() -> list[Provider]:
    return [
        InheritedLLMProvider("claude_cli", "Claude Code CLI", "claude", "inherited-cli"),
        InheritedLLMProvider("codex_cli", "Codex CLI", "codex", "inherited-cli"),
        InheritedLLMProvider("ollama_cli", "Ollama CLI", "ollama", "local-cli"),
        InheritedLLMProvider("llm_local_cli", "llm CLI", "llm", "local-cli"),
        CliProvider("llm_cli", "Local LLM CLI", "llm", "LINGJIAN_LLM_CLI", ["generate_script"]),
        CliProvider("tts_cli", "Local TTS CLI", "tts", "LINGJIAN_TTS_CLI", ["synthesize"]),
        LocalTTSProvider("macos_say", "macOS say", "say"),
        LocalTTSProvider("piper_cli", "Piper CLI", "piper"),
        LocalTTSProvider("espeak_ng", "espeak-ng", "espeak-ng"),
        VolcengineTTSProvider(),
        OpenAICompatibleLLMProvider(),
        OpenAICompatibleTTSProvider(),
        MockProvider("mock_llm", "Mock LLM", "llm", ["generate_script"]),
        MockProvider("mock_tts", "Mock TTS", "tts", ["synthesize"]),
        MockProvider("mock_ocr", "Mock OCR", "ocr", ["extract_text"]),
        MockProvider("mock_web_extract", "Mock Web Extractor", "web_extract", ["extract"]),
    ]


def resolve_provider(provider_id: str, kind: str) -> Provider:
    if provider_id == "auto":
        provider_id = best_provider_id(kind) or provider_id
    alias = {
        ("mock", "llm"): "mock_llm",
        ("mock", "tts"): "mock_tts",
        ("mock", "ocr"): "mock_ocr",
        ("mock", "web_extract"): "mock_web_extract",
        ("cli", "llm"): "llm_cli",
        ("cli", "tts"): "tts_cli",
        ("claude", "llm"): "claude_cli",
        ("codex", "llm"): "codex_cli",
        ("ollama", "llm"): "ollama_cli",
        ("say", "tts"): "macos_say",
        ("piper", "tts"): "piper_cli",
        ("espeak-ng", "tts"): "espeak_ng",
        ("openai", "llm"): "openai_compatible",
        ("openai", "tts"): "openai_compatible_tts",
        ("volcengine", "tts"): "volcengine_tts",
        ("doubao", "tts"): "volcengine_tts",
    }.get((provider_id, kind), provider_id)
    for provider in registered_providers():
        if provider.id == alias and provider.kind == kind:
            if not provider.is_configured():
                from packages.core.errors import LingjianError

                raise LingjianError(
                    "PROVIDER_NOT_CONFIGURED",
                    "Provider 未配置或不存在。",
                    provider.setup_hint(),
                    {"provider": provider_id, "kind": kind},
                )
            return provider
    from packages.core.errors import LingjianError

    raise LingjianError(
        "PROVIDER_NOT_CONFIGURED",
        "Provider 未配置或不存在。",
        "请运行 doctor 查看可用 provider,或配置真实 CLI/API provider。",
        {"provider": provider_id, "kind": kind},
    )
