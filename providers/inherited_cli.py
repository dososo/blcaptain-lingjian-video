from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from packages.core.errors import LingjianError
from providers.base import LicenseInfo, Provider, ProviderStatus
from providers.validation import validate_script_output, validate_tts_output

INHERITED_CLI_TIMEOUT_SEC = 60


class InheritedLLMProvider(Provider):
    def __init__(self, provider_id: str, name: str, command_name: str, source_type: str) -> None:
        self.id = provider_id
        self.name = name
        self.kind = "llm"
        self.command_name = command_name
        self.source_type = source_type
        self.capabilities = ["generate_script"]
        self.is_mock = False

    def is_installed(self) -> bool:
        return shutil.which(self.command_name) is not None

    def is_configured(self) -> bool:
        return self.is_installed()

    def doctor(self) -> ProviderStatus:
        if self.is_configured():
            return ProviderStatus(self.id, True, f"{self.name} 已检测到,将继承当前 CLI 登录能力。")
        return ProviderStatus(self.id, False, f"未检测到 {self.command_name}。")

    def setup_hint(self) -> str:
        return f"安装并登录官方 {self.command_name} CLI；灵剪只调用命令,不读取凭据文件。"

    def license_info(self) -> LicenseInfo:
        return LicenseInfo(f"{self.name} inherited CLI")

    def generate_script(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = _script_prompt(payload)
        stdout = _run_text(self.id, self._argv(prompt), input_text=None)
        generated = _json_or_text_scene(stdout)
        return validate_script_output(generated, self.id)

    def _argv(self, prompt: str) -> list[str]:
        binary = self.command_name
        if self.command_name == "claude":
            return [binary, "-p", prompt]
        if self.command_name == "codex":
            return [binary, "exec", "--skip-git-repo-check", prompt]
        if self.command_name == "ollama":
            model = os.getenv("LINGJIAN_OLLAMA_MODEL", "llama3.1")
            return [binary, "run", model, prompt]
        return [binary, prompt]


class LocalTTSProvider(Provider):
    def __init__(self, provider_id: str, name: str, command_name: str) -> None:
        self.id = provider_id
        self.name = name
        self.kind = "tts"
        self.command_name = command_name
        self.capabilities = ["synthesize"]
        self.is_mock = False

    def is_installed(self) -> bool:
        return shutil.which(self.command_name) is not None

    def is_configured(self) -> bool:
        return self.is_installed()

    def doctor(self) -> ProviderStatus:
        if self.is_configured():
            return ProviderStatus(self.id, True, f"{self.name} 已检测到,可作为本机零 key TTS。")
        return ProviderStatus(self.id, False, f"未检测到 {self.command_name}。")

    def setup_hint(self) -> str:
        return f"安装 {self.command_name} 后可作为本机 TTS；订阅 CLI 通常不包含 TTS。"

    def license_info(self) -> LicenseInfo:
        return LicenseInfo(f"{self.name} local TTS")

    def synthesize(self, payload: dict[str, Any]) -> tuple[bytes, float]:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise LingjianError(
                "TTS_OUTPUT_INVALID",
                "TTS 输入文本为空。",
                "请先生成包含 narration_text 的脚本。",
                {"provider": self.id},
            )
        if self.command_name == "say":
            return self._synthesize_with_say(text, str(payload.get("voice") or ""))
        stdout = _run_text(self.id, [self.command_name], input_text=text)
        audio = stdout.encode("utf-8")
        return validate_tts_output(audio, _estimate_duration(text), self.id)

    def _synthesize_with_say(self, text: str, voice: str) -> tuple[bytes, float]:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "voice.aiff"
            argv = [self.command_name]
            if voice and voice != "v1":
                argv.extend(["-v", voice])
            argv.extend(["-o", str(output_path), text])
            _run_text(self.id, argv, input_text=None)
            audio = output_path.read_bytes() if output_path.exists() else b""
        return validate_tts_output(audio, _estimate_duration(text), self.id)


def _run_text(provider_id: str, argv: list[str], input_text: str | None) -> str:
    if not argv or shutil.which(argv[0]) is None:
        raise LingjianError(
            "PROVIDER_NOT_CONFIGURED",
            "继承 CLI provider 未安装或不可执行。",
            "请运行 lj setup 查看可继承能力。",
            {"provider": provider_id},
        )
    completed = None
    for attempt in range(2):
        try:
            completed = subprocess.run(
                argv,
                input=input_text,
                text=True,
                capture_output=True,
                check=False,
                timeout=INHERITED_CLI_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as exc:
            if attempt == 0:
                continue
            raise LingjianError(
                "PROVIDER_TIMEOUT",
                "继承 CLI provider 执行超时。",
                "请确认 CLI 已登录且可在 60 秒内返回,或稍后重试。",
                {"provider": provider_id},
            ) from exc
        if completed.returncode == 0:
            break
    assert completed is not None
    if completed.returncode != 0:
        raise LingjianError(
            "PROVIDER_CLI_FAILED",
            "继承 CLI provider 执行失败。",
            "外部 CLI 偶发失败时可重试;若持续失败,请单独运行对应官方 CLI 确认已登录。",
            {"provider": provider_id, "exit_code": completed.returncode, "attempts": 2},
        )
    return (completed.stdout or "").strip()


def _script_prompt(payload: dict[str, Any]) -> str:
    return (
        "请为灵剪生成短视频脚本,只输出 JSON object,顶层包含 scenes 数组,"
        "每个 scene 至少包含 narration_text。参数:"
        + json.dumps(payload, ensure_ascii=False)
    )


def _json_or_text_scene(stdout: str) -> dict[str, Any]:
    decoded = _decode_json_object(stdout)
    if isinstance(decoded, dict):
        return decoded
    return {"scenes": [{"id": "s1", "narration_text": stdout}]}


def _decode_json_object(stdout: str) -> dict[str, Any] | None:
    candidates = [stdout, _strip_fenced_json(stdout), _json_slice(stdout)]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return decoded
    return None


def _strip_fenced_json(stdout: str) -> str:
    lines = stdout.strip().splitlines()
    if len(lines) >= 3 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return ""


def _json_slice(stdout: str) -> str:
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return stdout[start : end + 1]


def _estimate_duration(text: str) -> float:
    return max(len("".join(text.split())) / 8.0, 1.0)
