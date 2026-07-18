from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from packages.core.artifacts import read_json
from packages.core.errors import LingjianError
from packages.core.paths import resolve_inside, safe_segment
from packages.core.project import ProjectRef
from packages.core.qa import (
    CAPTURED_DYNAMIC_EVIDENCE_TYPES,
    OPEN_SOURCE_EVIDENCE_TYPE_GROUPS,
    OPEN_SOURCE_RECORDING_EVIDENCE_SOURCES,
    PROFILE_EVIDENCE_TYPE_GROUPS,
    audio_visual_alignment_audit,
    recording_intent_marker_groups_for_scene,
    recording_task_matches_marker_groups,
    run_qa,
    voice_plan_caption_backing_audit,
)
from packages.core.rendering import latest_render_manifest, xfade_name_for_transition_family

PLATFORM_EXTRA_FILES = {
    "youtube": {
        "thumbnail.png": "stub thumbnail\n",
        "description.md": "# YouTube Description\n",
        "chapters.md": "00:00 开场\n",
    },
}

@dataclass(slots=True)
class ExportPackageResult:
    export_dir: Path
    export_manifest: dict


def _ratio_dir(ratio: str) -> str:
    return safe_segment(ratio, "ratio").replace(":", "x")


def _approvals(project: ProjectRef) -> list[dict]:
    path = project.path / "artifacts" / "approvals.json"
    if not path.exists():
        return []
    return list(read_json(path).values())


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_project_file_if_exists(project: ProjectRef, export_dir: Path, relative_path: str) -> None:
    source = project.path / relative_path
    if not source.exists():
        return
    destination = export_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_redacted_project_text_file_if_exists(
    project: ProjectRef, export_dir: Path, relative_path: str
) -> None:
    source = project.path / relative_path
    if not source.exists():
        return
    destination = export_dir / relative_path
    redacted = _redact_project_path_in_string(project, source.read_text(encoding="utf-8"))
    _write_text(destination, redacted)


def _read_json_file(path: Path) -> object | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _iter_dicts(value: object) -> list[dict]:
    if isinstance(value, dict):
        items: list[dict] = [value]
        for nested in value.values():
            items.extend(_iter_dicts(nested))
        return items
    if isinstance(value, list):
        items: list[dict] = []
        for nested in value:
            items.extend(_iter_dicts(nested))
        return items
    return []


