#!/usr/bin/env python3
from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

COMMAND_TIMEOUT_SEC = 90
FFMPEG_TIMEOUT_SEC = 90
MAX_OUTPUT_CHARS = 5000


def _redact_sensitive_text(value: str) -> str:
    redacted = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)\S+", r"\1***", value)
    redacted = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|token|secret|password)\s*=\s*([^\s]+)",
        r"\1=***",
        redacted,
    )
    redacted = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1***", redacted)
    return redacted


def _run_command(command: str) -> str:
    try:
        args = shlex.split(command)
    except ValueError:
        args = ["zsh", "-lc", command]
    if not args:
        return "command: (empty)\nstatus: failed_empty_command"
    try:
        completed = subprocess.run(
            args,
            text=True,
            capture_output=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired as exc:
        return _redact_sensitive_text(
            f"command: {command}\nstatus: timeout\nerror: {exc}"
        )
    except OSError as exc:
        return _redact_sensitive_text(
            f"command: {command}\nstatus: failed_to_start\nerror: {exc}"
        )
    output = "\n".join(
        [
            f"command: {command}",
            f"exit_code: {completed.returncode}",
            "",
            "stdout:",
            completed.stdout or "(empty)",
            "",
            "stderr:",
            completed.stderr or "(empty)",
        ]
    )
    return _redact_sensitive_text(output[:MAX_OUTPUT_CHARS])


def _ffmpeg_escape_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


def _render_terminal_video(text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["LINGJIAN TERMINAL EVIDENCE", *text.splitlines()]
    compact = "\n".join(lines[:22])
    with tempfile.TemporaryDirectory(prefix="lingjian-terminal-drawtext-") as tmp:
        textfile = Path(tmp) / "terminal.txt"
        textfile.write_text(compact, encoding="utf-8")
        textfile_arg = _ffmpeg_escape_filter_value(str(textfile))
        vf = (
            "drawtext="
            "fontcolor=0xE5F0FF:"
            "fontsize=34:"
            "line_spacing=10:"
            "box=1:"
            "boxcolor=0x020617CC:"
            "boxborderw=28:"
            "expansion=none:"
            f"textfile={textfile_arg}:"
            "x=70:"
            "y='110+24*sin(2*PI*t/6)'"
        )
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x020617:s=1080x1920:d=4.5:r=30",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-y",
            str(output_path),
        ]
        subprocess.run(command, check=True, timeout=FFMPEG_TIMEOUT_SEC)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: terminal_record_cli.py '<command>' <output.mp4>", file=sys.stderr)
        return 2
    command = argv[1]
    output_path = Path(argv[2])
    text = _run_command(command)
    with tempfile.TemporaryDirectory(prefix="lingjian-terminal-record-") as tmp:
        transcript = Path(tmp) / "terminal.txt"
        transcript.write_text(text, encoding="utf-8")
        _render_terminal_video(text, output_path)
    print('{"ok":true,"recording_tool":"terminal-output-video"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
