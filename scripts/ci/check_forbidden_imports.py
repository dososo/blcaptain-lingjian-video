from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci._scan import iter_text_files

DENY = {"remotion", "hyperframes", "playwright"}


def check_forbidden_imports(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for path in iter_text_files(paths):
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name in DENY:
                        findings.append(f"{path}:{name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                name = node.module.split(".")[0]
                if name in DENY:
                    findings.append(f"{path}:{name}")
    return findings


if __name__ == "__main__":
    found = check_forbidden_imports(["packages/core", "providers"])
    if found:
        print("\n".join(found))
        raise SystemExit(1)