def _controlled_evidence_relative_path(project: ProjectRef, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or "://" in candidate:
        return None
    if candidate.startswith(("assets/evidence/", "logs/")):
        return candidate
    path = Path(candidate)
    if not path.is_absolute():
        return None
    try:
        resolved = resolve_inside(project.path, path)
    except LingjianError:
        return None
    try:
        relative = resolved.relative_to(project.path.resolve()).as_posix()
    except ValueError:
        return None
    if relative.startswith(("assets/evidence/", "logs/")):
        return relative
    return None


def _controlled_audio_relative_path(project: ProjectRef, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or "://" in candidate:
        return None
    allowed_prefixes = ("artifacts/voice_segments/", "assets/audio/", "renders/")
    if candidate.startswith(allowed_prefixes):
        return candidate
    path = Path(candidate)
    if not path.is_absolute():
        return None
    try:
        resolved = resolve_inside(project.path, path)
    except LingjianError:
        return None
    try:
        relative = resolved.relative_to(project.path.resolve()).as_posix()
    except ValueError:
        return None
    if relative.startswith(allowed_prefixes):
        return relative
    return None


def _source_map_audio_path(project: ProjectRef, value: object) -> str | None:
    controlled = _controlled_audio_relative_path(project, value)
    if controlled:
        return controlled
    text = _caption_text(value)
    if not text:
        return None
    return "<external-redacted>"


def _collect_evidence_source_files(project: ProjectRef, source_manifest: dict) -> list[str]:
    paths: set[str] = set()
    path_fields = {
        "path",
        "source_uri",
        "evidence_clip_path",
        "recording_path",
        "screenshot_path",
        "terminal_log_path",
    }
    evidence_manifest = _read_json_file(
        project.path / "assets" / "evidence" / "evidence_assets.json"
    )
    input_assets = _read_json_file(project.path / "assets" / "input_assets.json")
    for source in (source_manifest, evidence_manifest, input_assets):
        for item in _iter_dicts(source):
            for field in path_fields:
                relative_path = _controlled_evidence_relative_path(project, item.get(field))
                if relative_path:
                    paths.add(relative_path)
    return sorted(paths)


def _collect_audio_source_files(project: ProjectRef, source_manifest: dict) -> list[str]:
    paths: set[str] = set()
    path_fields = {
        "full_audio_path",
        "audio_path",
        "path",
        "bgm_path",
        "mixed_audio_path",
    }
    voice_plan = _read_json_file(project.path / "artifacts" / "voice_plan.json")
    for source in (source_manifest.get("audio_mix"), voice_plan):
        for item in _iter_dicts(source):
            for field in path_fields:
                relative_path = _controlled_audio_relative_path(project, item.get(field))
                if relative_path:
                    paths.add(relative_path)
    return sorted(paths)


def _copy_evidence_sources(project: ProjectRef, export_dir: Path, source_manifest: dict) -> None:
    for relative_path in (
        "assets/input_assets.json",
        "assets/evidence/evidence_assets.json",
    ):
        _copy_redacted_project_text_file_if_exists(project, export_dir, relative_path)
    for relative_path in _collect_evidence_source_files(project, source_manifest):
        _copy_project_file_if_exists(project, export_dir, relative_path)


def _copy_audio_sources(project: ProjectRef, export_dir: Path, source_manifest: dict) -> None:
    for relative_path in _collect_audio_source_files(project, source_manifest):
        _copy_project_file_if_exists(project, export_dir, relative_path)


def _positive_float(value: object) -> float | None:
    parsed = _float_value(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _float_value(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _caption_text(value: object) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def _redact_project_path_in_string(project: ProjectRef, value: str) -> str:
    redacted = value
    candidates = {str(project.path)}
    try:
        candidates.add(str(project.path.resolve()))
    except OSError:
        pass
    for candidate in candidates:
        if candidate and candidate != "/":
            redacted = redacted.replace(candidate, "<project>")
    return redacted


def _source_map_command_text(project: ProjectRef, value: object) -> str | None:
    text = _caption_text(value)
    if not text:
        return None
    return _redact_project_path_in_string(project, text)


def _source_map_project_relative_path(project: ProjectRef, value: object) -> str | None:
    text = _caption_text(value)
    if not text or "://" in text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = project.path / candidate
    try:
        resolved = resolve_inside(project.path, candidate)
        return resolved.relative_to(project.path.resolve()).as_posix()
    except (OSError, ValueError, LingjianError):
        return None


def _redact_project_paths_for_export(project: ProjectRef, value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _redact_project_paths_for_export(project, nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_project_paths_for_export(project, nested) for nested in value]
    if isinstance(value, str):
        return _redact_project_path_in_string(project, value)
    return value


def _write_export_qa_report_json(project: ProjectRef, export_dir: Path) -> None:
    qa_json = project.path / "artifacts" / "qa_report.json"
    if not qa_json.exists():
        return
    destination = export_dir / "qa_report.json"
    try:
        payload = json.loads(qa_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        redacted = _redact_project_path_in_string(project, qa_json.read_text(encoding="utf-8"))
        _write_text(destination, redacted)
        return
    safe_payload = _redact_project_paths_for_export(project, payload)
    _write_text(destination, json.dumps(safe_payload, ensure_ascii=False, indent=2) + "\n")


def _timeline_caption_entries(source_manifest: dict) -> list[tuple[float, float, str]]:
    entries: list[tuple[float, float, str]] = []
    offset = 0.0
    scenes = source_manifest.get("scenes")
    if not isinstance(scenes, list):
        return [(0.0, 1.0, "灵剪")]
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        duration = _positive_float(scene.get("duration_sec")) or 0.0
        cues = scene.get("caption_cues")
        if isinstance(cues, list) and cues:
            for cue in cues:
                if not isinstance(cue, dict):
                    continue
                text = _caption_text(cue.get("text"))
                start = _float_value(cue.get("start_sec"))
                end = _positive_float(cue.get("end_sec"))
                if not text or start is None or start < 0 or end is None or end <= start:
                    continue
                entries.append((offset + start, offset + end, text))
        else:
            text = _caption_text(scene.get("narration_text") or scene.get("visual_prompt"))
            if text and duration > 0:
                entries.append((offset, offset + duration, text))
        offset += duration
    return entries or [(0.0, 1.0, "灵剪")]


def _format_srt_timestamp(seconds: float) -> str:
    millis = max(int(round(seconds * 1000)), 0)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_vtt_timestamp(seconds: float) -> str:
    return _format_srt_timestamp(seconds).replace(",", ".")


def _format_ass_timestamp(seconds: float) -> str:
    centis = max(int(round(seconds * 100)), 0)
    hours, remainder = divmod(centis, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _subtitle_files(source_manifest: dict) -> dict[str, str]:
    entries = _timeline_caption_entries(source_manifest)
    srt_blocks = []
    for index, (start, end, text) in enumerate(entries, start=1):
        srt_blocks.append(
            f"{index}\n{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n{text}"
        )
    vtt_lines = ["WEBVTT", ""]
    for start, end, text in entries:
        vtt_lines.extend(
            [
                f"{_format_vtt_timestamp(start)} --> {_format_vtt_timestamp(end)}",
                text,
                "",
            ]
        )
    ass_lines = [
        "[Script Info]",
        "Title: LingJian",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding"
        ),
        (
            "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "0,0,0,0,100,100,0,0,1,2,0,2,40,40,90,1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for start, end, text in entries:
        ass_lines.append(
            f"Dialogue: 0,{_format_ass_timestamp(start)},{_format_ass_timestamp(end)},"
            f"Default,,0,0,0,,{text}"
        )
    return {
        "subtitles.srt": "\n\n".join(srt_blocks) + "\n",
        "subtitles.vtt": "\n".join(vtt_lines).rstrip() + "\n",
        "subtitles.ass": "\n".join(ass_lines) + "\n",
    }


def _source_map_caption_cues(scene: dict, offset: float) -> list[dict]:
    mapped: list[dict] = []
    cues = scene.get("caption_cues")
    if not isinstance(cues, list):
        return mapped
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        text = _caption_text(cue.get("text"))
        start = _float_value(cue.get("start_sec"))
        end = _positive_float(cue.get("end_sec"))
        if not text or start is None or start < 0 or end is None or end <= start:
            continue
        mapped.append(
            {
                "text": text,
                "start_sec": round(offset + start, 3),
                "end_sec": round(offset + end, 3),
                "source": _caption_text(cue.get("source")) or "manifest",
            }
        )
        timing_basis = _caption_text(cue.get("timing_basis"))
        if timing_basis:
            mapped[-1]["timing_basis"] = timing_basis
    return mapped


def _source_map_caption_timing(scene: dict) -> dict | None:
    timing = scene.get("caption_timing")
    if not isinstance(timing, dict):
        return None
    mapped = {
        "source": timing.get("source"),
        "timing_basis": timing.get("timing_basis"),
        "max_cue_sec": timing.get("max_cue_sec"),
        "estimated_max_cue_sec": timing.get("estimated_max_cue_sec"),
        "release_ready": timing.get("release_ready"),
        "release_gate": timing.get("release_gate"),
        "release_blocker_code": timing.get("release_blocker_code"),
        "release_blocker_zh": timing.get("release_blocker_zh"),
        "recovery_target_field": timing.get("recovery_target_field"),
        "recovery_next_action_zh": timing.get("recovery_next_action_zh"),
        "required_timing_basis": timing.get("required_timing_basis"),
        "accepted_timing_sources": timing.get("accepted_timing_sources"),
    }
    return {key: value for key, value in mapped.items() if value not in (None, "")} or None


def _source_map_caption_audit(project: ProjectRef, scene: dict) -> dict | None:
    raw_cues = scene.get("caption_cues")
    cues = [cue for cue in raw_cues if isinstance(cue, dict)] if isinstance(raw_cues, list) else []
    caption_timing = scene.get("caption_timing")
    if not cues and not isinstance(caption_timing, dict):
        return None
    cue_sources = sorted(
        {
            _caption_text(cue.get("source")) or "manifest"
            for cue in cues
            if isinstance(cue, dict)
        }
    )
    cue_timing_bases = sorted(
        {
            _caption_text(cue.get("timing_basis"))
            for cue in cues
            if isinstance(cue, dict) and _caption_text(cue.get("timing_basis"))
        }
    )
    timing_source = ""
    timing_basis = ""
    if isinstance(caption_timing, dict):
        timing_source = _caption_text(caption_timing.get("source"))
        timing_basis = _caption_text(caption_timing.get("timing_basis"))
    estimated_timing = any(
        value == "estimated"
        for value in (
            timing_source,
            timing_basis,
            *cue_sources,
            *cue_timing_bases,
        )
    )
    audit: dict[str, object] = {
        "timing_source": timing_source or None,
        "timing_basis": timing_basis or None,
        "cue_sources": cue_sources,
        "cue_timing_bases": cue_timing_bases,
        "estimated_timing": estimated_timing,
    }
    audit.update(
        voice_plan_caption_backing_audit(project, scene, caption_timing, cues)
    )
    return {key: value for key, value in audit.items() if value not in (None, "", [], {})}


def _source_map_transition_semantic_audit(
    value: dict,
    target_scene: dict | None,
    transition_index: int,
) -> dict | None:
    target_scene_id = _caption_text(value.get("to_scene_id"))
    if isinstance(target_scene, dict):
        target_scene_id = (
            _caption_text(
                target_scene.get("scene_id")
                or target_scene.get("id")
                or target_scene_id
            )
            or target_scene_id
        )
    plan = target_scene.get("transition_plan") if isinstance(target_scene, dict) else None
    if not isinstance(plan, dict):
        if not target_scene_id:
            return None
        return {
            "planned_scene_id": target_scene_id,
            "plan_present": False,
        }
    planned_family = _caption_text(plan.get("family") or plan.get("intent"))
    if not planned_family:
        return {
            "planned_scene_id": target_scene_id,
            "plan_present": True,
            "semantic_match": False,
            "mismatch_reason": "missing_planned_family",
        }
    expected_xfade = xfade_name_for_transition_family(planned_family, transition_index)
    actual_family = _caption_text(value.get("family"))
    actual_xfade = _caption_text(value.get("xfade"))
    family_matches = not actual_family or actual_family == planned_family
    xfade_matches = actual_xfade == expected_xfade
    audit: dict[str, object] = {
        "planned_scene_id": target_scene_id,
        "plan_present": True,
        "planned_family": planned_family,
        "expected_xfade": expected_xfade,
        "actual_family": actual_family or None,
        "actual_xfade": actual_xfade or None,
        "semantic_match": family_matches and xfade_matches,
    }
    if not family_matches:
        audit["mismatch_reason"] = "family_mismatch"
    elif not xfade_matches:
        audit["mismatch_reason"] = "xfade_mismatch"
    return {key: val for key, val in audit.items() if val not in (None, "")}


def _source_map_transition(
    value: object,
    mode: object,
    target_scene: dict | None = None,
    transition_index: int = 1,
) -> dict | None:
    if not isinstance(value, dict):
        return None
    mapped: dict[str, object] = {
        "from_scene_id": value.get("from_scene_id"),
        "to_scene_id": value.get("to_scene_id"),
        "family": value.get("family"),
        "xfade": value.get("xfade"),
        "mode": mode,
    }
    offset = _float_value(value.get("offset_sec"))
    duration = _positive_float(value.get("duration_sec"))
    if offset is not None and offset >= 0:
        mapped["offset_sec"] = round(offset, 3)
    if duration is not None:
        mapped["duration_sec"] = round(duration, 3)
    semantic_audit = _source_map_transition_semantic_audit(
        value, target_scene, transition_index
    )
    if semantic_audit is not None:
        mapped["semantic_audit"] = semantic_audit
    return mapped


def _source_map_transition_lookup(
    source_manifest: dict,
    scenes: list,
) -> tuple[dict[str, dict], dict[str, dict]]:
    incoming: dict[str, dict] = {}
    outgoing: dict[str, dict] = {}
    transition_rendering = source_manifest.get("transition_rendering")
    if not isinstance(transition_rendering, dict):
        return incoming, outgoing
    transitions = transition_rendering.get("transitions")
    if not isinstance(transitions, list):
        return incoming, outgoing
    mode = transition_rendering.get("mode")
    scene_by_id = {
        _caption_text(scene.get("scene_id") or scene.get("id") or ""): scene
        for scene in scenes
        if isinstance(scene, dict)
    }
    for index, transition in enumerate(transitions, start=1):
        to_scene_id = (
            _caption_text(transition.get("to_scene_id"))
            if isinstance(transition, dict)
            else ""
        )
        target_scene = scene_by_id.get(to_scene_id) if to_scene_id else None
        mapped = _source_map_transition(transition, mode, target_scene, index)
        if mapped is None:
            continue
        from_scene_id = _caption_text(mapped.get("from_scene_id"))
        to_scene_id = _caption_text(mapped.get("to_scene_id"))
        if from_scene_id:
            outgoing[from_scene_id] = mapped
        if to_scene_id:
            incoming[to_scene_id] = mapped
    return incoming, outgoing


def _source_map_transition_diagnostics(source_manifest: dict) -> dict | None:
    transition_rendering = source_manifest.get("transition_rendering")
    if not isinstance(transition_rendering, dict):
        return None
    mapped = {
        "rendered": transition_rendering.get("rendered"),
        "mode": transition_rendering.get("mode"),
        "reason": transition_rendering.get("reason"),
        "transition_count": transition_rendering.get("transition_count"),
    }
    return {key: value for key, value in mapped.items() if value not in (None, "")} or None


def _source_map_bgm_track(
    project: ProjectRef, source_manifest: dict, total_duration: float
) -> dict | None:
    mix = source_manifest.get("audio_mix")
    if not isinstance(mix, dict) or not mix.get("bgm_present"):
        return None
    return {
        "path": _source_map_audio_path(project, mix.get("bgm_path")),
        "start_sec": 0.0,
        "end_sec": round(max(total_duration, 0.0), 3),
        "bgm_to_voice_db": mix.get("bgm_to_voice_db"),
        "mixed_audio_path": _source_map_audio_path(project, mix.get("mixed_audio_path")),
        "rendered": bool(mix.get("rendered")),
    }


def _source_map_audio_diagnostics(source_manifest: dict) -> dict | None:
    mix = source_manifest.get("audio_mix")
    if not isinstance(mix, dict):
        return None
    invalid_assets = mix.get("invalid_audio_assets")
    mapped_assets = []
    if isinstance(invalid_assets, list):
        for asset in invalid_assets:
            if not isinstance(asset, dict):
                continue
            mapped_assets.append(
                {
                    key: asset.get(key)
                    for key in ("kind", "path", "scene_id", "action", "reason")
                    if asset.get(key) not in (None, "")
                }
            )
    declared_requirements = mix.get("declared_audio_requirements")
    has_declared_requirements = isinstance(declared_requirements, dict) and bool(
        declared_requirements
    )
    if not mapped_assets and not has_declared_requirements:
        return None
    result: dict[str, object] = {}
    if mapped_assets:
        result.update(
            {
                "invalid_audio_asset_count": int(
                    mix.get("invalid_audio_asset_count") or len(mapped_assets)
                ),
                "invalid_audio_assets": mapped_assets,
            }
        )
    if has_declared_requirements:
        result["declared_audio_requirements"] = declared_requirements
    return result


def _source_map_sfx_event(
    project: ProjectRef, value: object, scene_start: float
) -> dict | None:
    if not isinstance(value, dict):
        return None
    at_sec = _float_value(value.get("at_sec"))
    mapped: dict[str, object] = {
        "path": _source_map_audio_path(project, value.get("path")),
        "scene_id": value.get("scene_id"),
        "action": value.get("action"),
        "purpose": value.get("purpose"),
        "visual_event": value.get("visual_event"),
        "cue_id": value.get("cue_id"),
        "time_basis": value.get("time_basis"),
    }
    gain = _float_value(value.get("gain_db"))
    local_at_sec = _float_value(value.get("local_at_sec"))
    if at_sec is not None and at_sec >= 0:
        mapped["at_sec"] = round(at_sec, 3)
        mapped["local_at_sec"] = round(max(at_sec - scene_start, 0.0), 3)
    if local_at_sec is not None and local_at_sec >= 0:
        mapped["local_at_sec"] = round(local_at_sec, 3)
    if gain is not None:
        mapped["gain_db"] = gain
    return {key: value for key, value in mapped.items() if value not in (None, "")}


def _source_map_sfx_events(
    project: ProjectRef, source_manifest: dict, scene_id: str, start: float, end: float
) -> list[dict]:
    mix = source_manifest.get("audio_mix")
    if not isinstance(mix, dict):
        return []
    events = mix.get("sfx_events")
    if not isinstance(events, list):
        return []
    mapped_events: list[dict] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_scene_id = _caption_text(event.get("scene_id"))
        at_sec = _float_value(event.get("at_sec"))
        if event_scene_id:
            if event_scene_id != scene_id:
                continue
        elif at_sec is None or at_sec < start or at_sec >= end:
            continue
        mapped = _source_map_sfx_event(project, event, start)
        if mapped is not None:
            mapped_events.append(mapped)
    return mapped_events


def _safe_voice_settings(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    allowed_keys = {
        "emotion",
        "language",
        "pitch",
        "sample_rate_hz",
        "speed",
        "style",
        "volume",
    }
    settings = {key: value.get(key) for key in allowed_keys if value.get(key) is not None}
    return settings or None


def _source_map_voice_segment(segment: dict) -> dict:
    mapped: dict[str, object] = {
        "scene_id": _caption_text(segment.get("scene_id")),
        "audio_path": segment.get("audio_path"),
        "voice_id": segment.get("voice_id") or segment.get("voice_type"),
        "provider_id": segment.get("provider_id"),
        "quality_tier": segment.get("quality_tier"),
    }
    duration = _positive_float(segment.get("duration_sec"))
    if duration is not None:
        mapped["duration_sec"] = round(duration, 3)
    caption_cues = segment.get("caption_cues")
    if isinstance(caption_cues, list):
        mapped["caption_cue_count"] = len([cue for cue in caption_cues if isinstance(cue, dict)])
    voice_settings = _safe_voice_settings(segment.get("provider_voice_settings"))
    if voice_settings is not None:
        mapped["provider_voice_settings"] = voice_settings
    return {key: value for key, value in mapped.items() if value not in (None, "")}


def _source_map_voice_lookup(project: ProjectRef) -> dict[str, dict]:
    voice_plan = _read_json_file(project.path / "artifacts" / "voice_plan.json")
    if not isinstance(voice_plan, dict):
        return {}
    segments = voice_plan.get("segments")
    if not isinstance(segments, list):
        return {}
    lookup: dict[str, dict] = {}
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            continue
        scene_id = _caption_text(segment.get("scene_id") or f"s{index}")
        if not scene_id:
            continue
        segment_with_scene_id = {**segment, "scene_id": scene_id}
        lookup[scene_id] = _source_map_voice_segment(segment_with_scene_id)
    return lookup


def _source_map_director_review(scene: dict) -> dict | None:
    review = (
        scene.get("director_review_sheet_v2")
        or scene.get("director_review_sheet")
        or scene.get("director_board")
    )
    if not isinstance(review, dict):
        return None
    mapped = {
        "version": review.get("version"),
        "scene_goal": review.get("scene_goal")
        or review.get("narrative_role")
        or review.get("role"),
        "visual_content": review.get("visual_content") or review.get("visual_summary"),
        "asset_strategy": review.get("asset_strategy") or review.get("asset_status"),
        "composition": review.get("composition"),
        "caption_region": review.get("caption_region") or review.get("caption_contract"),
        "transition": review.get("transition"),
        "main_motion": review.get("main_motion") or review.get("main_motion_intent"),
        "qa_checkpoints": review.get("qa_checkpoints"),
    }
    return {key: value for key, value in mapped.items() if value not in (None, "", [], {})}


def _source_map_audio_visual_alignment_ref(value: object) -> object | None:
    if isinstance(value, str):
        return _caption_text(value) or None
    if not isinstance(value, dict):
        return None
    allowed_keys = {
        "id",
        "asset_id",
        "scene_id",
        "target_scene_id",
        "evidence_type",
        "type",
    }
    mapped = {
        key: value.get(key)
        for key in allowed_keys
        if value.get(key) not in (None, "", [], {})
    }
    return mapped or None


def _source_map_audio_visual_alignment(
    project: ProjectRef,
    source_manifest: dict,
    scene: dict,
) -> dict | None:
    candidates = [("scene", scene.get("audio_visual_alignment"))]
    for key in ("director_review_sheet_v2", "director_review_sheet", "director_board"):
        review = scene.get(key)
        if isinstance(review, dict):
            candidates.append((key, review.get("audio_visual_alignment")))
    for source, candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        status = _caption_text(candidate.get("status"))
        if not status:
            continue
        mapped: dict[str, object] = {"source": source, "status": status}
        for key in ("notes", "method", "verified_by", "reviewed_by"):
            text = _caption_text(candidate.get(key))
            if text:
                mapped[key] = text
        refs = candidate.get("evidence_refs")
        if isinstance(refs, list):
            mapped_refs = [
                ref
                for ref in (_source_map_audio_visual_alignment_ref(ref) for ref in refs)
                if ref is not None
            ]
            if mapped_refs:
                mapped["evidence_refs"] = mapped_refs
        evidence_fields = ("evidence", "evidence_zh", "proof")
        mapped["has_evidence"] = any(
            candidate.get(key) not in (None, "", [], {}) for key in evidence_fields
        ) or bool(mapped.get("evidence_refs"))
        audit = audio_visual_alignment_audit(project, source_manifest, scene)
        if isinstance(audit, dict):
            mapped.update(audit)
        return mapped
    return None


def _source_map_evidence_lookup(project: ProjectRef) -> dict[str, dict]:
    manifest = _read_json_file(project.path / "assets" / "evidence" / "evidence_assets.json")
    if not isinstance(manifest, dict):
        return {}
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        return {}
    lookup: dict[str, dict] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_id = _caption_text(asset.get("id"))
        if asset_id:
            lookup[asset_id] = asset
    return lookup


def _source_map_evidence_asset(
    project: ProjectRef,
    value: object,
    lookup: dict[str, dict],
    scene: dict,
    scene_id: str,
    expected_evidence_type_groups: list[set[str]],
    recording_intent_marker_groups: list[tuple[str, ...]],
) -> dict | None:
    if not isinstance(value, dict):
        return None
    evidence_id = _caption_text(value.get("id") or value.get("asset_id"))
    source = {**lookup.get(evidence_id, {}), **value}
    evidence_type = source.get("evidence_type") or source.get("type")
    target_scene_id = _caption_text(source.get("target_scene_id"))
    mapped: dict[str, object] = {
        "id": evidence_id,
        "evidence_type": evidence_type,
        "target_scene_id": target_scene_id,
        "evidence_clip_status": source.get("evidence_clip_status"),
        "evidence_clip_render_source": source.get("evidence_clip_render_source"),
        "evidence_visual_source": source.get("evidence_visual_source"),
        "evidence_clip_style": source.get("evidence_clip_style"),
        "evidence_clip_role_zh": source.get("evidence_clip_role_zh"),
        "recording_status": source.get("recording_status"),
        "source_video_probe_status": source.get("source_video_probe_status"),
        "source_video_probe_tool": source.get("source_video_probe_tool"),
        "recording_task_redacted": source.get("recording_task_redacted"),
        "task_redacted": source.get("task_redacted"),
        "next_action_zh": source.get("next_action_zh"),
        "next_command": _source_map_command_text(project, source.get("next_command")),
        "manual_fallback_command": _source_map_command_text(
            project, source.get("manual_fallback_command")
        ),
        "manual_fallback_note_zh": source.get("manual_fallback_note_zh"),
        "privacy_notice_zh": source.get("privacy_notice_zh"),
    }
    for field in ("screen_recording_consent_required", "screen_recording_consent"):
        if isinstance(source.get(field), bool):
            mapped[field] = source[field]
    if scene_id:
        mapped["target_scene_matches"] = bool(target_scene_id and target_scene_id == scene_id)
    if expected_evidence_type_groups:
        evidence_type_text = _caption_text(evidence_type)
        mapped["expected_evidence_type_matches"] = any(
            evidence_type_text in group for group in expected_evidence_type_groups
        )
    if recording_intent_marker_groups and _source_map_evidence_is_recording(source):
        mapped["recording_task_intent_matches"] = _source_map_recording_task_intent_matches(
            source,
            recording_intent_marker_groups,
        )
    mapped.update(_source_map_evidence_primary_visual_consumption(project, scene, source))
    for field in ("path", "source_uri", "evidence_clip_path"):
        safe_path = _controlled_evidence_relative_path(project, source.get(field))
        if safe_path:
            mapped[field] = safe_path
    for field in (
        "materialized_evidence_video",
        "publish_grade_evidence_video",
        "publish_grade_visual_candidate",
        "source_video_has_video_stream",
        "original_path_redacted",
    ):
        if isinstance(source.get(field), bool):
            mapped[field] = source[field]
    for field in ("source_video_duration_sec", "evidence_clip_duration_sec"):
        duration = _positive_float(source.get(field))
        if duration is not None:
            mapped[field] = round(duration, 3)
    return {key: value for key, value in mapped.items() if value not in (None, "", [], {})}


def _source_map_evidence_primary_visual_consumption(
    project: ProjectRef,
    scene: dict,
    source: dict,
) -> dict:
    if not _source_map_evidence_is_recording(source):
        return {}
    scene_asset_path = _source_map_project_relative_path(project, scene.get("asset_path"))
    evidence_clip_path = _source_map_project_relative_path(
        project, source.get("evidence_clip_path")
    )
    mapped: dict[str, object] = {
        "primary_visual_consumed": False,
        "primary_visual_consumption_source": "none",
    }
    if scene_asset_path:
        mapped["scene_asset_path"] = scene_asset_path
    if scene_asset_path and evidence_clip_path and scene_asset_path == evidence_clip_path:
        mapped["primary_visual_consumed"] = True
        mapped["primary_visual_consumption_source"] = "asset_path"
    elif _source_map_host_contract_declares_evidence_primary_visual(
        scene.get("host_generation_contract")
    ):
        mapped["primary_visual_consumed"] = True
        mapped["primary_visual_consumption_source"] = "host_generation_contract"
    return mapped


def _source_map_host_contract_declares_evidence_primary_visual(contract: object) -> bool:
    if not isinstance(contract, dict):
        return False
    try:
        evidence_media_count = int(contract.get("evidence_media_count"))
    except (TypeError, ValueError):
        evidence_media_count = 0
    return (
        evidence_media_count >= 1
        and _caption_text(contract.get("evidence_media_hero_kind")) == "video"
        and _caption_text(contract.get("evidence_media_hero_role")) == "primary_visual"
        and contract.get("template_body_suppressed_for_evidence") is True
        and contract.get("contract_confirmed_by_generator") is True
    )


def _source_map_evidence_is_recording(source: dict) -> bool:
    if source.get("evidence_clip_status") != "captured":
        return False
    evidence_type = _caption_text(source.get("evidence_type") or source.get("type"))
    visual_source = _caption_text(source.get("evidence_visual_source"))
    return (
        evidence_type in CAPTURED_DYNAMIC_EVIDENCE_TYPES
        or visual_source in OPEN_SOURCE_RECORDING_EVIDENCE_SOURCES
    )


def _source_map_recording_task_intent_matches(
    source: dict,
    marker_groups: list[tuple[str, ...]],
) -> bool:
    task_text = " ".join(
        part
        for part in (
            _caption_text(source.get("recording_task_redacted")),
            _caption_text(source.get("task_redacted")),
        )
        if part
    )
    if not task_text:
        return False
    return recording_task_matches_marker_groups(task_text, marker_groups)


def _source_map_expected_evidence_type_groups(expected_real_evidence: object) -> list[set[str]]:
    if isinstance(expected_real_evidence, list):
        expected_text = " ".join(str(item) for item in expected_real_evidence)
    else:
        expected_text = str(expected_real_evidence or "")
    lowered = expected_text.lower()
    groups: list[set[str]] = []
    for needles, evidence_types in (
        *OPEN_SOURCE_EVIDENCE_TYPE_GROUPS,
        *PROFILE_EVIDENCE_TYPE_GROUPS,
    ):
        if any(needle in lowered or needle in expected_text for needle in needles):
            groups.append(set(evidence_types))
    return groups


def _source_map_evidence_contract(scene: dict) -> dict | None:
    expected_real_evidence = scene.get("expected_real_evidence")
    expected_groups = _source_map_expected_evidence_type_groups(expected_real_evidence)
    asset_strategy = scene.get("asset_strategy_v2")
    contract: dict[str, object] = {
        "requires_real_evidence_asset": scene.get("requires_real_evidence_asset"),
        "expected_real_evidence": expected_real_evidence,
        "expected_evidence_type_groups": [
            sorted(group) for group in expected_groups if group
        ],
    }
    if isinstance(asset_strategy, dict):
        strategy_summary = {
            key: asset_strategy.get(key)
            for key in (
                "profile",
                "blueprint_id",
                "current_asset_kind",
                "current_asset_status",
                "publish_grade_visual",
                "next_action_zh",
                "stock_image_allowed",
                "stock_image_requires_user_consent",
                "stock_image_not_evidence",
            )
            if asset_strategy.get(key) not in (None, "", [], {})
        }
        stock_policy = _source_map_stock_image_policy(scene)
        if stock_policy:
            strategy_summary["stock_image_policy"] = stock_policy
        if strategy_summary:
            contract["asset_strategy"] = strategy_summary
    marker_groups = recording_intent_marker_groups_for_scene(scene)
    if marker_groups:
        contract["recording_intent_marker_groups"] = [
            list(group) for group in marker_groups if group
        ]
    return {
        key: value for key, value in contract.items() if value not in (None, "", [], {})
    } or None


def _source_map_stock_image_policy(scene: dict) -> dict | None:
    policy = scene.get("stock_image_policy")
    if not isinstance(policy, dict):
        strategy = scene.get("asset_strategy_v2")
        if isinstance(strategy, dict):
            policy = strategy.get("stock_image_policy")
    if not isinstance(policy, dict):
        return None
    mapped = {
        "allowed": policy.get("allowed"),
        "allowed_when": _caption_text(policy.get("allowed_when")),
        "requires_user_consent": policy.get("requires_user_consent"),
        "user_consent_status": _caption_text(policy.get("user_consent_status")),
        "not_evidence": policy.get("not_evidence"),
        "does_not_satisfy_real_evidence": policy.get("does_not_satisfy_real_evidence"),
        "source_priority": policy.get("source_priority"),
        "license_fields_required": policy.get("license_fields_required"),
        "license_unverified_value": policy.get("license_unverified_value"),
        "processing_requirements": policy.get("processing_requirements"),
        "selected_source": _source_map_stock_image_source(policy.get("selected_source")),
    }
    sources = policy.get("sources") or scene.get("stock_image_sources")
    if isinstance(sources, list):
        mapped["sources"] = [
            source
            for source in (_source_map_stock_image_source(item) for item in sources)
            if source
        ]
    return {key: value for key, value in mapped.items() if value not in (None, "", [], {})}


def _source_map_stock_image_source(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    mapped = {
        "source": _caption_text(value.get("source")),
        "sourceUrl": _caption_text(value.get("sourceUrl") or value.get("source_url")),
        "license": _caption_text(value.get("license")),
        "license_verification_status": _caption_text(
            value.get("license_verification_status")
        ),
    }
    return {key: item for key, item in mapped.items() if item not in (None, "", [], {})}


def _source_map_evidence_assets(
    project: ProjectRef, scene: dict, lookup: dict[str, dict]
) -> list[dict]:
    refs = scene.get("evidence_asset_refs")
    if not isinstance(refs, list):
        return []
    scene_id = _caption_text(scene.get("scene_id") or scene.get("id"))
    expected_groups = _source_map_expected_evidence_type_groups(
        scene.get("expected_real_evidence")
    )
    recording_intent_marker_groups = recording_intent_marker_groups_for_scene(scene)
    mapped_assets: list[dict] = []
    for ref in refs:
        mapped = _source_map_evidence_asset(
            project,
            ref,
            lookup,
            scene,
            scene_id,
            expected_groups,
            recording_intent_marker_groups,
        )
        if mapped is not None:
            mapped_assets.append(mapped)
    return mapped_assets


def _source_map_evidence_recovery_lookup(
    project: ProjectRef, qa_report: object | None
) -> dict[str, list[dict]]:
    metadata = getattr(qa_report, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    blockers = metadata.get("remaining_evidence_blockers")
    if not isinstance(blockers, list):
        return {}
    lookup: dict[str, list[dict]] = {}
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        scene_id = _caption_text(blocker.get("scene_id"))
        if not scene_id:
            continue
        mapped = {
            "scene_id": scene_id,
            "scene_number": blocker.get("scene_number"),
            "asset_recipe_id": blocker.get("asset_recipe_id"),
            "expected_evidence_types": blocker.get("expected_evidence_types"),
            "next_action_zh": blocker.get("next_action_zh"),
            "first_command": _source_map_command_text(project, blocker.get("first_command")),
            "first_command_label_zh": blocker.get("first_command_label_zh"),
            "screen_recording_consent_required": blocker.get(
                "screen_recording_consent_required"
            ),
            "privacy_notice_zh": blocker.get("privacy_notice_zh"),
            "manual_fallback_command": _source_map_command_text(
                project, blocker.get("manual_fallback_command")
            ),
            "manual_fallback_note_zh": blocker.get("manual_fallback_note_zh"),
        }
        cleaned = {
            key: value
            for key, value in mapped.items()
            if value not in (None, "", [], {})
        }
        lookup.setdefault(scene_id, []).append(cleaned)
    return lookup


def _source_map_audio_recovery_lookup(
    project: ProjectRef, qa_report: object | None
) -> dict[str, list[dict]]:
    metadata = getattr(qa_report, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    blockers = metadata.get("remaining_audio_asset_blockers")
    if not isinstance(blockers, list):
        return {}
    lookup: dict[str, list[dict]] = {}
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        scene_ids: list[str] = []
        raw_scene_ids = blocker.get("scene_ids")
        if isinstance(raw_scene_ids, list):
            scene_ids.extend(_caption_text(scene_id) for scene_id in raw_scene_ids)
        scene_id = _caption_text(blocker.get("scene_id"))
        if scene_id:
            scene_ids.append(scene_id)
        scene_ids = [scene_id for scene_id in dict.fromkeys(scene_ids) if scene_id]
        if not scene_ids:
            continue
        mapped = {
            "kind": _caption_text(blocker.get("kind")),
            "scene_ids": scene_ids,
            "scene_number": blocker.get("scene_number"),
            "declared_sfx_markers": blocker.get("declared_sfx_markers"),
            "expected_audio_asset": _caption_text(blocker.get("expected_audio_asset")),
            "accepted_formats": blocker.get("accepted_formats"),
            "next_action_zh": blocker.get("next_action_zh"),
            "first_command": _source_map_command_text(
                project, blocker.get("first_command")
            ),
            "first_command_label_zh": blocker.get("first_command_label_zh"),
            "suggested_at_sec": blocker.get("suggested_at_sec"),
            "suggested_timing_basis": blocker.get("suggested_timing_basis"),
            "suggested_action": blocker.get("suggested_action"),
            "timing_hint_zh": blocker.get("timing_hint_zh"),
        }
        suggested_commands = blocker.get("suggested_commands")
        if isinstance(suggested_commands, list):
            mapped["suggested_commands"] = [
                {
                    key: value
                    for key, value in {
                        "label_zh": item.get("label_zh"),
                        "command": _source_map_command_text(project, item.get("command")),
                        "note_zh": item.get("note_zh"),
                    }.items()
                    if value not in (None, "", [], {})
                }
                for item in suggested_commands
                if isinstance(item, dict)
                and _source_map_command_text(project, item.get("command"))
            ]
        scenes = blocker.get("scenes")
        if isinstance(scenes, list):
            mapped["scenes"] = [
                {
                    key: value
                    for key, value in {
                        "scene_id": _caption_text(scene.get("scene_id")),
                        "scene_number": scene.get("scene_number"),
                        "declared_bgm": scene.get("declared_bgm"),
                    }.items()
                    if value not in (None, "", [], {})
                }
                for scene in scenes
                if isinstance(scene, dict)
            ]
        cleaned = {
            key: value
            for key, value in mapped.items()
            if value not in (None, "", [], {})
        }
        for target_scene_id in scene_ids:
            lookup.setdefault(target_scene_id, []).append(cleaned)
    return lookup


def _source_map_stock_image_recovery_lookup(
    qa_report: object | None,
) -> dict[str, list[dict]]:
    metadata = getattr(qa_report, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    blockers = metadata.get("remaining_stock_image_blockers")
    if not isinstance(blockers, list):
        return {}
    lookup: dict[str, list[dict]] = {}
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        scene_id = _caption_text(blocker.get("scene_id"))
        if not scene_id:
            continue
        mapped = {
            "issue_code": _caption_text(blocker.get("issue_code")),
            "next_action_zh": _caption_text(blocker.get("next_action_zh")),
        }
        lookup.setdefault(scene_id, []).append(
            {key: value for key, value in mapped.items() if value not in (None, "", [], {})}
        )
    return lookup


def _source_map_approval_command_item(project: ProjectRef, value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    command = _source_map_command_text(
        project, value.get("command") or value.get("approval_command")
    )
    approval_command = _source_map_command_text(
        project, value.get("approval_command") or value.get("command")
    )
    mapped = {
        "target": _caption_text(value.get("target")),
        "artifact": _caption_text(value.get("artifact")),
        "approval_command": approval_command,
        "command": command,
    }
    return {key: item for key, item in mapped.items() if item not in (None, "", [], {})}


def _source_map_approval_command_items(
    project: ProjectRef, value: object
) -> list[dict] | None:
    if not isinstance(value, list):
        return None
    items = [
        mapped
        for mapped in (_source_map_approval_command_item(project, item) for item in value)
        if mapped
    ]
    return items or None


def _source_map_approval_recovery(project: ProjectRef, qa_report: object | None) -> dict:
    metadata = getattr(qa_report, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    mapped: dict[str, object] = {}
    for key in (
        "approval_gate_error_code",
        "approval_gate_message_zh",
        "approval_gate_hint_zh",
        "stale_approval_targets",
        "missing_approval_targets",
        "stale_approval_notice_zh",
        "approval_required_notice_zh",
        "voice_reapproval_required",
        "visuals_reapproval_required",
        "voice_reapproval_message_zh",
    ):
        value = metadata.get(key)
        if value not in (None, "", [], {}):
            mapped[key] = value
    for key in ("voice_approval_command", "visuals_approval_command"):
        command = _source_map_command_text(project, metadata.get(key))
        if command:
            mapped[key] = command
    for key in ("stale_approval_commands", "missing_approval_commands"):
        command_items = _source_map_approval_command_items(project, metadata.get(key))
        if command_items:
            mapped[key] = command_items
    return mapped


def _source_map(
    project: ProjectRef, source_manifest: dict, qa_report: object | None = None
) -> list[dict]:
    source_map: list[dict] = []
    offset = 0.0
    scenes = source_manifest.get("scenes")
    if not isinstance(scenes, list):
        return source_map
    scene_durations = [
        _positive_float(scene.get("duration_sec")) or 0.0
        for scene in scenes
        if isinstance(scene, dict)
    ]
    total_duration = sum(scene_durations)
    incoming_transitions, outgoing_transitions = _source_map_transition_lookup(
        source_manifest, scenes
    )
    transition_diagnostics = _source_map_transition_diagnostics(source_manifest)
    bgm_track = _source_map_bgm_track(project, source_manifest, total_duration)
    audio_diagnostics = _source_map_audio_diagnostics(source_manifest)
    voice_lookup = _source_map_voice_lookup(project)
    evidence_lookup = _source_map_evidence_lookup(project)
    evidence_recovery_lookup = _source_map_evidence_recovery_lookup(project, qa_report)
    audio_recovery_lookup = _source_map_audio_recovery_lookup(project, qa_report)
    stock_image_recovery_lookup = _source_map_stock_image_recovery_lookup(qa_report)
    approval_recovery = _source_map_approval_recovery(project, qa_report)
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        duration = _positive_float(scene.get("duration_sec")) or 0.0
        scene_id = _caption_text(scene.get("scene_id") or scene.get("id") or f"s{index}")
        caption_cues = _source_map_caption_cues(scene, offset)
        refs = scene.get("evidence_asset_refs")
        entry = {
            "scene_id": scene_id,
            "scene_number": index,
            "start_sec": round(offset, 3),
            "end_sec": round(offset + duration, 3),
            "duration_sec": round(duration, 3),
            "narration_text": scene.get("narration_text"),
            "on_screen_text": scene.get("on_screen_text") or scene.get("screen_text"),
            "voice_segment": voice_lookup.get(scene_id),
            "director_review": _source_map_director_review(scene),
            "audio_visual_alignment": _source_map_audio_visual_alignment(
                project, source_manifest, scene
            ),
            "evidence_contract": _source_map_evidence_contract(scene),
            "asset_path": scene.get("asset_path"),
            "render_source": scene.get("render_source"),
            "asset_origin": scene.get("asset_origin"),
            "caption_count": len(caption_cues),
            "caption_cues": caption_cues,
            "caption_timing": _source_map_caption_timing(scene),
            "caption_audit": _source_map_caption_audit(project, scene),
            "incoming_transition": incoming_transitions.get(scene_id),
            "outgoing_transition": outgoing_transitions.get(scene_id),
            "transition_diagnostics": transition_diagnostics,
            "sfx_events": _source_map_sfx_events(
                project, source_manifest, scene_id, offset, offset + duration
            ),
            "bgm_track": bgm_track,
            "audio_diagnostics": audio_diagnostics,
            "stock_image_policy": _source_map_stock_image_policy(scene),
            "evidence_assets": _source_map_evidence_assets(project, scene, evidence_lookup),
            "evidence_asset_refs": refs if isinstance(refs, list) else [],
            "qa_evidence_recovery": evidence_recovery_lookup.get(scene_id, []),
            "qa_audio_recovery": audio_recovery_lookup.get(scene_id, []),
            "qa_stock_image_recovery": stock_image_recovery_lookup.get(scene_id, []),
            "qa_approval_recovery": approval_recovery,
        }
        source_map.append(entry)
        offset += duration
    return source_map


def _export_root(project: ProjectRef) -> Path:
    if project.path.parent.name == "projects":
        return project.path.parent.parent / "exports"
    return project.path.parent / "exports"


def _latest_any_render_manifest(project: ProjectRef, mode: str) -> dict | None:
    render_root = project.path / "renders" / mode
    if not render_root.exists():
        return None
    for manifest_path in sorted(render_root.glob("*/render_manifest.json")):
        return read_json(manifest_path)
    return None


def _license_manifest_text(source_manifest: dict) -> str:
    lines = ["# License Manifest", "", "- renderer: ffmpeg_card"]
    inherited_llm_ids = {"claude_cli", "codex_cli", "ollama_cli", "llm_local_cli"}
    local_tts_ids = {"kokoro_zh_tts", "macos_say", "piper_cli", "espeak_ng"}
    for provider in source_manifest.get("providers", []):
        provider_id = provider.get("id")
        if provider_id in {"llm_cli", "tts_cli"}:
            lines.append(f"- {provider_id}: User supplied CLI provider")
        if provider_id in inherited_llm_ids:
            lines.append(f"- {provider_id}: Inherited CLI provider")
        if provider_id in local_tts_ids:
            lines.append(f"- {provider_id}: Local TTS provider")
        if provider_id in {"openai_compatible", "openai_compatible_tts"}:
            lines.append(f"- {provider_id}: OpenAI-compatible API provider")
        if provider_id == "volcengine_tts":
            lines.append("- volcengine_tts: Volcengine Doubao TTS API provider")
        if provider_id == "user_audio":
            lines.append("- user_audio: User supplied recorded narration")
    return "\n".join(lines) + "\n"


def _export_qa_report(project: ProjectRef, platform: str, release: bool, strict: bool):
    if release:
        return run_qa(project, release=True, platform=platform, strict=strict)
    if strict:
        return run_qa(project, release=True, platform=platform, strict=True)
    return run_qa(project, release=False, platform=platform, strict=False)


def export_project(
    project: ProjectRef,
    platform: str,
    language: str,
    ratio: str,
    release: bool = False,
    allow_preview_source: bool = False,
    strict: bool = False,
) -> ExportPackageResult:
    platform = safe_segment(platform, "platform")
    language = safe_segment(language, "language")
    preview_manifest = latest_render_manifest(project, platform, "preview")
    release_manifest = latest_render_manifest(project, platform, "release")
    fallback_preview_manifest = preview_manifest or _latest_any_render_manifest(project, "preview")
    fallback_release_manifest = release_manifest or _latest_any_render_manifest(project, "release")

    if release and allow_preview_source and fallback_preview_manifest is not None:
        raise LingjianError(
            "PREVIEW_ARTIFACT_NOT_RELEASABLE",
            "preview 渲染产物不能用于正式发布。",
            "请使用真实 provider 重新生成 release render。",
        )

    source_manifest = (
        fallback_release_manifest
        if release
        else fallback_preview_manifest or fallback_release_manifest
    )
    if release and source_manifest is None and fallback_preview_manifest is not None:
        if any(
            provider.get("is_mock") for provider in fallback_preview_manifest.get("providers", [])
        ):
            raise LingjianError(
                "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE",
                "mock provider 不能用于正式发布。",
                "请配置真实 LLM/TTS provider 后重试。",
            )
        raise LingjianError(
            "PREVIEW_ARTIFACT_NOT_RELEASABLE",
            "preview 渲染产物不能用于正式发布。",
            "请使用 release render 后重试。",
        )
    if source_manifest is None:
        raise LingjianError("RENDER_FAILED", "缺少可导出的渲染产物。", "请先运行 render/preview。")

    if release and any(
        provider.get("is_mock") for provider in source_manifest.get("providers", [])
    ):
        raise LingjianError(
            "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE",
            "mock provider 不能用于正式发布。",
            "请配置真实 LLM/TTS provider 后重试。",
        )

    qa_report = _export_qa_report(project, platform, release, strict)
    if release and not qa_report.release_ready:
        raise LingjianError("QA_BLOCKING", "QA hard fail 阻止 release。", "请修复 QA 问题后重试。")

    export_dir = _export_root(project) / project.path.name / platform / language / _ratio_dir(ratio)
    export_dir.mkdir(parents=True, exist_ok=True)
    source_video = resolve_inside(project.path, project.path / source_manifest["video_path"])
    shutil.copy2(source_video, export_dir / "video.mp4")

    for subtitle_name, subtitle_text in _subtitle_files(source_manifest).items():
        _write_text(export_dir / "captions" / subtitle_name, subtitle_text)
    _write_text(
        export_dir / "source_map.json",
        json.dumps(_source_map(project, source_manifest, qa_report), ensure_ascii=False, indent=2)
        + "\n",
    )
    _write_text(
        export_dir / "artifacts" / "render_manifest.json",
        json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n",
    )
    for review_artifact in (
        "artifacts/script.json",
        "artifacts/voice_plan.json",
        "artifacts/visual_plan.json",
        "artifacts/director_review_sheet.md",
    ):
        _copy_project_file_if_exists(project, export_dir, review_artifact)
    _copy_evidence_sources(project, export_dir, source_manifest)
    _copy_audio_sources(project, export_dir, source_manifest)
    qa_md = project.path / "artifacts" / "qa_report.md"
    if qa_md.exists():
        _write_text(
            export_dir / "qa_report.md",
            _redact_project_path_in_string(project, qa_md.read_text(encoding="utf-8")),
        )
    else:
        _write_text(export_dir / "qa_report.md", "# QA Report\n")
    evidence_checklist = project.path / "artifacts" / "evidence_collection_checklist.md"
    if evidence_checklist.exists():
        _copy_redacted_project_text_file_if_exists(
            project, export_dir, "artifacts/evidence_collection_checklist.md"
        )
    _write_text(
        export_dir / "license_manifest.md",
        _license_manifest_text(source_manifest),
    )
    _write_text(export_dir / "cover.png", "stub cover\n")
    _write_text(export_dir / "metadata" / "publish.md", "# 发布文案\n")
    for relative_path, content in PLATFORM_EXTRA_FILES.get(platform, {}).items():
        _write_text(export_dir / relative_path, content)
    provider_manifest = {
        "release_allowed": not any(
            provider.get("is_mock") for provider in source_manifest["providers"]
        ),
        "providers": source_manifest["providers"],
    }
    _write_text(
        export_dir / "provider_manifest.json",
        json.dumps(provider_manifest, ensure_ascii=False, indent=2),
    )
    _write_export_qa_report_json(project, export_dir)

    export_manifest = {
        "project_id": project.path.name,
        "platform": platform,
        "language": language,
        "ratio": ratio,
        "release": release,
        "approvals": _approvals(project),
    }
    _write_text(
        export_dir / "export_manifest.json",
        json.dumps(export_manifest, ensure_ascii=False, indent=2),
    )
    return ExportPackageResult(export_dir=export_dir, export_manifest=export_manifest)
