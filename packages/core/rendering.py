from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from engines.ffmpeg_card.text_layout import break_cjk_text
from packages.core.approvals import validate_render_gate
from packages.core.artifacts import read_json
from packages.core.errors import LingjianError
from packages.core.evidence_assets import (
    ASSET_RECIPE_EVIDENCE_TYPES,
    EVIDENCE_MATERIALIZATION_PROFILES,
    SOURCE_VIDEO_EVIDENCE_TYPES,
    load_evidence_assets,
)
from packages.core.hash import canonical_json_hash
from packages.core.paths import resolve_inside, safe_segment
from packages.core.project import ProjectRef
from packages.core.visual_generation import ensure_scene_asset

RenderMode = Literal["preview", "release"]
STUB_VIDEO_BYTES = b"LINGJIAN_STUB_MP4"
FFMPEG_TIMEOUT_SEC = 60
FPS = 30
CAPTION_DEFAULT_MAX_CHARS_PER_LINE = 12
CAPTION_MAX_LINES = 1
CAPTION_ESTIMATED_MAX_CHARS_PER_CUE = 12
CAPTION_ESTIMATED_MAX_CUE_SEC = 1.8
CAPTION_MIN_CUE_SEC = 0.45
CAPTION_MAX_CUE_SEC = 2.2
CAPTION_GAP_SEC = 0.03
CAPTION_SAFE_START_RATIO = 0.72
CAPTION_SAFE_END_RATIO = 0.92
CAPTION_RAIL_CENTER_RATIO = 0.87
CAPTION_RAIL_WIDTH_RATIO = 0.78
CAPTION_RAIL_HEIGHT_RATIO = 0.10
CAPTION_TRANSITION_GUARD_SEC = 0.03
CAPTION_MIN_RENDERED_CUE_SEC = 0.18
CAPTION_TARGET_READING_UNITS_PER_SEC = 11.4
TRANSITION_DEFAULT_SEC = 0.35
TRANSITION_MIN_SEC = 0.08
DEFAULT_BGM_TO_VOICE_DB = -16.0
DEFAULT_SFX_GAIN_DB = -12.0
RELEASE_LOUDNORM_FILTER = "loudnorm=I=-14:LRA=11:TP=-1.0"
SCENE_VIDEO_DURATION_TOLERANCE_SEC = 0.25
EVIDENCE_RECORDING_MIN_DURATION_SEC = 1.5
EVIDENCE_RECORDING_MIN_SCENE_RATIO = 0.5
AUDIO_ACTION_MARKER_FIELDS = (
    "id",
    "cue_id",
    "event_id",
    "visual_event",
    "action",
    "purpose",
    "label",
    "name",
)
AUDIO_ACTION_MARKER_CONTAINERS = (
    "visual_events",
    "keyframes",
    "motion_beats",
    "animation_beats",
    "action_markers",
    "sfx_points",
    "sound_cues",
)
RECORDING_EVIDENCE_VISUAL_SOURCES = {
    "codex_operation_video",
    "screen_recording",
    "screen_recording_video",
    "terminal_recording",
    "terminal_recording_video",
    "web_recording",
    "web_recording_video",
}
RECORDING_EVIDENCE_KEYWORDS = (
    "codex",
    "github",
    "qa",
    "readme",
    "render_manifest",
    "terminal",
    "web",
    "仓库",
    "测试",
    "导出",
    "录屏",
    "命令",
    "屏幕",
    "操作",
    "终端",
    "验证",
)
RECORDING_EVIDENCE_EXPECTED_TYPE_GROUPS = (
    (
        ("codex",),
        {"codex_operation_recording", "screen_recording_capture"},
    ),
    (
        ("terminal", "终端", "命令"),
        {"terminal_recording_capture", "screen_recording_capture"},
    ),
    (
        ("github", "readme", "web", "仓库", "网页", "文档"),
        {"web_recording_capture", "screen_recording_capture"},
    ),
    (
        ("qa", "测试", "验证"),
        {
            "terminal_recording_capture",
            "codex_operation_recording",
            "screen_recording_capture",
        },
    ),
    (
        ("export", "render_manifest", "导出"),
        {
            "terminal_recording_capture",
            "codex_operation_recording",
            "screen_recording_capture",
        },
    ),
)
RECORDING_INTENT_MARKER_GROUPS_BY_SCENE_KEY = {
    "codex_prompt_or_reconstructed_ui": (
        ("codex", "灵剪", "lingjian", "lingjian-video"),
        ("触发", "一句话", "prompt", "对话", "输入"),
    ),
    "codex_operation_capture": (
        ("codex",),
        ("三审", "脚本", "配音", "画面", "能力", "流程", "操作", "点击"),
    ),
    "codex_prompt_capture": (
        ("codex", "灵剪", "lingjian", "lingjian-video"),
        ("触发", "一句话", "prompt", "对话", "输入"),
    ),
    "hook_codex_prompt": (
        ("codex", "灵剪", "lingjian", "lingjian-video"),
        ("触发", "一句话", "prompt", "对话", "输入"),
    ),
    "solution_cursor_demo": (
        ("codex",),
        ("三审", "脚本", "配音", "画面", "能力", "流程", "操作", "点击"),
    ),
    "visual_asset_generation_queue": (
        ("资产", "素材", "生成", "队列", "宿主", "插件", "hyperframes", "remotion"),
    ),
    "solution_asset_pipeline": (
        ("资产", "素材", "生成", "队列", "宿主", "插件", "hyperframes", "remotion"),
    ),
    "product_interface_capture": (
        ("产品", "商品", "product"),
        ("界面", "ui", "操作", "流程", "工作流", "演示", "demo"),
    ),
    "product_ui_capture": (
        ("产品", "商品", "product"),
        ("界面", "ui", "操作", "流程", "工作流", "演示", "demo"),
    ),
    "product_demo_capture": (
        ("产品", "商品", "product"),
        ("界面", "ui", "操作", "流程", "工作流", "演示", "demo"),
    ),
    "tutorial_step_capture": (
        ("教程", "教学", "步骤", "tutorial", "guide", "step"),
        ("操作", "流程", "页面", "命令", "演示", "结果"),
    ),
    "review_comparison_capture": (
        ("评测", "测评", "对比", "review", "comparison", "测试"),
        ("结果", "数据", "表现", "对比", "演示", "界面"),
    ),
    "ecommerce_product_capture": (
        ("商品", "产品", "电商", "带货"),
        ("实拍", "展示", "详情", "页面", "下单", "购买", "演示"),
    ),
}
RECORDING_INTENT_EXPECTED_GROUPS = (
    (("codex",), (("codex",),)),
    (
        ("资产", "素材", "生成队列", "asset queue", "asset generation"),
        (("资产", "素材", "生成", "队列", "宿主", "插件", "hyperframes", "remotion"),),
    ),
    (
        (
            "产品界面",
            "产品ui",
            "产品 ui",
            "product ui",
            "product interface",
            "核心工作流",
            "产品操作",
            "操作流程",
        ),
        (
            ("产品", "商品", "product"),
            ("界面", "ui", "操作", "流程", "工作流", "演示", "demo"),
        ),
    ),
    (
        ("教程", "教学", "步骤", "操作步骤", "tutorial", "guide", "step"),
        (
            ("教程", "教学", "步骤", "tutorial", "guide", "step"),
            ("操作", "流程", "页面", "命令", "演示", "结果"),
        ),
    ),
    (
        ("评测", "测评", "对比", "测试结果", "review", "comparison"),
        (
            ("评测", "测评", "对比", "review", "comparison", "测试"),
            ("结果", "数据", "表现", "对比", "演示", "界面"),
        ),
    ),
    (
        ("商品", "电商", "带货", "下单", "购买", "权益", "价格"),
        (
            ("商品", "产品", "电商", "带货"),
            ("实拍", "展示", "详情", "页面", "下单", "购买", "演示"),
        ),
    ),
)
AUDIO_ACTION_MARKER_GROUPS = (
    "director_review_sheet_v2",
    "director_review_sheet",
    "director_board",
    "motion_intent",
    "motion_spec",
)

XFADE_TRANSITIONS = (
    "fade",
    "wipeleft",
    "wiperight",
    "wipeup",
    "wipedown",
    "slideleft",
    "slideright",
    "slideup",
    "slidedown",
    "smoothleft",
    "smoothright",
    "smoothup",
    "smoothdown",
    "circleopen",
    "circleclose",
    "distance",
    "radial",
    "dissolve",
    "pixelize",
)
XFADE_FAMILY_MAP = {
    "hook": "fade",
    "pain": "wipeleft",
    "solution": "slideright",
    "proof": "wipeup",
    "cta": "circleclose",
    "ticker-crash": "pixelize",
    "zoom-through": "distance",
    "grid-dissolve": "dissolve",
    "glitch-pressure": "pixelize",
    "focus-pull": "radial",
    "push-squeeze": "smoothleft",
    "card-morph": "rectcrop",
    "clean-wipe": "wipeleft",
    "grid-align": "smoothright",
    "scan-focus": "smoothup",
    "terminal-scan": "wipeup",
    "timeline-push": "slideup",
    "cta-morph": "circleclose",
    "button-press": "circleopen",
    "logo-lockup": "fade",
    "push-slide": "slideright",
    "same-transition": "fade",
}


@dataclass(slots=True)
class RenderResult:
    mode: RenderMode
    video_path: Path
    manifest_path: Path


def _used_providers(project: ProjectRef) -> list[dict]:
    providers: list[dict] = []
    script_path = project.path / "artifacts" / "script.json"
    voice_path = project.path / "artifacts" / "voice_plan.json"
    if script_path.exists():
        script = read_json(script_path)
        providers.append(
            {
                "id": script.get("provider_id", "unknown"),
                "kind": "llm",
                "is_mock": bool(script.get("provider_is_mock")),
            }
        )
    if voice_path.exists():
        voice = read_json(voice_path)
        providers.append(
            {
                "id": voice.get("provider_id", "unknown"),
                "kind": "tts",
                "is_mock": bool(voice.get("provider_is_mock")),
            }
        )
    visual_path = project.path / "artifacts" / "visual_plan.json"
    renderer_id = "ffmpeg_card"
    if visual_path.exists():
        visual_plan = read_json(visual_path)
        generators = {
            str(scene.get("generator", "fallback_solid"))
            for scene in visual_plan.get("scenes", [])
            if isinstance(scene, dict)
        }
        if generators:
            renderer_id = "delegated_scene_assembly"
    providers.append({"id": renderer_id, "kind": "renderer", "is_mock": False})
    return providers


def _release_text(project: ProjectRef) -> str:
    script_path = project.path / "artifacts" / "script.json"
    if not script_path.exists():
        return "灵剪"
    script = read_json(script_path)
    text = " ".join(
        str(scene.get("narration_text", ""))
        for scene in script.get("scenes", [])
        if isinstance(scene, dict)
    ).strip()
    return text or "灵剪"


def _release_duration(project: ProjectRef) -> float:
    voice_path = project.path / "artifacts" / "voice_plan.json"
    if not voice_path.exists():
        return 3.0
    voice = read_json(voice_path)
    return max(float(voice.get("total_duration_sec") or 3.0), 1.0)


def _voice_segments(project: ProjectRef) -> dict[str, dict[str, Any]]:
    voice_path = project.path / "artifacts" / "voice_plan.json"
    if not voice_path.exists():
        return {}
    voice = read_json(voice_path)
    segments: dict[str, dict[str, Any]] = {}
    for index, segment in enumerate(voice.get("segments", []), start=1):
        if not isinstance(segment, dict):
            continue
        scene_id = str(segment.get("scene_id") or f"s{index}")
        segments[scene_id] = segment
    return segments


def _voice_plan(project: ProjectRef) -> dict[str, Any]:
    voice_path = project.path / "artifacts" / "voice_plan.json"
    if not voice_path.exists():
        return {}
    return read_json(voice_path)


def _audio_asset_path(project: ProjectRef, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    try:
        resolved = resolve_inside(project.path, project.path / raw_path)
    except LingjianError:
        return None
    if not resolved.exists() or not _audio_asset_has_audio_stream(resolved):
        return None
    return resolved


def _audio_asset_has_audio_stream(path: Path) -> bool:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return False
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "json",
                str(path),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in payload.get("streams", [])
    )


