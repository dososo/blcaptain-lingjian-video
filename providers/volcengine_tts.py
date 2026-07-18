from __future__ import annotations

import base64
import binascii
import json
import os
import struct
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
VOLCENGINE_TTS_LEGACY_ENDPOINT = "https://openspeech.bytedance.com/api/v1/tts"
VOLCENGINE_TTS_V3_ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
DEFAULT_VOLCENGINE_TTS_RESOURCE_ID = "seed-tts-2.0"
DEFAULT_VOLCENGINE_TTS_VOICE_TYPE = "zh_female_vv_uranus_bigtts"
DEFAULT_VOLCENGINE_TTS_VOICE_LABEL = "默认女声"
VOLCENGINE_TTS_CANDIDATE_VOICES = [
    (DEFAULT_VOLCENGINE_TTS_VOICE_TYPE, DEFAULT_VOLCENGINE_TTS_VOICE_LABEL),
    ("zh_female_qingxinnvsheng_uranus_bigtts", "清新女声"),
    ("zh_male_yangguangqingnian_uranus_bigtts", "阳光青年男声"),
    ("zh_male_yuanboxiaoshu_uranus_bigtts", "渊博小叔男声"),
    ("zh_male_qingshuangnanda_uranus_bigtts", "清爽男大"),
]


