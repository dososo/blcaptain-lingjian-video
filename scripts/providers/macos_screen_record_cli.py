#!/usr/bin/env python3
"""Record a short real screen video for a Codex operation evidence slot.

Contract: macos_screen_record_cli.py <task> <output.mp4>
The task text is intentionally not rendered or logged here. It is only part of
the generic recorder contract used by `lj ingest codex`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_SECONDS = 6


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: macos_screen_record_cli.py <task> <output.mp4>", file=sys.stderr)
        return 2
    output_path = Path(argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    screencapture = shutil.which("screencapture")
    if not screencapture:
        print("screencapture is not available", file=sys.stderr)
        return 3
    command = [
        screencapture,
        "-v",
        "-V",
        str(DEFAULT_SECONDS),
        "-x",
        str(output_path),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        if stderr:
            print(stderr[-1000:], file=sys.stderr)
        return completed.returncode or 1
    if not output_path.exists() or output_path.stat().st_size <= 0:
        print("screencapture completed but output video is empty", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
