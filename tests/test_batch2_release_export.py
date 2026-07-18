import json
import subprocess
from pathlib import Path

from packages.core.approvals import approve_target
from packages.core.artifacts import write_artifact
from packages.core.director_contract import director_review_sheet_markdown
from packages.core.errors import LingjianError
from packages.core.evidence_assets import collect_evidence_assets
from packages.core.exporting import export_project
from packages.core.hash import canonical_json_hash
from packages.core.project import init_project
from packages.core.qa import QAIssue, QAReport, run_qa
from packages.core.rendering import (
    RELEASE_LOUDNORM_FILTER,
    STUB_VIDEO_BYTES,
    _release_audio_path,
    _release_duration,
    _xfade_name,
    render_project,
)


def _write_visuals_artifact(project, artifact: dict) -> None:
    write_artifact(project, "visuals", artifact)
    review_path = project.path / "artifacts" / "director_review_sheet.md"
    review_path.write_text(director_review_sheet_markdown(artifact), encoding="utf-8")


def _approved_mock_project(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    write_artifact(
        project,
        "script",
        {"id": "script", "provider_id": "mock", "provider_is_mock": True, "scenes": []},
    )
    write_artifact(
        project,
        "voice",
        {"id": "voice", "provider_id": "mock", "provider_is_mock": True, "segments": []},
    )
    _write_visuals_artifact(project, {"id": "visuals", "engine": "ffmpeg_card", "scenes": []})
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    return project


def _is_ffprobe_command(command: list[str]) -> bool:
    return Path(str(command[0])).name == "ffprobe"


def _fake_ffprobe_audio(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps({"streams": [{"codec_type": "audio"}]}),
        stderr="",
    )


def _fake_ffprobe_audio_or_video(command: list[str]) -> subprocess.CompletedProcess:
    stream_type = "video" if Path(command[-1]).suffix.lower() == ".mp4" else "audio"
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps({"streams": [{"codec_type": stream_type}]}),
        stderr="",
    )


def _approved_release_project_with_required_evidence(
    tmp_path: Path,
    *,
    name: str,
    evidence_refs: list[dict] | None = None,
    evidence_assets: list[dict] | None = None,
):
    project = init_project(tmp_path / name, "项目")
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "full.wav").write_bytes(b"VOICE")
    scene_dir = project.path / "assets" / "scenes"
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "s1.mp4").write_bytes(b"VIDEO")
    for asset in evidence_assets or []:
        clip_path = asset.get("evidence_clip_path")
        if isinstance(clip_path, str) and clip_path:
            (project.path / clip_path).parent.mkdir(parents=True, exist_ok=True)
            (project.path / clip_path).write_bytes(b"EVIDENCE")
    evidence_manifest = {
        "version": "v1",
        "assets": evidence_assets or [],
        "evidence_types": sorted(
            {
                str(asset.get("evidence_type"))
                for asset in evidence_assets or []
                if asset.get("evidence_type")
            }
        ),
        "count": len(evidence_assets or []),
    }
    (project.path / "assets" / "evidence" / "evidence_assets.json").write_text(
        json.dumps(evidence_manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "真实证据镜头"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/full.wav",
                    "duration_sec": 4.0,
                    "caption_cues": [
                        {"text": "真实证据", "start_sec": 0.2, "end_sec": 1.6},
                        {"text": "镜头", "start_sec": 1.8, "end_sec": 2.8},
                    ],
                }
            ],
            "total_duration_sec": 4.0,
        },
    )
    scene = {
        "scene_id": "s1",
        "narration_text": "真实证据镜头",
        "duration_sec": 4.0,
        "generator": "user-asset",
        "asset_path": "assets/scenes/s1.mp4",
        "subtitle_burn": True,
        "requires_real_evidence_asset": True,
        "expected_real_evidence": ["Codex app 操作录屏"],
    }
    if evidence_refs is not None:
        scene["evidence_asset_refs"] = evidence_refs
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [scene],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    return project


