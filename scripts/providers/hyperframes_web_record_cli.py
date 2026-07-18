from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CAPTURE_TIMEOUT_SEC = 120
FFMPEG_TIMEOUT_SEC = 90
MIN_SCREENSHOTS = 2
SCREENSHOT_DURATION_SEC = 1.6


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "usage: hyperframes_web_record_cli.py <url> <output.mp4>",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    url = argv[1]
    output_path = Path(argv[2]).resolve()
    npx = shutil.which("npx")
    ffmpeg = shutil.which("ffmpeg")
    if not npx or not ffmpeg:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "missing npx or ffmpeg",
                    "hint_zh": "网页动态证据捕获需要 npx hyperframes 与 ffmpeg。",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lingjian-web-record-") as tmp:
        capture_dir = Path(tmp) / "capture"
        capture = subprocess.run(
            [
                npx,
                "hyperframes",
                "capture",
                url,
                "-o",
                str(capture_dir),
                "--max-screenshots=8",
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=CAPTURE_TIMEOUT_SEC,
        )
        if capture.returncode != 0:
            print(_stderr_json("hyperframes capture failed", capture.stderr), file=sys.stderr)
            return 1
        screenshots = sorted((capture_dir / "screenshots").glob("scroll-*.png"))
        if len(screenshots) < MIN_SCREENSHOTS:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "not enough scroll screenshots",
                        "screenshot_count": len(screenshots),
                        "hint_zh": (
                            "网页动态证据至少需要两个真实滚动位置截图;"
                            "单张截图不能冒充录屏。"
                        ),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1
        concat_file = Path(tmp) / "screenshots.txt"
        concat_file.write_text(_concat_demuxer(screenshots), encoding="utf-8")
        ffmpeg_run = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-vf",
                (
                    "scale=1080:1920:force_original_aspect_ratio=decrease,"
                    "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x0b1020,"
                    "setsar=1,format=yuv420p"
                ),
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=FFMPEG_TIMEOUT_SEC,
        )
        if (
            ffmpeg_run.returncode != 0
            or not output_path.exists()
            or output_path.stat().st_size <= 0
        ):
            print(_stderr_json("ffmpeg render failed", ffmpeg_run.stderr), file=sys.stderr)
            return 1
    print(
        json.dumps(
            {
                "ok": True,
                "recording_tool": "hyperframes-capture-scroll",
                "output_path": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _concat_demuxer(screenshots: list[Path]) -> str:
    lines: list[str] = []
    for screenshot in screenshots:
        lines.append(f"file '{_escape_concat_path(screenshot)}'")
        lines.append(f"duration {SCREENSHOT_DURATION_SEC:.2f}")
    lines.append(f"file '{_escape_concat_path(screenshots[-1])}'")
    return "\n".join(lines) + "\n"


def _escape_concat_path(path: Path) -> str:
    return str(path).replace("'", r"'\''")


def _stderr_json(error: str, stderr: str) -> str:
    lines = [line for line in (stderr or "").splitlines() if line.strip()]
    return json.dumps(
        {
            "ok": False,
            "error": error,
            "stderr_tail": "\n".join(lines[-6:])[:800],
        },
        ensure_ascii=False,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