def _audio_assets(project: ProjectRef) -> dict[str, Any]:
    voice = _voice_plan(project)
    assets = voice.get("audio_assets")
    return assets if isinstance(assets, dict) else {}


def _voice_scene_start_offsets(project: ProjectRef) -> dict[str, float]:
    voice = _voice_plan(project)
    offsets: dict[str, float] = {}
    cursor = 0.0
    segments = voice.get("segments")
    if not isinstance(segments, list):
        return offsets
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            continue
        scene_id = str(segment.get("scene_id") or f"s{index}")
        offsets.setdefault(scene_id, cursor)
        duration = _float_time(segment.get("duration_sec"))
        if duration is not None:
            cursor += max(duration, 0.0)
    return offsets


def _scene_identifier(scene: dict[str, Any], index: int) -> str:
    return str(scene.get("scene_id") or scene.get("id") or f"s{index}")


def _scene_review_sheets(scene: dict[str, Any]) -> list[dict[str, Any]]:
    sheets: list[dict[str, Any]] = []
    for key in ("director_review_sheet_v2", "director_review_sheet", "director_board"):
        value = scene.get(key)
        if isinstance(value, dict):
            sheets.append(value)
    return sheets


def _bgm_texts(scene: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for key in ("bgm", "bgm_strategy", "music", "music_strategy"):
        value = scene.get(key)
        if value:
            texts.append(str(value))
    audio_notes = scene.get("audio_sfx_notes")
    if isinstance(audio_notes, dict) and audio_notes.get("bgm"):
        texts.append(str(audio_notes["bgm"]))
    for sheet in _scene_review_sheets(scene):
        for key in ("bgm", "bgm_strategy", "music", "music_strategy"):
            value = sheet.get(key)
            if value:
                texts.append(str(value))
        notes = sheet.get("audio_sfx_notes")
        if isinstance(notes, dict) and notes.get("bgm"):
            texts.append(str(notes["bgm"]))
    return texts


def _normalize_audio_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _bgm_text_requires_render(text: str) -> bool:
    normalized = _normalize_audio_text(text)
    if not normalized:
        return False
    no_bgm_terms = (
        "无 bgm",
        "无bgm",
        "无背景音乐",
        "无配乐",
        "不需要bgm",
        "不需要 bgm",
        "无需bgm",
        "无需 bgm",
        "可无",
        "或无",
        "none",
        "n/a",
        "not needed",
    )
    if any(term in normalized for term in no_bgm_terms):
        return False
    return "bgm" in normalized or "音乐" in normalized or "配乐" in normalized


def _collect_audio_action_markers(markers: set[str], value: object) -> None:
    if isinstance(value, dict):
        for key in AUDIO_ACTION_MARKER_FIELDS:
            _add_audio_action_marker(markers, value.get(key))
        for key in AUDIO_ACTION_MARKER_CONTAINERS:
            _collect_audio_action_markers(markers, value.get(key))
        notes = value.get("audio_sfx_notes")
        if isinstance(notes, dict):
            _collect_audio_action_markers(markers, notes.get("sfx"))
            _collect_audio_action_markers(markers, notes.get("sfx_points"))
            _collect_audio_action_markers(markers, notes.get("sound_cues"))
        return
    if isinstance(value, list):
        for item in value:
            _collect_audio_action_markers(markers, item)
        return
    _add_audio_action_marker(markers, value)


def _add_audio_action_marker(markers: set[str], value: object) -> None:
    marker = _normalize_audio_text(value)
    if marker:
        markers.add(marker)


def _sfx_marker_requires_render(marker: str) -> bool:
    normalized = _normalize_audio_text(marker)
    if not normalized:
        return False
    exact_no_sfx_terms = {
        "无",
        "不需要",
        "无需",
        "未声明",
        "none",
        "n/a",
        "na",
        "not needed",
    }
    if normalized in exact_no_sfx_terms:
        return False
    no_sfx_terms = (
        "无音效",
        "无特殊音效",
        "不需要音效",
        "无需音效",
        "可无音效",
        "音效可无",
        "或无音效",
        "不加音效",
        "可不加音效",
        "或不加音效",
        "不要音效",
        "避免音效",
        "不做音效",
        "no sfx",
        "no sound effect",
        "without sfx",
        "optional sfx",
    )
    return not any(term in normalized for term in no_sfx_terms)


def _sfx_markers(scene: dict[str, Any]) -> list[str]:
    markers: set[str] = set()
    for key in AUDIO_ACTION_MARKER_CONTAINERS:
        _collect_audio_action_markers(markers, scene.get(key))
    for key in AUDIO_ACTION_MARKER_GROUPS:
        group = scene.get(key)
        if isinstance(group, dict):
            for container in AUDIO_ACTION_MARKER_CONTAINERS:
                _collect_audio_action_markers(markers, group.get(container))
            notes = group.get("audio_sfx_notes")
            if isinstance(notes, dict):
                _collect_audio_action_markers(markers, notes.get("sfx"))
                _collect_audio_action_markers(markers, notes.get("sfx_points"))
                _collect_audio_action_markers(markers, notes.get("sound_cues"))
    return sorted(marker for marker in markers if _sfx_marker_requires_render(marker))


def _declared_audio_requirements(scenes: list[dict[str, Any]]) -> dict[str, Any] | None:
    bgm_scenes: list[dict[str, Any]] = []
    sfx_scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        scene_id = _scene_identifier(scene, index)
        bgm_texts = [text for text in _bgm_texts(scene) if _bgm_text_requires_render(text)]
        if bgm_texts:
            bgm_scenes.append({"scene_id": scene_id, "texts": bgm_texts})
        markers = _sfx_markers(scene)
        if markers:
            sfx_scenes.append({"scene_id": scene_id, "markers": markers})
    if not bgm_scenes and not sfx_scenes:
        return None
    return {
        "bgm_required": bool(bgm_scenes),
        "bgm_scene_ids": [item["scene_id"] for item in bgm_scenes],
        "bgm_texts_by_scene": bgm_scenes,
        "sfx_required": bool(sfx_scenes),
        "sfx_scene_ids": [item["scene_id"] for item in sfx_scenes],
        "sfx_markers_by_scene": sfx_scenes,
    }


def _audio_mix_with_declared_requirements(
    audio_mix: dict[str, Any],
    scenes: list[dict[str, Any]],
) -> dict[str, Any]:
    declared = _declared_audio_requirements(scenes)
    if not declared:
        return audio_mix
    return {**audio_mix, "declared_audio_requirements": declared}


def _audio_asset_manifest_ref(raw_path: Any) -> str | None:
    if not isinstance(raw_path, str):
        return None
    value = raw_path.strip()
    if not value:
        return None
    path = Path(value)
    if path.is_absolute() or "://" in value:
        return "<external-redacted>"
    if ".." in path.parts:
        return "<outside-redacted>"
    return value


def _invalid_audio_asset_refs(project: ProjectRef, assets: dict[str, Any]) -> list[dict[str, Any]]:
    invalid: list[dict[str, Any]] = []
    bgm = assets.get("bgm")
    if isinstance(bgm, dict):
        raw_path = bgm.get("path")
        manifest_ref = _audio_asset_manifest_ref(raw_path)
        if manifest_ref is not None and _audio_asset_path(project, raw_path) is None:
            invalid.append(
                {
                    "kind": "bgm",
                    "path": manifest_ref,
                    "reason": "missing_or_unverifiable",
                }
            )
    raw_events = assets.get("sfx")
    if isinstance(raw_events, list):
        for raw_event in raw_events:
            if not isinstance(raw_event, dict):
                continue
            raw_path = raw_event.get("path")
            manifest_ref = _audio_asset_manifest_ref(raw_path)
            if manifest_ref is None or _audio_asset_path(project, raw_path) is not None:
                continue
            invalid.append(
                {
                    "kind": "sfx",
                    "path": manifest_ref,
                    "scene_id": raw_event.get("scene_id"),
                    "action": raw_event.get("action"),
                    "reason": "missing_or_unverifiable",
                }
            )
    return invalid


def _audio_mix_manifest(
    project: ProjectRef, rendered: bool = False, mixed_audio_path: Path | None = None
) -> dict[str, Any]:
    voice = _voice_plan(project)
    provider_id = str(voice.get("provider_id") or "unknown")
    mixed_audio_relative = (
        str(mixed_audio_path.relative_to(project.path)) if mixed_audio_path else None
    )
    mix = voice.get("audio_mix")
    assets = _audio_assets(project)
    invalid_audio_assets = _invalid_audio_asset_refs(project, assets)
    if isinstance(mix, dict):
        mapped = {
            "voice_provider_id": provider_id,
            "rendered": rendered,
            **mix,
            "mixed_audio_path": mixed_audio_relative or mix.get("mixed_audio_path"),
        }
        if invalid_audio_assets and "invalid_audio_assets" not in mapped:
            mapped["invalid_audio_assets"] = invalid_audio_assets
            mapped["invalid_audio_asset_count"] = len(invalid_audio_assets)
        elif "invalid_audio_assets" in mapped and "invalid_audio_asset_count" not in mapped:
            existing_invalid = mapped.get("invalid_audio_assets")
            if isinstance(existing_invalid, list):
                mapped["invalid_audio_asset_count"] = len(existing_invalid)
        return mapped
    bgm = assets.get("bgm")
    bgm_path = None
    bgm_to_voice_db = DEFAULT_BGM_TO_VOICE_DB
    if isinstance(bgm, dict):
        bgm_path = _audio_asset_path(project, bgm.get("path"))
        bgm_to_voice_db = float(bgm.get("bgm_to_voice_db") or DEFAULT_BGM_TO_VOICE_DB)
    sfx_events = _normalized_sfx_events(project, assets)
    return {
        "voice_provider_id": provider_id,
        "rendered": rendered,
        "mixed_audio_path": mixed_audio_relative,
        "bgm_present": bgm_path is not None,
        "bgm_path": str(bgm_path.relative_to(project.path)) if bgm_path else None,
        "bgm_to_voice_db": bgm_to_voice_db if bgm_path else None,
        "sfx_count": len(sfx_events),
        "sfx_density_per_10_sec": _sfx_density(project, sfx_events),
        "sfx_events": [
            {
                key: value
                for key, value in {
                    "path": str(event["path"].relative_to(project.path)),
                    "at_sec": event["at_sec"],
                    "gain_db": event["gain_db"],
                    "scene_id": event.get("scene_id"),
                    "action": event.get("action"),
                    "purpose": event.get("purpose"),
                    "visual_event": event.get("visual_event"),
                    "cue_id": event.get("cue_id"),
                    "time_basis": event.get("time_basis"),
                    "local_at_sec": event.get("local_at_sec"),
                }.items()
                if value not in (None, "")
            }
            for event in sfx_events
        ],
        "invalid_audio_asset_count": len(invalid_audio_assets),
        "invalid_audio_assets": invalid_audio_assets,
        "policy": "BGM 默认低于人声 16dB,SFX 只提示动作且不得过密。",
    }


def _release_audio_path(project: ProjectRef) -> Path:
    voice = _voice_plan(project)
    if not voice:
        raise LingjianError(
            "RELEASE_AUDIO_MISSING",
            "release 渲染缺少语音产物。",
            "请先使用真实 TTS provider 生成并审批 voice。",
        )
    full_audio_path = voice.get("full_audio_path")
    if isinstance(full_audio_path, str) and full_audio_path:
        resolved_full_audio = _audio_asset_path(project, full_audio_path)
        if resolved_full_audio is not None:
            return resolved_full_audio
    for segment in voice.get("segments", []):
        if not isinstance(segment, dict):
            continue
        audio_path = segment.get("audio_path")
        if not isinstance(audio_path, str) or not audio_path:
            continue
        resolved = _audio_asset_path(project, audio_path)
        if resolved is not None:
            return resolved
    raise LingjianError(
        "RELEASE_AUDIO_MISSING",
        "release 渲染缺少可验证口播音频文件。",
        "请重新生成包含 audio stream 的真实 voice 产物后再 release render。",
    )


def _make_silent_base_track(project: ProjectRef, render_dir: Path, duration: float) -> Path:
    """无旁白模式:生成时长 = duration 的静音基轨(anullsrc),供 BGM/SFX 混在其上;
    无 BGM/SFX 时即纯静音音轨(片子靠画面 + 文字卡叙事)。"""
    output = render_dir / "silent_base.wav"
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo",
        "-t",
        f"{max(float(duration), 0.5):.3f}",
        str(output),
    ]
    _run_ffmpeg(project, command, output)
    return output