def test_preview_render_writes_preview_manifest_and_release_export_refuses_preview(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")

    assert render_result.mode == "preview"
    assert render_result.video_path.parts[-3:] == ("preview", "douyin", "video.mp4")

    try:
        export_project(project, "douyin", "zh-CN", "9:16", release=True, allow_preview_source=True)
    except LingjianError as exc:
        assert exc.error_code == "PREVIEW_ARTIFACT_NOT_RELEASABLE"
    else:
        raise AssertionError("expected PREVIEW_ARTIFACT_NOT_RELEASABLE")


def test_release_export_refuses_mock_provider(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_project(project, "douyin", "zh-CN", "9:16", mode="preview")

    try:
        export_project(project, "douyin", "zh-CN", "9:16", release=True)
    except LingjianError as exc:
        assert exc.error_code == "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE"
    else:
        raise AssertionError("expected MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE")


def test_preview_export_writes_canonical_package_with_approval_provenance(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "narration_text": "第一镜口播",
            "on_screen_text": "第一镜短文案",
            "audio_visual_alignment": {
                "status": "verified",
                "notes": "口播提到一句话触发,画面展示 Codex 对话和项目关键词。",
                "method": "manual_watch_and_manifest",
                "verified_by": "tester",
                "evidence_refs": [
                    {
                        "id": "ev-s1",
                        "evidence_type": "screen_recording_capture",
                        "target_scene_id": "s1",
                        "external_path": "/Users/example/raw-screen.mov",
                    }
                ],
                "proof": {"raw_path": "/Users/example/raw-screen.mov"},
            },
            "director_review_sheet_v2": {
                "version": "v2",
                "scene_goal": "Hook",
                "visual_content": "展示一句话触发灵剪",
                "asset_strategy": {"asset_status": "ready_user_video"},
                "composition": "左侧 Codex 对话,右侧项目关键词",
                "caption_region": {"position": "bottom_safe_area"},
                "transition": "clean wipe",
                "main_motion": "界面推进加关键词浮现",
                "qa_checkpoints": ["字幕不遮挡主体", "真实动态证据为主画面"],
            },
            "caption_cues": [
                {"text": "第一句", "start_sec": 0.0, "end_sec": 1.0, "source": "estimated"}
            ],
            "caption_timing": {
                "source": "estimated",
                "estimated_max_cue_sec": 1.8,
                "release_ready": False,
                "release_gate": "strict_caption_timing",
                "release_blocker_code": "RELEASE_CAPTION_TIMING_IS_ESTIMATED",
                "release_blocker_zh": "当前字幕 timing 来自 estimated fallback。",
                "recovery_target_field": "artifacts/voice_plan.json segments[].caption_cues",
                "recovery_next_action_zh": "请补齐真实 TTS/ASR/人工校准字幕时间戳。",
                "required_timing_basis": "real_segment_duration",
                "accepted_timing_sources": [
                    "voice_plan.caption_cues",
                    "voice_plan.timed_captions",
                    "ASR",
                    "manual_timing",
                ],
            },
        },
        {
            "scene_id": "s2",
            "duration_sec": 3.0,
            "asset_path": "assets/scenes/s2.mp4",
            "render_source": "video",
            "transition_plan": {"family": "clean-wipe"},
            "requires_real_evidence_asset": True,
            "expected_real_evidence": ["Codex 操作录屏"],
            "asset_strategy_v2": {
                "profile": "open_source_project_intro",
                "blueprint_id": "codex_prompt_capture",
                "current_asset_kind": "video",
                "current_asset_status": "ready_user_video",
                "publish_grade_visual": True,
                "next_action_zh": "重新运行灵剪主线绑定录屏。",
            },
            "evidence_asset_refs": [
                {
                    "id": "ev-s2",
                    "evidence_type": "codex_operation_recording",
                    "target_scene_id": "s2",
                }
            ],
            "caption_cues": [
                {
                    "text": "第二句",
                    "start_sec": 0.5,
                    "end_sec": 1.5,
                    "source": "voice_duration_aligned",
                    "timing_basis": "real_segment_duration",
                }
            ],
            "caption_timing": {
                "source": "voice_duration_aligned",
                "timing_basis": "real_segment_duration",
                "max_cue_sec": 1.8,
                "release_ready": True,
                "release_gate": "strict_caption_timing",
            },
        },
    ]
    manifest["transition_rendering"] = {
        "rendered": True,
        "mode": "ffmpeg_xfade",
        "transition_count": 1,
        "transitions": [
            {
                "from_scene_id": "s1",
                "to_scene_id": "s2",
                "family": "clean-wipe",
                "xfade": "wipeleft",
                "offset_sec": 1.7,
                "duration_sec": 0.3,
            }
        ],
    }
    manifest["audio_mix"] = {
        "rendered": True,
        "mixed_audio_path": "renders/preview/douyin/mixed_audio.m4a",
        "bgm_present": True,
        "bgm_path": "assets/audio/bgm.wav",
        "bgm_to_voice_db": -16.0,
        "sfx_count": 1,
        "sfx_events": [
            {
                "path": "assets/audio/click.wav",
                "at_sec": 2.75,
                "local_at_sec": 0.75,
                "time_basis": "scene_local",
                "gain_db": -12.0,
                "scene_id": "s2",
                "action": "Star CTA",
                "purpose": "强调行动",
                "visual_event": "button_press",
                "cue_id": "cta-hit",
            }
        ],
        "invalid_audio_asset_count": 2,
        "invalid_audio_assets": [
            {
                "kind": "bgm",
                "path": "assets/audio/missing-bgm.wav",
                "reason": "missing_or_unverifiable",
            },
            {
                "kind": "sfx",
                "path": "<external-redacted>",
                "scene_id": "s2",
                "action": "Star CTA",
                "reason": "missing_or_unverifiable",
            },
        ],
        "declared_audio_requirements": {
            "bgm_required": True,
            "bgm_scene_ids": ["s1"],
            "bgm_texts_by_scene": [
                {"scene_id": "s1", "texts": ["克制科技感 BGM,人声优先。"]}
            ],
            "sfx_required": True,
            "sfx_scene_ids": ["s2"],
            "sfx_markers_by_scene": [
                {"scene_id": "s2", "markers": ["star cta", "cta-hit"]}
            ],
        },
    }
    voice_dir = project.path / "artifacts" / "voice_segments"
    voice_dir.mkdir(parents=True, exist_ok=True)
    full_voice = voice_dir / "full.wav"
    scene_voice = voice_dir / "s1.wav"
    scene_voice_2 = voice_dir / "s2.wav"
    full_voice.write_bytes(b"FULL-VOICE")
    scene_voice.write_bytes(b"SCENE-VOICE")
    scene_voice_2.write_bytes(b"SCENE-VOICE-2")
    voice_plan_path = project.path / "artifacts" / "voice_plan.json"
    voice_plan = json.loads(voice_plan_path.read_text(encoding="utf-8"))
    voice_plan.update(
        {
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 2.0,
                    "voice_id": "voice-a",
                    "provider_id": "volcengine_tts",
                    "quality_tier": "publish",
                    "provider_voice_settings": {
                        "emotion": "product_intro",
                        "speed": 1.0,
                        "access_token": "must-not-export",
                    },
                },
                {
                    "scene_id": "s2",
                    "audio_path": "artifacts/voice_segments/s2.wav",
                    "duration_sec": 3.0,
                    "voice_id": "voice-a",
                    "provider_id": "volcengine_tts",
                    "quality_tier": "publish",
                    "caption_cues": [
                        {
                            "text": "第二句",
                            "start_sec": 0.5,
                            "end_sec": 1.5,
                            "source": "voice_duration_aligned",
                            "timing_basis": "real_segment_duration",
                        }
                    ],
                }
            ],
        }
    )
    voice_plan_path.write_text(
        json.dumps(voice_plan, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    bgm_path = project.path / "assets" / "audio" / "bgm.wav"
    sfx_path = project.path / "assets" / "audio" / "click.wav"
    bgm_path.parent.mkdir(parents=True, exist_ok=True)
    bgm_path.write_bytes(b"BGM-AUDIO")
    sfx_path.write_bytes(b"SFX-AUDIO")
    mixed_audio = project.path / "renders" / "preview" / "douyin" / "mixed_audio.m4a"
    mixed_audio.parent.mkdir(parents=True, exist_ok=True)
    mixed_audio.write_bytes(b"MIXED-AUDIO")
    evidence_video = project.path / "assets" / "evidence" / "videos" / "codex-s2.mp4"
    evidence_video.parent.mkdir(parents=True, exist_ok=True)
    evidence_video.write_bytes(b"EVIDENCE-VIDEO")
    evidence_note = project.path / "assets" / "evidence" / "clips" / "codex-s2.txt"
    evidence_note.parent.mkdir(parents=True, exist_ok=True)
    evidence_note.write_text("Codex 操作录屏说明\n", encoding="utf-8")
    terminal_log = project.path / "logs" / "terminal-s2.log"
    terminal_log.parent.mkdir(parents=True, exist_ok=True)
    terminal_log.write_text("uv run lj qa --release --strict\n", encoding="utf-8")
    input_assets = [
        {
            "type": "codex_operation",
            "source_uri": "codex://task",
            "recording_path": "assets/evidence/videos/codex-s2.mp4",
            "recording_evidence_type": "codex_operation_recording",
            "target_scene_id": "s2",
            "original_path_redacted": True,
        }
    ]
    (project.path / "assets" / "input_assets.json").write_text(
        json.dumps(input_assets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    evidence_manifest = {
        "version": "v1",
        "assets": [
            {
                "id": "ev-s2",
                "path": "assets/evidence/videos/codex-s2.mp4",
                "evidence_clip_path": "assets/evidence/clips/codex-s2.txt",
                "source_uri": "logs/terminal-s2.log",
                "evidence_clip_status": "captured",
                "evidence_clip_render_source": "source_video_capture",
                "evidence_visual_source": "codex_operation_recording",
                "evidence_clip_style": "codex_operation",
                "evidence_clip_role_zh": "Codex 操作录屏",
                "materialized_evidence_video": True,
                "publish_grade_evidence_video": True,
                "recording_status": "captured",
                "source_video_probe_status": "verifiable",
                "source_video_probe_tool": "ffprobe",
                "source_video_has_video_stream": True,
                "source_video_duration_sec": 2.4,
                "evidence_clip_duration_sec": 2.4,
                "recording_task_redacted": "展示 Codex app 触发灵剪 TOKEN=***",
                "publish_grade_visual_candidate": True,
                "target_scene_id": "s2",
                "next_action_zh": "重新运行灵剪主线绑定录屏。",
                "next_command": f"uv run lj run {project.path} --release --json",
                "screen_recording_consent_required": True,
                "screen_recording_consent": False,
                "privacy_notice_zh": "请确认当前屏幕没有私密信息。",
                "manual_fallback_command": (
                    f"uv run lj ingest video {project.path} --file '把录屏文件拖到这里.mp4' "
                    "--role codex_recording --scene-id s2 --json"
                ),
                "manual_fallback_note_zh": "不授权自动录屏时,先手动录好 mp4 再导入。",
            }
        ],
    }
    (project.path / "assets" / "evidence" / "evidence_assets.json").write_text(
        json.dumps(evidence_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    checklist = project.path / "artifacts" / "evidence_collection_checklist.md"
    checklist.write_text(
        (
            "# 真实动态证据素材采集清单\n\n"
            f"uv run lj ingest video {project.path} --file demo.mp4 "
            "--role codex_recording --scene-id s2 --json\n"
        ),
        encoding="utf-8",
    )
    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    export_dir = package.export_dir
    assert (export_dir / "video.mp4").exists()
    assert (export_dir / "captions" / "subtitles.srt").exists()
    assert (export_dir / "captions" / "subtitles.vtt").exists()
    assert (export_dir / "captions" / "subtitles.ass").exists()
    srt = (export_dir / "captions" / "subtitles.srt").read_text(encoding="utf-8")
    vtt = (export_dir / "captions" / "subtitles.vtt").read_text(encoding="utf-8")
    ass = (export_dir / "captions" / "subtitles.ass").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,000\n第一句" in srt
    assert "00:00:02,500 --> 00:00:03,500\n第二句" in srt
    assert "00:00:02.500 --> 00:00:03.500\n第二句" in vtt
    assert "Dialogue: 0,0:00:02.50,0:00:03.50,Default,,0,0,0,,第二句" in ass
    assert "\n灵剪\n" not in srt
    source_map = json.loads((export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["scene_id"] == "s1"
    assert source_map[0]["start_sec"] == 0.0
    assert source_map[0]["narration_text"] == "第一镜口播"
    assert source_map[0]["on_screen_text"] == "第一镜短文案"
    assert source_map[0]["voice_segment"] == {
        "scene_id": "s1",
        "audio_path": "artifacts/voice_segments/s1.wav",
        "voice_id": "voice-a",
        "provider_id": "volcengine_tts",
        "quality_tier": "publish",
        "duration_sec": 2.0,
        "provider_voice_settings": {"emotion": "product_intro", "speed": 1.0},
    }
    assert "access_token" not in json.dumps(
        source_map[0]["voice_segment"], ensure_ascii=False
    )
    assert source_map[0]["director_review"] == {
        "version": "v2",
        "scene_goal": "Hook",
        "visual_content": "展示一句话触发灵剪",
        "asset_strategy": {"asset_status": "ready_user_video"},
        "composition": "左侧 Codex 对话,右侧项目关键词",
        "caption_region": {"position": "bottom_safe_area"},
        "transition": "clean wipe",
        "main_motion": "界面推进加关键词浮现",
        "qa_checkpoints": ["字幕不遮挡主体", "真实动态证据为主画面"],
    }
    assert source_map[0]["audio_visual_alignment"] == {
        "source": "scene",
        "status": "verified",
        "notes": "口播提到一句话触发,画面展示 Codex 对话和项目关键词。",
        "method": "manual_watch_and_manifest",
        "verified_by": "tester",
        "evidence_refs": [
            {
                "id": "ev-s1",
                "evidence_type": "screen_recording_capture",
                "target_scene_id": "s1",
            }
        ],
        "has_text_evidence": True,
        "evidence_ref_count": 1,
        "evidence_ref_verifiable": False,
        "has_evidence": True,
    }
    assert "/Users/" not in json.dumps(
        source_map[0]["audio_visual_alignment"], ensure_ascii=False
    )
    assert source_map[0]["caption_cues"] == [
        {"text": "第一句", "start_sec": 0.0, "end_sec": 1.0, "source": "estimated"}
    ]
    assert source_map[0]["caption_timing"] == {
        "source": "estimated",
        "estimated_max_cue_sec": 1.8,
        "release_ready": False,
        "release_gate": "strict_caption_timing",
        "release_blocker_code": "RELEASE_CAPTION_TIMING_IS_ESTIMATED",
        "release_blocker_zh": "当前字幕 timing 来自 estimated fallback。",
        "recovery_target_field": "artifacts/voice_plan.json segments[].caption_cues",
        "recovery_next_action_zh": "请补齐真实 TTS/ASR/人工校准字幕时间戳。",
        "required_timing_basis": "real_segment_duration",
        "accepted_timing_sources": [
            "voice_plan.caption_cues",
            "voice_plan.timed_captions",
            "ASR",
            "manual_timing",
        ],
    }
    assert source_map[0]["caption_audit"] == {
        "timing_source": "estimated",
        "cue_sources": ["estimated"],
        "estimated_timing": True,
        "requires_voice_plan": False,
    }
    assert source_map[0]["outgoing_transition"] == {
        "from_scene_id": "s1",
        "to_scene_id": "s2",
        "family": "clean-wipe",
        "xfade": "wipeleft",
        "mode": "ffmpeg_xfade",
        "offset_sec": 1.7,
        "duration_sec": 0.3,
        "semantic_audit": {
            "planned_scene_id": "s2",
            "plan_present": True,
            "planned_family": "clean-wipe",
            "expected_xfade": "wipeleft",
            "actual_family": "clean-wipe",
            "actual_xfade": "wipeleft",
            "semantic_match": True,
        },
    }
    assert source_map[0]["transition_diagnostics"] == {
        "rendered": True,
        "mode": "ffmpeg_xfade",
        "transition_count": 1,
    }
    assert source_map[0]["bgm_track"] == {
        "path": "assets/audio/bgm.wav",
        "start_sec": 0.0,
        "end_sec": 5.0,
        "bgm_to_voice_db": -16.0,
        "mixed_audio_path": "renders/preview/douyin/mixed_audio.m4a",
        "rendered": True,
    }
    assert source_map[0]["audio_diagnostics"] == {
        "invalid_audio_asset_count": 2,
        "invalid_audio_assets": [
            {
                "kind": "bgm",
                "path": "assets/audio/missing-bgm.wav",
                "reason": "missing_or_unverifiable",
            },
            {
                "kind": "sfx",
                "path": "<external-redacted>",
                "scene_id": "s2",
                "action": "Star CTA",
                "reason": "missing_or_unverifiable",
            },
        ],
        "declared_audio_requirements": {
            "bgm_required": True,
            "bgm_scene_ids": ["s1"],
            "bgm_texts_by_scene": [
                {"scene_id": "s1", "texts": ["克制科技感 BGM,人声优先。"]}
            ],
            "sfx_required": True,
            "sfx_scene_ids": ["s2"],
            "sfx_markers_by_scene": [
                {"scene_id": "s2", "markers": ["star cta", "cta-hit"]}
            ],
        },
    }
    assert "/Users/" not in json.dumps(source_map[0]["audio_diagnostics"], ensure_ascii=False)
    assert source_map[1]["scene_id"] == "s2"
    assert source_map[1]["start_sec"] == 2.0
    assert source_map[1]["end_sec"] == 5.0
    assert source_map[1]["caption_count"] == 1
    assert source_map[1]["caption_cues"] == [
        {
            "text": "第二句",
            "start_sec": 2.5,
            "end_sec": 3.5,
            "source": "voice_duration_aligned",
            "timing_basis": "real_segment_duration",
        }
    ]
    assert source_map[1]["caption_timing"] == {
        "source": "voice_duration_aligned",
        "timing_basis": "real_segment_duration",
        "max_cue_sec": 1.8,
        "release_ready": True,
        "release_gate": "strict_caption_timing",
    }
    assert source_map[1]["caption_audit"] == {
        "timing_source": "voice_duration_aligned",
        "timing_basis": "real_segment_duration",
        "cue_sources": ["voice_duration_aligned"],
        "cue_timing_bases": ["real_segment_duration"],
        "estimated_timing": False,
        "requires_voice_plan": True,
        "required_sources": ["voice_duration_aligned"],
        "voice_plan_segment_found": True,
        "voice_plan_caption_cue_count": 1,
        "voice_plan_backed": True,
    }
    assert source_map[1]["evidence_contract"] == {
        "requires_real_evidence_asset": True,
        "expected_real_evidence": ["Codex 操作录屏"],
        "expected_evidence_type_groups": [
            ["codex_operation_recording", "screenshot_capture", "web_recording_capture"]
        ],
        "asset_strategy": {
            "profile": "open_source_project_intro",
            "blueprint_id": "codex_prompt_capture",
            "current_asset_kind": "video",
            "current_asset_status": "ready_user_video",
            "publish_grade_visual": True,
            "next_action_zh": "重新运行灵剪主线绑定录屏。",
        },
        "recording_intent_marker_groups": [
            ["codex", "灵剪", "lingjian", "lingjian-video"],
            ["触发", "一句话", "prompt", "对话", "输入"],
        ],
    }
    assert source_map[1]["incoming_transition"] == source_map[0]["outgoing_transition"]
    assert source_map[1]["evidence_assets"] == [
        {
            "id": "ev-s2",
            "evidence_type": "codex_operation_recording",
            "target_scene_id": "s2",
            "evidence_clip_status": "captured",
            "evidence_clip_render_source": "source_video_capture",
            "evidence_visual_source": "codex_operation_recording",
            "evidence_clip_style": "codex_operation",
            "evidence_clip_role_zh": "Codex 操作录屏",
            "recording_status": "captured",
            "source_video_probe_status": "verifiable",
            "source_video_probe_tool": "ffprobe",
            "source_video_duration_sec": 2.4,
            "evidence_clip_duration_sec": 2.4,
            "recording_task_redacted": "展示 Codex app 触发灵剪 TOKEN=***",
            "target_scene_matches": True,
            "expected_evidence_type_matches": True,
            "recording_task_intent_matches": True,
            "primary_visual_consumed": False,
            "primary_visual_consumption_source": "none",
            "scene_asset_path": "assets/scenes/s2.mp4",
            "next_action_zh": "重新运行灵剪主线绑定录屏。",
            "next_command": "uv run lj run <project> --release --json",
            "manual_fallback_command": (
                "uv run lj ingest video <project> --file '把录屏文件拖到这里.mp4' "
                "--role codex_recording --scene-id s2 --json"
            ),
            "manual_fallback_note_zh": "不授权自动录屏时,先手动录好 mp4 再导入。",
            "privacy_notice_zh": "请确认当前屏幕没有私密信息。",
            "screen_recording_consent_required": True,
            "screen_recording_consent": False,
            "path": "assets/evidence/videos/codex-s2.mp4",
            "source_uri": "logs/terminal-s2.log",
            "evidence_clip_path": "assets/evidence/clips/codex-s2.txt",
            "materialized_evidence_video": True,
            "publish_grade_evidence_video": True,
            "publish_grade_visual_candidate": True,
            "source_video_has_video_stream": True,
        }
    ]
    assert "/Users/" not in json.dumps(source_map[1]["evidence_assets"], ensure_ascii=False)
    assert str(project.path) not in json.dumps(
        source_map[1]["evidence_assets"], ensure_ascii=False
    )
    assert source_map[1]["sfx_events"] == [
        {
            "path": "assets/audio/click.wav",
            "scene_id": "s2",
            "action": "Star CTA",
            "purpose": "强调行动",
            "visual_event": "button_press",
            "cue_id": "cta-hit",
            "time_basis": "scene_local",
            "at_sec": 2.75,
            "local_at_sec": 0.75,
            "gain_db": -12.0,
        }
    ]
    assert source_map[1]["evidence_asset_refs"][0]["target_scene_id"] == "s2"
    exported_render_manifest = json.loads(
        (export_dir / "artifacts" / "render_manifest.json").read_text(encoding="utf-8")
    )
    assert exported_render_manifest["scenes"] == manifest["scenes"]
    assert exported_render_manifest["transition_rendering"] == manifest["transition_rendering"]
    assert exported_render_manifest["audio_mix"] == manifest["audio_mix"]
    for artifact_name in (
        "script.json",
        "voice_plan.json",
        "visual_plan.json",
        "director_review_sheet.md",
    ):
        exported_artifact = export_dir / "artifacts" / artifact_name
        source_artifact = project.path / "artifacts" / artifact_name
        assert exported_artifact.read_text(encoding="utf-8") == source_artifact.read_text(
            encoding="utf-8"
        )
    assert (export_dir / "provider_manifest.json").exists()
    assert (export_dir / "license_manifest.md").exists()
    qa_report = (export_dir / "qa_report.md").read_text(encoding="utf-8")
    assert "release_ready:" in qa_report
    assert "## Info" in qa_report
    exported_checklist = export_dir / "artifacts" / "evidence_collection_checklist.md"
    exported_checklist_text = exported_checklist.read_text(encoding="utf-8")
    assert "uv run lj ingest video <project> --file demo.mp4" in exported_checklist_text
    assert str(project.path) not in exported_checklist_text
    assert (export_dir / "assets" / "input_assets.json").read_text(
        encoding="utf-8"
    ) == (project.path / "assets" / "input_assets.json").read_text(encoding="utf-8")
    exported_evidence_manifest = json.loads(
        (export_dir / "assets" / "evidence" / "evidence_assets.json").read_text(
            encoding="utf-8"
        )
    )
    assert exported_evidence_manifest["assets"][0]["next_command"] == (
        "uv run lj run <project> --release --json"
    )
    assert "uv run lj ingest video <project>" in exported_evidence_manifest["assets"][0][
        "manual_fallback_command"
    ]
    assert str(project.path) not in json.dumps(
        exported_evidence_manifest, ensure_ascii=False
    )
    assert str(project.path) in (
        project.path / "assets" / "evidence" / "evidence_assets.json"
    ).read_text(
        encoding="utf-8",
    )
    assert (export_dir / "assets" / "evidence" / "videos" / "codex-s2.mp4").read_bytes() == (
        evidence_video.read_bytes()
    )
    assert (export_dir / "assets" / "evidence" / "clips" / "codex-s2.txt").read_text(
        encoding="utf-8"
    ) == evidence_note.read_text(encoding="utf-8")
    assert (export_dir / "logs" / "terminal-s2.log").read_text(
        encoding="utf-8"
    ) == terminal_log.read_text(encoding="utf-8")
    assert (export_dir / "artifacts" / "voice_segments" / "full.wav").read_bytes() == (
        full_voice.read_bytes()
    )
    assert (export_dir / "artifacts" / "voice_segments" / "s1.wav").read_bytes() == (
        scene_voice.read_bytes()
    )
    assert (export_dir / "artifacts" / "voice_segments" / "s2.wav").read_bytes() == (
        scene_voice_2.read_bytes()
    )
    assert (export_dir / "assets" / "audio" / "bgm.wav").read_bytes() == bgm_path.read_bytes()
    assert (export_dir / "assets" / "audio" / "click.wav").read_bytes() == sfx_path.read_bytes()
    assert (
        export_dir / "renders" / "preview" / "douyin" / "mixed_audio.m4a"
    ).read_bytes() == mixed_audio.read_bytes()
    assert len(package.export_manifest["approvals"]) == 3


def test_preview_export_source_map_records_manual_video_recording_status(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    evidence_video = project.path / "assets" / "evidence" / "videos" / "manual-s1.mp4"
    evidence_video.parent.mkdir(parents=True, exist_ok=True)
    evidence_video.write_bytes(b"manual-screen-recording")
    input_assets = [
        {
            "type": "video",
            "source_uri": "assets/evidence/videos/manual-s1.mp4",
            "role": "screen_recording",
            "target_scene_id": "s1",
            "source_video_probe_status": "verifiable",
            "source_video_has_video_stream": True,
            "source_video_probe_tool": "ffprobe",
            "source_video_duration_sec": 3.2,
            "publish_grade_visual_candidate": True,
            "next_action_zh": "重新运行灵剪主线绑定录屏。",
            "next_command": f"uv run lj run {project.path} --release --json",
        }
    ]
    (project.path / "assets" / "input_assets.json").write_text(
        json.dumps(input_assets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    evidence_manifest = collect_evidence_assets(project)
    assert evidence_manifest["assets"][0]["recording_status"] == "captured"

    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 3.2,
            "narration_text": "展示真实录屏",
            "on_screen_text": "真实动态证据",
            "render_source": "video",
            "asset_path": "assets/evidence/videos/manual-s1.mp4",
            "requires_real_evidence_asset": True,
            "expected_real_evidence": ["screen recording"],
            "evidence_asset_refs": [
                {
                    "id": "input-01",
                    "evidence_type": "screen_recording_capture",
                    "target_scene_id": "s1",
                }
            ],
        }
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads(
        (package.export_dir / "source_map.json").read_text(encoding="utf-8")
    )
    evidence_asset = source_map[0]["evidence_assets"][0]
    assert evidence_asset["id"] == "input-01"
    assert evidence_asset["evidence_type"] == "screen_recording_capture"
    assert evidence_asset["target_scene_id"] == "s1"
    assert evidence_asset["recording_status"] == "captured"
    assert evidence_asset["source_video_probe_status"] == "verifiable"
    assert evidence_asset["source_video_probe_tool"] == "ffprobe"
    assert evidence_asset["source_video_has_video_stream"] is True
    assert evidence_asset["source_video_duration_sec"] == 3.2
    assert evidence_asset["evidence_clip_duration_sec"] == 3.2
    assert evidence_asset["publish_grade_visual_candidate"] is True
    assert evidence_asset["path"] == "assets/evidence/videos/manual-s1.mp4"
    assert evidence_asset["source_uri"] == "assets/evidence/videos/manual-s1.mp4"
    assert evidence_asset["target_scene_matches"] is True
    assert evidence_asset["next_command"] == "uv run lj run <project> --release --json"
    assert str(project.path) not in json.dumps(evidence_asset, ensure_ascii=False)


def test_preview_export_source_map_records_hard_concat_transition_diagnostics(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {"scene_id": "s1", "duration_sec": 1.0, "render_source": "video"},
        {"scene_id": "s2", "duration_sec": 1.0, "render_source": "video"},
    ]
    manifest["transition_rendering"] = {
        "rendered": False,
        "mode": "hard_concat",
        "reason": "当前分镜没有可执行 transition_plan,使用 ffmpeg concat 直接拼接。",
        "transition_count": 0,
    }
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["transition_diagnostics"] == {
        "rendered": False,
        "mode": "hard_concat",
        "reason": "当前分镜没有可执行 transition_plan,使用 ffmpeg concat 直接拼接。",
        "transition_count": 0,
    }
    assert source_map[1]["transition_diagnostics"] == source_map[0]["transition_diagnostics"]


def test_preview_export_source_map_marks_transition_semantic_mismatch(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {"scene_id": "s1", "duration_sec": 1.0, "render_source": "video"},
        {
            "scene_id": "s2",
            "duration_sec": 1.0,
            "render_source": "video",
            "transition_plan": {"family": "focus-pull"},
        },
    ]
    manifest["transition_rendering"] = {
        "rendered": True,
        "mode": "ffmpeg_xfade",
        "transition_count": 1,
        "transitions": [
            {
                "from_scene_id": "s1",
                "to_scene_id": "s2",
                "family": "focus-pull",
                "xfade": "fade",
                "offset_sec": 0.7,
                "duration_sec": 0.3,
            }
        ],
    }
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["outgoing_transition"]["semantic_audit"] == {
        "planned_scene_id": "s2",
        "plan_present": True,
        "planned_family": "focus-pull",
        "expected_xfade": "radial",
        "actual_family": "focus-pull",
        "actual_xfade": "fade",
        "semantic_match": False,
        "mismatch_reason": "xfade_mismatch",
    }
    assert source_map[1]["incoming_transition"] == source_map[0]["outgoing_transition"]


def test_preview_export_source_map_redacts_external_bgm_and_sfx_paths(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    mixed_audio_path = project.path / "renders" / "release" / "douyin" / "mixed_audio.m4a"
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
        }
    ]
    manifest["audio_mix"] = {
        "rendered": True,
        "bgm_present": True,
        "bgm_path": "/Users/example/private-bgm.wav",
        "bgm_to_voice_db": -16.0,
        "mixed_audio_path": str(mixed_audio_path),
        "sfx_count": 1,
        "sfx_events": [
            {
                "path": "/Users/example/private-click.wav",
                "scene_id": "s1",
                "at_sec": 0.6,
                "gain_db": -12.0,
                "action": "按钮点击",
                "purpose": "提示画面动作",
            }
        ],
    }
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["bgm_track"]["path"] == "<external-redacted>"
    assert (
        source_map[0]["bgm_track"]["mixed_audio_path"]
        == "renders/release/douyin/mixed_audio.m4a"
    )
    assert source_map[0]["sfx_events"][0]["path"] == "<external-redacted>"
    assert "/Users/" not in json.dumps(source_map, ensure_ascii=False)


def test_preview_export_source_map_marks_evidence_scene_and_type_mismatch(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/other-scenes/s1.mp4",
            "expected_real_evidence": ["终端 QA 录屏"],
            "evidence_asset_refs": [
                {
                    "id": "ev-web-s2",
                    "evidence_type": "web_recording_capture",
                    "target_scene_id": "s2",
                }
            ],
        }
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    evidence_manifest = {
        "version": "v1",
        "assets": [
            {
                "id": "ev-web-s2",
                "path": "assets/evidence/videos/web-s2.mp4",
                "evidence_clip_path": "assets/evidence/videos/web-s2.mp4",
                "evidence_type": "web_recording_capture",
                "evidence_clip_status": "captured",
                "target_scene_id": "s2",
                "source_video_probe_status": "verifiable",
                "source_video_has_video_stream": True,
                "source_video_duration_sec": 0.8,
            }
        ],
    }
    evidence_manifest_path = project.path / "assets" / "evidence" / "evidence_assets.json"
    evidence_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_manifest_path.write_text(
        json.dumps(evidence_manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["evidence_contract"] == {
        "expected_real_evidence": ["终端 QA 录屏"],
        "expected_evidence_type_groups": [
            [
                "qa_report_artifact",
                "render_manifest_capture",
                "terminal_log_capture",
                "terminal_recording_capture",
            ],
            ["qa_report_artifact"],
        ],
    }
    assert source_map[0]["evidence_assets"] == [
        {
            "id": "ev-web-s2",
            "evidence_type": "web_recording_capture",
            "target_scene_id": "s2",
            "evidence_clip_status": "captured",
            "source_video_probe_status": "verifiable",
            "source_video_duration_sec": 0.8,
            "target_scene_matches": False,
            "expected_evidence_type_matches": False,
            "primary_visual_consumed": False,
            "primary_visual_consumption_source": "none",
            "scene_asset_path": "assets/other-scenes/s1.mp4",
            "path": "assets/evidence/videos/web-s2.mp4",
            "evidence_clip_path": "assets/evidence/videos/web-s2.mp4",
            "source_video_has_video_stream": True,
        }
    ]


def test_preview_export_source_map_marks_recording_task_intent_mismatch(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/evidence/videos/product-ui.mp4",
            "expected_real_evidence": ["产品界面", "核心工作流"],
            "asset_recipe_id": "product_interface_capture",
            "asset_strategy_v2": {
                "profile": "product_intro",
                "required_evidence": ["产品界面", "核心工作流"],
            },
            "evidence_asset_refs": [
                {
                    "id": "ev-product",
                    "evidence_type": "product_interface_capture",
                    "target_scene_id": "s1",
                }
            ],
        }
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    evidence_manifest = {
        "version": "v1",
        "assets": [
            {
                "id": "ev-product",
                "path": "assets/evidence/videos/product-ui.mp4",
                "evidence_clip_path": "assets/evidence/videos/product-ui.mp4",
                "evidence_type": "product_interface_capture",
                "evidence_clip_status": "captured",
                "evidence_visual_source": "product_interface_video",
                "target_scene_id": "s1",
                "source_video_probe_status": "verifiable",
                "source_video_has_video_stream": True,
                "recording_task_redacted": "展示无关日历页面滚动",
            }
        ],
    }
    evidence_manifest_path = project.path / "assets" / "evidence" / "evidence_assets.json"
    evidence_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_manifest_path.write_text(
        json.dumps(evidence_manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["evidence_contract"] == {
        "expected_real_evidence": ["产品界面", "核心工作流"],
        "expected_evidence_type_groups": [
            [
                "product_demo_capture",
                "product_interface_capture",
                "product_ui_capture",
                "screen_recording_capture",
            ]
        ],
        "asset_strategy": {
            "profile": "product_intro",
        },
        "recording_intent_marker_groups": [
            ["产品", "商品", "product"],
            ["界面", "ui", "操作", "流程", "工作流", "演示", "demo"],
        ],
    }
    assert source_map[0]["evidence_assets"] == [
        {
            "id": "ev-product",
            "evidence_type": "product_interface_capture",
            "target_scene_id": "s1",
            "evidence_clip_status": "captured",
            "evidence_visual_source": "product_interface_video",
            "source_video_probe_status": "verifiable",
            "recording_task_redacted": "展示无关日历页面滚动",
            "target_scene_matches": True,
            "expected_evidence_type_matches": True,
            "recording_task_intent_matches": False,
            "primary_visual_consumed": True,
            "primary_visual_consumption_source": "asset_path",
            "scene_asset_path": "assets/evidence/videos/product-ui.mp4",
            "path": "assets/evidence/videos/product-ui.mp4",
            "evidence_clip_path": "assets/evidence/videos/product-ui.mp4",
            "source_video_has_video_stream": True,
        }
    ]


def test_preview_export_source_map_marks_host_contract_primary_visual_consumption(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/scenes/generated-s1.mp4",
            "expected_real_evidence": ["产品界面"],
            "host_generation_contract": {
                "evidence_media_count": 1,
                "evidence_media_hero_kind": "video",
                "evidence_media_hero_role": "primary_visual",
                "template_body_suppressed_for_evidence": True,
                "contract_confirmed_by_generator": True,
            },
            "evidence_asset_refs": [
                {
                    "id": "ev-product",
                    "evidence_type": "product_interface_capture",
                    "target_scene_id": "s1",
                }
            ],
        }
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    evidence_manifest_path = project.path / "assets" / "evidence" / "evidence_assets.json"
    evidence_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_manifest_path.write_text(
        json.dumps(
            {
                "version": "v1",
                "assets": [
                    {
                        "id": "ev-product",
                        "path": "assets/evidence/videos/product-ui.mp4",
                        "evidence_clip_path": "assets/evidence/videos/product-ui.mp4",
                        "evidence_type": "product_interface_capture",
                        "evidence_clip_status": "captured",
                        "evidence_visual_source": "product_interface_video",
                        "target_scene_id": "s1",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    evidence_asset = source_map[0]["evidence_assets"][0]
    assert evidence_asset["primary_visual_consumed"] is True
    assert evidence_asset["primary_visual_consumption_source"] == "host_generation_contract"
    assert evidence_asset["scene_asset_path"] == "assets/scenes/generated-s1.mp4"


def test_preview_export_source_map_marks_caption_timing_not_backed_by_voice_plan(
    tmp_path,
):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
            "caption_cues": [
                {
                    "text": "第一句",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "source": "voice_duration_aligned",
                    "timing_basis": "real_segment_duration",
                }
            ],
            "caption_timing": {
                "source": "voice_duration_aligned",
                "timing_basis": "real_segment_duration",
            },
        }
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    voice_plan_path = project.path / "artifacts" / "voice_plan.json"
    voice_plan = json.loads(voice_plan_path.read_text(encoding="utf-8"))
    voice_plan["segments"] = [{"scene_id": "s1", "duration_sec": 2.0}]
    voice_plan_path.write_text(
        json.dumps(voice_plan, ensure_ascii=False),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["caption_audit"] == {
        "timing_source": "voice_duration_aligned",
        "timing_basis": "real_segment_duration",
        "cue_sources": ["voice_duration_aligned"],
        "cue_timing_bases": ["real_segment_duration"],
        "estimated_timing": False,
        "requires_voice_plan": True,
        "required_sources": ["voice_duration_aligned"],
        "voice_plan_segment_found": True,
        "voice_plan_caption_cue_count": 0,
        "voice_plan_backed": False,
    }


def test_preview_export_source_map_marks_estimated_caption_timing_basis(
    tmp_path,
):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
            "caption_cues": [
                {
                    "text": "第一句",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "source": "voice_segment",
                    "timing_basis": "estimated",
                }
            ],
            "caption_timing": {
                "source": "voice_segment",
                "timing_basis": "estimated",
            },
        }
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["caption_audit"] == {
        "timing_source": "voice_segment",
        "timing_basis": "estimated",
        "cue_sources": ["voice_segment"],
        "cue_timing_bases": ["estimated"],
        "estimated_timing": True,
        "requires_voice_plan": True,
        "required_sources": ["voice_segment"],
        "voice_plan_segment_found": False,
        "voice_plan_caption_cue_count": 0,
        "voice_plan_backed": False,
    }


def test_preview_export_source_map_marks_unverifiable_audio_visual_alignment_ref(
    tmp_path,
):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    evidence_video = project.path / "assets" / "evidence" / "videos" / "s2.mp4"
    evidence_video.parent.mkdir(parents=True, exist_ok=True)
    evidence_video.write_bytes(b"MP4")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["visual_evidence_assets"] = {
        "assets": [
            {
                "id": "ev-s2",
                "target_scene_id": "s2",
                "evidence_clip_status": "captured",
                "evidence_clip_path": "assets/evidence/videos/s2.mp4",
                "evidence_type": "screen_recording_capture",
            }
        ]
    }
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/scenes/s1.mp4",
            "audio_visual_alignment": {
                "status": "verified",
                "evidence_refs": [{"id": "ev-s2"}],
            },
        }
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["audio_visual_alignment"] == {
        "source": "scene",
        "status": "verified",
        "evidence_refs": [{"id": "ev-s2"}],
        "has_text_evidence": False,
        "has_evidence": False,
        "evidence_ref_count": 1,
        "evidence_ref_verifiable": False,
        "evidence_issue_code": "RELEASE_AUDIO_VISUAL_ALIGNMENT_REF_NOT_VERIFIABLE",
    }


def test_preview_export_source_map_records_qa_evidence_recovery_metadata(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/scenes/s1.mp4",
        },
        {
            "scene_id": "s2",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/scenes/s2.mp4",
        },
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    recovery_metadata = {
        "remaining_evidence_blockers": [
            {
                "scene_id": "s1",
                "scene_number": 1,
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "expected_evidence_types": [
                    "codex_operation_recording",
                    "screen_recording_capture",
                ],
                "next_action_zh": "请录制第 1 镜 Codex app 触发过程。",
                "first_command": (
                    f"uv run lj ingest codex {project.path} --task '展示触发过程' "
                    "--scene-id s1 --allow-screen-recording --json"
                ),
                "first_command_label_zh": "优先:记录 Codex app 操作录屏任务",
                "screen_recording_consent_required": True,
                "privacy_notice_zh": "请确认当前屏幕没有私密信息。",
                "manual_fallback_command": (
                    f"uv run lj ingest video {project.path} --file '把录屏文件拖到这里.mp4' "
                    "--role codex_recording --scene-id s1 --json"
                ),
                "manual_fallback_note_zh": "不授权自动录屏时,先手动录好 mp4 再导入。",
            }
        ],
        "evidence_collection_checklist_artifact": (
            "artifacts/evidence_collection_checklist.md"
        ),
    }

    def fake_run_qa(*_args, **_kwargs):
        report = QAReport(metadata=recovery_metadata)
        artifacts = project.path / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "qa_report.json").write_text(
            json.dumps(
                {
                    "hard_failures": [],
                    "warnings": [],
                    "info": [],
                    "metadata": report.metadata,
                    "release_ready": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (artifacts / "qa_report.md").write_text(
            (
                "# QA Report\n\n"
                "release_ready: true\n\n"
                "## 真实动态证据素材恢复建议\n\n"
                f"uv run lj ingest video {project.path} --file demo.mp4 "
                "--role codex_recording --scene-id s1 --json\n"
            ),
            encoding="utf-8",
        )
        return report

    monkeypatch.setattr("packages.core.exporting.run_qa", fake_run_qa)

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["qa_evidence_recovery"] == [
        {
            "scene_id": "s1",
            "scene_number": 1,
            "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
            "expected_evidence_types": [
                "codex_operation_recording",
                "screen_recording_capture",
            ],
            "next_action_zh": "请录制第 1 镜 Codex app 触发过程。",
            "first_command": (
                "uv run lj ingest codex <project> --task '展示触发过程' "
                "--scene-id s1 --allow-screen-recording --json"
            ),
            "first_command_label_zh": "优先:记录 Codex app 操作录屏任务",
            "screen_recording_consent_required": True,
            "privacy_notice_zh": "请确认当前屏幕没有私密信息。",
            "manual_fallback_command": (
                "uv run lj ingest video <project> --file '把录屏文件拖到这里.mp4' "
                "--role codex_recording --scene-id s1 --json"
            ),
            "manual_fallback_note_zh": "不授权自动录屏时,先手动录好 mp4 再导入。",
        }
    ]
    assert source_map[1]["qa_evidence_recovery"] == []
    assert "access_token" not in json.dumps(
        source_map[0]["qa_evidence_recovery"], ensure_ascii=False
    )
    assert str(project.path) not in json.dumps(
        source_map[0]["qa_evidence_recovery"], ensure_ascii=False
    )
    assert "真实动态证据素材恢复建议" in (
        package.export_dir / "qa_report.md"
    ).read_text(encoding="utf-8")
    exported_qa_markdown = (package.export_dir / "qa_report.md").read_text(
        encoding="utf-8"
    )
    assert "uv run lj ingest video <project> --file demo.mp4" in exported_qa_markdown
    assert str(project.path) not in exported_qa_markdown
    exported_qa_report = json.loads(
        (package.export_dir / "qa_report.json").read_text(encoding="utf-8")
    )
    assert exported_qa_report["metadata"]["remaining_evidence_blockers"][0][
        "scene_id"
    ] == "s1"
    assert (
        exported_qa_report["metadata"]["remaining_evidence_blockers"][0][
            "manual_fallback_command"
        ]
        == source_map[0]["qa_evidence_recovery"][0]["manual_fallback_command"]
    )
    assert (
        exported_qa_report["metadata"]["remaining_evidence_blockers"][0]["first_command"]
        == source_map[0]["qa_evidence_recovery"][0]["first_command"]
    )
    assert str(project.path) not in json.dumps(exported_qa_report, ensure_ascii=False)


def test_preview_export_source_map_records_stock_image_policy_and_recovery(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    stock_policy = {
        "used": True,
        "requires_user_consent": True,
        "user_consent_status": "pending",
        "not_evidence": True,
        "does_not_satisfy_real_evidence": True,
        "source_priority": ["用户自有图片/截图", "国内 CC0 源", "Unsplash/Pexels"],
        "license_fields_required": [
            "source",
            "sourceUrl",
            "license",
            "license_verification_status",
        ],
        "selected_source": {
            "source": "Pexels",
            "sourceUrl": "https://www.pexels.com/photo/example",
            "license": "Pexels License",
            "license_verification_status": "UNVERIFIED",
        },
        "processing_requirements": ["透明背景处理", "主体/CTA/字幕避让"],
    }
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/scenes/s1.mp4",
            "asset_strategy_v2": {
                "profile": "knowledge_explainer",
                "blueprint_id": "concept_diagram",
                "current_asset_kind": "stock_image",
                "current_asset_status": "reference_only_stock_image",
                "publish_grade_visual": False,
                "next_action_zh": "请转成动态视频并完成授权审计。",
                "stock_image_policy": stock_policy,
            },
        }
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    recovery_metadata = {
        "remaining_stock_image_blockers": [
            {
                "scene_id": "s1",
                "issue_code": "RELEASE_STOCK_IMAGE_LICENSE_NOT_VERIFIABLE",
                "next_action_zh": "补齐图库许可核验后再重新 QA。",
            }
        ]
    }

    def fake_run_qa(*_args, **_kwargs):
        report = QAReport(metadata=recovery_metadata)
        artifacts = project.path / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "qa_report.json").write_text(
            json.dumps(
                {
                    "hard_failures": [],
                    "warnings": [],
                    "info": [],
                    "metadata": report.metadata,
                    "release_ready": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (artifacts / "qa_report.md").write_text("# QA Report\n", encoding="utf-8")
        return report

    monkeypatch.setattr("packages.core.exporting.run_qa", fake_run_qa)

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["stock_image_policy"]["selected_source"] == {
        "source": "Pexels",
        "sourceUrl": "https://www.pexels.com/photo/example",
        "license": "Pexels License",
        "license_verification_status": "UNVERIFIED",
    }
    assert source_map[0]["stock_image_policy"]["not_evidence"] is True
    assert source_map[0]["evidence_contract"]["asset_strategy"]["stock_image_policy"][
        "does_not_satisfy_real_evidence"
    ] is True
    assert source_map[0]["qa_stock_image_recovery"] == [
        {
            "issue_code": "RELEASE_STOCK_IMAGE_LICENSE_NOT_VERIFIABLE",
            "next_action_zh": "补齐图库许可核验后再重新 QA。",
        }
    ]


def test_preview_export_source_map_records_qa_approval_recovery_metadata(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/scenes/s1.mp4",
        },
        {
            "scene_id": "s2",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/scenes/s2.mp4",
        },
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    recovery_metadata = {
        "approval_gate_error_code": "APPROVAL_STALE",
        "approval_gate_message_zh": "三审审批已过期。",
        "approval_gate_hint_zh": "请重新审阅并批准。",
        "stale_approval_targets": ["voice", "visuals"],
        "stale_approval_commands": [
            {
                "target": "voice",
                "artifact": "artifacts/voice_plan.json",
                "approval_command": (
                    f"uv run lj approve voice {project.path} "
                    "--approved-by '你的名字' --json"
                ),
                "command": (
                    f"uv run lj approve voice {project.path} "
                    "--approved-by '你的名字' --json"
                ),
            },
            {
                "target": "visuals",
                "artifact": "artifacts/visual_plan.json",
                "approval_command": (
                    f"uv run lj approve visuals {project.path} "
                    "--approved-by '你的名字' --json"
                ),
                "command": (
                    f"uv run lj approve visuals {project.path} "
                    "--approved-by '你的名字' --json"
                ),
            },
        ],
        "stale_approval_notice_zh": "QA 只提供恢复动作,不能自动批准。",
        "voice_reapproval_required": True,
        "visuals_reapproval_required": True,
        "voice_approval_command": (
            f"uv run lj approve voice {project.path} --approved-by '你的名字' --json"
        ),
        "visuals_approval_command": (
            f"uv run lj approve visuals {project.path} --approved-by '你的名字' --json"
        ),
        "voice_reapproval_message_zh": (
            "voice_plan 已变更,需要重新试听或审阅配音与字幕节奏后再批准 voice。"
        ),
    }

    def fake_run_qa(*_args, **_kwargs):
        report = QAReport(metadata=recovery_metadata)
        artifacts = project.path / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "qa_report.json").write_text(
            json.dumps(
                {
                    "hard_failures": [],
                    "warnings": [],
                    "info": [],
                    "metadata": report.metadata,
                    "release_ready": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (artifacts / "qa_report.md").write_text(
            (
                "# QA Report\n\n"
                "release_ready: true\n\n"
                "## 审批恢复建议\n\n"
                f"- 重审命令: `uv run lj approve voice {project.path} "
                "--approved-by '你的名字' --json`\n"
            ),
            encoding="utf-8",
        )
        return report

    monkeypatch.setattr("packages.core.exporting.run_qa", fake_run_qa)

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    expected_recovery = {
        "approval_gate_error_code": "APPROVAL_STALE",
        "approval_gate_message_zh": "三审审批已过期。",
        "approval_gate_hint_zh": "请重新审阅并批准。",
        "stale_approval_targets": ["voice", "visuals"],
        "stale_approval_notice_zh": "QA 只提供恢复动作,不能自动批准。",
        "voice_reapproval_required": True,
        "visuals_reapproval_required": True,
        "voice_reapproval_message_zh": (
            "voice_plan 已变更,需要重新试听或审阅配音与字幕节奏后再批准 voice。"
        ),
        "voice_approval_command": (
            "uv run lj approve voice <project> --approved-by '你的名字' --json"
        ),
        "visuals_approval_command": (
            "uv run lj approve visuals <project> --approved-by '你的名字' --json"
        ),
        "stale_approval_commands": [
            {
                "target": "voice",
                "artifact": "artifacts/voice_plan.json",
                "approval_command": (
                    "uv run lj approve voice <project> --approved-by '你的名字' --json"
                ),
                "command": (
                    "uv run lj approve voice <project> --approved-by '你的名字' --json"
                ),
            },
            {
                "target": "visuals",
                "artifact": "artifacts/visual_plan.json",
                "approval_command": (
                    "uv run lj approve visuals <project> --approved-by '你的名字' --json"
                ),
                "command": (
                    "uv run lj approve visuals <project> --approved-by '你的名字' --json"
                ),
            },
        ],
    }
    assert source_map[0]["qa_approval_recovery"] == expected_recovery
    assert source_map[1]["qa_approval_recovery"] == expected_recovery
    assert str(project.path) not in json.dumps(
        source_map[0]["qa_approval_recovery"], ensure_ascii=False
    )
    exported_qa_report = json.loads(
        (package.export_dir / "qa_report.json").read_text(encoding="utf-8")
    )
    assert (
        exported_qa_report["metadata"]["stale_approval_commands"][0]["command"]
        == source_map[0]["qa_approval_recovery"]["stale_approval_commands"][0]["command"]
    )
    assert str(project.path) not in json.dumps(exported_qa_report, ensure_ascii=False)


def test_strict_preview_export_includes_release_qa_recovery_without_blocking(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    bgm_recovery_command = (
        f"uv run lj ingest audio {project.path} --file '把BGM文件拖到这里.wav' "
        "--kind bgm --bgm-to-voice-db -16 --json"
    )
    sfx_recovery_command = (
        f"uv run lj ingest audio {project.path} --file '把音效文件拖到这里.wav' "
        "--kind sfx --scene-id s1 --at-sec 0.5 --gain-db -12 "
        "--action '轻微点击音' --json"
    )
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["scenes"] = [
        {
            "scene_id": "s1",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/scenes/s1.mp4",
        },
        {
            "scene_id": "s2",
            "duration_sec": 2.0,
            "render_source": "video",
            "asset_path": "assets/scenes/s2.mp4",
        },
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    recovery_metadata = {
        "approval_gate_error_code": "APPROVAL_STALE",
        "stale_approval_targets": ["voice", "visuals"],
        "stale_approval_commands": [
            {
                "target": "voice",
                "artifact": "artifacts/voice_plan.json",
                "command": (
                    f"uv run lj approve voice {project.path} "
                    "--approved-by '你的名字' --json"
                ),
            }
        ],
        "voice_reapproval_required": True,
        "voice_approval_command": (
            f"uv run lj approve voice {project.path} --approved-by '你的名字' --json"
        ),
        "remaining_evidence_blockers": [
            {
                "scene_id": "s1",
                "scene_number": 1,
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "expected_evidence_types": ["codex_operation_recording"],
                "next_action_zh": "请录制第 1 镜 Codex app 触发过程。",
                "first_command": (
                    f"uv run lj ingest codex {project.path} --task '展示触发过程' "
                    "--scene-id s1 --allow-screen-recording --json"
                ),
                "manual_fallback_command": (
                    f"uv run lj ingest video {project.path} --file '把录屏文件拖到这里.mp4' "
                    "--role codex_recording --scene-id s1 --json"
                ),
            }
        ],
        "remaining_audio_asset_blockers": [
            {
                "kind": "bgm",
                "scene_ids": ["s1", "s2"],
                "scenes": [
                    {
                        "scene_id": "s1",
                        "scene_number": 1,
                        "declared_bgm": "科技感轻节奏 BGM,人声优先。",
                    },
                    {
                        "scene_id": "s2",
                        "scene_number": 2,
                        "declared_bgm": "科技感轻节奏 BGM,人声优先。",
                    },
                ],
                "expected_audio_asset": "voice_plan.audio_assets.bgm.path",
                "accepted_formats": ["wav", "mp3", "m4a", "aac"],
                "first_command_label_zh": "导入 BGM 音频并写入 voice_plan",
                "first_command": bgm_recovery_command,
                "suggested_commands": [
                    {
                        "label_zh": "导入 BGM 音频",
                        "command": bgm_recovery_command,
                        "note_zh": "导入后需要重新审阅并批准 voice,再重跑 render/QA。",
                    }
                ],
                "next_action_zh": "请提供项目内可验证 BGM 音频。",
            },
            {
                "kind": "sfx",
                "scene_id": "s1",
                "scene_number": 1,
                "declared_sfx_markers": ["轻微点击音"],
                "expected_audio_asset": "voice_plan.audio_assets.sfx[]",
                "accepted_formats": ["wav", "mp3", "m4a", "aac"],
                "suggested_at_sec": 0.5,
                "suggested_timing_basis": "default_first_beat",
                "suggested_action": "轻微点击音",
                "first_command_label_zh": "导入本镜 SFX 音效并绑定动作点",
                "first_command": sfx_recovery_command,
                "suggested_commands": [
                    {
                        "label_zh": "导入本镜 SFX 音效",
                        "command": sfx_recovery_command,
                        "note_zh": "如果实际动作点不在该时间,请调整 --at-sec 后再执行。",
                    }
                ],
                "timing_hint_zh": (
                    "未找到同名视觉动作时间点,命令先给 0.5 秒附近的默认动作点;"
                    "请按真实画面动作调整 --at-sec。"
                ),
                "next_action_zh": "请提供第 1 镜同镜 SFX 音频。",
            },
        ],
        "audio_asset_recovery_notice_zh": (
            "BGM/SFX 已进入导演分镜,但还没有可验证音频素材或可信混音证据。"
        ),
    }
    calls = []

    def fake_run_qa(*_args, **kwargs):
        calls.append({"release": kwargs.get("release"), "strict": kwargs.get("strict")})
        report = QAReport(
            hard_failures=[
                QAIssue(
                    "RELEASE_VISUAL_EVIDENCE_BLOCKERS_REMAIN",
                    "hard",
                    "visual_plan 仍有真实动态 evidence 素材缺口。",
                )
            ],
            metadata=recovery_metadata,
        )
        artifacts = project.path / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "qa_report.json").write_text(
            json.dumps(
                {
                    "hard_failures": [
                        {
                            "code": issue.code,
                            "severity": issue.severity,
                            "message_zh": issue.message_zh,
                        }
                        for issue in report.hard_failures
                    ],
                    "warnings": [],
                    "info": [],
                    "metadata": report.metadata,
                    "release_ready": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (artifacts / "qa_report.md").write_text(
            (
                "# QA Report\n\n"
                "release_ready: false\n\n"
                "## 审批恢复建议\n\n"
                f"- 重审命令: `uv run lj approve voice {project.path} "
                "--approved-by '你的名字' --json`\n\n"
                "## 真实动态证据素材恢复建议\n\n"
                f"uv run lj ingest video {project.path} --file demo.mp4 "
                "--role codex_recording --scene-id s1 --json\n"
                "\n## BGM/SFX 声音素材恢复建议\n\n"
                "- 请提供项目内可验证 BGM/SFX 音频。\n"
            ),
            encoding="utf-8",
        )
        return report

    monkeypatch.setattr("packages.core.exporting.run_qa", fake_run_qa)

    package = export_project(
        project,
        "douyin",
        "zh-CN",
        "9:16",
        release=False,
        strict=True,
    )

    assert calls == [{"release": True, "strict": True}]
    assert package.export_manifest["release"] is False
    source_map = json.loads((package.export_dir / "source_map.json").read_text(encoding="utf-8"))
    assert source_map[0]["qa_evidence_recovery"][0]["scene_id"] == "s1"
    assert source_map[0]["qa_evidence_recovery"][0]["first_command"] == (
        "uv run lj ingest codex <project> --task '展示触发过程' "
        "--scene-id s1 --allow-screen-recording --json"
    )
    assert source_map[0]["qa_approval_recovery"]["approval_gate_error_code"] == (
        "APPROVAL_STALE"
    )
    assert source_map[0]["qa_approval_recovery"]["stale_approval_targets"] == [
        "voice",
        "visuals",
    ]
    assert source_map[0]["qa_approval_recovery"]["voice_approval_command"] == (
        "uv run lj approve voice <project> --approved-by '你的名字' --json"
    )
    redacted_bgm_recovery_command = bgm_recovery_command.replace(
        str(project.path), "<project>"
    )
    redacted_sfx_recovery_command = sfx_recovery_command.replace(
        str(project.path), "<project>"
    )
    assert source_map[0]["qa_audio_recovery"] == [
        {
            "kind": "bgm",
            "scene_ids": ["s1", "s2"],
            "expected_audio_asset": "voice_plan.audio_assets.bgm.path",
            "accepted_formats": ["wav", "mp3", "m4a", "aac"],
            "next_action_zh": "请提供项目内可验证 BGM 音频。",
            "first_command": redacted_bgm_recovery_command,
            "first_command_label_zh": "导入 BGM 音频并写入 voice_plan",
            "suggested_commands": [
                {
                    "label_zh": "导入 BGM 音频",
                    "command": redacted_bgm_recovery_command,
                    "note_zh": "导入后需要重新审阅并批准 voice,再重跑 render/QA。",
                }
            ],
            "scenes": [
                {
                    "scene_id": "s1",
                    "scene_number": 1,
                    "declared_bgm": "科技感轻节奏 BGM,人声优先。",
                },
                {
                    "scene_id": "s2",
                    "scene_number": 2,
                    "declared_bgm": "科技感轻节奏 BGM,人声优先。",
                },
            ],
        },
        {
            "kind": "sfx",
            "scene_ids": ["s1"],
            "scene_number": 1,
            "declared_sfx_markers": ["轻微点击音"],
            "expected_audio_asset": "voice_plan.audio_assets.sfx[]",
            "accepted_formats": ["wav", "mp3", "m4a", "aac"],
            "next_action_zh": "请提供第 1 镜同镜 SFX 音频。",
            "first_command": redacted_sfx_recovery_command,
            "first_command_label_zh": "导入本镜 SFX 音效并绑定动作点",
            "suggested_at_sec": 0.5,
            "suggested_timing_basis": "default_first_beat",
            "suggested_action": "轻微点击音",
            "timing_hint_zh": (
                "未找到同名视觉动作时间点,命令先给 0.5 秒附近的默认动作点;"
                "请按真实画面动作调整 --at-sec。"
            ),
            "suggested_commands": [
                {
                    "label_zh": "导入本镜 SFX 音效",
                    "command": redacted_sfx_recovery_command,
                    "note_zh": "如果实际动作点不在该时间,请调整 --at-sec 后再执行。",
                }
            ],
        },
    ]
    assert source_map[1]["qa_evidence_recovery"] == []
    assert source_map[1]["qa_audio_recovery"] == [
        {
            "kind": "bgm",
            "scene_ids": ["s1", "s2"],
            "expected_audio_asset": "voice_plan.audio_assets.bgm.path",
            "accepted_formats": ["wav", "mp3", "m4a", "aac"],
            "next_action_zh": "请提供项目内可验证 BGM 音频。",
            "first_command": redacted_bgm_recovery_command,
            "first_command_label_zh": "导入 BGM 音频并写入 voice_plan",
            "suggested_commands": [
                {
                    "label_zh": "导入 BGM 音频",
                    "command": redacted_bgm_recovery_command,
                    "note_zh": "导入后需要重新审阅并批准 voice,再重跑 render/QA。",
                }
            ],
            "scenes": [
                {
                    "scene_id": "s1",
                    "scene_number": 1,
                    "declared_bgm": "科技感轻节奏 BGM,人声优先。",
                },
                {
                    "scene_id": "s2",
                    "scene_number": 2,
                    "declared_bgm": "科技感轻节奏 BGM,人声优先。",
                },
            ],
        }
    ]
    assert source_map[1]["qa_approval_recovery"] == source_map[0]["qa_approval_recovery"]
    exported_qa_report = json.loads(
        (package.export_dir / "qa_report.json").read_text(encoding="utf-8")
    )
    assert exported_qa_report["release_ready"] is False
    assert exported_qa_report["metadata"]["stale_approval_targets"] == ["voice", "visuals"]
    assert (
        exported_qa_report["metadata"]["remaining_evidence_blockers"][0]["first_command"]
        == source_map[0]["qa_evidence_recovery"][0]["first_command"]
    )
    assert (
        exported_qa_report["metadata"]["remaining_audio_asset_blockers"][0][
            "first_command"
        ]
        == source_map[0]["qa_audio_recovery"][0]["first_command"]
    )
    exported_qa_markdown = (package.export_dir / "qa_report.md").read_text(
        encoding="utf-8"
    )
    assert "release_ready: false" in exported_qa_markdown
    assert "BGM/SFX 声音素材恢复建议" in exported_qa_markdown
    assert str(project.path) not in json.dumps(source_map, ensure_ascii=False)
    assert str(project.path) not in json.dumps(exported_qa_report, ensure_ascii=False)
    assert str(project.path) not in exported_qa_markdown


def test_export_license_manifest_records_cli_provider(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["providers"] = [
        {"id": "llm_cli", "kind": "llm", "is_mock": False},
        {"id": "tts_cli", "kind": "tts", "is_mock": False},
        {"id": "ffmpeg_card", "kind": "renderer", "is_mock": False},
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    license_text = (package.export_dir / "license_manifest.md").read_text(encoding="utf-8")
    assert "llm_cli: User supplied CLI provider" in license_text
    assert "tts_cli: User supplied CLI provider" in license_text


def test_export_license_manifest_records_openai_provider_without_secrets(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["providers"] = [
        {"id": "openai_compatible", "kind": "llm", "is_mock": False},
        {"id": "openai_compatible_tts", "kind": "tts", "is_mock": False},
        {"id": "ffmpeg_card", "kind": "renderer", "is_mock": False},
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    license_text = (package.export_dir / "license_manifest.md").read_text(encoding="utf-8")
    assert "openai_compatible: OpenAI-compatible API provider" in license_text
    assert "openai_compatible_tts: OpenAI-compatible API provider" in license_text
    assert "sk-" not in license_text
    assert "OPENAI_API_KEY" not in license_text


def test_export_license_manifest_records_volcengine_tts_without_secrets(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["providers"] = [
        {"id": "claude_cli", "kind": "llm", "is_mock": False},
        {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
        {"id": "delegated_scene_assembly", "kind": "renderer", "is_mock": False},
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    license_text = (package.export_dir / "license_manifest.md").read_text(encoding="utf-8")
    assert "volcengine_tts: Volcengine Doubao TTS API provider" in license_text
    assert "VOLCENGINE_TTS_ACCESS_TOKEN" not in license_text
    assert "token" not in license_text.lower()


def test_export_license_manifest_records_inherited_cli_provider_without_commands(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    manifest = json.loads(render_result.manifest_path.read_text(encoding="utf-8"))
    manifest["providers"] = [
        {"id": "claude_cli", "kind": "llm", "is_mock": False},
        {"id": "macos_say", "kind": "tts", "is_mock": False},
        {"id": "ffmpeg_card", "kind": "renderer", "is_mock": False},
    ]
    render_result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = export_project(project, "douyin", "zh-CN", "9:16", release=False)

    license_text = (package.export_dir / "license_manifest.md").read_text(encoding="utf-8")
    assert "claude_cli: Inherited CLI provider" in license_text
    assert "macos_say: Local TTS provider" in license_text
    assert "claude -p" not in license_text
    assert "say -o" not in license_text


def test_youtube_export_writes_platform_extra_files(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_project(project, "youtube", "en-US", "16:9", mode="preview")
    package = export_project(project, "youtube", "en-US", "16:9", release=False)

    export_dir = package.export_dir
    assert (export_dir / "thumbnail.png").exists()
    assert (export_dir / "description.md").exists()
    assert (export_dir / "chapters.md").exists()


def test_qa_marks_mock_release_as_hard_failure(tmp_path):
    project = _approved_mock_project(tmp_path)
    render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    report = run_qa(project, release=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_CONTAINS_MOCK" for issue in report.hard_failures)


def test_rejects_unsafe_platform_path_segment(tmp_path):
    project = _approved_mock_project(tmp_path)

    try:
        render_project(project, "../escape", "zh-CN", "9:16", mode="preview")
    except LingjianError as exc:
        assert exc.error_code == "INVALID_PATH_SEGMENT"
    else:
        raise AssertionError("expected INVALID_PATH_SEGMENT")


def test_release_qa_checks_release_manifest_not_preview_manifest(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    render_project(project, "douyin", "zh-CN", "9:16", mode="preview")
    write_artifact(
        project,
        "script",
        {"id": "script", "provider_id": "real_llm", "provider_is_mock": False, "scenes": []},
    )
    write_artifact(
        project,
        "voice",
        {"id": "voice", "provider_id": "real_tts", "provider_is_mock": False, "segments": []},
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"real-ish video bytes")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false},
    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: None)

    report = run_qa(project, release=True)

    assert report.release_ready is False
    assert any(issue.code == "RENDER_NOT_VERIFIABLE" for issue in report.hard_failures)


def test_release_render_requires_ffmpeg_before_writing_stub(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "script",
        {"id": "script", "provider_id": "real_llm", "provider_is_mock": False, "scenes": []},
    )
    write_artifact(
        project,
        "voice",
        {"id": "voice", "provider_id": "real_tts", "provider_is_mock": False, "segments": []},
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr("packages.core.rendering.shutil.which", lambda name: None)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release")
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_RENDER_REQUIRES_FFMPEG"
    else:
        raise AssertionError("expected RELEASE_RENDER_REQUIRES_FFMPEG")

    assert not (project.path / "renders" / "release" / "douyin" / "video.mp4").exists()


def test_release_render_uses_ffmpeg_and_writes_non_stub_video(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "真实发布字幕"}],
        },
    )
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.aiff",
                    "duration_sec": 2.0,
                }
            ],
            "total_duration_sec": 2.0,
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        commands.append(command)
        Path(command[-1]).write_bytes(b"REAL MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    assert result.video_path.read_bytes() == b"REAL MP4"
    assert result.video_path.read_bytes() != STUB_VIDEO_BYTES
    assert commands
    command_text = "\n".join(" ".join(command) for command in commands)
    video_commands = [command for command in commands if "-vf" in command]
    assert video_commands
    assert video_commands[0][0] == "ffmpeg"
    assert "真实发布字幕" in " ".join(video_commands[0])
    assert "h*0.87-text_h/2" in " ".join(video_commands[0])
    assert "(h/2)" not in " ".join(video_commands[0])
    assert RELEASE_LOUDNORM_FILTER in command_text
    assert "-c:a" in commands[-1]
    assert "aac" in commands[-1]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["expected_duration_sec"] == 2.0
    assert manifest["audio_mix"]["bgm_present"] is False
    assert manifest["audio_mix"]["voice_provider_id"] == "real_tts"
    assert manifest["audio_mix"]["audio_normalization"]["rendered"] is True


def test_release_render_consumes_delegated_video_and_image_scene_assets(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    assets_dir = project.path / "assets" / "scenes"
    assets_dir.mkdir(parents=True)
    (assets_dir / "s1.mp4").write_bytes(b"HOST VIDEO")
    (assets_dir / "s2.png").write_bytes(b"HOST IMAGE")
    audio_path = project.path / "artifacts" / "voice_segments" / "voice.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "动态图形"},
                {"id": "s2", "narration_text": "静态图片"},
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 2.0,
                },
                {
                    "scene_id": "s2",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 3.0,
                },
            ],
            "total_duration_sec": 5.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "动态图形",
                    "duration_sec": 2.0,
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s1.mp4",
                    "subtitle_burn": False,
                    "audio_visual_alignment": {
                        "status": "verified",
                        "notes": "口播讲 QA 报告,画面展示 ffprobe 终端证据和 QA 报告墙。",
                        "verified_by": "tester",
                        "evidence_refs": [
                            {
                                "id": "ev-qa",
                                "evidence_type": "terminal_recording",
                                "target_scene_id": "s1",
                            }
                        ],
                    },
                    "director_review_sheet_v2": {
                        "visual_content": "ffprobe 终端证据和 QA 报告墙。",
                        "audio_sfx_notes": {
                            "bgm": "克制科技感 BGM,人声优先。",
                            "sfx_points": [
                                {"cue_id": "qa-pass", "action": "QA 通过提示音"}
                            ],
                        },
                        "keyframes": [
                            {"time_sec": 0.0, "state": "终端窗口入场。"},
                            {"time_sec": 1.0, "state": "ffprobe 视频流证据高亮。"},
                            {"time_sec": 1.8, "state": "QA 通过状态收束。"},
                        ],
                    },
                    "host_generation_contract": {
                        "adapter": "lingjian_hyperframes_director",
                        "blueprint_id": "proof_ffprobe_dashboard",
                        "asset_recipe_id": "ffprobe_terminal_capture",
                    },
                },
                {
                    "scene_id": "s2",
                    "narration_text": "静态图片",
                    "duration_sec": 3.0,
                    "generator": "image-gen",
                    "asset_path": "assets/scenes/s2.png",
                    "subtitle_burn": True,
                    "director_review_sheet_v2": {
                        "audio_sfx_notes": {
                            "bgm": "无 BGM",
                            "sfx_points": ["可无音效,避免抢口播。"],
                        }
                    },
                },
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        commands.append(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    command_text = "\n".join(" ".join(command) for command in commands)
    assert "assets/scenes/s1.mp4" in command_text
    assert "assets/scenes/s2.png" in command_text
    assert "split=2[ljbg][ljfg]" in command_text
    assert "gblur=sigma=18" in command_text
    assert "overlay=(W-w)/2" in command_text
    assert "zoompan" in command_text
    assert "concat" in command_text
    assert "-c:a" in commands[-1]
    assert "-shortest" not in commands[-1]
    assert "-stream_loop" in commands[-1]
    assert "-1" in commands[-1]
    assert "-t" in commands[-1]
    assert "5.000" in commands[-1]
    assert manifest["visual_real_count"] == 1
    assert manifest["visual_total"] == 2
    visual_plan = json.loads(
        (project.path / "artifacts" / "visual_plan.json").read_text(encoding="utf-8")
    )
    assert manifest["visual_plan_sha256"] == canonical_json_hash(visual_plan)
    assert manifest["video_duration_policy"]["mode"] == "loop_video_to_voice_duration"
    assert manifest["video_duration_policy"]["expected_duration_sec"] == 5.0
    assert manifest["audio_mix"]["declared_audio_requirements"] == {
        "bgm_required": True,
        "bgm_scene_ids": ["s1"],
        "bgm_texts_by_scene": [
            {"scene_id": "s1", "texts": ["克制科技感 BGM,人声优先。"]}
        ],
        "sfx_required": True,
        "sfx_scene_ids": ["s1"],
        "sfx_markers_by_scene": [
            {"scene_id": "s1", "markers": ["qa 通过提示音", "qa-pass"]}
        ],
    }
    assert [scene["render_source"] for scene in manifest["scenes"]] == ["video", "image"]
    assert manifest["scenes"][0]["host_generation_contract"]["blueprint_id"] == (
        "proof_ffprobe_dashboard"
    )
    assert manifest["scenes"][0]["audio_visual_alignment"] == {
        "status": "verified",
        "notes": "口播讲 QA 报告,画面展示 ffprobe 终端证据和 QA 报告墙。",
        "verified_by": "tester",
        "evidence_refs": [
            {
                "id": "ev-qa",
                "evidence_type": "terminal_recording",
                "target_scene_id": "s1",
            }
        ],
    }
    assert manifest["scenes"][0]["director_review_sheet_v2"]["visual_content"] == (
        "ffprobe 终端证据和 QA 报告墙。"
    )
    assert manifest["scenes"][0]["keyframes"] == [
        {"time_sec": 0.0, "state": "终端窗口入场。"},
        {"time_sec": 1.0, "state": "ffprobe 视频流证据高亮。"},
        {"time_sec": 1.8, "state": "QA 通过状态收束。"},
    ]
    assert manifest["scenes"][1]["caption_cues"]
    assert all(
        "start_sec" in cue and "end_sec" in cue
        for cue in manifest["scenes"][1]["caption_cues"]
    )
    assert manifest["transition_rendering"]["rendered"] is False


def test_release_render_blocks_known_non_publish_grade_visual_diagnosis(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "需要真实录屏"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [{"scene_id": "s1", "duration_sec": 2.0}],
            "total_duration_sec": 2.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "需要真实录屏",
                    "duration_sec": 2.0,
                    "generator": "hyperframes",
                    "asset_diagnosis": {
                        "publish_grade_visual": False,
                        "asset_status": "blocked_missing_matching_evidence_video",
                        "next_action_zh": "请补第 1 镜 Codex app 触发录屏。",
                    },
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release")
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_VISUAL_ASSET_NOT_PUBLISH_GRADE"
        assert exc.details["scenes"] == [
            {
                "scene_id": "s1",
                "asset_status": "blocked_missing_matching_evidence_video",
                "next_action_zh": "请补第 1 镜 Codex app 触发录屏。",
            }
        ]
    else:
        raise AssertionError("expected RELEASE_VISUAL_ASSET_NOT_PUBLISH_GRADE")


def test_release_qa_report_includes_evidence_recovery_metadata(tmp_path):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "visuals",
        {
            "id": "visuals",
            "evidence_collection_checklist_v1": {
                "items": [
                    {
                        "scene_id": "s1",
                        "scene_number": 1,
                        "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                        "expected_evidence_types": [
                            "codex_operation_recording",
                            "screen_recording_capture",
                        ],
                        "next_action_zh": "请录制第 1 镜 Codex app 触发过程。",
                        "screen_recording_consent_required": True,
                        "privacy_notice_zh": "请确认当前屏幕没有私密信息。",
                        "manual_fallback_command": (
                            "uv run lj ingest video /tmp/project --file '把录屏文件拖到这里.mp4' "
                            "--role codex_recording --scene-id s1 --json"
                        ),
                        "suggested_commands": [
                            {
                                "label_zh": "优先:记录 Codex app 操作录屏任务",
                                "command": (
                                    "uv run lj ingest codex /tmp/project --task '展示触发过程' "
                                    "--scene-id s1 --allow-screen-recording --json"
                                ),
                            }
                        ],
                    }
                ]
            },
        },
    )
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )

    report = run_qa(project, release=True)

    blockers = report.metadata["remaining_evidence_blockers"]
    assert blockers[0]["scene_id"] == "s1"
    assert blockers[0]["screen_recording_consent_required"] is True
    assert "--scene-id s1" in blockers[0]["manual_fallback_command"]
    qa_report = json.loads((project.path / "artifacts" / "qa_report.json").read_text())
    assert qa_report["metadata"]["remaining_evidence_blockers"][0]["scene_id"] == "s1"
    qa_markdown = (project.path / "artifacts" / "qa_report.md").read_text(encoding="utf-8")
    assert "真实动态证据素材恢复建议" in qa_markdown
    assert "录屏前必须确认当前屏幕没有私密信息" in qa_markdown
    assert "--scene-id s1 --allow-screen-recording --json" in qa_markdown
    assert "--role codex_recording --scene-id s1 --json" in qa_markdown

    strict_report = run_qa(project, release=True, strict=True)
    strict_codes = {issue.code for issue in strict_report.hard_failures}
    assert "RELEASE_VISUAL_EVIDENCE_BLOCKERS_REMAIN" in strict_codes
    assert "RELEASE_RENDER_MANIFEST_STALE" in strict_codes
    strict_qa_report = json.loads(
        (project.path / "artifacts" / "qa_report.json").read_text(encoding="utf-8")
    )
    assert strict_qa_report["metadata"]["remaining_evidence_blockers"][0]["scene_id"] == "s1"


def test_release_qa_report_derives_evidence_manual_fallback_from_suggested_commands(
    tmp_path,
):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "visuals",
        {
            "id": "visuals",
            "evidence_collection_checklist_v1": {
                "items": [
                    {
                        "scene_id": "s4",
                        "scene_number": 4,
                        "asset_recipe_id": "qa_report_capture",
                        "expected_evidence_types": [
                            "terminal_recording_capture",
                            "screen_recording_capture",
                        ],
                        "next_action_zh": "请录制终端运行 QA/strict 检查过程。",
                        "suggested_commands": [
                            {
                                "label_zh": "优先:录制终端命令证据",
                                "command": (
                                    "uv run lj ingest command /tmp/project "
                                    "--command 'uv run lj qa /tmp/project "
                                    "--release --strict --json' "
                                    "--role terminal_recording --record --scene-id s4 --json"
                                ),
                            },
                            {
                                "label_zh": "兜底:把你手动录好的视频绑定到这一镜",
                                "command": (
                                    "uv run lj ingest video /tmp/project "
                                    "--file '把录屏文件拖到这里.mp4' "
                                    "--role terminal_recording --scene-id s4 "
                                    "--task '录制终端运行 QA/strict 检查过程。' --json"
                                ),
                                "note_zh": "手动录屏后绑定到本镜。",
                            },
                        ],
                    }
                ]
            },
        },
    )
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )

    report = run_qa(project, release=True)

    blocker = report.metadata["remaining_evidence_blockers"][0]
    assert blocker["scene_id"] == "s4"
    assert "--scene-id s4" in blocker["manual_fallback_command"]
    assert "--task" in blocker["manual_fallback_command"]
    assert blocker["manual_fallback_note_zh"] == "手动录屏后绑定到本镜。"
    qa_markdown = (project.path / "artifacts" / "qa_report.md").read_text(
        encoding="utf-8"
    )
    assert "手动导入" in qa_markdown
    assert "--role terminal_recording --scene-id s4" in qa_markdown


def test_release_qa_report_includes_stale_approval_recovery_metadata(tmp_path):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "duration_sec": 2.0,
                    "caption_cues": [
                        {
                            "text": "审批后新增字幕",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "source": "voice_duration_aligned",
                        }
                    ],
                }
            ],
        },
    )
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_APPROVALS_STALE" in codes
    assert report.metadata["approval_gate_error_code"] == "APPROVAL_STALE"
    assert report.metadata["stale_approval_targets"] == ["voice"]
    command = report.metadata["stale_approval_commands"][0]["command"]
    assert command.startswith("uv run lj approve voice ")
    assert "--approved-by '你的名字'" in command
    assert report.metadata["voice_reapproval_required"] is True
    qa_report = json.loads((project.path / "artifacts" / "qa_report.json").read_text())
    assert qa_report["metadata"]["stale_approval_targets"] == ["voice"]
    qa_markdown = (project.path / "artifacts" / "qa_report.md").read_text(
        encoding="utf-8"
    )
    assert "审批恢复建议" in qa_markdown
    assert "artifacts/voice_plan.json" in qa_markdown
    assert "uv run lj approve voice" in qa_markdown


def test_strict_release_qa_reports_voice_plan_caption_gap_when_manifest_stale(tmp_path):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 2.0,
                }
            ],
            "total_duration_sec": 2.0,
        },
    )
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_RENDER_MANIFEST_STALE" in codes
    assert "RELEASE_VOICE_PLAN_CAPTION_CUES_MISSING" in codes
    qa_report = json.loads((project.path / "artifacts" / "qa_report.json").read_text())
    assert any(
        issue["code"] == "RELEASE_VOICE_PLAN_CAPTION_CUES_MISSING"
        for issue in qa_report["hard_failures"]
    )


def test_release_render_uses_xfade_when_transition_plan_exists(tmp_path, monkeypatch):
    project = init_project(tmp_path / "p1", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    (video_dir / "s2.mp4").write_bytes(b"VIDEO2")
    audio_path = project.path / "artifacts" / "voice_segments" / "voice.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "第一镜"},
                {"id": "s2", "narration_text": "第二镜"},
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 2.0,
                },
                {
                    "scene_id": "s2",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 2.0,
                },
            ],
            "total_duration_sec": 4.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "第一镜",
                    "duration_sec": 2.0,
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s1.mp4",
                    "transition_plan": {"family": "ticker-crash"},
                    "subtitle_burn": False,
                },
                {
                    "scene_id": "s2",
                    "narration_text": "第二镜",
                    "duration_sec": 2.0,
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s2.mp4",
                    "transition_plan": {"family": "focus-pull"},
                    "subtitle_burn": False,
                },
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        commands.append(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    command_text = "\n".join(" ".join(command) for command in commands)
    assert "-stream_loop -1" in command_text
    assert "xfade=transition=" in command_text
    assert "xfade=transition=radial" in command_text
    assert "fps=30,settb=AVTB,setpts=PTS-STARTPTS" in command_text
    assert "filter_complex" in command_text
    assert manifest["transition_rendering"]["rendered"] is True
    assert manifest["transition_rendering"]["mode"] == "ffmpeg_xfade"
    assert manifest["transition_rendering"]["transition_count"] == 1
    assert manifest["transition_rendering"]["transitions"][0]["family"] == "focus-pull"
    assert manifest["transition_rendering"]["transitions"][0]["xfade"] == "radial"


def test_release_render_trims_caption_cues_away_from_xfade_windows(tmp_path, monkeypatch):
    project = init_project(tmp_path / "p1", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    (video_dir / "s2.mp4").write_bytes(b"VIDEO2")
    audio_path = project.path / "artifacts" / "voice_segments" / "voice.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "第一镜"},
                {"id": "s2", "narration_text": "第二镜"},
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 4.0,
                    "caption_cues": [
                        {
                            "start_sec": 3.2,
                            "end_sec": 3.95,
                            "text": "第一镜收束",
                            "source": "voice_duration_aligned",
                            "timing_basis": "real_segment_duration",
                        }
                    ],
                },
                {
                    "scene_id": "s2",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 4.0,
                    "caption_cues": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 0.8,
                            "text": "第二镜开场",
                            "source": "voice_duration_aligned",
                            "timing_basis": "real_segment_duration",
                        }
                    ],
                },
            ],
            "total_duration_sec": 8.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "第一镜",
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s1.mp4",
                    "transition_plan": {"family": "ticker-crash"},
                    "subtitle_burn": True,
                },
                {
                    "scene_id": "s2",
                    "narration_text": "第二镜",
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s2.mp4",
                    "transition_plan": {"family": "focus-pull"},
                    "subtitle_burn": True,
                },
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            if "format=duration" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps({"format": {"duration": "4.0"}}),
                    stderr="",
                )
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    transition = manifest["transition_rendering"]["transitions"][0]
    assert transition["duration_sec"] == 0.35
    first_scene = manifest["scenes"][0]
    second_scene = manifest["scenes"][1]
    assert first_scene["caption_cues"][0]["end_sec"] <= 3.62
    assert first_scene["caption_cues"][0]["transition_safe_window"] == {
        "applied": True,
        "original_start_sec": 3.2,
        "original_end_sec": 3.95,
        "trim_start_sec": 0.0,
        "trim_end_sec": 0.35,
        "guard_sec": 0.03,
    }
    assert second_scene["caption_cues"][0]["start_sec"] >= 0.38
    assert second_scene["caption_cues"][0]["transition_safe_window"] == {
        "applied": True,
        "original_start_sec": 0.0,
        "original_end_sec": 0.8,
        "trim_start_sec": 0.35,
        "trim_end_sec": 0.0,
        "guard_sec": 0.03,
    }
    assert first_scene["caption_timing"]["transition_safe_window"]["adjusted_cue_count"] == 1
    assert second_scene["caption_timing"]["transition_safe_window"]["adjusted_cue_count"] == 1


def test_release_render_xfade_offset_uses_rendered_clip_duration(tmp_path, monkeypatch):
    project = init_project(tmp_path / "p1", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    (video_dir / "s2.mp4").write_bytes(b"VIDEO2")
    audio_path = project.path / "artifacts" / "voice_segments" / "voice.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "第一镜"},
                {"id": "s2", "narration_text": "第二镜"},
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 4.0,
                },
                {
                    "scene_id": "s2",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 4.0,
                },
            ],
            "total_duration_sec": 8.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "第一镜",
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s1.mp4",
                    "transition_plan": {"family": "ticker-crash"},
                    "subtitle_burn": False,
                },
                {
                    "scene_id": "s2",
                    "narration_text": "第二镜",
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s2.mp4",
                    "transition_plan": {"family": "focus-pull"},
                    "subtitle_burn": False,
                },
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            if "format=duration" in command:
                durations = {"scene_001.mp4": 2.0, "scene_002.mp4": 4.0}
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps(
                        {"format": {"duration": str(durations.get(Path(command[-1]).name, 8.0))}}
                    ),
                    stderr="",
                )
            return _fake_ffprobe_audio(command)
        commands.append(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    command_text = "\n".join(" ".join(command) for command in commands)
    assert "fps=30,settb=AVTB,setpts=PTS-STARTPTS" in command_text
    assert "offset=1.650" in command_text
    assert "offset=3.650" not in command_text
    assert manifest["scenes"][0]["duration_sec"] == 4.0
    assert manifest["scenes"][0]["rendered_duration_sec"] == 2.0
    assert manifest["transition_rendering"]["transitions"][0]["offset_sec"] == 1.65


def test_semantic_transition_families_map_to_deterministic_xfade():
    assert _xfade_name("clean-wipe", 1) == "wipeleft"
    assert _xfade_name("scan-focus", 2) == "smoothup"
    assert _xfade_name("terminal_scan", 3) == "wipeup"
    assert _xfade_name("cta morph", 4) == "circleclose"
    assert _xfade_name("zoom-through", 5) == "distance"
    assert _xfade_name("grid-dissolve", 6) == "dissolve"
    assert _xfade_name("glitch-pressure", 7) == "pixelize"


def test_release_render_prefers_voice_segment_duration_for_captions(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "p1", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {
                    "id": "s1",
                    "narration_text": "灵剪把脚本配音画面审查导出串起来",
                }
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 2.0,
                }
            ],
            "total_duration_sec": 2.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "灵剪把脚本配音画面审查导出串起来",
                    "duration_sec": 8.0,
                    "generator": "user-asset",
                    "asset_path": "assets/scenes/s1.mp4",
                    "subtitle_burn": True,
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        commands.append(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    command_text = "\n".join(" ".join(command) for command in commands)
    assert "-t 2.00" in command_text
    assert manifest["scenes"][0]["duration_sec"] == 2.0
    assert manifest["scenes"][0]["render_width"] == 1080
    assert manifest["scenes"][0]["render_height"] == 1920
    assert manifest["scenes"][0]["caption_render_region"] == {
        "x": 119,
        "y": 1570,
        "w": 842,
        "h": 192,
        "canvas_width": 1080,
        "canvas_height": 1920,
        "unit": "px",
    }
    assert manifest["scenes"][0]["caption_cues"]
    assert manifest["scenes"][0]["caption_cues"][0]["caption_bbox"] == (
        manifest["scenes"][0]["caption_render_region"]
    )
    assert manifest["scenes"][0]["caption_cues"][0]["caption_safe_area"] == {
        "x": 0,
        "y": 1382,
        "w": 1080,
        "h": 384,
        "canvas_width": 1080,
        "canvas_height": 1920,
        "unit": "px",
    }
    assert manifest["scenes"][0]["caption_cues"][-1]["end_sec"] == 2.0


def test_release_render_caps_single_caption_cue_duration(tmp_path, monkeypatch):
    project = init_project(tmp_path / "p1", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "灵剪开源"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 8.0,
                }
            ],
            "total_duration_sec": 8.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "灵剪开源",
                    "duration_sec": 8.0,
                    "generator": "user-asset",
                    "asset_path": "assets/scenes/s1.mp4",
                    "subtitle_burn": True,
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    cue = manifest["scenes"][0]["caption_cues"][0]
    assert cue["start_sec"] == 0.0
    assert cue["end_sec"] == 1.8
    assert cue["source"] == "estimated"
    assert cue["lines"] == ["灵剪开源"]
    assert manifest["scenes"][0]["caption_timing"]["source"] == "estimated"
    assert manifest["scenes"][0]["caption_timing"]["max_cue_sec"] == 2.2
    assert manifest["scenes"][0]["caption_timing"]["estimated_max_cue_sec"] == 1.8
    assert manifest["scenes"][0]["caption_timing"]["release_ready"] is False
    assert manifest["scenes"][0]["caption_timing"]["release_gate"] == (
        "strict_caption_timing"
    )
    assert manifest["scenes"][0]["caption_timing"]["release_blocker_code"] == (
        "RELEASE_CAPTION_TIMING_IS_ESTIMATED"
    )
    assert manifest["scenes"][0]["caption_timing"]["recovery_target_field"] == (
        "artifacts/voice_plan.json segments[].caption_cues"
    )


def test_release_strict_render_blocks_estimated_caption_timing(tmp_path, monkeypatch):
    project = init_project(tmp_path / "strict-caption-estimated", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "灵剪开源"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 8.0,
                }
            ],
            "total_duration_sec": 8.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "灵剪开源",
                    "duration_sec": 8.0,
                    "generator": "user-asset",
                    "asset_path": "assets/scenes/s1.mp4",
                    "subtitle_burn": True,
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_CAPTION_TIMING_NOT_READY"
        assert exc.details["render_manifest"] == "renders/release/douyin/render_manifest.json"
        assert exc.details["blockers"][0]["scene_id"] == "s1"
        assert exc.details["blockers"][0]["release_blocker_code"] == (
            "RELEASE_CAPTION_TIMING_IS_ESTIMATED"
        )
        assert exc.details["blockers"][0]["recovery_target_field"] == (
            "artifacts/voice_plan.json segments[].caption_cues"
        )
    else:
        raise AssertionError("expected RELEASE_CAPTION_TIMING_NOT_READY")

    manifest_path = project.path / "renders" / "release" / "douyin" / "render_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenes"][0]["caption_timing"]["release_ready"] is False
    assert manifest["scenes"][0]["caption_timing"]["release_blocker_code"] == (
        "RELEASE_CAPTION_TIMING_IS_ESTIMATED"
    )


def test_release_render_splits_estimated_captions_into_shorter_cues(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "p1", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    narration = "灵剪把脚本配音画面审查导出串起来，让普通用户也能按步骤做短视频。"
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": narration}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 6.0,
                }
            ],
            "total_duration_sec": 6.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": narration,
                    "duration_sec": 6.0,
                    "generator": "user-asset",
                    "asset_path": "assets/scenes/s1.mp4",
                    "subtitle_burn": True,
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    cues = manifest["scenes"][0]["caption_cues"]
    assert len(cues) >= 3
    assert all(len(cue["text"]) <= 12 for cue in cues)
    assert all(len(cue["lines"]) == 1 for cue in cues)
    assert all(cue["end_sec"] - cue["start_sec"] <= 1.801 for cue in cues)
    assert all(cue["source"] == "estimated" for cue in cues)


def test_release_render_defaults_missing_subtitle_burn_to_bottom_captions(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "caption-default", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    narration = "灵剪用底部字幕承接口播节奏。"
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": narration}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 3.0,
                }
            ],
            "total_duration_sec": 3.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": narration,
                    "duration_sec": 3.0,
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/s1.mp4",
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    scene = manifest["scenes"][0]
    assert scene["subtitle_burn"] is True
    assert scene["caption_timing"]["source"] == "estimated"
    assert scene["caption_cues"]
    assert all(cue["source"] == "estimated" for cue in scene["caption_cues"])


def test_release_render_prefers_voice_segment_caption_cues(tmp_path, monkeypatch):
    project = init_project(tmp_path / "p1", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "第一句第二句"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 4.0,
                    "caption_cues": [
                        {"text": "第一句", "start_sec": 0.2, "end_sec": 1.4},
                        {"text": "第二句", "start_sec": 1.6, "end_sec": 2.8},
                    ],
                }
            ],
            "total_duration_sec": 4.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "第一句第二句",
                    "duration_sec": 4.0,
                    "generator": "user-asset",
                    "asset_path": "assets/scenes/s1.mp4",
                    "subtitle_burn": True,
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    scene = manifest["scenes"][0]
    assert scene["caption_timing"]["source"] == "voice_segment"
    assert scene["caption_timing"]["release_ready"] is True
    assert scene["caption_timing"]["release_gate"] == "strict_caption_timing"
    assert [
        (cue["text"], cue["start_sec"], cue["end_sec"], cue["source"])
        for cue in scene["caption_cues"]
    ] == [
        ("第一句", 0.2, 1.4, "voice_segment"),
        ("第二句", 1.6, 2.8, "voice_segment"),
    ]


def test_release_render_preserves_voice_caption_source_metadata(tmp_path, monkeypatch):
    project = init_project(tmp_path / "caption-source", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "第一句第二句"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 4.0,
                    "caption_cues": [
                        {
                            "text": "第一句",
                            "start_sec": 0.2,
                            "end_sec": 1.4,
                            "source": "voice_duration_aligned",
                            "timing_basis": "real_segment_duration",
                        },
                        {
                            "text": "第二句",
                            "start_sec": 1.6,
                            "end_sec": 2.8,
                            "source": "voice_duration_aligned",
                            "timing_basis": "real_segment_duration",
                        },
                    ],
                }
            ],
            "total_duration_sec": 4.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "第一句第二句",
                    "duration_sec": 4.0,
                    "generator": "user-asset",
                    "asset_path": "assets/scenes/s1.mp4",
                    "subtitle_burn": True,
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    scene = json.loads(result.manifest_path.read_text(encoding="utf-8"))["scenes"][0]
    assert scene["caption_timing"]["source"] == "voice_duration_aligned"
    assert scene["caption_timing"]["timing_basis"] == "real_segment_duration"
    assert scene["caption_timing"]["release_ready"] is True
    assert scene["caption_timing"]["release_gate"] == "strict_caption_timing"
    assert [
        (cue["source"], cue["timing_basis"])
        for cue in scene["caption_cues"]
    ] == [
        ("voice_duration_aligned", "real_segment_duration"),
        ("voice_duration_aligned", "real_segment_duration"),
    ]


def test_release_render_marks_invalid_voice_segment_caption_cues(tmp_path, monkeypatch):
    project = init_project(tmp_path / "p1", "项目")
    video_dir = project.path / "assets" / "scenes"
    video_dir.mkdir(parents=True)
    (video_dir / "s1.mp4").write_bytes(b"VIDEO1")
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "第一句第二句"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 4.0,
                    "caption_cues": [{"text": "缺少结束时间", "start_sec": 0.2}],
                }
            ],
            "total_duration_sec": 4.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "第一句第二句",
                    "duration_sec": 4.0,
                    "generator": "user-asset",
                    "asset_path": "assets/scenes/s1.mp4",
                    "subtitle_burn": True,
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    scene = manifest["scenes"][0]
    assert scene["caption_timing"]["source"] == "voice_segment_invalid"
    assert scene["caption_timing"]["release_ready"] is False
    assert scene["caption_timing"]["release_blocker_code"] == (
        "RELEASE_CAPTION_VOICE_TIMING_INVALID"
    )
    assert scene["caption_timing"]["recovery_target_field"] == (
        "artifacts/voice_plan.json segments[].caption_cues"
    )
    assert scene["caption_cues"][0]["text"] == "第一句第二句"

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_CAPTION_TIMING_NOT_READY"
        assert exc.details["blockers"][0]["release_blocker_code"] == (
            "RELEASE_CAPTION_VOICE_TIMING_INVALID"
        )
    else:
        raise AssertionError("expected RELEASE_CAPTION_TIMING_NOT_READY")


def test_release_strict_render_blocks_required_evidence_without_scene_ref(
    tmp_path, monkeypatch
):
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-unbound",
        evidence_assets=[
            {
                "id": "codex-s1",
                "evidence_type": "codex_operation_recording",
                "target_scene_id": "s1",
                "evidence_clip_status": "captured",
                "evidence_clip_path": "assets/evidence/videos/codex-s1.mp4",
            }
        ],
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio_or_video(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenes"][0]["requires_real_evidence_asset"] is True
    assert manifest["visual_evidence_assets"]["count"] == 1

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_VISUAL_EVIDENCE_NOT_READY"
        assert exc.details["blockers"][0]["release_blocker_code"] == (
            "RELEASE_SCENE_EVIDENCE_ASSET_UNBOUND"
        )
        assert exc.details["blockers"][0]["scene_id"] == "s1"
        assert exc.details["render_manifest"] == "renders/release/douyin/render_manifest.json"
    else:
        raise AssertionError("expected RELEASE_VISUAL_EVIDENCE_NOT_READY")


def test_release_strict_render_blocks_evidence_ref_bound_to_other_scene(
    tmp_path, monkeypatch
):
    evidence_asset = {
        "id": "codex-s2",
        "evidence_type": "codex_operation_recording",
        "target_scene_id": "s2",
        "evidence_clip_status": "captured",
        "evidence_clip_path": "assets/evidence/videos/codex-s2.mp4",
    }
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-mismatch",
        evidence_refs=[{"id": "codex-s2", "target_scene_id": "s2"}],
        evidence_assets=[evidence_asset],
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio_or_video(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_VISUAL_EVIDENCE_NOT_READY"
        codes = {blocker["release_blocker_code"] for blocker in exc.details["blockers"]}
        assert "RELEASE_SCENE_EVIDENCE_TARGET_MISMATCH" in codes
        assert "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED" not in codes
    else:
        raise AssertionError("expected RELEASE_VISUAL_EVIDENCE_NOT_READY")


def test_release_strict_render_rejects_generated_evidence_card_for_recording_requirement(
    tmp_path, monkeypatch
):
    evidence_asset = {
        "id": "codex-card",
        "evidence_type": "codex_operation_recording",
        "target_scene_id": "s1",
        "evidence_clip_status": "generated",
        "evidence_clip_path": "assets/evidence/videos/codex-card.mp4",
        "evidence_visual_source": "text_card",
    }
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-generated-card",
        evidence_refs=[{"id": "codex-card", "target_scene_id": "s1"}],
        evidence_assets=[evidence_asset],
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio_or_video(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")
    manifest_scene = json.loads(result.manifest_path.read_text(encoding="utf-8"))[
        "scenes"
    ][0]
    assert manifest_scene["evidence_asset_refs"][0]["target_scene_id"] == "s1"

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_VISUAL_EVIDENCE_NOT_READY"
        codes = {blocker["release_blocker_code"] for blocker in exc.details["blockers"]}
        assert "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC" in codes
    else:
        raise AssertionError("expected RELEASE_VISUAL_EVIDENCE_NOT_READY")


def test_release_strict_render_blocks_captured_evidence_type_mismatch(
    tmp_path, monkeypatch
):
    evidence_asset = {
        "id": "terminal-s1",
        "evidence_type": "terminal_recording_capture",
        "target_scene_id": "s1",
        "evidence_clip_status": "captured",
        "evidence_clip_path": "assets/evidence/videos/terminal-s1.mp4",
        "evidence_visual_source": "terminal_recording_video",
    }
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-type-mismatch",
        evidence_refs=[{"id": "terminal-s1", "target_scene_id": "s1"}],
        evidence_assets=[evidence_asset],
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio_or_video(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_VISUAL_EVIDENCE_NOT_READY"
        codes = {blocker["release_blocker_code"] for blocker in exc.details["blockers"]}
        assert "RELEASE_SCENE_EVIDENCE_RECORDING_TYPE_MISMATCH" in codes
    else:
        raise AssertionError("expected RELEASE_VISUAL_EVIDENCE_NOT_READY")


def test_release_strict_render_uses_scene_recipe_over_profile_evidence_list(
    tmp_path, monkeypatch
):
    evidence_asset = {
        "id": "codex-s1",
        "evidence_type": "codex_operation_recording",
        "target_scene_id": "s1",
        "evidence_clip_status": "captured",
        "evidence_clip_path": "assets/evidence/videos/codex-s1.mp4",
        "evidence_visual_source": "codex_operation_video",
        "recording_task_redacted": "录制 Codex app 一句话触发灵剪流程",
        "evidence_clip_duration_sec": 4.0,
    }
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-scene-recipe-over-profile",
        evidence_refs=[{"id": "codex-s1", "target_scene_id": "s1"}],
        evidence_assets=[evidence_asset],
    )
    visual_path = project.path / "artifacts" / "visual_plan.json"
    visual_plan = json.loads(visual_path.read_text(encoding="utf-8"))
    visual_plan["scenes"][0]["asset_recipe_id"] = "codex_prompt_or_reconstructed_ui"
    visual_plan["scenes"][0]["expected_real_evidence"] = [
        "GitHub repo",
        "README 顶部安装入口",
        "Codex app 对话触发",
        "终端/QA 证据",
        "导出包或 Star CTA",
    ]
    _write_visuals_artifact(project, visual_plan)
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio_or_video(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenes"][0]["asset_recipe_id"] == "codex_prompt_or_reconstructed_ui"
    assert manifest["scenes"][0]["evidence_asset_refs"][0]["id"] == "codex-s1"


def test_release_strict_render_does_not_apply_profile_intent_to_scene_recipe(
    tmp_path, monkeypatch
):
    evidence_asset = {
        "id": "qa-s1",
        "evidence_type": "terminal_recording_capture",
        "target_scene_id": "s1",
        "evidence_clip_status": "captured",
        "evidence_clip_path": "assets/evidence/videos/qa-s1.mp4",
        "evidence_visual_source": "terminal_recording_video",
        "source_uri": "logs/qa.log",
        "evidence_clip_duration_sec": 4.0,
    }
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-scene-recipe-without-profile-intent",
        evidence_refs=[{"id": "qa-s1", "target_scene_id": "s1"}],
        evidence_assets=[evidence_asset],
    )
    visual_path = project.path / "artifacts" / "visual_plan.json"
    visual_plan = json.loads(visual_path.read_text(encoding="utf-8"))
    visual_plan["scenes"][0]["asset_recipe_id"] = "qa_report_capture"
    visual_plan["scenes"][0]["expected_real_evidence"] = [
        "GitHub repo",
        "README 顶部安装入口",
        "Codex app 对话触发",
        "终端/QA 证据",
        "导出包或 Star CTA",
        "qa_report_capture",
    ]
    _write_visuals_artifact(project, visual_plan)
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio_or_video(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenes"][0]["asset_recipe_id"] == "qa_report_capture"
    assert manifest["scenes"][0]["evidence_asset_refs"][0]["id"] == "qa-s1"


def test_release_strict_render_blocks_captured_recording_without_task_intent(
    tmp_path, monkeypatch
):
    evidence_asset = {
        "id": "codex-s1",
        "evidence_type": "codex_operation_recording",
        "target_scene_id": "s1",
        "evidence_clip_status": "captured",
        "evidence_clip_path": "assets/evidence/videos/codex-s1.mp4",
        "evidence_visual_source": "codex_operation_video",
    }
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-intent-missing",
        evidence_refs=[{"id": "codex-s1", "target_scene_id": "s1"}],
        evidence_assets=[evidence_asset],
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio_or_video(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_VISUAL_EVIDENCE_NOT_READY"
        codes = {blocker["release_blocker_code"] for blocker in exc.details["blockers"]}
        assert "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE" in codes
    else:
        raise AssertionError("expected RELEASE_VISUAL_EVIDENCE_NOT_READY")


def test_release_strict_render_blocks_captured_recording_intent_mismatch(
    tmp_path, monkeypatch
):
    evidence_asset = {
        "id": "codex-s1",
        "evidence_type": "codex_operation_recording",
        "target_scene_id": "s1",
        "evidence_clip_status": "captured",
        "evidence_clip_path": "assets/evidence/videos/codex-s1.mp4",
        "evidence_visual_source": "codex_operation_video",
        "recording_task_redacted": "录制 GitHub README 页面滚动",
    }
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-intent-mismatch",
        evidence_refs=[{"id": "codex-s1", "target_scene_id": "s1"}],
        evidence_assets=[evidence_asset],
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio_or_video(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_VISUAL_EVIDENCE_NOT_READY"
        codes = {blocker["release_blocker_code"] for blocker in exc.details["blockers"]}
        assert "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE" in codes
    else:
        raise AssertionError("expected RELEASE_VISUAL_EVIDENCE_NOT_READY")


def test_release_strict_render_blocks_captured_recording_too_short(
    tmp_path, monkeypatch
):
    evidence_asset = {
        "id": "codex-s1",
        "evidence_type": "codex_operation_recording",
        "target_scene_id": "s1",
        "evidence_clip_status": "captured",
        "evidence_clip_path": "assets/evidence/videos/codex-s1.mp4",
        "evidence_visual_source": "codex_operation_video",
        "recording_task_redacted": "录制 Codex app 一句话触发灵剪流程",
        "evidence_clip_duration_sec": 0.5,
    }
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-recording-too-short",
        evidence_refs=[{"id": "codex-s1", "target_scene_id": "s1"}],
        evidence_assets=[evidence_asset],
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio_or_video(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_VISUAL_EVIDENCE_NOT_READY"
        codes = {blocker["release_blocker_code"] for blocker in exc.details["blockers"]}
        assert "RELEASE_SCENE_EVIDENCE_RECORDING_TOO_SHORT" in codes
    else:
        raise AssertionError("expected RELEASE_VISUAL_EVIDENCE_NOT_READY")


def test_release_strict_render_blocks_captured_recording_duration_not_verifiable(
    tmp_path, monkeypatch
):
    evidence_asset = {
        "id": "codex-s1",
        "evidence_type": "codex_operation_recording",
        "target_scene_id": "s1",
        "evidence_clip_status": "captured",
        "evidence_clip_path": "assets/evidence/videos/codex-s1.mp4",
        "evidence_visual_source": "codex_operation_video",
        "recording_task_redacted": "录制 Codex app 一句话触发灵剪流程",
    }
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-recording-duration-unreadable",
        evidence_refs=[{"id": "codex-s1", "target_scene_id": "s1"}],
        evidence_assets=[evidence_asset],
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            if "format=duration" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps({"format": {}}),
                    stderr="",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_type": (
                                    "video"
                                    if Path(command[-1]).suffix.lower() == ".mp4"
                                    else "audio"
                                )
                            }
                        ]
                    }
                ),
                stderr="",
            )
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_VISUAL_EVIDENCE_NOT_READY"
        codes = {blocker["release_blocker_code"] for blocker in exc.details["blockers"]}
        assert "RELEASE_SCENE_EVIDENCE_RECORDING_DURATION_NOT_VERIFIABLE" in codes
    else:
        raise AssertionError("expected RELEASE_VISUAL_EVIDENCE_NOT_READY")


def test_release_strict_render_accepts_same_scene_verifiable_evidence(
    tmp_path, monkeypatch
):
    evidence_asset = {
        "id": "codex-s1",
        "evidence_type": "codex_operation_recording",
        "target_scene_id": "s1",
        "evidence_clip_status": "captured",
        "evidence_clip_path": "assets/evidence/videos/codex-s1.mp4",
        "evidence_visual_source": "codex_operation_video",
        "recording_task_redacted": "录制 Codex app 一句话触发灵剪流程",
        "evidence_clip_duration_sec": 4.0,
    }
    project = _approved_release_project_with_required_evidence(
        tmp_path,
        name="evidence-ready",
        evidence_refs=[{"id": "codex-s1", "target_scene_id": "s1"}],
        evidence_assets=[evidence_asset],
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio_or_video(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenes"][0]["evidence_asset_refs"][0]["target_scene_id"] == "s1"


def test_release_render_mixes_declared_bgm_and_sfx_assets(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "full.wav").write_bytes(b"VOICE")
    asset_dir = project.path / "assets" / "audio"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "bgm.wav").write_bytes(b"BGM")
    (asset_dir / "click.wav").write_bytes(b"SFX")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "真实发布字幕"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/full.wav",
                    "duration_sec": 10.0,
                }
            ],
            "total_duration_sec": 10.0,
            "audio_assets": {
                "bgm": {
                    "path": "assets/audio/bgm.wav",
                    "bgm_to_voice_db": -16.0,
                },
                "sfx": [
                    {
                        "path": "assets/audio/click.wav",
                        "at_sec": 1.25,
                        "gain_db": -12.0,
                        "scene_id": "s1",
                        "action": "安装命令高亮",
                        "purpose": "提示用户注意操作结果",
                    }
                ],
            },
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "/usr/bin/ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"codec_type": "audio"}]}),
                stderr="",
            )
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    command_text = "\n".join(" ".join(command) for command in commands)
    assert "amix=inputs=3" in command_text
    assert RELEASE_LOUDNORM_FILTER in command_text
    assert "volume=-16.0dB" in command_text
    assert "adelay=1250|1250" in command_text
    assert "mixed_audio.m4a" in " ".join(commands[-1])
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["audio_mix"]["rendered"] is True
    assert manifest["audio_mix"]["mixed_audio_path"] == "renders/release/douyin/mixed_audio.m4a"
    assert manifest["audio_mix"]["bgm_present"] is True
    assert manifest["audio_mix"]["bgm_path"] == "assets/audio/bgm.wav"
    assert manifest["audio_mix"]["bgm_to_voice_db"] == -16.0
    assert manifest["audio_mix"]["sfx_count"] == 1
    assert manifest["audio_mix"]["sfx_density_per_10_sec"] == 1.0
    assert manifest["audio_mix"]["sfx_events"][0]["path"] == "assets/audio/click.wav"
    assert manifest["audio_mix"]["sfx_events"][0]["scene_id"] == "s1"
    assert manifest["audio_mix"]["sfx_events"][0]["action"] == "安装命令高亮"
    assert manifest["audio_mix"]["sfx_events"][0]["purpose"] == "提示用户注意操作结果"
    assert manifest["audio_mix"]["audio_normalization"] == {
        "rendered": True,
        "filter": RELEASE_LOUDNORM_FILTER,
        "target_lufs": -14,
        "target_lra": 11,
        "target_true_peak_db": -1.0,
    }


def test_release_strict_render_blocks_declared_bgm_sfx_without_mix(
    tmp_path, monkeypatch
):
    project = init_project(tmp_path / "declared-audio", "项目")
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "full.wav").write_bytes(b"VOICE")
    scene_dir = project.path / "assets" / "scenes"
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "s1.mp4").write_bytes(b"VIDEO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "真实发布字幕"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/full.wav",
                    "duration_sec": 4.0,
                    "caption_cues": [
                        {"text": "真实发布", "start_sec": 0.2, "end_sec": 1.6},
                        {"text": "字幕", "start_sec": 1.8, "end_sec": 2.8},
                    ],
                }
            ],
            "total_duration_sec": 4.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "真实发布字幕",
                    "duration_sec": 4.0,
                    "generator": "user-asset",
                    "asset_path": "assets/scenes/s1.mp4",
                    "subtitle_burn": True,
                    "bgm": "科技感 BGM 低于人声",
                    "sfx_points": [
                        {
                            "action": "安装命令高亮",
                            "purpose": "提示用户注意操作结果",
                        }
                    ],
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    audio_mix = manifest["audio_mix"]
    assert audio_mix["bgm_present"] is False
    assert audio_mix["sfx_count"] == 0
    assert audio_mix["declared_audio_requirements"]["bgm_required"] is True
    assert audio_mix["declared_audio_requirements"]["sfx_required"] is True

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_AUDIO_MIX_NOT_READY"
        codes = {blocker["release_blocker_code"] for blocker in exc.details["blockers"]}
        assert "RELEASE_BGM_DECLARED_BUT_NOT_RENDERED" in codes
        assert "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED" in codes
        assert exc.details["render_manifest"] == "renders/release/douyin/render_manifest.json"
    else:
        raise AssertionError("expected RELEASE_AUDIO_MIX_NOT_READY")


