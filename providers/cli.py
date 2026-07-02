from __future__ import annotations

import base64
import binascii
import json
import os
import shlex
import shutil
import subprocess
from typing import Any

from packages.core.errors import LingjianError
from providers.base import LicenseInfo, Provider, ProviderStatus
from providers.validation import validate_script_output, validate_tts_output

CLI_PROVIDER_TIMEOUT_SEC = 60


class CliProvider(Provider):
    def __init__(
        self,
        provider_id: str,
        name: str,
        kind: str,
        env_var: str,
        capabilities: list[str],
    ) -> None:
        self.id = provider_id
        self.name = name
        self.kind = kind
        self.env_var = env_var
        self.capabilities = capabilities
        self.is_mock = False

    def _argv(self) -> list[str]:
        raw = os.getenv(self.env_var, "")
        return shlex.split(raw) if raw else []

    def is_installed(self) -> bool:
        argv = self._argv()
        return bool(argv and shutil.which(argv[0]))

    def is_configured(self) -> bool:
        return self.is_installed()

    def doctor(self) -> ProviderStatus:
        if self.is_configured():
            return ProviderStatus(self.id, True, "本机 CLI provider 已配置,可用于 release。")
        return ProviderStatus(self.id, False, f"缺少可执行的 {self.env_var}。")

    def setup_hint(self) -> str:
        return (
            f"设置 {self.env_var}=<本机可执行命令>,"
            "命令需从 stdin 读取 JSON 并向 stdout 输出 JSON。"
        )

    def license_info(self) -> LicenseInfo:
        return LicenseInfo("User supplied CLI provider")

    def _run_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        argv = self._argv()
        if not argv or not shutil.which(argv[0]):
            raise LingjianError(
                "PROVIDER_NOT_CONFIGURED",
                "CLI provider 未配置或不可执行。",
                self.setup_hint(),
                {"provider": self.id, "env_var": self.env_var},
            )
        try:
            completed = subprocess.run(
                argv,
                input=json.dumps(payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                check=False,
                timeout=CLI_PROVIDER_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as exc:
            raise LingjianError(
                "PROVIDER_TIMEOUT",
                "CLI provider 执行超时。",
                "请检查本机 CLI provider 是否可在 60 秒内返回 JSON。",
                {"provider": self.id},
            ) from exc
        if completed.returncode != 0:
            raise LingjianError(
                "PROVIDER_CLI_FAILED",
                "CLI provider 执行失败。",
                "请直接运行配置的 CLI 命令排查 stderr。",
                {"provider": self.id, "exit_code": completed.returncode},
            )
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise LingjianError(
                "LLM_INVALID_JSON",
                "CLI provider 没有输出合法 JSON。",
                "请让 CLI provider stdout 只输出 JSON。",
                {"provider": self.id},
            ) from exc
        if not isinstance(payload, dict):
            raise LingjianError(
                "LLM_INVALID_JSON",
                "CLI provider JSON 顶层必须是对象。",
                "请输出 JSON object。",
                {"provider": self.id},
            )
        return payload

    def generate_script(self, payload: dict[str, Any]) -> dict[str, Any]:
        return validate_script_output(
            self._run_json({"task": "generate_script", **payload}),
            self.id,
        )

    def synthesize(self, payload: dict[str, Any]) -> tuple[bytes, float]:
        response = self._run_json({"task": "synthesize", **payload})
        audio_base64 = response.get("audio_base64")
        if not isinstance(audio_base64, str) or not audio_base64:
            raise LingjianError(
                "TTS_OUTPUT_INVALID",
                "CLI TTS provider 返回的音频无效。",
                "请让 TTS CLI 输出非空 audio_base64 和大于 0 的 duration_sec。",
                {"provider": self.id},
            )
        try:
            audio = base64.b64decode(audio_base64, validate=True)
            duration = float(response.get("duration_sec"))
        except (binascii.Error, TypeError, ValueError) as exc:
            raise LingjianError(
                "TTS_OUTPUT_INVALID",
                "CLI TTS provider 返回的音频或时长无效。",
                "请让 TTS CLI 输出合法 base64 音频和大于 0 的 duration_sec。",
                {"provider": self.id},
            ) from exc
        return validate_tts_output(audio, duration, self.id)