def _normalized_sfx_events(project: ProjectRef, assets: dict[str, Any]) -> list[dict[str, Any]]:
    raw_events = assets.get("sfx")
    if not isinstance(raw_events, list):
        return []
    scene_start_offsets = _voice_scene_start_offsets(project)
    events: list[dict[str, Any]] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            continue
        path = _audio_asset_path(project, raw_event.get("path"))
        if path is None:
            continue
        scene_id = raw_event.get("scene_id")
        local_at_sec = None
        time_basis = str(raw_event.get("time_basis") or "").strip()
        try:
            at_sec = max(float(raw_event.get("at_sec") or 0), 0.0)
        except (TypeError, ValueError):
            at_sec = 0.0
        if time_basis == "scene_local":
            try:
                local_at_sec = max(
                    float(raw_event.get("local_at_sec", raw_event.get("at_sec", 0)) or 0),
                    0.0,
                )
            except (TypeError, ValueError):
                local_at_sec = 0.0
            at_sec = scene_start_offsets.get(str(scene_id or ""), 0.0) + local_at_sec
        try:
            gain_db = float(raw_event.get("gain_db") or DEFAULT_SFX_GAIN_DB)
        except (TypeError, ValueError):
            gain_db = DEFAULT_SFX_GAIN_DB
        event = {
            "path": path,
            "at_sec": round(at_sec, 3),
            "gain_db": gain_db,
            "scene_id": scene_id,
            "action": raw_event.get("action"),
            "purpose": raw_event.get("purpose"),
            "visual_event": raw_event.get("visual_event"),
            "cue_id": raw_event.get("cue_id"),
        }
        if time_basis:
            event["time_basis"] = time_basis
        if local_at_sec is not None:
            event["local_at_sec"] = round(local_at_sec, 3)
        events.append(event)
    return events


def _sfx_density(project: ProjectRef, events: list[dict[str, Any]]) -> float:
    if not events:
        return 0.0
    duration = max(_release_duration(project), 1.0)
    return round(len(events) / duration * 10.0, 3)


def _normalize_release_audio(project: ProjectRef, source_path: Path, output_path: Path) -> Path:
    _run_ffmpeg(
        project,
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-af",
            RELEASE_LOUDNORM_FILTER,
            "-c:a",
            "aac",
            str(output_path),
        ],
        output_path,
    )
    return output_path


def _audio_normalization_manifest(output_path: Path | None) -> dict[str, Any]:
    return {
        "audio_normalization": {
            "rendered": output_path is not None,
            "filter": RELEASE_LOUDNORM_FILTER,
            "target_lufs": -14,
            "target_lra": 11,
            "target_true_peak_db": -1.0,  # 必须与 RELEASE_LOUDNORM_FILTER 的 TP 一致(测试锁死)
        }
    }


def _render_release_audio(project: ProjectRef, render_dir: Path) -> tuple[Path, dict[str, Any]]:
    voice = _voice_plan(project)
    voiceless = isinstance(voice, dict) and voice.get("voiceover") is False
    if voiceless:
        # 无旁白模式:无人声轨,用静音基轨(时长=总时长),BGM/SFX 混其上;无则纯静音
        try:
            total = max(float(voice.get("total_duration_sec") or 0.0), 0.5)
        except (TypeError, ValueError):
            total = max(_release_duration(project), 1.0)
        voice_audio = _make_silent_base_track(project, render_dir, total)
    else:
        voice_audio = _release_audio_path(project)
    assets = _audio_assets(project)
    bgm = assets.get("bgm")
    bgm_path = None
    bgm_to_voice_db = DEFAULT_BGM_TO_VOICE_DB
    if isinstance(bgm, dict):
        bgm_path = _audio_asset_path(project, bgm.get("path"))
        try:
            bgm_to_voice_db = float(bgm.get("bgm_to_voice_db") or DEFAULT_BGM_TO_VOICE_DB)
        except (TypeError, ValueError):
            bgm_to_voice_db = DEFAULT_BGM_TO_VOICE_DB
    sfx_events = _normalized_sfx_events(project, assets)
    if bgm_path is None and not sfx_events:
        output_path = render_dir / "normalized_audio.m4a"
        if voiceless:
            # 纯静音片(无旁白+无BGM+无SFX):直接编码,不 loudnorm
            # (纯静音做 loudnorm 会让 aac 编码器报 Invalid argument)
            _run_ffmpeg(
                project,
                ["ffmpeg", "-y", "-i", str(voice_audio), "-c:a", "aac", "-b:a", "128k",
                 str(output_path)],
                output_path,
            )
        else:
            _normalize_release_audio(project, voice_audio, output_path)
        manifest = _audio_mix_manifest(project, rendered=False)
        manifest.update(_audio_normalization_manifest(output_path))
        manifest["mixed_audio_path"] = str(output_path.relative_to(project.path))
        return output_path, manifest

    output_path = render_dir / "mixed_audio.m4a"
    command = ["ffmpeg", "-y", "-i", str(voice_audio)]
    filter_parts: list[str] = []
    mix_inputs = ["[0:a]"]
    input_index = 1
    if bgm_path is not None:
        command.extend(["-stream_loop", "-1", "-i", str(bgm_path)])
        filter_parts.append(f"[{input_index}:a]volume={bgm_to_voice_db:.1f}dB[bgm]")
        mix_inputs.append("[bgm]")
        input_index += 1
    for event_index, event in enumerate(sfx_events):
        command.extend(["-i", str(event["path"])])
        delay_ms = int(event["at_sec"] * 1000)
        label = f"sfx{event_index}"
        filter_parts.append(
            f"[{input_index}:a]adelay={delay_ms}|{delay_ms},"
            f"volume={event['gain_db']:.1f}dB[{label}]"
        )
        mix_inputs.append(f"[{label}]")
        input_index += 1
    filter_parts.append(
        "".join(mix_inputs)
        + f"amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0,"
        + f"{RELEASE_LOUDNORM_FILTER}[a]"
    )
    command.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[a]",
            "-c:a",
            "aac",
            str(output_path),
        ]
    )
    _run_ffmpeg(project, command, output_path)
    manifest = _audio_mix_manifest(project, rendered=True, mixed_audio_path=output_path)
    manifest.update(_audio_normalization_manifest(output_path))
    return output_path, manifest


def _script_scene_text(project: ProjectRef) -> dict[str, str]:
    script_path = project.path / "artifacts" / "script.json"
    if not script_path.exists():
        return {}
    script = read_json(script_path)
    result: dict[str, str] = {}
    for index, scene in enumerate(script.get("scenes", []), start=1):
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("id") or scene.get("scene_id") or f"s{index}")
        result[scene_id] = str(scene.get("narration_text") or "")
    return result


def _visual_plan(project: ProjectRef) -> dict[str, Any]:
    visual_path = project.path / "artifacts" / "visual_plan.json"
    if not visual_path.exists():
        return {}
    plan = read_json(visual_path)
    return plan if isinstance(plan, dict) else {}


def _visual_plan_scenes(project: ProjectRef) -> list[dict[str, Any]]:
    visual_plan = _visual_plan(project)
    return [scene for scene in visual_plan.get("scenes", []) if isinstance(scene, dict)]