def test_release_render_converts_scene_local_sfx_time_to_absolute_delay(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "full.wav").write_bytes(b"VOICE")
    asset_dir = project.path / "assets" / "audio"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "click.wav").write_bytes(b"SFX")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [
                {"id": "s1", "narration_text": "第一镜"},
                {"id": "s2", "narration_text": "第二镜按钮出现"},
            ],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/full.wav",
                    "duration_sec": 2.0,
                },
                {
                    "scene_id": "s2",
                    "audio_path": "artifacts/voice_segments/full.wav",
                    "duration_sec": 3.0,
                },
            ],
            "total_duration_sec": 5.0,
            "audio_assets": {
                "sfx": [
                    {
                        "path": "assets/audio/click.wav",
                        "at_sec": 0.75,
                        "local_at_sec": 0.75,
                        "time_basis": "scene_local",
                        "gain_db": -12.0,
                        "scene_id": "s2",
                        "action": "第二镜按钮点击",
                        "visual_event": "button_press",
                    }
                ],
            },
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "/usr/bin/ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"codec_type": "audio"}]}),
                stderr="",
            )
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    command_text = "\n".join(" ".join(command) for command in commands)
    assert "amix=inputs=2" in command_text
    assert "adelay=2750|2750" in command_text
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    sfx_event = manifest["audio_mix"]["sfx_events"][0]
    assert sfx_event["scene_id"] == "s2"
    assert sfx_event["at_sec"] == 2.75
    assert sfx_event["local_at_sec"] == 0.75
    assert sfx_event["time_basis"] == "scene_local"
    assert sfx_event["visual_event"] == "button_press"


