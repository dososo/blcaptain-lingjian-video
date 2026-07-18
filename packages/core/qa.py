from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from packages.core.approvals import validate_render_gate
from packages.core.artifacts import read_json
from packages.core.director_contract import (
    director_diversity_findings,
    director_route_findings,
    host_generation_contract_findings,
    layout_quality_findings,
    motion_quality_findings,
)
from packages.core.errors import LingjianError
from packages.core.evidence_assets import (
    EVIDENCE_MATERIALIZATION_PROFILES,
    OPEN_SOURCE_MIN_EVIDENCE_TYPES,
    SOURCE_VIDEO_EXTENSIONS,
)
from packages.core.hash import canonical_json_hash
from packages.core.paths import resolve_inside
from packages.core.project import ProjectRef
from packages.core.rendering import (
    DEFAULT_BGM_TO_VOICE_DB,
    DEFAULT_SFX_GAIN_DB,
    STUB_VIDEO_BYTES,
    latest_render_manifest,
    xfade_name_for_transition_family,
)

FFPROBE_TIMEOUT_SEC = 20
SAMPLE_TTS_PROVIDER_IDS = {"kokoro_zh_tts", "piper_cli", "macos_say", "espeak_ng"}
OPEN_SOURCE_NON_TEXT_EVIDENCE_SOURCES = {
    "source_image",
    "terminal_transcript",
    "web_recording_video",
    "terminal_recording_video",
    "codex_operation_video",
    "screen_recording_video",
}
OPEN_SOURCE_RECORDING_EVIDENCE_SOURCES = {
    "web_recording_video",
    "terminal_recording_video",
    "codex_operation_video",
    "screen_recording_video",
}
OPEN_SOURCE_RECORDING_EVIDENCE_TYPES = {
    "web_recording_capture",
    "terminal_recording_capture",
    "codex_operation_recording",
    "screen_recording_capture",
}
APPROVAL_ARTIFACTS = {
    "script": "artifacts/script.json",
    "voice": "artifacts/voice_plan.json",
    "visuals": "artifacts/visual_plan.json",
}
OPEN_SOURCE_EVIDENCE_TYPE_GROUPS = (
    (
        ("github",),
        {"github_repo", "web_recording_capture", "screenshot_capture"},
    ),
    (
        ("readme",),
        {"readme_install_entry"},
    ),
    (
        ("codex",),
        {"codex_operation_recording", "web_recording_capture", "screenshot_capture"},
    ),
    (
        ("terminal", "终端"),
        {
            "terminal_log_capture",
            "terminal_recording_capture",
            "qa_report_artifact",
            "render_manifest_capture",
        },
    ),
    (
        ("qa",),
        {"qa_report_artifact"},
    ),
    (
        ("export", "导出"),
        {"export_package_capture"},
    ),
    (
        ("render_manifest",),
        {"render_manifest_capture"},
    ),
)
PROFILE_EVIDENCE_TYPE_GROUPS = (
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
        {
            "product_interface_capture",
            "product_ui_capture",
            "product_demo_capture",
            "screen_recording_capture",
        },
    ),
    (
        ("教程", "教学", "步骤", "操作步骤", "tutorial", "guide", "step"),
        {
            "tutorial_step_capture",
            "terminal_recording_capture",
            "screen_recording_capture",
        },
    ),
    (
        ("评测", "测评", "对比", "测试结果", "review", "comparison"),
        {
            "review_comparison_capture",
            "screen_recording_capture",
        },
    ),
    (
        ("商品", "电商", "带货", "下单", "购买", "权益", "价格"),
        {
            "ecommerce_product_capture",
            "product_demo_capture",
            "screen_recording_capture",
        },
    ),
)
OPEN_SOURCE_RECORDING_EVIDENCE_TYPE_GROUPS = (
    (
        ("github", "仓库"),
        {"web_recording_capture", "screen_recording_capture"},
    ),
    (
        ("readme", "文档"),
        {"web_recording_capture", "terminal_recording_capture", "screen_recording_capture"},
    ),
    (
        ("codex",),
        {"codex_operation_recording", "screen_recording_capture"},
    ),
    (
        ("terminal", "终端", "命令"),
        {"terminal_recording_capture", "screen_recording_capture"},
    ),
    (
        ("qa", "验证", "测试"),
        {
            "terminal_recording_capture",
            "codex_operation_recording",
            "screen_recording_capture",
        },
    ),
    (
        ("export", "导出", "render_manifest"),
        {
            "terminal_recording_capture",
            "codex_operation_recording",
            "screen_recording_capture",
        },
    ),
)
PROFILE_CAPTURED_EVIDENCE_TYPES = frozenset(
    evidence_type
    for _, evidence_types in PROFILE_EVIDENCE_TYPE_GROUPS
    for evidence_type in evidence_types
)
CAPTURED_DYNAMIC_EVIDENCE_TYPES = frozenset(
    (*OPEN_SOURCE_RECORDING_EVIDENCE_TYPES, *PROFILE_CAPTURED_EVIDENCE_TYPES)
)
STOCK_IMAGE_ASSET_ORIGINS = {
    "stock_image",
    "public_stock_image",
    "free_stock_image",
    "free_stock_library",
    "cc0_stock_library",
}
STOCK_IMAGE_LICENSE_VERIFIED_STATUSES = {
    "verified",
    "confirmed",
    "approved",
    "cc0",
    "public_domain",
    "public-domain",
    "license_verified",
    "user_verified",
    "user_confirmed",
}
SCREEN_RECORDING_CONSENT_EVIDENCE_TYPES = {
    "codex_operation_recording",
}
SCREEN_RECORDING_CONSENT_VISUAL_SOURCES = {
    "codex_operation_video",
    "screen_recording_video",
}
SCREEN_RECORDING_CONSENT_ROLES = {
    "codex",
    "codex_operation",
    "codex_recording",
    "screen",
    "screen_capture",
    "screen_recording",
}
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
FRAME_SAMPLE_WIDTH = 90
FRAME_SAMPLE_HEIGHT = 160
VISUAL_FINGERPRINT_GRID = 8
VISUAL_FINGERPRINT_MAX_HAMMING_DISTANCE = 4
TRANSITION_TIMING_TOLERANCE_SEC = 0.1
TRANSITION_MIN_VISIBLE_SEC = 0.12
LAYOUT_REFERENCE_WIDTH = 1080
LAYOUT_REFERENCE_HEIGHT = 1920
SUBTITLE_CONTRAST_MIN = 24.0
CAPTION_SAFE_START_RATIO = 0.72
CAPTION_SAFE_END_RATIO = 0.92
CAPTION_PIXEL_MAX_SAMPLES = 12
CAPTION_LEAK_MIN_CONTRAST = 120.0
CAPTION_LEAK_MIN_DARK_RATIO = 0.24
CAPTION_LEAK_MIN_BRIGHT_RATIO = 0.025
FRAME_MOTION_DELTA_MIN = 3.0
FRAME_MOTION_SEGMENT_DELTA_MIN = 1.5
TRANSITION_PIXEL_DELTA_MIN = 1.5
SCENE_VIDEO_MIN_DURATION_RATIO = 0.8
SCENE_VIDEO_DURATION_TOLERANCE_SEC = 0.25
EVIDENCE_RECORDING_MIN_DURATION_SEC = 1.5
EVIDENCE_RECORDING_MIN_SCENE_RATIO = 0.5
BGM_MAX_RELATIVE_DB = -12.0
SFX_MAX_PER_10_SEC = 6.0
SFX_MAX_GAIN_DB = -6.0
SFX_TIMING_TOLERANCE_SEC = 0.1
SFX_VISUAL_ACTION_TIMING_TOLERANCE_SEC = 0.35
SFX_EVENT_MARKER_FIELDS = ("cue_id", "visual_event", "action", "purpose")
SCENE_ACTION_TIME_FIELDS = (
    "time_sec",
    "local_at_sec",
    "at_sec",
    "timestamp_sec",
    "t_sec",
    "time",
    "at",
)
AUDIO_VISUAL_ALIGNMENT_EVIDENCE_FIELDS = (
    "evidence",
    "evidence_zh",
    "notes",
    "proof",
    "method",
    "verified_by",
    "reviewed_by",
    "evidence_refs",
)
AUDIO_VISUAL_ALIGNMENT_TEXT_EVIDENCE_FIELDS = (
    "evidence",
    "evidence_zh",
    "notes",
    "proof",
    "method",
    "verified_by",
    "reviewed_by",
)
HOOK_VISIBLE_ANCHOR_TERMS = (
    "一句话",
    "怎么",
    "为什么",
    "别",
    "不再",
    "解决",
    "痛点",
    "结果",
    "效果",
    "收益",
    "反差",
    "小白",
    "关注",
    "star",
    "收藏",
    "开源",
    "卡点",
    "问题",
    "看完",
    "马上",
    "先看",
)
SCENE_ACTION_MARKER_FIELDS = (
    "id",
    "cue_id",
    "event_id",
    "visual_event",
    "action",
    "purpose",
    "label",
    "name",
)
SCENE_ACTION_MARKER_CONTAINERS = (
    "visual_events",
    "keyframes",
    "motion_beats",
    "animation_beats",
    "action_markers",
    "sfx_points",
    "sound_cues",
)
SCENE_ACTION_MARKER_GROUPS = (
    "director_review_sheet_v2",
    "director_review_sheet",
    "director_board",
    "motion_intent",
    "motion_spec",
)
FINAL_AUDIO_MEAN_MIN_DB = -34.0
FINAL_AUDIO_MEAN_MAX_DB = -10.0
FINAL_AUDIO_PEAK_MIN_DB = -28.0
FINAL_AUDIO_PEAK_MAX_DB = -0.2
FINAL_AUDIO_DYNAMIC_RANGE_MIN_DB = 4.0
FINAL_AUDIO_LUFS_MIN = -28.0
FINAL_AUDIO_LUFS_MAX = -10.0
RELEASE_DURATION_TOLERANCE_RATIO = 0.04
RELEASE_DURATION_MIN_TOLERANCE_SEC = 0.75
RELEASE_DURATION_MAX_TOLERANCE_SEC = 1.5
CAPTION_MAX_CUE_SEC = 2.2
CAPTION_MAX_TOTAL_CHARS = 16
CAPTION_MAX_LINE_CHARS = 12
CAPTION_MAX_READING_UNITS_PER_SEC = 12.0
CAPTION_SCENE_END_TOLERANCE_SEC = 0.1
CAPTION_CUE_OVERLAP_TOLERANCE_SEC = 0.02
CAPTION_VOICE_PLAN_MATCH_TOLERANCE_SEC = 0.03
VOICE_DURATION_ALIGNED_CAPTION_SOURCE = "voice_duration_aligned"
VOICE_DURATION_ALIGNED_TIMING_BASIS = "real_segment_duration"
VOICE_PLAN_BACKED_CAPTION_SOURCES = {
    "voice_segment",
    VOICE_DURATION_ALIGNED_CAPTION_SOURCE,
}
SCREEN_TEXT_DUPLICATE_MIN_UNITS = 10
SCREEN_TEXT_DUPLICATE_OVERLAP_RATIO = 0.8
SCREEN_TEXT_MAX_UNITS = 18
HOOK_MAX_FIRST_SCENE_SEC = 4.0
AUDIO_VISUAL_COMMON_TOKENS = {
    "一个",
    "这个",
    "可以",
    "用户",
    "视频",
    "短视频",
    "画面",
    "内容",
    "项目",
    "介绍",
    "发布",
    "展示",
    "镜头",
}
AUDIO_VISUAL_KEY_TERMS = (
    "灵剪",
    "codex",
    "github",
    "star",
    "readme",
    "qa",
    "ffprobe",
    "脚本",
    "配音",
    "分镜",
    "三审",
    "终端",
    "导出",
    "素材",
    "火山",
    "豆包",
    "hyperframes",
    "remotion",
    "开源",
)


def _latest_any_render_manifest(project: ProjectRef, mode: str) -> dict | None:
    render_root = project.path / "renders" / mode
    if not render_root.exists():
        return None
    for manifest_path in sorted(render_root.glob("*/render_manifest.json")):
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return None


def _current_visual_plan_sha256(project: ProjectRef) -> str | None:
    path = project.path / "artifacts" / "visual_plan.json"
    if not path.exists():
        return None
    visual_plan = read_json(path)
    return canonical_json_hash(visual_plan) if isinstance(visual_plan, dict) else None


def _check_render_manifest_freshness(
    project: ProjectRef, manifest: dict, report: QAReport, strict: bool
) -> bool:
    current_hash = _current_visual_plan_sha256(project)
    if current_hash is None:
        return False
    manifest_hash = str(manifest.get("visual_plan_sha256") or "")
    if manifest_hash == current_hash:
        return False
    _add_release_quality_issue(
        report,
        "RELEASE_RENDER_MANIFEST_STALE",
        "render_manifest.json 与当前 artifacts/visual_plan.json 不一致;"
        "请先重新执行 release render,再进行发布级 QA。",
        strict,
    )
    return True


@dataclass(slots=True)
class QAIssue:
    code: str
    severity: str
    message_zh: str


@dataclass(slots=True)
class QAReport:
    hard_failures: list[QAIssue] = field(default_factory=list)
    warnings: list[QAIssue] = field(default_factory=list)
    info: list[QAIssue] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def release_ready(self) -> bool:
        return not self.hard_failures


def _evidence_recovery_metadata(project: ProjectRef) -> dict:
    visual_plan_path = project.path / "artifacts" / "visual_plan.json"
    if not visual_plan_path.exists():
        return {}
    try:
        visual_plan = read_json(visual_plan_path)
    except (json.JSONDecodeError, OSError):
        return {}
    checklist = visual_plan.get("evidence_collection_checklist_v1")
    if not isinstance(checklist, dict):
        return {}
    blockers = []
    for item in checklist.get("items") or []:
        if not isinstance(item, dict):
            continue
        suggested_commands = [
            command_item
            for command_item in item.get("suggested_commands") or []
            if isinstance(command_item, dict)
            and str(command_item.get("command") or "").strip()
        ]
        first_command = suggested_commands[0] if suggested_commands else {}
        first_command_text = str(first_command.get("command") or "")
        fallback = _find_manual_evidence_fallback(suggested_commands)
        blockers.append(
            {
                "scene_id": item.get("scene_id"),
                "scene_number": item.get("scene_number"),
                "asset_recipe_id": item.get("asset_recipe_id"),
                "expected_evidence_types": item.get("expected_evidence_types") or [],
                "next_action_zh": item.get("next_action_zh")
                or item.get("action_zh")
                or "",
                "first_command": first_command.get("command"),
                "first_command_label_zh": first_command.get("label_zh"),
                "screen_recording_consent_required": bool(
                    item.get("screen_recording_consent_required")
                )
                or _command_requires_screen_recording(first_command_text),
                "privacy_notice_zh": item.get("privacy_notice_zh")
                or (
                    "这条命令会录制当前屏幕。只有在你确认当前屏幕没有私密信息、账号密钥、"
                    "聊天内容或不可公开素材时才执行;否则请先用手动录屏工具录好 mp4,"
                    "再执行 manual_fallback_command 导入同一镜头。"
                    if _command_requires_screen_recording(first_command_text)
                    else None
                ),
                "manual_fallback_command": item.get("manual_fallback_command")
                or ((fallback or {}).get("command")),
                "manual_fallback_note_zh": item.get("manual_fallback_note_zh")
                or ((fallback or {}).get("note_zh")),
            }
        )
    if not blockers:
        return {}
    return {
        "remaining_evidence_blockers": blockers,
        "evidence_collection_checklist_artifact": (
            "artifacts/evidence_collection_checklist.md"
        ),
    }


def _command_requires_screen_recording(command: str) -> bool:
    return "--allow-screen-recording" in command


def _find_manual_evidence_fallback(suggested_commands: list[dict]) -> dict | None:
    for command_item in suggested_commands:
        command = str(command_item.get("command") or "")
        if " lj ingest video " in command or command.startswith("uv run lj ingest video "):
            return command_item
    return None


def _current_visual_plan(project: ProjectRef) -> dict:
    visual_plan_path = project.path / "artifacts" / "visual_plan.json"
    if not visual_plan_path.exists():
        return {}
    try:
        visual_plan = read_json(visual_plan_path)
    except (json.JSONDecodeError, OSError):
        return {}
    return visual_plan if isinstance(visual_plan, dict) else {}


def _voice_plan_audio_assets(project: ProjectRef) -> dict:
    voice_plan = _release_voice_plan(project)
    if not isinstance(voice_plan, dict):
        return {}
    assets = voice_plan.get("audio_assets")
    return assets if isinstance(assets, dict) else {}


def _latest_release_manifest_for_audio_recovery(
    project: ProjectRef, platform: str
) -> dict | None:
    manifest = latest_render_manifest(project, platform, "release") or _latest_any_render_manifest(
        project, "release"
    )
    if not isinstance(manifest, dict):
        return None
    current_hash = _current_visual_plan_sha256(project)
    if current_hash is None:
        return manifest
    return manifest if str(manifest.get("visual_plan_sha256") or "") == current_hash else None


def _scene_label(scene: dict, index: int) -> str:
    return str(scene.get("scene_id") or scene.get("id") or f"s{index}")


def _scene_required_bgm_text(scene: dict) -> str:
    for text in _scene_bgm_texts(scene):
        normalized = _normalize_bgm_text(text)
        if not normalized or _bgm_text_declares_optional_or_none(normalized):
            continue
        if "bgm" in normalized or "音乐" in normalized or "配乐" in normalized:
            return str(text)
    return ""


def _audio_recovery_float_arg(value: float) -> str:
    rounded = round(float(value), 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _audio_ingest_command(
    project: ProjectRef,
    kind: str,
    *,
    scene_id: str = "",
    at_sec: float | None = None,
    action: str = "",
) -> str:
    placeholder = "把BGM文件拖到这里.wav" if kind == "bgm" else "把音效文件拖到这里.wav"
    args = [
        "uv",
        "run",
        "lj",
        "ingest",
        "audio",
        str(project.path),
        "--file",
        placeholder,
        "--kind",
        kind,
    ]
    if kind == "bgm":
        args.extend(["--bgm-to-voice-db", _audio_recovery_float_arg(DEFAULT_BGM_TO_VOICE_DB)])
    else:
        args.extend(
            [
                "--scene-id",
                scene_id,
                "--at-sec",
                _audio_recovery_float_arg(at_sec if at_sec is not None else 0.5),
                "--gain-db",
                _audio_recovery_float_arg(DEFAULT_SFX_GAIN_DB),
            ]
        )
        if action:
            args.extend(["--action", action])
    args.append("--json")
    return " ".join(shlex.quote(str(arg)) for arg in args)


def _audio_recovery_command_item(
    label_zh: str,
    command: str,
    note_zh: str,
) -> dict:
    return {
        "label_zh": label_zh,
        "command": command,
        "note_zh": note_zh,
    }


def _sfx_audio_recovery_timing(scene: dict, markers: list[str]) -> tuple[float, str]:
    marker_set = set(markers)
    for visual_markers, marker_time_sec in _scene_visual_action_timed_markers(scene):
        if _marker_sets_overlap(marker_set, visual_markers):
            return marker_time_sec, "matched_visual_action"
    duration_sec = _positive_float(scene.get("duration_sec"))
    if duration_sec is not None and duration_sec < 1.0:
        return max(duration_sec * 0.5, 0.0), "default_scene_midpoint"
    return 0.5, "default_first_beat"


def _voice_plan_bgm_asset_ready(project: ProjectRef, assets: dict) -> bool:
    bgm = assets.get("bgm")
    return isinstance(bgm, dict) and _audio_source_asset_is_verifiable(project, bgm.get("path"))


def _manifest_bgm_audio_ready(project: ProjectRef, manifest: dict | None) -> bool:
    if not isinstance(manifest, dict):
        return False
    mix = manifest.get("audio_mix")
    if not isinstance(mix, dict):
        return False
    return (
        mix.get("rendered") is True
        and bool(mix.get("bgm_present"))
        and _audio_source_asset_is_verifiable(project, mix.get("bgm_path"))
    )


def _voice_plan_sfx_asset_ready(project: ProjectRef, assets: dict, scene_id: str) -> bool:
    events = assets.get("sfx")
    if not isinstance(events, list):
        return False
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("scene_id") or "").strip() != scene_id:
            continue
        if _audio_source_asset_is_verifiable(project, event.get("path")):
            return True
    return False


def _manifest_sfx_audio_ready(
    project: ProjectRef, manifest: dict | None, scene_id: str
) -> bool:
    if not isinstance(manifest, dict):
        return False
    mix = manifest.get("audio_mix")
    if not isinstance(mix, dict) or mix.get("rendered") is not True:
        return False
    events = mix.get("sfx_events")
    if not isinstance(events, list):
        return False
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("scene_id") or "").strip() != scene_id:
            continue
        if _audio_source_asset_is_verifiable(project, event.get("path")):
            return True
    return False


def _audio_recovery_metadata(project: ProjectRef, platform: str) -> dict:
    visual_plan = _current_visual_plan(project)
    scenes = [scene for scene in visual_plan.get("scenes", []) if isinstance(scene, dict)]
    if not scenes:
        return {}
    audio_assets = _voice_plan_audio_assets(project)
    trusted_manifest = _latest_release_manifest_for_audio_recovery(project, platform)
    blockers: list[dict] = []

    bgm_scene_items = []
    for index, scene in enumerate(scenes, start=1):
        declared_bgm = _scene_required_bgm_text(scene)
        if not declared_bgm:
            continue
        bgm_scene_items.append(
            {
                "scene_id": _scene_label(scene, index),
                "scene_number": index,
                "declared_bgm": declared_bgm,
            }
        )
    if bgm_scene_items and not (
        _voice_plan_bgm_asset_ready(project, audio_assets)
        or _manifest_bgm_audio_ready(project, trusted_manifest)
    ):
        scene_ids = [item["scene_id"] for item in bgm_scene_items]
        bgm_command = _audio_ingest_command(project, "bgm")
        blockers.append(
            {
                "kind": "bgm",
                "scene_ids": scene_ids,
                "scenes": bgm_scene_items,
                "expected_audio_asset": "voice_plan.audio_assets.bgm.path",
                "accepted_formats": ["wav", "mp3", "m4a", "aac"],
                "first_command_label_zh": "导入 BGM 音频并写入 voice_plan",
                "first_command": bgm_command,
                "suggested_commands": [
                    _audio_recovery_command_item(
                        "导入 BGM 音频",
                        bgm_command,
                        "导入后需要重新审阅并批准 voice,再重跑 render/QA。",
                    )
                ],
                "next_action_zh": (
                    "分镜已声明需要 BGM;请提供项目内可 ffprobe 验证的 BGM 音频,"
                    "执行 first_command 写入 voice_plan.audio_assets.bgm.path,"
                    "或把分镜 BGM 明确改为可无/无 BGM 后重新审阅。"
                ),
            }
        )

    for index, scene in enumerate(scenes, start=1):
        scene_id = _scene_label(scene, index)
        markers = sorted(_scene_declared_sfx_markers(scene))
        if not markers:
            continue
        if _voice_plan_sfx_asset_ready(
            project, audio_assets, scene_id
        ) or _manifest_sfx_audio_ready(project, trusted_manifest, scene_id):
            continue
        suggested_action = markers[0]
        suggested_at_sec, timing_basis = _sfx_audio_recovery_timing(scene, markers)
        sfx_command = _audio_ingest_command(
            project,
            "sfx",
            scene_id=scene_id,
            at_sec=suggested_at_sec,
            action=suggested_action,
        )
        blockers.append(
            {
                "kind": "sfx",
                "scene_id": scene_id,
                "scene_number": index,
                "declared_sfx_markers": markers,
                "expected_audio_asset": "voice_plan.audio_assets.sfx[]",
                "accepted_formats": ["wav", "mp3", "m4a", "aac"],
                "suggested_at_sec": suggested_at_sec,
                "suggested_timing_basis": timing_basis,
                "suggested_action": suggested_action,
                "first_command_label_zh": "导入本镜 SFX 音效并绑定动作点",
                "first_command": sfx_command,
                "suggested_commands": [
                    _audio_recovery_command_item(
                        "导入本镜 SFX 音效",
                        sfx_command,
                        "如果实际动作点不在该时间,请调整 --at-sec 后再执行。",
                    )
                ],
                "timing_hint_zh": (
                    "已按分镜同名视觉动作时间点给出 --at-sec。"
                    if timing_basis == "matched_visual_action"
                    else "未找到同名视觉动作时间点,命令先给 0.5 秒附近的默认动作点;"
                    "请按真实画面动作调整 --at-sec。"
                ),
                "next_action_zh": (
                    f"第 {index} 镜分镜已声明动作音效;请提供同镜可 ffprobe 验证的 SFX "
                    "音频并执行 first_command 写入 voice_plan.audio_assets.sfx[],"
                    "包含 scene_id、path、at_sec、gain_db 和 action/purpose/visual_event,"
                    "或把该镜音效明确改为可无后重新审阅。"
                ),
            }
        )
    if not blockers:
        return {}
    return {
        "remaining_audio_asset_blockers": blockers,
        "audio_asset_recovery_notice_zh": (
            "BGM/SFX 已进入导演分镜,但还没有可验证音频素材或可信混音证据;"
            "QA 只暴露恢复动作,不会自动生成音乐或音效。"
        ),
    }


