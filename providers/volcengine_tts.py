from __future__ import annotations

import base64
import binascii
import json
import os
import uuid
import wave
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from packages.core.errors import LingjianError
from packages.core.provider_errors import classify_provider_error
from providers.base import LicenseInfo, Provider, ProviderStatus
from providers.validation import validate_tts_output

VOLCENGINE_TTS_TIMEOUT_SEC = 60
VOLCENGINE_TTS_ENDPOINT = "https://openspeech.bytedance.com/api/v1/tts"


class VolcengineTTSProvider(Provider):
    id = "volcengine_tts"
    name = "火山豆包 TTS"
    kind = "tts"
    capabilities = ["synthesize"]
    is_mock = False

    def is_installed(self) -> bool:
        return True

    def is_configured(self) -> bool:
        return bool(
            os.getenv("VOLCENGINE_TTS_APP_ID")
            and os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN")
            and os.getenv("VOLCENGINE_TTS_CLUSTER")
        )

    def doctor(self) -> ProviderStatus:
        if self.is_configured():
            return ProviderStatus(self.id, True, "火山豆包 TTS 已配置,可作为发布级中文配音。")
        return ProviderStatus(
            self.id,
            False,
            "缺少 VOLCENGINE_TTS_APP_ID、VOLCENGINE_TTS_ACCESS_TOKEN 或 VOLCENGINE_TTS_CLUSTER。",
        )

    def setup_hint(self) -> str:
        return (
            "配置 VOLCENGINE_TTS_APP_ID、VOLCENGINE_TTS_ACCESS_TOKEN、"
            "VOLCENGINE_TTS_CLUSTER 后使用 --provider volcengine_tts。"
        )

    def license_info(self) -> LicenseInfo:
        return LicenseInfo("Volcengine Doubao TTS API", "https://www.volcengine.com/docs/6561/1257584")

    def synthesize(self, payload: dict[str, Any]) -> tuple[bytes, float]:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise LingjianError(
                "TTS_OUTPUT_INVALID",
                "火山 TTS 输入文本为空。",
                "请先生成包含 narration_text 的脚本。",
                {"provider": self.id},
            )
        voice = str(payload.get("voice") or os.getenv("VOLCENGINE_TTS_VOICE_TYPE") or "")
        response = _post_tts(
            {
                "app": {
                    "appid": os.getenv("VOLCENGINE_TTS_APP_ID", ""),
                    "token": os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN", ""),
                    "cluster": os.getenv("VOLCENGINE_TTS_CLUSTER", ""),
                },
                "user": {"uid": os.getenv("VOLCENGINE_TTS_USER_ID", "lingjian-local")},
                "audio": {
                    "voice_type": voice or os.getenv("VOLCENGINE_TTS_VOICE_TYPE", ""),
                    "encoding": "wav",
                    "speed_ratio": 1.0,
                },
                "request": {
                    "reqid": str(uuid.uuid4()),
                    "text": text,
                    "text_type": "plain",
                    "operation": "query",
                },
            }
        )
        audio = _decode_audio(response)
        return validate_tts_output(audio, _wav_duration_or_default(audio), self.id)


def _post_tts(payload: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN", "")
    endpoint = os.getenv("VOLCENGINE_TTS_ENDPOINT", VOLCENGINE_TTS_ENDPOINT)
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=VOLCENGINE_TTS_TIMEOUT_SEC) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LingjianError(
            classify_provider_error(exc.code, body),
            "火山豆包 TTS 请求被拒绝。",
            "请检查 AppID、Access Token、Cluster、音色与配额。",
            {"provider": "volcengine_tts", "status_code": exc.code},
        ) from exc
    except (TimeoutError, URLError) as exc:
        raise LingjianError(
            "PROVIDER_API_FAILED",
            "火山豆包 TTS 请求失败。",
            "请检查网络、火山 TTS 配置与账号权限。",
            {"provider": "volcengine_tts"},
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LingjianError(
            "PROVIDER_API_FAILED",
            "火山豆包 TTS 返回非 JSON 响应。",
            "请确认接口地址与账号配置。",
            {"provider": "volcengine_tts"},
        ) from exc
    if not isinstance(decoded, dict):
        raise LingjianError(
            "PROVIDER_API_FAILED",
            "火山豆包 TTS 响应顶层不是对象。",
            "请确认接口返回格式。",
            {"provider": "volcengine_tts"},
        )
    return decoded


def _decode_audio(response: dict[str, Any]) -> bytes:
    code = response.get("code")
    if code not in {0, 3000, "0", "3000", None}:
        raise LingjianError(
            "PROVIDER_API_FAILED",
            "火山豆包 TTS 返回失败状态。",
            "请检查火山 TTS 音色、配额与文本内容。",
            {"provider": "volcengine_tts", "status_code": code},
        )
    audio_base64 = response.get("data") or response.get("audio_base64")
    if not isinstance(audio_base64, str) or not audio_base64:
        raise LingjianError(
            "TTS_OUTPUT_INVALID",
            "火山豆包 TTS 未返回有效音频。",
            "请确认接口返回 data 字段为 base64 音频。",
            {"provider": "volcengine_tts"},
        )
    try:
        return base64.b64decode(audio_base64, validate=True)
    except binascii.Error as exc:
        raise LingjianError(
            "TTS_OUTPUT_INVALID",
            "火山豆包 TTS 返回的音频 base64 无效。",
            "请确认接口返回 data 字段。",
            {"provider": "volcengine_tts"},
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