def test_release_render_records_unverifiable_audio_assets_without_mixing(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "full.wav").write_bytes(b"VOICE")
    asset_dir = project.path / "assets" / "audio"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "bad-bgm.wav").write_bytes(b"not-bgm")
    (asset_dir / "bad-click.wav").write_bytes(b"not-sfx")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "真实发布字幕"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/full.wav",
                    "duration_sec": 10.0,
                }
            ],
            "total_duration_sec": 10.0,
            "audio_assets": {
                "bgm": {
                    "path": "assets/audio/bad-bgm.wav",
                    "bgm_to_voice_db": -16.0,
                },
                "sfx": [
                    {
                        "path": "assets/audio/bad-click.wav",
                        "at_sec": 1.25,
                        "gain_db": -12.0,
                        "scene_id": "s1",
                        "action": "安装命令高亮",
                    }
                ],
            },
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if _is_ffprobe_command(command):
            stream_type = "audio" if Path(command[-1]).name == "full.wav" else "video"
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"codec_type": stream_type}]}),
                stderr="",
            )
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    command_text = "\n".join(" ".join(command) for command in commands)
    assert "amix=inputs=" not in command_text
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    audio_mix = manifest["audio_mix"]
    assert audio_mix["rendered"] is False
    assert audio_mix["bgm_present"] is False
    assert audio_mix["sfx_count"] == 0
    assert audio_mix["invalid_audio_asset_count"] == 2
    assert audio_mix["invalid_audio_assets"][0] == {
        "kind": "bgm",
        "path": "assets/audio/bad-bgm.wav",
        "reason": "missing_or_unverifiable",
    }
    assert audio_mix["invalid_audio_assets"][1] == {
        "kind": "sfx",
        "path": "assets/audio/bad-click.wav",
        "scene_id": "s1",
        "action": "安装命令高亮",
        "reason": "missing_or_unverifiable",
    }


