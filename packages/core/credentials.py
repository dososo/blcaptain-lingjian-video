from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

KNOWN_SECRET_NAMES = [
    "OPENAI_API_KEY",
    "OPENAI_TTS_API_KEY",
    "ANTHROPIC_API_KEY",
]


@dataclass(frozen=True, slots=True)
class CredentialBackend:
    name: str
    available: bool


def detect_secret_store() -> CredentialBackend:
    system = platform.system().lower()
    if system == "darwin":
        return CredentialBackend("macos-keychain", shutil.which("security") is not None)
    if system == "windows":
        return CredentialBackend("windows-credential-manager", shutil.which("cmdkey") is not None)
    return CredentialBackend("secret-service", shutil.which("secret-tool") is not None)


def credential_status() -> dict[str, Any]:
    backend = detect_secret_store()
    return {
        "secret_store_backend": backend.name,
        "secret_store_available": backend.available,
        "default_mode": "ephemeral-env",
        "ephemeral_env": {
            name: {"present": bool(os.getenv(name)), "value": "***" if os.getenv(name) else ""}
            for name in KNOWN_SECRET_NAMES
        },
        "message_zh": (
            "默认只读取当前 shell 环境变量,不落盘。需要持久化时优先使用 OS 安全存储。"
        ),
    }


def forget_credential(name: str) -> dict[str, Any]:
    backend = detect_secret_store()
    removed = False
    if backend.available:
        removed = _forget_from_backend(backend.name, name)
    return {
        "ok": True,
        "name": name,
        "secret_store_backend": backend.name,
        "secret_store_available": backend.available,
        "removed": removed,
        "message_zh": (
            "已尝试从安全存储撤销凭据；当前 shell 环境变量如仍存在,请在 shell 中 unset。"
        ),
    }


def _forget_from_backend(backend_name: str, name: str) -> bool:
    try:
        if backend_name == "macos-keychain":
            completed = subprocess.run(
                ["security", "delete-generic-password", "-s", f"lingjian:{name}"],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            return completed.returncode == 0
        if backend_name == "secret-service":
            completed = subprocess.run(
                ["secret-tool", "clear", "service", "lingjian", "account", name],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            return completed.returncode == 0
        if backend_name == "windows-credential-manager":
            completed = subprocess.run(
                ["cmdkey", f"/delete:lingjian:{name}"],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
    return False
