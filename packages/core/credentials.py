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
    "VOLCENGINE_TTS_API_KEY",
    "VOLCENGINE_ARK_API_KEY",
]

# 凭据在系统安全存储里的命名标准(唯一标准,见 docs/ONBOARDING.md +
# tests/test_capability_onboarding.py 回归测试):
# macOS Keychain / Linux Secret Service 均用 service = account = "lingjian:<NAME>"。
# Windows 走用户环境变量(见 docs/ONBOARDING.md,用 setx / SetEnvironmentVariable(...,"User")),
# 重开终端后进程环境直接可读,因此 read_credential 无需 Windows 分支——inject 时 os.environ 会先命中。
_SECRET_NS = "lingjian"


def _secret_id(name: str) -> str:
    return f"{_SECRET_NS}:{name}"


@dataclass(frozen=True, slots=True)
class CredentialBackend:
    name: str
    available: bool


def detect_secret_store() -> CredentialBackend:
    system = platform.system().lower()
    if system == "darwin":
        return CredentialBackend("macos-keychain", shutil.which("security") is not None)
    if system == "windows":
        # 标准:Windows 用用户环境变量,不依赖外部凭据工具;读取靠进程环境。
        return CredentialBackend("windows-user-env", True)
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


def read_credential(name: str) -> str:
    """从系统安全存储读取 lingjian:{name} 的值。找不到返回空串。key 只在内存,不落盘、不回显。

    命名对齐 ONBOARDING_ARK_KEY.md 标准:service = account = "lingjian:<NAME>"。
    Windows 走用户环境变量(inject 前 os.environ 已命中),故此处不设 Windows 分支。
    """
    secret_id = _secret_id(name)
    backend = detect_secret_store()
    if not backend.available:
        return ""
    try:
        if backend.name == "macos-keychain":
            completed = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    secret_id,
                    "-a",
                    secret_id,
                    "-w",
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            if completed.returncode == 0:
                return completed.stdout.strip()
        elif backend.name == "secret-service":
            completed = subprocess.run(
                ["secret-tool", "lookup", "service", secret_id, "account", secret_id],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            if completed.returncode == 0:
                return completed.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return ""


def inject_stored_credentials(names: list[str] | None = None) -> list[str]:
    """把已存入系统安全存储的 lj 凭据注入当前进程 os.environ(仅当环境里还没有)。

    让用户把 key 一次存进钥匙串后,后续跑 lj 无需每次手动 export。返回本次注入的名字列表。
    key 只驻留本进程内存,不写仓库/日志/产物。
    """
    injected: list[str] = []
    for name in names or KNOWN_SECRET_NAMES:
        if (os.environ.get(name) or "").strip():
            continue
        value = read_credential(name)
        if value:
            os.environ[name] = value
            injected.append(name)
    return injected


def _forget_from_backend(backend_name: str, name: str) -> bool:
    secret_id = _secret_id(name)
    try:
        if backend_name == "macos-keychain":
            completed = subprocess.run(
                ["security", "delete-generic-password", "-s", secret_id, "-a", secret_id],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            return completed.returncode == 0
        if backend_name == "secret-service":
            completed = subprocess.run(
                ["secret-tool", "clear", "service", secret_id, "account", secret_id],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            return completed.returncode == 0
        # Windows:key 存在用户环境变量里,无法用一条可移植命令自动删除;
        # 交由用户在系统环境变量设置里移除(status/forget 文案已提示)。
    except (OSError, subprocess.TimeoutExpired):
        return False
    return False
