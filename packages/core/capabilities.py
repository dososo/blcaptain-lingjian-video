from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

PathLookup = Callable[[str], str | None]
FFMPEG_FILTER_TIMEOUT_SEC = 20
HOST_VISUAL_PROBE_TIMEOUT_SEC = 75
LOCAL_TTS_PROBE_TIMEOUT_SEC = 10


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
    quality_tier: str | None = None
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
            "quality_tier": self.quality_tier,
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
        "visuals": _group("visuals", _visual_candidates(env_map, lookup, tool_overrides)),
        "render": _group("render", _render_candidates(lookup, tool_overrides)),
        "font": _group("font", _font_candidates(tool_overrides)),
    }
    next_steps = _next_steps(groups)
    release_ready = []
    sample_or_helper = []
    for group in groups.values():
        candidate = next(
            (
                item
                for item in group.candidates
                if item.source_type in {"inherited-cli", "local-cli", "host-plugin"}
                and item.configured
            ),
            None,
        )
        if candidate is not None:
            if candidate.safe_for_release and candidate.quality_tier not in {"zero_key", "preview"}:
                release_ready.append(candidate.label_zh)
            else:
                sample_or_helper.append(candidate.label_zh)
    if release_ready:
        summary = "已具备发布级能力: " + "、".join(release_ready) + "。"
        if sample_or_helper:
            summary += " 已检测到样片/辅助能力: " + "、".join(sample_or_helper) + "。"
    elif sample_or_helper:
        summary = (
            "已检测到样片/辅助能力: "
            + "、".join(sample_or_helper)
            + ";发布级仍需按缺失项补齐。"
        )
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
                    "safe_for_release": candidate.safe_for_release,
                    "is_mock": False,
                    "probe_ok": candidate.configured,
                    "command": candidate.command_name or "",
                    "config": raw_config,
                    "source_type": candidate.source_type,
                    "quality_tier": candidate.quality_tier,
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
    volcengine_has_api_key = bool(env.get("VOLCENGINE_TTS_API_KEY"))
    volcengine_has_legacy = bool(
        env.get("VOLCENGINE_TTS_APP_ID")
        and env.get("VOLCENGINE_TTS_ACCESS_TOKEN")
        and env.get("VOLCENGINE_TTS_CLUSTER")
    )
    candidates = [
        CapabilityCandidate(
            id="volcengine_tts",
            kind="tts",
            source_type="api-key",
            configured=volcengine_has_api_key or volcengine_has_legacy,
            safe_for_release=volcengine_has_api_key or volcengine_has_legacy,
            label_zh="火山豆包 TTS",
            provider_type="volcengine_tts",
            quality_tier="publish",
            config={
                "api_key": env.get("VOLCENGINE_TTS_API_KEY", ""),
                "resource_id": env.get("VOLCENGINE_TTS_RESOURCE_ID", "seed-tts-2.0"),
                "app_id": env.get("VOLCENGINE_TTS_APP_ID", ""),
                "access_token": env.get("VOLCENGINE_TTS_ACCESS_TOKEN", ""),
                "cluster": env.get("VOLCENGINE_TTS_CLUSTER", ""),
                "voice_type": env.get("VOLCENGINE_TTS_VOICE_TYPE", ""),
            },
            hint="中文发布级配音首选;新版火山豆包 TTS 只需配置 VOLCENGINE_TTS_API_KEY。",
            setup_command="export VOLCENGINE_TTS_API_KEY=...",
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
            quality_tier="publish",
        ),
        _cli_candidate(
            "tts_cli",
            "tts",
            "local-cli",
            "自定义 TTS CLI",
            tts_cli,
            lookup,
            "已检测到 LINGJIAN_TTS_CLI。",
            setup_command='export LINGJIAN_TTS_CLI="/path/to/real-tts"',
            quality_tier="publish",
        ),
        _local_tts_candidate(
            "kokoro_zh_tts",
            "Kokoro 中文本地 TTS",
            "kokoro",
            env.get("LINGJIAN_KOKORO_TTS_READY") == "1",
            lookup,
            "已检测到 Kokoro 中文本地 TTS,零 key 样片可用;发布级请使用用户录音或云 TTS。",
            "uv sync && npx hyperframes tts --list",
            quality_tier="zero_key",
        ),
        _local_tts_candidate(
            "piper_cli",
            "Piper 中文本地 TTS",
            "piper",
            env.get("LINGJIAN_PIPER_TTS_READY") == "1",
            lookup,
            "已检测到 Piper 中文本地 TTS;GPL 组件仅用户自装,灵剪只子进程调用。",
            "pip install piper-tts && python3 -m piper.download_voices zh_CN-huayan-medium",
            quality_tier="zero_key",
        ),
        _cli_candidate(
            "macos_say",
            "tts",
            "local-cli",
            "macOS say",
            "say",
            lookup,
            "已检测到 macOS say，本机零 key TTS 可用。",
            quality_tier="preview",
            release_capable=False,
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
            quality_tier="preview",
            release_capable=False,
        ),
        _missing(
            "tts",
            "缺少真实 TTS",
            "订阅 CLI 通常只覆盖 LLM，不含 TTS；"
            "请优先提供已录好的口播音频;没有录音时配置火山/OpenAI-compatible TTS key。"
            "Kokoro 仅用于零 key 样片试听。",
            "uv run lj run <project> --voice-audio-file narration.m4a",
        ),
    ]
    return candidates


