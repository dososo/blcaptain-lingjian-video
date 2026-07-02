from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from engines.ffmpeg_card.text_layout import break_cjk_text
from packages.core.approvals import validate_render_gate
from packages.core.artifacts import read_json
from packages.core.errors import LingjianError
from packages.core.paths import resolve_inside, safe_segment
from packages.core.project import ProjectRef
from packages.core.visual_generation import ensure_scene_asset

RenderMode = Literal["preview", "release"]
STUB_VIDEO_BYTES = b"LINGJIAN_STUB_MP4"
FFMPEG_TIMEOUT_SEC = 60
FPS = 30


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


def _release_audio_path(project: ProjectRef) -> Path:
    voice_path = project.path / "artifacts" / "voice_plan.json"
    if not voice_path.exists():
        raise LingjianError(
            "RELEASE_AUDIO_MISSING",
            "release 渲染缺少语音产物。",
            "请先使用真实 TTS provider 生成并审批 voice。",
        )
    voice = read_json(voice_path)
    for segment in voice.get("segments", []):
        if not isinstance(segment, dict):
            continue
        audio_path = segment.get("audio_path")
        if not isinstance(audio_path, str) or not audio_path:
            continue
        resolved = resolve_inside(project.path, project.path / audio_path)
        if resolved.exists():
            return resolved
    raise LingjianError(
        "RELEASE_AUDIO_MISSING",
        "release 渲染缺少可用音频文件。",
        "请重新生成真实 voice 产物后再 release render。",
    )


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


def _visual_plan_scenes(project: ProjectRef) -> list[dict[str, Any]]:
    visual_path = project.path / "artifacts" / "visual_plan.json"
    if not visual_path.exists():
        return []
    visual_plan = read_json(visual_path)
    return [scene for scene in visual_plan.get("scenes", []) if isinstance(scene, dict)]


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