def test_release_render_records_missing_declared_audio_assets(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "full.wav").write_bytes(b"VOICE")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "真实发布字幕"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/full.wav",
                    "duration_sec": 10.0,
                }
            ],
            "total_duration_sec": 10.0,
            "audio_assets": {
                "bgm": {
                    "path": "assets/audio/missing-bgm.wav",
                    "bgm_to_voice_db": -16.0,
                },
                "sfx": [
                    {
                        "path": "/Users/example/private-click.wav",
                        "at_sec": 1.25,
                        "gain_db": -12.0,
                        "scene_id": "s1",
                        "action": "安装命令高亮",
                    }
                ],
            },
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    audio_mix = manifest["audio_mix"]
    assert audio_mix["rendered"] is False
    assert audio_mix["bgm_present"] is False
    assert audio_mix["sfx_count"] == 0
    assert audio_mix["invalid_audio_asset_count"] == 2
    assert audio_mix["invalid_audio_assets"][0] == {
        "kind": "bgm",
        "path": "assets/audio/missing-bgm.wav",
        "reason": "missing_or_unverifiable",
    }
    assert audio_mix["invalid_audio_assets"][1]["kind"] == "sfx"
    assert audio_mix["invalid_audio_assets"][1]["path"] == "<external-redacted>"
    assert audio_mix["invalid_audio_assets"][1]["scene_id"] == "s1"
    assert audio_mix["invalid_audio_assets"][1]["action"] == "安装命令高亮"

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release", strict=True)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_AUDIO_MIX_NOT_READY"
        assert exc.details["blockers"][0]["release_blocker_code"] == (
            "RELEASE_AUDIO_DECLARED_ASSET_MISSING"
        )
        invalid = exc.details["blockers"][0]["invalid_audio_assets"]
        assert invalid[0]["path"] == "assets/audio/missing-bgm.wav"
        assert invalid[1]["path"] == "<external-redacted>"
    else:
        raise AssertionError("expected RELEASE_AUDIO_MIX_NOT_READY")


