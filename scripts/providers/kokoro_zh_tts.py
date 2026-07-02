from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Any

DEFAULT_VOICE = "zf_xiaobei"
DEFAULT_SAMPLE_RATE = 24000


def main() -> int:
    parser = argparse.ArgumentParser(description="LingJian Kokoro TTS adapter")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.probe:
        return 0 if _probe() else 1
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        audio, duration = _synthesize(payload)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "audio_base64": base64.b64encode(audio).decode("ascii"),
                "duration_sec": duration,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _probe() -> bool:
    if find_spec("kokoro_onnx") and find_spec("soundfile"):
        model, voices = _kokoro_onnx_paths()
        return model.exists() and voices.exists()
    return bool(find_spec("kokoro") and find_spec("soundfile"))


def _synthesize(payload: dict[str, Any]) -> tuple[bytes, float]:
    text = str(payload.get("text") or "").strip()
    if not text:
        raise RuntimeError("Kokoro 输入文本为空。")
    voice = _voice(str(payload.get("voice") or ""))
    if find_spec("kokoro_onnx") and find_spec("soundfile"):
        return _synthesize_onnx(text, voice)
    if find_spec("kokoro") and find_spec("soundfile"):
        return _synthesize_pipeline(text, voice)
    raise RuntimeError("未安装 Kokoro 运行包。请先运行 uv sync 安装 kokoro-onnx/soundfile。")


def _synthesize_onnx(text: str, voice: str) -> tuple[bytes, float]:
    import soundfile as sf
    from kokoro_onnx import EspeakConfig, Kokoro

    model_path, voices_path = _kokoro_onnx_paths()
    if not model_path.exists() or not voices_path.exists():
        raise RuntimeError("未找到 Kokoro ONNX 模型或 voices 文件。")
    kokoro = Kokoro(
        str(model_path),
        str(voices_path),
        espeak_config=EspeakConfig(
            lib_path=_first_existing(
                [
                    "/opt/homebrew/lib/libespeak-ng.dylib",
                    "/usr/local/lib/libespeak-ng.dylib",
                ]
            ),
            data_path=_first_existing(
                [
                    "/opt/homebrew/share/espeak-ng-data",
                    "/usr/local/share/espeak-ng-data",
                ]
            ),
        ),
    )
    audio, sample_rate = kokoro.create(text, voice=voice, lang="cmn")
    return _wav_bytes(audio, int(sample_rate), sf)


def _synthesize_pipeline(text: str, voice: str) -> tuple[bytes, float]:
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="z")
    chunks = [audio for _, _, audio in pipeline(text, voice=voice)]
    if not chunks:
        raise RuntimeError("Kokoro 没有返回音频。")
    return _wav_bytes(np.concatenate(chunks), DEFAULT_SAMPLE_RATE, sf)


def _wav_bytes(audio: Any, sample_rate: int, sf: Any) -> tuple[bytes, float]:
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV")
    raw = buffer.getvalue()
    duration = max(float(len(audio)) / float(sample_rate), 0.1)
    return raw, duration


def _kokoro_onnx_paths() -> tuple[Path, Path]:
    cache_root = Path(os.getenv("LINGJIAN_KOKORO_CACHE", "~/.cache/hyperframes/tts")).expanduser()
    return (
        cache_root / "models" / "kokoro-v1.0.onnx",
        cache_root / "voices" / "voices-v1.0.bin",
    )


def _voice(raw: str) -> str:
    if raw and raw not in {"test-voice", "release-voice", "v1", "default"}:
        return raw
    return os.getenv("LINGJIAN_KOKORO_VOICE", DEFAULT_VOICE)


def _first_existing(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


if __name__ == "__main__":
    raise SystemExit(main())