def _ark_key_present(env: Mapping[str, str]) -> bool:
    """火山方舟 ARK key 是否可用(只读传入 env,保持检测可隔离)。

    钥匙串里的 key 由 CLI 启动时 inject_stored_credentials() 注入 env,再被这里读到;
    直接读传入 env 而不查钥匙串,测试传受控 env 时才不会误判。
    """
    return bool((env.get("VOLCENGINE_ARK_API_KEY") or "").strip())


def _visual_candidates(
    env: Mapping[str, str],
    lookup: PathLookup,
    tool_overrides: dict[str, bool] | None,
) -> list[CapabilityCandidate]:
    hyperframes_publish_ready = _visual_env_or_cli_ready(
        env,
        lookup,
        tool_overrides,
        "LINGJIAN_HOST_HYPERFRAMES_PUBLISH_READY",
        "LINGJIAN_HOST_HYPERFRAMES_CLI",
        "host_hyperframes_publish",
        "hyperframes",
    )
    remotion_publish_ready = _visual_env_or_cli_ready(
        env,
        lookup,
        tool_overrides,
        "LINGJIAN_HOST_REMOTION_PUBLISH_READY",
        "LINGJIAN_HOST_REMOTION_CLI",
        "host_remotion_publish",
        "remotion",
    )
    seedance_ready = _ark_key_present(env)
    return [
        CapabilityCandidate(
            id="host_seedance",
            kind="visuals",
            source_type="host-plugin",
            configured=seedance_ready,
            safe_for_release=seedance_ready,
            quality_tier="publish",
            label_zh="Seedance 文生视频(发布级)",
            provider_type="host-plugin",
            command_name="seedance",
            config={"generator": "seedance", "credential": "VOLCENGINE_ARK_API_KEY"},
            hint=(
                "已检测到火山方舟 ARK key,可按分镜用 Seedance 生成发布级真实动态视频。"
                if seedance_ready
                else "未检测到火山方舟 ARK key。"
            ),
            setup_command=(
                "开通火山方舟 Seedance 并配置 ARK key(环境变量 VOLCENGINE_ARK_API_KEY,"
                "或本机钥匙串 lingjian:VOLCENGINE_ARK_API_KEY);"
                "标准动作见 docs/ONBOARDING.md 的 Seedance / ARK 一节。"
            ),
        ),
        _host_visual_candidate(
            "host_hyperframes",
            "HyperFrames director 动态视频",
            "npx",
            "hyperframes",
            env.get("LINGJIAN_HOST_HYPERFRAMES_READY") == "1",
            lookup,
            tool_overrides,
            "已检测到 HyperFrames,可按导演分镜渲染动态视频;发布前仍需通过 strict QA。",
            safe_for_release=hyperframes_publish_ready,
        ),
        _host_visual_candidate(
            "host_remotion",
            "Remotion 宿主程序化视频",
            "remotion",
            "remotion",
            env.get("LINGJIAN_HOST_REMOTION_READY") == "1",
            lookup,
            tool_overrides,
            "已检测到宿主 Remotion 能力,可按镜渲染 React 视频产物。",
            safe_for_release=remotion_publish_ready,
        ),
        CapabilityCandidate(
            id="host_imagegen",
            kind="visuals",
            source_type="host-plugin",
            configured=_visual_env_or_cli_ready(
                env,
                lookup,
                tool_overrides,
                "LINGJIAN_HOST_IMAGEGEN_READY",
                "LINGJIAN_HOST_IMAGEGEN_CLI",
                "host_imagegen",
                "image-gen",
            ),
            safe_for_release=False,
            label_zh="宿主 imagegen 静态参考图",
            provider_type="host-plugin",
            hint=(
                "已检测到宿主 imagegen 时,可生成静态参考图;"
                "发布级必须进一步转成动态视频资产。"
            ),
            setup_command=(
                "在 Codex app 启用 imagegen 能力;安装/启用后新开会话再跑 "
                "uv run lj setup。静态图只能做样片/参考,发布级请提供每镜 mp4/mov/m4v。"
            ),
        ),
        CapabilityCandidate(
            id="fallback_solid",
            kind="visuals",
            source_type="fallback",
            configured=True,
            safe_for_release=False,
            label_zh="回落卡片画面",
            hint=(
                "未检测到可自动继承的宿主画面生成能力;"
                "将消费已有 project/assets/scenes 产物,否则回落纯色卡片并给 QA warning。"
            ),
            setup_command=(
                "优先安装 HyperFrames 零 key 画面能力:"
                "npx skills add heygen-com/hyperframes。"
                "也可在 Codex app 插件市场安装/启用 HyperFrames 或 Remotion;"
                "imagegen 只能做静态参考图;"
                "备用 Remotion 命令为 "
                "npx skills add remotion-dev/skills。HyperFrames 需 Node.js 22+ 与 FFmpeg;"
                "Remotion 商用场景需核对 license。若入口变化,以官方文档和 Codex app 插件市场为准。"
                "安装后新开会话再跑 uv run lj setup。仍缺失时可提供每镜 mp4/mov/m4v。"
            ),
        ),
    ]


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
    quality_tier: str | None = None,
    release_capable: bool = True,
) -> CapabilityCandidate:
    configured = bool(command and lookup(command))
    return CapabilityCandidate(
        id=provider_id,
        kind=kind,
        source_type=source_type,
        configured=configured,
        safe_for_release=configured and release_capable,
        label_zh=label,
        provider_type="cli",
        command_name=command if command else None,
        quality_tier=quality_tier,
        config={"command": command or ""},
        hint=configured_hint if configured else f"未检测到 {label}。",
        setup_command=setup_command,
    )


