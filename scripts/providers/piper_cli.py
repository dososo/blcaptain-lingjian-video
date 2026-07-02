from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

DEFAULT_VOICE = "zh_CN-huayan-medium"
PIPER_TIMEOUT_SEC = 120


def main() -> int:
    parser = argparse.ArgumentParser(description="LingJian Piper TTS adapter")
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
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "piper", "--help"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _synthesize(payload: dict[str, Any]) -> tuple[bytes, float]:
    text = str(payload.get("text") or "").strip()
    if not text:
        raise RuntimeError("Piper 输入文本为空。")
    voice = _voice(str(payload.get("voice") or ""))
    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "voice.wav"
        completed = subprocess.run(
            [sys.executable, "-m", "piper", "-m", voice, "-f", str(output), "--", text],
            text=True,
            capture_output=True,
            check=False,
            timeout=PIPER_TIMEOUT_SEC,
        )
        if completed.returncode != 0:
            raise RuntimeError("Piper 执行失败。")
        audio = output.read_bytes() if output.exists() else b""
    if not audio:
        raise RuntimeError("Piper 没有返回音频。")
    return audio, _wav_duration(audio)


def _voice(raw: str) -> str:
    if raw and raw not in {"test-voice", "v1", "default"}:
        return raw
    return DEFAULT_VOICE


def _wav_duration(audio: bytes) -> float:
    with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
        handle.write(audio)
        handle.flush()
        with wave.open(handle.name, "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate() or 1
    return max(float(frames) / float(rate), 0.1)


if __name__ == "__main__":
    raise SystemExit(main())