def audio_recovery_metadata(project: ProjectRef, platform: str = "douyin") -> dict:
    return _audio_recovery_metadata(project, platform)


def _approval_targets(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    requested = {str(target) for target in value}
    return [target for target in APPROVAL_ARTIFACTS if target in requested]


def _approval_command(project: ProjectRef, target: str) -> str:
    return (
        f"uv run lj approve {shlex.quote(target)} {shlex.quote(str(project.path))} "
        f"--approved-by {shlex.quote('你的名字')} --json"
    )


def _approval_command_items(project: ProjectRef, targets: list[str]) -> list[dict]:
    return [
        {
            "target": target,
            "artifact": APPROVAL_ARTIFACTS[target],
            "approval_command": _approval_command(project, target),
            "command": _approval_command(project, target),
        }
        for target in targets
    ]


def _approval_recovery_metadata(project: ProjectRef) -> dict:
    gate_error = validate_render_gate(project)
    if gate_error is None:
        return {}
    if gate_error.error_code not in {"APPROVAL_REQUIRED", "APPROVAL_STALE"}:
        return {}
    metadata: dict = {
        "approval_gate_error_code": gate_error.error_code,
        "approval_gate_message_zh": gate_error.message_zh,
        "approval_gate_hint_zh": gate_error.hint,
    }
    if gate_error.error_code == "APPROVAL_STALE":
        targets = _approval_targets(gate_error.details.get("stale"))
        if not targets:
            return metadata
        metadata.update(
            {
                "stale_approval_targets": targets,
                "stale_approval_commands": _approval_command_items(project, targets),
                "stale_approval_notice_zh": (
                    "这些审批对应的产物已经变更。QA 只能暴露恢复动作;"
                    "仍需用户重新审阅后手动批准,不能自动放行 release。"
                ),
            }
        )
        if "voice" in targets:
            metadata.update(
                {
                    "voice_reapproval_required": True,
                    "voice_approval_command": _approval_command(project, "voice"),
                    "voice_reapproval_message_zh": (
                        "voice_plan 已变更,需要重新试听或审阅配音与字幕节奏后再批准 voice。"
                    ),
                }
            )
        if "visuals" in targets:
            metadata.update(
                {
                    "visuals_reapproval_required": True,
                    "visuals_approval_command": _approval_command(project, "visuals"),
                }
            )
        return metadata

    targets = _approval_targets(gate_error.details.get("missing"))
    if not targets:
        return metadata
    metadata.update(
        {
            "missing_approval_targets": targets,
            "missing_approval_commands": _approval_command_items(project, targets),
            "approval_required_notice_zh": (
                "release 前必须完成缺失三审审批;QA 报告只提供恢复命令,"
                "不会替用户批准。"
            ),
        }
    )
    return metadata


def _check_approval_recovery(report: QAReport, strict: bool) -> None:
    targets = report.metadata.get("stale_approval_targets")
    if not isinstance(targets, list) or not targets:
        return
    target_text = "、".join(str(target) for target in targets)
    _add_release_quality_issue(
        report,
        "RELEASE_APPROVALS_STALE",
        f"三审审批已过期;涉及:{target_text};"
        "请按 stale_approval_commands 重新审阅并手动批准后再发布。",
        strict,
    )


def _check_remaining_evidence_blockers(report: QAReport, strict: bool) -> None:
    blockers = report.metadata.get("remaining_evidence_blockers")
    if not isinstance(blockers, list) or not blockers:
        return
    scene_labels = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        scene_label = blocker.get("scene_number") or blocker.get("scene_id")
        if scene_label:
            scene_labels.append(str(scene_label))
    scene_text = "、".join(scene_labels[:5])
    if len(scene_labels) > 5:
        scene_text += "等"
    suffix = f"涉及镜头:{scene_text};" if scene_text else ""
    _add_release_quality_issue(
        report,
        "RELEASE_VISUAL_EVIDENCE_BLOCKERS_REMAIN",
        "visual_plan 仍有真实动态 evidence 素材缺口;"
        f"{suffix}请先按 remaining_evidence_blockers 或 "
        "evidence_collection_checklist 补齐同镜录屏素材。",
        strict,
    )


def _check_remaining_audio_asset_blockers(report: QAReport, strict: bool) -> None:
    blockers = report.metadata.get("remaining_audio_asset_blockers")
    if not isinstance(blockers, list) or not blockers:
        return
    kinds = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        kind = str(blocker.get("kind") or "").strip()
        if kind and kind not in kinds:
            kinds.append(kind)
    kind_text = "、".join(kinds) if kinds else "BGM/SFX"
    _add_release_quality_issue(
        report,
        "RELEASE_AUDIO_ASSET_BLOCKERS_REMAIN",
        f"分镜已声明 {kind_text} 声音设计,但缺少可验证的项目内音频素材或可信混音证据;"
        "请先按 remaining_audio_asset_blockers 补齐 BGM/SFX,或在分镜中明确标为可无后重新审阅。",
        strict,
    )


def _check_voice_plan_caption_cue_readiness(
    project: ProjectRef, report: QAReport, strict: bool
) -> None:
    voice_plan = _release_voice_plan(project)
    if not isinstance(voice_plan, dict) or voice_plan.get("provider_is_mock") is True:
        return
    segments = voice_plan.get("segments")
    if not isinstance(segments, list) or not segments:
        return
    missing_scene_ids: list[str] = []
    invalid_scene_ids: list[str] = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            continue
        scene_id = str(segment.get("scene_id") or segment.get("id") or f"segment-{index}")
        cues = _voice_plan_segment_caption_cues(segment)
        if not cues:
            missing_scene_ids.append(scene_id)
            continue
        if not all(_voice_plan_caption_cue_is_readable(cue) for cue in cues):
            invalid_scene_ids.append(scene_id)
    if not missing_scene_ids and not invalid_scene_ids:
        return
    parts = []
    if missing_scene_ids:
        parts.append(f"缺失镜头:{'、'.join(missing_scene_ids[:5])}")
    if invalid_scene_ids:
        parts.append(f"不可读镜头:{'、'.join(invalid_scene_ids[:5])}")
    for scene_id in missing_scene_ids:
        _append_caption_timing_blocker(
            report,
            {"scene_id": scene_id},
            "RELEASE_VOICE_PLAN_CAPTION_CUES_MISSING",
            "请为该 voice segment 补齐 caption_cues 或 timed_captions,"
            "每条至少包含 text、start_sec、end_sec,并使用真实 TTS/ASR/人工校准时间。",
        )
    for scene_id in invalid_scene_ids:
        _append_caption_timing_blocker(
            report,
            {"scene_id": scene_id},
            "RELEASE_VOICE_PLAN_CAPTION_CUES_MISSING",
            "请修正该 voice segment 的 caption_cues/timed_captions,"
            "确保每条都有可读文本和合法起止时间。",
        )
    _add_release_quality_issue(
        report,
        "RELEASE_VOICE_PLAN_CAPTION_CUES_MISSING",
        "voice_plan 分段缺少可审计 timed caption cues;"
        f"{';'.join(parts)};"
        "不能等 render 临时估算字幕后再发现发布级字幕节奏不可验证。",
        strict,
    )


def _voice_plan_caption_cue_is_readable(cue: dict) -> bool:
    if not _caption_cue_text(cue):
        return False
    start = _caption_cue_time(cue, "start_sec", "start", "begin_sec", "begin")
    end = _caption_cue_time(cue, "end_sec", "end", "finish_sec", "finish")
    return start is not None and end is not None and end > start


def _append_caption_timing_blocker(
    report: QAReport,
    scene: dict,
    issue_code: str,
    next_action_zh: str,
) -> None:
    blockers = report.metadata.setdefault("remaining_caption_timing_blockers", [])
    if not isinstance(blockers, list):
        blockers = []
        report.metadata["remaining_caption_timing_blockers"] = blockers
    scene_id = str(scene.get("scene_id") or scene.get("id") or "").strip()
    caption_timing = scene.get("caption_timing")
    timing_source = ""
    timing_basis = ""
    if isinstance(caption_timing, dict):
        timing_source = str(caption_timing.get("source") or "").strip()
        timing_basis = str(caption_timing.get("timing_basis") or "").strip()
    cues = scene.get("caption_cues")
    cue_sources: list[str] = []
    cue_timing_bases: list[str] = []
    if isinstance(cues, list):
        cue_sources = sorted(
            {
                str(cue.get("source") or "").strip()
                for cue in cues
                if isinstance(cue, dict) and str(cue.get("source") or "").strip()
            }
        )
        cue_timing_bases = sorted(
            {
                str(cue.get("timing_basis") or "").strip()
                for cue in cues
                if isinstance(cue, dict)
                and str(cue.get("timing_basis") or "").strip()
            }
        )
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        if (
            blocker.get("scene_id") == scene_id
            and blocker.get("issue_code") == issue_code
        ):
            return
    item = {
        "scene_id": scene_id or None,
        "issue_code": issue_code,
        "target_field": "artifacts/voice_plan.json segments[].caption_cues",
        "accepted_timing_sources": [
            "voice_plan.caption_cues",
            "voice_plan.timed_captions",
            "ASR",
            "manual_timing",
        ],
        "required_timing_basis": VOICE_DURATION_ALIGNED_TIMING_BASIS,
        "next_action_zh": next_action_zh,
    }
    if timing_source:
        item["current_timing_source"] = timing_source
    if timing_basis:
        item["current_timing_basis"] = timing_basis
    if cue_sources:
        item["cue_sources"] = cue_sources
    if cue_timing_bases:
        item["cue_timing_bases"] = cue_timing_bases
    blockers.append(
        {key: value for key, value in item.items() if value not in (None, "", [])}
    )
    report.metadata["caption_timing_recovery_notice_zh"] = (
        "发布级 strict 不接受 estimated caption timing。请在 voice_plan 中补齐"
        "真实 TTS/ASR/人工校准的短句时间戳,再重新审阅 voice 并重新 release render。"
    )


def _qa_report_markdown(report: QAReport) -> str:
    lines = [
        "# QA Report",
        "",
        f"release_ready: {str(report.release_ready).lower()}",
        "",
    ]
    for title, issues in (
        ("Hard Failures", report.hard_failures),
        ("Warnings", report.warnings),
        ("Info", report.info),
    ):
        lines.extend([f"## {title}", ""])
        if not issues:
            lines.extend(["- 无", ""])
            continue
        for issue in issues:
            lines.append(f"- `{issue.code}`: {issue.message_zh}")
        lines.append("")
    stale_commands = report.metadata.get("stale_approval_commands")
    missing_commands = report.metadata.get("missing_approval_commands")
    if (
        isinstance(stale_commands, list)
        and stale_commands
        or isinstance(missing_commands, list)
        and missing_commands
    ):
        lines.extend(["## 审批恢复建议", ""])
        stale_targets = report.metadata.get("stale_approval_targets")
        if isinstance(stale_targets, list) and stale_targets:
            lines.append(f"- 已过期审批: `{', '.join(str(target) for target in stale_targets)}`")
        missing_targets = report.metadata.get("missing_approval_targets")
        if isinstance(missing_targets, list) and missing_targets:
            lines.append(f"- 缺失审批: `{', '.join(str(target) for target in missing_targets)}`")
        for command_item in (stale_commands or []) + (missing_commands or []):
            if not isinstance(command_item, dict):
                continue
            command = str(command_item.get("command") or "").strip()
            target = command_item.get("target") or "approval"
            artifact = command_item.get("artifact")
            if artifact:
                lines.append(f"- `{target}` 审阅产物: `{artifact}`")
            if command:
                lines.append(f"  - 重审命令: `{command}`")
        if report.metadata.get("voice_reapproval_message_zh"):
            lines.append(f"- {report.metadata['voice_reapproval_message_zh']}")
        lines.append("")
    blockers = report.metadata.get("remaining_evidence_blockers")
    if isinstance(blockers, list) and blockers:
        lines.extend(["## 真实动态证据素材恢复建议", ""])
        checklist = report.metadata.get("evidence_collection_checklist_artifact")
        if checklist:
            lines.append(f"- 采集清单: `{checklist}`")
        for index, blocker in enumerate(blockers, start=1):
            if not isinstance(blocker, dict):
                continue
            scene_label = blocker.get("scene_number") or blocker.get("scene_id") or index
            action = blocker.get("next_action_zh") or "补齐真实动态 evidence 素材。"
            lines.append(f"- 镜头 {scene_label}: {action}")
            if blocker.get("screen_recording_consent_required"):
                lines.append("  - 录屏前必须确认当前屏幕没有私密信息。")
            if blocker.get("first_command"):
                lines.append(f"  - 推荐命令: `{blocker['first_command']}`")
            if blocker.get("manual_fallback_command"):
                lines.append(f"  - 手动导入: `{blocker['manual_fallback_command']}`")
        lines.append("")
    audio_blockers = report.metadata.get("remaining_audio_asset_blockers")
    if isinstance(audio_blockers, list) and audio_blockers:
        lines.extend(["## BGM/SFX 声音素材恢复建议", ""])
        notice = report.metadata.get("audio_asset_recovery_notice_zh")
        if notice:
            lines.append(f"- {notice}")
        for index, blocker in enumerate(audio_blockers, start=1):
            if not isinstance(blocker, dict):
                continue
            kind = blocker.get("kind") or "audio"
            action = blocker.get("next_action_zh") or "补齐可验证的项目内声音素材。"
            expected = blocker.get("expected_audio_asset")
            scene_label = blocker.get("scene_number") or blocker.get("scene_id")
            if not scene_label:
                scene_ids = blocker.get("scene_ids")
                if isinstance(scene_ids, list) and scene_ids:
                    scene_label = ",".join(str(scene_id) for scene_id in scene_ids)
            prefix = f"- {kind}"
            if scene_label:
                prefix += f" / 镜头 {scene_label}"
            lines.append(f"{prefix}: {action}")
            if expected:
                lines.append(f"  - 目标字段: `{expected}`")
            formats = blocker.get("accepted_formats")
            if isinstance(formats, list) and formats:
                lines.append(f"  - 接受格式: `{', '.join(str(item) for item in formats)}`")
            if blocker.get("timing_hint_zh"):
                lines.append(f"  - 时间提示: {blocker['timing_hint_zh']}")
            if blocker.get("first_command"):
                label = blocker.get("first_command_label_zh") or "推荐命令"
                lines.append(f"  - {label}: `{blocker['first_command']}`")
            suggested_commands = blocker.get("suggested_commands")
            if isinstance(suggested_commands, list):
                for command_item in suggested_commands:
                    if not isinstance(command_item, dict):
                        continue
                    command = str(command_item.get("command") or "").strip()
                    if not command or command == blocker.get("first_command"):
                        continue
                    label = command_item.get("label_zh") or "备选命令"
                    lines.append(f"  - {label}: `{command}`")
        lines.append("")
    stock_blockers = report.metadata.get("remaining_stock_image_blockers")
    if isinstance(stock_blockers, list) and stock_blockers:
        lines.extend(["## 免费图库配图恢复建议", ""])
        for index, blocker in enumerate(stock_blockers, start=1):
            if not isinstance(blocker, dict):
                continue
            scene_label = blocker.get("scene_id") or index
            code = blocker.get("issue_code") or "stock_image"
            action = blocker.get("next_action_zh") or (
                "补齐用户授权、图库来源 URL、license 与 license 核验状态。"
            )
            lines.append(f"- 镜头 {scene_label} / `{code}`: {action}")
        lines.append("")
    caption_blockers = report.metadata.get("remaining_caption_timing_blockers")
    if isinstance(caption_blockers, list) and caption_blockers:
        lines.extend(["## 字幕 timing 恢复建议", ""])
        notice = report.metadata.get("caption_timing_recovery_notice_zh")
        if notice:
            lines.append(f"- {notice}")
        for index, blocker in enumerate(caption_blockers, start=1):
            if not isinstance(blocker, dict):
                continue
            scene_label = blocker.get("scene_id") or index
            code = blocker.get("issue_code") or "caption_timing"
            action = blocker.get("next_action_zh") or "补齐真实 timed caption cues。"
            lines.append(f"- 镜头 {scene_label} / `{code}`: {action}")
            target = blocker.get("target_field")
            if target:
                lines.append(f"  - 目标字段: `{target}`")
            current_source = blocker.get("current_timing_source")
            if current_source:
                lines.append(f"  - 当前 timing source: `{current_source}`")
            current_basis = blocker.get("current_timing_basis")
            if current_basis:
                lines.append(f"  - 当前 timing basis: `{current_basis}`")
            accepted = blocker.get("accepted_timing_sources")
            if isinstance(accepted, list) and accepted:
                lines.append(
                    f"  - 接受来源: `{', '.join(str(item) for item in accepted)}`"
                )
            required_basis = blocker.get("required_timing_basis")
            if required_basis:
                lines.append(f"  - voice_duration_aligned 需要: `{required_basis}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _media_streams_are_verifiable(path: Path) -> tuple[bool, bool]:
    if not shutil.which("ffprobe"):
        return False, False
    try:
        completed = subprocess.run(
            [
                "ffprobe",
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
            timeout=FFPROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return False, False
    if completed.returncode != 0:
        return False, False
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return False, False
    stream_types = {
        stream.get("codec_type")
        for stream in payload.get("streams", [])
        if isinstance(stream, dict)
    }
    return "video" in stream_types, "audio" in stream_types


def _media_duration_sec(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    try:
        completed = subprocess.run(
            [
                "ffprobe",
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
            timeout=FFPROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return None
    return _positive_float(payload.get("format", {}).get("duration"))


def _audio_volume_stats(path: Path) -> dict[str, float] | None:
    if not shutil.which("ffmpeg"):
        return None
    try:
        completed = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=FFPROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    output = "\n".join([completed.stdout or "", completed.stderr or ""])
    mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", output)
    peak_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", output)
    if not mean_match or not peak_match:
        return None
    return {
        "mean_volume_db": float(mean_match.group(1)),
        "peak_volume_db": float(peak_match.group(1)),
    }


def _audio_dynamic_stats(path: Path) -> dict[str, float] | None:
    if not shutil.which("ffmpeg"):
        return None
    try:
        completed = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-af",
                "astats=metadata=1:reset=1",
                "-f",
                "null",
                "-",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=FFPROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    output = "\n".join([completed.stdout or "", completed.stderr or ""])
    rms_levels = [
        float(match.group(1))
        for match in re.finditer(r"RMS level dB:\s*(-?\d+(?:\.\d+)?)", output)
    ]
    if len(rms_levels) < 2:
        return None
    return {
        "rms_dynamic_range_db": max(rms_levels) - min(rms_levels),
        "rms_window_count": float(len(rms_levels)),
    }


def _audio_lufs_stats(path: Path) -> dict[str, float] | None:
    if not shutil.which("ffmpeg"):
        return None
    try:
        completed = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-filter:a",
                "ebur128=peak=true",
                "-f",
                "null",
                "-",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=FFPROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    output = "\n".join([completed.stdout or "", completed.stderr or ""])
    lufs_values = [
        float(match.group(1))
        for match in re.finditer(r"\bI:\s*(-?\d+(?:\.\d+)?)\s*LUFS", output)
    ]
    if not lufs_values:
        return None
    return {"integrated_lufs": lufs_values[-1]}


def _positive_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _frame_sample_is_verifiable(path: Path) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    try:
        completed = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                "0.10",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-f",
                "null",
                "-",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=FFPROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def _sample_frame_rgb(path: Path, timestamp: str) -> bytes | None:
    if not shutil.which("ffmpeg"):
        return None
    try:
        completed = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                timestamp,
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                f"scale={FRAME_SAMPLE_WIDTH}:{FRAME_SAMPLE_HEIGHT}",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            capture_output=True,
            check=False,
            timeout=FFPROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    raw = completed.stdout
    if isinstance(raw, str):
        raw = raw.encode("latin1", errors="ignore")
    expected = FRAME_SAMPLE_WIDTH * FRAME_SAMPLE_HEIGHT * 3
    if len(raw) < expected:
        return None
    return raw[:expected]


def _sample_frame_luma_contrast(path: Path) -> float | None:
    raw = _sample_frame_rgb(path, "0.10")
    if raw is None:
        return None
    start_y = int(FRAME_SAMPLE_HEIGHT * CAPTION_SAFE_START_RATIO)
    end_y = int(FRAME_SAMPLE_HEIGHT * CAPTION_SAFE_END_RATIO)
    values: list[float] = []
    for y in range(start_y, end_y):
        row = y * FRAME_SAMPLE_WIDTH * 3
        for x in range(FRAME_SAMPLE_WIDTH):
            index = row + x * 3
            r, g, b = raw[index], raw[index + 1], raw[index + 2]
            values.append(0.2126 * r + 0.7152 * g + 0.0722 * b)
    if not values:
        return None
    return max(values) - min(values)


def _visual_fingerprint(path: Path) -> tuple[int, ...] | None:
    raw = _sample_frame_rgb(path, "0.70")
    if raw is None:
        return None
    cell_count = VISUAL_FINGERPRINT_GRID * VISUAL_FINGERPRINT_GRID
    totals = [0.0] * cell_count
    counts = [0] * cell_count
    for y in range(FRAME_SAMPLE_HEIGHT):
        cell_y = min(
            y * VISUAL_FINGERPRINT_GRID // FRAME_SAMPLE_HEIGHT,
            VISUAL_FINGERPRINT_GRID - 1,
        )
        row = y * FRAME_SAMPLE_WIDTH * 3
        for x in range(FRAME_SAMPLE_WIDTH):
            cell_x = min(
                x * VISUAL_FINGERPRINT_GRID // FRAME_SAMPLE_WIDTH,
                VISUAL_FINGERPRINT_GRID - 1,
            )
            cell = cell_y * VISUAL_FINGERPRINT_GRID + cell_x
            index = row + x * 3
            r, g, b = raw[index], raw[index + 1], raw[index + 2]
            totals[cell] += 0.2126 * r + 0.7152 * g + 0.0722 * b
            counts[cell] += 1
    if not any(counts):
        return None
    averages = [
        totals[index] / counts[index] if counts[index] else 0.0
        for index in range(cell_count)
    ]
    threshold = sum(averages) / len(averages)
    return tuple(1 if value > threshold else 0 for value in averages)


def _fingerprint_distance(first: tuple[int, ...], second: tuple[int, ...]) -> int:
    return sum(1 for left, right in zip(first, second, strict=True) if left != right)


def _sample_frame_has_caption_pixels_outside_safe_area(
    path: Path,
    timestamps: list[str] | None = None,
) -> bool | None:
    saw_frame = False
    for timestamp in timestamps or ["0.10"]:
        raw = _sample_frame_rgb(path, timestamp)
        if raw is None:
            continue
        saw_frame = True
        if _frame_has_caption_band_outside_safe_area(raw):
            return True
    return False if saw_frame else None


def _sample_frame_has_caption_pixels_in_safe_area(
    path: Path,
    timestamps: list[str] | None = None,
) -> bool | None:
    saw_frame = False
    for timestamp in timestamps or ["0.10"]:
        raw = _sample_frame_rgb(path, timestamp)
        if raw is None:
            continue
        saw_frame = True
        if _frame_has_caption_band_in_safe_area(raw):
            return True
    return False if saw_frame else None


def _sample_frame_has_caption_pixels_inside_subject_region(
    path: Path,
    scenes: list[dict],
    timestamps: list[str] | None = None,
) -> bool | None:
    saw_frame = False
    for timestamp in timestamps or ["0.10"]:
        raw = _sample_frame_rgb(path, timestamp)
        if raw is None:
            continue
        saw_frame = True
        if any(_frame_subject_region_contains_caption_overlay(raw, scene) for scene in scenes):
            return True
    return False if saw_frame else None


def _sample_frame_has_caption_pixels_inside_cta_region(
    path: Path,
    scenes: list[dict],
    timestamps: list[str] | None = None,
) -> bool | None:
    saw_frame = False
    for timestamp in timestamps or ["0.10"]:
        raw = _sample_frame_rgb(path, timestamp)
        if raw is None:
            continue
        saw_frame = True
        if any(_frame_cta_region_contains_caption_overlay(raw, scene) for scene in scenes):
            return True
    return False if saw_frame else None


def _caption_pixel_sample_timestamps(scenes: list[dict]) -> list[str]:
    timestamps: list[float] = [0.10]
    offset = 0.0
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_duration = _positive_float(scene.get("duration_sec"))
        cues = scene.get("caption_cues")
        max_cue_end = 0.0
        if isinstance(cues, list):
            for cue in cues:
                if not isinstance(cue, dict):
                    continue
                start_sec = _float_or_none(cue.get("start_sec"))
                end_sec = _float_or_none(cue.get("end_sec"))
                if start_sec is None or end_sec is None or end_sec <= start_sec:
                    continue
                midpoint = (start_sec + end_sec) / 2
                if scene_duration is not None:
                    midpoint = min(midpoint, scene_duration)
                timestamps.append(offset + max(midpoint, 0.0))
                max_cue_end = max(max_cue_end, end_sec)
        if scene_duration is not None:
            offset += scene_duration
        else:
            offset += max_cue_end
    normalized: list[str] = []
    seen: set[str] = set()
    for timestamp in timestamps:
        item = f"{max(timestamp, 0.01):.2f}"
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
        if len(normalized) >= CAPTION_PIXEL_MAX_SAMPLES:
            break
    return normalized


def _frame_has_caption_band_outside_safe_area(raw: bytes) -> bool:
    safe_start_y = int(FRAME_SAMPLE_HEIGHT * CAPTION_SAFE_START_RATIO)
    unsafe_start_y = int(FRAME_SAMPLE_HEIGHT * 0.18)
    unsafe_end_y = min(int(FRAME_SAMPLE_HEIGHT * 0.68), safe_start_y)
    band_height = max(int(FRAME_SAMPLE_HEIGHT * 0.10), 12)
    step = max(band_height // 3, 4)
    for y0 in range(unsafe_start_y, max(unsafe_start_y, unsafe_end_y - band_height) + 1, step):
        if _band_looks_like_caption_overlay(raw, y0, min(y0 + band_height, unsafe_end_y)):
            return True
    return False


def _frame_has_caption_band_in_safe_area(raw: bytes) -> bool:
    safe_start_y = int(FRAME_SAMPLE_HEIGHT * CAPTION_SAFE_START_RATIO)
    safe_end_y = int(FRAME_SAMPLE_HEIGHT * CAPTION_SAFE_END_RATIO)
    band_height = max(int(FRAME_SAMPLE_HEIGHT * 0.08), 10)
    step = max(band_height // 3, 4)
    end_limit = max(safe_start_y, safe_end_y - band_height)
    for top in range(safe_start_y, end_limit + 1, step):
        if _band_looks_like_caption_overlay(raw, top, min(top + band_height, safe_end_y)):
            return True
    if safe_end_y - safe_start_y < band_height:
        return _band_looks_like_caption_overlay(raw, safe_start_y, safe_end_y)
    return False


def _frame_subject_region_contains_caption_overlay(raw: bytes, scene: dict) -> bool:
    return any(
        _rect_region_contains_caption_overlay(raw, region)
        for region in _scene_subject_regions(scene)
    )


def _scene_caption_bboxes(scene: dict) -> list[dict]:
    bboxes: list[dict] = []
    for cue in scene.get("caption_cues") or []:
        if not isinstance(cue, dict):
            continue
        bbox = _coerce_rect(cue.get("caption_bbox"))
        if bbox is not None:
            bboxes.append(bbox)
    scene_bbox = _coerce_rect(scene.get("caption_render_region"))
    if scene_bbox is not None and not bboxes:
        bboxes.append(scene_bbox)
    return bboxes


def _caption_bbox_geometry_findings(scenes: list[dict]) -> dict[str, bool]:
    findings = {
        "has_caption_bbox": False,
        "outside_safe_area": False,
        "overlaps_subject": False,
        "overlaps_cta": False,
    }
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for bbox in _scene_caption_bboxes(scene):
            findings["has_caption_bbox"] = True
            if not _caption_bbox_inside_safe_area(bbox, scene):
                findings["outside_safe_area"] = True
            if any(_rects_overlap(bbox, region, scene) for region in _scene_subject_regions(scene)):
                findings["overlaps_subject"] = True
            if any(_rects_overlap(bbox, region, scene) for region in _scene_cta_regions(scene)):
                findings["overlaps_cta"] = True
    return findings


def _caption_bbox_inside_safe_area(bbox: dict, scene: dict) -> bool:
    _, y0, _, y1 = _rect_unit_bounds(bbox, scene)
    return y0 >= CAPTION_SAFE_START_RATIO and y1 <= CAPTION_SAFE_END_RATIO


def _rects_overlap(first: dict, second: dict, scene: dict) -> bool:
    first_x0, first_y0, first_x1, first_y1 = _rect_unit_bounds(first, scene)
    second_x0, second_y0, second_x1, second_y1 = _rect_unit_bounds(second, scene)
    return (
        first_x0 < second_x1
        and first_x1 > second_x0
        and first_y0 < second_y1
        and first_y1 > second_y0
    )


def _rect_unit_bounds(rect: dict, scene: dict) -> tuple[float, float, float, float]:
    width, height = _rect_canvas_dimensions(rect, scene)
    try:
        x = float(rect.get("x", 0))
        y = float(rect.get("y", 0))
        w = float(rect.get("w", 0))
        h = float(rect.get("h", 0))
    except (TypeError, ValueError):
        return 0.0, 0.0, 0.0, 0.0
    return (
        max(x / width, 0.0),
        max(y / height, 0.0),
        min((x + w) / width, 1.0),
        min((y + h) / height, 1.0),
    )


def _rect_canvas_dimensions(rect: dict, scene: dict) -> tuple[float, float]:
    width = _float_or_none(rect.get("canvas_width"))
    height = _float_or_none(rect.get("canvas_height"))
    if width and height:
        return width, height
    render_width = _float_or_none(scene.get("render_width"))
    render_height = _float_or_none(scene.get("render_height"))
    if render_width and render_height:
        return render_width, render_height
    dimensions = scene.get("render_dimensions")
    if isinstance(dimensions, dict):
        render_width = _float_or_none(dimensions.get("width"))
        render_height = _float_or_none(dimensions.get("height"))
        if render_width and render_height:
            return render_width, render_height
    return float(LAYOUT_REFERENCE_WIDTH), float(LAYOUT_REFERENCE_HEIGHT)


def _scene_subject_regions(scene: dict) -> list[dict]:
    regions: list[dict] = []
    contract = scene.get("layout_contract")
    if isinstance(contract, dict):
        for key in ("subjectRect", "subject_rect", "mainSubjectRect", "main_subject_rect"):
            rect = _coerce_rect(contract.get(key))
            if rect is not None:
                regions.append(rect)
    for sheet in _scene_review_sheets(scene):
        for key in (
            "subject_region",
            "subjectRegion",
            "main_subject_region",
            "mainSubjectRegion",
            "subjectRect",
            "subject_rect",
        ):
            rect = _coerce_rect(sheet.get(key))
            if rect is not None:
                regions.append(rect)
    return regions


def _rect_region_contains_caption_overlay(raw: bytes, rect: dict) -> bool:
    y0, y1 = _scaled_vertical_range(rect)
    if y1 <= y0:
        return False
    band_height = max(int(FRAME_SAMPLE_HEIGHT * 0.08), 10)
    step = max(band_height // 3, 4)
    end_limit = max(y0, y1 - band_height)
    for top in range(y0, end_limit + 1, step):
        if _band_looks_like_caption_overlay(raw, top, min(top + band_height, y1)):
            return True
    if y1 - y0 < band_height:
        return _band_looks_like_caption_overlay(raw, y0, y1)
    return False


def _frame_cta_region_contains_caption_overlay(raw: bytes, scene: dict) -> bool:
    return any(
        _rect_region_contains_caption_overlay(raw, region)
        for region in _scene_cta_regions(scene)
    )


def _scene_cta_regions(scene: dict) -> list[dict]:
    regions: list[dict] = []
    contract = scene.get("layout_contract")
    if isinstance(contract, dict):
        for key in ("ctaRect", "cta_rect", "callToActionRect", "buttonRect", "button_rect"):
            rect = _coerce_rect(contract.get(key))
            if rect is not None:
                regions.append(rect)
    for sheet in _scene_review_sheets(scene):
        for key in ("cta_region", "ctaRegion", "call_to_action_region", "button_region"):
            rect = _coerce_rect(sheet.get(key))
            if rect is not None:
                regions.append(rect)
    return regions


def _coerce_rect(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    if {"x", "y", "w", "h"}.issubset(value):
        return value
    for key in ("rect", "region", "ctaRect", "buttonRect"):
        nested = value.get(key)
        if isinstance(nested, dict) and {"x", "y", "w", "h"}.issubset(nested):
            return nested
    return None


def _scaled_vertical_range(rect: dict) -> tuple[int, int]:
    try:
        y = float(rect.get("y", 0))
        h = float(rect.get("h", 0))
    except (TypeError, ValueError):
        return 0, 0
    start = int(max(0, min(FRAME_SAMPLE_HEIGHT, y / LAYOUT_REFERENCE_HEIGHT * FRAME_SAMPLE_HEIGHT)))
    end = int(
        max(
            0,
            min(FRAME_SAMPLE_HEIGHT, (y + h) / LAYOUT_REFERENCE_HEIGHT * FRAME_SAMPLE_HEIGHT),
        )
    )
    return start, end


def _band_looks_like_caption_overlay(raw: bytes, start_y: int, end_y: int) -> bool:
    values: list[float] = []
    dark = 0
    bright = 0
    for y in range(start_y, end_y):
        row = y * FRAME_SAMPLE_WIDTH * 3
        for x in range(FRAME_SAMPLE_WIDTH):
            index = row + x * 3
            r, g, b = raw[index], raw[index + 1], raw[index + 2]
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            values.append(luma)
            if luma < 48:
                dark += 1
            elif luma > 205:
                bright += 1
    if not values:
        return False
    total = len(values)
    return (
        max(values) - min(values) >= CAPTION_LEAK_MIN_CONTRAST
        and dark / total >= CAPTION_LEAK_MIN_DARK_RATIO
        and bright / total >= CAPTION_LEAK_MIN_BRIGHT_RATIO
    )


def _sample_frame_motion_delta(path: Path) -> float | None:
    first = _sample_frame_rgb(path, "0.10")
    second = _sample_frame_rgb(path, "0.70")
    if first is None or second is None:
        return None
    stride = max(len(first) // 4096, 1)
    sampled = range(0, min(len(first), len(second)), stride)
    total = 0
    count = 0
    for index in sampled:
        total += abs(first[index] - second[index])
        count += 1
    if count == 0:
        return None
    return total / count


def _sample_frame_motion_segment_deltas(path: Path) -> list[float] | None:
    frames = [
        _sample_frame_rgb(path, timestamp)
        for timestamp in ("0.10", "0.40", "0.70")
    ]
    if any(frame is None for frame in frames):
        return None
    first, middle, last = frames
    if first is None or middle is None or last is None:
        return None
    return [
        _frame_delta(first, middle),
        _frame_delta(middle, last),
    ]


def _frame_delta(first: bytes, second: bytes) -> float:
    stride = max(len(first) // 4096, 1)
    sampled = range(0, min(len(first), len(second)), stride)
    total = 0
    count = 0
    for index in sampled:
        total += abs(first[index] - second[index])
        count += 1
    return total / count if count else 0.0


def _add_release_quality_issue(
    report: QAReport,
    code: str,
    message_zh: str,
    strict: bool,
) -> None:
    issue = QAIssue(code, "hard" if strict else "warning", message_zh)
    if strict:
        report.hard_failures.append(issue)
    else:
        report.warnings.append(issue)


def _scene_asset_diagnosis(scene: dict) -> dict | None:
    diagnosis = scene.get("asset_diagnosis")
    if isinstance(diagnosis, dict):
        return diagnosis
    for sheet in _scene_review_sheets(scene):
        if isinstance(sheet.get("asset_status"), dict):
            return sheet["asset_status"]
    return None


def _check_scene_stock_image_policy(
    scene: dict,
    report: QAReport,
    strict: bool,
) -> None:
    if not _scene_uses_stock_image(scene):
        return
    policy = _scene_stock_image_policy(scene)
    if not _stock_image_user_consent_confirmed(policy):
        _add_stock_image_blocker(
            report,
            scene,
            code="RELEASE_STOCK_IMAGE_USER_CONSENT_MISSING",
            message_zh=(
                "该镜头使用公开图库/免费图库图片,但缺少用户授权使用图库的可审计记录。"
            ),
            strict=strict,
        )
    sources = _scene_stock_image_sources(scene, policy)
    if not sources or any(not _stock_image_source_license_verified(source) for source in sources):
        _add_stock_image_blocker(
            report,
            scene,
            code="RELEASE_STOCK_IMAGE_LICENSE_NOT_VERIFIABLE",
            message_zh=(
                "该镜头使用公开图库/免费图库图片,但 source/sourceUrl/license/"
                "license_verification_status 不完整或未核验。"
            ),
            strict=strict,
        )
    if _scene_requires_real_evidence(scene):
        _add_stock_image_blocker(
            report,
            scene,
            code="RELEASE_STOCK_IMAGE_CANNOT_SATISFY_REAL_EVIDENCE",
            message_zh=(
                "该镜头仍要求真实动态 evidence;图库图只能做辅助设计层,"
                "不能替代 Codex/终端/网页/产品操作等真实录屏证据。"
            ),
            strict=strict,
        )


def _add_stock_image_blocker(
    report: QAReport,
    scene: dict,
    *,
    code: str,
    message_zh: str,
    strict: bool,
) -> None:
    _add_release_quality_issue(report, code, message_zh, strict)
    blocker = {
        "scene_id": str(scene.get("scene_id") or scene.get("id") or ""),
        "issue_code": code,
        "next_action_zh": (
            "请先确认用户是否授权使用公开免费图库,并补齐 source/sourceUrl/license/"
            "license_verification_status;若这一镜要求真实 evidence,还必须采集同镜动态录屏。"
        ),
    }
    report.metadata.setdefault("remaining_stock_image_blockers", []).append(
        {key: value for key, value in blocker.items() if value}
    )


def _scene_stock_image_policy(scene: dict) -> dict:
    policy = scene.get("stock_image_policy")
    if isinstance(policy, dict):
        return policy
    strategy = scene.get("asset_strategy_v2")
    if isinstance(strategy, dict) and isinstance(strategy.get("stock_image_policy"), dict):
        return strategy["stock_image_policy"]
    for sheet in _scene_review_sheets(scene):
        policy = sheet.get("stock_image_policy")
        if isinstance(policy, dict):
            return policy
        strategy = sheet.get("asset_strategy_v2")
        if isinstance(strategy, dict) and isinstance(strategy.get("stock_image_policy"), dict):
            return strategy["stock_image_policy"]
    return {}


def _scene_uses_stock_image(scene: dict) -> bool:
    policy = _scene_stock_image_policy(scene)
    if policy.get("used") is True or policy.get("selected") is True:
        return True
    if _scene_stock_image_sources(scene, policy):
        return True
    origin = str(scene.get("asset_origin") or "").strip().lower()
    if origin in STOCK_IMAGE_ASSET_ORIGINS:
        return True
    kind = str(scene.get("asset_kind") or "").strip().lower()
    diagnosis = _scene_asset_diagnosis(scene) or {}
    diagnosis_kind = str(diagnosis.get("asset_kind") or "").strip().lower()
    strategy = scene.get("asset_strategy_v2")
    strategy_kind = ""
    if isinstance(strategy, dict):
        strategy_kind = str(strategy.get("current_asset_kind") or "").strip().lower()
    return any(
        "stock_image" in value or value in STOCK_IMAGE_ASSET_ORIGINS
        for value in (kind, diagnosis_kind, strategy_kind)
    )


def _scene_stock_image_sources(scene: dict, policy: dict | None = None) -> list[dict]:
    policy = policy if isinstance(policy, dict) else _scene_stock_image_policy(scene)
    sources: list[dict] = []
    selected = policy.get("selected_source")
    if isinstance(selected, dict):
        sources.append(selected)
    for container in (policy.get("sources"), scene.get("stock_image_sources")):
        if isinstance(container, list):
            sources.extend(item for item in container if isinstance(item, dict))
    return sources


def _stock_image_user_consent_confirmed(policy: dict) -> bool:
    if policy.get("user_consent_confirmed") is True:
        return True
    status = str(policy.get("user_consent_status") or "").strip().lower()
    return status in {"confirmed", "approved", "accepted", "user_confirmed"}


def _stock_image_source_license_verified(source: dict) -> bool:
    source_name = str(source.get("source") or "").strip()
    source_url = str(source.get("sourceUrl") or source.get("source_url") or "").strip()
    license_name = str(source.get("license") or "").strip()
    status = str(source.get("license_verification_status") or "").strip().lower()
    return bool(
        source_name
        and source_url
        and license_name
        and status in STOCK_IMAGE_LICENSE_VERIFIED_STATUSES
    )


def _scene_requires_real_evidence(scene: dict) -> bool:
    if scene.get("requires_real_evidence_asset") is True:
        return True
    return bool(_expected_evidence_type_groups(scene.get("expected_real_evidence")))


def _scene_has_director_contract(scene: dict) -> bool:
    return any(
        scene.get(key)
        for key in (
            "template_id",
            "blueprint_id",
            "visual_archetype",
            "asset_recipe_id",
            "transition_plan",
            "motion_intent",
            "layout_contract",
            "host_generation_contract",
            "director_review_sheet_v2",
            "director_review_sheet",
            "director_knowledge_refs",
            "asset_strategy_v2",
            "expected_real_evidence",
        )
    )


def _scene_review_sheets(scene: dict) -> list[dict]:
    sheets: list[dict] = []
    for key in ("director_review_sheet_v2", "director_review_sheet"):
        sheet = scene.get(key)
        if isinstance(sheet, dict):
            sheets.append(sheet)
    return sheets


def _text_markers_from(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        markers: list[str] = []
        for item in value.values():
            markers.extend(_text_markers_from(item))
        return markers
    if isinstance(value, list):
        markers = []
        for item in value:
            markers.extend(_text_markers_from(item))
        return markers
    return [str(value)]


def _scene_proves_opening_hook(scene: dict) -> bool:
    markers: list[str] = []
    for key in (
        "role",
        "template_id",
        "blueprint_id",
        "visual_archetype",
        "asset_recipe_id",
        "director_knowledge_refs",
        "director_review_sheet_v2",
        "director_review_sheet",
    ):
        markers.extend(_text_markers_from(scene.get(key)))
    marker_text = " ".join(markers).lower().replace(" ", "")
    return any(
        token in marker_text
        for token in ("hook", "钩子", "开场", "前3秒", "抓人", "注意力")
    ) and _scene_has_visible_hook_anchor(scene)


def _scene_has_visible_hook_anchor(scene: dict) -> bool:
    sheet_parts: list[object] = []
    for sheet in _scene_review_sheets(scene):
        sheet_parts.extend(
            [
                sheet.get("narration_text"),
                sheet.get("screen_text"),
                sheet.get("visual_content"),
                sheet.get("visual_elements"),
                sheet.get("qa_checkpoints"),
            ]
        )
    text = " ".join(
        " ".join(_text_markers_from(part))
        for part in (
            [
                scene.get("narration_text"),
                scene.get("on_screen_text"),
                scene.get("visual_prompt"),
                scene.get("expected_real_evidence"),
            ]
            + sheet_parts
        )
        if part
    ).lower()
    compact = text.replace(" ", "")
    return any(term.lower() in compact for term in HOOK_VISIBLE_ANCHOR_TERMS)


def _check_opening_hook(scenes: list[dict], report: QAReport, strict: bool) -> None:
    if not scenes or not any(_scene_has_director_contract(scene) for scene in scenes):
        return
    first_scene = scenes[0]
    if not _scene_proves_opening_hook(first_scene):
        _add_release_quality_issue(
            report,
            "RELEASE_HOOK_TOO_WEAK",
            "导演契约未证明第一镜承担前 3 秒 hook;发布级短视频需要先建立注意力锚点。",
            strict,
        )
        return
    try:
        first_duration = float(first_scene.get("duration_sec"))
    except (TypeError, ValueError):
        first_duration = 0.0
    if first_duration <= 0 or first_duration > HOOK_MAX_FIRST_SCENE_SEC:
        _add_release_quality_issue(
            report,
            "RELEASE_HOOK_TOO_WEAK",
            "第一镜 hook 缺少短节奏时长证据或时长过长;前 3 秒应快速建立视觉锚点。",
            strict,
        )


def _scene_alignment_record(scene: dict) -> dict | None:
    candidates = [scene.get("audio_visual_alignment")]
    for sheet in _scene_review_sheets(scene):
        candidates.append(sheet.get("audio_visual_alignment"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            status = str(candidate.get("status") or "").strip().lower()
            if status:
                return candidate
    return None


def _scene_alignment_status(scene: dict) -> str:
    record = _scene_alignment_record(scene)
    if not isinstance(record, dict):
        return ""
    return str(record.get("status") or "").strip().lower()


def _scene_alignment_evidence_issue(
    project: ProjectRef,
    manifest: dict,
    scene: dict,
) -> tuple[str, str] | None:
    record = _scene_alignment_record(scene)
    if not isinstance(record, dict):
        return (
            "RELEASE_AUDIO_VISUAL_ALIGNMENT_EVIDENCE_MISSING",
            "该镜头声明音画匹配已确认,但缺少 evidence/notes/verified_by/evidence_refs "
            "等可审计说明;发布级不能只靠状态字段放行。",
        )
    if _alignment_record_has_textual_evidence(record):
        return None
    refs = record.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        return (
            "RELEASE_AUDIO_VISUAL_ALIGNMENT_EVIDENCE_MISSING",
            "该镜头声明音画匹配已确认,但缺少 evidence/notes/verified_by/evidence_refs "
            "等可审计说明;发布级不能只靠状态字段放行。",
        )
    if _alignment_evidence_refs_are_verifiable(project, manifest, scene, refs):
        return None
    return (
        "RELEASE_AUDIO_VISUAL_ALIGNMENT_REF_NOT_VERIFIABLE",
        "该镜头用 evidence_refs 声明音画匹配已确认,但引用没有指向当前镜头可验证的视频证据;"
        "发布级不能用不存在、跨镜或不可 ffprobe 的 evidence ref 放行音画匹配。",
    )


def audio_visual_alignment_audit(
    project: ProjectRef,
    manifest: dict,
    scene: dict,
) -> dict[str, object] | None:
    record = _scene_alignment_record(scene)
    if not isinstance(record, dict):
        return None
    refs = record.get("evidence_refs")
    ref_count = len(refs) if isinstance(refs, list) else 0
    ref_verifiable = (
        _alignment_evidence_refs_are_verifiable(project, manifest, scene, refs)
        if isinstance(refs, list) and refs
        else False
    )
    issue = _scene_alignment_evidence_issue(project, manifest, scene)
    audit: dict[str, object] = {
        "has_text_evidence": _alignment_record_has_textual_evidence(record),
        "has_evidence": issue is None,
    }
    if ref_count:
        audit["evidence_ref_count"] = ref_count
        audit["evidence_ref_verifiable"] = ref_verifiable
    if issue is not None:
        audit["evidence_issue_code"] = issue[0]
    return audit


def _alignment_record_has_textual_evidence(record: dict) -> bool:
    for key in AUDIO_VISUAL_ALIGNMENT_TEXT_EVIDENCE_FIELDS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and value:
            return True
        if isinstance(value, dict) and value:
            return True
    return False


def _alignment_evidence_refs_are_verifiable(
    project: ProjectRef,
    manifest: dict,
    scene: dict,
    refs: list,
) -> bool:
    evidence_manifest = manifest.get("visual_evidence_assets")
    if not isinstance(evidence_manifest, dict):
        evidence_manifest = {}
    lookup = _evidence_asset_lookup(evidence_manifest)
    scene_refs = scene.get("evidence_asset_refs")
    bound_scene_refs = (
        [ref for ref in scene_refs if isinstance(ref, dict)]
        if isinstance(scene_refs, list)
        else []
    )
    for raw_ref in refs:
        for candidate, bound_to_scene in _alignment_evidence_ref_candidates(
            raw_ref,
            bound_scene_refs,
            lookup,
        ):
            merged = _merged_evidence_ref(candidate, lookup)
            if not _alignment_evidence_ref_targets_scene(
                merged,
                scene,
                bound_to_scene,
            ):
                continue
            if _evidence_clip_video_is_verifiable(project, merged):
                return True
    return False


def _alignment_evidence_ref_candidates(
    raw_ref: object,
    bound_scene_refs: list[dict],
    lookup: dict[str, dict],
) -> list[tuple[dict, bool]]:
    candidates: list[tuple[dict, bool]] = []
    ref_ids = _alignment_evidence_ref_ids(raw_ref)
    for scene_ref in bound_scene_refs:
        if ref_ids and not (_alignment_evidence_ref_ids(scene_ref) & ref_ids):
            continue
        candidates.append((scene_ref, True))
    for ref_id in ref_ids:
        if ref_id in lookup:
            candidates.append(({"id": ref_id}, False))
    if isinstance(raw_ref, dict):
        candidates.append((raw_ref, False))
    return candidates


def _alignment_evidence_ref_ids(raw_ref: object) -> set[str]:
    if isinstance(raw_ref, str):
        text = raw_ref.strip()
        return {text} if text else set()
    if not isinstance(raw_ref, dict):
        return set()
    ids: set[str] = set()
    for key in ("id", "asset_id", "evidence_asset_id"):
        value = str(raw_ref.get(key) or "").strip()
        if value:
            ids.add(value)
    return ids


def _alignment_evidence_ref_targets_scene(
    ref: dict,
    scene: dict,
    bound_to_scene: bool,
) -> bool:
    scene_id = str(scene.get("scene_id") or scene.get("id") or "").strip()
    target = str(ref.get("target_scene_id") or ref.get("scene_id") or "").strip()
    if target and scene_id:
        return target == scene_id
    return bound_to_scene


def _caption_text(scene: dict) -> str:
    cues = scene.get("caption_cues")
    if not isinstance(cues, list):
        return ""
    return " ".join(str(cue.get("text") or "") for cue in cues if isinstance(cue, dict))


def _scene_screen_text(scene: dict) -> str:
    sheet_text = " ".join(
        str(sheet.get("screen_text") or "")
        for sheet in _scene_review_sheets(scene)
        if sheet.get("screen_text")
    )
    return " ".join(
        part
        for part in [
            str(scene.get("on_screen_text") or ""),
            sheet_text,
        ]
        if part
    )


def _scene_narration_text(scene: dict) -> str:
    sheet_text = " ".join(
        str(sheet.get("narration_text") or "")
        for sheet in _scene_review_sheets(scene)
        if sheet.get("narration_text")
    )
    return " ".join(
        part
        for part in [
            str(scene.get("narration_text") or ""),
            sheet_text,
            _caption_text(scene),
        ]
        if part
    )


def _scene_spoken_caption_source_text(scene: dict) -> str:
    sheet_text = " ".join(
        str(sheet.get("narration_text") or "")
        for sheet in _scene_review_sheets(scene)
        if sheet.get("narration_text")
    )
    return " ".join(
        part
        for part in [
            str(scene.get("narration_text") or ""),
            sheet_text,
        ]
        if part
    )


def _scene_visual_alignment_text(scene: dict) -> str:
    sheet_parts: list[object] = []
    for sheet in _scene_review_sheets(scene):
        sheet_parts.extend(
            [
                sheet.get("screen_text"),
                sheet.get("visual_content"),
                sheet.get("visual_elements"),
                sheet.get("asset_source"),
                sheet.get("composition"),
                sheet.get("qa_checkpoints"),
            ]
        )
    parts: list[object] = [
        scene.get("on_screen_text"),
        scene.get("visual_prompt"),
        scene.get("visual_archetype"),
        scene.get("blueprint_id"),
        scene.get("template_id"),
        scene.get("asset_recipe_id"),
        scene.get("expected_real_evidence"),
        scene.get("director_knowledge_refs"),
        scene.get("asset_strategy_v2"),
    ]
    parts.extend(sheet_parts)
    return " ".join(" ".join(_text_markers_from(part)) for part in parts if part)


def _semantic_tokens(value: str) -> set[str]:
    normalized = str(value or "").lower()
    tokens = {
        item
        for item in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", normalized)
        if item not in AUDIO_VISUAL_COMMON_TOKENS
    }
    for term in AUDIO_VISUAL_KEY_TERMS:
        if term.lower() in normalized:
            tokens.add(term.lower())
    cjk_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    for chunk in cjk_chunks:
        for size in (2, 3):
            for index in range(0, max(len(chunk) - size + 1, 0)):
                token = chunk[index : index + size]
                if token not in AUDIO_VISUAL_COMMON_TOKENS:
                    tokens.add(token)
    return tokens


def _check_audio_visual_alignment(
    project: ProjectRef,
    manifest: dict,
    scenes: list[dict],
    report: QAReport,
    strict: bool,
) -> None:
    for scene in scenes:
        if not _scene_has_director_contract(scene):
            continue
        alignment_status = _scene_alignment_status(scene)
        if alignment_status in {"aligned", "verified"}:
            evidence_issue = _scene_alignment_evidence_issue(project, manifest, scene)
            if evidence_issue is not None:
                code, message = evidence_issue
                _add_release_quality_issue(
                    report,
                    code,
                    message,
                    strict,
                )
            continue
        if alignment_status == "planned":
            _add_release_quality_issue(
                report,
                "RELEASE_AUDIO_VISUAL_ALIGNMENT_NOT_VERIFIED",
                "该镜头的音画匹配仍停留在 planned 计划态;"
                "发布级 strict 需要 aligned/verified 或可审计的实际匹配证据。",
                strict,
            )
            continue
        narration_text = _scene_narration_text(scene)
        visual_text = _scene_visual_alignment_text(scene)
        if not narration_text or not visual_text:
            _add_release_quality_issue(
                report,
                "RELEASE_AUDIO_VISUAL_MISMATCH",
                "该镜头缺少口播文本或画面描述证据,无法证明音画匹配。",
                strict,
            )
            continue
        narration_tokens = _semantic_tokens(narration_text)
        visual_tokens = _semantic_tokens(visual_text)
        if narration_tokens and visual_tokens and not (narration_tokens & visual_tokens):
            _add_release_quality_issue(
                report,
                "RELEASE_AUDIO_VISUAL_MISMATCH",
                "口播关键词与画面描述/屏幕短文案缺少可审计交集,需要人工确认该镜头是否音画匹配。",
                strict,
            )


def _check_audio_mix(
    project: ProjectRef,
    manifest: dict,
    scenes: list[dict],
    report: QAReport,
    strict: bool,
) -> None:
    declared_bgm_required = _scenes_require_bgm(scenes)
    declared_sfx_markers = _declared_sfx_markers_by_scene(scenes)
    mix = manifest.get("audio_mix")
    if not isinstance(mix, dict):
        if declared_bgm_required:
            _add_release_quality_issue(
                report,
                "RELEASE_BGM_DECLARED_BUT_NOT_RENDERED",
                "分镜声明了 BGM 情绪/策略,但 release manifest 没有 BGM 混音证据;"
                "发布级 BGM 不能只停留在导演分镜。",
                strict,
            )
        if declared_sfx_markers:
            _add_release_quality_issue(
                report,
                "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED",
                "分镜声明了音效点,但 release manifest 没有音效混音证据;"
                "发布级音效必须在最终 audio_mix.sfx_events 中兑现。",
                strict,
            )
        return
    invalid_audio_assets = mix.get("invalid_audio_assets")
    try:
        invalid_audio_asset_count = int(mix.get("invalid_audio_asset_count") or 0)
    except (TypeError, ValueError):
        invalid_audio_asset_count = 0
    if invalid_audio_asset_count > 0 or (
        isinstance(invalid_audio_assets, list) and invalid_audio_assets
    ):
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_DECLARED_ASSET_MISSING",
            "voice_plan 声明了 BGM/SFX 源音频,但 release render 无法在项目内验证这些资产;"
            "发布级声音设计不能静默跳过缺失音频。",
            strict,
        )
    bgm_present = bool(mix.get("bgm_present"))
    sfx_count = int(mix.get("sfx_count") or 0)
    if declared_bgm_required and not bgm_present:
        _add_release_quality_issue(
            report,
            "RELEASE_BGM_DECLARED_BUT_NOT_RENDERED",
            "分镜声明了 BGM 情绪/策略,但最终 audio_mix 未包含 BGM;"
            "发布级声音策略必须在混音中兑现,或在分镜中明确标为可无 BGM。",
            strict,
        )
    if (bgm_present or sfx_count > 0) and mix.get("rendered") is not True:
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_MIX_NOT_RENDERED",
            "release 声明包含 BGM/SFX,但 manifest 未证明这些音频已实际混入最终音轨。",
            strict,
        )
        return
    if (bgm_present or sfx_count > 0) and not _audio_mix_output_is_verifiable(project, mix):
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_MIX_OUTPUT_NOT_VERIFIABLE",
            "release 声明 BGM/SFX 已混音,但 mixed_audio_path 缺失、"
            "文件不存在或 ffprobe 未确认音频流。",
            strict,
        )
        return
    if bgm_present or sfx_count > 0:
        _check_audio_mix_duration(project, manifest, mix, report, strict)
    if bgm_present:
        if "bgm_to_voice_db" not in mix:
            _add_release_quality_issue(
                report,
                "RELEASE_AUDIO_MIX_NOT_VERIFIABLE",
                "release 声明包含 BGM,但缺少 BGM 与人声相对音量证据。",
                strict,
            )
            return
        try:
            bgm_to_voice_db = float(mix["bgm_to_voice_db"])
        except (TypeError, ValueError):
            _add_release_quality_issue(
                report,
                "RELEASE_AUDIO_MIX_NOT_VERIFIABLE",
                "release 的 BGM 与人声音量证据不可解析。",
                strict,
            )
            return
        if bgm_to_voice_db > BGM_MAX_RELATIVE_DB:
            _add_release_quality_issue(
                report,
                "RELEASE_BGM_OVER_VOICE",
                "BGM 相对人声过高,发布前需要降低背景音乐,确保口播优先。",
                strict,
            )
        if not _audio_source_asset_is_verifiable(project, mix.get("bgm_path")):
            _add_release_quality_issue(
                report,
                "RELEASE_BGM_ASSET_NOT_VERIFIABLE",
                "release 声明包含 BGM,但 bgm_path 缺失、文件不存在或 ffprobe 未确认音频流。",
                strict,
            )
    if declared_sfx_markers and sfx_count <= 0:
        _add_release_quality_issue(
            report,
            "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED",
            "分镜声明了音效点,但最终混音没有任何 SFX 事件;"
            "发布级音效必须服务具体画面动作,不能只停留在导演分镜。",
            strict,
        )
    if sfx_count <= 0:
        return
    if "sfx_density_per_10_sec" not in mix:
        _add_release_quality_issue(
            report,
            "RELEASE_SFX_DENSITY_NOT_VERIFIABLE",
            "release 声明包含音效,但缺少 SFX 密度证据。",
            strict,
        )
        return
    try:
        sfx_density = float(mix["sfx_density_per_10_sec"])
    except (TypeError, ValueError):
        _add_release_quality_issue(
            report,
            "RELEASE_SFX_DENSITY_NOT_VERIFIABLE",
            "release 的 SFX 密度证据不可解析。",
            strict,
        )
        return
    if sfx_density > SFX_MAX_PER_10_SEC:
        _add_release_quality_issue(
            report,
            "RELEASE_SFX_TOO_DENSE",
            "音效触发过密,发布级视频应让音效服务动作提示,不能抢口播。",
            strict,
        )
    events = mix.get("sfx_events")
    if not isinstance(events, list) or len(events) < sfx_count:
        _add_release_quality_issue(
            report,
            "RELEASE_SFX_ACTION_NOT_VERIFIABLE",
            "release 声明包含音效,但缺少逐个音效与镜头动作点的绑定证据。",
            strict,
        )
        return
    if declared_sfx_markers and not _declared_sfx_markers_are_rendered(
        declared_sfx_markers,
        events[:sfx_count],
    ):
        _add_release_quality_issue(
            report,
            "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED",
            "分镜声明的音效点没有在最终 SFX 事件中找到同镜匹配;"
            "发布级音效必须把确认单里的动作音效落实到混音。",
            strict,
        )
        return
    for event in events[:sfx_count]:
        if not isinstance(event, dict) or not _sfx_event_has_action_anchor(event):
            _add_release_quality_issue(
                report,
                "RELEASE_SFX_ACTION_NOT_VERIFIABLE",
                "音效缺少 scene_id 与 action/purpose/visual_event/cue_id 证据;"
                "发布级音效必须服务具体画面动作。",
                strict,
            )
            return
        gain_db = _sfx_event_gain_db(event)
        if gain_db is None:
            _add_release_quality_issue(
                report,
                "RELEASE_SFX_GAIN_NOT_VERIFIABLE",
                "音效缺少可解析的 gain_db;发布级音效必须证明不会压过口播。",
                strict,
            )
            return
        if gain_db > SFX_MAX_GAIN_DB:
            _add_release_quality_issue(
                report,
                "RELEASE_SFX_TOO_LOUD",
                "单个音效增益过高,可能抢口播或造成突兀听感;发布前需要降低 SFX gain。",
                strict,
            )
            return
        if not _sfx_event_timing_matches_scene(event, scenes):
            _add_release_quality_issue(
                report,
                "RELEASE_SFX_TIMING_NOT_VERIFIABLE",
                "音效时间点没有落在绑定镜头的时间窗内;发布级音效必须和具体画面动作同步。",
                strict,
            )
            return
        if not _sfx_event_matches_scene_action_marker(event, scenes):
            _add_release_quality_issue(
                report,
                "RELEASE_SFX_VISUAL_ACTION_UNMATCHED",
                "音效声明的动作点没有匹配到绑定镜头的视觉动作标记;"
                "发布级音效必须服务可审计的画面动作,不能只靠文字描述。",
                strict,
            )
            return
        if not _sfx_event_matches_visual_action_timing(event, scenes):
            _add_release_quality_issue(
                report,
                "RELEASE_SFX_VISUAL_ACTION_TIMING_MISMATCH",
                "音效触发点与绑定镜头的同名视觉动作时间错开过大;"
                "发布级音效必须贴合可审计的画面动作发生点。",
                strict,
            )
            return
        if not _audio_source_asset_is_verifiable(project, event.get("path")):
            _add_release_quality_issue(
                report,
                "RELEASE_SFX_ASSET_NOT_VERIFIABLE",
                "release 声明包含音效,但 SFX 源文件缺失、越界或 ffprobe 未确认音频流。",
                strict,
            )
            return


def _declared_sfx_markers_by_scene(scenes: list[dict]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        markers = _scene_declared_sfx_markers(scene)
        if not markers:
            continue
        scene_id = str(scene.get("scene_id") or scene.get("id") or f"s{index}")
        result[scene_id] = markers
    return result


def _scene_declared_sfx_markers(scene: dict) -> set[str]:
    markers: set[str] = set()
    for key in ("sfx_points", "sound_cues"):
        _collect_action_markers(markers, scene.get(key))
    for group_key in SCENE_ACTION_MARKER_GROUPS:
        group = scene.get(group_key)
        if not isinstance(group, dict):
            continue
        for key in ("sfx_points", "sound_cues"):
            _collect_action_markers(markers, group.get(key))
    return {marker for marker in markers if _declared_sfx_marker_requires_render(marker)}


def _declared_sfx_marker_requires_render(marker: str) -> bool:
    normalized = _normalize_action_marker(marker)
    if not normalized:
        return False
    return not _sfx_marker_declares_optional_or_none(normalized)


def _sfx_marker_declares_optional_or_none(marker: str) -> bool:
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
    if marker in exact_no_sfx_terms:
        return True
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
    return any(term in marker for term in no_sfx_terms)


def _declared_sfx_markers_are_rendered(
    declared_by_scene: dict[str, set[str]],
    events: list[object],
) -> bool:
    rendered_by_scene: dict[str, set[str]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        scene_id = str(event.get("scene_id") or "").strip()
        if not scene_id:
            continue
        rendered_by_scene.setdefault(scene_id, set()).update(
            _sfx_event_marker_candidates(event)
        )
    for scene_id, declared_markers in declared_by_scene.items():
        rendered_markers = rendered_by_scene.get(scene_id, set())
        if not rendered_markers or not _marker_sets_overlap(
            declared_markers,
            rendered_markers,
        ):
            return False
    return True


def _audio_mix_output_is_verifiable(project: ProjectRef, mix: dict) -> bool:
    resolved = _audio_mix_output_path(project, mix)
    if resolved is None:
        return False
    _, has_audio = _media_streams_are_verifiable(resolved)
    return has_audio


def _audio_source_asset_is_verifiable(project: ProjectRef, raw_path: object) -> bool:
    resolved = _audio_source_asset_path(project, raw_path)
    if resolved is None:
        return False
    _, has_audio = _media_streams_are_verifiable(resolved)
    return has_audio


def _audio_source_asset_path(project: ProjectRef, raw_path: object) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    resolved = resolve_inside(project.path, project.path / raw_path)
    if not resolved.is_file():
        return None
    return resolved


def _audio_mix_output_path(project: ProjectRef, mix: dict) -> Path | None:
    raw_path = str(mix.get("mixed_audio_path") or "")
    if not raw_path:
        return None
    resolved = resolve_inside(project.path, project.path / raw_path)
    if not resolved.is_file():
        return None
    return resolved


def _check_audio_mix_duration(
    project: ProjectRef,
    manifest: dict,
    mix: dict,
    report: QAReport,
    strict: bool,
) -> None:
    expected = _expected_release_duration(project, manifest)
    if expected is None:
        return
    resolved = _audio_mix_output_path(project, mix)
    if resolved is None:
        return
    actual = _media_duration_sec(resolved)
    if actual is None:
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_MIX_DURATION_NOT_VERIFIABLE",
            "release 声明 BGM/SFX 已混音,但未能用 ffprobe 验证混音文件时长。",
            strict,
        )
        return
    tolerance = _release_duration_tolerance_sec(expected)
    drift = abs(actual - expected)
    report.info.append(
        QAIssue(
            "RELEASE_AUDIO_MIX_DURATION_STATS",
            "info",
            f"混音时长体检:actual={actual:.2f}s,expected={expected:.2f}s,drift={drift:.2f}s。",
        )
    )
    if drift > tolerance:
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_MIX_DURATION_MISMATCH",
            "BGM/SFX 混音时长与 release 预期时长偏差过大,"
            f"actual={actual:.2f}s,expected={expected:.2f}s,tolerance={tolerance:.2f}s;"
            "可能存在背景音乐/音效被截断或只覆盖了部分视频。",
            strict,
        )


def _scenes_require_bgm(scenes: list[dict]) -> bool:
    return any(_scene_requires_bgm(scene) for scene in scenes if isinstance(scene, dict))


def _scene_requires_bgm(scene: dict) -> bool:
    for text in _scene_bgm_texts(scene):
        normalized = _normalize_bgm_text(text)
        if not normalized:
            continue
        if _bgm_text_declares_optional_or_none(normalized):
            continue
        if "bgm" in normalized or "音乐" in normalized or "配乐" in normalized:
            return True
    return False


def _scene_bgm_texts(scene: dict) -> list[str]:
    texts: list[str] = []
    for key in ("bgm", "bgm_strategy", "music", "music_strategy"):
        value = scene.get(key)
        if value:
            texts.append(str(value))
    audio_notes = scene.get("audio_sfx_notes")
    if isinstance(audio_notes, dict) and audio_notes.get("bgm"):
        texts.append(str(audio_notes["bgm"]))
    board = scene.get("director_board")
    if isinstance(board, dict):
        notes = board.get("audio_sfx_notes")
        if isinstance(notes, dict) and notes.get("bgm"):
            texts.append(str(notes["bgm"]))
    for sheet in _scene_review_sheets(scene):
        for key in ("bgm", "bgm_strategy", "music", "music_strategy"):
            value = sheet.get(key)
            if value:
                texts.append(str(value))
        notes = sheet.get("audio_sfx_notes")
        if isinstance(notes, dict) and notes.get("bgm"):
            texts.append(str(notes["bgm"]))
    return texts


def _normalize_bgm_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _bgm_text_declares_optional_or_none(text: str) -> bool:
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
    return any(term in text for term in no_bgm_terms)


def _sfx_event_has_action_anchor(event: dict) -> bool:
    if not str(event.get("scene_id") or "").strip():
        return False
    for key in ("action", "purpose", "visual_event", "cue_id"):
        if str(event.get(key) or "").strip():
            return True
    return False


def _sfx_event_gain_db(event: dict) -> float | None:
    try:
        return float(event.get("gain_db"))
    except (TypeError, ValueError):
        return None


def _sfx_event_timing_matches_scene(event: dict, scenes: list[dict]) -> bool:
    scene_id = str(event.get("scene_id") or "").strip()
    if not scene_id:
        return False
    try:
        at_sec = float(event.get("at_sec"))
    except (TypeError, ValueError):
        return False
    if at_sec < 0:
        return False
    start_sec = 0.0
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        duration_sec = _positive_float(scene.get("duration_sec"))
        if duration_sec is None:
            return False
        current_scene_id = str(scene.get("scene_id") or scene.get("id") or f"s{index}")
        end_sec = start_sec + duration_sec
        if current_scene_id == scene_id:
            return (
                start_sec - SFX_TIMING_TOLERANCE_SEC
                <= at_sec
                <= end_sec + SFX_TIMING_TOLERANCE_SEC
            )
        start_sec = end_sec
    return False


def _sfx_event_matches_scene_action_marker(event: dict, scenes: list[dict]) -> bool:
    scene = _scene_for_sfx_event(event, scenes)
    if scene is None:
        return False
    scene_markers = _scene_visual_action_markers(scene)
    event_markers = _sfx_event_marker_candidates(event)
    if not scene_markers:
        return not str(event.get("cue_id") or "").strip()
    if not event_markers:
        return False
    return _marker_sets_overlap(event_markers, scene_markers)


def _sfx_event_matches_visual_action_timing(event: dict, scenes: list[dict]) -> bool:
    scene_with_start = _scene_for_sfx_event_with_start(event, scenes)
    if scene_with_start is None:
        return False
    scene, scene_start_sec = scene_with_start
    event_local_at_sec = _sfx_event_local_at_sec(event, scene_start_sec)
    if event_local_at_sec is None:
        return False
    event_markers = _sfx_event_marker_candidates(event)
    if not event_markers:
        return False
    matched_times: list[float] = []
    for marker_set, marker_time_sec in _scene_visual_action_timed_markers(scene):
        if _marker_sets_overlap(event_markers, marker_set):
            matched_times.append(marker_time_sec)
    if not matched_times:
        return True
    return any(
        abs(event_local_at_sec - marker_time_sec)
        <= SFX_VISUAL_ACTION_TIMING_TOLERANCE_SEC
        for marker_time_sec in matched_times
    )


def _scene_for_sfx_event(event: dict, scenes: list[dict]) -> dict | None:
    scene_with_start = _scene_for_sfx_event_with_start(event, scenes)
    if scene_with_start is None:
        return None
    scene, _ = scene_with_start
    return scene


def _scene_for_sfx_event_with_start(
    event: dict,
    scenes: list[dict],
) -> tuple[dict, float] | None:
    scene_id = str(event.get("scene_id") or "").strip()
    if not scene_id:
        return None
    start_sec = 0.0
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        current_scene_id = str(scene.get("scene_id") or scene.get("id") or f"s{index}")
        if current_scene_id == scene_id:
            return scene, start_sec
        duration_sec = _positive_float(scene.get("duration_sec"))
        if duration_sec is None:
            return None
        start_sec += duration_sec
    return None


def _sfx_event_local_at_sec(event: dict, scene_start_sec: float) -> float | None:
    local_at_sec = _non_negative_float(event.get("local_at_sec"))
    if local_at_sec is not None:
        return local_at_sec
    at_sec = _non_negative_float(event.get("at_sec"))
    if at_sec is None:
        return None
    return max(at_sec - scene_start_sec, 0.0)


def _sfx_event_marker_candidates(event: dict) -> set[str]:
    markers: set[str] = set()
    for key in SFX_EVENT_MARKER_FIELDS:
        _add_marker(markers, event.get(key))
    return markers


def _scene_visual_action_timed_markers(scene: dict) -> list[tuple[set[str], float]]:
    markers: list[tuple[set[str], float]] = []
    for key in SCENE_ACTION_MARKER_CONTAINERS:
        _collect_action_timed_markers(markers, scene.get(key))
    for group_key in SCENE_ACTION_MARKER_GROUPS:
        group = scene.get(group_key)
        if not isinstance(group, dict):
            continue
        for key in SCENE_ACTION_MARKER_CONTAINERS:
            _collect_action_timed_markers(markers, group.get(key))
    return markers


def _collect_action_timed_markers(
    markers: list[tuple[set[str], float]],
    value: object,
) -> None:
    if isinstance(value, dict):
        marker_time_sec = _action_marker_time_sec(value)
        marker_set = _action_marker_candidates(value)
        if marker_time_sec is not None and marker_set:
            markers.append((marker_set, marker_time_sec))
        for key in SCENE_ACTION_MARKER_CONTAINERS:
            _collect_action_timed_markers(markers, value.get(key))
        return
    if isinstance(value, list):
        for item in value:
            _collect_action_timed_markers(markers, item)


def _action_marker_candidates(value: dict) -> set[str]:
    markers: set[str] = set()
    for key in SCENE_ACTION_MARKER_FIELDS:
        _add_marker(markers, value.get(key))
    return markers


def _action_marker_time_sec(value: dict) -> float | None:
    for key in SCENE_ACTION_TIME_FIELDS:
        time_sec = _non_negative_float(value.get(key))
        if time_sec is not None:
            return time_sec
    return None


def _scene_visual_action_markers(scene: dict) -> set[str]:
    markers: set[str] = set()
    for key in SCENE_ACTION_MARKER_CONTAINERS:
        _collect_action_markers(markers, scene.get(key))
    for group_key in SCENE_ACTION_MARKER_GROUPS:
        group = scene.get(group_key)
        if not isinstance(group, dict):
            continue
        for key in SCENE_ACTION_MARKER_CONTAINERS:
            _collect_action_markers(markers, group.get(key))
    return markers


def _collect_action_markers(markers: set[str], value: object) -> None:
    if isinstance(value, dict):
        for key in SCENE_ACTION_MARKER_FIELDS:
            _add_marker(markers, value.get(key))
        for key in SCENE_ACTION_MARKER_CONTAINERS:
            _collect_action_markers(markers, value.get(key))
        return
    if isinstance(value, list):
        for item in value:
            _collect_action_markers(markers, item)
        return
    _add_marker(markers, value)


def _add_marker(markers: set[str], value: object) -> None:
    marker = _normalize_action_marker(value)
    if marker:
        markers.add(marker)


def _normalize_action_marker(value: object) -> str:
    marker = " ".join(str(value or "").strip().lower().split())
    return marker


def _marker_sets_overlap(left: set[str], right: set[str]) -> bool:
    if left & right:
        return True
    for left_marker in left:
        for right_marker in right:
            if (
                len(left_marker) >= 4
                and len(right_marker) >= 4
                and (left_marker in right_marker or right_marker in left_marker)
            ):
                return True
    return False


def _check_final_audio_volume(video_path: Path, report: QAReport, strict: bool) -> None:
    stats = _audio_volume_stats(video_path)
    if stats is None:
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_VOLUME_NOT_VERIFIABLE",
            "未能用 FFmpeg volumedetect 验证最终音轨响度/峰值;发布前需要人工试听。",
            strict,
        )
        return
    mean_volume = stats["mean_volume_db"]
    peak_volume = stats["peak_volume_db"]
    report.info.append(
        QAIssue(
            "RELEASE_AUDIO_VOLUME_STATS",
            "info",
            f"最终音轨响度体检:mean_volume={mean_volume:.1f}dB,max_volume={peak_volume:.1f}dB。",
        )
    )
    dynamic_stats = _audio_dynamic_stats(video_path)
    if dynamic_stats is None:
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_DYNAMIC_RANGE_NOT_VERIFIABLE",
            "未能用 FFmpeg astats 验证最终音轨动态范围;发布前需要人工试听。",
            strict,
        )
    else:
        dynamic_range = dynamic_stats["rms_dynamic_range_db"]
        window_count = int(dynamic_stats["rms_window_count"])
        report.info.append(
            QAIssue(
                "RELEASE_AUDIO_DYNAMIC_RANGE_STATS",
                "info",
                "最终音轨动态范围体检:"
                f"rms_dynamic_range={dynamic_range:.1f}dB,windows={window_count}。",
            )
        )
        if dynamic_range < FINAL_AUDIO_DYNAMIC_RANGE_MIN_DB:
            _add_release_quality_issue(
                report,
                "RELEASE_AUDIO_DYNAMIC_RANGE_TOO_FLAT",
                "最终音轨 RMS 动态范围过窄,可能听起来平板或过度压缩;"
                "发布前需要人工试听并调整口播/BGM 混音。",
                strict,
            )
    lufs_stats = _audio_lufs_stats(video_path)
    if lufs_stats is None:
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_LUFS_NOT_VERIFIABLE",
            "未能用 FFmpeg ebur128 验证最终音轨 LUFS;发布前需要人工试听。",
            strict,
        )
    else:
        integrated_lufs = lufs_stats["integrated_lufs"]
        report.info.append(
            QAIssue(
                "RELEASE_AUDIO_LUFS_STATS",
                "info",
                f"最终音轨 LUFS 体检:integrated_lufs={integrated_lufs:.1f}。",
            )
        )
        if integrated_lufs > FINAL_AUDIO_LUFS_MAX:
            _add_release_quality_issue(
                report,
                "RELEASE_AUDIO_LUFS_TOO_HOT",
                "最终音轨综合响度过高,可能压迫口播动态或在平台二次响度处理后失真;"
                "发布前需要重新做响度归一化。",
                strict,
            )
        if integrated_lufs < FINAL_AUDIO_LUFS_MIN:
            _add_release_quality_issue(
                report,
                "RELEASE_AUDIO_LUFS_TOO_QUIET",
                "最终音轨综合响度过低,可能在手机外放环境听不清;"
                "发布前需要提升口播响度或重新做响度归一化。",
                strict,
            )
    if peak_volume > FINAL_AUDIO_PEAK_MAX_DB:
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_PEAK_TOO_HIGH",
            "最终音轨峰值接近或超过 0dB,可能削波失真;发布前需要降低或限幅。",
            strict,
        )
    if mean_volume > FINAL_AUDIO_MEAN_MAX_DB:
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_TOO_HOT",
            "最终音轨平均响度过高,可能压迫口播动态或在手机外放上刺耳;"
            "发布前需要降低整体响度或重新做响度归一化。",
            strict,
        )
    if mean_volume < FINAL_AUDIO_MEAN_MIN_DB or peak_volume < FINAL_AUDIO_PEAK_MIN_DB:
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_TOO_QUIET",
            "最终音轨整体过轻,可能在手机外放环境听不清;发布前需要提升口播响度。",
            strict,
        )


def _manifest_expected_release_duration(manifest: dict) -> float | None:
    for key in ("expected_duration_sec", "voice_duration_sec", "total_duration_sec"):
        expected = _positive_float(manifest.get(key))
        if expected is not None:
            return expected
    return None


def _expected_release_duration(project: ProjectRef, manifest: dict) -> float | None:
    manifest_expected = _manifest_expected_release_duration(manifest)
    if manifest_expected is not None:
        return manifest_expected
    voice_plan = _release_voice_plan(project)
    if not isinstance(voice_plan, dict):
        return None
    return _positive_float(voice_plan.get("total_duration_sec"))


def _release_voice_plan(project: ProjectRef) -> dict | None:
    voice_path = project.path / "artifacts" / "voice_plan.json"
    if not voice_path.exists():
        return None
    try:
        voice_plan = json.loads(voice_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(voice_plan, dict):
        return None
    return voice_plan


def _manifest_tts_provider_id(manifest: dict) -> str:
    for provider in manifest.get("providers", []):
        if isinstance(provider, dict) and provider.get("kind") == "tts":
            return str(provider.get("id") or "")
    return ""


def _voice_plan_declares_audio_source(project: ProjectRef, voice_plan: dict) -> bool:
    full_audio_path = voice_plan.get("full_audio_path")
    if isinstance(full_audio_path, str) and full_audio_path:
        if _audio_source_asset_is_verifiable(project, full_audio_path):
            return True
    segments = voice_plan.get("segments")
    if not isinstance(segments, list) or not segments:
        return False
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        audio_path = segment.get("audio_path")
        if isinstance(audio_path, str) and audio_path:
            if _audio_source_asset_is_verifiable(project, audio_path):
                return True
    return False


def _voice_plan_audio_duration_issue(
    project: ProjectRef,
    voice_plan: dict,
) -> QAIssue | None:
    expected_total = _positive_float(voice_plan.get("total_duration_sec"))
    full_audio_path = voice_plan.get("full_audio_path")
    if isinstance(full_audio_path, str) and full_audio_path and expected_total is not None:
        resolved = _audio_source_asset_path(project, full_audio_path)
        if resolved is None:
            return None
        actual = _media_duration_sec(resolved)
        if actual is None:
            return QAIssue(
                "RELEASE_VOICE_PLAN_AUDIO_DURATION_NOT_VERIFIABLE",
                "warning",
                "无法用 ffprobe 验证 voice_plan.full_audio_path 的实际时长;"
                "发布前不能确认口播源音频是否覆盖计划总时长。",
            )
        tolerance = _release_duration_tolerance_sec(expected_total)
        drift = abs(actual - expected_total)
        if drift > tolerance:
            return QAIssue(
                "RELEASE_VOICE_PLAN_AUDIO_DURATION_MISMATCH",
                "warning",
                "voice_plan.full_audio_path 实际时长与计划总时长偏差过大,"
                f"actual={actual:.2f}s,expected={expected_total:.2f}s,tolerance={tolerance:.2f}s;"
                "可能导致配音截断、画面拖长或字幕节奏错位。",
            )
        return None

    segments = voice_plan.get("segments")
    if not isinstance(segments, list):
        return None
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        audio_path = segment.get("audio_path")
        expected = _positive_float(segment.get("duration_sec"))
        if not isinstance(audio_path, str) or not audio_path or expected is None:
            continue
        resolved = _audio_source_asset_path(project, audio_path)
        if resolved is None:
            continue
        actual = _media_duration_sec(resolved)
        if actual is None:
            return QAIssue(
                "RELEASE_VOICE_PLAN_AUDIO_DURATION_NOT_VERIFIABLE",
                "warning",
                "无法用 ffprobe 验证 voice_plan segment 音频源的实际时长;"
                "发布前不能确认分段口播是否覆盖对应镜头。",
            )
        tolerance = _release_duration_tolerance_sec(expected)
        drift = abs(actual - expected)
        if drift > tolerance:
            return QAIssue(
                "RELEASE_VOICE_PLAN_AUDIO_DURATION_MISMATCH",
                "warning",
                "voice_plan segment 音频源实际时长与计划分段时长偏差过大,"
                f"actual={actual:.2f}s,expected={expected:.2f}s,tolerance={tolerance:.2f}s;"
                "可能导致该镜头配音和字幕不同步。",
            )
    return None


def _voice_plan_segment_duration_issue(voice_plan: dict) -> QAIssue | None:
    expected_total = _positive_float(voice_plan.get("total_duration_sec"))
    segments = voice_plan.get("segments")
    if expected_total is None or not isinstance(segments, list) or not segments:
        return None
    total = 0.0
    for segment in segments:
        if not isinstance(segment, dict):
            return QAIssue(
                "RELEASE_VOICE_PLAN_SEGMENT_DURATION_NOT_VERIFIABLE",
                "warning",
                "voice_plan.segments 中存在不可审计的分段;"
                "发布前不能确认口播分段时长是否覆盖全片。",
            )
        duration = _positive_float(segment.get("duration_sec"))
        if duration is None:
            return QAIssue(
                "RELEASE_VOICE_PLAN_SEGMENT_DURATION_NOT_VERIFIABLE",
                "warning",
                "voice_plan.segments 缺少可审计的 duration_sec;"
                "发布前不能确认每镜口播和字幕节奏。",
            )
        total += duration
    tolerance = _release_duration_tolerance_sec(expected_total)
    drift = abs(total - expected_total)
    if drift > tolerance:
        return QAIssue(
            "RELEASE_VOICE_PLAN_SEGMENT_DURATION_MISMATCH",
            "warning",
            "voice_plan 分段时长总和与计划总时长偏差过大,"
            f"segments_total={total:.2f}s,expected={expected_total:.2f}s,tolerance={tolerance:.2f}s;"
            "可能导致画面分镜、字幕和完整音轨不同步。",
        )
    return None


def _check_voice_plan_source(
    project: ProjectRef,
    manifest: dict,
    report: QAReport,
    strict: bool,
) -> None:
    manifest_provider_id = _manifest_tts_provider_id(manifest)
    if not manifest_provider_id:
        return
    voice_plan = _release_voice_plan(project)
    if not isinstance(voice_plan, dict):
        _add_release_quality_issue(
            report,
            "RELEASE_VOICE_PLAN_MISSING",
            "release manifest 声明包含口播音轨,但缺少 artifacts/voice_plan.json;"
            "无法审计配音 provider、音色、分段和音频来源。",
            strict,
        )
        return
    voice_provider_id = str(voice_plan.get("provider_id") or "")
    segments = voice_plan.get("segments")
    if (
        not voice_provider_id
        or voice_provider_id != manifest_provider_id
        or voice_plan.get("provider_is_mock") is True
        or not isinstance(segments, list)
        or not segments
        or _positive_float(voice_plan.get("total_duration_sec")) is None
        or not _voice_plan_declares_audio_source(project, voice_plan)
    ):
        _add_release_quality_issue(
            report,
            "RELEASE_VOICE_PLAN_NOT_VERIFIABLE",
            "release 口播计划不可审计:"
            "provider、mock 状态、segments、总时长或音频源文件缺失/不匹配。",
            strict,
        )
        return
    duration_issue = _voice_plan_audio_duration_issue(project, voice_plan)
    if duration_issue is not None:
        _add_release_quality_issue(
            report,
            duration_issue.code,
            duration_issue.message_zh,
            strict,
        )
        return
    segment_duration_issue = _voice_plan_segment_duration_issue(voice_plan)
    if segment_duration_issue is not None:
        _add_release_quality_issue(
            report,
            segment_duration_issue.code,
            segment_duration_issue.message_zh,
            strict,
        )


def _voice_settings_fingerprint(settings: object) -> str | None:
    if not isinstance(settings, dict) or not settings:
        return None
    return json.dumps(settings, ensure_ascii=False, sort_keys=True)


def _check_voice_settings_consistency(
    project: ProjectRef,
    report: QAReport,
    strict: bool,
) -> None:
    voice_plan = _release_voice_plan(project)
    if not isinstance(voice_plan, dict):
        return
    provider_id = str(voice_plan.get("provider_id") or "")
    if not provider_id or provider_id == "user_audio" or provider_id in SAMPLE_TTS_PROVIDER_IDS:
        return
    top_voice_id = str(voice_plan.get("voice_id") or "").strip()
    top_settings = _voice_settings_fingerprint(voice_plan.get("provider_voice_settings"))
    segments = [item for item in voice_plan.get("segments", []) if isinstance(item, dict)]
    if not top_voice_id or not top_settings or not segments:
        _add_release_quality_issue(
            report,
            "RELEASE_VOICE_SETTINGS_NOT_VERIFIABLE",
            "发布级配音缺少可审计的固定音色/参数记录;无法证明同片口播音色一致。",
            strict,
        )
        return
    segment_voice_ids: set[str] = set()
    segment_settings: set[str] = set()
    for segment in segments:
        segment_voice_id = str(segment.get("voice_id") or "").strip()
        segment_setting = _voice_settings_fingerprint(segment.get("provider_voice_settings"))
        if not segment_voice_id or not segment_setting:
            _add_release_quality_issue(
                report,
                "RELEASE_VOICE_SETTINGS_NOT_VERIFIABLE",
                "发布级配音 segment 缺少 voice_id 或 provider_voice_settings;"
                "无法证明多镜口播没有音色漂移。",
                strict,
            )
            return
        segment_voice_ids.add(segment_voice_id)
        segment_settings.add(segment_setting)
    if segment_voice_ids != {top_voice_id} or segment_settings != {top_settings}:
        _add_release_quality_issue(
            report,
            "RELEASE_VOICE_SETTINGS_INCONSISTENT",
            "发布级配音不同 segment 的音色或 provider 参数不一致;"
            "同一条视频应固定同一中文音色和参数,避免口播听感漂移。",
            strict,
        )


def _release_duration_tolerance_sec(expected: float) -> float:
    return min(
        max(
            expected * RELEASE_DURATION_TOLERANCE_RATIO,
            RELEASE_DURATION_MIN_TOLERANCE_SEC,
        ),
        RELEASE_DURATION_MAX_TOLERANCE_SEC,
    )


def _check_manifest_voice_duration_consistency(
    project: ProjectRef,
    manifest: dict,
    report: QAReport,
    strict: bool,
) -> None:
    manifest_expected = _manifest_expected_release_duration(manifest)
    if manifest_expected is None:
        return
    voice_plan = _release_voice_plan(project)
    if not isinstance(voice_plan, dict):
        return
    voice_expected = _positive_float(voice_plan.get("total_duration_sec"))
    if voice_expected is None:
        return
    tolerance = _release_duration_tolerance_sec(voice_expected)
    drift = abs(manifest_expected - voice_expected)
    if drift > tolerance:
        _add_release_quality_issue(
            report,
            "RELEASE_MANIFEST_VOICE_DURATION_MISMATCH",
            "render_manifest 的预期时长与 voice_plan.total_duration_sec 不一致,"
            f"manifest={manifest_expected:.2f}s,voice_plan={voice_expected:.2f}s,"
            f"tolerance={tolerance:.2f}s;发布前需要重新渲染或修正过期 manifest。",
            strict,
        )


def _check_release_duration(
    project: ProjectRef,
    video_path: Path,
    manifest: dict,
    report: QAReport,
    strict: bool,
) -> None:
    expected = _expected_release_duration(project, manifest)
    if expected is None:
        return
    _check_manifest_voice_duration_consistency(project, manifest, report, strict)
    actual = _media_duration_sec(video_path)
    if actual is None:
        _add_release_quality_issue(
            report,
            "RELEASE_DURATION_NOT_VERIFIABLE",
            "未能用 ffprobe 验证最终 release 成片时长;发布前需要确认音画没有被截断。",
            strict,
        )
        return
    tolerance = _release_duration_tolerance_sec(expected)
    drift = abs(actual - expected)
    report.info.append(
        QAIssue(
            "RELEASE_DURATION_STATS",
            "info",
            f"最终成片时长体检:actual={actual:.2f}s,expected={expected:.2f}s,drift={drift:.2f}s。",
        )
    )
    if drift > tolerance:
        _add_release_quality_issue(
            report,
            "RELEASE_DURATION_MISMATCH",
            "最终 release 成片时长与口播/分镜预期偏差过大,"
            f"actual={actual:.2f}s,expected={expected:.2f}s,tolerance={tolerance:.2f}s;"
            "可能存在配音被截断、画面拉长或字幕节奏错位。",
            strict,
        )


def _check_scene_caption_cues(
    project: ProjectRef, scene: dict, report: QAReport, strict: bool
) -> None:
    if scene.get("subtitle_burn") is not True:
        return
    caption_timing = scene.get("caption_timing")
    manifest_caption_issue_codes: set[str] = set()
    if isinstance(caption_timing, dict) and caption_timing.get("release_ready") is False:
        issue_code = str(
            caption_timing.get("release_blocker_code")
            or "RELEASE_CAPTION_TIMING_NOT_RELEASE_READY"
        ).strip()
        manifest_caption_issue_codes.add(issue_code)
        next_action = str(caption_timing.get("recovery_next_action_zh") or "").strip()
        if not next_action:
            next_action = (
                "请在 voice_plan 的同镜 caption_cues/timed_captions 中补齐真实"
                " TTS/ASR/人工校准时间戳,重新审阅 voice 后再 release render。"
            )
        _append_caption_timing_blocker(report, scene, issue_code, next_action)
        message = str(caption_timing.get("release_blocker_zh") or "").strip()
        if not message:
            message = (
                "render_manifest 已标记该镜头 caption_timing.release_ready=false;"
                "发布级 strict 必须先修复 timed captions。"
            )
        _add_release_quality_issue(report, issue_code, message, strict)
    if (
        isinstance(caption_timing, dict)
        and caption_timing.get("source") == "voice_segment_invalid"
    ):
        _append_caption_timing_blocker(
            report,
            scene,
            "RELEASE_CAPTION_VOICE_TIMING_INVALID",
            "请修正 voice_plan 中该镜头的 caption_cues/timed_captions 结构,"
            "再重新生成 release 字幕,不能回退为估算 timing。",
        )
        if "RELEASE_CAPTION_VOICE_TIMING_INVALID" not in manifest_caption_issue_codes:
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_VOICE_TIMING_INVALID",
                "voice_plan 提供了口播字幕时间戳,但 render 无法验证其结构;"
                "不能静默回退估算字幕冒充已按真实口播节奏对齐。",
                strict,
            )
        return
    cues = scene.get("caption_cues")
    if not isinstance(cues, list) or not cues:
        _append_caption_timing_blocker(
            report,
            scene,
            "RELEASE_CAPTION_NOT_TIMED",
            "请为该镜头补齐按真实口播节奏拆分的 caption_cues,"
            "每条包含 text、start_sec、end_sec。",
        )
        _add_release_quality_issue(
            report,
            "RELEASE_CAPTION_NOT_TIMED",
            "release 字幕仍缺少按口播节奏拆分的 timed caption cue。",
            strict,
        )
        return
    if _caption_timing_is_estimated(caption_timing, cues):
        _append_caption_timing_blocker(
            report,
            scene,
            "RELEASE_CAPTION_TIMING_IS_ESTIMATED",
            "请用真实 TTS/ASR/人工校准时间戳替换 estimated caption timing,"
            "并写回 voice_plan 的同镜 caption_cues/timed_captions。",
        )
        if "RELEASE_CAPTION_TIMING_IS_ESTIMATED" not in manifest_caption_issue_codes:
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_TIMING_IS_ESTIMATED",
                "release 字幕时间轴仍为估算兜底,不能证明字幕按真实口播节奏出现;"
                "发布级 strict 需要 TTS/ASR/人工校准提供的 timed captions。",
                strict,
            )
    if _voice_duration_aligned_timing_basis_invalid(caption_timing, cues):
        _append_caption_timing_blocker(
            report,
            scene,
            "RELEASE_CAPTION_TIMING_BASIS_NOT_VERIFIABLE",
            "请为 voice_duration_aligned 字幕补齐 timing_basis=real_segment_duration,"
            "并确保每条 cue 来自真实口播段时长。",
        )
        if (
            "RELEASE_CAPTION_TIMING_BASIS_NOT_VERIFIABLE"
            not in manifest_caption_issue_codes
        ):
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_TIMING_BASIS_NOT_VERIFIABLE",
                "release 字幕声明为 voice_duration_aligned,但 manifest/cue 缺少"
                " timing_basis=real_segment_duration;不能证明字幕按真实口播段时长对齐。",
                strict,
            )
    if _voice_plan_caption_cues_not_backed(project, scene, caption_timing, cues):
        _append_caption_timing_blocker(
            report,
            scene,
            "RELEASE_CAPTION_TIMING_NOT_BACKED_BY_VOICE_PLAN",
            "请在 artifacts/voice_plan.json 的同镜 segment 中补齐可匹配的"
            " caption_cues/timed_captions,不能只靠 render_manifest 自证。",
        )
        _add_release_quality_issue(
            report,
            "RELEASE_CAPTION_TIMING_NOT_BACKED_BY_VOICE_PLAN",
            "release 字幕声明来自 voice_plan/真实口播段时长,但 artifacts/voice_plan.json "
            "中找不到同镜头可匹配的 caption_cues/timed_captions;"
            "不能只靠 render_manifest 自证 timed captions。",
            strict,
        )
    scene_duration = _positive_float(scene.get("duration_sec"))
    previous_end_sec: float | None = None
    for cue in cues:
        if not isinstance(cue, dict):
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_NOT_TIMED",
                "release 字幕 cue 结构不可验证。",
                strict,
            )
            return
        lines = cue.get("lines")
        text = str(cue.get("text") or "")
        try:
            start_sec = float(cue.get("start_sec"))
            end_sec = float(cue.get("end_sec"))
        except (TypeError, ValueError):
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_NOT_TIMED",
                "release 字幕 cue 缺少有效起止时间。",
                strict,
            )
            return
        if end_sec <= start_sec:
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_NOT_TIMED",
                "release 字幕 cue 起止时间不合法。",
                strict,
            )
            return
        if start_sec < 0:
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_NOT_TIMED",
                "release 字幕 cue 起始时间不能为负数。",
                strict,
            )
            return
        if (
            previous_end_sec is not None
            and start_sec < previous_end_sec - CAPTION_CUE_OVERLAP_TOLERANCE_SEC
        ):
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_CUE_OVERLAP",
                "release 字幕 cue 时间轴乱序或互相重叠,可能导致多条字幕同时压在画面底部。",
                strict,
            )
            return
        if (
            scene_duration is not None
            and end_sec > scene_duration + CAPTION_SCENE_END_TOLERANCE_SEC
        ):
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_CUE_OUT_OF_SCENE",
                "release 字幕 cue 超出当前镜头时长,可能导致字幕压到下一镜或节奏错位。",
                strict,
            )
            return
        cue_duration = end_sec - start_sec
        if cue_duration > CAPTION_MAX_CUE_SEC:
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_CUE_TOO_LONG",
                "单条字幕 cue 展示时间过长,容易出现整段字幕一直压在底部。",
                strict,
            )
            return
        if len(text) > CAPTION_MAX_TOTAL_CHARS:
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_CUE_TOO_LONG",
                "单条字幕 cue 文本过长,发布级字幕应按口播节奏短句出现。",
                strict,
            )
            return
        if isinstance(lines, list) and any(
            len(str(line)) > CAPTION_MAX_LINE_CHARS for line in lines
        ):
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_CUE_TOO_LONG",
                "字幕单行过长,发布级字幕需要更短的底部安全区 cue。",
                strict,
            )
            return
        reading_units_per_sec = _caption_reading_units(text) / cue_duration
        if reading_units_per_sec > CAPTION_MAX_READING_UNITS_PER_SEC:
            _add_release_quality_issue(
                report,
                "RELEASE_CAPTION_READING_LOAD_TOO_HIGH",
                "单条字幕 cue 在短时间内承载过多文字,发布级字幕需要按口播节奏继续拆短。",
                strict,
            )
            return
        previous_end_sec = end_sec
    if not _caption_matches_spoken_text(scene):
        _add_release_quality_issue(
            report,
            "RELEASE_CAPTION_TEXT_MISMATCH",
            "release 字幕 cue 与口播文本缺少可审计覆盖;发布级中文字幕应承载口播内容。",
            strict,
        )