def _local_tts_candidate(
    provider_id: str,
    label: str,
    command_name: str,
    env_ready: bool,
    lookup: PathLookup,
    ready_hint: str,
    setup_command: str,
    quality_tier: str,
) -> CapabilityCandidate:
    configured = env_ready or _local_tts_probe(provider_id)
    return CapabilityCandidate(
        id=provider_id,
        kind="tts",
        source_type="local-cli",
        configured=configured,
        safe_for_release=configured,
        label_zh=label,
        provider_type=provider_id,
        command_name=command_name if lookup(command_name) else None,
        quality_tier=quality_tier,
        config={"command": command_name if configured else ""},
        hint=ready_hint if configured else f"未检测到 {label}。",
        setup_command=setup_command,
    )


def _host_visual_candidate(
    provider_id: str,
    label: str,
    command: str,
    generator: str,
    env_ready: bool,
    lookup: PathLookup,
    overrides: dict[str, bool] | None,
    ready_hint: str,
    safe_for_release: bool,
) -> CapabilityCandidate:
    override_key = provider_id
    configured = env_ready or safe_for_release or bool(overrides and overrides.get(override_key))
    resolved = lookup(command)
    if not configured and provider_id == "host_hyperframes":
        configured = _npx_hyperframes_available(lookup)
    if not configured and resolved and provider_id != "host_hyperframes":
        configured = _host_visual_cli_probe([resolved], generator)
    return CapabilityCandidate(
        id=provider_id,
        kind="visuals",
        source_type="host-plugin",
        configured=configured,
        safe_for_release=configured and safe_for_release,
        label_zh=label,
        provider_type="host-plugin",
        command_name=command,
        config={"command": command, "env_ready": env_ready},
        hint=ready_hint if configured else f"未检测到 {label}。",
        setup_command=(
            f"在 Codex app 安装/启用 {label} 对应插件或 skill;"
            "安装后新开会话再跑 uv run lj setup。"
        ),
    )