def test_release_render_merges_missing_audio_assets_into_explicit_audio_mix(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "full.wav").write_bytes(b"VOICE")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "真实发布字幕"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/full.wav",
                    "duration_sec": 10.0,
                }
            ],
            "total_duration_sec": 10.0,
            "audio_mix": {
                "rendered": False,
                "bgm_present": False,
                "sfx_count": 0,
                "policy": "上游声明无可用音频混合。",
            },
            "audio_assets": {
                "bgm": {"path": "assets/audio/missing-bgm.wav"},
                "sfx": [
                    {
                        "path": "/Users/example/private-click.wav",
                        "scene_id": "s1",
                        "action": "安装命令高亮",
                    }
                ],
            },
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"OUTPUT")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    audio_mix = manifest["audio_mix"]
    assert audio_mix["policy"] == "上游声明无可用音频混合。"
    assert audio_mix["invalid_audio_asset_count"] == 2
    assert audio_mix["invalid_audio_assets"][0]["path"] == "assets/audio/missing-bgm.wav"
    assert audio_mix["invalid_audio_assets"][1]["path"] == "<external-redacted>"


def test_release_render_falls_back_to_solid_when_delegated_asset_missing_and_qa_warns(
    tmp_path, monkeypatch
):
    project = _approved_mock_project(tmp_path)
    audio_path = project.path / "artifacts" / "voice_segments" / "voice.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "缺少宿主产物"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/voice.aiff",
                    "duration_sec": 2.0,
                }
            ],
            "total_duration_sec": 2.0,
        },
    )
    _write_visuals_artifact(
        project,
        {
            "id": "visuals",
            "ratio": "9:16",
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_text": "缺少宿主产物",
                    "duration_sec": 2.0,
                    "generator": "hyperframes",
                    "asset_path": "assets/scenes/missing.mp4",
                    "subtitle_burn": False,
                }
            ],
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_render_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        Path(command[-1]).write_bytes(b"MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_render_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="release")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        "packages.core.qa.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
            stderr="",
        ),
    )
    report = run_qa(project, release=True)

    assert manifest["visual_real_count"] == 0
    assert manifest["visual_total"] == 1
    assert manifest["scenes"][0]["render_source"] == "fallback_solid"
    assert report.release_ready is True
    assert any(issue.code == "RELEASE_VISUAL_IS_BLANK_CARD" for issue in report.warnings)

    strict_report = run_qa(project, release=True, strict=True)

    assert strict_report.release_ready is False
    assert any(
        issue.code == "RELEASE_VISUAL_IS_BLANK_CARD"
        for issue in strict_report.hard_failures
    )
    try:
        export_project(project, "douyin", "zh-CN", "9:16", release=True, strict=True)
    except LingjianError as exc:
        assert exc.error_code == "QA_BLOCKING"
    else:
        raise AssertionError("expected QA_BLOCKING")


