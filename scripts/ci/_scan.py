from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".toml", ".yaml", ".yml", ".json"}
IGNORED_PARTS = {
    ".next",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "lingjian_video_studio.egg-info",
    "node_modules",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def iter_text_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    root = repo_root()
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            raise FileNotFoundError(f"scan target not found: {path}")
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            files.append(path)
        elif path.is_dir():
            files.extend(
                child
                for child in path.rglob("*")
                if child.is_file()
                and child.suffix in TEXT_SUFFIXES
                and not any(part in IGNORED_PARTS for part in child.parts)
            )
    return files
