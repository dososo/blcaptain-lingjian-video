from __future__ import annotations

import math
from typing import Any

from packages.core.errors import LingjianError

MIN_TOTAL_NARRATION_CHARS = 6


def validate_script_output(payload: dict[str, Any], provider_id: str) -> dict[str, Any]:
    scenes = payload.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise _thin_script(provider_id)

    total_chars = 0
    for scene in scenes:
        if not isinstance(scene, dict):
            raise _thin_script(provider_id)
        narration = scene.get("narration_text")
        if not isinstance(narration, str) or not narration.strip():
            raise _thin_script(provider_id)
        total_chars += len("".join(narration.split()))

    if total_chars < MIN_TOTAL_NARRATION_CHARS:
        raise _thin_script(provider_id)
    return payload


def validate_tts_output(audio: bytes, duration_sec: float, provider_id: str) -> tuple[bytes, float]:
    if not audio or not math.isfinite(duration_sec) or duration_sec <= 0:
        raise LingjianError(
            "TTS_OUTPUT_INVALID",
            "TTS provider 返回的音频或时长无效。",
            "请确认 TTS provider 返回非空音频字节,且 duration_sec 大于 0。",
            {"provider": provider_id},
        )
    return audio, duration_sec


def _thin_script(provider_id: str) -> LingjianError:
    return LingjianError(
        "LLM_OUTPUT_TOO_THIN",
        "LLM provider 返回的脚本内容过薄。",
        "请确认 provider 返回非空 scenes,且每个 scene 包含足够的 narration_text。",
        {"provider": provider_id},
    )