def test_release_render_reports_ffmpeg_filter_error_with_stderr(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.aiff"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"REAL AUDIO")
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "provider_id": "real_llm",
            "provider_is_mock": False,
            "scenes": [{"id": "s1", "narration_text": "真实发布字幕"}],
        },
    )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.aiff",
                    "duration_sec": 2.0,
                }
            ],
            "total_duration_sec": 2.0,
        },
    )
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    def fake_run(command, **kwargs):
        if _is_ffprobe_command(command):
            return _fake_ffprobe_audio(command)
        return subprocess.CompletedProcess(
            command,
            8,
            stdout="",
            stderr="No such filter: 'drawtext'\n/private/path/should/not/leak\n",
        )

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="release")
    except LingjianError as exc:
        assert exc.error_code == "FFMPEG_FILTER_UNAVAILABLE"
        assert "No such filter" in exc.details["ffmpeg_stderr_tail"]
        assert str(project.path) not in exc.details["ffmpeg_stderr_tail"]
    else:
        raise AssertionError("expected FFMPEG_FILTER_UNAVAILABLE")


def test_release_duration_uses_voice_plan_total_duration(tmp_path):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "segments": [],
            "total_duration_sec": 7.25,
        },
    )

    assert _release_duration(project) == 7.25


def test_release_audio_path_prefers_full_audio_track(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    full_audio = audio_dir / "full.wav"
    first_segment = audio_dir / "s1.wav"
    full_audio.write_bytes(b"FULL AUDIO")
    first_segment.write_bytes(b"FIRST AUDIO")
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 1.0,
                }
            ],
            "total_duration_sec": 1.0,
        },
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "ffprobe" else None,
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"streams": [{"codec_type": "audio"}]}),
            stderr="",
        )

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    assert _release_audio_path(project) == full_audio


