from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

PathLookup = Callable[[str], str | None]
FFMPEG_FILTER_TIMEOUT_SEC = 20


@dataclass(frozen=True, slots=True)
class CapabilityCandidate:
    id: str
    kind: str
    source_type: str
    configured: bool
    safe_for_release: bool
    label_zh: str
    provider_type: str | None = None
    command_name: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    hint: str | None = None
    setup_command: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "source_type": self.source_type,
            "configured": self.configured,
            "safe_for_release": self.safe_for_release,
            "label_zh": self.label_zh,
            "provider_type": self.provider_type,
            "command_name": self.command_name,
            "config_redacted": _redact_config(self.config),
            "hint": self.hint,
            "setup_command": self.setup_command,
        }


@dataclass(frozen=True, slots=True)
class CapabilityGroup:
    kind: str
    best: CapabilityCandidate
    candidates: list[CapabilityCandidate]

    def public_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "best": self.best.public_dict(),
            "candidates": [candidate.public_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    groups: dict[str, CapabilityGroup]
    summary_zh: str
    next_steps: list[str]

    def public_dict(self) -> dict[str, Any]:
        return {
            "capabilities": {
                kind: group.public_dict() for kind, group in self.groups.items()
            },
            "summary_zh": self.summary_zh,
            "next_steps": self.next_steps,
        }


def detect_capabilities(
    env: Mapping[str, str] | None = None,
    path_lookup: PathLookup | None = None,
    tool_overrides: dict[str, bool] | None = None,
) -> CapabilityReport:
    env_map = env or os.environ
    lookup = path_lookup or shutil.which
    groups = {
        "llm": _group("llm", _llm_candidates(env_map, lookup)),
        "tts": _group("tts", _tts_candidates(env_map, lookup)),
        "render": _group("render", _render_candidates(lookup, tool_overrides)),
        "font": _group("font", _font_candidates(tool_overrides)),
    }
    next_steps = _next_steps(groups)
    inherited = [
        group.best.label_zh
        for group in groups.values()
        if group.best.source_type in {"inherited-cli", "local-cli"} and group.best.configured
    ]
    if inherited:
        summary = "已继承/检测到 " + "、".join(inherited) + "，无需 key。"
    else:
        summary = "未检测到可直接继承的发布能力；请按缺失项逐步补齐。"
    return CapabilityReport(groups=groups, summary_zh=summary, next_steps=next_steps)


def provider_overrides_from_capabilities(
    report: CapabilityReport,
    env: Mapping[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    env_map = env or os.environ
    overrides: dict[str, list[dict[str, Any]]] = {"llm": [], "tts": []}
    for kind in ("llm", "tts"):
        candidates = sorted(
            report.groups[kind].candidates,
            key=lambda item: (not item.safe_for_release, not item.configured),
        )
        for candidate in candidates:
            if candidate.source_type == "missing":
                continue
            raw_config = dict(candidate.config)
            if candidate.id == "openai_compatible":
                raw_config = {
                    "api_key": env_map.get("OPENAI_API_KEY", ""),
                    "base_url": env_map.get("OPENAI_BASE_URL", ""),
                    "model": env_map.get("OPENAI_MODEL", ""),
                }
            if candidate.id == "openai_compatible_tts":
                raw_config = {
                    "api_key": env_map.get("OPENAI_TTS_API_KEY", ""),
                    "base_url": env_map.get("OPENAI_TTS_BASE_URL")
                    or env_map.get("OPENAI_BASE_URL", ""),
                    "model": env_map.get("OPENAI_TTS_MODEL", ""),
                }
            overrides[kind].append(
                {
                    "id": candidate.id,
                    "type": candidate.provider_type or "cli",
                    "configured": candidate.configured,
                    "is_mock": False,
                    "probe_ok": candidate.configured,
                    "command": candidate.command_name or "",
                    "config": raw_config,
                    "source_type": candidate.source_type,
                    "label_zh": candidate.label_zh,
                    "hint": _doctor_hint(candidate),
                    "setup_command": None,
                }
            )
    return overrides


def best_provider_id(kind: str) -> str | None:
    report = detect_capabilities()
    group = report.groups.get(kind)
    if not group or not group.best.safe_for_release:
        return None
    return group.best.id


def _group(kind: str, candidates: list[CapabilityCandidate]) -> CapabilityGroup:
    best = next((item for item in candidates if item.safe_for_release), candidates[-1])
    return CapabilityGroup(kind=kind, best=best, candidates=candidates)


def _llm_candidates(env: Mapping[str, str], lookup: PathLookup) -> list[CapabilityCandidate]:
    candidates = [
        _cli_candidate(
            "claude_cli",
            "llm",
            "inherited-cli",
            "Claude Code CLI",
            "claude",
            lookup,
            "已检测到 Claude Code CLI，将继承当前登录订阅能力。",
        ),
        _cli_candidate(
            "codex_cli",
            "llm",
            "inherited-cli",
            "Codex CLI",
            "codex",
            lookup,
            "已检测到 Codex CLI，将继承当前登录订阅能力。",
        ),
    ]
    llm_cli = _first_argv(env.get("LINGJIAN_LLM_CLI", ""))
    candidates.append(
        _cli_candidate(
            "llm_cli",
            "llm",
            "local-cli",
            "自定义 LLM CLI",
            llm_cli,
            lookup,
            "已检测到 LINGJIAN_LLM_CLI。",
            setup_command='export LINGJIAN_LLM_CLI="/path/to/real-llm"',
        )
    )
    candidates.extend(
        [
            _cli_candidate(
                "ollama_cli",
                "llm",
                "local-cli",
                "Ollama CLI",
                "ollama",
                lookup,
                "已检测到 Ollama 本机模型 CLI。",
                setup_command="brew install ollama",
            ),
            _cli_candidate(
                "llm_local_cli",
                "llm",
                "local-cli",
                "llm CLI",
                "llm",
                lookup,
                "已检测到 llm 本机模型 CLI。",
                setup_command="pipx install llm",
            ),
            _api_candidate(
                "openai_compatible",
                "llm",
                "OpenAI-compatible LLM",
                bool(
                    env.get("OPENAI_BASE_URL")
                    and env.get("OPENAI_API_KEY")
                    and env.get("OPENAI_MODEL")
                ),
                {
                    "api_key": env.get("OPENAI_API_KEY", ""),
                    "base_url": env.get("OPENAI_BASE_URL", ""),
                    "model": env.get("OPENAI_MODEL", ""),
                },
                "配置 OPENAI_BASE_URL、OPENAI_API_KEY、OPENAI_MODEL。",
            ),
            _missing(
                "llm",
                "缺少真实 LLM",
                "先安装/登录 claude 或 codex CLI；没有订阅 CLI 时再配置 OpenAI-compatible key。",
                "export OPENAI_BASE_URL=... OPENAI_API_KEY=... OPENAI_MODEL=...",
            ),
        ]
    )
    return candidates


def _tts_candidates(env: Mapping[str, str], lookup: PathLookup) -> list[CapabilityCandidate]:
    tts_cli = _first_argv(env.get("LINGJIAN_TTS_CLI", ""))
    candidates = [
        _cli_candidate(
            "tts_cli",
            "tts",
            "local-cli",
            "自定义 TTS CLI",
            tts_cli,
            lookup,
            "已检测到 LINGJIAN_TTS_CLI。",
            setup_command='export LINGJIAN_TTS_CLI="/path/to/real-tts"',
        ),
        _cli_candidate(
            "macos_say",
            "tts",
            "local-cli",
            "macOS say",
            "say",
            lookup,
            "已检测到 macOS say，本机零 key TTS 可用。",
        ),
        _cli_candidate(
            "piper_cli",
            "tts",
            "local-cli",
            "Piper CLI",
            "piper",
            lookup,
            "已检测到 Piper 本机 TTS。",
            setup_command="brew install piper",
        ),
        _cli_candidate(
            "espeak_ng",
            "tts",
            "local-cli",
            "espeak-ng",
            "espeak-ng",
            lookup,
            "已检测到 espeak-ng 本机 TTS。",
            setup_command="brew install espeak-ng",
        ),
        _api_candidate(
            "openai_compatible_tts",
            "tts",
            "OpenAI-compatible TTS",
            bool(
                env.get("OPENAI_TTS_API_KEY")
                and (env.get("OPENAI_TTS_BASE_URL") or env.get("OPENAI_BASE_URL"))
                and env.get("OPENAI_TTS_MODEL")
            ),
            {
                "api_key": env.get("OPENAI_TTS_API_KEY", ""),
                "base_url": env.get("OPENAI_TTS_BASE_URL") or env.get("OPENAI_BASE_URL", ""),
                "model": env.get("OPENAI_TTS_MODEL", ""),
            },
            "配置 OPENAI_TTS_API_KEY、OPENAI_TTS_BASE_URL、OPENAI_TTS_MODEL。",
        ),
        _missing(
            "tts",
            "缺少真实 TTS",
            "订阅 CLI 通常只覆盖 LLM，不含 TTS；"
            "请先使用 macOS say/Piper/espeak-ng，再考虑 TTS key。",
            'export OPENAI_TTS_BASE_URL=... OPENAI_TTS_API_KEY=... OPENAI_TTS_MODEL=...',
        ),
    ]
    return candidates


def _render_candidates(
    lookup: PathLookup,
    tool_overrides: dict[str, bool] | None,
) -> list[CapabilityCandidate]:
    ffmpeg_ok = _tool_available("ffmpeg", lookup, tool_overrides)
    ffprobe_ok = _tool_available("ffprobe", lookup, tool_overrides)
    drawtext_ok = ffmpeg_drawtext_available(lookup, tool_overrides)
    configured = ffmpeg_ok and ffprobe_ok and drawtext_ok
    hint = (
        "release 渲染必须本机安装 ffmpeg、ffprobe,且 ffmpeg 支持 drawtext/libfreetype。"
    )
    if ffmpeg_ok and ffprobe_ok and not drawtext_ok:
        hint = (
            "当前 ffmpeg 缺少 drawtext/libfreetype 滤镜,请安装带 freetype 的 ffmpeg,"
            "并用 `ffmpeg -hide_banner -h filter=drawtext` 或 "
            "`ffmpeg -filters | grep drawtext` 验证。"
        )
    return [
        CapabilityCandidate(
            id="ffmpeg_suite",
            kind="render",
            source_type="local-cli" if configured else "missing",
            configured=configured,
            safe_for_release=configured,
            label_zh="FFmpeg/ffprobe",
            command_name="ffmpeg",
            hint=hint,
            setup_command=_ffmpeg_install_command(),
        ),
        _missing(
            "render",
            "缺少 FFmpeg/ffprobe",
            hint,
            _ffmpeg_install_command(),
        ),
    ]


def _font_candidates(tool_overrides: dict[str, bool] | None) -> list[CapabilityCandidate]:
    configured = _cjk_font_ok(tool_overrides)
    return [
        CapabilityCandidate(
            id="cjk_font",
            kind="font",
            source_type="local-cli" if configured else "missing",
            configured=configured,
            safe_for_release=configured,
            label_zh="中文字体",
            hint="macOS 默认使用 PingFang；其他系统可放置 NotoSansSC-Regular.otf。",
            setup_command=(
                "mkdir -p ~/.cache/lingjian/fonts && "
                "cp NotoSansSC-Regular.otf ~/.cache/lingjian/fonts/"
            ),
        ),
        _missing(
            "font",
            "缺少中文字体",
            "请安装中文字体,或放置 NotoSansSC-Regular.otf。",
            "mkdir -p ~/.cache/lingjian/fonts && "
            "cp NotoSansSC-Regular.otf ~/.cache/lingjian/fonts/",
        ),
    ]


def _cli_candidate(
    provider_id: str,
    kind: str,
    source_type: str,
    label: str,
    command: str | None,
    lookup: PathLookup,
    configured_hint: str,
    setup_command: str | None = None,
) -> CapabilityCandidate:
    configured = bool(command and lookup(command))
    return CapabilityCandidate(
        id=provider_id,
        kind=kind,
        source_type=source_type,
        configured=configured,
        safe_for_release=configured,
        label_zh=label,
        provider_type="cli",
        command_name=command if command else None,
        config={"command": command or ""},
        hint=configured_hint if configured else f"未检测到 {label}。",
        setup_command=setup_command,
    )


def _api_candidate(
    provider_id: str,
    kind: str,
    label: str,
    configured: bool,
    config: dict[str, Any],
    hint: str,
) -> CapabilityCandidate:
    return CapabilityCandidate(
        id=provider_id,
        kind=kind,
        source_type="api-key",
        configured=configured,
        safe_for_release=configured,
        label_zh=label,
        provider_type="openai_compatible",
        config=config,
        hint=hint,
    )


def _missing(kind: str, label: str, hint: str, setup_command: str) -> CapabilityCandidate:
    return CapabilityCandidate(
        id=f"missing_{kind}",
        kind=kind,
        source_type="missing",
        configured=False,
        safe_for_release=False,
        label_zh=label,
        hint=hint,
        setup_command=setup_command,
    )


def _next_steps(groups: dict[str, CapabilityGroup]) -> list[str]:
    steps: list[str] = []
    for kind in ("llm", "tts", "render", "font"):
        group = groups[kind]
        if group.best.safe_for_release:
            continue
        setup = group.best.setup_command
        hint = group.best.hint or ""
        steps.append(f"{group.best.label_zh}: {hint}" + (f" 命令: {setup}" if setup else ""))
    return steps


def _tool_available(
    name: str,
    lookup: PathLookup,
    overrides: dict[str, bool] | None,
) -> bool:
    if overrides and name in overrides:
        return overrides[name]
    return lookup(name) is not None


def ffmpeg_drawtext_available(
    lookup: PathLookup,
    overrides: dict[str, bool] | None,
) -> bool:
    if overrides and "ffmpeg_drawtext" in overrides:
        return overrides["ffmpeg_drawtext"]
    ffmpeg = lookup("ffmpeg")
    if not ffmpeg:
        return False
    return _ffmpeg_supports_drawtext_help(ffmpeg) or _ffmpeg_filters_include_drawtext(ffmpeg)


def _run_ffmpeg_probe(ffmpeg: str, args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            [ffmpeg, *args],
            text=True,
            capture_output=True,
            check=False,
            timeout=FFMPEG_FILTER_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _ffmpeg_supports_drawtext_help(ffmpeg: str) -> bool:
    completed = _run_ffmpeg_probe(ffmpeg, ["-hide_banner", "-h", "filter=drawtext"])
    if completed is None or completed.returncode != 0:
        return False
    output = f"{completed.stdout}\n{completed.stderr}"
    return "drawtext" in output and "libfreetype" in output


def _ffmpeg_filters_include_drawtext(ffmpeg: str) -> bool:
    completed = _run_ffmpeg_probe(ffmpeg, ["-hide_banner", "-filters"])
    if completed is None or completed.returncode != 0:
        return False
    return "drawtext" in completed.stdout


def _cjk_font_ok(overrides: dict[str, bool] | None) -> bool:
    if overrides and "cjk_font" in overrides:
        return overrides["cjk_font"]
    return any(
        Path(path).exists()
        for path in [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            str(Path.home() / ".cache/lingjian/fonts/NotoSansSC-Regular.otf"),
        ]
    )


def _first_argv(raw: str) -> str:
    if not raw:
        return ""
    try:
        parts = shlex.split(raw)
    except ValueError:
        return ""
    return parts[0] if parts else ""


def _ffmpeg_install_command() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "brew install ffmpeg"
    if system == "windows":
        return "winget install Gyan.FFmpeg"
    return "sudo apt-get update && sudo apt-get install -y ffmpeg"


def _redact_config(config: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in config.items():
        lower = key.lower()
        if lower in {"api_key", "token", "password", "secret", "authorization"}:
            redacted[key] = "***" if value else ""
        elif lower in {"base_url", "model", "command", "value"} and value:
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def _doctor_hint(candidate: CapabilityCandidate) -> str | None:
    if candidate.source_type == "api-key":
        return "可配置 OpenAI-compatible 三件套,或优先使用可继承的 CLI 能力。"
    if candidate.id.startswith("missing_"):
        return "请运行 lj setup 查看最短开通步骤。"
    return candidate.hint
