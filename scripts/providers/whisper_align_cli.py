# ruff: noqa: E501
"""LingJian Whisper 逐字对齐适配器 —— 把配音音频转成真·时间轴字幕 cue。

灵剪硬规则:字幕/卡点时间必须从音频测出,不许字数估算(估切点必错,已实证)。
本适配器用 faster-whisper 识别配音音频,产出带真实起止时间的 caption cue;
渲染层 `_voice_caption_raw_cues` 会用 voice_segment 里的 `timed_captions` 顶替估算。

契约:
- `--probe`          有 faster-whisper 返回 0,否则 1。
- stdin JSON payload  `{"audio_path": <绝对路径>, "language": "zh", "model": "base"?}`
- stdout JSON         `{"timed_captions": [{"text","start_sec","end_sec","source":"whisper","timing_basis":"whisper_segment"}], "language":..., "segments": N}`

模型默认 `base`(快、够用于对齐时间);可用环境变量 LINGJIAN_WHISPER_MODEL 覆盖。首次会下载模型权重。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="LingJian Whisper alignment adapter")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.probe:
        return 0 if _whisper_available() else 1
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = _align(payload)
    except Exception as exc:  # noqa: BLE001 — 失败即非 0,上游回落估算
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    return True


def _align(payload: dict[str, Any]) -> dict[str, Any]:
    audio_path = Path(str(payload.get("audio_path") or "")).expanduser()
    if not audio_path.is_absolute() or not audio_path.exists():
        raise RuntimeError("audio_path 必须是存在的绝对路径。")
    language = str(payload.get("language") or "zh").strip() or "zh"
    model_name = str(payload.get("model") or os.environ.get("LINGJIAN_WHISPER_MODEL") or "base").strip()

    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=True,
        vad_filter=True,
    )

    cues: list[dict[str, Any]] = []
    index = 0
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        start = float(seg.start)
        end = float(seg.end)
        if end <= start:
            continue
        index += 1
        cues.append(
            {
                "index": index,
                "text": text,
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "source": "whisper",
                "timing_basis": "whisper_segment",
            }
        )
    return {
        "timed_captions": cues,
        "language": language,
        "model": model_name,
        "segments": len(cues),
        "audio_duration_sec": round(float(getattr(info, "duration", 0.0)), 3),
    }


if __name__ == "__main__":
    raise SystemExit(main())