def _visual_env_or_cli_ready(
    env: Mapping[str, str],
    lookup: PathLookup,
    overrides: dict[str, bool] | None,
    ready_env: str,
    cli_env: str,
    override_key: str,
    generator: str,
) -> bool:
    if env.get(ready_env) == "1" or bool(overrides and overrides.get(override_key)):
        return True
    argv = _env_cli_argv(env.get(cli_env, ""), lookup)
    if not argv:
        return False
    return _host_visual_cli_probe(argv, generator)


def _env_cli_argv(raw: str, lookup: PathLookup) -> list[str]:
    if not raw:
        return []
    try:
        argv = shlex.split(raw)
    except ValueError:
        return []
    if not argv:
        return []
    command = argv[0]
    path = Path(command)
    if path.is_absolute() or len(path.parts) > 1:
        return argv if path.exists() else []
    resolved = lookup(command)
    return [resolved, *argv[1:]] if resolved else []


def _api_candidate(
    provider_id: str,
    kind: str,
    label: str,
    configured: bool,
    config: dict[str, Any],
    hint: str,
    quality_tier: str | None = None,
) -> CapabilityCandidate:
    return CapabilityCandidate(
        id=provider_id,
        kind=kind,
        source_type="api-key",
        configured=configured,
        safe_for_release=configured,
        label_zh=label,
        provider_type="openai_compatible",
        quality_tier=quality_tier,
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
    for kind in ("llm", "tts", "visuals", "render", "font"):
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


def _host_visual_cli_probe(argv: list[str], generator: str) -> bool:
    ext = ".png" if generator == "image-gen" else ".mp4"
    with tempfile.TemporaryDirectory() as temp_dir:
        expected = Path(temp_dir) / f"probe{ext}"
        payload = {
            "task": "probe_visual_asset",
            "probe": True,
            "generator": generator,
            "scene_id": "probe",
            "visual_prompt": "探测灵剪宿主画面生成器能否写出资产。",
            "motion_spec": {"main": "probe", "one_main_only": True},
            "brief": {"aspect": "9:16", "safe_zone": "center", "forbidden": "none"},
            "duration_sec": 0.2,
            "expected_asset_path": str(expected),
        }
        try:
            completed = subprocess.run(
                argv,
                input=json.dumps(payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                check=False,
                timeout=HOST_VISUAL_PROBE_TIMEOUT_SEC,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0 and expected.exists() and expected.stat().st_size > 0


def _npx_hyperframes_available(lookup: PathLookup) -> bool:
    npx = lookup("npx")
    if not npx:
        return False
    try:
        completed = subprocess.run(
            [npx, "hyperframes", "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=HOST_VISUAL_PROBE_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and bool((completed.stdout or completed.stderr).strip())


def _local_tts_probe(provider_id: str) -> bool:
    script = _repo_root() / "scripts" / "providers" / f"{provider_id}.py"
    if not script.exists():
        return False
    try:
        completed = subprocess.run(
            [sys.executable, str(script), "--probe"],
            text=True,
            capture_output=True,
            check=False,
            timeout=LOCAL_TTS_PROBE_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


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
        if lower in {
            "api_key",
            "access_token",
            "token",
            "password",
            "secret",
            "authorization",
        }:
            redacted[key] = "***" if value else ""
        elif lower in {"base_url", "model", "command", "value"} and value:
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def _doctor_hint(candidate: CapabilityCandidate) -> str | None:
    if candidate.source_type == "api-key":
        if candidate.id == "volcengine_tts":
            return "可配置新版火山豆包 TTS API Key;旧版四字段仅作为兼容路径。"
        return "可配置 OpenAI-compatible 三件套,或优先使用可继承的 CLI 能力。"
    if candidate.id.startswith("missing_"):
        return "请运行 lj setup 查看最短开通步骤。"
    return candidate.hint
