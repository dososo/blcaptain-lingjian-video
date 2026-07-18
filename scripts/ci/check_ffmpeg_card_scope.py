from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci._scan import iter_text_files

DENY = ["zoompan", "Ken Burns", "keyframe", "shader", "transition library"]


def check_ffmpeg_card_scope(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for path in iter_text_files(paths):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in DENY:
            if token in text:
                findings.append(f"{path}:{token}")
    return findings


if __name__ == "__main__":
    found = check_ffmpeg_card_scope(["engines/ffmpeg_card"])
    if found:
        print("\n".join(found))
        raise SystemExit(1)