def _caption_timing_is_estimated(caption_timing: object, cues: list) -> bool:
    if isinstance(caption_timing, dict) and any(
        _caption_timing_marker_is_estimated(caption_timing.get(field))
        for field in ("source", "timing_basis")
    ):
        return True
    return any(
        isinstance(cue, dict)
        and any(
            _caption_timing_marker_is_estimated(cue.get(field))
            for field in ("source", "timing_basis")
        )
        for cue in cues
    )


def _caption_timing_marker_is_estimated(value: object) -> bool:
    return str(value or "").strip().lower() == "estimated"


def _voice_duration_aligned_timing_basis_invalid(
    caption_timing: object,
    cues: list,
) -> bool:
    timing_source = ""
    timing_basis = ""
    if isinstance(caption_timing, dict):
        timing_source = str(caption_timing.get("source") or "").strip()
        timing_basis = str(caption_timing.get("timing_basis") or "").strip()
    aligned_cues = [
        cue
        for cue in cues
        if isinstance(cue, dict)
        and str(cue.get("source") or "").strip()
        == VOICE_DURATION_ALIGNED_CAPTION_SOURCE
    ]
    if timing_source != VOICE_DURATION_ALIGNED_CAPTION_SOURCE and not aligned_cues:
        return False
    if timing_source != VOICE_DURATION_ALIGNED_CAPTION_SOURCE:
        return True
    if timing_basis != VOICE_DURATION_ALIGNED_TIMING_BASIS:
        return True
    if not aligned_cues:
        return True
    return any(
        str(cue.get("timing_basis") or "").strip()
        != VOICE_DURATION_ALIGNED_TIMING_BASIS
        for cue in aligned_cues
    )


