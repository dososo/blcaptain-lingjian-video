from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci._scan import iter_text_files

DENY = [
    "engines.hyperframes",
    "engines.remotion",
    "from engines import hyperframes",
    "from engines import remotion",
]


def check_render_engine_m1(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for path in iter_text_files(paths):
        if str(path).startswith("docs/"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in DENY:
            if token in text:
                findings.append(f"{path}:{token}")
    return findings


if __name__ == "__main__":
    found = check_render_engine_m1(["packages", "engines"])
    if found:
        print("\n".join(found))
        raise SystemExit(1)
