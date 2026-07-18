from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci._scan import iter_text_files, repo_root

DENY = ["--force", "SKIP_APPROVAL", "BYPASS_APPROVAL"]
ALLOW = [
    "tests/test_cli_contract.py",
    "tests/test_static_guards.py",
    "scripts/ci/check_no_force.py",
]


def check_no_force(paths: list[str]) -> list[str]:
    findings: list[str] = []
    root = repo_root()
    for path in iter_text_files(paths):
        rel_path = str(path.relative_to(root))
        if rel_path in ALLOW:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in DENY:
            if token in text:
                findings.append(f"{path}:{token}")
    return findings


if __name__ == "__main__":
    found = check_no_force(["apps", "packages", "providers", "engines"])
    if found:
        print("\n".join(found))
        raise SystemExit(1)