def _voice_plan_caption_cues_not_backed(
    project: ProjectRef,
    scene: dict,
    caption_timing: object,
    cues: list,
) -> bool:
    required_sources = _voice_plan_backed_caption_sources(caption_timing, cues)
    if not required_sources:
        return False
    voice_plan = _release_voice_plan(project)
    if not isinstance(voice_plan, dict):
        return False
    scene_id = str(scene.get("scene_id") or scene.get("id") or "").strip()
    if not scene_id:
        return True
    segments = voice_plan.get("segments")
    if not isinstance(segments, list):
        return True
    manifest_cues = [cue for cue in cues if isinstance(cue, dict)]
    if not manifest_cues:
        return True
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        if str(segment.get("scene_id") or segment.get("id") or "").strip() != scene_id:
            continue
        plan_cues = _voice_plan_segment_caption_cues(segment)
        if _voice_plan_cues_cover_manifest_cues(plan_cues, manifest_cues, required_sources):
            return False
    return True


def voice_plan_caption_backing_audit(
    project: ProjectRef,
    scene: dict,
    caption_timing: object,
    cues: list,
) -> dict[str, object]:
    required_sources = _voice_plan_backed_caption_sources(caption_timing, cues)
    audit: dict[str, object] = {"requires_voice_plan": bool(required_sources)}
    if not required_sources:
        return audit
    audit["required_sources"] = sorted(required_sources)
    voice_plan = _release_voice_plan(project)
    if not isinstance(voice_plan, dict):
        audit["voice_plan_segment_found"] = False
        audit["voice_plan_caption_cue_count"] = 0
        audit["voice_plan_backed"] = False
        return audit
    scene_id = str(scene.get("scene_id") or scene.get("id") or "").strip()
    segments = voice_plan.get("segments")
    if not scene_id or not isinstance(segments, list):
        audit["voice_plan_segment_found"] = False
        audit["voice_plan_caption_cue_count"] = 0
        audit["voice_plan_backed"] = False
        return audit
    manifest_cues = [cue for cue in cues if isinstance(cue, dict)]
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        if str(segment.get("scene_id") or segment.get("id") or "").strip() != scene_id:
            continue
        plan_cues = _voice_plan_segment_caption_cues(segment)
        audit["voice_plan_segment_found"] = True
        audit["voice_plan_caption_cue_count"] = len(plan_cues)
        audit["voice_plan_backed"] = (
            bool(manifest_cues)
            and _voice_plan_cues_cover_manifest_cues(
                plan_cues,
                manifest_cues,
                required_sources,
            )
        )
        return audit
    audit["voice_plan_segment_found"] = False
    audit["voice_plan_caption_cue_count"] = 0
    audit["voice_plan_backed"] = False
    return audit