def test_release_audio_path_falls_back_when_full_audio_unverifiable(
    tmp_path,
    monkeypatch,
):
    project = _approved_mock_project(tmp_path)
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    full_audio = audio_dir / "full.wav"
    first_segment = audio_dir / "s1.wav"
    full_audio.write_bytes(b"NOT AUDIO")
    first_segment.write_bytes(b"FIRST AUDIO")
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 1.0,
                }
            ],
            "total_duration_sec": 1.0,
        },
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "ffprobe" else None,
    )

    def fake_run(command, **kwargs):
        stream_type = "video" if Path(command[-1]).name == "full.wav" else "audio"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"streams": [{"codec_type": stream_type}]}),
            stderr="",
        )

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    assert _release_audio_path(project) == first_segment


def test_release_audio_path_rejects_unverifiable_voice_audio(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "full.wav").write_bytes(b"NOT AUDIO")
    (audio_dir / "s1.wav").write_bytes(b"NOT AUDIO EITHER")
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "real_tts",
            "provider_is_mock": False,
            "full_audio_path": "artifacts/voice_segments/full.wav",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 1.0,
                }
            ],
            "total_duration_sec": 1.0,
        },
    )
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "ffprobe" else None,
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"streams": [{"codec_type": "video"}]}),
            stderr="",
        )

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    try:
        _release_audio_path(project)
    except LingjianError as exc:
        assert exc.error_code == "RELEASE_AUDIO_MISSING"
        assert "可验证口播音频" in exc.message_zh
    else:
        raise AssertionError("expected RELEASE_AUDIO_MISSING")


def test_release_duration_falls_back_when_voice_duration_missing(tmp_path):
    project = _approved_mock_project(tmp_path)
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "mock",
            "provider_is_mock": True,
            "segments": [],
        },
    )

    assert _release_duration(project) == 3.0


def test_preview_real_without_ffmpeg_fails_instead_of_writing_stub(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    monkeypatch.setattr("packages.core.rendering.shutil.which", lambda name: None)

    try:
        render_project(project, "douyin", "zh-CN", "9:16", mode="preview", real_preview=True)
    except LingjianError as exc:
        assert exc.error_code == "REAL_PREVIEW_RENDER_REQUIRES_FFMPEG"
    else:
        raise AssertionError("expected REAL_PREVIEW_RENDER_REQUIRES_FFMPEG")


def test_preview_real_uses_ffmpeg_when_available(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    monkeypatch.setattr(
        "packages.core.rendering.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"REAL PREVIEW MP4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.rendering.subprocess.run", fake_run)

    result = render_project(project, "douyin", "zh-CN", "9:16", mode="preview", real_preview=True)

    assert result.video_path.read_bytes() == b"REAL PREVIEW MP4"
    assert commands


def test_release_qa_rejects_stub_and_unverifiable_video(tmp_path):
    project = _approved_mock_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(STUB_VIDEO_BYTES)
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false},
    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )

    report = run_qa(project, release=True)

    assert report.release_ready is False
    assert {issue.code for issue in report.hard_failures} >= {
        "RELEASE_VIDEO_IS_STUB",
        "RENDER_NOT_VERIFIABLE",
    }


def test_release_qa_rejects_release_without_audio_stream(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false},
    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        "packages.core.qa.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"streams":[{"codec_type":"video"}]}',
            stderr="",
        ),
    )

    report = run_qa(project, release=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_AUDIO_MISSING" for issue in report.hard_failures)


def test_release_qa_accepts_when_ffprobe_confirms_video_and_audio(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false},
    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        "packages.core.qa.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
            stderr="",
        ),
    )

    report = run_qa(project, release=True)

    assert report.release_ready is True


def test_release_qa_rejects_evidence_refs_bound_to_other_scene(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_video = project.path / "assets" / "evidence" / "videos" / "codex-s1.mp4"
    evidence_video.parent.mkdir(parents=True)
    evidence_video.write_bytes(b"mp4")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_plan_sha256": canonical_json_hash(
                    {"id": "visuals", "engine": "ffmpeg_card", "scenes": []}
                ),
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "real_tts", "kind": "tts", "is_mock": False},
                    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": False},
                ],
                "visual_evidence_assets": {
                    "assets": [
                        {
                            "id": "codex-s1",
                            "evidence_type": "codex_operation_recording",
                            "path": "assets/evidence/videos/codex-s1.mp4",
                            "evidence_clip_path": "assets/evidence/videos/codex-s1.mp4",
                            "evidence_clip_status": "captured",
                            "target_scene_id": "s1",
                        }
                    ],
                    "evidence_types": ["codex_operation_recording"],
                },
                "scenes": [
                    {
                        "scene_id": "s2",
                        "render_source": "video",
                        "duration_sec": 2.0,
                        "requires_real_evidence_asset": True,
                        "evidence_asset_refs": [
                            {
                                "id": "codex-s1",
                                "evidence_type": "codex_operation_recording",
                                "path": "assets/evidence/videos/codex-s1.mp4",
                                "evidence_clip_path": "assets/evidence/videos/codex-s1.mp4",
                                "evidence_clip_status": "captured",
                                "target_scene_id": "s1",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        "packages.core.qa.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
            stderr="",
        ),
    )

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SCENE_EVIDENCE_TARGET_MISMATCH"
        for issue in report.hard_failures
    )


def test_release_qa_rejects_unbound_recording_evidence_ref(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_video = project.path / "assets" / "evidence" / "videos" / "codex.mp4"
    evidence_video.parent.mkdir(parents=True)
    evidence_video.write_bytes(b"mp4")
    unbound_ref = {
        "id": "codex",
        "evidence_type": "codex_operation_recording",
        "path": "assets/evidence/videos/codex.mp4",
        "evidence_clip_path": "assets/evidence/videos/codex.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "codex_operation_video",
    }
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_plan_sha256": canonical_json_hash(
                    {"id": "visuals", "engine": "ffmpeg_card", "scenes": []}
                ),
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "real_tts", "kind": "tts", "is_mock": False},
                    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": False},
                ],
                "visual_evidence_assets": {
                    "assets": [unbound_ref],
                    "evidence_types": ["codex_operation_recording"],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "render_source": "video",
                        "duration_sec": 2.0,
                        "requires_real_evidence_asset": True,
                        "expected_real_evidence": ["Codex app 操作画面"],
                        "evidence_asset_refs": [unbound_ref],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        "packages.core.qa.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
            stderr="",
        ),
    )

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SCENE_EVIDENCE_TARGET_UNBOUND"
        for issue in report.hard_failures
    )


def test_release_qa_timeout_marks_video_not_verifiable(tmp_path, monkeypatch):
    project = _approved_mock_project(tmp_path)
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        """
{
  "mode": "release",
  "platform": "douyin",
  "language": "zh-CN",
  "ratio": "9:16",
  "video_path": "renders/release/douyin/video.mp4",
  "providers": [
    {"id": "real_llm", "kind": "llm", "is_mock": false},
    {"id": "real_tts", "kind": "tts", "is_mock": false},
    {"id": "ffmpeg_card", "kind": "renderer", "is_mock": false}
  ]
}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffprobe")

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout"))

    monkeypatch.setattr("packages.core.qa.subprocess.run", timeout_run)

    report = run_qa(project, release=True)

    assert report.release_ready is False
    assert any(issue.code == "RENDER_NOT_VERIFIABLE" for issue in report.hard_failures)
