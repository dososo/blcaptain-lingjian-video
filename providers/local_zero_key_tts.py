from __future__ import annotations

import base64
import binascii
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from packages.core.errors import LingjianError
from providers.base import LicenseInfo, Provider, ProviderStatus
from providers.validation import validate_tts_output

LOCAL_TTS_TIMEOUT_SEC = 180


class AdapterTTSProvider(Provider):
    def __init__(
        self,
        provider_id: str,
        name: str,
        script_name: str,
        license_name: str,
        license_url: str | None,
        hint: str,
    ) -> None:
        self.id = provider_id
        self.name = name
        self.kind = "tts"
        self.script_name = script_name
        self._license_name = license_name
        self._license_url = license_url
        self._hint = hint
        self.capabilities = ["synthesize"]
        self.is_mock = False

    def is_installed(self) -> bool:
        return self.is_configured()

    def is_configured(self) -> bool:
        try:
            completed = subprocess.run(
                [sys.executable, str(self._script_path()), "--probe"],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0

    def doctor(self) -> ProviderStatus:
        if self.is_configured():
            return ProviderStatus(self.id, True, f"{self.name} 已检测到,零 key 可用。")
        return ProviderStatus(self.id, False, self._hint)

    def setup_hint(self) -> str:
        return self._hint

    def license_info(self) -> LicenseInfo:
        return LicenseInfo(self._license_name, self._license_url)

    def synthesize(self, payload: dict[str, Any]) -> tuple[bytes, float]:
        try:
            completed = subprocess.run(
                [sys.executable, str(self._script_path())],
                input=json.dumps({"task": "synthesize", **payload}, ensure_ascii=False),
                text=True,
                capture_output=True,
                check=False,
                timeout=LOCAL_TTS_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as exc:
            raise LingjianError(
                "PROVIDER_TIMEOUT",
                "本地 TTS 执行超时。",
                "请缩短文案或检查本地 TTS 环境。",
                {"provider": self.id},
            ) from exc
        if completed.returncode != 0:
            raise LingjianError(
                "PROVIDER_CLI_FAILED",
                "本地 TTS 执行失败。",
                self.setup_hint(),
                {"provider": self.id},
            )
        try:
            response = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise LingjianError(
                "TTS_OUTPUT_INVALID",
                "本地 TTS 没有输出合法 JSON。",
                "请确认本地 TTS 适配器可输出 audio_base64 与 duration_sec。",
                {"provider": self.id},
            ) from exc
        return _decode_tts_response(response, self.id)

    def _script_path(self) -> Path:
        return Path(__file__).resolve().parents[1] / "scripts" / "providers" / self.script_name


class KokoroTTSProvider(AdapterTTSProvider):
    def __init__(self) -> None:
        super().__init__(
            "kokoro_zh_tts",
            "Kokoro 中文本地 TTS",
            "kokoro_zh_tts.py",
            "Kokoro Apache-2.0 local TTS",
            "https://github.com/hexgrad/kokoro",
            '请安装: uv pip install "kokoro>=0.9.4" "misaki[zh]" soundfile torch。',
        )


class PiperTTSProvider(AdapterTTSProvider):
    def __init__(self) -> None:
        super().__init__(
            "piper_cli",
            "Piper 中文本地 TTS",
            "piper_cli.py",
            "Piper GPL-3.0 local TTS",
            "https://github.com/rhasspy/piper",
            "请用户自行安装 piper-tts 与 zh_CN-huayan-medium voice;灵剪只子进程调用。",
        )


def _decode_tts_response(response: dict[str, Any], provider_id: str) -> tuple[bytes, float]:
    audio_base64 = response.get("audio_base64")
    if not isinstance(audio_base64, str) or not audio_base64:
        raise LingjianError(
            "TTS_OUTPUT_INVALID",
            "本地 TTS 返回的音频无效。",
            "请确认适配器输出非空 audio_base64。",
            {"provider": provider_id},
        )
    try:
        audio = base64.b64decode(audio_base64, validate=True)
        duration = float(response.get("duration_sec"))
    except (binascii.Error, TypeError, ValueError) as exc:
        raise LingjianError(
            "TTS_OUTPUT_INVALID",
            "本地 TTS 返回的音频或时长无效。",
            "请确认适配器输出合法 base64 与 duration_sec。",
            {"provider": provider_id},
        ) from exc
    return validate_tts_output(audio, duration, provider_id)