def _voice_plan_backed_caption_sources(caption_timing: object, cues: list) -> set[str]:
    sources: set[str] = set()
    if isinstance(caption_timing, dict):
        source = str(caption_timing.get("source") or "").strip()
        if source in VOICE_PLAN_BACKED_CAPTION_SOURCES:
            sources.add(source)
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        source = str(cue.get("source") or "").strip()
        if source in VOICE_PLAN_BACKED_CAPTION_SOURCES:
            sources.add(source)
    return sources


def _voice_plan_segment_caption_cues(segment: dict) -> list[dict]:
    raw = segment.get("caption_cues")
    if raw is None:
        raw = segment.get("timed_captions")
    if not isinstance(raw, list):
        return []
    return [cue for cue in raw if isinstance(cue, dict)]


def _voice_plan_cues_cover_manifest_cues(
    plan_cues: list[dict],
    manifest_cues: list[dict],
    required_sources: set[str],
) -> bool:
    if not plan_cues:
        return False
    return all(
        any(
            _voice_plan_caption_cue_matches(plan_cue, manifest_cue, required_sources)
            for plan_cue in plan_cues
        )
        for manifest_cue in manifest_cues
    )


def _voice_plan_caption_cue_matches(
    plan_cue: dict,
    manifest_cue: dict,
    required_sources: set[str],
) -> bool:
    if _caption_cue_text(plan_cue) != _caption_cue_text(manifest_cue):
        return False
    plan_start = _caption_cue_time(plan_cue, "start_sec", "start", "begin_sec", "begin")
    plan_end = _caption_cue_time(plan_cue, "end_sec", "end", "finish_sec", "finish")
    manifest_start = _caption_cue_time(
        manifest_cue, "start_sec", "start", "begin_sec", "begin"
    )
    manifest_end = _caption_cue_time(manifest_cue, "end_sec", "end", "finish_sec", "finish")
    if None in {plan_start, plan_end, manifest_start, manifest_end}:
        return False
    match_start = manifest_start
    match_end = manifest_end
    transition_safe_window = manifest_cue.get("transition_safe_window")
    if isinstance(transition_safe_window, dict) and transition_safe_window.get("applied") is True:
        original_start = _caption_cue_time(transition_safe_window, "original_start_sec")
        original_end = _caption_cue_time(transition_safe_window, "original_end_sec")
        if original_start is None or original_end is None:
            return False
        original_duration = original_end - original_start
        manifest_duration = manifest_end - manifest_start
        if original_duration <= 0 or manifest_duration <= 0:
            return False
        if manifest_duration > original_duration + CAPTION_VOICE_PLAN_MATCH_TOLERANCE_SEC:
            return False
        match_start = original_start
        match_end = original_end
    if abs(plan_start - match_start) > CAPTION_VOICE_PLAN_MATCH_TOLERANCE_SEC:
        return False
    if abs(plan_end - match_end) > CAPTION_VOICE_PLAN_MATCH_TOLERANCE_SEC:
        return False
    if VOICE_DURATION_ALIGNED_CAPTION_SOURCE in required_sources:
        return (
            str(plan_cue.get("source") or "").strip()
            == VOICE_DURATION_ALIGNED_CAPTION_SOURCE
            and str(plan_cue.get("timing_basis") or "").strip()
            == VOICE_DURATION_ALIGNED_TIMING_BASIS
        )
    return True


