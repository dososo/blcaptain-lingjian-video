from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from packages.core.capabilities import (
    detect_capabilities,
    ffmpeg_drawtext_available,
    provider_overrides_from_capabilities,
)

ProviderMethodType = Literal[
    "cli",
    "openai_compatible",
    "volcengine_tts",
    "kokoro_zh_tts",
    "piper_cli",
    "anthropic",
    "codex_host",
    "mock",
]


class DoctorItem(BaseModel):
    id: str
    ok: bool
    message_zh: str
    hint: str | None = None


class ProviderMethodStatus(BaseModel):
    id: str
    type: ProviderMethodType
    configured: bool
    is_mock: bool = False
    safe_for_release: bool = False
    source_type: str | None = None
    label_zh: str | None = None
    quality_tier: str | None = None
    config_redacted: dict[str, Any] = Field(default_factory=dict)
    hint: str | None = None
    setup_command: str | None = None


class ProviderGroupStatus(BaseModel):
    ready: bool
    usable_real: bool
    methods: list[ProviderMethodStatus] = Field(default_factory=list)


class DoctorResult(BaseModel):
    ready: bool
    exit_code: int
    required: list[DoctorItem]
    optional: list[DoctorItem]
    providers: dict[str, ProviderGroupStatus]
    capabilities: dict[str, Any] = Field(default_factory=dict)


SECRET_KEYS = {
    "api_key",
    "access_token",
    "token",
    "password",
    "secret",
    "authorization",
    "base_url",
    "model",
    "command",
    "value",
}
SAMPLE_TTS_PROVIDER_IDS = {"kokoro_zh_tts", "piper_cli", "macos_say", "espeak_ng"}
PUBLISH_VISUAL_PROVIDER_IDS = {"host_hyperframes", "host_remotion"}


def _is_publish_tts_method(method: ProviderMethodStatus) -> bool:
    if not method.safe_for_release:
        return False
    if method.quality_tier == "publish":
        return True
    return method.quality_tier is None and method.id not in SAMPLE_TTS_PROVIDER_IDS


def _has_publish_visual_provider(capability_report: Any) -> bool:
    visual_group = capability_report.groups["visuals"]
    for candidate in visual_group.candidates:
        if not candidate.configured or not candidate.safe_for_release:
            continue
        if candidate.id in PUBLISH_VISUAL_PROVIDER_IDS:
            return True
    return False


def _redact_value(value: Any, key_name: str = "") -> Any:
    if isinstance(value, dict):
        return {key: _redact_value(val, key) for key, val in value.items()}
    if key_name.lower() in SECRET_KEYS:
        return "***" if value else ""
    if isinstance(value, str) and value:
        if "secret" in value.lower() or value.startswith(("sk-", "ak-", "pk-")):
            return value[:3] + "***"
    return value


def _tool_ok(name: str, overrides: dict[str, bool] | None) -> bool:
    if overrides and name in overrides:
        return overrides[name]
    if name == "ffmpeg_drawtext":
        return ffmpeg_drawtext_available(shutil.which, overrides)
    if name == "cjk_font":
        return any(
            Path(path).exists()
            for path in [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
                str(Path.home() / ".cache/lingjian/fonts/NotoSansSC-Regular.otf"),
            ]
        )
    return shutil.which(name) is not None


def _method_status(raw: dict[str, Any]) -> ProviderMethodStatus:
    method_type = raw.get("type", "mock")
    configured = bool(raw.get("configured"))
    is_mock = bool(raw.get("is_mock", method_type == "mock"))
    config = raw.get("config", {})
    declared_safe = raw.get("safe_for_release")
    if method_type == "cli":
        command = raw.get("command")
        probe_ok = bool(raw.get("probe_ok")) or bool(command and shutil.which(command))
        safe_for_release = configured and probe_ok and not is_mock
    elif method_type == "openai_compatible":
        safe_for_release = (
            configured
            and not is_mock
            and bool(config.get("api_key"))
            and bool(config.get("base_url"))
            and bool(config.get("model"))
        )
    elif method_type == "volcengine_tts":
        has_api_key = bool(config.get("api_key"))
        has_legacy_config = bool(
            config.get("app_id") and config.get("access_token") and config.get("cluster")
        )
        safe_for_release = (
            configured
            and not is_mock
            and (has_api_key or has_legacy_config)
        )
    else:
        safe_for_release = configured and not is_mock and method_type not in {"codex_host", "mock"}
    if declared_safe is False:
        safe_for_release = False
    return ProviderMethodStatus(
        id=raw["id"],
        type=method_type,
        configured=configured,
        is_mock=is_mock,
        safe_for_release=safe_for_release,
        source_type=raw.get("source_type"),
        label_zh=raw.get("label_zh"),
        quality_tier=raw.get("quality_tier"),
        config_redacted=_redact_value(raw.get("config", {})),
        hint=raw.get("hint"),
        setup_command=raw.get("setup_command"),
    )


def _provider_group(kind: str, methods: list[dict[str, Any]]) -> ProviderGroupStatus:
    statuses = [_method_status(method) for method in methods]
    usable_real = any(method.safe_for_release for method in statuses)
    return ProviderGroupStatus(ready=usable_real, usable_real=usable_real, methods=statuses)


def _doctor_capabilities(capability_report: Any | None) -> dict[str, Any]:
    if capability_report is None:
        return {}
    return {
        kind: {
            "id": group.best.id,
            "source_type": group.best.source_type,
            "configured": group.best.configured,
            "safe_for_release": group.best.safe_for_release,
            "label_zh": group.best.label_zh,
            "command_name": group.best.command_name,
            "quality_tier": group.best.quality_tier,
            "hint": group.best.hint,
            "setup_command": group.best.setup_command,
            "candidates": [candidate.public_dict() for candidate in group.candidates],
        }
        for kind, group in capability_report.groups.items()
    }


