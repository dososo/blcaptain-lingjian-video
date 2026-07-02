from __future__ import annotations

import json
import os
import wave
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from packages.core.errors import LingjianError
from packages.core.provider_errors import classify_provider_error
from providers.base import LicenseInfo, Provider, ProviderStatus
from providers.validation import validate_script_output, validate_tts_output

OPENAI_COMPATIBLE_TIMEOUT_SEC = 60


class OpenAICompatibleLLMProvider(Provider):
    id = "openai_compatible"
    name = "OpenAI-compatible LLM"
    kind = "llm"
    capabilities = ["generate_script"]
    is_mock = False

    def is_installed(self) -> bool:
        return True

    def is_configured(self) -> bool:
        return bool(
            os.getenv("OPENAI_BASE_URL")
            and os.getenv("OPENAI_API_KEY")
            and os.getenv("OPENAI_MODEL")
        )

    def doctor(self) -> ProviderStatus:
        if self.is_configured():
            return ProviderStatus(self.id, True, "OpenAI-compatible LLM 已配置,可用于 release。")
        return ProviderStatus(
            self.id,
            False,
            "缺少 OPENAI_BASE_URL、OPENAI_API_KEY 或 OPENAI_MODEL。",
        )

    def setup_hint(self) -> str:
        return (
            "配置 OPENAI_BASE_URL、OPENAI_API_KEY、OPENAI_MODEL "
            "后显式使用 --provider openai_compatible。"
        )

    def license_info(self) -> LicenseInfo:
        return LicenseInfo("OpenAI-compatible API provider")

    def generate_script(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = _post_json(
            self.id,
            _base_url("OPENAI_BASE_URL") + "/chat/completions",
            os.getenv("OPENAI_API_KEY", ""),
            {
                "model": os.getenv("OPENAI_MODEL", ""),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是短视频脚本生成器。只返回 JSON object,"
                            "顶层必须包含非空 scenes 数组。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
                "response_format": {"type": "json_object"},
            },
        )
        try:
            content = response["choices"][0]["message"]["content"]
            generated = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LingjianError(
                "LLM_INVALID_JSON",
                "OpenAI-compatible LLM 未返回合法脚本 JSON。",
                "请确认模型支持 JSON object 输出,且返回包含 scenes 的对象。",
                {"provider": self.id},
            ) from exc
        if not isinstance(generated, dict):
            raise LingjianError(
                "LLM_INVALID_JSON",
                "OpenAI-compatible LLM 返回的脚本顶层不是对象。",
                "请让模型返回 JSON object。",
                {"provider": self.id},
            )
        return validate_script_output(generated, self.id)


class OpenAICompatibleTTSProvider(Provider):
    id = "openai_compatible_tts"
    name = "OpenAI-compatible TTS"
    kind = "tts"
    capabilities = ["synthesize"]
    is_mock = False

    def is_installed(self) -> bool:
        return True

    def is_configured(self) -> bool:
        return bool(
            os.getenv("OPENAI_TTS_API_KEY")
            and (os.getenv("OPENAI_TTS_BASE_URL") or os.getenv("OPENAI_BASE_URL"))
            and os.getenv("OPENAI_TTS_MODEL")
        )

    def doctor(self) -> ProviderStatus:
        if self.is_configured():
            return ProviderStatus(self.id, True, "OpenAI-compatible TTS 已配置,可用于 release。")
        return ProviderStatus(
            self.id,
            False,
            "缺少 OPENAI_TTS_API_KEY、OPENAI_TTS_BASE_URL 或 OPENAI_TTS_MODEL。",
        )

    def setup_hint(self) -> str:
        return (
            "配置 OPENAI_TTS_API_KEY、OPENAI_TTS_BASE_URL、OPENAI_TTS_MODEL "
            "后显式使用 --provider openai_compatible_tts。"
        )

    def license_info(self) -> LicenseInfo:
        return LicenseInfo("OpenAI-compatible API provider")

    def synthesize(self, payload: dict[str, Any]) -> tuple[bytes, float]:
        audio = _post_bytes(
            self.id,
            _tts_base_url() + "/audio/speech",
            os.getenv("OPENAI_TTS_API_KEY", ""),
            {
                "model": os.getenv("OPENAI_TTS_MODEL", ""),
                "input": str(payload.get("text") or ""),
                "voice": str(payload.get("voice") or "alloy"),
                "response_format": "wav",
            },
        )
        return validate_tts_output(audio, _wav_duration_or_default(audio), self.id)


def _base_url(env_var: str) -> str:
    value = os.getenv(env_var, "").rstrip("/")
    if not value:
        raise LingjianError(
            "PROVIDER_NOT_CONFIGURED",
            "OpenAI-compatible provider 未配置。",
            "请配置 base_url、model 与 key 后重试。",
        )
    return value


def _tts_base_url() -> str:
    return (os.getenv("OPENAI_TTS_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").rstrip("/")


def _post_json(provider_id: str, url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw = _post_bytes(provider_id, url, api_key, payload)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LingjianError(
            "PROVIDER_API_FAILED",
            "OpenAI-compatible provider 返回非 JSON 响应。",
            "请确认 API endpoint 与模型配置正确。",
            {"provider": provider_id},
        ) from exc
    if not isinstance(decoded, dict):
        raise LingjianError(
            "PROVIDER_API_FAILED",
            "OpenAI-compatible provider 响应顶层不是对象。",
            "请确认 API endpoint 与模型配置正确。",
            {"provider": provider_id},
        )
    return decoded


def _post_bytes(provider_id: str, url: str, api_key: str, payload: dict[str, Any]) -> bytes:
    if not api_key or not url:
        raise LingjianError(
            "PROVIDER_NOT_CONFIGURED",
            "OpenAI-compatible provider 未配置。",
            "请配置 base_url、model 与 key 后重试。",
            {"provider": provider_id},
        )
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=OPENAI_COMPATIBLE_TIMEOUT_SEC) as response:
            return response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LingjianError(
            classify_provider_error(exc.code, body),
            "OpenAI-compatible provider 请求被拒绝。",
            "请检查 API key、配额、模型权限与 base_url。",
            {"provider": provider_id, "status_code": exc.code},
        ) from exc
    except TimeoutError as exc:
        raise LingjianError(
            "PROVIDER_TIMEOUT",
            "OpenAI-compatible provider 请求超时。",
            "请检查 API 网络、base_url 与模型响应时间。",
            {"provider": provider_id},
        ) from exc
    except URLError as exc:
        raise LingjianError(
            "PROVIDER_API_FAILED",
            "OpenAI-compatible provider 请求失败。",
            "请检查 API base_url、模型与网络连通性。",
            {"provider": provider_id},
        ) from exc


def _wav_duration_or_default(audio: bytes) -> float:
    try:
        with wave.open(BytesIO(audio), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
    except (EOFError, wave.Error):
        return 1.0
    if frame_rate <= 0 or frame_count <= 0:
        return 1.0
    return frame_count / frame_rate