class VolcengineTTSProvider(Provider):
    id = "volcengine_tts"
    name = "火山豆包 TTS"
    kind = "tts"
    capabilities = ["synthesize"]
    is_mock = False
    prefer_continuous_full_track = True

    def is_installed(self) -> bool:
        return True

    def is_configured(self) -> bool:
        return bool(
            os.getenv("VOLCENGINE_TTS_API_KEY")
            or (
                os.getenv("VOLCENGINE_TTS_APP_ID")
                and os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN")
                and os.getenv("VOLCENGINE_TTS_CLUSTER")
            )
        )

    def doctor(self) -> ProviderStatus:
        if self.is_configured():
            return ProviderStatus(self.id, True, "火山豆包 TTS 已配置,可作为发布级中文配音。")
        return ProviderStatus(
            self.id,
            False,
            "缺少 VOLCENGINE_TTS_API_KEY。旧版兼容才需要 APP_ID、ACCESS_TOKEN、CLUSTER。",
        )

    def setup_hint(self) -> str:
        return (
            "新版火山豆包 TTS 只需配置 VOLCENGINE_TTS_API_KEY;"
            "默认使用 seed-tts-2.0 与中文女声音色。"
        )

    def license_info(self) -> LicenseInfo:
        return LicenseInfo("Volcengine Doubao TTS API", "https://www.volcengine.com/docs/6561/2528925")

    def resolve_voice_id(self, voice: str | None = None) -> str:
        return str(
            voice
            or os.getenv("VOLCENGINE_TTS_VOICE_TYPE")
            or DEFAULT_VOLCENGINE_TTS_VOICE_TYPE
        )

    def voice_label(self, voice: str | None = None) -> str:
        voice_id = self.resolve_voice_id(voice)
        for candidate_id, label in _configured_voice_candidates():
            if candidate_id == voice_id:
                return label
        return voice_id

    def voice_settings(self, voice: str | None = None) -> dict[str, Any]:
        return {
            "resource_id": os.getenv(
                "VOLCENGINE_TTS_RESOURCE_ID",
                DEFAULT_VOLCENGINE_TTS_RESOURCE_ID,
            ),
            "voice_type": self.resolve_voice_id(voice),
            "audio_format": os.getenv("VOLCENGINE_TTS_AUDIO_FORMAT", "wav"),
            "sample_rate": int(os.getenv("VOLCENGINE_TTS_SAMPLE_RATE", "24000")),
            "track_strategy": "continuous_full_track",
        }

    def discover_voice_options(
        self,
        sample_text: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []
        for voice_id, label in _configured_voice_candidates():
            if len(options) >= limit:
                break
            try:
                audio_bytes, duration = self.synthesize({"voice": voice_id, "text": sample_text})
            except LingjianError:
                continue
            options.append(
                {
                    "voice_id": voice_id,
                    "label_zh": label,
                    "sample_text": sample_text,
                    "audio_bytes": audio_bytes,
                    "duration_sec": duration,
                    "source": "synthesis_probe",
                }
            )
        if not options:
            raise LingjianError(
                "TTS_VOICE_OPTIONS_UNAVAILABLE",
                "未能生成可用的火山音色试听。",
                "请检查 API Key、Resource ID、音色权限和配额。",
                {"provider": self.id},
            )
        return options

    def synthesize(self, payload: dict[str, Any]) -> tuple[bytes, float]:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise LingjianError(
                "TTS_OUTPUT_INVALID",
                "火山 TTS 输入文本为空。",
                "请先生成包含 narration_text 的脚本。",
                {"provider": self.id},
            )
        voice = self.resolve_voice_id(str(payload.get("voice") or ""))
        if os.getenv("VOLCENGINE_TTS_API_KEY"):
            audio = _post_tts_v3(text, voice)
            return validate_tts_output(audio, _wav_duration_or_default(audio), self.id)
        response = _post_tts_legacy(
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


def _configured_voice_candidates() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    configured_voice = os.getenv("VOLCENGINE_TTS_VOICE_TYPE", "").strip()
    if configured_voice:
        candidates.append((configured_voice, "当前配置音色"))
    extra = os.getenv("VOLCENGINE_TTS_VOICE_CANDIDATES", "").strip()
    if extra:
        for item in extra.split(","):
            voice_id, _, label = item.strip().partition(":")
            if voice_id:
                candidates.append((voice_id, label or voice_id))
    candidates.extend(VOLCENGINE_TTS_CANDIDATE_VOICES)
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for voice_id, label in candidates:
        if voice_id in seen:
            continue
        seen.add(voice_id)
        deduped.append((voice_id, label))
    return deduped


def _post_tts_v3(text: str, voice: str) -> bytes:
    api_key = os.getenv("VOLCENGINE_TTS_API_KEY", "")
    resource_id = os.getenv(
        "VOLCENGINE_TTS_RESOURCE_ID",
        DEFAULT_VOLCENGINE_TTS_RESOURCE_ID,
    )
    endpoint = os.getenv("VOLCENGINE_TTS_V3_ENDPOINT", VOLCENGINE_TTS_V3_ENDPOINT)
    payload = {
        "user": {"uid": os.getenv("VOLCENGINE_TTS_USER_ID", "lingjian-local")},
        "req_params": {
            "text": text,
            "speaker": voice,
            "audio_params": {
                "format": os.getenv("VOLCENGINE_TTS_AUDIO_FORMAT", "wav"),
                "sample_rate": int(os.getenv("VOLCENGINE_TTS_SAMPLE_RATE", "24000")),
                "speed_ratio": float(os.getenv("VOLCENGINE_TTS_SPEED_RATIO", "1.0")),
            },
        },
    }
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=VOLCENGINE_TTS_TIMEOUT_SEC) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LingjianError(
            classify_provider_error(exc.code, body),
            "火山豆包 TTS 请求被拒绝。",
            "请检查 API Key、Resource ID、音色与配额。",
            {"provider": "volcengine_tts", "status_code": exc.code},
        ) from exc
    except (TimeoutError, URLError) as exc:
        raise LingjianError(
            "PROVIDER_API_FAILED",
            "火山豆包 TTS 请求失败。",
            "请检查网络、火山 TTS API Key 与账号权限。",
            {"provider": "volcengine_tts"},
        ) from exc
    except UnicodeDecodeError as exc:
        raise LingjianError(
            "PROVIDER_API_FAILED",
            "火山豆包 TTS 返回非文本流响应。",
            "请确认接口地址与账号配置。",
            {"provider": "volcengine_tts"},
        ) from exc
    return _decode_stream_audio(_decode_json_stream(raw))


def _post_tts_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN", "")
    endpoint = os.getenv("VOLCENGINE_TTS_ENDPOINT", VOLCENGINE_TTS_LEGACY_ENDPOINT)
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


def _decode_json_stream(raw: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    index = 0
    while index < len(raw):
        while index < len(raw) and raw[index].isspace():
            index += 1
        if index >= len(raw):
            break
        try:
            item, index = decoder.raw_decode(raw, index)
        except json.JSONDecodeError as exc:
            raise LingjianError(
                "PROVIDER_API_FAILED",
                "火山豆包 TTS 返回非 JSON 流。",
                "请确认接口地址与账号配置。",
                {"provider": "volcengine_tts"},
            ) from exc
        if isinstance(item, dict):
            objects.append(item)
    if not objects:
        raise LingjianError(
            "PROVIDER_API_FAILED",
            "火山豆包 TTS 返回空响应。",
            "请确认接口地址与账号配置。",
            {"provider": "volcengine_tts"},
        )
    return objects


def _decode_stream_audio(responses: list[dict[str, Any]]) -> bytes:
    chunks: list[bytes] = []
    for response in responses:
        code = response.get("code")
        if code not in {0, "0", 20000000, "20000000", None}:
            raise LingjianError(
                "PROVIDER_API_FAILED",
                "火山豆包 TTS 返回失败状态。",
                "请检查火山 TTS API Key、Resource ID、音色、配额与文本内容。",
                {"provider": "volcengine_tts", "status_code": code},
            )
        audio_base64 = response.get("data") or response.get("audio_base64")
        if not isinstance(audio_base64, str) or not audio_base64:
            continue
        try:
            chunks.append(base64.b64decode(audio_base64, validate=True))
        except binascii.Error as exc:
            raise LingjianError(
                "TTS_OUTPUT_INVALID",
                "火山豆包 TTS 返回的音频 base64 无效。",
                "请确认接口返回 data 字段。",
                {"provider": "volcengine_tts"},
            ) from exc
    if not chunks:
        raise LingjianError(
            "TTS_OUTPUT_INVALID",
            "火山豆包 TTS 未返回有效音频。",
            "请确认 API Key、Resource ID 与音色匹配。",
            {"provider": "volcengine_tts"},
        )
    return b"".join(chunks)


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
        return _streaming_wav_duration_or_default(audio)
    if frame_rate <= 0 or frame_count <= 0:
        return _streaming_wav_duration_or_default(audio)
    duration = frame_count / frame_rate
    byte_duration = _streaming_wav_duration_or_default(audio)
    if byte_duration > 0 and duration > byte_duration * 10:
        return byte_duration
    return duration


def _streaming_wav_duration_or_default(audio: bytes) -> float:
    if len(audio) < 44 or audio[0:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return 1.0
    offset = 12
    byte_rate = 0
    while offset + 8 <= len(audio):
        chunk_id = audio[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", audio, offset + 4)[0]
        data_start = offset + 8
        if chunk_id == b"fmt " and data_start + 16 <= len(audio):
            byte_rate = struct.unpack_from("<I", audio, data_start + 8)[0]
        if chunk_id == b"data":
            data_size = min(chunk_size, max(len(audio) - data_start, 0))
            if byte_rate > 0 and data_size > 0:
                return data_size / byte_rate
            return 1.0
        next_offset = data_start + chunk_size + (chunk_size % 2)
        if next_offset <= offset or next_offset > len(audio):
            break
        offset = next_offset
    return 1.0