def _default_provider_overrides() -> dict[str, list[dict[str, Any]]]:
    report = detect_capabilities()
    return provider_overrides_from_capabilities(report)


def _whisper_precise_align_available(overrides: dict[str, bool] | None = None) -> bool:
    """faster-whisper 是否可用于逐字对齐(WORKFLOW§114:与 FFmpeg 同级必备,环境预检必测)。"""
    if overrides is not None and "whisper" in overrides:
        return bool(overrides["whisper"])
    import importlib.util

    return importlib.util.find_spec("faster_whisper") is not None


def run_doctor(
    tool_overrides: dict[str, bool] | None = None,
    provider_overrides: dict[str, list[dict[str, Any]]] | None = None,
) -> DoctorResult:
    required: list[DoctorItem] = []
    optional: list[DoctorItem] = []
    capability_report = (
        detect_capabilities(tool_overrides=tool_overrides)
        if provider_overrides is None
        else None
    )

    for tool, label in {
        "ffmpeg": "FFmpeg",
        "ffprobe": "ffprobe",
        "cjk_font": "中文字体",
    }.items():
        if not _tool_ok(tool, tool_overrides):
            required.append(
                DoctorItem(
                    id=tool,
                    ok=False,
                    message_zh=f"缺少必需能力:{label}",
                    hint=f"请安装或配置 {label} 后重试。",
                )
            )
    if (
        _tool_ok("ffmpeg", tool_overrides)
        and _tool_ok("ffprobe", tool_overrides)
        and not _tool_ok("ffmpeg_drawtext", tool_overrides)
    ):
        required.append(
            DoctorItem(
                id="ffmpeg_drawtext",
                ok=False,
                message_zh="当前 FFmpeg 缺少 drawtext/libfreetype 滤镜。",
                hint=(
                    "请安装带 freetype 的 FFmpeg,并用 "
                    "`ffmpeg -hide_banner -h filter=drawtext` 或 "
                    "`ffmpeg -filters | grep drawtext` 验证。"
                ),
            )
        )

    providers_raw = (
        provider_overrides
        if provider_overrides is not None
        else provider_overrides_from_capabilities(capability_report or detect_capabilities())
    )
    providers = {
        "llm": _provider_group("llm", providers_raw.get("llm", [])),
        "tts": _provider_group("tts", providers_raw.get("tts", [])),
    }
    if not providers["llm"].usable_real:
        required.append(
            DoctorItem(
                id="real_llm_provider",
                ok=False,
                message_zh="缺少可用于正式发布的真实 LLM provider。",
                hint="可配置 CLI provider,或提供 OpenAI-compatible/Anthropic 三件套。",
            )
        )
    if not providers["tts"].usable_real:
        required.append(
            DoctorItem(
                id="real_tts_provider",
                ok=False,
                message_zh="缺少可用于正式发布的真实 TTS provider。",
                hint=(
                    "可提供录好的口播音频,或配置新版火山豆包 TTS API Key/"
                    "OpenAI-compatible TTS。mock 只能预览,不能 release。"
                ),
            )
        )
    elif not any(_is_publish_tts_method(method) for method in providers["tts"].methods):
        required.append(
            DoctorItem(
                id="publish_tts_provider",
                ok=False,
                message_zh=(
                    "当前只检测到本地样片级 TTS;发布档需要用户录音或自然中文云 TTS。"
                ),
                hint="请提供 --voice-audio-file,或配置火山豆包/OpenAI-compatible TTS。",
            )
        )
    if capability_report is not None:
        if not _has_publish_visual_provider(capability_report):
            required.append(
                DoctorItem(
                    id="publish_visual_provider",
                    ok=False,
                    message_zh=(
                        "当前画面能力只能生成回落卡片、静态参考图或内置样片模板;"
                        "发布档需要真实动态视频素材或真正的视频生成插件。"
                    ),
                    hint=(
                        "请提供每镜 mp4/mov/m4v,或在 Codex app 启用可生成内容相关"
                        "动态视频资产的 HyperFrames/Remotion/视频生成插件。"
                    ),
                )
            )

    optional.append(
        DoctorItem(
            id="host_visual_delegation_notice",
            ok=True,
            message_zh=(
                "HyperFrames/Remotion/imagegen 为宿主委托能力;"
                "灵剪不默认、不捆绑、不 import 相关 SDK。"
            ),
        )
    )
    whisper_ok = _whisper_precise_align_available(tool_overrides)
    optional.append(
        DoctorItem(
            id="whisper_precise_alignment",
            ok=whisper_ok,
            message_zh=(
                "faster-whisper 已就位:配音走逐字识别 → 精确切分 → 字幕/画面逐句对齐。"
                if whisper_ok
                else (
                    "未检测到 faster-whisper:字幕/卡点会退回按字数粗估,长文本易逐句错位。"
                    "发布级精确对齐建议安装。"
                )
            ),
            hint=(
                None
                if whisper_ok
                else "安装:`pip install faster-whisper`(与 FFmpeg 同级必备,见 WORKFLOW 精确对齐)。"
            ),
        )
    )
    ready = not required
    return DoctorResult(
        ready=ready,
        exit_code=0 if ready else 1,
        required=required,
        optional=optional,
        providers=providers,
        capabilities=_doctor_capabilities(capability_report),
    )