def _caption_cue_text(cue: dict) -> str:
    return " ".join(str(cue.get("text") or cue.get("caption") or "").split()).strip()


def _caption_cue_time(cue: dict, *keys: str) -> float | None:
    for key in keys:
        value = cue.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _caption_reading_units(text: str) -> int:
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    latin_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", text)
    return len(cjk_chars) + len(latin_words) * 2


def _caption_matches_spoken_text(scene: dict) -> bool:
    spoken_text = _scene_spoken_caption_source_text(scene)
    caption_text = _caption_text(scene)
    spoken_tokens = _caption_match_tokens(spoken_text)
    if not spoken_tokens:
        return True
    caption_tokens = _caption_match_tokens(caption_text)
    if not caption_tokens:
        return False
    overlap = len(spoken_tokens & caption_tokens)
    return overlap / len(spoken_tokens) >= 0.55


def _caption_match_tokens(text: str) -> set[str]:
    normalized = str(text or "").lower()
    cjk_text = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    cjk_tokens = {
        cjk_text[index : index + 2]
        for index in range(max(len(cjk_text) - 1, 0))
        if len(cjk_text[index : index + 2]) == 2
    }
    latin_tokens = {
        item
        for item in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", normalized)
        if item not in AUDIO_VISUAL_COMMON_TOKENS
    }
    if cjk_tokens or latin_tokens:
        return cjk_tokens | latin_tokens
    return set(cjk_text)


def _screen_text_duplicates_narration(scene: dict) -> bool:
    screen_text = _scene_screen_text(scene)
    if _caption_reading_units(screen_text) < SCREEN_TEXT_DUPLICATE_MIN_UNITS:
        return False
    spoken_text = _scene_spoken_caption_source_text(scene)
    if not spoken_text:
        return False
    normalized_screen = _compact_text(screen_text)
    normalized_spoken = _compact_text(spoken_text)
    if normalized_screen and normalized_screen in normalized_spoken:
        return True
    screen_tokens = _caption_match_tokens(screen_text)
    spoken_tokens = _caption_match_tokens(spoken_text)
    if not screen_tokens or not spoken_tokens:
        return False
    overlap = len(screen_tokens & spoken_tokens) / max(len(screen_tokens), 1)
    return overlap >= SCREEN_TEXT_DUPLICATE_OVERLAP_RATIO


def _screen_text_too_dense(scene: dict) -> bool:
    return _caption_reading_units(_scene_screen_text(scene)) > SCREEN_TEXT_MAX_UNITS


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _check_scene_video_motion(
    project: ProjectRef,
    scenes: list[dict],
    report: QAReport,
    strict: bool,
) -> None:
    for scene in scenes:
        if scene.get("render_source") != "video":
            continue
        raw_asset_path = scene.get("asset_path")
        if not isinstance(raw_asset_path, str) or not raw_asset_path:
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_MOTION_NOT_VERIFIABLE",
                "视频镜头缺少可复核的动态素材路径,无法证明每镜都有真实运动。",
                strict,
            )
            continue
        scene_asset_path = resolve_inside(project.path, project.path / raw_asset_path)
        motion_delta = _sample_frame_motion_delta(scene_asset_path)
        if motion_delta is None:
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_MOTION_NOT_VERIFIABLE",
                "无法抽帧验证单镜视频素材的运动变化;发布级不能只看整片平均变化。",
                strict,
            )
        elif motion_delta < FRAME_MOTION_DELTA_MIN:
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_MOTION_NOT_DETECTED",
                "单个视频镜头帧变化过低,疑似静止视频或单图转 mp4,不满足发布级动态画面要求。",
                strict,
            )
        else:
            segment_deltas = _sample_frame_motion_segment_deltas(scene_asset_path)
            if segment_deltas is None:
                _add_release_quality_issue(
                    report,
                    "RELEASE_SCENE_MOTION_CONTINUITY_NOT_VERIFIABLE",
                    "无法验证单镜视频素材在前中后段持续运动;发布级镜头不能只靠入场动效。",
                    strict,
                )
            elif any(delta < FRAME_MOTION_SEGMENT_DELTA_MIN for delta in segment_deltas):
                _add_release_quality_issue(
                    report,
                    "RELEASE_SCENE_MOTION_NOT_CONTINUOUS",
                    "单镜视频素材只有局部帧段在动,疑似入场后冻结或短模板停帧。",
                    strict,
                )
        if _scene_keyframe_times(scene):
            keyframe_deltas = _sample_keyframe_motion_deltas(scene_asset_path, scene)
            if keyframe_deltas is None:
                _add_release_quality_issue(
                    report,
                    "RELEASE_SCENE_KEYFRAME_MOTION_NOT_VERIFIABLE",
                    "无法按导演关键帧时间点抽帧验证画面变化;发布级不能只相信分镜文字。",
                    strict,
                )
            elif any(delta < FRAME_MOTION_SEGMENT_DELTA_MIN for delta in keyframe_deltas):
                _add_release_quality_issue(
                    report,
                    "RELEASE_SCENE_KEYFRAME_MOTION_NOT_DETECTED",
                    "导演关键帧相邻画面变化过低,关键帧可能没有被真实执行到视频像素中。",
                    strict,
                )
        scene_duration = _positive_float(scene.get("duration_sec"))
        if scene_duration is None:
            continue
        asset_duration = _media_duration_sec(scene_asset_path)
        if asset_duration is None:
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_VIDEO_DURATION_NOT_VERIFIABLE",
                "无法用 ffprobe 验证单镜视频素材时长;发布级不能只靠 render 后拉伸结果。",
                strict,
            )
            continue
        min_duration = scene_duration * SCENE_VIDEO_MIN_DURATION_RATIO
        if asset_duration + SCENE_VIDEO_DURATION_TOLERANCE_SEC < min_duration:
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_VIDEO_TOO_SHORT_FOR_DURATION",
                "单镜视频素材时长明显短于镜头时长,疑似短循环/模板片段被拉长;"
                "发布级每镜需要足够覆盖口播节奏的动态视频资产。",
                strict,
            )


def _sample_keyframe_motion_deltas(path: Path, scene: dict) -> list[float] | None:
    times = _scene_keyframe_times(scene)
    if len(times) < 2:
        return []
    frames = [_sample_frame_rgb(path, f"{time_sec:.2f}") for time_sec in times]
    if any(frame is None for frame in frames):
        return None
    deltas: list[float] = []
    for first, second in zip(frames, frames[1:], strict=False):
        if first is None or second is None:
            return None
        deltas.append(_frame_delta(first, second))
    return deltas


def _scene_keyframe_times(scene: dict) -> list[float]:
    keyframes = _scene_keyframes(scene)
    times = []
    scene_duration = _positive_float(scene.get("duration_sec"))
    for keyframe in keyframes:
        parsed = _keyframe_time_sec(keyframe)
        if parsed is None:
            continue
        if scene_duration is not None:
            parsed = min(parsed, scene_duration)
        times.append(max(parsed, 0.0))
    return sorted(dict.fromkeys(times))


def _scene_keyframes(scene: dict) -> list[object]:
    direct = scene.get("keyframes") or scene.get("keyframe_beats")
    if isinstance(direct, list):
        return [item for item in direct if item is not None]
    for sheet in _scene_review_sheets(scene):
        sheet_keyframes = sheet.get("keyframes") or sheet.get("keyframe_beats")
        if isinstance(sheet_keyframes, list):
            return [item for item in sheet_keyframes if item is not None]
    return []


def _keyframe_time_sec(value: object) -> float | None:
    if isinstance(value, dict):
        for key in ("time_sec", "time", "at_sec", "at"):
            parsed = _non_negative_float(value.get(key))
            if parsed is not None:
                return parsed
    return _non_negative_float(value)


def _non_negative_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip().removesuffix("s").strip())
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _check_scene_visual_repetition(
    project: ProjectRef,
    scenes: list[dict],
    report: QAReport,
    strict: bool,
) -> None:
    fingerprints: list[tuple[str, tuple[int, ...]]] = []
    for scene in scenes:
        if scene.get("render_source") != "video":
            continue
        raw_asset_path = scene.get("asset_path")
        if not isinstance(raw_asset_path, str) or not raw_asset_path:
            continue
        scene_asset_path = resolve_inside(project.path, project.path / raw_asset_path)
        fingerprint = _visual_fingerprint(scene_asset_path)
        if fingerprint is None:
            continue
        scene_id = str(scene.get("scene_id") or raw_asset_path)
        fingerprints.append((scene_id, fingerprint))
    for index, (scene_id, fingerprint) in enumerate(fingerprints):
        for other_scene_id, other_fingerprint in fingerprints[index + 1:]:
            distance = _fingerprint_distance(fingerprint, other_fingerprint)
            if distance <= VISUAL_FINGERPRINT_MAX_HAMMING_DISTANCE:
                _add_release_quality_issue(
                    report,
                    "RELEASE_SCENE_VISUAL_REPEATED",
                    f"镜头 {scene_id} 与 {other_scene_id} 抽帧视觉指纹高度相似;"
                    "发布级视频不能用重复画面或同构图模板换字冒充多镜头。",
                    strict,
                )
                return


def _check_transition_rendering(
    manifest: dict,
    scenes: list[dict],
    video_path: Path,
    report: QAReport,
    strict: bool,
) -> None:
    if len(scenes) < 2:
        return
    has_transition_plan = any(scene.get("transition_plan") for scene in scenes)
    if not has_transition_plan:
        return
    transition_rendering = manifest.get("transition_rendering")
    rendered = (
        isinstance(transition_rendering, dict)
        and transition_rendering.get("rendered") is True
    )
    if not rendered:
        _add_release_quality_issue(
            report,
            "RELEASE_TRANSITION_NOT_RENDERED",
            "导演契约包含转场计划,但 render manifest 未证明真实跨镜转场已渲染;"
            "当前不能只用硬拼 concat 通过 strict。",
            strict,
        )
        return
    expected_count = len(scenes) - 1
    transitions = transition_rendering.get("transitions")
    try:
        transition_count = int(transition_rendering.get("transition_count") or 0)
    except (TypeError, ValueError):
        transition_count = 0
    if (
        not isinstance(transitions, list)
        or len(transitions) < expected_count
        or transition_count < expected_count
    ):
        _add_release_quality_issue(
            report,
            "RELEASE_TRANSITION_RENDERING_INCOMPLETE",
            "render manifest 未证明每个跨镜切点都真实渲染了转场。",
            strict,
        )
        return
    if not _transition_timing_is_verifiable(transitions, scenes, expected_count):
        _add_release_quality_issue(
            report,
            "RELEASE_TRANSITION_TIMING_NOT_VERIFIABLE",
            "render manifest 的转场 from/to、offset 或 duration 不可验证;"
            "发布级转场必须证明每个切点真实落在时间轴上。",
            strict,
        )
        return
    if not _transition_caption_boundaries_are_clear(transitions, scenes, expected_count):
        _add_release_quality_issue(
            report,
            "RELEASE_TRANSITION_CAPTION_CUTS_CUE",
            "真实跨镜转场与 timed caption cue 时间窗重叠;"
            "发布级转场不能切在口播字幕短句中,需要把字幕 cue 收在转场前或延后到转场后。",
            strict,
        )
        return
    if not _transition_semantic_xfade_is_verifiable(transitions, scenes, expected_count):
        _add_release_quality_issue(
            report,
            "RELEASE_TRANSITION_SEMANTIC_MISMATCH",
            "render manifest 的实际 xfade 与导演语义转场 family 不一致;"
            "发布级转场不能只写语义计划,还必须真实渲染对应转场。",
            strict,
        )
        return
    if not _transition_visual_diversity_is_verifiable(transitions, expected_count):
        _add_release_quality_issue(
            report,
            "RELEASE_TRANSITION_VISUAL_TOO_UNIFORM",
            "多个跨镜切点实际转场变化不足或相邻重复,转场观感过于单一。",
            strict,
        )
        return
    if not _transition_pixel_evidence_is_verifiable(
        video_path, transitions, expected_count
    ):
        _add_release_quality_issue(
            report,
            "RELEASE_TRANSITION_PIXEL_EVIDENCE_NOT_VERIFIABLE",
            "render manifest 声明已渲染 xfade,但最终视频转场窗口无法抽帧或像素变化过低;"
            "发布级转场必须用成片抽帧证明真实跨镜变化。",
            strict,
        )