def _non_publish_grade_visual_scenes(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        diagnosis = scene.get("asset_diagnosis")
        if not isinstance(diagnosis, dict) or diagnosis.get("publish_grade_visual") is not False:
            continue
        blocked.append(
            {
                "scene_id": str(scene.get("scene_id") or scene.get("id") or f"s{index}"),
                "asset_status": diagnosis.get("asset_status"),
                "next_action_zh": diagnosis.get("next_action_zh")
                or diagnosis.get("missing_evidence_action_zh"),
            }
        )
    return blocked


def _visual_plan_manifest_metadata(project: ProjectRef) -> dict[str, Any]:
    visual_plan = _visual_plan(project)
    metadata: dict[str, Any] = {}
    if visual_plan:
        metadata["visual_plan_sha256"] = canonical_json_hash(visual_plan)
    for key in ("profile", "profile_preset", "profile_required_evidence"):
        value = visual_plan.get(key)
        if value:
            metadata[key] = value
    return metadata


def _video_size(ratio: str) -> str:
    return "1920x1080" if ratio == "16:9" else "1080x1920"


def _video_dimensions(ratio: str) -> tuple[int, int]:
    return (1920, 1080) if ratio == "16:9" else (1080, 1920)


def _font_path() -> str | None:
    for candidate in [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        str(Path.home() / ".cache/lingjian/fonts/NotoSansSC-Regular.otf"),
    ]:
        if Path(candidate).exists():
            return candidate
    return None


def _escape_drawtext(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _drawtext_filter(
    text: str,
    *,
    max_chars: int = 18,
    enable_expr: str | None = None,
) -> str:
    lines, _warnings = break_cjk_text(text, max_chars=max_chars, max_lines=CAPTION_MAX_LINES)
    font = _font_path()
    font_part = f"fontfile='{_escape_drawtext(font)}':" if font else ""
    enable_part = f"enable='{enable_expr}':" if enable_expr else ""
    filters = []
    start_y = f"h*{CAPTION_RAIL_CENTER_RATIO:.2f}-text_h/2"
    for index, line in enumerate(lines or ["灵剪"]):
        y_expr = start_y if index == 0 else f"h*{CAPTION_RAIL_CENTER_RATIO:.2f}-text_h/2"
        filters.append(
            "drawtext="
            f"{font_part}"
            f"text='{_escape_drawtext(line)}':"
            "fontcolor=white:"
            "fontsize=46:"
            "x=(w-text_w)/2:"
            f"y={y_expr}:"
            "box=1:"
            "boxcolor=black@0.58:"
            "boxborderw=18:"
            f"{enable_part}"
            "fix_bounds=1"
        )
    return ",".join(filters)


def _caption_safe_area_bbox(width: int, height: int) -> dict[str, Any]:
    start_y = int(height * CAPTION_SAFE_START_RATIO)
    end_y = int(height * CAPTION_SAFE_END_RATIO)
    return {
        "x": 0,
        "y": start_y,
        "w": width,
        "h": max(end_y - start_y, 0),
        "canvas_width": width,
        "canvas_height": height,
        "unit": "px",
    }


def _caption_render_bbox(width: int, height: int) -> dict[str, Any]:
    box_w = int(width * CAPTION_RAIL_WIDTH_RATIO)
    box_h = max(int(height * CAPTION_RAIL_HEIGHT_RATIO), 76)
    safe_top = int(height * CAPTION_SAFE_START_RATIO)
    safe_bottom = int(height * CAPTION_SAFE_END_RATIO)
    y = int(height * CAPTION_RAIL_CENTER_RATIO - box_h / 2)
    y = max(safe_top + 4, min(y, safe_bottom - box_h - 4))
    return {
        "x": max((width - box_w) // 2, 0),
        "y": max(y, 0),
        "w": min(box_w, width),
        "h": min(box_h, height),
        "canvas_width": width,
        "canvas_height": height,
        "unit": "px",
    }


def _attach_caption_render_bboxes(
    cues: list[dict[str, Any]],
    *,
    width: int,
    height: int,
) -> list[dict[str, Any]]:
    if not cues:
        return cues
    bbox = _caption_render_bbox(width, height)
    safe_area = _caption_safe_area_bbox(width, height)
    updated: list[dict[str, Any]] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        updated.append(
            {
                **cue,
                "caption_bbox": dict(bbox),
                "caption_safe_area": dict(safe_area),
            }
        )
    return updated


def _caption_max_chars(scene: dict[str, Any]) -> int:
    contract = scene.get("caption_contract")
    if isinstance(contract, dict):
        try:
            return max(8, min(int(contract.get("max_chars_per_line") or 0), 18))
        except (TypeError, ValueError):
            pass
    sheet = scene.get("director_review_sheet")
    if isinstance(sheet, dict):
        position_size = sheet.get("subtitle_position_size")
        if isinstance(position_size, dict):
            try:
                return max(8, min(int(position_size.get("max_chars_per_line") or 0), 18))
            except (TypeError, ValueError):
                pass
    return CAPTION_DEFAULT_MAX_CHARS_PER_LINE


def _caption_chunks(text: str, max_chars: int) -> list[str]:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return []
    max_chunk_chars = min(max_chars * CAPTION_MAX_LINES, CAPTION_ESTIMATED_MAX_CHARS_PER_CUE)
    chunks: list[str] = []
    current = ""
    punctuation = set("，。！？；、,.!?;")
    for char in normalized:
        current += char
        if char in punctuation or len(current) >= max_chunk_chars:
            chunks.extend(_split_long_caption_chunk(current.strip(), max_chunk_chars))
            current = ""
    if current.strip():
        chunks.extend(_split_long_caption_chunk(current.strip(), max_chunk_chars))
    return [chunk for chunk in chunks if chunk]


def _split_long_caption_chunk(text: str, max_chunk_chars: int) -> list[str]:
    if len(text) <= max_chunk_chars:
        return [text]
    return [text[index : index + max_chunk_chars] for index in range(0, len(text), max_chunk_chars)]


def _caption_cues(text: str, duration: float, max_chars: int) -> list[dict[str, Any]]:
    chunks = _caption_chunks(text, max_chars)
    if not chunks:
        return []
    safe_duration = max(float(duration), CAPTION_MIN_CUE_SEC)
    total_gap = CAPTION_GAP_SEC * max(len(chunks) - 1, 0)
    available = max(safe_duration - total_gap, CAPTION_MIN_CUE_SEC)
    weights = [max(len(chunk), 1) for chunk in chunks]
    total_weight = sum(weights)
    cues: list[dict[str, Any]] = []
    elapsed = 0.0
    for index, chunk in enumerate(chunks):
        if elapsed >= safe_duration:
            break
        cue_duration = max(available * (weights[index] / total_weight), CAPTION_MIN_CUE_SEC)
        cue_duration = min(cue_duration, CAPTION_ESTIMATED_MAX_CUE_SEC)
        end = min(elapsed + cue_duration, safe_duration)
        if end <= elapsed:
            end = min(elapsed + CAPTION_MIN_CUE_SEC, safe_duration)
        lines, warnings = break_cjk_text(chunk, max_chars=max_chars, max_lines=CAPTION_MAX_LINES)
        cues.append(
            {
                "index": index + 1,
                "start_sec": round(elapsed, 3),
                "end_sec": round(end, 3),
                "text": chunk,
                "lines": lines,
                "max_chars_per_line": max_chars,
                "warnings": warnings,
                "source": "estimated",
            }
        )
        elapsed = min(end + CAPTION_GAP_SEC, safe_duration)
    return cues


def _float_time(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _caption_time(raw: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in raw:
            return _float_time(raw.get(key))
    return None


def _voice_caption_raw_cues(voice_segment: dict[str, Any] | None) -> list[Any] | None:
    if not isinstance(voice_segment, dict):
        return None
    if "caption_cues" in voice_segment:
        raw_cues = voice_segment.get("caption_cues")
    elif "timed_captions" in voice_segment:
        raw_cues = voice_segment.get("timed_captions")
    else:
        return None
    return raw_cues if isinstance(raw_cues, list) else []


def _voice_caption_cues(
    voice_segment: dict[str, Any] | None,
    *,
    duration: float,
    max_chars: int,
) -> tuple[list[dict[str, Any]], str]:
    raw_cues = _voice_caption_raw_cues(voice_segment)
    if raw_cues is None:
        return [], "missing"
    if not raw_cues:
        return [], "invalid"
    safe_duration = max(float(duration), CAPTION_MIN_CUE_SEC)
    cues: list[dict[str, Any]] = []
    previous_end = 0.0
    for raw in raw_cues:
        if not isinstance(raw, dict):
            return [], "invalid"
        text = str(raw.get("text") or raw.get("caption") or "").strip()
        start = _caption_time(raw, "start_sec", "start", "begin_sec", "begin")
        end = _caption_time(raw, "end_sec", "end", "finish_sec", "finish")
        if not text or start is None or end is None:
            return [], "invalid"
        start = max(start, 0.0)
        end = min(end, safe_duration, start + CAPTION_MAX_CUE_SEC)
        if end <= start:
            return [], "invalid"
        if cues and start < previous_end:
            return [], "invalid"
        lines, warnings = break_cjk_text(text, max_chars=max_chars, max_lines=CAPTION_MAX_LINES)
        cue_source = str(raw.get("source") or "voice_segment").strip() or "voice_segment"
        timing_basis = str(raw.get("timing_basis") or "").strip()
        cue = {
            "index": len(cues) + 1,
            "start_sec": round(start, 3),
            "end_sec": round(end, 3),
            "text": text,
            "lines": lines,
            "max_chars_per_line": max_chars,
            "warnings": warnings,
            "source": cue_source,
        }
        if timing_basis:
            cue["timing_basis"] = timing_basis
        cues.append(
            cue
        )
        previous_end = end
    return cues, "valid"


def _caption_timing_basis(cues: list[dict[str, Any]]) -> str | None:
    bases = {
        str(cue.get("timing_basis") or "").strip()
        for cue in cues
        if isinstance(cue, dict) and str(cue.get("timing_basis") or "").strip()
    }
    if not bases:
        return None
    if len(bases) == 1:
        return next(iter(bases))
    return "mixed"


def _caption_reading_units_for_render(text: str) -> int:
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    latin_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", text)
    return len(cjk_chars) + len(latin_words) * 2


def _transition_safe_caption_cues(
    cues: list[dict[str, Any]],
    *,
    duration: float,
    trim_start_sec: float = 0.0,
    trim_end_sec: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    trim_start = max(float(trim_start_sec or 0.0), 0.0)
    trim_end = max(float(trim_end_sec or 0.0), 0.0)
    safe_duration = max(float(duration), 0.0)
    safe_start = trim_start + (CAPTION_TRANSITION_GUARD_SEC if trim_start > 0 else 0.0)
    safe_end = safe_duration - trim_end - (CAPTION_TRANSITION_GUARD_SEC if trim_end > 0 else 0.0)
    safe_start = min(max(safe_start, 0.0), safe_duration)
    safe_end = min(max(safe_end, 0.0), safe_duration)
    applied = trim_start > 0 or trim_end > 0
    audit: dict[str, Any] = {
        "applied": applied,
        "trim_start_sec": round(trim_start, 3),
        "trim_end_sec": round(trim_end, 3),
        "guard_sec": round(CAPTION_TRANSITION_GUARD_SEC, 3) if applied else 0.0,
        "safe_start_sec": round(safe_start, 3),
        "safe_end_sec": round(safe_end, 3),
        "adjusted_cue_count": 0,
        "dropped_cue_count": 0,
    }
    if not cues or not applied:
        return cues, audit
    items: list[dict[str, Any]] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        start = _float_time(cue.get("start_sec"))
        end = _float_time(cue.get("end_sec"))
        if start is None or end is None or end <= start:
            continue
        if end <= safe_start or start >= safe_end:
            audit["dropped_cue_count"] += 1
            continue
        text = str(cue.get("text") or "")
        original_duration = end - start
        readable_duration = _caption_reading_units_for_render(text) / max(
            CAPTION_TARGET_READING_UNITS_PER_SEC, 1.0
        )
        target_duration = max(CAPTION_MIN_RENDERED_CUE_SEC, readable_duration)
        target_duration = min(
            max(target_duration, CAPTION_MIN_RENDERED_CUE_SEC),
            CAPTION_MAX_CUE_SEC,
        )
        target_duration = min(target_duration, original_duration, CAPTION_MAX_CUE_SEC)
        items.append(
            {
                "cue": cue,
                "original_start": start,
                "original_end": end,
                "duration": target_duration,
            }
        )
    total_required = sum(float(item["duration"]) for item in items)
    total_required += CAPTION_GAP_SEC * max(len(items) - 1, 0)
    if total_required > max(safe_end - safe_start, 0.0) + 0.001:
        audit["dropped_cue_count"] += len(items)
        return [], audit
    positioned = []
    previous_end = safe_start - CAPTION_GAP_SEC
    for item in items:
        duration_sec = float(item["duration"])
        original_start = float(item["original_start"])
        start = max(original_start, safe_start, previous_end + CAPTION_GAP_SEC)
        end = start + duration_sec
        positioned.append({**item, "start": start, "end": end})
        previous_end = end
    latest_start = safe_end + CAPTION_GAP_SEC
    for index in range(len(positioned) - 1, -1, -1):
        item = positioned[index]
        duration_sec = float(item["duration"])
        if item["end"] <= safe_end and item["end"] <= latest_start - CAPTION_GAP_SEC:
            latest_start = item["start"]
            continue
        next_end = min(safe_end, latest_start - CAPTION_GAP_SEC)
        next_start = next_end - duration_sec
        if next_start < safe_start - 0.001:
            audit["dropped_cue_count"] += len(positioned)
            return [], audit
        positioned[index] = {**item, "start": next_start, "end": next_end}
        latest_start = next_start
    adjusted: list[dict[str, Any]] = []
    for item in positioned:
        duration_sec = float(item["duration"])
        next_start = max(float(item["start"]), safe_start)
        next_end = next_start + duration_sec
        if next_end > safe_end + 0.001:
            audit["dropped_cue_count"] += 1
            continue
        cue = item["cue"]
        start = float(item["original_start"])
        end = float(item["original_end"])
        changed = abs(next_start - start) > 0.001 or abs(next_end - end) > 0.001
        next_cue = dict(cue)
        next_cue["index"] = len(adjusted) + 1
        next_cue["start_sec"] = round(next_start, 3)
        next_cue["end_sec"] = round(next_end, 3)
        if changed:
            audit["adjusted_cue_count"] += 1
            next_cue["transition_safe_window"] = {
                "applied": True,
                "original_start_sec": round(start, 3),
                "original_end_sec": round(end, 3),
                "trim_start_sec": round(trim_start, 3),
                "trim_end_sec": round(trim_end, 3),
                "guard_sec": round(CAPTION_TRANSITION_GUARD_SEC, 3),
            }
        adjusted.append(next_cue)
    return adjusted, audit


def _caption_timing_release_fields(
    caption_source: str,
    cues: list[dict[str, Any]],
) -> dict[str, Any]:
    timing_basis = _caption_timing_basis(cues)
    cue_sources = {
        str(cue.get("source") or "").strip()
        for cue in cues
        if isinstance(cue, dict) and str(cue.get("source") or "").strip()
    }
    cue_bases = {
        str(cue.get("timing_basis") or "").strip()
        for cue in cues
        if isinstance(cue, dict) and str(cue.get("timing_basis") or "").strip()
    }
    recovery = {
        "release_ready": False,
        "release_gate": "strict_caption_timing",
        "recovery_target_field": "artifacts/voice_plan.json segments[].caption_cues",
        "accepted_timing_sources": [
            "voice_plan.caption_cues",
            "voice_plan.timed_captions",
            "ASR",
            "manual_timing",
        ],
        "required_timing_basis": "real_segment_duration",
    }
    if caption_source == "voice_segment_invalid":
        return {
            **recovery,
            "release_blocker_code": "RELEASE_CAPTION_VOICE_TIMING_INVALID",
            "release_blocker_zh": "voice_plan 中的 caption_cues/timed_captions 不可解析。",
            "recovery_next_action_zh": (
                "请在 voice_plan.segments[].caption_cues 中补齐每句字幕的"
                " start_sec/end_sec/text/source,重新审阅 voice 后再 release render。"
            ),
        }
    if (
        caption_source == "estimated"
        or "estimated" in cue_sources
        or "estimated" in cue_bases
    ):
        return {
            **recovery,
            "release_blocker_code": "RELEASE_CAPTION_TIMING_IS_ESTIMATED",
            "release_blocker_zh": (
                "当前字幕 timing 来自 estimated fallback,不能作为发布级口播节奏证据。"
            ),
            "recovery_next_action_zh": (
                "请基于真实 TTS 分段时长、ASR 或人工校准写入"
                " voice_plan.segments[].caption_cues,重新审阅 voice 后再 release render。"
            ),
        }
    if caption_source == "voice_duration_aligned" and timing_basis != "real_segment_duration":
        return {
            **recovery,
            "release_blocker_code": "RELEASE_CAPTION_TIMING_BASIS_NOT_VERIFIABLE",
            "release_blocker_zh": (
                "voice_duration_aligned 字幕缺少 real_segment_duration timing_basis。"
            ),
            "recovery_next_action_zh": (
                "请把 voice_duration_aligned cues 的 timing_basis 标为"
                " real_segment_duration,或改用 ASR/人工校准时间戳。"
            ),
        }
    return {
        "release_ready": True,
        "release_gate": "strict_caption_timing",
    }


def _timed_caption_filter(
    text: str,
    *,
    duration: float,
    max_chars: int,
    cues: list[dict[str, Any]] | None = None,
    trim_start_sec: float = 0.0,
    trim_end_sec: float = 0.0,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    cues = cues if cues is not None else _caption_cues(text, duration, max_chars)
    cues, safe_window = _transition_safe_caption_cues(
        cues,
        duration=duration,
        trim_start_sec=trim_start_sec,
        trim_end_sec=trim_end_sec,
    )
    filters = []
    for cue in cues:
        enable = f"between(t\\,{cue['start_sec']:.3f}\\,{cue['end_sec']:.3f})"
        filters.append(_drawtext_filter(cue["text"], max_chars=max_chars, enable_expr=enable))
    return ",".join(filter_text for filter_text in filters if filter_text), cues, safe_window


def _ffmpeg_stderr_tail(stderr: str, project_path: Path) -> str:
    tail = "\n".join(stderr.splitlines()[-8:])
    return tail.replace(str(project_path), "<project>").replace(str(Path.home()), "~")


def _run_ffmpeg(project: ProjectRef, command: list[str], output_path: Path) -> None:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=FFMPEG_TIMEOUT_SEC,
    )
    if completed.returncode != 0 or not output_path.exists():
        stderr_tail = _ffmpeg_stderr_tail(completed.stderr, project.path)
        if "No such filter" in completed.stderr and "drawtext" in completed.stderr:
            raise LingjianError(
                "FFMPEG_FILTER_UNAVAILABLE",
                "当前 FFmpeg 缺少 release 字幕渲染所需滤镜。",
                "请安装带 drawtext/libfreetype 的 FFmpeg 后重试。",
                {"exit_code": completed.returncode, "ffmpeg_stderr_tail": stderr_tail},
            )
        raise LingjianError(
            "RENDER_FAILED",
            "release 渲染失败。",
            "请检查 FFmpeg、字体与输入 artifact 后重试。",
            {"exit_code": completed.returncode, "ffmpeg_stderr_tail": stderr_tail},
        )


def _render_ffmpeg_card_video(
    project: ProjectRef,
    ratio: str,
    video_path: Path,
    include_audio: bool = False,
    audio_path: Path | None = None,
) -> None:
    duration = _release_duration(project)
    caption_filter, _cues, _safe_window = _timed_caption_filter(
        _release_text(project),
        duration=duration,
        max_chars=CAPTION_DEFAULT_MAX_CHARS_PER_LINE,
    )
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x111827:s={_video_size(ratio)}:d={duration:.2f}",
    ]
    if include_audio:
        command.extend(["-i", str(audio_path or _release_audio_path(project))])
    command.extend(
        [
            "-vf",
            caption_filter or _drawtext_filter("灵剪"),
            "-map",
            "0:v:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if include_audio:
        command.extend(["-map", "1:a:0", "-c:a", "aac", "-shortest"])
    else:
        command.append("-an")
    command.extend(
        [
            str(video_path),
        ]
    )
    _run_ffmpeg(project, command, video_path)


def _scene_duration(
    scene: dict[str, Any],
    voice_segments: dict[str, dict[str, Any]],
    scene_count: int,
    project: ProjectRef,
) -> float:
    scene_id = str(scene.get("scene_id") or scene.get("id") or "")
    voice_segment = voice_segments.get(scene_id)
    if voice_segment and voice_segment.get("duration_sec"):
        return max(float(voice_segment["duration_sec"]), 0.5)
    if scene.get("duration_sec"):
        return max(float(scene["duration_sec"]), 0.5)
    return max(_release_duration(project) / max(scene_count, 1), 0.5)


def _scene_asset(project: ProjectRef, scene: dict[str, Any]) -> Path | None:
    raw_path = scene.get("asset_path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    return resolve_inside(project.path, project.path / raw_path)


def _video_scene_filters(width: int, height: int) -> list[str]:
    if height <= width:
        return [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "setsar=1",
            f"fps={FPS}",
        ]
    foreground_width = max(width - 96, 1)
    foreground_height = max(int(height * 0.54), 1)
    foreground_y = max(int(height * 0.11), 0)
    return [
        (
            "split=2[ljbg][ljfg];"
            f"[ljbg]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},gblur=sigma=18,eq=brightness=-0.16:saturation=0.75"
            "[ljbg2];"
            f"[ljfg]scale={foreground_width}:{foreground_height}:"
            "force_original_aspect_ratio=decrease[ljfg2];"
            f"[ljbg2][ljfg2]overlay=(W-w)/2:{foreground_y},setsar=1,fps={FPS}"
        )
    ]


def _scene_text(scene: dict[str, Any], script_text: dict[str, str]) -> str:
    scene_id = str(scene.get("scene_id") or scene.get("id") or "")
    return str(scene.get("narration_text") or script_text.get(scene_id) or "灵剪")


def _append_subtitle_filter(
    filters: list[str],
    *,
    scene: dict[str, Any],
    voice_segment: dict[str, Any] | None,
    text: str,
    duration: float,
    enabled: bool,
    caption_trim_start_sec: float = 0.0,
    caption_trim_end_sec: float = 0.0,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    if not enabled:
        return [], "disabled", {"applied": False}
    max_chars = _caption_max_chars(scene)
    voice_cues, voice_status = _voice_caption_cues(
        voice_segment,
        duration=duration,
        max_chars=max_chars,
    )
    if voice_status == "valid":
        cue_sources = {
            str(cue.get("source") or "").strip()
            for cue in voice_cues
            if isinstance(cue, dict)
        }
        cue_source = next(iter(cue_sources)) if len(cue_sources) == 1 else "voice_segment"
    elif voice_status == "invalid":
        cue_source = "voice_segment_invalid"
    else:
        cue_source = "estimated"
    filter_text, cues, safe_window = _timed_caption_filter(
        text,
        duration=duration,
        max_chars=max_chars,
        cues=voice_cues or None,
        trim_start_sec=caption_trim_start_sec,
        trim_end_sec=caption_trim_end_sec,
    )
    if filter_text:
        filters.append(filter_text)
    return cues, cue_source, safe_window


def _render_scene_clip(
    project: ProjectRef,
    ratio: str,
    scene: dict[str, Any],
    scene_index: int,
    duration: float,
    text: str,
    voice_segment: dict[str, Any] | None,
    output_path: Path,
    caption_trim_start_sec: float = 0.0,
    caption_trim_end_sec: float = 0.0,
) -> dict[str, Any]:
    scene = ensure_scene_asset(project, dict(scene))
    width, height = _video_dimensions(ratio)
    generator = str(scene.get("generator") or "fallback_solid")
    subtitle_burn = bool(scene.get("subtitle_burn", True))
    asset = _scene_asset(project, scene)
    render_source = "fallback_solid"
    caption_cues: list[dict[str, Any]] = []
    caption_source = "none"
    caption_safe_window: dict[str, Any] = {"applied": False}
    command: list[str]
    if asset and asset.exists() and asset.suffix.lower() in {".mp4", ".mov", ".m4v"}:
        render_source = "video"
        filters = _video_scene_filters(width, height)
        caption_cues, caption_source, caption_safe_window = _append_subtitle_filter(
            filters,
            scene=scene,
            voice_segment=voice_segment,
            text=text,
            duration=duration,
            enabled=subtitle_burn,
            caption_trim_start_sec=caption_trim_start_sec,
            caption_trim_end_sec=caption_trim_end_sec,
        )
        command = [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(asset),
            "-t",
            f"{duration:.2f}",
            "-vf",
            ",".join(filters),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
    elif asset and asset.exists() and asset.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        render_source = "image"
        zoom_frames = max(int(duration * FPS), 1)
        filters = [
            f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase",
            f"crop={width * 2}:{height * 2}",
            (
                "zoompan="
                "z='min(zoom+0.0007,1.15)':"
                f"d={zoom_frames}:s={width}x{height}:fps={FPS}"
            ),
        ]
        caption_cues, caption_source, caption_safe_window = _append_subtitle_filter(
            filters,
            scene=scene,
            voice_segment=voice_segment,
            text=text,
            duration=duration,
            enabled=subtitle_burn,
            caption_trim_start_sec=caption_trim_start_sec,
            caption_trim_end_sec=caption_trim_end_sec,
        )
        command = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(asset),
            "-t",
            f"{duration:.2f}",
            "-vf",
            ",".join(filters),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
    else:
        filters = []
        caption_cues, caption_source, caption_safe_window = _append_subtitle_filter(
            filters,
            scene=scene,
            voice_segment=voice_segment,
            text=text,
            duration=duration,
            enabled=True,
            caption_trim_start_sec=caption_trim_start_sec,
            caption_trim_end_sec=caption_trim_end_sec,
        )
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x111827:s={width}x{height}:d={duration:.2f}",
            "-vf",
            ",".join(filters),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
    _run_ffmpeg(project, command, output_path)
    caption_cues = _attach_caption_render_bboxes(
        caption_cues,
        width=width,
        height=height,
    )
    caption_timing = {
        "mode": "timed_drawtext",
        "source": caption_source,
        "cue_count": len(caption_cues),
        "max_chars_per_line": _caption_max_chars(scene),
        "max_cue_sec": CAPTION_MAX_CUE_SEC,
        "estimated_max_cue_sec": CAPTION_ESTIMATED_MAX_CUE_SEC,
        "transition_safe_window": caption_safe_window,
    }
    timing_basis = _caption_timing_basis(caption_cues)
    if timing_basis:
        caption_timing["timing_basis"] = timing_basis
    caption_timing.update(_caption_timing_release_fields(caption_source, caption_cues))
    rendered_duration_sec = _ffprobe_media_duration_sec_for_render(output_path)
    return {
        "scene_id": str(scene.get("scene_id") or scene.get("id") or f"s{scene_index}"),
        "generator": generator,
        "render_width": width,
        "render_height": height,
        "asset_path": str(asset.relative_to(project.path)) if asset and asset.exists() else None,
        "asset_origin": scene.get("asset_origin"),
        "generation_status": scene.get("generation_status"),
        "host_generation_contract": scene.get("host_generation_contract"),
        "render_source": render_source,
        "duration_sec": duration,
        "rendered_duration_sec": rendered_duration_sec or duration,
        "narration_text": text,
        "on_screen_text": scene.get("on_screen_text"),
        "visual_prompt": scene.get("visual_prompt"),
        "bgm": scene.get("bgm"),
        "bgm_strategy": scene.get("bgm_strategy"),
        "music": scene.get("music"),
        "music_strategy": scene.get("music_strategy"),
        "audio_sfx_notes": scene.get("audio_sfx_notes"),
        "sfx_points": scene.get("sfx_points"),
        "sound_cues": scene.get("sound_cues"),
        "visual_events": scene.get("visual_events"),
        "audio_visual_alignment": scene.get("audio_visual_alignment"),
        "subtitle_burn": subtitle_burn,
        "caption_render_region": _caption_render_bbox(width, height),
        "caption_safe_area": _caption_safe_area_bbox(width, height),
        "caption_transition_safe_window": caption_safe_window,
        "caption_cues": caption_cues,
        "caption_timing": caption_timing,
        "template_id": scene.get("template_id"),
        "blueprint_id": scene.get("blueprint_id"),
        "visual_archetype": scene.get("visual_archetype"),
        "asset_recipe_id": scene.get("asset_recipe_id"),
        "asset_diagnosis": scene.get("asset_diagnosis"),
        "engine_policy": scene.get("engine_policy"),
        "route_reason": scene.get("route_reason"),
        "asset_strategy_v2": scene.get("asset_strategy_v2"),
        "stock_image_policy": _scene_stock_image_policy(scene),
        "stock_image_sources": scene.get("stock_image_sources"),
        "expected_real_evidence": scene.get("expected_real_evidence"),
        "evidence_asset_refs": scene.get("evidence_asset_refs"),
        "evidence_asset_ids": scene.get("evidence_asset_ids"),
        "director_knowledge_refs": scene.get("director_knowledge_refs"),
        "caption_contract": scene.get("caption_contract"),
        "keyframes": _scene_keyframes_metadata(scene),
        "director_review_sheet": scene.get("director_review_sheet"),
        "director_review_sheet_v2": scene.get("director_review_sheet_v2"),
        "material_key": scene.get("material_key"),
        "compiler_policy": scene.get("compiler_policy"),
        "replaceable_fields": scene.get("replaceable_fields"),
        "non_replaceable_fields": scene.get("non_replaceable_fields"),
        "layout_contract": scene.get("layout_contract"),
        "motion_intent": (
            scene.get("motion_intent") or scene.get("motion_spec") or scene.get("motion")
        ),
        "motion_rule_ids": scene.get("motion_rule_ids")
        or (scene.get("motion_intent") or {}).get("motion_rule_ids"),
        "transition_plan": scene.get("transition_plan"),
        "requires_real_evidence_asset": scene.get("requires_real_evidence_asset"),
        "style_lock": scene.get("style_lock"),
        "inherits_design": scene.get("inherits_design"),
        "develop_full_duration": scene.get("develop_full_duration"),
    }


def _scene_transition_plan(scene: dict[str, Any]) -> dict[str, Any]:
    plan = scene.get("transition_plan")
    return plan if isinstance(plan, dict) else {}


def _scene_stock_image_policy(scene: dict[str, Any]) -> object | None:
    direct = scene.get("stock_image_policy")
    if direct not in (None, "", [], {}):
        return direct
    strategy = scene.get("asset_strategy_v2")
    if isinstance(strategy, dict):
        return strategy.get("stock_image_policy")
    return None


def _scene_keyframes_metadata(scene: dict[str, Any]) -> list[Any] | None:
    direct = scene.get("keyframes") or scene.get("keyframe_beats")
    if isinstance(direct, list):
        return direct
    for key in ("director_review_sheet_v2", "director_review_sheet"):
        sheet = scene.get(key)
        if isinstance(sheet, dict):
            sheet_keyframes = sheet.get("keyframes") or sheet.get("keyframe_beats")
            if isinstance(sheet_keyframes, list):
                return sheet_keyframes
    return None


def _transition_family(scene: dict[str, Any], index: int) -> str:
    plan = _scene_transition_plan(scene)
    family = str(plan.get("family") or plan.get("intent") or "").strip()
    if family:
        return family
    role = str(scene.get("visual_archetype") or scene.get("role") or "").strip()
    return role or f"scene-{index}"


def xfade_name_for_transition_family(family: str, index: int) -> str:
    normalized = family.strip().lower().replace("_", "-").replace(" ", "-")
    mapped = XFADE_FAMILY_MAP.get(normalized)
    if mapped:
        return mapped
    return XFADE_TRANSITIONS[index % len(XFADE_TRANSITIONS)]


def _xfade_name(family: str, index: int) -> str:
    return xfade_name_for_transition_family(family, index)


def _transition_duration(rendered_scenes: list[dict[str, Any]]) -> float:
    durations = [_rendered_scene_duration_sec(scene) for scene in rendered_scenes]
    shortest = min(durations) if durations else TRANSITION_DEFAULT_SEC
    return max(TRANSITION_MIN_SEC, min(TRANSITION_DEFAULT_SEC, shortest / 4))


def _planned_transition_duration(durations: list[float]) -> float:
    return _transition_duration([{"duration_sec": duration} for duration in durations])


def _rendered_scene_duration_sec(scene: dict[str, Any]) -> float:
    for key in ("rendered_duration_sec", "duration_sec"):
        try:
            duration = float(scene.get(key) or 0)
        except (TypeError, ValueError):
            duration = 0.0
        if duration > 0:
            return duration
    return 0.0


def _render_concat_montage(
    project: ProjectRef,
    scene_dir: Path,
    clip_paths: list[Path],
    montage_path: Path,
) -> dict[str, Any]:
    concat_path = scene_dir / "concat.txt"
    concat_path.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in clip_paths),
        encoding="utf-8",
    )
    _run_ffmpeg(
        project,
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            str(montage_path),
        ],
        montage_path,
    )
    return {
        "rendered": False,
        "mode": "hard_concat",
        "reason": "当前分镜没有可执行 transition_plan,使用 ffmpeg concat 直接拼接。",
    }


def _render_xfade_montage(
    project: ProjectRef,
    clip_paths: list[Path],
    rendered_scenes: list[dict[str, Any]],
    montage_path: Path,
) -> dict[str, Any]:
    transition_sec = _transition_duration(rendered_scenes)
    command = ["ffmpeg", "-y"]
    for path in clip_paths:
        command.extend(["-i", str(path)])
    durations = [_rendered_scene_duration_sec(scene) for scene in rendered_scenes]
    filters: list[str] = [
        f"[{index}:v]fps={FPS},settb=AVTB,setpts=PTS-STARTPTS[v{index}n]"
        for index in range(len(clip_paths))
    ]
    transitions = []
    previous_label = "v0n"
    for index in range(1, len(clip_paths)):
        scene = rendered_scenes[index]
        family = _transition_family(scene, index)
        transition = _xfade_name(family, index)
        offset = max(sum(durations[:index]) - transition_sec * index, 0.01)
        output_label = f"v{index}"
        filters.append(
            f"[{previous_label}][v{index}n]"
            f"xfade=transition={transition}:duration={transition_sec:.3f}:"
            f"offset={offset:.3f}[{output_label}]"
        )
        transitions.append(
            {
                "from_scene_id": rendered_scenes[index - 1].get("scene_id"),
                "to_scene_id": scene.get("scene_id"),
                "family": family,
                "xfade": transition,
                "duration_sec": round(transition_sec, 3),
                "offset_sec": round(offset, 3),
            }
        )
        previous_label = output_label
    _run_ffmpeg(
        project,
        command
        + [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{previous_label}]",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(montage_path),
        ],
        montage_path,
    )
    return {
        "rendered": True,
        "mode": "ffmpeg_xfade",
        "transition_count": len(transitions),
        "transitions": transitions,
    }


def _render_visual_plan_video(
    project: ProjectRef,
    ratio: str,
    video_path: Path,
    scenes: list[dict[str, Any]],
) -> dict[str, Any]:
    scene_dir = video_path.parent / "scene_clips"
    scene_dir.mkdir(parents=True, exist_ok=True)
    voice_segments = _voice_segments(project)
    script_text = _script_scene_text(project)
    scene_count = len(scenes)
    planned_durations = [
        _scene_duration(scene, voice_segments, scene_count, project) for scene in scenes
    ]
    has_transition_plan = any(_scene_transition_plan(scene) for scene in scenes)
    caption_transition_sec = (
        _planned_transition_duration(planned_durations)
        if scene_count > 1 and has_transition_plan
        else 0.0
    )
    rendered_scenes = []
    clip_paths = []
    for index, scene in enumerate(scenes, start=1):
        duration = planned_durations[index - 1]
        text = _scene_text(scene, script_text)
        clip_path = scene_dir / f"scene_{index:03d}.mp4"
        scene_id = str(scene.get("scene_id") or scene.get("id") or f"s{index}")
        caption_trim_start = caption_transition_sec if index > 1 else 0.0
        caption_trim_end = caption_transition_sec if index < scene_count else 0.0
        rendered_scenes.append(
            _render_scene_clip(
                project,
                ratio,
                scene,
                index,
                duration,
                text,
                voice_segments.get(scene_id),
                clip_path,
                caption_trim_start_sec=caption_trim_start,
                caption_trim_end_sec=caption_trim_end,
            )
        )
        clip_paths.append(clip_path)
    montage_path = scene_dir / "montage.mp4"
    if len(clip_paths) > 1 and has_transition_plan:
        transition_rendering = _render_xfade_montage(
            project, clip_paths, rendered_scenes, montage_path
        )
    else:
        transition_rendering = _render_concat_montage(project, scene_dir, clip_paths, montage_path)
    audio_path, audio_mix = _render_release_audio(project, video_path.parent)
    audio_mix = _audio_mix_with_declared_requirements(audio_mix, rendered_scenes)
    expected_duration = _release_duration(project)
    _run_ffmpeg(
        project,
        [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(montage_path),
            "-i",
            str(audio_path),
            "-t",
            f"{expected_duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            str(video_path),
        ],
        video_path,
    )
    visual_real_count = sum(1 for scene in rendered_scenes if scene["render_source"] == "video")
    return {
        "scenes": rendered_scenes,
        "visual_real_count": visual_real_count,
        "visual_total": len(rendered_scenes),
        "transition_rendering": transition_rendering,
        "audio_mix": audio_mix,
        "video_duration_policy": {
            "mode": "loop_video_to_voice_duration",
            "expected_duration_sec": round(expected_duration, 3),
            "reason_zh": (
                "最终发布视频不允许静默截断口播;若视觉素材短于口播,"
                "渲染会循环视频到口播时长,再由 strict QA 以素材过短/重复阻断。"
            ),
        },
    }


def _release_caption_timing_blockers(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for scene in manifest.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        caption_timing = scene.get("caption_timing")
        if not isinstance(caption_timing, dict):
            continue
        if caption_timing.get("release_ready") is not False:
            continue
        blocker = {
            "scene_id": scene.get("scene_id"),
            "release_blocker_code": (
                caption_timing.get("release_blocker_code")
                or "RELEASE_CAPTION_TIMING_NOT_READY"
            ),
            "release_blocker_zh": caption_timing.get("release_blocker_zh"),
            "recovery_target_field": caption_timing.get("recovery_target_field"),
            "recovery_next_action_zh": caption_timing.get("recovery_next_action_zh"),
            "caption_timing_source": caption_timing.get("source"),
            "timing_basis": caption_timing.get("timing_basis"),
            "accepted_timing_sources": caption_timing.get("accepted_timing_sources"),
            "required_timing_basis": caption_timing.get("required_timing_basis"),
        }
        blockers.append({key: value for key, value in blocker.items() if value not in (None, "")})
    return blockers


def _release_audio_mix_blockers(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    audio_mix = manifest.get("audio_mix")
    scenes = [scene for scene in manifest.get("scenes") or [] if isinstance(scene, dict)]
    declared = _declared_audio_requirements(scenes)
    if isinstance(audio_mix, dict):
        declared = audio_mix.get("declared_audio_requirements") or declared
    if not isinstance(declared, dict):
        declared = {}
    if not isinstance(audio_mix, dict):
        if declared.get("bgm_required"):
            blockers.append(
                {
                    "release_blocker_code": "RELEASE_BGM_DECLARED_BUT_NOT_RENDERED",
                    "release_blocker_zh": "分镜声明了 BGM,但 release manifest 没有 BGM 混音证据。",
                    "scene_ids": declared.get("bgm_scene_ids") or [],
                }
            )
        if declared.get("sfx_required"):
            blockers.append(
                {
                    "release_blocker_code": "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED",
                    "release_blocker_zh": (
                        "分镜声明了音效点,但 release manifest 没有 SFX 混音证据。"
                    ),
                    "scene_ids": declared.get("sfx_scene_ids") or [],
                }
            )
        return blockers
    invalid_assets = audio_mix.get("invalid_audio_assets")
    try:
        invalid_count = int(audio_mix.get("invalid_audio_asset_count") or 0)
    except (TypeError, ValueError):
        invalid_count = 0
    if invalid_count > 0 or (isinstance(invalid_assets, list) and invalid_assets):
        blockers.append(
            {
                "release_blocker_code": "RELEASE_AUDIO_DECLARED_ASSET_MISSING",
                "release_blocker_zh": (
                    "voice_plan 声明了 BGM/SFX 源音频,但 release render 无法验证这些资产。"
                ),
                "invalid_audio_assets": invalid_assets if isinstance(invalid_assets, list) else [],
            }
        )
    bgm_present = bool(audio_mix.get("bgm_present"))
    try:
        sfx_count = int(audio_mix.get("sfx_count") or 0)
    except (TypeError, ValueError):
        sfx_count = 0
    if declared.get("bgm_required") and not bgm_present:
        blockers.append(
            {
                "release_blocker_code": "RELEASE_BGM_DECLARED_BUT_NOT_RENDERED",
                "release_blocker_zh": "分镜声明了 BGM,但最终 audio_mix 未包含 BGM。",
                "scene_ids": declared.get("bgm_scene_ids") or [],
            }
        )
    if declared.get("sfx_required") and sfx_count <= 0:
        blockers.append(
            {
                "release_blocker_code": "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED",
                "release_blocker_zh": "分镜声明了音效点,但最终 audio_mix 未包含 SFX 事件。",
                "scene_ids": declared.get("sfx_scene_ids") or [],
                "markers_by_scene": declared.get("sfx_markers_by_scene") or [],
            }
        )
    if (bgm_present or sfx_count > 0) and audio_mix.get("rendered") is not True:
        blockers.append(
            {
                "release_blocker_code": "RELEASE_AUDIO_MIX_NOT_RENDERED",
                "release_blocker_zh": (
                    "release manifest 声明包含 BGM/SFX,但未证明这些音频已混入最终音轨。"
                ),
            }
        )
    return [
        {key: value for key, value in blocker.items() if value not in (None, "", [])}
        for blocker in blockers
    ]


def _release_visual_evidence_blockers(
    project: ProjectRef,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    scenes = [scene for scene in manifest.get("scenes") or [] if isinstance(scene, dict)]
    evidence_scenes = [scene for scene in scenes if _scene_requires_visual_evidence(scene)]
    if not evidence_scenes:
        return []
    evidence_manifest = manifest.get("visual_evidence_assets")
    if not isinstance(evidence_manifest, dict) or not evidence_manifest.get("assets"):
        return [
            {
                "release_blocker_code": "RELEASE_VISUAL_EVIDENCE_ASSETS_MISSING",
                "release_blocker_zh": (
                    "导演契约要求真实证据画面,但 render manifest 缺少 evidence_assets 清单。"
                ),
                "scene_ids": [_render_scene_id(scene) for scene in evidence_scenes],
            }
        ]
    lookup = _evidence_asset_lookup(evidence_manifest)
    blockers: list[dict[str, Any]] = []
    for scene in evidence_scenes:
        scene_id = _render_scene_id(scene)
        raw_refs = scene.get("evidence_asset_refs")
        if not isinstance(raw_refs, list) or not raw_refs:
            blockers.append(
                {
                    "scene_id": scene_id,
                    "release_blocker_code": "RELEASE_SCENE_EVIDENCE_ASSET_UNBOUND",
                    "release_blocker_zh": (
                        "分镜要求真实证据素材,但该镜头没有绑定任何 evidence asset。"
                    ),
                    "expected_real_evidence": scene.get("expected_real_evidence"),
                }
            )
            continue
        refs = [
            _merged_evidence_ref(ref, lookup)
            for ref in raw_refs
            if isinstance(ref, dict)
        ]
        if any(_evidence_ref_targets_other_scene(ref, scene_id) for ref in refs):
            blockers.append(
                {
                    "scene_id": scene_id,
                    "release_blocker_code": "RELEASE_SCENE_EVIDENCE_TARGET_MISMATCH",
                    "release_blocker_zh": (
                        "分镜绑定的 evidence asset 属于其它镜头,不能跨镜复用。"
                    ),
                }
            )
        if any(_captured_dynamic_evidence_missing_target(ref) for ref in refs):
            blockers.append(
                {
                    "scene_id": scene_id,
                    "release_blocker_code": "RELEASE_SCENE_EVIDENCE_TARGET_UNBOUND",
                    "release_blocker_zh": (
                        "分镜绑定的真实录屏 evidence asset 缺少 target_scene_id。"
                    ),
                }
            )
        verifiable_refs = [ref for ref in refs if _evidence_video_is_verifiable(project, ref)]
        if not verifiable_refs:
            blockers.append(
                {
                    "scene_id": scene_id,
                    "release_blocker_code": "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED",
                    "release_blocker_zh": (
                        "分镜要求真实证据画面,但没有绑定可 ffprobe 验证的视频 evidence。"
                    ),
                    "expected_real_evidence": scene.get("expected_real_evidence"),
                }
            )
            continue
        if _scene_requires_captured_recording_evidence(scene) and not any(
            _evidence_ref_is_captured_recording(ref) for ref in verifiable_refs
        ):
            blockers.append(
                {
                    "scene_id": scene_id,
                    "release_blocker_code": "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC",
                    "release_blocker_zh": (
                        "实证型内容镜头不能只依赖 generated 证据卡;"
                        "必须绑定同镜 captured 录屏类视频 evidence。"
                    ),
                    "expected_real_evidence": scene.get("expected_real_evidence"),
                }
            )
        elif not _evidence_refs_match_expected_for_render(scene, verifiable_refs):
            blockers.append(
                {
                    "scene_id": scene_id,
                    "release_blocker_code": "RELEASE_SCENE_EVIDENCE_RECORDING_TYPE_MISMATCH",
                    "release_blocker_zh": (
                        "分镜绑定的 captured 录屏类型与 expected_real_evidence 不匹配;"
                        "不能用无关录屏给当前镜头的真实证据要求背书。"
                    ),
                    "expected_real_evidence": scene.get("expected_real_evidence"),
                    "materialized_evidence_types": sorted(
                        _captured_recording_evidence_types(verifiable_refs)
                    ),
                }
            )
        else:
            intent_blocker = _recording_evidence_intent_blocker_for_render(
                scene,
                verifiable_refs,
            )
            if intent_blocker is not None:
                blockers.append({"scene_id": scene_id, **intent_blocker})
            else:
                duration_blocker = _recording_evidence_duration_blocker_for_render(
                    project,
                    scene,
                    verifiable_refs,
                )
                if duration_blocker is not None:
                    blockers.append({"scene_id": scene_id, **duration_blocker})
    return [
        {key: value for key, value in blocker.items() if value not in (None, "", [])}
        for blocker in blockers
    ]


def _scene_requires_visual_evidence(scene: dict[str, Any]) -> bool:
    if scene.get("requires_real_evidence_asset") is True:
        return True
    recipe_id = _asset_recipe_id_for_render(scene)
    return recipe_id in ASSET_RECIPE_EVIDENCE_TYPES


def _scene_requires_captured_recording_evidence(scene: dict[str, Any]) -> bool:
    recipe_id = _asset_recipe_id_for_render(scene)
    if recipe_id in ASSET_RECIPE_EVIDENCE_TYPES:
        return True
    if scene.get("requires_real_evidence_asset") is not True:
        return False
    profile = _scene_profile_for_render(scene)
    if profile in EVIDENCE_MATERIALIZATION_PROFILES:
        return True
    expected = scene.get("expected_real_evidence")
    if isinstance(expected, list):
        expected_text = " ".join(str(item) for item in expected)
    else:
        expected_text = str(expected or "")
    lowered = expected_text.lower()
    return any(
        keyword in lowered or keyword in expected_text
        for keyword in RECORDING_EVIDENCE_KEYWORDS
    )


def _evidence_refs_match_expected_for_render(
    scene: dict[str, Any],
    refs: list[dict[str, Any]],
) -> bool:
    expected_groups = _expected_recording_evidence_type_groups_for_render(scene)
    if not expected_groups:
        return True
    materialized_types = _captured_recording_evidence_types(refs)
    return all(materialized_types & group for group in expected_groups)


def _recording_evidence_intent_blocker_for_render(
    scene: dict[str, Any],
    refs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    marker_groups = _recording_intent_marker_groups_for_render(scene)
    if not marker_groups:
        return None
    recording_refs = [ref for ref in refs if _evidence_ref_is_captured_recording(ref)]
    if not recording_refs:
        return None
    task_texts = [
        task_text
        for task_text in (
            _recording_task_intent_text_for_render(ref) for ref in recording_refs
        )
        if task_text
    ]
    if task_texts and any(
        _recording_task_matches_marker_groups_for_render(task_text, marker_groups)
        for task_text in task_texts
    ):
        return None
    return {
        "release_blocker_code": "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE",
        "release_blocker_zh": (
            "分镜绑定的真实录屏缺少与本镜 expected_real_evidence / asset_recipe_id "
            "匹配的脱敏任务意图;不能只靠录屏 evidence 类型和 ffprobe 给发布级"
            "实证镜头背书。"
        ),
        "expected_real_evidence": scene.get("expected_real_evidence"),
        "recording_intent_marker_groups": [list(group) for group in marker_groups],
    }


def _recording_intent_marker_groups_for_render(
    scene: dict[str, Any],
) -> list[tuple[str, ...]]:
    for key in _recording_intent_scene_keys_for_render(scene):
        groups = RECORDING_INTENT_MARKER_GROUPS_BY_SCENE_KEY.get(key)
        if groups:
            return [tuple(group) for group in groups]
        if key in ASSET_RECIPE_EVIDENCE_TYPES:
            return []
    expected_text = _expected_evidence_text_for_render(scene.get("expected_real_evidence"))
    lowered = expected_text.lower()
    for needles, groups in RECORDING_INTENT_EXPECTED_GROUPS:
        if any(str(needle).lower() in lowered for needle in needles):
            return [tuple(group) for group in groups]
    return []


def _recording_intent_scene_keys_for_render(scene: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("asset_recipe_id", "blueprint_id", "visual_archetype", "template_id"):
        value = str(scene.get(key) or "").strip()
        if value:
            values.append(value)
    for container_key in ("asset_strategy_v2", "director_knowledge_refs"):
        container = scene.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in (
            "asset_recipe_id",
            "blueprint_id",
            "visual_archetype",
            "template_id",
        ):
            value = str(container.get(key) or "").strip()
            if value:
                values.append(value)
    return values


def _expected_evidence_text_for_render(expected: object) -> str:
    if isinstance(expected, list):
        return " ".join(str(item) for item in expected)
    return str(expected or "")


def _recording_task_intent_text_for_render(ref: dict[str, Any]) -> str:
    parts = [
        str(ref.get("recording_task_redacted") or "").strip(),
        str(ref.get("task_redacted") or "").strip(),
        str(ref.get("command_redacted") or "").strip(),
        str(ref.get("source_uri") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def _recording_task_matches_marker_groups_for_render(
    task_text: str,
    marker_groups: list[tuple[str, ...]],
) -> bool:
    lowered = task_text.lower()
    for group in marker_groups:
        if not any(str(marker).lower() in lowered for marker in group):
            return False
    return True


def _recording_evidence_duration_blocker_for_render(
    project: ProjectRef,
    scene: dict[str, Any],
    refs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    recording_refs = [ref for ref in refs if _evidence_ref_is_captured_recording(ref)]
    if not recording_refs:
        return None
    min_duration = _minimum_recording_evidence_duration_for_render(
        _float_time(scene.get("duration_sec"))
    )
    saw_duration = False
    measured_durations: list[float] = []
    for ref in recording_refs:
        duration = _evidence_clip_duration_sec_for_render(project, ref)
        if duration is None:
            continue
        saw_duration = True
        measured_durations.append(duration)
        if duration + SCENE_VIDEO_DURATION_TOLERANCE_SEC >= min_duration:
            return None
    if saw_duration:
        return {
            "release_blocker_code": "RELEASE_SCENE_EVIDENCE_RECORDING_TOO_SHORT",
            "release_blocker_zh": (
                "分镜绑定的真实录屏证据过短;"
                f"至少需要 {min_duration:.1f}s 的可验证录屏支撑当前镜头,"
                "不能用瞬间闪屏或极短片段给发布级证据镜头背书。"
            ),
            "minimum_recording_duration_sec": round(min_duration, 3),
            "measured_recording_duration_sec": [
                round(duration, 3) for duration in measured_durations
            ],
            "expected_real_evidence": scene.get("expected_real_evidence"),
        }
    return {
        "release_blocker_code": "RELEASE_SCENE_EVIDENCE_RECORDING_DURATION_NOT_VERIFIABLE",
        "release_blocker_zh": (
            "分镜绑定的真实录屏证据虽有视频流,但 ffprobe 未能读取时长;"
            "无法确认录屏足够支撑当前镜头。"
        ),
        "minimum_recording_duration_sec": round(min_duration, 3),
        "expected_real_evidence": scene.get("expected_real_evidence"),
    }


def _minimum_recording_evidence_duration_for_render(
    scene_duration_sec: float | None,
) -> float:
    if scene_duration_sec is None:
        return EVIDENCE_RECORDING_MIN_DURATION_SEC
    return max(
        EVIDENCE_RECORDING_MIN_DURATION_SEC,
        scene_duration_sec * EVIDENCE_RECORDING_MIN_SCENE_RATIO,
    )


def _evidence_clip_duration_sec_for_render(
    project: ProjectRef,
    ref: dict[str, Any],
) -> float | None:
    for key in ("evidence_clip_duration_sec", "source_video_duration_sec", "duration_sec"):
        duration = _float_time(ref.get(key))
        if duration is not None:
            return max(duration, 0.0)
    resolved = _evidence_clip_project_path_for_render(project, ref)
    if resolved is None:
        return None
    return _ffprobe_media_duration_sec_for_render(resolved)


def _evidence_clip_project_path_for_render(
    project: ProjectRef,
    ref: dict[str, Any],
) -> Path | None:
    raw_path = ref.get("evidence_clip_path") or ref.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = Path(raw_path)
    try:
        resolved = resolve_inside(project.path, path if path.is_absolute() else project.path / path)
    except LingjianError:
        return None
    return resolved if resolved.is_file() else None


def _ffprobe_media_duration_sec_for_render(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return None
    media_format = payload.get("format")
    if not isinstance(media_format, dict):
        return None
    duration = _float_time(media_format.get("duration"))
    if duration is None:
        return None
    return max(duration, 0.0)


def _expected_recording_evidence_type_groups_for_render(
    scene: dict[str, Any],
) -> list[set[str]]:
    groups: list[set[str]] = []
    recipe_id = _asset_recipe_id_for_render(scene)
    if recipe_id in ASSET_RECIPE_EVIDENCE_TYPES:
        return [set(ASSET_RECIPE_EVIDENCE_TYPES[recipe_id])]
    expected = scene.get("expected_real_evidence")
    if isinstance(expected, list):
        expected_text = " ".join(str(item) for item in expected)
    else:
        expected_text = str(expected or "")
    lowered = expected_text.lower()
    for needles, evidence_types in RECORDING_EVIDENCE_EXPECTED_TYPE_GROUPS:
        if any(needle in lowered or needle in expected_text for needle in needles):
            groups.append(set(evidence_types))
    return groups


def _asset_recipe_id_for_render(scene: dict[str, Any]) -> str:
    direct = str(scene.get("asset_recipe_id") or "").strip()
    if direct:
        return direct
    strategy = scene.get("asset_strategy_v2")
    if isinstance(strategy, dict):
        return str(strategy.get("asset_recipe_id") or "").strip()
    return ""


def _captured_recording_evidence_types(refs: list[dict[str, Any]]) -> set[str]:
    return {
        str(ref.get("evidence_type") or ref.get("type") or "").strip()
        for ref in refs
        if _evidence_ref_is_captured_recording(ref)
        and str(ref.get("evidence_type") or ref.get("type") or "").strip()
    }


def _scene_profile_for_render(scene: dict[str, Any]) -> str:
    direct = str(scene.get("profile") or scene.get("profile_key") or "").strip()
    if direct:
        return direct
    refs = scene.get("director_knowledge_refs")
    if isinstance(refs, dict) and refs.get("profile"):
        return str(refs["profile"])
    strategy = scene.get("asset_strategy_v2")
    if isinstance(strategy, dict) and strategy.get("profile"):
        return str(strategy["profile"])
    return ""


def _render_scene_id(scene: dict[str, Any]) -> str:
    return str(scene.get("scene_id") or scene.get("id") or "")


def _evidence_asset_lookup(evidence_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for asset in evidence_manifest.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        asset_id = _evidence_ref_id(asset)
        if asset_id:
            lookup[asset_id] = asset
    return lookup


def _evidence_ref_id(ref: dict[str, Any]) -> str:
    return str(ref.get("id") or ref.get("asset_id") or "").strip()


def _merged_evidence_ref(
    ref: dict[str, Any],
    lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    ref_id = _evidence_ref_id(ref)
    return {**lookup.get(ref_id, {}), **ref}


def _evidence_ref_targets_other_scene(ref: dict[str, Any], scene_id: str) -> bool:
    target_scene_id = str(ref.get("target_scene_id") or "").strip()
    return bool(target_scene_id and scene_id and target_scene_id != scene_id)


def _captured_dynamic_evidence_missing_target(ref: dict[str, Any]) -> bool:
    if str(ref.get("evidence_clip_status") or "") != "captured":
        return False
    if str(ref.get("target_scene_id") or "").strip():
        return False
    evidence_type = str(ref.get("evidence_type") or ref.get("type") or "")
    visual_source = str(ref.get("evidence_visual_source") or "")
    return (
        evidence_type
        in {
            "codex_operation_recording",
            "screen_recording_capture",
            "terminal_recording_capture",
            "web_recording_capture",
        }
        or visual_source
        in {
            "codex_operation_video",
            "screen_recording",
            "terminal_recording",
            "web_recording",
        }
    )


def _evidence_ref_is_captured_recording(ref: dict[str, Any]) -> bool:
    if str(ref.get("evidence_clip_status") or "") != "captured":
        return False
    evidence_type = str(ref.get("evidence_type") or ref.get("type") or "").strip()
    visual_source = str(ref.get("evidence_visual_source") or "").strip()
    return (
        evidence_type in SOURCE_VIDEO_EVIDENCE_TYPES
        or visual_source in RECORDING_EVIDENCE_VISUAL_SOURCES
    )


def _evidence_video_is_verifiable(project: ProjectRef, ref: dict[str, Any]) -> bool:
    if ref.get("evidence_clip_status") not in {"generated", "captured"}:
        return False
    raw_path = ref.get("evidence_clip_path") or ref.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return False
    path = Path(raw_path)
    try:
        resolved = resolve_inside(project.path, path if path.is_absolute() else project.path / path)
    except LingjianError:
        return False
    if not resolved.exists():
        return False
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return False
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "json",
                str(resolved),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return any(
        isinstance(stream, dict) and stream.get("codec_type") == "video"
        for stream in payload.get("streams", [])
    )


def render_project(
    project: ProjectRef,
    platform: str,
    language: str,
    ratio: str,
    mode: RenderMode = "preview",
    real_preview: bool = False,
    strict: bool = False,
) -> RenderResult:
    platform = safe_segment(platform, "platform")
    safe_segment(language, "language")
    safe_segment(ratio, "ratio")
    gate_error = validate_render_gate(project)
    if gate_error:
        raise LingjianError(
            gate_error.error_code,
            gate_error.message_zh,
            gate_error.hint,
            gate_error.details,
        )

    providers = _used_providers(project)
    if mode == "release" and any(provider["is_mock"] for provider in providers):
        raise LingjianError(
            "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE",
            "mock provider 不能用于正式发布。",
            "请配置真实 LLM/TTS provider 后重试。",
        )
    if mode == "release" and (not shutil.which("ffmpeg") or not shutil.which("ffprobe")):
        raise LingjianError(
            "RELEASE_RENDER_REQUIRES_FFMPEG",
            "正式发布渲染必须可调用 FFmpeg 和 ffprobe。",
            "请安装 FFmpeg/ffprobe 后重新执行 release render。",
        )

    render_dir = resolve_inside(project.path, project.path / "renders" / mode / platform)
    render_dir.mkdir(parents=True, exist_ok=True)
    video_path = render_dir / "video.mp4"
    visual_meta: dict[str, Any] = {}
    audio_mix_meta = _audio_mix_manifest(project)
    visual_scenes = _visual_plan_scenes(project)
    visual_plan_meta = _visual_plan_manifest_metadata(project)
    if mode == "release":
        blocked_visual_scenes = _non_publish_grade_visual_scenes(visual_scenes)
        if blocked_visual_scenes:
            raise LingjianError(
                "RELEASE_VISUAL_ASSET_NOT_PUBLISH_GRADE",
                "画面分镜仍包含非发布级动态素材。",
                (
                    "请先按 evidence_collection_checklist.md 补齐真实动态视频素材,"
                    "重新审核画面分镜后再执行 release render。"
                ),
                {"scenes": blocked_visual_scenes},
            )
        if visual_scenes:
            visual_meta = _render_visual_plan_video(project, ratio, video_path, visual_scenes)
            audio_mix_meta = visual_meta.get("audio_mix", audio_mix_meta)
        else:
            audio_path, audio_mix_meta = _render_release_audio(project, render_dir)
            _render_ffmpeg_card_video(
                project,
                ratio,
                video_path,
                include_audio=True,
                audio_path=audio_path,
            )
        if video_path.read_bytes() == STUB_VIDEO_BYTES:
            raise LingjianError(
                "RELEASE_VIDEO_IS_STUB",
                "release 视频不能是离线 stub。",
                "请检查 release 渲染路径是否实际调用 FFmpeg。",
            )
    elif real_preview:
        if not shutil.which("ffmpeg"):
            raise LingjianError(
                "REAL_PREVIEW_RENDER_REQUIRES_FFMPEG",
                "--real 预览渲染必须可调用 FFmpeg。",
                (
                    "请安装 FFmpeg 或把 ffmpeg 加入 PATH 后重试;"
                    "未加 --real 的预览才允许生成 stub 占位。"
                ),
            )
        if visual_scenes:
            visual_meta = _render_visual_plan_video(project, ratio, video_path, visual_scenes)
        else:
            _render_ffmpeg_card_video(project, ratio, video_path)
    else:
        video_path.write_bytes(STUB_VIDEO_BYTES)
    manifest = {
        "mode": mode,
        "platform": platform,
        "language": language,
        "ratio": ratio,
        "video_path": str(video_path.relative_to(project.path)),
        "providers": providers,
        "audio_mix": audio_mix_meta,
        "visual_evidence_assets": load_evidence_assets(project),
        **visual_plan_meta,
        **visual_meta,
    }
    if mode == "release":
        manifest["expected_duration_sec"] = round(_release_duration(project), 3)
    manifest_path = render_dir / "render_manifest.json"
    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    if mode == "release" and strict:
        caption_blockers = _release_caption_timing_blockers(manifest)
        if caption_blockers:
            raise LingjianError(
                "RELEASE_CAPTION_TIMING_NOT_READY",
                "release strict 渲染发现字幕 timing 仍不可发布。",
                (
                    "请按 render_manifest.json 中每镜 caption_timing 的恢复动作补齐"
                    " voice_plan caption_cues,重新审阅 voice 后再执行 release strict render。"
                ),
                {
                    "render_manifest": str(manifest_path.relative_to(project.path)),
                    "blockers": caption_blockers,
                },
            )
        audio_blockers = _release_audio_mix_blockers(manifest)
        if audio_blockers:
            raise LingjianError(
                "RELEASE_AUDIO_MIX_NOT_READY",
                "release strict 渲染发现 BGM/SFX 声音契约仍不可发布。",
                (
                    "请按 render_manifest.json 中 audio_mix 的 blockers 补齐项目内可验证的"
                    " BGM/SFX 音频资产,重新审阅 voice/visuals 后再执行 release strict render。"
                ),
                {
                    "render_manifest": str(manifest_path.relative_to(project.path)),
                    "blockers": audio_blockers,
                },
            )
        evidence_blockers = _release_visual_evidence_blockers(project, manifest)
        if evidence_blockers:
            raise LingjianError(
                "RELEASE_VISUAL_EVIDENCE_NOT_READY",
                "release strict 渲染发现真实动态 evidence 仍不可发布。",
                (
                    "请按 render_manifest.json 中的 evidence blockers 补齐同镜可验证的"
                    "动态证据素材,重新审阅 visuals 后再执行 release strict render。"
                ),
                {
                    "render_manifest": str(manifest_path.relative_to(project.path)),
                    "blockers": evidence_blockers,
                },
            )
    return RenderResult(mode, video_path, manifest_path)


def latest_render_manifest(project: ProjectRef, platform: str, mode: RenderMode) -> dict | None:
    platform = safe_segment(platform, "platform")
    path = resolve_inside(
        project.path,
        project.path / "renders" / mode / platform / "render_manifest.json",
    )
    if not path.exists():
        return None
    return read_json(path)