def _drawtext_filter(text: str) -> str:
    lines, _warnings = break_cjk_text(text, max_chars=18, max_lines=2)
    font = _font_path()
    font_part = f"fontfile='{_escape_drawtext(font)}':" if font else ""
    filters = []
    start_y = "(h/2)-80" if len(lines) > 1 else "(h-text_h)/2"
    for index, line in enumerate(lines or ["灵剪"]):
        y_expr = start_y if index == 0 else "(h/2)+10"
        filters.append(
            "drawtext="
            f"{font_part}"
            f"text='{_escape_drawtext(line)}':"
            "fontcolor=white:"
            "fontsize=54:"
            "x=(w-text_w)/2:"
            f"y={y_expr}:"
            "box=1:"
            "boxcolor=black@0.45:"
            "boxborderw=24"
        )
    return ",".join(filters)


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
) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x111827:s={_video_size(ratio)}:d={_release_duration(project):.2f}",
    ]
    if include_audio:
        command.extend(["-i", str(_release_audio_path(project))])
    command.extend(
        [
            "-vf",
            _drawtext_filter(_release_text(project)),
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
    if scene.get("duration_sec"):
        return max(float(scene["duration_sec"]), 0.5)
    scene_id = str(scene.get("scene_id") or scene.get("id") or "")
    voice_segment = voice_segments.get(scene_id)
    if voice_segment and voice_segment.get("duration_sec"):
        return max(float(voice_segment["duration_sec"]), 0.5)
    return max(_release_duration(project) / max(scene_count, 1), 0.5)


def _scene_asset(project: ProjectRef, scene: dict[str, Any]) -> Path | None:
    raw_path = scene.get("asset_path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    return resolve_inside(project.path, project.path / raw_path)


def _scene_text(scene: dict[str, Any], script_text: dict[str, str]) -> str:
    scene_id = str(scene.get("scene_id") or scene.get("id") or "")
    return str(scene.get("narration_text") or script_text.get(scene_id) or "灵剪")


def _append_subtitle_filter(filters: list[str], text: str, enabled: bool) -> list[str]:
    if enabled:
        filters.append(_drawtext_filter(text))
    return filters


def _render_scene_clip(
    project: ProjectRef,
    ratio: str,
    scene: dict[str, Any],
    scene_index: int,
    duration: float,
    text: str,
    output_path: Path,
) -> dict[str, Any]:
    scene = ensure_scene_asset(project, dict(scene))
    width, height = _video_dimensions(ratio)
    generator = str(scene.get("generator") or "fallback_solid")
    subtitle_burn = bool(scene.get("subtitle_burn", generator not in {"hyperframes", "remotion"}))
    asset = _scene_asset(project, scene)
    render_source = "fallback_solid"
    command: list[str]
    if asset and asset.exists() and asset.suffix.lower() in {".mp4", ".mov", ".m4v"}:
        render_source = "video"
        filters = [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "setsar=1",
            f"fps={FPS}",
        ]
        _append_subtitle_filter(filters, text, subtitle_burn)
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
        _append_subtitle_filter(filters, text, subtitle_burn)
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
        filters = [_drawtext_filter(text)]
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
    return {
        "scene_id": str(scene.get("scene_id") or scene.get("id") or f"s{scene_index}"),
        "generator": generator,
        "asset_path": str(asset.relative_to(project.path)) if asset and asset.exists() else None,
        "render_source": render_source,
        "duration_sec": duration,
        "subtitle_burn": subtitle_burn,
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
    rendered_scenes = []
    clip_paths = []
    for index, scene in enumerate(scenes, start=1):
        duration = _scene_duration(scene, voice_segments, len(scenes), project)
        text = _scene_text(scene, script_text)
        clip_path = scene_dir / f"scene_{index:03d}.mp4"
        rendered_scenes.append(
            _render_scene_clip(project, ratio, scene, index, duration, text, clip_path)
        )
        clip_paths.append(clip_path)
    concat_path = scene_dir / "concat.txt"
    concat_path.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in clip_paths),
        encoding="utf-8",
    )
    montage_path = scene_dir / "montage.mp4"
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
    _run_ffmpeg(
        project,
        [
            "ffmpeg",
            "-y",
            "-i",
            str(montage_path),
            "-i",
            str(_release_audio_path(project)),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(video_path),
        ],
        video_path,
    )
    visual_real_count = sum(
        1 for scene in rendered_scenes if scene["render_source"] in {"video", "image"}
    )
    return {
        "scenes": rendered_scenes,
        "visual_real_count": visual_real_count,
        "visual_total": len(rendered_scenes),
    }


def render_project(
    project: ProjectRef,
    platform: str,
    language: str,
    ratio: str,
    mode: RenderMode = "preview",
    real_preview: bool = False,
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
    visual_scenes = _visual_plan_scenes(project)
    if mode == "release":
        if visual_scenes:
            visual_meta = _render_visual_plan_video(project, ratio, video_path, visual_scenes)
        else:
            _render_ffmpeg_card_video(project, ratio, video_path, include_audio=True)
        if video_path.read_bytes() == STUB_VIDEO_BYTES:
            raise LingjianError(
                "RELEASE_VIDEO_IS_STUB",
                "release 视频不能是离线 stub。",
                "请检查 release 渲染路径是否实际调用 FFmpeg。",
            )
    elif real_preview and shutil.which("ffmpeg"):
        try:
            if visual_scenes:
                visual_meta = _render_visual_plan_video(project, ratio, video_path, visual_scenes)
            else:
                _render_ffmpeg_card_video(project, ratio, video_path)
        except LingjianError:
            video_path.write_bytes(STUB_VIDEO_BYTES)
    else:
        video_path.write_bytes(STUB_VIDEO_BYTES)
    manifest_path = render_dir / "render_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "mode": mode,
                "platform": platform,
                "language": language,
                "ratio": ratio,
                "video_path": str(video_path.relative_to(project.path)),
                "providers": providers,
                **visual_meta,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
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