def _transition_visual_diversity_is_verifiable(
    transitions: list,
    expected_count: int,
) -> bool:
    if expected_count < 2:
        return True
    selected = transitions[:expected_count]
    families: list[str] = []
    xfade_names: list[str] = []
    for item in selected:
        if not isinstance(item, dict):
            return False
        families.append(str(item.get("family") or "").strip())
        xfade_names.append(str(item.get("xfade") or "").strip())
    for previous, current in zip(xfade_names, xfade_names[1:], strict=False):
        if previous and current and previous == current:
            return False
    for previous, current in zip(families, families[1:], strict=False):
        if previous and current and previous == current:
            return False
    min_distinct = min(expected_count, 3)
    return len({name for name in xfade_names if name}) >= min_distinct


def _transition_pixel_evidence_is_verifiable(
    video_path: Path,
    transitions: list,
    expected_count: int,
) -> bool:
    if not video_path.is_file():
        return False
    for item in transitions[:expected_count]:
        if not isinstance(item, dict):
            return False
        duration_sec = _positive_float(item.get("duration_sec"))
        offset_sec = _float_or_none(item.get("offset_sec"))
        if duration_sec is None or offset_sec is None or offset_sec < 0:
            return False
        frames = [
            _sample_frame_rgb(video_path, f"{timestamp:.2f}")
            for timestamp in _transition_pixel_sample_timestamps(
                offset_sec, duration_sec
            )
        ]
        if any(frame is None for frame in frames):
            return False
        first, middle, last = frames
        if first is None or middle is None or last is None:
            return False
        if (
            _frame_delta(first, middle) < TRANSITION_PIXEL_DELTA_MIN
            or _frame_delta(middle, last) < TRANSITION_PIXEL_DELTA_MIN
        ):
            return False
    return True


def _transition_pixel_sample_timestamps(
    offset_sec: float,
    duration_sec: float,
) -> tuple[float, float, float]:
    return (
        max(offset_sec + duration_sec * 0.15, 0.01),
        max(offset_sec + duration_sec * 0.50, 0.01),
        max(offset_sec + duration_sec * 0.85, 0.01),
    )


def _transition_timing_is_verifiable(
    transitions: list,
    scenes: list[dict],
    expected_count: int,
) -> bool:
    total_duration = 0.0
    scene_ids: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        duration_sec = _positive_float(scene.get("duration_sec"))
        if duration_sec is None:
            return False
        total_duration += duration_sec
        scene_ids.append(str(scene.get("scene_id") or scene.get("id") or f"s{index}"))
    previous_offset: float | None = None
    for index, item in enumerate(transitions[:expected_count]):
        if not isinstance(item, dict):
            return False
        if str(item.get("from_scene_id") or "") != scene_ids[index]:
            return False
        if str(item.get("to_scene_id") or "") != scene_ids[index + 1]:
            return False
        if not str(item.get("xfade") or "").strip():
            return False
        duration_sec = _positive_float(item.get("duration_sec"))
        offset_sec = _positive_float(item.get("offset_sec"))
        if duration_sec is None or offset_sec is None:
            return False
        if duration_sec < TRANSITION_MIN_VISIBLE_SEC:
            return False
        if (
            previous_offset is not None
            and offset_sec <= previous_offset + TRANSITION_TIMING_TOLERANCE_SEC
        ):
            return False
        if offset_sec + duration_sec > total_duration + TRANSITION_TIMING_TOLERANCE_SEC:
            return False
        previous_offset = offset_sec
    return True


def _transition_caption_boundaries_are_clear(
    transitions: list,
    scenes: list[dict],
    expected_count: int,
) -> bool:
    for index, item in enumerate(transitions[:expected_count]):
        if not isinstance(item, dict):
            return False
        transition_duration = _positive_float(item.get("duration_sec"))
        outgoing_duration = _positive_float(scenes[index].get("duration_sec"))
        if transition_duration is None or outgoing_duration is None:
            return False
        outgoing_overlap_start = max(outgoing_duration - transition_duration, 0.0)
        if _caption_cues_overlap_window(
            scenes[index], outgoing_overlap_start, outgoing_duration
        ):
            return False
        if _caption_cues_overlap_window(scenes[index + 1], 0.0, transition_duration):
            return False
    return True


def _caption_cues_overlap_window(scene: dict, start_sec: float, end_sec: float) -> bool:
    if scene.get("subtitle_burn") is not True:
        return False
    cues = scene.get("caption_cues")
    if not isinstance(cues, list):
        return False
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        cue_start = _float_or_none(cue.get("start_sec"))
        cue_end = _float_or_none(cue.get("end_sec"))
        if cue_start is None or cue_end is None or cue_end <= cue_start:
            continue
        if (
            cue_start < end_sec - CAPTION_CUE_OVERLAP_TOLERANCE_SEC
            and cue_end > start_sec + CAPTION_CUE_OVERLAP_TOLERANCE_SEC
        ):
            return True
    return False


def _float_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _transition_semantic_xfade_is_verifiable(
    transitions: list,
    scenes: list[dict],
    expected_count: int,
) -> bool:
    for index, item in enumerate(transitions[:expected_count], start=1):
        if not isinstance(item, dict):
            return False
        target_scene = scenes[index]
        plan = target_scene.get("transition_plan")
        if not isinstance(plan, dict):
            continue
        family = str(plan.get("family") or plan.get("intent") or "").strip()
        if not family:
            continue
        manifest_family = str(item.get("family") or "").strip()
        if manifest_family and manifest_family != family:
            return False
        expected_xfade = xfade_name_for_transition_family(family, index)
        if str(item.get("xfade") or "").strip() != expected_xfade:
            return False
    return True


def _check_visual_evidence_assets(
    project: ProjectRef,
    manifest: dict,
    scenes: list[dict],
    report: QAReport,
    strict: bool,
) -> None:
    if not any(_scene_requires_real_evidence(scene) for scene in scenes):
        return
    evidence_manifest = manifest.get("visual_evidence_assets")
    if not isinstance(evidence_manifest, dict) or not evidence_manifest.get("assets"):
        _add_release_quality_issue(
            report,
            "RELEASE_VISUAL_EVIDENCE_ASSETS_MISSING",
            "导演契约要求真实证据画面,但 render manifest 缺少 evidence_assets 清单。",
            strict,
        )
        return
    evidence_types = {
        str(item)
        for item in evidence_manifest.get("evidence_types", [])
        if isinstance(item, str) and item
    }
    if _has_open_source_scene(scenes) and len(evidence_types) < OPEN_SOURCE_MIN_EVIDENCE_TYPES:
        _add_release_quality_issue(
            report,
            "RELEASE_VISUAL_EVIDENCE_ASSETS_TOO_THIN",
            "开源项目介绍片证据素材类型不足;至少需要 3 类 GitHub/README/终端/QA/导出等证据来源。",
            strict,
        )
    if _has_open_source_scene(scenes):
        generated_styles = {
            str(asset.get("evidence_clip_style"))
            for asset in evidence_manifest.get("assets", [])
            if isinstance(asset, dict)
            and asset.get("evidence_clip_status") in {"generated", "captured"}
            and asset.get("evidence_clip_style")
        }
        if len(generated_styles) < OPEN_SOURCE_MIN_EVIDENCE_TYPES:
            _add_release_quality_issue(
                report,
                "RELEASE_VISUAL_EVIDENCE_CLIPS_TOO_UNIFORM",
                "开源项目介绍片动态证据短片样式过于单一;"
                "README/QA/render/export 等证据需要差异化镜头呈现。",
                strict,
            )
        if not any(
            isinstance(asset, dict)
            and _evidence_clip_has_recording_visual_source(project, asset)
            for asset in evidence_manifest.get("assets", [])
        ):
            _add_release_quality_issue(
                report,
                "RELEASE_VISUAL_EVIDENCE_RECORDING_MISSING",
                "开源项目介绍片至少需要一段可 ffprobe 验证的真实动态录屏证据;"
                "截图扫描、终端文字回放或生成式证据卡只能作辅助,不能单独满足发布级画面。",
                strict,
            )
    for scene in scenes:
        if not _scene_requires_real_evidence(scene):
            continue
        refs = scene.get("evidence_asset_refs")
        if not isinstance(refs, list) or not refs:
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_EVIDENCE_ASSET_UNBOUND",
                "分镜要求真实证据素材,但该镜头没有绑定任何 evidence asset。",
                strict,
            )
            continue
        refs = _merged_scene_evidence_refs(refs, evidence_manifest)
        if _evidence_refs_target_other_scene(refs, scene):
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_EVIDENCE_TARGET_MISMATCH",
                "分镜绑定的 evidence asset 属于其它镜头;"
                "不能把一段录屏跨镜复用来满足当前镜头的真实证据要求。",
                strict,
            )
        if _evidence_refs_missing_scene_target(refs, scene):
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_EVIDENCE_TARGET_UNBOUND",
                "分镜绑定的真实录屏 evidence asset 缺少 target_scene_id;"
                "发布级录屏证据必须用 --scene-id 绑定到当前镜头,不能作为全片通用素材复用。",
                strict,
            )
        has_generated_video = any(
            isinstance(ref, dict)
            and _evidence_clip_video_is_verifiable(project, ref)
            for ref in refs
        )
        if not has_generated_video:
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED",
                "分镜要求真实证据画面,但绑定的 evidence asset 尚未物化为"
                "可 ffprobe 验证的视频证据镜头。",
                strict,
            )
            continue
        if _scene_requires_captured_evidence_video(scene) and not any(
            isinstance(ref, dict)
            and ref.get("evidence_clip_status") == "captured"
            and _evidence_clip_video_is_verifiable(project, ref)
            for ref in refs
        ):
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC",
                "实证型内容镜头不能只依赖生成式证据卡;"
                "产品界面、操作流程、评测过程或商品实拍必须绑定用户录屏/屏幕录制类视频证据。",
                strict,
            )
        if _has_open_source_scene([scene]) and not any(
            isinstance(ref, dict)
            and _evidence_clip_has_non_text_visual_source(project, ref)
            for ref in refs
        ):
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC",
                "开源项目介绍镜头不能只依赖 text_card 证据短片;"
                "至少需要截图扫描、终端回放或真实录屏等非文字卡视觉证据来源。",
                strict,
            )
        if _has_open_source_scene([scene]) and not any(
            isinstance(ref, dict)
            and _evidence_clip_has_recording_visual_source(project, ref)
            for ref in refs
        ):
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_EVIDENCE_RECORDING_MISSING",
                "开源项目介绍镜头不能借用其它镜头的录屏证据;"
                "该镜头自身至少需要绑定一段可 ffprobe 验证的网页/终端/Codex/屏幕录屏。",
                strict,
            )
        if _has_open_source_scene([scene]) and not _recording_evidence_refs_match_expected(
            project, refs, scene.get("expected_real_evidence")
        ):
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_EVIDENCE_RECORDING_TYPE_MISMATCH",
                "开源项目介绍镜头绑定的真实录屏类型与 expected_real_evidence 不匹配;"
                "不能用无关录屏给当前镜头的 GitHub/README/Codex/终端/QA 证据背书。",
                strict,
            )
        recording_status_issue = _recording_evidence_status_issue(refs, evidence_manifest)
        if (
            (_has_open_source_scene([scene]) or _scene_requires_captured_evidence_video(scene))
            and recording_status_issue is not None
        ):
            code, message = recording_status_issue
            _add_release_quality_issue(report, code, message, strict)
        recording_consent_issue = _recording_evidence_consent_issue(refs, evidence_manifest)
        if (
            (_has_open_source_scene([scene]) or _scene_requires_captured_evidence_video(scene))
            and recording_consent_issue is not None
        ):
            code, message = recording_consent_issue
            _add_release_quality_issue(report, code, message, strict)
        recording_intent_issue = _recording_evidence_intent_issue(
            project, refs, scene, evidence_manifest
        )
        if (
            (_has_open_source_scene([scene]) or _scene_requires_captured_evidence_video(scene))
            and recording_intent_issue is not None
        ):
            code, message = recording_intent_issue
            _add_release_quality_issue(report, code, message, strict)
        recording_duration_issue = _recording_evidence_duration_issue(
            project,
            refs,
            _positive_float(scene.get("duration_sec")),
        )
        if (
            (_has_open_source_scene([scene]) or _scene_requires_captured_evidence_video(scene))
            and recording_duration_issue is not None
        ):
            code, message = recording_duration_issue
            _add_release_quality_issue(report, code, message, strict)
        recording_motion_issue = _recording_evidence_motion_issue(project, refs)
        if (
            (_has_open_source_scene([scene]) or _scene_requires_captured_evidence_video(scene))
            and recording_motion_issue is not None
        ):
            code, message = recording_motion_issue
            _add_release_quality_issue(report, code, message, strict)
        if (
            (_has_open_source_scene([scene]) or _scene_requires_captured_evidence_video(scene))
            and not _scene_consumes_evidence_primary_visual(
                project, scene, refs, evidence_manifest
            )
        ):
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_EVIDENCE_PRIMARY_VISUAL_NOT_CONSUMED",
                "分镜绑定了可验证的真实录屏 evidence,但最终镜头主画面没有证明消费该录屏;"
                "asset_path 必须直接使用绑定的 evidence mp4,或宿主生成契约回写 "
                "evidence_media_hero_kind=video、evidence_media_hero_role=primary_visual "
                "且 template_body_suppressed_for_evidence=true。",
                strict,
            )
        if (
            (_has_open_source_scene([scene]) or _scene_requires_captured_evidence_video(scene))
            and not _evidence_refs_match_expected(
                project, refs, scene.get("expected_real_evidence")
            )
        ):
            profile = _scene_profile(scene)
            profile_label = (
                "开源项目介绍镜头" if profile == "open_source_project_intro" else "实证型内容镜头"
            )
            _add_release_quality_issue(
                report,
                "RELEASE_SCENE_EVIDENCE_TYPE_MISMATCH",
                f"{profile_label}绑定的 evidence asset 与 expected_real_evidence 不匹配;"
                "不能拿无关证据视频满足该镜头的真实证据要求。",
                strict,
            )


def _profile_required_evidence(manifest: dict) -> list[str]:
    evidence = manifest.get("profile_required_evidence")
    if evidence is None:
        preset = manifest.get("profile_preset")
        if isinstance(preset, dict):
            evidence = preset.get("required_evidence")
    if not isinstance(evidence, list):
        return []
    return [str(item).strip() for item in evidence if str(item).strip()]


def _profile_evidence_coverage_text(scenes: list[dict]) -> str:
    markers: list[str] = []
    for scene in scenes:
        markers.extend(_text_markers_from(scene.get("expected_real_evidence")))
        strategy = scene.get("asset_strategy_v2")
        if isinstance(strategy, dict):
            markers.extend(_text_markers_from(strategy.get("required_evidence")))
            markers.extend(_text_markers_from(strategy.get("evidence_plan")))
        refs = scene.get("director_knowledge_refs")
        if isinstance(refs, dict):
            markers.extend(_text_markers_from(refs))
        for sheet in _scene_review_sheets(scene):
            markers.extend(_text_markers_from(sheet.get("asset_status")))
            markers.extend(_text_markers_from(sheet.get("asset_source")))
    return " ".join(markers)


def _check_profile_required_evidence_coverage(
    manifest: dict,
    scenes: list[dict],
    report: QAReport,
    strict: bool,
) -> None:
    required = _profile_required_evidence(manifest)
    if not required:
        return
    coverage_text = _profile_evidence_coverage_text(scenes)
    missing = [item for item in required if item not in coverage_text]
    if not missing:
        return
    _add_release_quality_issue(
        report,
        "RELEASE_PROFILE_EVIDENCE_COVERAGE_INCOMPLETE",
        "内容类型 Profile 要求的素材/证据没有进入每镜导演契约;"
        f"缺少: {'、'.join(missing)}。",
        strict,
    )


def _evidence_clip_video_is_verifiable(project: ProjectRef, ref: dict) -> bool:
    if ref.get("evidence_clip_status") not in {"generated", "captured"}:
        return False
    raw_path = str(ref.get("evidence_clip_path") or "")
    if Path(raw_path).suffix.lower() not in SOURCE_VIDEO_EXTENSIONS:
        return False
    resolved = resolve_inside(project.path, project.path / raw_path)
    if not resolved.is_file():
        return False
    has_video, _ = _media_streams_are_verifiable(resolved)
    return has_video


def _evidence_refs_target_other_scene(refs: list, scene: dict) -> bool:
    scene_id = str(scene.get("scene_id") or scene.get("id") or "").strip()
    if not scene_id:
        return False
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        target_scene_id = str(ref.get("target_scene_id") or "").strip()
        if target_scene_id and target_scene_id != scene_id:
            return True
    return False


def _evidence_refs_missing_scene_target(refs: list, scene: dict) -> bool:
    scene_id = str(scene.get("scene_id") or scene.get("id") or "").strip()
    if not scene_id:
        return False
    return any(
        isinstance(ref, dict)
        and _evidence_ref_is_captured_dynamic(ref)
        and not str(ref.get("target_scene_id") or "").strip()
        for ref in refs
    )


def _merged_scene_evidence_refs(refs: list, evidence_manifest: dict) -> list[dict]:
    lookup = _evidence_asset_lookup(evidence_manifest)
    return [
        _merged_evidence_ref(ref, lookup)
        for ref in refs
        if isinstance(ref, dict)
    ]


def _evidence_ref_is_captured_dynamic(ref: dict) -> bool:
    if ref.get("evidence_clip_status") != "captured":
        return False
    evidence_type = str(ref.get("evidence_type") or "")
    visual_source = str(ref.get("evidence_visual_source") or "")
    return (
        evidence_type in CAPTURED_DYNAMIC_EVIDENCE_TYPES
        or visual_source in OPEN_SOURCE_RECORDING_EVIDENCE_SOURCES
    )


def _recording_evidence_status_issue(
    refs: list, evidence_manifest: dict
) -> tuple[str, str] | None:
    lookup = _evidence_asset_lookup(evidence_manifest)
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        merged_ref = _merged_evidence_ref(ref, lookup)
        if not _evidence_ref_is_captured_dynamic(merged_ref):
            continue
        recording_status = str(merged_ref.get("recording_status") or "").strip()
        if recording_status and recording_status != "captured":
            return (
                "RELEASE_SCENE_EVIDENCE_RECORDING_STATUS_NOT_CAPTURED",
                "分镜绑定的动态 evidence 声明为 captured,但录屏本体验证状态不是 captured;"
                "不能把失败、未授权或不可验证的录屏素材当作发布级真实动态证据。",
            )
    return None


def _recording_evidence_consent_issue(
    refs: list, evidence_manifest: dict
) -> tuple[str, str] | None:
    lookup = _evidence_asset_lookup(evidence_manifest)
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        merged_ref = _merged_evidence_ref(ref, lookup)
        if not _evidence_ref_is_captured_dynamic(merged_ref):
            continue
        if not _evidence_ref_requires_screen_recording_consent(merged_ref):
            continue
        if merged_ref.get("screen_recording_consent_required") is not True:
            return (
                "RELEASE_SCENE_EVIDENCE_SCREEN_RECORDING_CONSENT_NOT_VERIFIABLE",
                "分镜绑定了 Codex/屏幕录屏 evidence,但缺少可审计的录屏授权要求;"
                "发布级真实屏幕证据必须记录 screen_recording_consent_required=true。",
            )
        if merged_ref.get("screen_recording_consent") is not True:
            return (
                "RELEASE_SCENE_EVIDENCE_SCREEN_RECORDING_CONSENT_MISSING",
                "分镜绑定了 Codex/屏幕录屏 evidence,但没有证明用户已授权录制或提供该屏幕录屏;"
                "不能把未授权或授权状态不明的屏幕录屏当作发布级真实动态证据。",
            )
    return None


def _evidence_ref_requires_screen_recording_consent(ref: dict) -> bool:
    evidence_type = str(ref.get("evidence_type") or ref.get("type") or "").strip()
    visual_source = str(ref.get("evidence_visual_source") or "").strip()
    role = str(ref.get("role") or "").strip().lower()
    if evidence_type in SCREEN_RECORDING_CONSENT_EVIDENCE_TYPES:
        return True
    if visual_source in SCREEN_RECORDING_CONSENT_VISUAL_SOURCES:
        return True
    return evidence_type == "screen_recording_capture" and role in SCREEN_RECORDING_CONSENT_ROLES


def _recording_evidence_duration_issue(
    project: ProjectRef,
    refs: list,
    scene_duration_sec: float | None,
) -> tuple[str, str] | None:
    recording_refs = [
        ref
        for ref in refs
        if isinstance(ref, dict)
        and _evidence_clip_has_captured_dynamic_visual_source(project, ref)
    ]
    if not recording_refs:
        return None
    min_duration = _minimum_recording_evidence_duration(scene_duration_sec)
    saw_duration = False
    for ref in recording_refs:
        duration = _evidence_clip_duration_sec(project, ref)
        if duration is None:
            continue
        saw_duration = True
        if duration + SCENE_VIDEO_DURATION_TOLERANCE_SEC >= min_duration:
            return None
    if saw_duration:
        return (
            "RELEASE_SCENE_EVIDENCE_RECORDING_TOO_SHORT",
            "分镜绑定的真实录屏证据过短;"
            f"至少需要 {min_duration:.1f}s 的可验证录屏支撑当前镜头,"
            "不能用瞬间闪屏或极短片段给发布级证据镜头背书。",
        )
    return (
        "RELEASE_SCENE_EVIDENCE_RECORDING_DURATION_NOT_VERIFIABLE",
        "分镜绑定的真实录屏证据虽有视频流,但 ffprobe 未能读取时长;"
        "无法确认录屏足够支撑当前镜头。",
    )


def _recording_evidence_motion_issue(
    project: ProjectRef,
    refs: list,
) -> tuple[str, str] | None:
    recording_paths = [
        path
        for ref in refs
        if isinstance(ref, dict)
        and _evidence_clip_has_captured_dynamic_visual_source(project, ref)
        for path in [_evidence_clip_project_path(project, ref)]
        if path is not None
    ]
    if not recording_paths:
        return None
    for path in recording_paths:
        motion_delta = _sample_frame_motion_delta(path)
        if motion_delta is None:
            return (
                "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_VERIFIABLE",
                "分镜绑定的真实录屏 evidence 虽有视频流,但无法抽帧验证画面运动;"
                "不能只靠 ffprobe 和时长给发布级动态证据镜头背书。",
            )
        if motion_delta < FRAME_MOTION_DELTA_MIN:
            return (
                "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_DETECTED",
                "分镜绑定的真实录屏 evidence 帧变化过低,疑似静止录屏或单帧转 mp4;"
                "发布级证据镜头需要真实动态操作/页面/终端画面。",
            )
        segment_deltas = _sample_frame_motion_segment_deltas(path)
        if segment_deltas is None:
            return (
                "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_VERIFIABLE",
                "无法验证真实录屏 evidence 在前中后段持续运动;"
                "发布级证据素材不能只靠瞬间变化或静止片段。",
            )
        if any(delta < FRAME_MOTION_SEGMENT_DELTA_MIN for delta in segment_deltas):
            return (
                "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_CONTINUOUS",
                "真实录屏 evidence 只有局部帧段在动,疑似短动作后冻结;"
                "发布级证据镜头需要足够覆盖口播节奏的动态画面。",
            )
    return None


def _evidence_clip_project_path(project: ProjectRef, ref: dict) -> Path | None:
    raw_path = str(ref.get("evidence_clip_path") or "")
    if Path(raw_path).suffix.lower() not in SOURCE_VIDEO_EXTENSIONS:
        return None
    try:
        resolved = resolve_inside(project.path, project.path / raw_path)
    except LingjianError:
        return None
    return resolved if resolved.is_file() else None


def _scene_consumes_evidence_primary_visual(
    project: ProjectRef, scene: dict, refs: list, evidence_manifest: dict
) -> bool:
    lookup = _evidence_asset_lookup(evidence_manifest)
    recording_refs = [
        _merged_evidence_ref(ref, lookup)
        for ref in refs
        if isinstance(ref, dict)
    ]
    recording_refs = [
        ref
        for ref in recording_refs
        if _evidence_clip_has_captured_dynamic_visual_source(project, ref)
    ]
    if not recording_refs:
        return True
    return _scene_asset_matches_evidence_clip(project, scene, recording_refs) or (
        _host_contract_declares_evidence_primary_visual(
            scene.get("host_generation_contract"), len(recording_refs)
        )
    )


def _scene_asset_matches_evidence_clip(
    project: ProjectRef, scene: dict, refs: list[dict]
) -> bool:
    asset_path = _project_relative_path(project, scene.get("asset_path"))
    if asset_path is None:
        return False
    for ref in refs:
        evidence_path = _project_relative_path(project, ref.get("evidence_clip_path"))
        if evidence_path and evidence_path == asset_path:
            return True
    return False


def _host_contract_declares_evidence_primary_visual(
    contract: object, required_count: int
) -> bool:
    if not isinstance(contract, dict):
        return False
    try:
        evidence_media_count = int(contract.get("evidence_media_count"))
    except (TypeError, ValueError):
        evidence_media_count = 0
    return (
        evidence_media_count >= max(required_count, 1)
        and str(contract.get("evidence_media_hero_kind") or "") == "video"
        and str(contract.get("evidence_media_hero_role") or "") == "primary_visual"
        and contract.get("template_body_suppressed_for_evidence") is True
        and contract.get("contract_confirmed_by_generator") is True
    )


def _project_relative_path(project: ProjectRef, value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = project.path / candidate
    try:
        resolved = resolve_inside(project.path, candidate)
        return str(resolved.relative_to(project.path))
    except (OSError, ValueError, LingjianError):
        return None


def _minimum_recording_evidence_duration(scene_duration_sec: float | None) -> float:
    if scene_duration_sec is None:
        return EVIDENCE_RECORDING_MIN_DURATION_SEC
    return max(
        EVIDENCE_RECORDING_MIN_DURATION_SEC,
        scene_duration_sec * EVIDENCE_RECORDING_MIN_SCENE_RATIO,
    )


def _evidence_clip_duration_sec(project: ProjectRef, ref: dict) -> float | None:
    resolved = _evidence_clip_project_path(project, ref)
    if resolved is None:
        return None
    return _media_duration_sec(resolved)


def _recording_evidence_refs_match_expected(
    project: ProjectRef, refs: list, expected_real_evidence: object
) -> bool:
    expected_groups = _expected_recording_evidence_type_groups(expected_real_evidence)
    if not expected_groups:
        return True
    materialized_recording_types = {
        str(ref.get("evidence_type") or "")
        for ref in refs
        if isinstance(ref, dict) and _evidence_clip_has_recording_visual_source(project, ref)
    }
    return all(materialized_recording_types & group for group in expected_groups)


def _recording_evidence_intent_issue(
    project: ProjectRef, refs: list, scene: dict, evidence_manifest: dict
) -> tuple[str, str] | None:
    marker_groups = _recording_intent_marker_groups_for_scene(scene)
    if not marker_groups:
        return None
    lookup = _evidence_asset_lookup(evidence_manifest)
    recording_refs = [
        _merged_evidence_ref(ref, lookup)
        for ref in refs
        if isinstance(ref, dict)
    ]
    recording_refs = [
        ref
        for ref in recording_refs
        if _evidence_clip_has_captured_dynamic_visual_source(project, ref)
    ]
    if not recording_refs:
        return None
    task_texts = [
        task_text
        for task_text in (_recording_task_intent_text(ref) for ref in recording_refs)
        if task_text
    ]
    if task_texts and any(
        _recording_task_matches_marker_groups(task_text, marker_groups)
        for task_text in task_texts
    ):
        return None
    return (
        "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE",
        "分镜绑定的真实录屏缺少与本镜 expected_real_evidence / asset_recipe_id "
        "匹配的脱敏任务意图;不能只靠录屏 evidence 类型、ffprobe、时长或运动证据给发布级"
        "实证镜头背书。",
    )


def _recording_intent_marker_groups_for_scene(scene: dict) -> list[tuple[str, ...]]:
    keys = _recording_intent_scene_keys(scene)
    for key in keys:
        groups = RECORDING_INTENT_MARKER_GROUPS_BY_SCENE_KEY.get(key)
        if groups:
            return [tuple(group) for group in groups]
    expected_text = " ".join(_text_markers_from(scene.get("expected_real_evidence"))).lower()
    for needles, groups in RECORDING_INTENT_EXPECTED_GROUPS:
        if any(needle in expected_text for needle in needles):
            return [tuple(group) for group in groups]
    return []


def recording_intent_marker_groups_for_scene(scene: dict) -> list[tuple[str, ...]]:
    return _recording_intent_marker_groups_for_scene(scene)


def _recording_intent_scene_keys(scene: dict) -> list[str]:
    values: list[str] = []
    for key in ("asset_recipe_id", "blueprint_id", "visual_archetype", "template_id"):
        value = str(scene.get(key) or "").strip()
        if value:
            values.append(value)
    for container_key in ("asset_strategy_v2", "director_knowledge_refs"):
        container = scene.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in ("asset_recipe_id", "blueprint_id", "visual_archetype", "template_id"):
            value = str(container.get(key) or "").strip()
            if value:
                values.append(value)
    return values


def _evidence_asset_lookup(evidence_manifest: dict) -> dict[str, dict]:
    return {
        str(asset.get("id")): asset
        for asset in evidence_manifest.get("assets", [])
        if isinstance(asset, dict) and asset.get("id")
    }


def _merged_evidence_ref(ref: dict, lookup: dict[str, dict]) -> dict:
    source = lookup.get(str(ref.get("id") or ""))
    if not isinstance(source, dict):
        return ref
    merged = dict(source)
    for key, value in ref.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def _recording_task_intent_text(ref: dict) -> str:
    parts = [
        str(ref.get("recording_task_redacted") or "").strip(),
        str(ref.get("task_redacted") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def _recording_task_matches_marker_groups(
    task_text: str, marker_groups: list[tuple[str, ...]]
) -> bool:
    lowered = task_text.lower()
    tokens = _semantic_tokens(task_text)
    for group in marker_groups:
        if not any(_recording_task_contains_marker(lowered, tokens, marker) for marker in group):
            return False
    return True


def recording_task_matches_marker_groups(
    task_text: str, marker_groups: list[tuple[str, ...]]
) -> bool:
    return _recording_task_matches_marker_groups(task_text, marker_groups)


def _recording_task_contains_marker(
    lowered_task_text: str, tokens: set[str], marker: str
) -> bool:
    lowered_marker = marker.lower()
    return lowered_marker in lowered_task_text or lowered_marker in tokens


def _evidence_clip_has_non_text_visual_source(project: ProjectRef, ref: dict) -> bool:
    if not _evidence_clip_video_is_verifiable(project, ref):
        return False
    return str(ref.get("evidence_visual_source") or "") in OPEN_SOURCE_NON_TEXT_EVIDENCE_SOURCES


def _evidence_clip_has_recording_visual_source(project: ProjectRef, ref: dict) -> bool:
    if ref.get("evidence_clip_status") != "captured":
        return False
    if not _evidence_clip_video_is_verifiable(project, ref):
        return False
    return (
        str(ref.get("evidence_visual_source") or "")
        in OPEN_SOURCE_RECORDING_EVIDENCE_SOURCES
    )


def _evidence_clip_has_captured_dynamic_visual_source(
    project: ProjectRef, ref: dict
) -> bool:
    if not _evidence_ref_is_captured_dynamic(ref):
        return False
    return _evidence_clip_video_is_verifiable(project, ref)


def _evidence_refs_match_expected(
    project: ProjectRef, refs: list, expected_real_evidence: object
) -> bool:
    expected_groups = _expected_evidence_type_groups(expected_real_evidence)
    if not expected_groups:
        return True
    materialized_types = {
        str(ref.get("evidence_type") or "")
        for ref in refs
        if isinstance(ref, dict) and _evidence_clip_video_is_verifiable(project, ref)
    }
    return all(materialized_types & group for group in expected_groups)


def _expected_evidence_type_groups(expected_real_evidence: object) -> list[set[str]]:
    return _expected_evidence_groups(
        expected_real_evidence,
        (*OPEN_SOURCE_EVIDENCE_TYPE_GROUPS, *PROFILE_EVIDENCE_TYPE_GROUPS),
    )


def _expected_recording_evidence_type_groups(
    expected_real_evidence: object,
) -> list[set[str]]:
    return _expected_evidence_groups(
        expected_real_evidence, OPEN_SOURCE_RECORDING_EVIDENCE_TYPE_GROUPS
    )


def _expected_evidence_groups(
    expected_real_evidence: object, groups_source: tuple[tuple[tuple[str, ...], set[str]], ...]
) -> list[set[str]]:
    if isinstance(expected_real_evidence, list):
        expected_text = " ".join(str(item) for item in expected_real_evidence)
    else:
        expected_text = str(expected_real_evidence or "")
    lowered = expected_text.lower()
    groups: list[set[str]] = []
    for needles, evidence_types in groups_source:
        if any(needle in lowered or needle in expected_text for needle in needles):
            groups.append(set(evidence_types))
    return groups


def _scene_requires_real_evidence(scene: dict) -> bool:
    if scene.get("requires_real_evidence_asset") is True:
        return True
    expected = scene.get("expected_real_evidence")
    if not isinstance(expected, list) or not expected:
        return False
    return _scene_profile(scene) in EVIDENCE_MATERIALIZATION_PROFILES


def _scene_profile(scene: dict) -> str:
    refs = scene.get("director_knowledge_refs")
    if isinstance(refs, dict) and refs.get("profile"):
        return str(refs["profile"])
    strategy = scene.get("asset_strategy_v2")
    if isinstance(strategy, dict) and strategy.get("profile"):
        return str(strategy["profile"])
    return ""


def _scene_requires_captured_evidence_video(scene: dict) -> bool:
    profile = _scene_profile(scene)
    return (
        profile in EVIDENCE_MATERIALIZATION_PROFILES
        and profile != "open_source_project_intro"
    )


def _has_open_source_scene(scenes: list[dict]) -> bool:
    for scene in scenes:
        refs = scene.get("director_knowledge_refs")
        if isinstance(refs, dict) and refs.get("profile") == "open_source_project_intro":
            return True
        strategy = scene.get("asset_strategy_v2")
        if isinstance(strategy, dict) and strategy.get("profile") == "open_source_project_intro":
            return True
    return False


def _check_release_video_body(
    project: ProjectRef,
    manifest: dict,
    report: QAReport,
    strict: bool,
) -> None:
    video_path = resolve_inside(project.path, project.path / manifest.get("video_path", ""))
    scenes = [scene for scene in manifest.get("scenes", []) if isinstance(scene, dict)]
    if not video_path.exists():
        report.hard_failures.append(
            QAIssue("RENDER_NOT_VERIFIABLE", "hard", "release 视频文件不存在或不可验证。")
        )
        return
    if video_path.read_bytes() == STUB_VIDEO_BYTES:
        report.hard_failures.append(
            QAIssue("RELEASE_VIDEO_IS_STUB", "hard", "release 视频不能是离线 stub。")
        )
    has_video, has_audio = _media_streams_are_verifiable(video_path)
    if not has_video:
        report.hard_failures.append(
            QAIssue("RENDER_NOT_VERIFIABLE", "hard", "ffprobe 未能确认有效视频流。")
        )
    elif not _frame_sample_is_verifiable(video_path):
        report.hard_failures.append(
            QAIssue("RENDER_FRAME_NOT_VERIFIABLE", "hard", "无法抽取 release 视频校验帧。")
        )
    else:
        contrast = _sample_frame_luma_contrast(video_path)
        if contrast is not None and contrast < SUBTITLE_CONTRAST_MIN:
            _add_release_quality_issue(
                report,
                "RELEASE_SUBTITLE_CONTRAST_LOW",
                "抽帧检测到底部字幕区域亮度对比不足,发布前需要重渲染或调整字幕样式。",
                strict,
            )
        if _manifest_has_burned_captions(manifest):
            caption_sample_timestamps = _caption_pixel_sample_timestamps(scenes)
            caption_present = _sample_frame_has_caption_pixels_in_safe_area(
                video_path,
                caption_sample_timestamps,
            )
            if caption_present is False:
                _add_release_quality_issue(
                    report,
                    "RELEASE_CAPTION_PIXEL_NOT_DETECTED",
                    "manifest 声明已烧录字幕,但抽帧未在底部安全区检测到疑似字幕像素;"
                    "发布级字幕必须真实出现在画面底部。",
                    strict,
                )
            caption_geometry = _caption_bbox_geometry_findings(scenes)
            if caption_geometry["has_caption_bbox"]:
                caption_leak = caption_geometry["outside_safe_area"]
                subject_overlap = caption_geometry["overlaps_subject"]
                cta_overlap = caption_geometry["overlaps_cta"]
            else:
                caption_leak = bool(
                    _sample_frame_has_caption_pixels_outside_safe_area(
                        video_path,
                        caption_sample_timestamps,
                    )
                )
                subject_overlap = bool(
                    _sample_frame_has_caption_pixels_inside_subject_region(
                        video_path,
                        scenes,
                        caption_sample_timestamps,
                    )
                )
                cta_overlap = bool(
                    _sample_frame_has_caption_pixels_inside_cta_region(
                        video_path,
                        scenes,
                        caption_sample_timestamps,
                    )
                )
            if caption_leak:
                _add_release_quality_issue(
                    report,
                    "RELEASE_CAPTION_PIXEL_OUTSIDE_SAFE_AREA",
                    "抽帧检测到疑似字幕像素出现在底部安全区之外,发布级字幕必须避让主体区域。",
                    strict,
                )
            if subject_overlap:
                _add_release_quality_issue(
                    report,
                    "RELEASE_CAPTION_PIXEL_OVERLAPS_SUBJECT",
                    "抽帧检测到疑似字幕像素落在主体区域内,发布级字幕必须避让主体/CTA。",
                    strict,
                )
            if cta_overlap:
                _add_release_quality_issue(
                    report,
                    "RELEASE_CAPTION_PIXEL_OVERLAPS_CTA",
                    "抽帧检测到疑似字幕像素落在 CTA/按钮区域内,发布级字幕必须避让行动按钮。",
                    strict,
                )
        motion_delta = _sample_frame_motion_delta(video_path)
        if motion_delta is not None and motion_delta < FRAME_MOTION_DELTA_MIN:
            _add_release_quality_issue(
                report,
                "RELEASE_VISUAL_MOTION_NOT_DETECTED",
                "抽帧检测到视频帧变化过低,更像静态画面或 PPT 停帧。",
                strict,
            )
    if not has_audio:
        report.hard_failures.append(
            QAIssue("RELEASE_AUDIO_MISSING", "hard", "ffprobe 未能确认 release 音频流。")
        )
    else:
        _check_final_audio_volume(video_path, report, strict)
    if has_video and has_audio:
        _check_release_duration(project, video_path, manifest, report, strict)
    _check_audio_mix(project, manifest, scenes, report, strict)
    visual_total = int(manifest.get("visual_total") or 0)
    visual_real_count = int(manifest.get("visual_real_count") or 0)
    if visual_total > 0 and visual_real_count == 0:
        _add_release_quality_issue(
            report,
            "RELEASE_VISUAL_IS_BLANK_CARD",
            "release 画面全部为回落卡片,未消费宿主动态视频或用户视频素材。",
            strict,
        )
    if scenes:
        asset_paths = {
            scene.get("asset_path")
            for scene in scenes
            if isinstance(scene.get("asset_path"), str) and scene.get("asset_path")
        }
        if len(scenes) > 1 and len(asset_paths) == 1:
            _add_release_quality_issue(
                report,
                "RELEASE_VISUAL_REUSES_SINGLE_ASSET",
                "多镜头 release 复用了同一个画面资产,更像单图循环,不满足发布级视频要求。",
                strict,
            )
        if any(scene.get("render_source") == "image" for scene in scenes):
            _add_release_quality_issue(
                report,
                "RELEASE_VISUAL_CONTAINS_STATIC_IMAGE",
                "release 仍包含静态图片镜头;发布级视频应使用真实视频素材或动态生成资产。",
                strict,
            )
        _check_scene_video_motion(project, scenes, report, strict)
        _check_scene_visual_repetition(project, scenes, report, strict)
        _check_opening_hook(scenes, report, strict)
        _check_audio_visual_alignment(project, manifest, scenes, report, strict)
        for scene in scenes:
            _check_scene_caption_cues(project, scene, report, strict)
            if _screen_text_too_dense(scene):
                _add_release_quality_issue(
                    report,
                    "RELEASE_ON_SCREEN_TEXT_TOO_DENSE",
                    "画面主文案过长;发布级画面应只放短视觉关键词/eyebrow,"
                    "完整口播由底部 timed captions 承载。",
                    strict,
                )
            if _screen_text_duplicates_narration(scene):
                _add_release_quality_issue(
                    report,
                    "RELEASE_ON_SCREEN_TEXT_DUPLICATES_NARRATION",
                    "画面主文案重复了整句口播;发布级画面应只放短视觉关键词,"
                    "口播全文由底部字幕承载。",
                    strict,
                )
            diagnosis = _scene_asset_diagnosis(scene)
            if diagnosis and diagnosis.get("publish_grade_visual") is False:
                next_action = str(diagnosis.get("next_action_zh") or "")
                _add_release_quality_issue(
                    report,
                    "RELEASE_VISUAL_ASSET_NOT_PUBLISH_GRADE",
                    "分镜素材门诊已标记该镜头不是发布级动态视频素材。"
                    + (f" 下一步:{next_action}" if next_action else ""),
                    strict,
                )
            _check_scene_stock_image_policy(scene, report, strict)
        if any(scene.get("asset_origin") == "lingjian_hyperframes_template" for scene in scenes):
            _add_release_quality_issue(
                report,
                "RELEASE_VISUAL_IS_TEMPLATE_LOOP",
                "release 使用灵剪内置 HyperFrames 样片模板,可能只是短循环/闪动,"
                "不能冒充发布级真实视频。",
                strict,
            )
        for scene in scenes:
            generated_by_lingjian = scene.get("generator") in {
                "hyperframes",
                "remotion",
                "image-gen",
                "fallback_solid",
            }
            has_director_fields = any(
                scene.get(key)
                for key in ("layout_contract", "motion_intent", "template_id")
            ) or _scene_has_director_contract(scene)
            if not (generated_by_lingjian or has_director_fields):
                continue
            for finding in (
                layout_quality_findings(scene)
                + motion_quality_findings(scene)
                + director_route_findings(scene)
                + host_generation_contract_findings(scene)
            ):
                _add_release_quality_issue(
                    report,
                    finding["code"],
                    finding["message_zh"],
                    strict,
                )
        for finding in director_diversity_findings(scenes):
            _add_release_quality_issue(
                report,
                finding["code"],
                finding["message_zh"],
                strict,
            )
        _check_profile_required_evidence_coverage(manifest, scenes, report, strict)
        _check_visual_evidence_assets(project, manifest, scenes, report, strict)
        _check_transition_rendering(manifest, scenes, video_path, report, strict)
    if any(
        provider.get("kind") == "tts" and provider.get("id") in SAMPLE_TTS_PROVIDER_IDS
        for provider in manifest.get("providers", [])
    ):
        _add_release_quality_issue(
            report,
            "RELEASE_AUDIO_IS_PREVIEW_VOICE",
            "release 音轨来自本机样片级 TTS;"
            "请使用用户录音或火山豆包/OpenAI-compatible 等自然中文 TTS。",
            strict,
        )
    _check_voice_plan_source(project, manifest, report, strict)
    _check_voice_settings_consistency(project, report, strict)


def _manifest_has_burned_captions(manifest: dict) -> bool:
    scenes = [scene for scene in manifest.get("scenes", []) if isinstance(scene, dict)]
    return any(
        scene.get("subtitle_burn") is True or isinstance(scene.get("caption_cues"), list)
        for scene in scenes
    )


def run_qa(
    project: ProjectRef,
    release: bool = False,
    platform: str = "douyin",
    strict: bool = False,
) -> QAReport:
    report = QAReport()
    if release:
        approval_metadata = _approval_recovery_metadata(project)
        if approval_metadata:
            report.metadata.update(approval_metadata)
            _check_approval_recovery(report, strict)
        recovery_metadata = _evidence_recovery_metadata(project)
        if recovery_metadata:
            report.metadata.update(recovery_metadata)
            _check_remaining_evidence_blockers(report, strict)
        audio_metadata = _audio_recovery_metadata(project, platform)
        if audio_metadata:
            report.metadata.update(audio_metadata)
            _check_remaining_audio_asset_blockers(report, strict)
    release_manifest = latest_render_manifest(
        project, platform, "release"
    ) or _latest_any_render_manifest(project, "release")
    preview_manifest = latest_render_manifest(
        project, platform, "preview"
    ) or _latest_any_render_manifest(project, "preview")
    manifest = release_manifest if release and release_manifest is not None else preview_manifest
    if not release:
        manifest = preview_manifest or release_manifest
    if manifest is None:
        report.hard_failures.append(QAIssue("RENDER_MISSING", "hard", "缺少渲染产物。"))
    elif release and any(provider.get("is_mock") for provider in manifest.get("providers", [])):
        report.hard_failures.append(
            QAIssue("RELEASE_CONTAINS_MOCK", "hard", "release 包不能包含 mock provider。")
        )
    elif release:
        manifest_stale = _check_render_manifest_freshness(project, manifest, report, strict)
        if manifest_stale:
            _check_voice_plan_caption_cue_readiness(project, report, strict)
        if not (strict and manifest_stale):
            _check_release_video_body(project, manifest, report, strict)
    report.info.append(QAIssue("QA_STUB", "info", "Batch 2 最小 QA 已执行。"))

    artifacts = project.path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "qa_report.json").write_text(
        json.dumps(
            {
                "hard_failures": [asdict(issue) for issue in report.hard_failures],
                "warnings": [asdict(issue) for issue in report.warnings],
                "info": [asdict(issue) for issue in report.info],
                "metadata": report.metadata,
                "release_ready": report.release_ready,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (artifacts / "qa_report.md").write_text(
        _qa_report_markdown(report),
        encoding="utf-8",
    )
    return report
