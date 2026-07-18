import base64
import json
import subprocess

from packages.core.capabilities import detect_capabilities
from packages.core.director_contract import director_route_policy, layout_contract
from packages.core.project import ProjectRef
from packages.core.qa import FRAME_SAMPLE_HEIGHT, FRAME_SAMPLE_WIDTH, run_qa
from packages.core.visual_generation import _host_visual_asset_duration, ensure_scene_asset
from providers.registry import resolve_provider
from scripts.providers.hyperframes_scene_cli import (
    _adapter_contract,
    _html,
    _layout_for,
    _visual_keyword,
)


def _high_contrast_static_frame() -> bytes:
    pixels = bytearray()
    for y in range(FRAME_SAMPLE_HEIGHT):
        for x in range(FRAME_SAMPLE_WIDTH):
            in_subtitle_zone = int(FRAME_SAMPLE_HEIGHT * 0.72) <= y < int(
                FRAME_SAMPLE_HEIGHT * 0.92
            )
            value = 255 if in_subtitle_zone and x % 2 == 0 else 0
            pixels.extend([value, value, value])
    return bytes(pixels)


def _caption_band_frame(*, center_caption: bool) -> bytes:
    pixels = bytearray([96, 96, 96] * FRAME_SAMPLE_WIDTH * FRAME_SAMPLE_HEIGHT)
    _paint_caption_band(pixels, int(FRAME_SAMPLE_HEIGHT * 0.76), int(FRAME_SAMPLE_HEIGHT * 0.88))
    if center_caption:
        _paint_caption_band(
            pixels,
            int(FRAME_SAMPLE_HEIGHT * 0.36),
            int(FRAME_SAMPLE_HEIGHT * 0.48),
        )
    return bytes(pixels)


def _paint_caption_band(pixels: bytearray, start_y: int, end_y: int) -> None:
    for y in range(start_y, end_y):
        for x in range(FRAME_SAMPLE_WIDTH):
            index = (y * FRAME_SAMPLE_WIDTH + x) * 3
            value = 240 if y % 4 == 0 and x % 3 == 0 else 20
            pixels[index:index + 3] = bytes([value, value, value])


def _motion_variant(raw: bytes) -> bytes:
    frame = bytearray(raw)
    for index in range(0, len(frame), 9):
        frame[index] = (frame[index] + 64) % 255
    return bytes(frame)


def _half_tone_frame(*, inverted: bool = False) -> bytes:
    pixels = bytearray()
    for y in range(FRAME_SAMPLE_HEIGHT):
        bright_top = y < FRAME_SAMPLE_HEIGHT // 2
        if inverted:
            bright_top = not bright_top
        value = 220 if bright_top else 24
        for _ in range(FRAME_SAMPLE_WIDTH):
            pixels.extend([value, value, value])
    return bytes(pixels)


def _solid_frame(value: int) -> bytes:
    return bytes([value, value, value] * FRAME_SAMPLE_WIDTH * FRAME_SAMPLE_HEIGHT)


def _write_minimal_voice_plan(
    project: ProjectRef,
    *,
    provider_id: str = "volcengine_tts",
    duration: float = 8.0,
) -> None:
    voice_dir = project.path / "artifacts" / "voice_segments"
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "full.wav").write_bytes(b"voice")
    voice_id = "zh_female_vv_uranus_bigtts"
    settings = {"provider_id": provider_id, "voice_id": voice_id}
    (project.path / "artifacts" / "voice_plan.json").write_text(
        json.dumps(
            {
                "provider_id": provider_id,
                "provider_is_mock": False,
                "voice_id": voice_id,
                "provider_voice_settings": settings,
                "segments": [
                    {
                        "scene_id": "s1",
                        "audio_path": "artifacts/voice_segments/full.wav",
                        "duration_sec": duration,
                        "voice_id": voice_id,
                        "provider_voice_settings": settings,
                    }
                ],
                "full_audio_path": "artifacts/voice_segments/full.wav",
                "total_duration_sec": duration,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_voice_plan_caption_cues(
    project: ProjectRef,
    cues: list[dict],
    *,
    scene_id: str = "s1",
) -> None:
    voice_path = project.path / "artifacts" / "voice_plan.json"
    voice_plan = json.loads(voice_path.read_text(encoding="utf-8"))
    for segment in voice_plan.get("segments", []):
        if isinstance(segment, dict) and segment.get("scene_id") == scene_id:
            segment["caption_cues"] = cues
            break
    else:
        voice_plan.setdefault("segments", []).append(
            {"scene_id": scene_id, "duration_sec": 1.0, "caption_cues": cues}
        )
    voice_path.write_text(json.dumps(voice_plan, ensure_ascii=False), encoding="utf-8")


def _write_minimal_release_manifest(project: ProjectRef, **overrides) -> None:
    write_voice_plan = bool(overrides.pop("write_voice_plan", True))
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True, exist_ok=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    payload = {
        "mode": "release",
        "platform": "douyin",
        "language": "zh-CN",
        "ratio": "9:16",
        "video_path": "renders/release/douyin/video.mp4",
        "visual_total": 1,
        "visual_real_count": 1,
        "providers": [
            {"id": "real_llm", "kind": "llm", "is_mock": False},
            {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
        ],
    }
    payload.update(overrides)
    (release_dir / "render_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    if write_voice_plan:
        provider_id = next(
            (
                str(provider.get("id") or "")
                for provider in payload.get("providers", [])
                if isinstance(provider, dict) and provider.get("kind") == "tts"
            ),
            "",
        )
        if provider_id:
            duration = float(payload.get("expected_duration_sec") or 8.0)
            _write_minimal_voice_plan(project, provider_id=provider_id, duration=duration)


def _audio_mix_with_output(project: ProjectRef, mix: dict) -> dict:
    output = project.path / "renders" / "release" / "douyin" / "mixed_audio.m4a"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"not a stub audio")
    return {**mix, "mixed_audio_path": "renders/release/douyin/mixed_audio.m4a"}


def _audio_source_asset(project: ProjectRef, relative_path: str) -> str:
    output = project.path / relative_path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"not a stub source audio")
    return relative_path


def test_kokoro_zero_key_tts_is_detected_as_sample_candidate(monkeypatch):
    monkeypatch.setattr(
        "packages.core.capabilities._local_tts_probe",
        lambda provider_id: provider_id == "kokoro_zh_tts",
    )
    monkeypatch.setenv("PATH", "")

    report = detect_capabilities()

    assert report.groups["tts"].best.id == "kokoro_zh_tts"
    assert report.groups["tts"].best.quality_tier == "zero_key"
    assert report.groups["tts"].best.safe_for_release is True


def test_say_is_not_release_tts_candidate(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    say = bin_dir / "say"
    say.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    say.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr("packages.core.capabilities._local_tts_probe", lambda provider_id: False)

    report = detect_capabilities()

    assert report.groups["tts"].best.id == "missing_tts"
    say_candidate = next(item for item in report.groups["tts"].candidates if item.id == "macos_say")
    assert say_candidate.configured is True
    assert say_candidate.safe_for_release is False


def test_kokoro_provider_uses_json_adapter(monkeypatch):
    audio_base64 = base64.b64encode(b"WAVDATA").decode("ascii")

    def fake_run(command, **kwargs):
        if command[-1] == "--probe":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"audio_base64": audio_base64, "duration_sec": 2.75}),
            stderr="",
        )

    monkeypatch.setattr("providers.local_zero_key_tts.subprocess.run", fake_run)

    provider = resolve_provider("kokoro", "tts")
    audio, duration = provider.synthesize({"voice": "test-voice", "text": "中文自然口播"})

    assert provider.id == "kokoro_zh_tts"
    assert audio == b"WAVDATA"
    assert duration == 2.75


def test_hyperframes_default_adapter_generates_scene_asset(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    project.path.mkdir()
    expected = project.path / "assets" / "scenes" / "s1.mp4"

    monkeypatch.setattr("packages.core.visual_generation._npx_hyperframes_available", lambda: True)

    def fake_run(command, **kwargs):
        payload = json.loads(kwargs["input"])
        assert command[-1].endswith("hyperframes_scene_cli.py")
        assert payload["duration_sec"] == 4.0
        assert payload["blueprint_id"] == "proof_ffprobe_dashboard"
        assert payload["visual_archetype"] == "ffprobe_dashboard"
        assert payload["asset_recipe_id"] == "ffprobe_terminal_capture"
        assert payload["transition_plan"] == {"family": "terminal-scan"}
        assert payload["motion_intent"] == {
            "motion_rule_ids": ["hacker-flip-3d", "asr-keyword-glow"]
        }
        assert payload["expected_real_evidence"] == ["ffprobe", "QA"]
        assert payload["evidence_asset_refs"] == [
            {"id": "ev-1", "type": "ffprobe_terminal_capture"}
        ]
        expected_path = payload["expected_asset_path"]
        with open(expected_path, "wb") as handle:
            handle.write(b"MP4")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "asset_path": expected_path,
                    "host_generation_contract": {
                        "adapter": "lingjian_hyperframes_director",
                        "blueprint_id": "proof_ffprobe_dashboard",
                        "visual_archetype": "ffprobe_dashboard",
                        "asset_recipe_id": "ffprobe_terminal_capture",
                        "material_key": None,
                        "layout_signature": "ffprobe_dashboard",
                        "transition_family": "terminal-scan",
                        "motion_rule_ids": ["hacker-flip-3d", "asr-keyword-glow"],
                        "keyframe_count": 0,
                        "keyframe_state_count": 0,
                        "evidence_ref_count": 1,
                        "evidence_media_count": 0,
                        "contract_confirmed_by_generator": True,
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("packages.core.visual_generation.run_subprocess", fake_run)

    scene = ensure_scene_asset(
        project,
        {
            "scene_id": "s1",
            "generator": "hyperframes",
            "expected_asset_path": "assets/scenes/s1.mp4",
            "visual_prompt": "中文短视频动态画面",
            "duration_sec": 4.0,
            "blueprint_id": "proof_ffprobe_dashboard",
            "visual_archetype": "ffprobe_dashboard",
            "asset_recipe_id": "ffprobe_terminal_capture",
            "transition_plan": {"family": "terminal-scan"},
            "motion_intent": {
                "motion_rule_ids": ["hacker-flip-3d", "asr-keyword-glow"]
            },
            "expected_real_evidence": ["ffprobe", "QA"],
            "evidence_asset_refs": [
                {"id": "ev-1", "type": "ffprobe_terminal_capture"}
            ],
        },
    )

    assert expected.exists()
    assert scene["generation_status"] == "generated"
    assert scene["asset_path"] == "assets/scenes/s1.mp4"
    assert scene["asset_origin"] == "lingjian_hyperframes_director"
    assert scene["host_generation_contract"] == {
        "adapter": "lingjian_hyperframes_director",
        "blueprint_id": "proof_ffprobe_dashboard",
        "visual_archetype": "ffprobe_dashboard",
        "asset_recipe_id": "ffprobe_terminal_capture",
        "material_key": None,
        "layout_signature": "ffprobe_dashboard",
        "transition_family": "terminal-scan",
        "motion_rule_ids": ["hacker-flip-3d", "asr-keyword-glow"],
        "keyframe_count": 0,
        "keyframe_state_count": 0,
        "evidence_ref_count": 1,
        "evidence_media_count": 0,
        "contract_confirmed_by_generator": True,
    }
    sidecar = expected.with_name("s1.mp4.host_generation_contract.json")
    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["asset_path"] == "assets/scenes/s1.mp4"
    assert sidecar_payload["asset_origin"] == "lingjian_hyperframes_director"
    assert (
        sidecar_payload["host_generation_contract"]["contract_confirmed_by_generator"]
        is True
    )


def test_host_visual_asset_duration_uses_scene_duration_without_short_loop():
    assert _host_visual_asset_duration(6.0) == 6.0
    assert _host_visual_asset_duration(18.0) == 12.0
    assert _host_visual_asset_duration(0.2) == 0.8
    assert _host_visual_asset_duration("bad") == 1.0


def test_host_visual_generation_does_not_confirm_empty_returned_contract(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    project.path.mkdir()
    expected = project.path / "assets" / "scenes" / "s1.mp4"

    monkeypatch.setattr("packages.core.visual_generation._npx_hyperframes_available", lambda: True)

    def fake_run(command, **kwargs):
        payload = json.loads(kwargs["input"])
        expected_path = payload["expected_asset_path"]
        with open(expected_path, "wb") as handle:
            handle.write(b"MP4")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "asset_path": expected_path,
                    "host_generation_contract": {},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("packages.core.visual_generation.run_subprocess", fake_run)

    scene = ensure_scene_asset(
        project,
        {
            "scene_id": "s1",
            "generator": "hyperframes",
            "expected_asset_path": "assets/scenes/s1.mp4",
            "duration_sec": 4.0,
            "blueprint_id": "proof_ffprobe_dashboard",
            "visual_archetype": "ffprobe_dashboard",
            "asset_recipe_id": "ffprobe_terminal_capture",
        },
    )

    assert expected.exists()
    assert scene["generation_status"] == "generated"
    assert scene["host_generation_contract"]["contract_confirmed_by_generator"] is False


def test_hyperframes_existing_host_asset_without_contract_is_regenerated(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    project.path.mkdir()
    expected = project.path / "assets" / "scenes" / "s1.mp4"
    expected.parent.mkdir(parents=True)
    expected.write_bytes(b"OLD")
    monkeypatch.setattr("packages.core.visual_generation._npx_hyperframes_available", lambda: True)

    def fake_run(command, **kwargs):
        payload = json.loads(kwargs["input"])
        expected_path = payload["expected_asset_path"]
        with open(expected_path, "wb") as handle:
            handle.write(b"NEW")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "asset_path": expected_path,
                    "host_generation_contract": {
                        "adapter": "lingjian_hyperframes_director",
                        "blueprint_id": "hook_codex_prompt",
                        "layout_signature": "hook",
                        "contract_confirmed_by_generator": True,
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("packages.core.visual_generation.run_subprocess", fake_run)

    scene = ensure_scene_asset(
        project,
        {
            "scene_id": "s1",
            "generator": "hyperframes",
            "expected_asset_path": "assets/scenes/s1.mp4",
            "duration_sec": 3.0,
            "blueprint_id": "hook_codex_prompt",
        },
    )

    assert expected.read_bytes() == b"NEW"
    assert scene["generation_status"] == "generated"
    assert scene["host_generation_contract"]["contract_confirmed_by_generator"] is True


def test_hyperframes_existing_host_asset_with_contract_is_reused(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    project.path.mkdir()
    expected = project.path / "assets" / "scenes" / "s1.mp4"
    expected.parent.mkdir(parents=True)
    expected.write_bytes(b"OLD")
    monkeypatch.setattr("packages.core.visual_generation._npx_hyperframes_available", lambda: True)

    def fake_run(command, **kwargs):
        raise AssertionError("confirmed host asset should not be regenerated")

    monkeypatch.setattr("packages.core.visual_generation.run_subprocess", fake_run)

    scene = ensure_scene_asset(
        project,
        {
            "scene_id": "s1",
            "generator": "hyperframes",
            "expected_asset_path": "assets/scenes/s1.mp4",
            "host_generation_contract": {"contract_confirmed_by_generator": True},
        },
    )

    assert expected.read_bytes() == b"OLD"
    assert scene["generation_status"] == "existing"


def test_hyperframes_existing_host_asset_with_sidecar_contract_is_reused(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    project.path.mkdir()
    expected = project.path / "assets" / "scenes" / "s1.mp4"
    expected.parent.mkdir(parents=True)
    expected.write_bytes(b"OLD")
    expected.with_name("s1.mp4.host_generation_contract.json").write_text(
        json.dumps(
            {
                "asset_path": "assets/scenes/s1.mp4",
                "asset_origin": "lingjian_hyperframes_director",
                "host_generation_contract": {
                    "adapter": "lingjian_hyperframes_director",
                    "blueprint_id": "hook_codex_prompt",
                    "layout_signature": "hook",
                    "contract_confirmed_by_generator": True,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.visual_generation._npx_hyperframes_available", lambda: True)

    def fake_run(command, **kwargs):
        raise AssertionError("sidecar-confirmed host asset should not be regenerated")

    monkeypatch.setattr("packages.core.visual_generation.run_subprocess", fake_run)

    scene = ensure_scene_asset(
        project,
        {
            "scene_id": "s1",
            "generator": "hyperframes",
            "expected_asset_path": "assets/scenes/s1.mp4",
        },
    )

    assert expected.read_bytes() == b"OLD"
    assert scene["generation_status"] == "existing"
    assert scene["asset_origin"] == "lingjian_hyperframes_director"
    assert scene["host_generation_contract"]["contract_confirmed_by_generator"] is True


def test_hyperframes_scene_layouts_are_deterministic_and_varied():
    payloads = [
        {"scene_id": str(index), "visual_prompt": f"第{index}镜视觉提示", "duration_sec": 1.0}
        for index in range(1, 6)
    ]

    layouts = [_layout_for(payload) for payload in payloads]

    assert layouts == ["hook", "pain", "solution", "proof", "cta"]
    assert _layout_for(payloads[2]) == _layout_for(payloads[2])
    assert 'class="scene layout-hook"' in _html(payloads[0], 1.0)
    assert 'class="scene layout-solution"' in _html(payloads[2], 1.0)
    assert "repo-card" in _html(payloads[0], 1.0)
    assert "workflow" in _html(payloads[2], 1.0)


def test_hyperframes_scene_html_uses_product_demo_surfaces_not_default_gradient():
    rendered = _html(
        {"scene_id": "5", "visual_prompt": "灵剪开源项目 Star", "duration_sec": 4.0},
        4.0,
    )

    assert "github" in rendered
    assert "dososo / blcaptain-lingjian-video" in rendered
    assert "radial-gradient" not in rendered
    assert "LingJian × HyperFrames" not in rendered


def test_hyperframes_scene_html_honors_landscape_ratio_and_bundled_fonts():
    rendered = _html(
        {
            "scene_id": "s1",
            "brief": {"aspect": "16:9"},
            "visual_prompt": "横屏产品介绍",
            "duration_sec": 4.0,
        },
        4.0,
    )

    assert 'data-resolution="landscape"' in rendered
    assert 'content="width=1920, height=1080"' in rendered
    assert 'data-width="1920" data-height="1080"' in rendered
    assert "@font-face" in rendered
    assert "SourceHanSansSC-Medium.otf" in rendered
    assert "GlowSansSC-ExtraBold.otf" in rendered
    assert 'class="clip stage-grid"' in rendered
    assert 'data-track-index="0"' in rendered
    assert "gsap.timeline({ paused: true" in rendered
    assert 'window.__timelines["s1"]' in rendered
    assert "animation: none !important" in rendered
    assert "PingFang" not in rendered
    assert "Noto Sans CJK" not in rendered
    assert "SFMono" not in rendered
    assert "Menlo" not in rendered
    assert "ui-monospace" not in rendered


def test_hyperframes_scene_role_layouts_keep_adjacent_feature_and_proof_distinct():
    assert _layout_for({"scene_id": "4", "role": "feature"}) == "hook"
    assert _layout_for({"scene_id": "5", "role": "proof"}) == "proof"
    assert _layout_for({"scene_id": "6", "role": "cta"}) == "cta"


def test_hyperframes_scene_consumes_director_contract_metadata():
    payload = {
        "scene_id": "1",
        "role": "hook",
        "visual_prompt": "灵剪 strict QA 证据画面",
        "blueprint_id": "proof_ffprobe_dashboard",
        "visual_archetype": "ffprobe_dashboard",
        "asset_recipe_id": "ffprobe_terminal_capture",
        "transition_plan": {"family": "terminal-scan"},
        "motion_intent": {"motion_rule_ids": ["hacker-flip-3d", "asr-keyword-glow"]},
        "expected_real_evidence": ["ffprobe", "QA"],
        "evidence_asset_refs": [{"id": "ev-1", "type": "qa_report_capture"}],
        "director_board": {
            "visual_content": "ffprobe 输出和 QA 结果组成证据仪表盘。"
        },
    }

    rendered = _html(payload, 4.0)

    assert _layout_for(payload) == "proof"
    assert 'class="scene layout-proof"' in rendered
    assert 'data-blueprint-id="proof_ffprobe_dashboard"' in rendered
    assert 'data-asset-recipe-id="ffprobe_terminal_capture"' in rendered
    assert 'data-transition-family="terminal-scan"' in rendered
    assert 'data-motion-rules="hacker-flip-3d,asr-keyword-glow"' in rendered
    assert 'data-evidence-count="3"' in rendered
    assert "ffprobe 终端证据" in rendered
    assert "证据:ffprobe / QA" in rendered
    assert "ffprobe输出和QA结果" in rendered


def test_hyperframes_adapter_contract_reports_keyframe_execution_counts():
    contract = _adapter_contract(
        {
            "blueprint_id": "hook_codex_prompt",
            "visual_archetype": "hook",
            "asset_recipe_id": "github_readme_capture",
            "keyframes": [
                {"time_sec": 0.0, "state": "Codex 提示词窗口入场。"},
                {"time_sec": 2.0, "state": "README 安装入口放大。"},
                {"time_sec": 3.7, "state": "Star CTA 聚焦收束。"},
            ],
        },
        [],
    )

    assert contract["keyframe_count"] == 3
    assert contract["keyframe_state_count"] == 3
    assert contract["contract_confirmed_by_generator"] is True


def test_hyperframes_adapter_contract_marks_video_evidence_as_primary_visual():
    contract = _adapter_contract(
        {
            "blueprint_id": "proof_qa_evidence_wall",
            "visual_archetype": "proof",
            "asset_recipe_id": "qa_report_capture",
            "evidence_asset_refs": [{"id": "ev-1", "type": "qa_report_capture"}],
        },
        [
            {
                "kind": "video",
                "src": "assets/evidence_media/evidence-1.mp4",
                "label": "QA 报告",
                "evidence_type": "qa_report_capture",
            }
        ],
    )

    assert contract["evidence_media_hero_kind"] == "video"
    assert contract["evidence_media_hero_role"] == "primary_visual"
    assert contract["template_body_suppressed_for_evidence"] is True


def test_hyperframes_scene_embeds_evidence_media_in_html():
    payload = {
        "scene_id": "3",
        "visual_prompt": "灵剪 QA 证据画面",
        "blueprint_id": "proof_qa_evidence_wall",
        "asset_recipe_id": "qa_report_capture",
        "evidence_asset_refs": [
            {
                "id": "qa-video",
                "type": "qa_report_capture",
                "evidence_clip_path": "assets/evidence/videos/qa-report.mp4",
                "label": "QA 报告",
            }
        ],
    }

    rendered = _html(
        payload,
        4.0,
        evidence_media=[
            {
                "kind": "video",
                "src": "assets/evidence_media/evidence-1.mp4",
                "label": "QA 报告",
                "evidence_type": "qa_report_capture",
            }
        ],
    )

    assert 'data-evidence-media-count="1"' in rendered
    assert 'data-evidence-hero-kind="video"' in rendered
    assert 'class="evidence-hero"' in rendered
    assert 'class="evidence-story"' in rendered
    assert 'aria-label="真实动态证据主画面"' in rendered
    assert '<video src="assets/evidence_media/evidence-1.mp4"' in rendered
    assert "真实视频证据" in rendered
    assert 'data-evidence-type="qa_report_capture"' in rendered
    assert "QA 报告" in rendered
    assert '<section class="dashboard"' not in rendered
    assert '<section class="repo-card"' not in rendered
    assert '<section class="phone"' not in rendered


def test_hyperframes_scene_keeps_static_evidence_media_out_of_hero():
    payload = {
        "scene_id": "4",
        "visual_prompt": "灵剪 README 参考图",
        "blueprint_id": "proof_qa_evidence_wall",
        "asset_recipe_id": "readme_install_capture",
        "evidence_asset_refs": [
            {
                "id": "readme-image",
                "type": "readme_install_entry",
                "evidence_clip_path": "assets/reference_images/readme.png",
                "label": "README 参考图",
            }
        ],
    }

    rendered = _html(
        payload,
        4.0,
        evidence_media=[
            {
                "kind": "image",
                "src": "assets/evidence_media/evidence-1.png",
                "label": "README 参考图",
                "evidence_type": "readme_install_entry",
            }
        ],
    )

    assert 'data-evidence-media-count="1"' in rendered
    assert 'data-evidence-hero-kind=""' in rendered
    assert 'class="evidence-hero"' not in rendered
    assert 'class="evidence-story"' not in rendered
    assert '<img src="assets/evidence_media/evidence-1.png"' in rendered


def test_hyperframes_scene_visual_text_does_not_repeat_full_narration():
    narration = "找素材、配音、对字幕、导竖屏,一条抖音视频要来回折腾好几个小时。"
    payload = {
        "scene_id": "2",
        "visual_prompt": (
            "为竖屏短视频生成一镜画面。画幅 9:16,风格为干净的中文产品说明动态图形,"
            f"主体清晰,背景简洁。旁白/画面信息:{narration}"
        ),
        "narration_text": narration,
        "duration_sec": 1.0,
    }

    keyword = _visual_keyword(payload)
    rendered = _html(payload, 1.0)

    assert 0 < len(keyword) <= 8
    assert narration not in rendered
    assert "旁白/画面信息" not in rendered


def test_hyperframes_scene_html_does_not_expose_raw_motion_primitive():
    payload = {
        "scene_id": "3",
        "visual_prompt": "灵剪发布级画面验收",
        "motion_spec": {"main": "kinetic_pan", "one_main_only": True},
        "duration_sec": 1.0,
    }

    rendered = _html(payload, 1.0)

    assert "kinetic_pan" not in rendered
    assert "kinetic" not in rendered
    assert "kenburns_zoom_in" not in rendered


def test_strict_release_qa_blocks_kokoro_sample_tts(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "kokoro_zh_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_IS_PREVIEW_VOICE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_missing_voice_plan(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project, write_voice_plan=False)
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_VOICE_PLAN_MISSING"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_stock_image_without_user_consent_or_license(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 8.0,
                "render_source": "video",
                "asset_origin": "free_stock_library",
                "asset_strategy_v2": {
                    "current_asset_kind": "stock_image",
                    "stock_image_policy": {
                        "used": True,
                        "sources": [
                            {
                                "source": "Unsplash",
                                "sourceUrl": "https://unsplash.com/photos/example",
                                "license": "Unsplash License",
                                "license_verification_status": "UNVERIFIED",
                            }
                        ],
                    },
                },
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)
    codes = {issue.code for issue in report.hard_failures}

    assert "RELEASE_STOCK_IMAGE_USER_CONSENT_MISSING" in codes
    assert "RELEASE_STOCK_IMAGE_LICENSE_NOT_VERIFIABLE" in codes
    blockers = report.metadata["remaining_stock_image_blockers"]
    assert {blocker["issue_code"] for blocker in blockers} >= {
        "RELEASE_STOCK_IMAGE_USER_CONSENT_MISSING",
        "RELEASE_STOCK_IMAGE_LICENSE_NOT_VERIFIABLE",
    }
    qa_markdown = (project.path / "artifacts" / "qa_report.md").read_text(encoding="utf-8")
    assert "免费图库配图恢复建议" in qa_markdown


def test_strict_release_qa_rejects_stock_image_as_real_evidence(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 8.0,
                "render_source": "video",
                "requires_real_evidence_asset": True,
                "expected_real_evidence": ["Codex 操作录屏"],
                "asset_strategy_v2": {
                    "current_asset_kind": "stock_image",
                    "stock_image_policy": {
                        "used": True,
                        "user_consent_status": "confirmed",
                        "selected_source": {
                            "source": "cc0.cn",
                            "sourceUrl": "https://cc0.cn/example",
                            "license": "CC0",
                            "license_verification_status": "verified",
                        },
                    },
                },
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)
    codes = {issue.code for issue in report.hard_failures}

    assert "RELEASE_STOCK_IMAGE_USER_CONSENT_MISSING" not in codes
    assert "RELEASE_STOCK_IMAGE_LICENSE_NOT_VERIFIABLE" not in codes
    assert "RELEASE_STOCK_IMAGE_CANNOT_SATISFY_REAL_EVIDENCE" in codes


def test_strict_release_qa_blocks_unverifiable_voice_plan_source(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    voice_path = project.path / "artifacts" / "voice_plan.json"
    voice_path.write_text(
        json.dumps(
            {
                "provider_id": "volcengine_tts",
                "provider_is_mock": False,
                "voice_id": "zh_female_vv_uranus_bigtts",
                "provider_voice_settings": {"speaker": "zh_female_vv_uranus_bigtts"},
                "segments": [
                    {
                        "scene_id": "s1",
                        "duration_sec": 1.0,
                        "voice_id": "zh_female_vv_uranus_bigtts",
                        "provider_voice_settings": {
                            "speaker": "zh_female_vv_uranus_bigtts"
                        },
                    }
                ],
                "total_duration_sec": 1.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_VOICE_PLAN_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_voice_plan_source_without_audio_stream(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)

    def fake_media_streams(path):
        if path.name == "full.wav":
            return False, False
        return True, True

    monkeypatch.setattr("packages.core.qa._media_streams_are_verifiable", fake_media_streams)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_VOICE_PLAN_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_unverifiable_voice_plan_audio_duration(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)

    def fake_duration(path):
        if path.name == "full.wav":
            return None
        return 8.0

    monkeypatch.setattr("packages.core.qa._media_duration_sec", fake_duration)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_VOICE_PLAN_AUDIO_DURATION_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_voice_plan_audio_duration_mismatch(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)

    def fake_duration(path):
        if path.name == "full.wav":
            return 2.0
        return 8.0

    monkeypatch.setattr("packages.core.qa._media_duration_sec", fake_duration)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_VOICE_PLAN_AUDIO_DURATION_MISMATCH"
        for issue in report.hard_failures
    )


def test_strict_release_qa_allows_matching_voice_plan_audio_duration(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VOICE_PLAN_AUDIO_DURATION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_VOICE_PLAN_AUDIO_DURATION_MISMATCH" not in codes


def test_strict_release_qa_blocks_missing_voice_plan_segment_duration(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    voice_path = project.path / "artifacts" / "voice_plan.json"
    voice_plan = json.loads(voice_path.read_text(encoding="utf-8"))
    voice_plan["segments"][0].pop("duration_sec")
    voice_path.write_text(json.dumps(voice_plan, ensure_ascii=False), encoding="utf-8")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_VOICE_PLAN_SEGMENT_DURATION_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_voice_plan_segment_duration_mismatch(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    voice_path = project.path / "artifacts" / "voice_plan.json"
    voice_plan = json.loads(voice_path.read_text(encoding="utf-8"))
    voice_plan["segments"] = [
        {
            "scene_id": "s1",
            "audio_path": "artifacts/voice_segments/full.wav",
            "duration_sec": 2.0,
            "voice_id": voice_plan["voice_id"],
            "provider_voice_settings": voice_plan["provider_voice_settings"],
        },
        {
            "scene_id": "s2",
            "duration_sec": 2.0,
            "voice_id": voice_plan["voice_id"],
            "provider_voice_settings": voice_plan["provider_voice_settings"],
        },
    ]
    voice_plan["total_duration_sec"] = 8.0
    voice_path.write_text(json.dumps(voice_plan, ensure_ascii=False), encoding="utf-8")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_VOICE_PLAN_SEGMENT_DURATION_MISMATCH"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_unverifiable_voice_settings(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    voice_path = project.path / "artifacts" / "voice_plan.json"
    voice_path.parent.mkdir(parents=True, exist_ok=True)
    voice_path.write_text(
        json.dumps(
            {
                "provider_id": "volcengine_tts",
                "provider_is_mock": False,
                "voice_id": "zh_female_vv_uranus_bigtts",
                "provider_voice_settings": {"speaker": "zh_female_vv_uranus_bigtts"},
                "segments": [
                    {
                        "scene_id": "s1",
                        "duration_sec": 1.0,
                    }
                ],
                "total_duration_sec": 1.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_VOICE_SETTINGS_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_inconsistent_voice_settings(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    voice_path = project.path / "artifacts" / "voice_plan.json"
    voice_path.parent.mkdir(parents=True, exist_ok=True)
    voice_path.write_text(
        json.dumps(
            {
                "provider_id": "volcengine_tts",
                "provider_is_mock": False,
                "voice_id": "zh_female_vv_uranus_bigtts",
                "provider_voice_settings": {"speaker": "zh_female_vv_uranus_bigtts"},
                "segments": [
                    {
                        "scene_id": "s1",
                        "duration_sec": 1.0,
                        "voice_id": "zh_female_vv_uranus_bigtts",
                        "provider_voice_settings": {
                            "speaker": "zh_female_vv_uranus_bigtts"
                        },
                    },
                    {
                        "scene_id": "s2",
                        "duration_sec": 1.0,
                        "voice_id": "zh_male_other_bigtts",
                        "provider_voice_settings": {"speaker": "zh_male_other_bigtts"},
                    },
                ],
                "total_duration_sec": 2.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_VOICE_SETTINGS_INCONSISTENT"
        for issue in report.hard_failures
    )


def test_release_qa_allows_consistent_voice_settings(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    voice_path = project.path / "artifacts" / "voice_plan.json"
    voice_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path = project.path / "artifacts" / "voice_segments" / "full.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"voice")
    settings = {"speaker": "zh_female_vv_uranus_bigtts", "sample_rate": 24000}
    voice_path.write_text(
        json.dumps(
            {
                "provider_id": "volcengine_tts",
                "provider_is_mock": False,
                "voice_id": "zh_female_vv_uranus_bigtts",
                "provider_voice_settings": settings,
                "segments": [
                    {
                        "scene_id": "s1",
                        "duration_sec": 4.0,
                        "voice_id": "zh_female_vv_uranus_bigtts",
                        "provider_voice_settings": settings,
                    },
                    {
                        "scene_id": "s2",
                        "duration_sec": 4.0,
                        "voice_id": "zh_female_vv_uranus_bigtts",
                        "provider_voice_settings": settings,
                    },
                ],
                "full_audio_path": "artifacts/voice_segments/full.wav",
                "total_duration_sec": 8.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VOICE_PLAN_MISSING" not in codes
    assert "RELEASE_VOICE_PLAN_NOT_VERIFIABLE" not in codes
    assert "RELEASE_VOICE_SETTINGS_NOT_VERIFIABLE" not in codes
    assert "RELEASE_VOICE_SETTINGS_INCONSISTENT" not in codes


def test_strict_release_qa_blocks_unverifiable_bgm_mix(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "audio_mix": _audio_mix_with_output(
                    project, {"rendered": True, "bgm_present": True}
                ),
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_MIX_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_bgm_over_voice(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "audio_mix": _audio_mix_with_output(
                    project,
                    {"rendered": True, "bgm_present": True, "bgm_to_voice_db": -6},
                ),
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_BGM_OVER_VOICE" for issue in report.hard_failures)


def test_strict_release_qa_blocks_unrendered_bgm_mix(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        audio_mix={
            "rendered": False,
            "bgm_present": True,
            "bgm_to_voice_db": -16.0,
        },
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_AUDIO_MIX_NOT_RENDERED" for issue in report.hard_failures)


def test_strict_release_qa_blocks_declared_bgm_without_mix(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "bgm": "克制科技感 BGM,人声优先,BGM 比人声低 16dB",
            }
        ],
        audio_mix={
            "rendered": True,
            "bgm_present": False,
            "sfx_count": 0,
        },
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_BGM_DECLARED_BUT_NOT_RENDERED"
        for issue in report.hard_failures
    )


def test_release_qa_surfaces_audio_asset_blockers_when_manifest_stale(tmp_path):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[{"scene_id": "s1", "duration_sec": 3.0}],
        visual_plan_sha256="old-visual-plan",
    )
    _write_voice_plan_caption_cues(
        project,
        [
            {
                "text": "一句话触发灵剪",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "source": "voice_duration_aligned",
                "timing_basis": "real_segment_duration",
            }
        ],
    )
    artifacts = project.path / "artifacts"
    visual_plan = {
        "scenes": [
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "director_review_sheet_v2": {
                    "bgm": "科技感轻节奏 BGM,人声优先,BGM 比人声低 16dB",
                    "sfx_points": "轻微点击音 + 结果落定提示音。",
                },
            }
        ]
    }
    (artifacts / "visual_plan.json").write_text(
        json.dumps(visual_plan, ensure_ascii=False),
        encoding="utf-8",
    )

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_RENDER_MANIFEST_STALE" in codes
    assert "RELEASE_AUDIO_ASSET_BLOCKERS_REMAIN" in codes
    blockers = report.metadata["remaining_audio_asset_blockers"]
    assert [blocker["kind"] for blocker in blockers] == ["bgm", "sfx"]
    assert blockers[0]["scene_ids"] == ["s1"]
    assert blockers[0]["expected_audio_asset"] == "voice_plan.audio_assets.bgm.path"
    assert blockers[0]["first_command"].startswith("uv run lj ingest audio ")
    assert "--kind bgm" in blockers[0]["first_command"]
    assert "--bgm-to-voice-db -16" in blockers[0]["first_command"]
    assert blockers[0]["suggested_commands"][0]["command"] == blockers[0]["first_command"]
    assert blockers[1]["scene_id"] == "s1"
    assert blockers[1]["expected_audio_asset"] == "voice_plan.audio_assets.sfx[]"
    assert blockers[1]["first_command"].startswith("uv run lj ingest audio ")
    assert "--kind sfx" in blockers[1]["first_command"]
    assert "--scene-id s1" in blockers[1]["first_command"]
    assert "--at-sec 0.5" in blockers[1]["first_command"]
    assert "--gain-db -12" in blockers[1]["first_command"]
    assert "--action" in blockers[1]["first_command"]
    assert blockers[1]["suggested_commands"][0]["command"] == blockers[1]["first_command"]
    qa_markdown = (artifacts / "qa_report.md").read_text(encoding="utf-8")
    assert "BGM/SFX 声音素材恢复建议" in qa_markdown
    assert "voice_plan.audio_assets.bgm.path" in qa_markdown
    assert "voice_plan.audio_assets.sfx[]" in qa_markdown
    assert "uv run lj ingest audio" in qa_markdown


def test_strict_release_qa_allows_optional_bgm_without_mix(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "director_review_sheet_v2": {
                    "bgm": "极轻 BGM 或无 BGM,清晰口播优先",
                },
            }
        ],
        audio_mix={
            "rendered": True,
            "bgm_present": False,
            "sfx_count": 0,
        },
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_BGM_DECLARED_BUT_NOT_RENDERED" not in codes


def test_strict_release_qa_blocks_unrendered_sfx_mix(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[{"scene_id": "s1", "duration_sec": 3.0}],
        audio_mix={
            "rendered": False,
            "bgm_present": False,
            "sfx_count": 1,
            "sfx_density_per_10_sec": 1.0,
            "sfx_events": [
                {
                    "path": "assets/audio/click.wav",
                    "at_sec": 1.2,
                    "gain_db": -12.0,
                    "scene_id": "s1",
                    "action": "按钮落定",
                }
            ],
        },
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_AUDIO_MIX_NOT_RENDERED" for issue in report.hard_failures)


def test_strict_release_qa_blocks_unverifiable_audio_mix_output(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        audio_mix={
            "rendered": True,
            "bgm_present": True,
            "bgm_to_voice_db": -16.0,
            "mixed_audio_path": "renders/release/douyin/missing.m4a",
        },
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_MIX_OUTPUT_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_release_qa_allows_rendered_bgm_mix(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    bgm_path = _audio_source_asset(project, "assets/audio/bgm.wav")
    _write_minimal_release_manifest(
        project,
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": True,
                "bgm_path": bgm_path,
                "bgm_to_voice_db": -16.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_AUDIO_MIX_NOT_RENDERED" not in codes
    assert "RELEASE_BGM_OVER_VOICE" not in codes


def test_strict_release_qa_blocks_unverifiable_bgm_source_asset(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": True,
                "bgm_path": "assets/audio/missing-bgm.wav",
                "bgm_to_voice_db": -16.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_BGM_ASSET_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_release_qa_warns_unverifiable_bgm_source_asset_in_non_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": True,
                "bgm_path": "assets/audio/missing-bgm.wav",
                "bgm_to_voice_db": -16.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_BGM_ASSET_NOT_VERIFIABLE"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_audio_mix_duration_mismatch(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        expected_duration_sec=8.0,
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": True,
                "bgm_to_voice_db": -16.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._media_duration_sec",
        lambda path: 2.0 if path.name == "mixed_audio.m4a" else 8.0,
    )

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_MIX_DURATION_MISMATCH"
        for issue in report.hard_failures
    )


def test_release_qa_warns_audio_mix_duration_mismatch_in_non_strict(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        expected_duration_sec=8.0,
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": True,
                "bgm_to_voice_db": -16.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._media_duration_sec",
        lambda path: 2.0 if path.name == "mixed_audio.m4a" else 8.0,
    )

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_AUDIO_MIX_DURATION_MISMATCH"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_unverifiable_audio_mix_duration(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        expected_duration_sec=8.0,
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": True,
                "bgm_to_voice_db": -16.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._media_duration_sec",
        lambda path: None if path.name == "mixed_audio.m4a" else 8.0,
    )

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_MIX_DURATION_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_release_qa_allows_audio_mix_duration_matching_expected(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    bgm_path = _audio_source_asset(project, "assets/audio/bgm.wav")
    _write_minimal_release_manifest(
        project,
        expected_duration_sec=8.0,
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": True,
                "bgm_path": bgm_path,
                "bgm_to_voice_db": -16.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 8.2)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_AUDIO_MIX_DURATION_MISMATCH" not in codes
    assert "RELEASE_AUDIO_MIX_DURATION_NOT_VERIFIABLE" not in codes


def test_strict_release_qa_blocks_unverifiable_sfx_density(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "audio_mix": _audio_mix_with_output(
                    project,
                    {"rendered": True, "bgm_present": False, "sfx_count": 1},
                ),
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SFX_DENSITY_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_over_dense_sfx(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "audio_mix": _audio_mix_with_output(
                    project,
                    {
                        "rendered": True,
                        "bgm_present": False,
                        "sfx_count": 8,
                        "sfx_density_per_10_sec": 8.0,
                    },
                ),
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
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
    assert any(issue.code == "RELEASE_SFX_TOO_DENSE" for issue in report.hard_failures)


def test_strict_release_qa_blocks_sfx_without_action_anchor(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": "assets/audio/click.wav",
                        "at_sec": 1.2,
                        "gain_db": -12.0,
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SFX_ACTION_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_allows_sfx_with_action_anchor(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    sfx_path = _audio_source_asset(project, "assets/audio/click.wav")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "visual_events": [
                    {
                        "cue_id": "cta-lock",
                        "action": "按钮落定",
                        "time_sec": 1.2,
                    }
                ],
            }
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": sfx_path,
                        "at_sec": 1.2,
                        "gain_db": -12.0,
                        "scene_id": "s1",
                        "cue_id": "cta-lock",
                        "action": "按钮落定",
                        "purpose": "强化 CTA 出现",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SFX_ACTION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SFX_TIMING_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SFX_VISUAL_ACTION_UNMATCHED" not in codes


def test_strict_release_qa_blocks_sfx_visual_action_timing_mismatch(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    sfx_path = _audio_source_asset(project, "assets/audio/click.wav")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "visual_events": [
                    {
                        "cue_id": "cta-lock",
                        "action": "按钮落定",
                        "time_sec": 1.4,
                    }
                ],
            }
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": sfx_path,
                        "at_sec": 0.2,
                        "gain_db": -12.0,
                        "scene_id": "s1",
                        "cue_id": "cta-lock",
                        "action": "按钮落定",
                        "purpose": "强化 CTA 出现",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SFX_VISUAL_ACTION_TIMING_MISMATCH"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_declared_sfx_without_rendered_event(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "sfx_points": [{"cue_id": "cta-click", "action": "按钮点击"}],
            }
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 0,
                "sfx_density_per_10_sec": 0.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED"
        for issue in report.hard_failures
    )


def test_release_qa_warns_declared_sfx_without_rendered_event_in_non_strict(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "director_review_sheet_v2": {
                    "sfx_points": [{"cue_id": "cta-click", "action": "按钮点击"}],
                },
            }
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 0,
                "sfx_density_per_10_sec": 0.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_declared_missing_audio_assets(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[{"scene_id": "s1", "duration_sec": 3.0}],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": False,
                "bgm_present": False,
                "sfx_count": 0,
                "sfx_density_per_10_sec": 0.0,
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
                        "scene_id": "s1",
                        "reason": "missing_or_unverifiable",
                    },
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_DECLARED_ASSET_MISSING"
        for issue in report.hard_failures
    )


def test_release_qa_warns_declared_missing_audio_assets_without_strict(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[{"scene_id": "s1", "duration_sec": 3.0}],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": False,
                "bgm_present": False,
                "sfx_count": 0,
                "sfx_density_per_10_sec": 0.0,
                "invalid_audio_asset_count": 1,
                "invalid_audio_assets": [
                    {
                        "kind": "bgm",
                        "path": "assets/audio/missing-bgm.wav",
                        "reason": "missing_or_unverifiable",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_AUDIO_DECLARED_ASSET_MISSING"
        for issue in report.warnings
    )


def test_strict_release_qa_allows_optional_sfx_notes_without_rendered_event(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "director_review_sheet_v2": {
                    "sfx_points": ["可无音效,避免抢口播,画面动作自然过渡即可"],
                },
            }
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 0,
                "sfx_density_per_10_sec": 0.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED" not in codes


def test_strict_release_qa_does_not_treat_seamless_sfx_as_optional(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "director_review_sheet_v2": {
                    "sfx_points": ["无缝转场音效"],
                },
            }
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 0,
                "sfx_density_per_10_sec": 0.0,
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED"
        for issue in report.hard_failures
    )


def test_strict_release_qa_allows_declared_sfx_with_rendered_event(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    sfx_path = _audio_source_asset(project, "assets/audio/click.wav")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "sfx_points": [{"cue_id": "cta-click", "action": "按钮点击"}],
            }
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": sfx_path,
                        "at_sec": 1.2,
                        "gain_db": -12.0,
                        "scene_id": "s1",
                        "cue_id": "cta-click",
                        "action": "按钮点击",
                        "purpose": "强调 CTA 按钮落下",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SFX_DECLARED_BUT_NOT_RENDERED" not in codes
    assert "RELEASE_SFX_VISUAL_ACTION_UNMATCHED" not in codes


def test_strict_release_qa_blocks_sfx_unmatched_visual_action_marker(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    sfx_path = _audio_source_asset(project, "assets/audio/click.wav")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "visual_events": [{"cue_id": "cta-lock", "action": "按钮落定"}],
            }
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": sfx_path,
                        "at_sec": 1.2,
                        "gain_db": -12.0,
                        "scene_id": "s1",
                        "cue_id": "unrelated-flash",
                        "action": "无关闪烁",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SFX_VISUAL_ACTION_UNMATCHED"
        for issue in report.hard_failures
    )


def test_release_qa_warns_sfx_unmatched_visual_action_marker_in_non_strict(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    sfx_path = _audio_source_asset(project, "assets/audio/click.wav")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 3.0,
                "visual_events": [{"cue_id": "cta-lock", "action": "按钮落定"}],
            }
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": sfx_path,
                        "at_sec": 1.2,
                        "gain_db": -12.0,
                        "scene_id": "s1",
                        "cue_id": "unrelated-flash",
                        "action": "无关闪烁",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_SFX_VISUAL_ACTION_UNMATCHED"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_sfx_gain_too_loud(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    sfx_path = _audio_source_asset(project, "assets/audio/click.wav")
    _write_minimal_release_manifest(
        project,
        scenes=[{"scene_id": "s1", "duration_sec": 3.0}],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": sfx_path,
                        "at_sec": 1.2,
                        "gain_db": -2.0,
                        "scene_id": "s1",
                        "action": "按钮落定",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_SFX_TOO_LOUD" for issue in report.hard_failures)


def test_release_qa_warns_sfx_gain_too_loud_in_non_strict(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    sfx_path = _audio_source_asset(project, "assets/audio/click.wav")
    _write_minimal_release_manifest(
        project,
        scenes=[{"scene_id": "s1", "duration_sec": 3.0}],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": sfx_path,
                        "at_sec": 1.2,
                        "gain_db": -2.0,
                        "scene_id": "s1",
                        "action": "按钮落定",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(issue.code == "RELEASE_SFX_TOO_LOUD" for issue in report.warnings)


def test_strict_release_qa_blocks_unverifiable_sfx_gain(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    sfx_path = _audio_source_asset(project, "assets/audio/click.wav")
    _write_minimal_release_manifest(
        project,
        scenes=[{"scene_id": "s1", "duration_sec": 3.0}],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": sfx_path,
                        "at_sec": 1.2,
                        "gain_db": "loud",
                        "scene_id": "s1",
                        "action": "按钮落定",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SFX_GAIN_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_unverifiable_sfx_source_asset(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[{"scene_id": "s1", "duration_sec": 3.0}],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": "assets/audio/missing-click.wav",
                        "at_sec": 1.2,
                        "gain_db": -12.0,
                        "scene_id": "s1",
                        "action": "按钮落定",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SFX_ASSET_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_release_qa_warns_unverifiable_sfx_source_asset_in_non_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[{"scene_id": "s1", "duration_sec": 3.0}],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": "assets/audio/missing-click.wav",
                        "at_sec": 1.2,
                        "gain_db": -12.0,
                        "scene_id": "s1",
                        "action": "按钮落定",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_SFX_ASSET_NOT_VERIFIABLE"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_sfx_unknown_scene(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[{"scene_id": "s1", "duration_sec": 3.0}],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": "assets/audio/click.wav",
                        "at_sec": 1.2,
                        "gain_db": -12.0,
                        "scene_id": "s9",
                        "action": "按钮落定",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_SFX_TIMING_NOT_VERIFIABLE" for issue in report.hard_failures)


def test_strict_release_qa_blocks_sfx_outside_bound_scene(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {"scene_id": "s1", "duration_sec": 2.0},
            {"scene_id": "s2", "duration_sec": 2.0},
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": "assets/audio/click.wav",
                        "at_sec": 0.8,
                        "gain_db": -12.0,
                        "scene_id": "s2",
                        "purpose": "强调第二镜按钮",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_SFX_TIMING_NOT_VERIFIABLE" for issue in report.hard_failures)


def test_release_qa_allows_sfx_inside_bound_scene(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    sfx_path = _audio_source_asset(project, "assets/audio/click.wav")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {"scene_id": "s1", "duration_sec": 2.0},
            {"scene_id": "s2", "duration_sec": 2.0},
        ],
        audio_mix=_audio_mix_with_output(
            project,
            {
                "rendered": True,
                "bgm_present": False,
                "sfx_count": 1,
                "sfx_density_per_10_sec": 1.0,
                "sfx_events": [
                    {
                        "path": sfx_path,
                        "at_sec": 2.8,
                        "gain_db": -12.0,
                        "scene_id": "s2",
                        "visual_event": "第二镜 CTA 出现",
                    }
                ],
            },
        ),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SFX_TIMING_NOT_VERIFIABLE" not in codes


def test_release_qa_records_final_audio_volume_stats(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.info}
    assert "RELEASE_AUDIO_VOLUME_STATS" in codes
    assert not any(
        issue.code
        in {
            "RELEASE_AUDIO_VOLUME_NOT_VERIFIABLE",
            "RELEASE_AUDIO_PEAK_TOO_HIGH",
            "RELEASE_AUDIO_TOO_HOT",
            "RELEASE_AUDIO_TOO_QUIET",
        }
        for issue in report.warnings
    )


def test_release_qa_records_final_audio_dynamic_range_stats(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.info}
    assert "RELEASE_AUDIO_DYNAMIC_RANGE_STATS" in codes
    assert not any(
        issue.code
        in {
            "RELEASE_AUDIO_DYNAMIC_RANGE_NOT_VERIFIABLE",
            "RELEASE_AUDIO_DYNAMIC_RANGE_TOO_FLAT",
        }
        for issue in report.warnings
    )


def test_release_qa_records_final_audio_lufs_stats(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.info}
    assert "RELEASE_AUDIO_LUFS_STATS" in codes
    assert not any(
        issue.code
        in {
            "RELEASE_AUDIO_LUFS_NOT_VERIFIABLE",
            "RELEASE_AUDIO_LUFS_TOO_HOT",
            "RELEASE_AUDIO_LUFS_TOO_QUIET",
        }
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_when_final_audio_volume_unverifiable(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._audio_volume_stats", lambda path: None)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_AUDIO_VOLUME_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_when_final_audio_dynamic_range_unverifiable(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._audio_dynamic_stats", lambda path: None)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_AUDIO_DYNAMIC_RANGE_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_when_final_audio_lufs_unverifiable(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._audio_lufs_stats", lambda path: None)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_AUDIO_LUFS_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_when_final_audio_dynamic_range_too_flat(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._audio_dynamic_stats",
        lambda path: {"rms_dynamic_range_db": 1.2, "rms_window_count": 4.0},
    )

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_AUDIO_DYNAMIC_RANGE_TOO_FLAT"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_when_final_audio_lufs_too_hot(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._audio_lufs_stats",
        lambda path: {"integrated_lufs": -8.5},
    )

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_AUDIO_LUFS_TOO_HOT"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_when_final_audio_lufs_too_quiet(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._audio_lufs_stats",
        lambda path: {"integrated_lufs": -31.0},
    )

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_AUDIO_LUFS_TOO_QUIET"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_when_final_audio_peak_too_high(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._audio_volume_stats",
        lambda path: {"mean_volume_db": -12.0, "peak_volume_db": 0.0},
    )

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_AUDIO_PEAK_TOO_HIGH"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_when_final_audio_too_hot(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._audio_volume_stats",
        lambda path: {"mean_volume_db": -8.0, "peak_volume_db": -1.0},
    )

    report = run_qa(project, release=True, strict=True)

    assert any(issue.code == "RELEASE_AUDIO_TOO_HOT" for issue in report.hard_failures)
    assert not any(
        issue.code == "RELEASE_AUDIO_PEAK_TOO_HIGH"
        for issue in report.hard_failures
    )


def test_release_qa_warns_when_final_audio_too_hot_in_non_strict(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._audio_volume_stats",
        lambda path: {"mean_volume_db": -8.0, "peak_volume_db": -1.0},
    )

    report = run_qa(project, release=True, strict=False)

    assert any(issue.code == "RELEASE_AUDIO_TOO_HOT" for issue in report.warnings)
    assert not any(
        issue.code == "RELEASE_AUDIO_TOO_HOT" for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_when_final_audio_too_quiet(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._audio_volume_stats",
        lambda path: {"mean_volume_db": -40.0, "peak_volume_db": -35.0},
    )

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_AUDIO_TOO_QUIET"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_duration_mismatch(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project, expected_duration_sec=8.0)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 3.0)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_DURATION_MISMATCH" for issue in report.hard_failures)


def test_strict_release_qa_blocks_manifest_voice_duration_mismatch(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project, expected_duration_sec=4.0)
    _write_minimal_voice_plan(project, provider_id="volcengine_tts", duration=8.0)
    _patch_release_media_checks_ok(monkeypatch)

    def fake_duration(path):
        if path.name == "full.wav":
            return 8.0
        return 4.0

    monkeypatch.setattr("packages.core.qa._media_duration_sec", fake_duration)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_MANIFEST_VOICE_DURATION_MISMATCH"
        for issue in report.hard_failures
    )
    assert not any(
        issue.code == "RELEASE_DURATION_MISMATCH"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_stale_render_manifest_visual_plan(
    tmp_path,
):
    project = ProjectRef(tmp_path / "project", "project")
    visual_path = project.path / "artifacts" / "visual_plan.json"
    visual_path.parent.mkdir(parents=True, exist_ok=True)
    visual_path.write_text(
        json.dumps(
            {
                "id": "visuals",
                "scenes": [
                    {
                        "scene_id": "s1",
                        "narration_text": "当前分镜已经变更",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _write_minimal_release_manifest(project, visual_plan_sha256="old-render-plan")

    report = run_qa(project, release=True, strict=True)

    codes = [issue.code for issue in report.hard_failures]
    assert "RELEASE_RENDER_MANIFEST_STALE" in codes
    assert "RENDER_NOT_VERIFIABLE" not in codes


def test_release_qa_warns_when_duration_not_verifiable_in_non_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project, expected_duration_sec=8.0)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: None)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(issue.code == "RELEASE_DURATION_NOT_VERIFIABLE" for issue in report.warnings)


def test_release_qa_allows_matching_duration(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project, expected_duration_sec=8.0)
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 8.2)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_DURATION_MISMATCH" not in codes
    assert "RELEASE_DURATION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_MANIFEST_VOICE_DURATION_MISMATCH" not in codes


def test_strict_release_qa_blocks_scene_video_without_motion(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    def fake_motion(path):
        if str(path).endswith("assets/scenes/s1.mp4"):
            return 0.5
        return 12.0

    monkeypatch.setattr("packages.core.qa._sample_frame_motion_delta", fake_motion)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_SCENE_MOTION_NOT_DETECTED"
        for issue in report.hard_failures
    )


def test_release_qa_warns_when_scene_video_without_motion_in_non_strict(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    def fake_motion(path):
        if str(path).endswith("assets/scenes/s1.mp4"):
            return 0.5
        return 12.0

    monkeypatch.setattr("packages.core.qa._sample_frame_motion_delta", fake_motion)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_SCENE_MOTION_NOT_DETECTED"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_scene_video_without_continuous_motion(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_motion_segment_deltas",
        lambda path: [8.0, 0.3],
    )

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_SCENE_MOTION_NOT_CONTINUOUS"
        for issue in report.hard_failures
    )


def test_release_qa_warns_scene_video_without_continuous_motion_in_non_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_motion_segment_deltas",
        lambda path: [8.0, 0.3],
    )

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_SCENE_MOTION_NOT_CONTINUOUS"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_unverifiable_scene_motion_continuity(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_motion_segment_deltas",
        lambda path: None,
    )

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_SCENE_MOTION_CONTINUITY_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_release_qa_allows_scene_video_with_continuous_motion(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_motion_segment_deltas",
        lambda path: [4.0, 5.0],
    )

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SCENE_MOTION_NOT_CONTINUOUS" not in codes
    assert "RELEASE_SCENE_MOTION_CONTINUITY_NOT_VERIFIABLE" not in codes


def test_release_qa_allows_scene_video_with_motion(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SCENE_MOTION_NOT_DETECTED" not in codes
    assert "RELEASE_SCENE_MOTION_NOT_VERIFIABLE" not in codes


def _keyframed_scene() -> dict:
    return {
        "scene_id": "s1",
        "asset_path": "assets/scenes/s1.mp4",
        "render_source": "video",
        "duration_sec": 5.0,
        "keyframes": [
            {"time_sec": 0.0, "state": "开场界面入场。"},
            {"time_sec": 2.2, "state": "中段证据面板展开。"},
            {"time_sec": 4.6, "state": "CTA 收束。"},
        ],
    }


def test_strict_release_qa_blocks_unverifiable_keyframe_motion(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project, scenes=[_keyframed_scene()])
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._sample_keyframe_motion_deltas",
        lambda path, scene: None,
    )

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_SCENE_KEYFRAME_MOTION_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_keyframe_motion_without_pixel_change(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project, scenes=[_keyframed_scene()])
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._sample_keyframe_motion_deltas",
        lambda path, scene: [6.0, 0.2],
    )

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_SCENE_KEYFRAME_MOTION_NOT_DETECTED"
        for issue in report.hard_failures
    )


def test_release_qa_allows_keyframe_motion_with_pixel_change(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project, scenes=[_keyframed_scene()])
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SCENE_KEYFRAME_MOTION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_KEYFRAME_MOTION_NOT_DETECTED" not in codes


def test_strict_release_qa_blocks_scene_video_too_short_for_duration(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 5.0,
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    def fake_duration(path):
        if str(path).endswith("assets/scenes/s1.mp4"):
            return 1.2
        return 5.0

    monkeypatch.setattr("packages.core.qa._media_duration_sec", fake_duration)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_SCENE_VIDEO_TOO_SHORT_FOR_DURATION"
        for issue in report.hard_failures
    )


def test_release_qa_warns_scene_video_too_short_in_non_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 5.0,
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    def fake_duration(path):
        if str(path).endswith("assets/scenes/s1.mp4"):
            return 1.2
        return 5.0

    monkeypatch.setattr("packages.core.qa._media_duration_sec", fake_duration)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_SCENE_VIDEO_TOO_SHORT_FOR_DURATION"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_unverifiable_scene_video_duration(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 5.0,
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: None)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_SCENE_VIDEO_DURATION_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_release_qa_allows_scene_video_duration_covering_scene(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 5.0,
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    def fake_duration(path):
        if str(path).endswith("assets/scenes/s1.mp4"):
            return 4.2
        return 5.0

    monkeypatch.setattr("packages.core.qa._media_duration_sec", fake_duration)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SCENE_VIDEO_TOO_SHORT_FOR_DURATION" not in codes
    assert "RELEASE_SCENE_VIDEO_DURATION_NOT_VERIFIABLE" not in codes


def test_strict_release_qa_blocks_repeated_scene_visual_fingerprint(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
            },
            {
                "scene_id": "s2",
                "asset_path": "assets/scenes/s2.mp4",
                "render_source": "video",
            },
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene 1")
    (project.path / "assets" / "scenes" / "s2.mp4").write_bytes(b"scene 2")
    _patch_release_media_checks_ok(monkeypatch)
    frame = _half_tone_frame()
    monkeypatch.setattr("packages.core.qa._sample_frame_rgb", lambda path, timestamp: frame)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_SCENE_VISUAL_REPEATED"
        for issue in report.hard_failures
    )


def test_release_qa_allows_distinct_scene_visual_fingerprints(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
            },
            {
                "scene_id": "s2",
                "asset_path": "assets/scenes/s2.mp4",
                "render_source": "video",
            },
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene 1")
    (project.path / "assets" / "scenes" / "s2.mp4").write_bytes(b"scene 2")
    _patch_release_media_checks_ok(monkeypatch)

    def fake_frame(path, timestamp):
        if str(path).endswith("assets/scenes/s2.mp4"):
            return _half_tone_frame(inverted=True)
        return _half_tone_frame()

    monkeypatch.setattr("packages.core.qa._sample_frame_rgb", fake_frame)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SCENE_VISUAL_REPEATED" not in codes


def test_strict_release_qa_blocks_lingjian_hyperframes_template_loop(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "asset_origin": "lingjian_hyperframes_template",
                        "render_source": "video",
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "asset_origin": "lingjian_hyperframes_template",
                        "render_source": "video",
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
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
        issue.code == "RELEASE_VISUAL_IS_TEMPLATE_LOOP"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_single_asset_reuse(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/same.mp4",
                        "render_source": "video",
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/same.mp4",
                        "render_source": "video",
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
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
        issue.code == "RELEASE_VISUAL_REUSES_SINGLE_ASSET"
        for issue in report.hard_failures
    )


def test_release_qa_warns_for_static_image_scene_without_strict(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.png",
                        "render_source": "image",
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
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

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_VISUAL_CONTAINS_STATIC_IMAGE"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_different_static_image_scenes(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.png",
                        "render_source": "image",
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.png",
                        "render_source": "image",
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
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
        issue.code == "RELEASE_VISUAL_CONTAINS_STATIC_IMAGE"
        for issue in report.hard_failures
    )
    assert not any(
        issue.code == "RELEASE_VISUAL_REUSES_SINGLE_ASSET"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_non_publish_grade_asset_diagnosis(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "asset_diagnosis": {
                            "asset_status": "reference_only_static_image",
                            "asset_kind": "static_image",
                            "publish_grade_visual": False,
                            "next_action_zh": "请提供这一镜 mp4/mov/m4v 视频素材。",
                        },
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
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
        issue.code == "RELEASE_VISUAL_ASSET_NOT_PUBLISH_GRADE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_missing_director_route_fields(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "generator": "hyperframes",
                        "render_source": "video",
                        "blueprint_id": "hook_codex_prompt",
                        "layout_contract": layout_contract(1, "9:16", "hook"),
                        "motion_intent": {
                            "primary_motions": ["pan"],
                            "develop_full_duration": True,
                        },
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
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
        issue.code == "RELEASE_VISUAL_DIRECTOR_ROUTE_MISSING"
        for issue in report.hard_failures
    )


def _remotion_director_scene(*, confirmed: bool) -> dict:
    route = director_route_policy(
        generator="remotion",
        profile="shipinhao_knowledge",
        platform="douyin",
        blueprint_id="proof_ffprobe_dashboard",
        expected_asset_path="assets/scenes/s1.mp4",
        asset_path="assets/scenes/s1.mp4",
    )
    if confirmed:
        route["engine_policy"]["license_confirmation"] = {"status": "confirmed"}
    return {
        "scene_id": "s1",
        "generator": "remotion",
        "asset_path": "assets/scenes/s1.mp4",
        "render_source": "video",
        "duration_sec": 4.0,
        "narration_text": "用 QA 和 ffprobe 证据说明 Remotion 适合精确图表镜头。",
        "visual_prompt": "QA ffprobe 证据仪表盘和精确图表镜头。",
        "blueprint_id": "proof_ffprobe_dashboard",
        "visual_archetype": "ffprobe_dashboard",
        "asset_recipe_id": "ffprobe_terminal_capture",
        "layout_contract": layout_contract(1, "9:16", "proof"),
        "motion_intent": {
            "primary_motions": ["chart-scan"],
            "develop_full_duration": True,
        },
        "audio_visual_alignment": {
            "status": "aligned",
            "evidence": "人工确认 Remotion 精确图表镜头与 QA/ffprobe 口播匹配。",
        },
        **route,
    }


def test_strict_release_qa_blocks_director_route_mismatch(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    scene = _remotion_director_scene(confirmed=True)
    scene["generator"] = "hyperframes"
    _write_minimal_release_manifest(project, scenes=[scene])
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_VISUAL_DIRECTOR_ROUTE_MISMATCH"
        for issue in report.hard_failures
    )


def test_strict_release_qa_checks_director_review_sheet_v2_only_scene(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "director_review_sheet_v2": {
                    "visual_content": "GitHub README 页面和 Codex 对话触发灵剪流程。",
                    "composition": "左侧 Codex 对话,右侧 GitHub README 证据卡。",
                },
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_VISUAL_DIRECTOR_ROUTE_MISSING"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_insufficient_director_keyframes(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "generator": "user-asset",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "layout_contract": layout_contract(1, "9:16", "proof"),
                "motion_intent": {"primary_motions": ["pan"], "develop_full_duration": True},
                "engine_policy": {"selected_engine": "user_video"},
                "route_reason": "用户提供真实动态视频素材,灵剪负责字幕、QA 和导出。",
                "asset_strategy_v2": {"strategy": "user_video"},
                "director_knowledge_refs": ["director_knowledge_base_v1.beat_planning"],
                "caption_contract": {
                    "position": "bottom_safe_area",
                    "avoid_subject_and_cta": True,
                },
                "director_review_sheet_v2": {
                    "visual_content": "GitHub README 页面和 Codex 对话触发灵剪流程。",
                    "keyframes": [
                        {"time_sec": 0.0, "state": "Codex 对话窗口入场。"},
                        {"time_sec": 2.0, "state": "README 证据卡展开。"},
                    ],
                },
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_VISUAL_KEYFRAMES_INSUFFICIENT"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_profile_required_evidence_not_covered(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面"],
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面"],
                },
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_PROFILE_EVIDENCE_COVERAGE_INCOMPLETE"
        for issue in report.hard_failures
    )


def test_release_qa_warns_profile_required_evidence_not_covered_in_non_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面"],
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面"],
                },
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_PROFILE_EVIDENCE_COVERAGE_INCOMPLETE"
        for issue in report.warnings
    )


def test_release_qa_allows_profile_required_evidence_covered(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_PROFILE_EVIDENCE_COVERAGE_INCOMPLETE" not in codes


def test_strict_release_qa_blocks_product_profile_without_materialized_evidence(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_VISUAL_EVIDENCE_ASSETS_MISSING"
        for issue in report.hard_failures
    )


def test_release_qa_warns_product_profile_without_materialized_evidence_in_non_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_VISUAL_EVIDENCE_ASSETS_MISSING"
        for issue in report.warnings
    )


def test_strict_release_qa_allows_knowledge_profile_without_evidence_video(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        profile="knowledge_explainer",
        profile_required_evidence=["概念图解"],
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["概念图解"],
                "asset_strategy_v2": {
                    "profile": "knowledge_explainer",
                    "required_evidence": ["概念图解"],
                },
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_VISUAL_EVIDENCE_ASSETS_MISSING" not in codes
    assert "RELEASE_SCENE_EVIDENCE_ASSET_UNBOUND" not in codes


def test_strict_release_qa_blocks_product_profile_with_generated_evidence_card(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "product-card",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-card.mp4",
        "evidence_clip_status": "generated",
        "evidence_visual_source": "text_card",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC"
        for issue in report.hard_failures
    )


def test_strict_release_qa_allows_product_profile_with_materialized_evidence_video(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "product-ui",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-ui.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "screen_recording_video",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示产品界面操作流程和核心工作流",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/product-ui.mp4",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_VISUAL_EVIDENCE_ASSETS_MISSING" not in codes
    assert "RELEASE_SCENE_EVIDENCE_ASSET_UNBOUND" not in codes
    assert "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED" not in codes
    assert "RELEASE_SCENE_EVIDENCE_TYPE_MISMATCH" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_PRIMARY_VISUAL_NOT_CONSUMED" not in codes


def test_strict_release_qa_allows_webm_captured_dynamic_evidence(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "product-ui",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-ui.webm",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "product_interface_video",
        "recording_status": "captured",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示产品界面操作流程和核心工作流",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/product-ui.webm",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED" not in codes
    assert "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_TOO_SHORT" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_DURATION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_PRIMARY_VISUAL_NOT_CONSUMED" not in codes


def test_strict_release_qa_merges_minimal_scene_evidence_ref_from_manifest(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    manifest_ref = {
        "id": "product-ui",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-ui.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "product_interface_video",
        "target_scene_id": "s1",
        "recording_status": "captured",
        "recording_task_redacted": "展示产品界面操作流程和核心工作流",
    }
    clip_path = project.path / str(manifest_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [manifest_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/product-ui.mp4",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_recipe_id": "product_interface_capture",
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [{"id": "product-ui", "target_scene_id": "s1"}],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED" not in codes
    assert "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_DURATION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_TYPE_MISMATCH" not in codes
    assert "RELEASE_SCENE_EVIDENCE_PRIMARY_VISUAL_NOT_CONSUMED" not in codes


def test_strict_release_qa_blocks_product_captured_dynamic_evidence_not_captured_status(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    manifest_ref = {
        "id": "product-ui",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-ui.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "product_interface_video",
        "recording_status": "not_verifiable",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示产品界面操作流程和核心工作流",
    }
    evidence_ref = {
        key: value for key, value in manifest_ref.items() if key != "recording_status"
    }
    clip_path = project.path / str(manifest_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [manifest_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/product-ui.mp4",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_recipe_id": "product_interface_capture",
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_STATUS_NOT_CAPTURED" in codes


def test_strict_release_qa_blocks_short_product_captured_dynamic_evidence(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "product-ui",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-ui.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "product_interface_video",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示产品界面操作流程和核心工作流",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/product-ui.mp4",
                "duration_sec": 6.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_recipe_id": "product_interface_capture",
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 1.0)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_TOO_SHORT" in codes


def test_strict_release_qa_uses_ffprobe_duration_for_recording_evidence(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "product-ui",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-ui.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "product_interface_video",
        "evidence_clip_duration_sec": 8.0,
        "target_scene_id": "s1",
        "recording_task_redacted": "展示产品界面操作流程和核心工作流",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/product-ui.mp4",
                "duration_sec": 6.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_recipe_id": "product_interface_capture",
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 1.0)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_TOO_SHORT" in codes


def test_strict_release_qa_blocks_static_product_captured_dynamic_evidence(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "product-ui",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-ui.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "product_interface_video",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示产品界面操作流程和核心工作流",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/product-ui.mp4",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_recipe_id": "product_interface_capture",
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_motion_delta",
        lambda path: 0.2 if str(path).endswith("product-ui.mp4") else 12.0,
    )

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_DETECTED" in codes


def test_strict_release_qa_blocks_product_captured_dynamic_evidence_not_primary_visual(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "product-ui",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-ui.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "product_interface_video",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示产品界面操作流程和核心工作流",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    scene_asset = project.path / "assets" / "scenes" / "s1.mp4"
    scene_asset.parent.mkdir(parents=True, exist_ok=True)
    scene_asset.write_bytes(b"not evidence primary")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_recipe_id": "product_interface_capture",
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_PRIMARY_VISUAL_NOT_CONSUMED" in codes


def test_strict_release_qa_blocks_product_profile_with_wrong_evidence_type(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "terminal-proof",
        "evidence_type": "terminal_recording_capture",
        "evidence_clip_path": "assets/evidence/clips/terminal-proof.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "terminal_recording_video",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示产品界面操作流程和核心工作流",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["terminal_recording_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/terminal-proof.mp4",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_recipe_id": "product_interface_capture",
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED" not in codes
    assert "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_PRIMARY_VISUAL_NOT_CONSUMED" not in codes
    assert "RELEASE_SCENE_EVIDENCE_TYPE_MISMATCH" in codes


def test_strict_release_qa_blocks_product_recording_without_matching_task_intent(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "product-ui",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-ui.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "screen_recording_video",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示无关日历页面滚动",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/product-ui.mp4",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_recipe_id": "product_interface_capture",
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE" in codes


def test_strict_release_qa_allows_product_recording_with_matching_task_intent(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "product-ui",
        "evidence_type": "product_interface_capture",
        "evidence_clip_path": "assets/evidence/clips/product-ui.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "screen_recording_video",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示产品界面操作流程和核心工作流",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        profile="product_intro",
        profile_required_evidence=["产品界面", "核心工作流"],
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["product_interface_capture"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/product-ui.mp4",
                "duration_sec": 4.0,
                "render_source": "video",
                "expected_real_evidence": ["产品界面", "核心工作流"],
                "asset_recipe_id": "product_interface_capture",
                "asset_strategy_v2": {
                    "profile": "product_intro",
                    "required_evidence": ["产品界面", "核心工作流"],
                },
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_PRIMARY_VISUAL_NOT_CONSUMED" not in codes


def test_strict_release_qa_blocks_unconfirmed_remotion_license(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project, scenes=[_remotion_director_scene(confirmed=False)])
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_VISUAL_REMOTION_LICENSE_NOT_CONFIRMED"
        for issue in report.hard_failures
    )


def test_strict_release_qa_allows_confirmed_remotion_license(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(project, scenes=[_remotion_director_scene(confirmed=True)])
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert "RELEASE_VISUAL_REMOTION_LICENSE_NOT_CONFIRMED" not in {
        issue.code for issue in report.hard_failures
    }


def _host_generated_director_scene(
    host_contract: dict,
    *,
    asset_origin: str = "lingjian_hyperframes_director",
) -> dict:
    return {
        "scene_id": "s1",
        "generator": "hyperframes",
        "asset_origin": asset_origin,
        "asset_path": "assets/scenes/s1.mp4",
        "render_source": "video",
        "duration_sec": 4.0,
        "narration_text": "展示 GitHub README 和安装入口,说明灵剪能从一句话进入视频生产。",
        "visual_prompt": "GitHub README 安装入口和 Codex 对话触发的动态界面证据。",
        "blueprint_id": "hook_codex_prompt",
        "visual_archetype": "hook",
        "asset_recipe_id": "github_readme_capture",
        "material_key": "dark-ui",
        "layout_contract": layout_contract(1, "9:16", "hook"),
        "transition_plan": {"family": "push-slide"},
        "motion_rule_ids": ["screen-pan", "callout-pop"],
        "evidence_asset_refs": [{"id": "ev-1", "type": "github_repo"}],
        "engine_policy": {"selected_engine": "hyperframes"},
        "route_reason": "开源项目介绍镜头优先委托 HyperFrames 生成动态界面证据。",
        "asset_strategy_v2": {"strategy": "host_generated_video"},
        "director_knowledge_refs": ["director_knowledge_base_v1.motion.screen-pan"],
        "keyframes": [
            {"time_sec": 0.0, "state": "Codex 提示词窗口入场。"},
            {"time_sec": 2.0, "state": "README 安装入口放大。"},
            {"time_sec": 3.7, "state": "Star CTA 聚焦收束。"},
        ],
        "caption_contract": {
            "position": "bottom_safe_area",
            "avoid_subject_and_cta": True,
        },
        "host_generation_contract": host_contract,
    }


def test_strict_release_qa_blocks_host_adapter_contract_bypass_with_archetype_only(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    scene = {
        "scene_id": "s1",
        "generator": "hyperframes",
        "asset_origin": "lingjian_hyperframes_director",
        "asset_path": "assets/scenes/s1.mp4",
        "render_source": "video",
        "duration_sec": 4.0,
        "narration_text": "展示灵剪的真实证据镜头。",
        "visual_prompt": "Codex 操作画面和 QA 证据仪表盘。",
        "visual_archetype": "qa_evidence_wall",
        "asset_recipe_id": "qa_report_capture",
        "transition_plan": {"family": "terminal-scan"},
        "motion_intent": {"motion_rule_ids": ["screen-pan", "callout-pop"]},
    }
    _write_minimal_release_manifest(project, scenes=[scene])
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_enters_host_contract_gate_for_asset_recipe_only(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    scene = {
        "scene_id": "s1",
        "generator": "user_video",
        "asset_origin": "lingjian_hyperframes_director",
        "asset_path": "assets/scenes/s1.mp4",
        "render_source": "video",
        "duration_sec": 4.0,
        "narration_text": "展示 README 安装入口。",
        "visual_prompt": "README 安装入口动态证据。",
        "asset_recipe_id": "readme_install_capture",
    }
    _write_minimal_release_manifest(project, scenes=[scene])
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_incomplete_host_generation_contract(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            _host_generated_director_scene(
                {
                    "adapter": "lingjian_hyperframes_director",
                    "blueprint_id": "hook_codex_prompt",
                }
            )
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        for issue in report.hard_failures
    )


def test_release_qa_warns_incomplete_host_generation_contract_in_non_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            _host_generated_director_scene(
                {
                    "adapter": "lingjian_hyperframes_director",
                    "blueprint_id": "hook_codex_prompt",
                }
            )
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_host_contract_without_evidence_media_count(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    scene = _host_generated_director_scene(
        {
            "adapter": "lingjian_hyperframes_director",
            "blueprint_id": "hook_codex_prompt",
            "visual_archetype": "hook",
            "asset_recipe_id": "github_readme_capture",
            "material_key": "dark-ui",
            "layout_signature": "hook-layout",
            "transition_family": "push-slide",
            "motion_rule_ids": ["screen-pan", "callout-pop"],
            "evidence_ref_count": 1,
        }
    )
    scene["evidence_asset_refs"] = [
        {
            "id": "ev-1",
            "type": "github_repo",
            "evidence_clip_path": "assets/evidence/videos/github.mp4",
        }
    ]
    _write_minimal_release_manifest(project, scenes=[scene])
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_video_evidence_without_hero_contract(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    scene = _host_generated_director_scene(
        {
            "adapter": "lingjian_hyperframes_director",
            "blueprint_id": "hook_codex_prompt",
            "visual_archetype": "hook",
            "asset_recipe_id": "github_readme_capture",
            "material_key": "dark-ui",
            "layout_signature": "hook-layout",
            "transition_family": "push-slide",
            "motion_rule_ids": ["screen-pan", "callout-pop"],
            "keyframe_count": 3,
            "keyframe_state_count": 3,
            "evidence_ref_count": 1,
            "evidence_media_count": 1,
            "contract_confirmed_by_generator": True,
        }
    )
    scene["evidence_asset_refs"] = [
        {
            "id": "ev-1",
            "type": "github_repo",
            "evidence_clip_path": "assets/evidence/videos/github.mp4",
        }
    ]
    _write_minimal_release_manifest(project, scenes=[scene])
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        and "evidence_media_hero_kind" in issue.message_zh
        for issue in report.hard_failures
    )


def test_strict_release_qa_allows_video_evidence_with_hero_contract(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    scene = _host_generated_director_scene(
        {
            "adapter": "lingjian_hyperframes_director",
            "blueprint_id": "hook_codex_prompt",
            "visual_archetype": "hook",
            "asset_recipe_id": "github_readme_capture",
            "material_key": "dark-ui",
            "layout_signature": "hook-layout",
            "transition_family": "push-slide",
            "motion_rule_ids": ["screen-pan", "callout-pop"],
            "keyframe_count": 3,
            "keyframe_state_count": 3,
            "evidence_ref_count": 1,
            "evidence_media_count": 1,
            "evidence_media_hero_kind": "video",
            "evidence_media_hero_role": "primary_visual",
            "template_body_suppressed_for_evidence": True,
            "contract_confirmed_by_generator": True,
        }
    )
    scene["evidence_asset_refs"] = [
        {
            "id": "ev-1",
            "type": "github_repo",
            "evidence_clip_path": "assets/evidence/videos/github.mp4",
        }
    ]
    _write_minimal_release_manifest(project, scenes=[scene])
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is True
    assert not any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_video_evidence_when_template_body_not_suppressed(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    scene = _host_generated_director_scene(
        {
            "adapter": "lingjian_hyperframes_director",
            "blueprint_id": "hook_codex_prompt",
            "visual_archetype": "hook",
            "asset_recipe_id": "github_readme_capture",
            "material_key": "dark-ui",
            "layout_signature": "hook-layout",
            "transition_family": "push-slide",
            "motion_rule_ids": ["screen-pan", "callout-pop"],
            "keyframe_count": 3,
            "keyframe_state_count": 3,
            "evidence_ref_count": 1,
            "evidence_media_count": 1,
            "evidence_media_hero_kind": "video",
            "evidence_media_hero_role": "primary_visual",
            "contract_confirmed_by_generator": True,
        }
    )
    scene["evidence_asset_refs"] = [
        {
            "id": "ev-1",
            "type": "github_repo",
            "evidence_clip_path": "assets/evidence/videos/github.mp4",
        }
    ]
    _write_minimal_release_manifest(project, scenes=[scene])
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        and "template_body_suppressed_for_evidence" in issue.message_zh
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_unconfirmed_prefilled_host_contract(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            _host_generated_director_scene(
                {
                    "adapter": "lingjian_hyperframes_director",
                    "blueprint_id": "hook_codex_prompt",
                    "visual_archetype": "hook",
                    "asset_recipe_id": "github_readme_capture",
                    "material_key": "dark-ui",
                    "layout_signature": "hook-layout",
                    "transition_family": "push-slide",
                    "motion_rule_ids": ["screen-pan", "callout-pop"],
                    "evidence_ref_count": 1,
                    "evidence_media_count": 0,
                    "contract_confirmed_by_generator": False,
                }
            )
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        and "contract_confirmed_by_generator" in issue.message_zh
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_host_contract_without_keyframe_evidence(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    scene = _host_generated_director_scene(
        {
            "adapter": "lingjian_hyperframes_director",
            "blueprint_id": "hook_codex_prompt",
            "visual_archetype": "hook",
            "asset_recipe_id": "github_readme_capture",
            "material_key": "dark-ui",
            "layout_signature": "hook-layout",
            "transition_family": "push-slide",
            "motion_rule_ids": ["screen-pan", "callout-pop"],
            "evidence_ref_count": 1,
            "evidence_media_count": 0,
            "contract_confirmed_by_generator": True,
        }
    )
    scene["keyframes"] = [
        {"time_sec": 0.0, "state": "Codex 提示词窗口入场。"},
        {"time_sec": 2.0, "state": "README 安装入口放大。"},
        {"time_sec": 3.7, "state": "Star CTA 聚焦收束。"},
    ]
    _write_minimal_release_manifest(project, scenes=[scene])
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        and "keyframe_count" in issue.message_zh
        and "keyframe_state_count" in issue.message_zh
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_external_generator_without_contract_confirmation(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            _host_generated_director_scene(
                {
                    "adapter": "external_visual_generator",
                    "blueprint_id": "hook_codex_prompt",
                    "visual_archetype": "hook",
                    "asset_recipe_id": "github_readme_capture",
                    "material_key": "dark-ui",
                    "layout_signature": "hook-layout",
                    "transition_family": "push-slide",
                    "motion_rule_ids": ["screen-pan", "callout-pop"],
                    "evidence_ref_count": 1,
                    "evidence_media_count": 0,
                },
                asset_origin="external_visual_generator",
            )
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        and "contract_confirmed_by_generator" in issue.message_zh
        for issue in report.hard_failures
    )


def test_strict_release_qa_allows_complete_host_generation_contract(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            _host_generated_director_scene(
                {
                    "adapter": "lingjian_hyperframes_director",
                    "blueprint_id": "hook_codex_prompt",
                    "visual_archetype": "hook",
                    "asset_recipe_id": "github_readme_capture",
                    "material_key": "dark-ui",
                    "layout_signature": "hook-layout",
                    "transition_family": "push-slide",
                    "motion_rule_ids": ["screen-pan", "callout-pop"],
                    "keyframe_count": 3,
                    "keyframe_state_count": 3,
                    "evidence_ref_count": 1,
                    "evidence_media_count": 0,
                    "contract_confirmed_by_generator": True,
                }
            )
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is True
    assert not any(
        issue.code == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_allows_distinct_video_scenes(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
            },
            {
                "scene_id": "s2",
                "asset_path": "assets/scenes/s2.mp4",
                "render_source": "video",
            },
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is True
    assert not report.hard_failures


def test_strict_release_qa_blocks_missing_director_layout_contract(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "generator": "hyperframes",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "motion_intent": {"main_motion_intent": "痛点聚焦"},
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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
        issue.code == "RELEASE_VISUAL_LAYOUT_CONTRACT_MISSING"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_caption_safe_area_contract(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    contract = layout_contract(1, "9:16", "hook")
    contract["quiet_text_zone"] = {"x": 64, "y": 480, "w": 952, "h": 280}
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "generator": "hyperframes",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "layout_contract": contract,
                        "caption_contract": {
                            "rule_id": "center_caption",
                            "position": "画面中部",
                            "avoid_subject_and_cta": False,
                        },
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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
    codes = {issue.code for issue in report.hard_failures}

    assert report.release_ready is False
    assert "RELEASE_CAPTION_SAFE_AREA_INVALID" in codes
    assert "RELEASE_CAPTION_SAFE_AREA_NOT_DECLARED" in codes
    assert "RELEASE_CAPTION_AVOIDANCE_NOT_DECLARED" in codes


def test_strict_release_qa_blocks_weak_motion_contract(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "generator": "hyperframes",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "layout_contract": layout_contract(1, "9:16", "hook"),
                        "motion_intent": {
                            "beats": [
                                {"properties": ["opacity", "y"]},
                                {"properties": ["opacity", "translateY"]},
                            ]
                        },
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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
        issue.code == "RELEASE_VISUAL_MOTION_TOO_WEAK"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_repeated_director_blueprints(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 3,
                "visual_real_count": 3,
                "scenes": [
                    {
                        "scene_id": f"s{index}",
                        "generator": "hyperframes",
                        "asset_path": f"assets/scenes/s{index}.mp4",
                        "render_source": "video",
                        "blueprint_id": "same-blueprint",
                        "template_id": "same-blueprint",
                        "transition_plan": {"family": "same-transition"},
                        "material_key": "same-material",
                        "layout_contract": layout_contract(index, "9:16", "hook"),
                        "motion_intent": {
                            "motion_rule_ids": ["discrete-text-sequence"],
                            "develop_full_duration": True,
                        },
                    }
                    for index in range(1, 4)
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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
    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VISUAL_BLUEPRINT_REPEATED" in codes
    assert "RELEASE_VISUAL_TRANSITION_REPEATED" in codes
    assert "RELEASE_VISUAL_MOTION_VOCAB_TOO_THIN" in codes


def test_strict_release_qa_blocks_repeated_execution_layouts(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        visual_total=3,
        visual_real_count=3,
        scenes=[
            {
                "scene_id": "s1",
                "generator": "hyperframes",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "blueprint_id": "hook_a",
                "transition_plan": {"family": "a"},
                "material_key": "material-a",
                "motion_rule_ids": ["a", "b"],
                "layout_contract": layout_contract(1, "9:16", "hook"),
                "host_generation_contract": {"layout_signature": "same-layout"},
            },
            {
                "scene_id": "s2",
                "generator": "hyperframes",
                "asset_path": "assets/scenes/s2.mp4",
                "render_source": "video",
                "blueprint_id": "pain_b",
                "transition_plan": {"family": "b"},
                "material_key": "material-b",
                "motion_rule_ids": ["c", "d"],
                "layout_contract": layout_contract(2, "9:16", "pain"),
                "host_generation_contract": {"layout_signature": "same-layout"},
            },
            {
                "scene_id": "s3",
                "generator": "hyperframes",
                "asset_path": "assets/scenes/s3.mp4",
                "render_source": "video",
                "blueprint_id": "proof_c",
                "transition_plan": {"family": "c"},
                "material_key": "material-c",
                "motion_rule_ids": ["e", "f"],
                "layout_contract": layout_contract(3, "9:16", "proof"),
                "host_generation_contract": {"layout_signature": "same-layout"},
            },
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VISUAL_LAYOUT_TOO_UNIFORM" in codes


def test_strict_release_qa_blocks_repeated_layout_contract_geometry(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    repeated_layout = layout_contract(2, "9:16", "pain")
    _write_minimal_release_manifest(
        project,
        visual_total=3,
        visual_real_count=3,
        scenes=[
            {
                "scene_id": "s1",
                "generator": "hyperframes",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "blueprint_id": "hook_a",
                "transition_plan": {"family": "a"},
                "material_key": "material-a",
                "motion_rule_ids": ["a", "b"],
                "layout_contract": repeated_layout,
            },
            {
                "scene_id": "s2",
                "generator": "hyperframes",
                "asset_path": "assets/scenes/s2.mp4",
                "render_source": "video",
                "blueprint_id": "pain_b",
                "transition_plan": {"family": "b"},
                "material_key": "material-b",
                "motion_rule_ids": ["c", "d"],
                "layout_contract": repeated_layout,
            },
            {
                "scene_id": "s3",
                "generator": "hyperframes",
                "asset_path": "assets/scenes/s3.mp4",
                "render_source": "video",
                "blueprint_id": "proof_c",
                "transition_plan": {"family": "c"},
                "material_key": "material-c",
                "motion_rule_ids": ["e", "f"],
                "layout_contract": repeated_layout,
            },
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VISUAL_LAYOUT_TOO_UNIFORM" in codes


def _patch_release_media_checks_ok(monkeypatch) -> None:
    monkeypatch.setattr("packages.core.qa._media_streams_are_verifiable", lambda path: (True, True))
    monkeypatch.setattr("packages.core.qa._frame_sample_is_verifiable", lambda path: True)
    monkeypatch.setattr("packages.core.qa._sample_frame_luma_contrast", lambda path: 64.0)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_has_caption_pixels_outside_safe_area",
        lambda path, timestamps=None: False,
    )
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_has_caption_pixels_inside_subject_region",
        lambda path, scenes, timestamps=None: False,
    )
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_has_caption_pixels_inside_cta_region",
        lambda path, scenes, timestamps=None: False,
    )
    monkeypatch.setattr("packages.core.qa._sample_frame_motion_delta", lambda path: 12.0)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_motion_segment_deltas",
        lambda path: [12.0, 12.0],
    )
    monkeypatch.setattr(
        "packages.core.qa._sample_keyframe_motion_deltas",
        lambda path, scene: [12.0, 12.0],
    )
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 8.0)
    monkeypatch.setattr(
        "packages.core.qa._audio_volume_stats",
        lambda path: {"mean_volume_db": -18.0, "peak_volume_db": -2.0},
    )
    monkeypatch.setattr(
        "packages.core.qa._audio_dynamic_stats",
        lambda path: {"rms_dynamic_range_db": 8.0, "rms_window_count": 4.0},
    )
    monkeypatch.setattr(
        "packages.core.qa._audio_lufs_stats",
        lambda path: {"integrated_lufs": -18.0},
    )


def _patch_transition_pixel_evidence_ok(monkeypatch) -> None:
    def fake_sample_frame(_path, timestamp):
        raw_path = str(_path)
        if raw_path.endswith("s1.mp4"):
            return _half_tone_frame(inverted=False)
        if raw_path.endswith("s2.mp4"):
            return _half_tone_frame(inverted=True)
        if raw_path.endswith("s3.mp4"):
            return _caption_band_frame(center_caption=False)
        if raw_path.endswith("s4.mp4"):
            return _caption_band_frame(center_caption=True)
        seconds = float(timestamp)
        return (_solid_frame(32), _solid_frame(128), _solid_frame(224))[
            int(seconds * 10) % 3
        ]

    monkeypatch.setattr("packages.core.qa._sample_frame_rgb", fake_sample_frame)


def _director_keyframes(index: int, duration: float) -> list[dict]:
    return [
        {"time_sec": 0.0, "state": f"第 {index} 镜主体入场并建立视觉锚点。"},
        {
            "time_sec": round(duration * 0.5, 2),
            "state": f"第 {index} 镜证据或界面层级展开,画面继续发展。",
        },
        {
            "time_sec": round(duration * 0.9, 2),
            "state": f"第 {index} 镜收束到下一镜衔接状态。",
        },
    ]


def _director_hook_scene(index: int, *, blueprint: str, duration: float) -> dict:
    role = "hook" if "hook" in blueprint else "pain"
    keyframes = _director_keyframes(index, duration)
    return {
        "scene_id": f"s{index}",
        "generator": "hyperframes",
        "asset_path": f"assets/scenes/s{index}.mp4",
        "render_source": "video",
        "duration_sec": duration,
        "narration_text": "Codex 一句话触发灵剪主线。",
        "on_screen_text": "Codex 灵剪",
        "visual_prompt": "Codex 对话框点亮灵剪流程。",
        "director_review_sheet": {
            "narration_text": "Codex 一句话触发灵剪主线。",
            "screen_text": "Codex 灵剪",
            "visual_content": "Codex 对话框点亮灵剪流程。",
            "visual_elements": ["Codex", "灵剪", "流程"],
        },
        "blueprint_id": blueprint,
        "template_id": blueprint,
        "visual_archetype": blueprint,
        "layout_contract": layout_contract(index, "9:16", role),
        "caption_contract": {
            "rule_id": "bottom_safe_area_cjk",
            "position": "底部安全区",
            "avoid_subject_and_cta": True,
        },
        "engine_policy": {"selected_engine": "hyperframes"},
        "route_reason": "按导演契约路由到 HyperFrames。",
        "asset_strategy_v2": {"profile": "douyin_product"},
        "director_knowledge_refs": {"profile": "douyin_product"},
        "motion_intent": {
            "main_motion_intent": "持续推进",
            "motion_rule_ids": [f"motion-rule-{index}"],
            "develop_full_duration": True,
        },
        "keyframes": keyframes,
        "transition_plan": {"family": f"transition-{index}"},
        "host_generation_contract": {
            "contract_confirmed_by_generator": True,
            "blueprint_id": blueprint,
            "visual_archetype": blueprint,
            "layout_signature": f"layout-{index}",
            "transition_family": f"transition-{index}",
            "motion_rule_ids": [f"motion-rule-{index}"],
            "keyframe_count": len(keyframes),
            "keyframe_state_count": len(keyframes),
        },
    }


def _director_cta_scene(index: int, *, layout: dict) -> dict:
    scene = _director_hook_scene(index, blueprint="cta_repo_star_press", duration=2.0)
    scene.update(
        {
            "role": "cta",
            "narration_text": "关注项目并点一个 Star。",
            "on_screen_text": "Star 项目",
            "visual_prompt": "GitHub Star 行动按钮锁定在画面中下部。",
            "director_review_sheet": {
                "narration_text": "关注项目并点一个 Star。",
                "screen_text": "Star 项目",
                "visual_content": "GitHub Star 行动按钮锁定在画面中下部。",
                "visual_elements": ["GitHub", "Star", "行动按钮"],
            },
            "layout_contract": layout,
            "audio_visual_alignment": {
                "status": "verified",
                "evidence": "已核对 CTA 镜头画面为 GitHub Star 按钮,与口播行动号召一致。",
            },
        }
    )
    return scene


def _one_transition_rendering() -> dict:
    return {
        "rendered": True,
        "transition_count": 1,
        "transitions": [
            {
                "from_scene_id": "s1",
                "to_scene_id": "s2",
                "family": "transition-2",
                "xfade": "wipeleft",
                "offset_sec": 1.7,
                "duration_sec": 0.3,
            }
        ],
    }


def test_strict_release_qa_blocks_cta_scene_without_cta_region(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    cta_layout = layout_contract(2, "9:16", "cta")
    cta_layout.pop("ctaRect")
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        scenes=[
            _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.0),
            _director_cta_scene(2, layout=cta_layout),
        ],
        transition_rendering=_one_transition_rendering(),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_CTA_REGION_NOT_DECLARED"
        for issue in report.hard_failures
    )


def test_release_qa_warns_cta_scene_without_cta_region_in_non_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    cta_layout = layout_contract(2, "9:16", "cta")
    cta_layout.pop("ctaRect")
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        scenes=[
            _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.0),
            _director_cta_scene(2, layout=cta_layout),
        ],
        transition_rendering=_one_transition_rendering(),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_CTA_REGION_NOT_DECLARED"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_caption_region_overlapping_cta(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    cta_layout = layout_contract(2, "9:16", "cta")
    cta_layout["ctaRect"] = {"x": 64, "y": 1320, "w": 952, "h": 220}
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        scenes=[
            _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.0),
            _director_cta_scene(2, layout=cta_layout),
        ],
        transition_rendering=_one_transition_rendering(),
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_CAPTION_OVERLAPS_CTA"
        for issue in report.hard_failures
    )


def test_strict_release_qa_allows_cta_scene_with_protected_cta_region(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        scenes=[
            _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.0),
            _director_cta_scene(2, layout=layout_contract(2, "9:16", "cta")),
        ],
        transition_rendering=_one_transition_rendering(),
    )
    _patch_release_media_checks_ok(monkeypatch)
    _patch_transition_pixel_evidence_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)
    codes = {issue.code for issue in report.hard_failures}

    assert report.release_ready is True
    assert "RELEASE_CTA_REGION_NOT_DECLARED" not in codes
    assert "RELEASE_CAPTION_OVERLAPS_CTA" not in codes


def test_strict_release_qa_blocks_missing_opening_hook(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "scenes": [
                    _director_hook_scene(1, blueprint="pain_overwhelm", duration=2.0),
                    _director_hook_scene(2, blueprint="solution_flow", duration=2.0),
                ],
                "transition_rendering": {
                    "rendered": True,
                    "transition_count": 1,
                    "transitions": [
                        {
                            "from_scene_id": "s1",
                            "to_scene_id": "s2",
                            "family": "transition-2",
                            "xfade": "wipeleft",
                            "duration_sec": 0.35,
                            "offset_sec": 2.45,
                        }
                    ],
                },
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_HOOK_TOO_WEAK" for issue in report.hard_failures)


def test_strict_release_qa_blocks_overlong_opening_hook(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "scenes": [
                    _director_hook_scene(1, blueprint="hook_codex_prompt", duration=5.2),
                    _director_hook_scene(2, blueprint="solution_flow", duration=2.0),
                ],
                "transition_rendering": {"rendered": True},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_HOOK_TOO_WEAK" for issue in report.hard_failures)


def test_strict_release_qa_blocks_hook_template_without_visible_anchor(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    first_scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    first_scene.update(
        {
            "narration_text": "这里是产品介绍的第一部分。",
            "on_screen_text": "产品说明",
            "visual_prompt": "普通背景上展示产品说明标题。",
            "director_review_sheet": {
                "narration_text": "这里是产品介绍的第一部分。",
                "screen_text": "产品说明",
                "visual_content": "普通背景上展示产品说明标题。",
                "visual_elements": ["标题", "背景"],
            },
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "scenes": [
                    first_scene,
                    _director_hook_scene(2, blueprint="solution_flow", duration=2.0),
                ],
                "transition_rendering": {
                    "rendered": True,
                    "transition_count": 1,
                    "transitions": [
                        {
                            "from_scene_id": "s1",
                            "to_scene_id": "s2",
                            "family": "transition-2",
                            "xfade": "wipeleft",
                            "duration_sec": 0.35,
                            "offset_sec": 2.45,
                        }
                    ],
                },
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)
    _patch_transition_pixel_evidence_ok(monkeypatch)
    _write_minimal_voice_plan(project, duration=8.0)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_HOOK_TOO_WEAK" for issue in report.hard_failures)


def test_strict_release_qa_allows_short_opening_hook(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "scenes": [
                    _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8),
                    _director_hook_scene(2, blueprint="solution_flow", duration=2.0),
                ],
                "transition_rendering": {
                    "rendered": True,
                    "transition_count": 1,
                    "transitions": [
                        {
                            "from_scene_id": "s1",
                            "to_scene_id": "s2",
                            "family": "transition-2",
                            "xfade": "wipeleft",
                            "duration_sec": 0.35,
                            "offset_sec": 2.45,
                        }
                    ],
                },
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)
    _patch_transition_pixel_evidence_ok(monkeypatch)
    _write_minimal_voice_plan(project, duration=8.0)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is True
    assert not report.hard_failures


def test_strict_release_qa_does_not_require_hook_for_legacy_manifest(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "duration_sec": 8.0,
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "render_source": "video",
                        "duration_sec": 2.0,
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)
    _write_minimal_voice_plan(project, duration=8.0)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is True
    assert not report.hard_failures


def test_strict_release_qa_blocks_when_audio_visual_alignment_has_no_overlap(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.update(
        {
            "narration_text": "灵剪开源项目值得 star,能帮 AI 小白做视频。",
            "on_screen_text": "今日晚餐",
            "visual_prompt": "厨房切菜和晚餐摆盘。",
            "director_review_sheet": {
                "narration_text": "灵剪开源项目值得 star,能帮 AI 小白做视频。",
                "screen_text": "今日晚餐",
                "visual_content": "厨房切菜、锅具和晚餐摆盘。",
                "visual_elements": ["锅具", "菜板", "晚餐"],
            },
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_VISUAL_MISMATCH"
        for issue in report.hard_failures
    )


def test_release_qa_warns_when_audio_visual_alignment_has_no_overlap_in_non_strict(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.update(
        {
            "narration_text": "灵剪开源项目值得 star,能帮 AI 小白做视频。",
            "on_screen_text": "今日晚餐",
            "visual_prompt": "厨房切菜和晚餐摆盘。",
            "director_review_sheet": {
                "narration_text": "灵剪开源项目值得 star,能帮 AI 小白做视频。",
                "screen_text": "今日晚餐",
                "visual_content": "厨房切菜、锅具和晚餐摆盘。",
                "visual_elements": ["锅具", "菜板", "晚餐"],
            },
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(issue.code == "RELEASE_AUDIO_VISUAL_MISMATCH" for issue in report.warnings)


def test_release_qa_allows_explicit_audio_visual_alignment_status(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.update(
        {
            "narration_text": "灵剪开源项目值得 star。",
            "visual_prompt": "厨房切菜和晚餐摆盘。",
            "audio_visual_alignment": {
                "status": "aligned",
                "evidence": "用户已在导演分镜确认单中确认该镜头为隐喻画面。",
            },
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert not any(
        issue.code == "RELEASE_AUDIO_VISUAL_MISMATCH"
        for issue in report.hard_failures
    )
    assert not any(issue.code == "RELEASE_AUDIO_VISUAL_MISMATCH" for issue in report.warnings)


def test_strict_release_qa_blocks_alignment_status_without_evidence(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.update(
        {
            "narration_text": "灵剪开源项目值得 star。",
            "visual_prompt": "厨房切菜和晚餐摆盘。",
            "audio_visual_alignment": {"status": "aligned"},
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_VISUAL_ALIGNMENT_EVIDENCE_MISSING"
        for issue in report.hard_failures
    )


def test_release_qa_warns_alignment_status_without_evidence_in_non_strict(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.update(
        {
            "narration_text": "灵剪开源项目值得 star。",
            "visual_prompt": "厨房切菜和晚餐摆盘。",
            "audio_visual_alignment": {"status": "verified"},
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_AUDIO_VISUAL_ALIGNMENT_EVIDENCE_MISSING"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_alignment_evidence_ref_for_other_scene(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_video = project.path / "assets" / "evidence" / "videos" / "s2.mp4"
    evidence_video.parent.mkdir(parents=True)
    evidence_video.write_bytes(b"mp4")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.update(
        {
            "narration_text": "灵剪开源项目值得 star。",
            "visual_prompt": "厨房切菜和晚餐摆盘。",
            "audio_visual_alignment": {
                "status": "verified",
                "evidence_refs": [{"id": "ev-s2"}],
            },
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "assets": [
                        {
                            "id": "ev-s2",
                            "target_scene_id": "s2",
                            "evidence_clip_status": "captured",
                            "evidence_clip_path": "assets/evidence/videos/s2.mp4",
                            "evidence_type": "screen_recording_capture",
                        }
                    ]
                },
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_VISUAL_ALIGNMENT_REF_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_release_qa_allows_alignment_evidence_ref_for_current_scene(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_video = project.path / "assets" / "evidence" / "videos" / "s1.mp4"
    evidence_video.parent.mkdir(parents=True)
    evidence_video.write_bytes(b"mp4")
    evidence_ref = {
        "id": "ev-s1",
        "target_scene_id": "s1",
        "evidence_clip_status": "captured",
        "evidence_clip_path": "assets/evidence/videos/s1.mp4",
        "evidence_type": "screen_recording_capture",
    }
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.update(
        {
            "narration_text": "灵剪开源项目值得 star。",
            "visual_prompt": "厨房切菜和晚餐摆盘。",
            "evidence_asset_refs": [{"id": "ev-s1", "target_scene_id": "s1"}],
            "audio_visual_alignment": {
                "status": "verified",
                "evidence_refs": [{"id": "ev-s1"}],
            },
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {"assets": [evidence_ref]},
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_AUDIO_VISUAL_ALIGNMENT_REF_NOT_VERIFIABLE" not in codes
    assert "RELEASE_AUDIO_VISUAL_MISMATCH" not in codes


def test_strict_release_qa_blocks_planned_audio_visual_alignment_status(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.update(
        {
            "narration_text": "Codex 一句话触发灵剪主线。",
            "on_screen_text": "Codex 灵剪",
            "visual_prompt": "Codex 对话框点亮灵剪流程。",
            "audio_visual_alignment": {
                "status": "planned",
                "evidence": "导演分镜计划让 Codex 对话框对应口播。",
            },
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_VISUAL_ALIGNMENT_NOT_VERIFIED"
        for issue in report.hard_failures
    )


def test_release_qa_warns_planned_audio_visual_alignment_status_in_non_strict(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.update(
        {
            "narration_text": "Codex 一句话触发灵剪主线。",
            "on_screen_text": "Codex 灵剪",
            "visual_prompt": "Codex 对话框点亮灵剪流程。",
            "audio_visual_alignment": {"status": "planned"},
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_AUDIO_VISUAL_ALIGNMENT_NOT_VERIFIED"
        for issue in report.warnings
    )


def test_release_qa_allows_audio_visual_keyword_overlap(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.update(
        {
            "narration_text": "Codex 一句话触发灵剪主线。",
            "on_screen_text": "Codex 灵剪",
            "visual_prompt": "Codex 对话框点亮灵剪流程。",
            "director_review_sheet": {
                "narration_text": "Codex 一句话触发灵剪主线。",
                "screen_text": "Codex 灵剪",
                "visual_content": "Codex 对话框点亮灵剪流程。",
                "visual_elements": ["Codex", "灵剪", "流程"],
            },
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert not any(
        issue.code == "RELEASE_AUDIO_VISUAL_MISMATCH"
        for issue in report.hard_failures
    )
    assert not any(issue.code == "RELEASE_AUDIO_VISUAL_MISMATCH" for issue in report.warnings)


def test_release_qa_uses_director_review_sheet_v2_for_audio_visual_overlap(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.pop("director_review_sheet", None)
    scene.update(
        {
            "narration_text": "Codex 一句话触发灵剪主线。",
            "on_screen_text": "",
            "visual_prompt": "",
            "director_review_sheet_v2": {
                "narration_text": "Codex 一句话触发灵剪主线。",
                "screen_text": "Codex 灵剪",
                "visual_content": "Codex 对话框点亮灵剪流程。",
                "visual_elements": ["Codex", "灵剪", "流程"],
            },
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert not any(
        issue.code == "RELEASE_AUDIO_VISUAL_MISMATCH"
        for issue in report.hard_failures
    )
    assert not any(issue.code == "RELEASE_AUDIO_VISUAL_MISMATCH" for issue in report.warnings)


def test_strict_release_qa_reads_planned_alignment_from_review_sheet_v2(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene = _director_hook_scene(1, blueprint="hook_codex_prompt", duration=2.8)
    scene.pop("director_review_sheet", None)
    scene.update(
        {
            "director_review_sheet_v2": {
                "narration_text": "Codex 一句话触发灵剪主线。",
                "screen_text": "Codex 灵剪",
                "visual_content": "Codex 对话框点亮灵剪流程。",
                "audio_visual_alignment": {
                    "status": "planned",
                    "evidence": "导演分镜计划让 Codex 对话框对应口播。",
                },
            },
        }
    )
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [scene],
                "transition_rendering": {"rendered": False},
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_AUDIO_VISUAL_ALIGNMENT_NOT_VERIFIED"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_missing_timed_caption_cues(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "subtitle_burn": True,
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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
    assert any(issue.code == "RELEASE_CAPTION_NOT_TIMED" for issue in report.hard_failures)


def test_strict_release_qa_blocks_estimated_caption_timing(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "narration_text": "灵剪会按脚本配音分镜导出。",
                "caption_timing": {"source": "estimated"},
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                        "text": "灵剪会按脚本配音",
                        "lines": ["灵剪会按脚本配音"],
                        "source": "estimated",
                    },
                    {
                        "start_sec": 1.05,
                        "end_sec": 1.9,
                        "text": "分镜导出",
                        "lines": ["分镜导出"],
                        "source": "estimated",
                    },
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_CAPTION_TIMING_IS_ESTIMATED"
        for issue in report.hard_failures
    )
    blocker = report.metadata["remaining_caption_timing_blockers"][0]
    assert blocker["scene_id"] == "s1"
    assert blocker["issue_code"] == "RELEASE_CAPTION_TIMING_IS_ESTIMATED"
    assert blocker["target_field"] == "artifacts/voice_plan.json segments[].caption_cues"
    assert blocker["current_timing_source"] == "estimated"
    assert blocker["cue_sources"] == ["estimated"]
    qa_markdown = (project.path / "artifacts" / "qa_report.md").read_text(
        encoding="utf-8"
    )
    assert "字幕 timing 恢复建议" in qa_markdown
    assert "RELEASE_CAPTION_TIMING_IS_ESTIMATED" in qa_markdown
    assert "artifacts/voice_plan.json segments[].caption_cues" in qa_markdown


def test_strict_release_qa_consumes_caption_timing_release_ready_false(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    caption_cues = [
        {
            "start_sec": 0.0,
            "end_sec": 1.0,
            "text": "灵剪会按脚本配音",
            "lines": ["灵剪会按脚本配音"],
            "source": "voice_segment",
        },
        {
            "start_sec": 1.05,
            "end_sec": 1.9,
            "text": "分镜导出",
            "lines": ["分镜导出"],
            "source": "voice_segment",
        },
    ]
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "narration_text": "灵剪会按脚本配音分镜导出。",
                "caption_timing": {
                    "source": "voice_segment",
                    "release_ready": False,
                    "release_blocker_code": "RELEASE_CAPTION_TIMING_NOT_RELEASE_READY",
                    "release_blocker_zh": "render_manifest 已标记字幕 timing 不可发布。",
                    "recovery_next_action_zh": "请补齐真实字幕时间戳后重新渲染。",
                },
                "caption_cues": caption_cues,
            }
        ],
    )
    _write_voice_plan_caption_cues(project, caption_cues)
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_CAPTION_TIMING_NOT_RELEASE_READY"
        for issue in report.hard_failures
    )
    blocker = report.metadata["remaining_caption_timing_blockers"][0]
    assert blocker["scene_id"] == "s1"
    assert blocker["issue_code"] == "RELEASE_CAPTION_TIMING_NOT_RELEASE_READY"
    assert blocker["current_timing_source"] == "voice_segment"
    assert blocker["next_action_zh"] == "请补齐真实字幕时间戳后重新渲染。"


def test_strict_release_qa_blocks_estimated_caption_timing_basis(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    caption_cues = [
        {
            "start_sec": 0.0,
            "end_sec": 1.0,
            "text": "灵剪会按脚本配音",
            "lines": ["灵剪会按脚本配音"],
            "source": "voice_segment",
            "timing_basis": "estimated",
        },
        {
            "start_sec": 1.05,
            "end_sec": 1.9,
            "text": "分镜导出",
            "lines": ["分镜导出"],
            "source": "voice_segment",
            "timing_basis": "estimated",
        },
    ]
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "narration_text": "灵剪会按脚本配音分镜导出。",
                "caption_timing": {
                    "source": "voice_segment",
                    "timing_basis": "estimated",
                },
                "caption_cues": caption_cues,
            }
        ],
    )
    _write_voice_plan_caption_cues(project, caption_cues)
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_CAPTION_TIMING_IS_ESTIMATED"
        for issue in report.hard_failures
    )
    blocker = report.metadata["remaining_caption_timing_blockers"][0]
    assert blocker["scene_id"] == "s1"
    assert blocker["issue_code"] == "RELEASE_CAPTION_TIMING_IS_ESTIMATED"
    assert blocker["current_timing_source"] == "voice_segment"
    assert blocker["current_timing_basis"] == "estimated"
    assert blocker["cue_timing_bases"] == ["estimated"]


def test_release_qa_warns_for_estimated_caption_timing_without_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "narration_text": "灵剪会按脚本配音分镜导出。",
                "caption_timing": {"source": "estimated"},
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                        "text": "灵剪会按脚本配音",
                        "lines": ["灵剪会按脚本配音"],
                        "source": "estimated",
                    },
                    {
                        "start_sec": 1.05,
                        "end_sec": 1.9,
                        "text": "分镜导出",
                        "lines": ["分镜导出"],
                        "source": "estimated",
                    },
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert any(
        issue.code == "RELEASE_CAPTION_TIMING_IS_ESTIMATED" for issue in report.warnings
    )
    assert not any(
        issue.code == "RELEASE_CAPTION_TIMING_IS_ESTIMATED"
        for issue in report.hard_failures
    )


def test_release_qa_allows_voice_segment_caption_timing(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    caption_cues = [
        {
            "start_sec": 0.0,
            "end_sec": 1.0,
            "text": "灵剪会按脚本配音",
            "lines": ["灵剪会按脚本配音"],
            "source": "voice_segment",
        },
        {
            "start_sec": 1.05,
            "end_sec": 1.9,
            "text": "分镜导出",
            "lines": ["分镜导出"],
            "source": "voice_segment",
        },
    ]
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "narration_text": "灵剪会按脚本配音分镜导出。",
                "caption_timing": {"source": "voice_segment"},
                "caption_cues": caption_cues,
            }
        ],
    )
    _write_voice_plan_caption_cues(project, caption_cues)
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_CAPTION_TIMING_IS_ESTIMATED" not in codes
    assert "RELEASE_CAPTION_TIMING_BASIS_NOT_VERIFIABLE" not in codes


def test_release_qa_allows_voice_duration_aligned_caption_timing(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    caption_cues = [
        {
            "start_sec": 0.0,
            "end_sec": 1.0,
            "text": "灵剪会按脚本配音",
            "lines": ["灵剪会按脚本配音"],
            "source": "voice_duration_aligned",
            "timing_basis": "real_segment_duration",
        },
        {
            "start_sec": 1.05,
            "end_sec": 1.9,
            "text": "分镜导出",
            "lines": ["分镜导出"],
            "source": "voice_duration_aligned",
            "timing_basis": "real_segment_duration",
        },
    ]
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "narration_text": "灵剪会按脚本配音分镜导出。",
                "caption_timing": {
                    "source": "voice_duration_aligned",
                    "timing_basis": "real_segment_duration",
                },
                "caption_cues": caption_cues,
            }
        ],
    )
    _write_voice_plan_caption_cues(project, caption_cues)
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_CAPTION_TIMING_IS_ESTIMATED" not in codes
    assert "RELEASE_CAPTION_TIMING_BASIS_NOT_VERIFIABLE" not in codes


def test_release_qa_allows_transition_safe_caption_cues_backed_by_voice_plan(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    voice_plan_cues = [
        {
            "start_sec": 0.0,
            "end_sec": 0.8,
            "text": "灵剪会按脚本配音",
            "lines": ["灵剪会按脚本配音"],
            "source": "voice_duration_aligned",
            "timing_basis": "real_segment_duration",
        }
    ]
    rendered_cues = [
        {
            "start_sec": 0.38,
            "end_sec": 0.8,
            "text": "灵剪会按脚本配音",
            "lines": ["灵剪会按脚本配音"],
            "source": "voice_duration_aligned",
            "timing_basis": "real_segment_duration",
            "transition_safe_window": {
                "applied": True,
                "original_start_sec": 0.0,
                "original_end_sec": 0.8,
                "trim_start_sec": 0.35,
                "trim_end_sec": 0.0,
                "guard_sec": 0.03,
            },
        }
    ]
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "narration_text": "灵剪会按脚本配音。",
                "caption_timing": {
                    "source": "voice_duration_aligned",
                    "timing_basis": "real_segment_duration",
                    "release_ready": True,
                },
                "caption_cues": rendered_cues,
            }
        ],
    )
    _write_voice_plan_caption_cues(project, voice_plan_cues)
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_CAPTION_TIMING_NOT_BACKED_BY_VOICE_PLAN" not in codes


def test_strict_release_qa_blocks_caption_timing_not_backed_by_voice_plan(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "narration_text": "灵剪会按脚本配音分镜导出。",
                "caption_timing": {
                    "source": "voice_duration_aligned",
                    "timing_basis": "real_segment_duration",
                    "release_ready": True,
                },
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                        "text": "灵剪会按脚本配音",
                        "lines": ["灵剪会按脚本配音"],
                        "source": "voice_duration_aligned",
                        "timing_basis": "real_segment_duration",
                    },
                    {
                        "start_sec": 1.05,
                        "end_sec": 1.9,
                        "text": "分镜导出",
                        "lines": ["分镜导出"],
                        "source": "voice_duration_aligned",
                        "timing_basis": "real_segment_duration",
                    },
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_CAPTION_TIMING_NOT_BACKED_BY_VOICE_PLAN"
        for issue in report.hard_failures
    )
    blocker = report.metadata["remaining_caption_timing_blockers"][0]
    assert blocker["scene_id"] == "s1"
    assert blocker["issue_code"] == "RELEASE_CAPTION_TIMING_NOT_BACKED_BY_VOICE_PLAN"
    assert blocker["current_timing_source"] == "voice_duration_aligned"
    assert blocker["required_timing_basis"] == "real_segment_duration"


def test_strict_release_qa_blocks_voice_duration_aligned_without_timing_basis(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "narration_text": "灵剪会按脚本配音分镜导出。",
                "caption_timing": {"source": "voice_duration_aligned"},
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                        "text": "灵剪会按脚本配音",
                        "lines": ["灵剪会按脚本配音"],
                        "source": "voice_duration_aligned",
                    },
                    {
                        "start_sec": 1.05,
                        "end_sec": 1.9,
                        "text": "分镜导出",
                        "lines": ["分镜导出"],
                        "source": "voice_duration_aligned",
                    },
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_CAPTION_TIMING_BASIS_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )
    blocker = report.metadata["remaining_caption_timing_blockers"][0]
    assert blocker["scene_id"] == "s1"
    assert blocker["issue_code"] == "RELEASE_CAPTION_TIMING_BASIS_NOT_VERIFIABLE"
    assert blocker["current_timing_source"] == "voice_duration_aligned"
    assert blocker["required_timing_basis"] == "real_segment_duration"


def test_strict_release_qa_blocks_overlong_caption_cue(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "subtitle_burn": True,
                        "caption_cues": [
                            {
                                "start_sec": 0,
                                "end_sec": 5.0,
                                "text": "这一整段字幕会压在底部太久不符合发布级节奏",
                                "lines": ["这一整段字幕会压在底部太久"],
                            }
                        ],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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
    assert any(issue.code == "RELEASE_CAPTION_CUE_TOO_LONG" for issue in report.hard_failures)


def test_strict_release_qa_blocks_invalid_voice_caption_timing_source(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "subtitle_burn": True,
                "duration_sec": 4.0,
                "narration_text": "第一句第二句",
                "caption_timing": {"source": "voice_segment_invalid"},
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                        "text": "第一句",
                        "lines": ["第一句"],
                    }
                ],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_CAPTION_VOICE_TIMING_INVALID"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_caption_reading_load_too_high(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
                {
                    "scene_id": "s1",
                    "asset_path": "assets/scenes/s1.mp4",
                    "render_source": "video",
                    "duration_sec": 1.4,
                    "subtitle_burn": True,
                    "caption_cues": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 0.5,
                            "text": "灵剪脚本配音画面审查",
                            "lines": ["灵剪脚本配音画面审查"],
                        }
                    ],
                }
            ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_CAPTION_READING_LOAD_TOO_HIGH"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_caption_cue_text_too_long_even_with_short_timing(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.6,
                        "text": "灵剪把脚本配音画面审查导出串起来",
                        "lines": ["灵剪把脚本配音画面审查导出串起来"],
                    }
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_CAPTION_CUE_TOO_LONG"
        for issue in report.hard_failures
    )


def test_release_qa_allows_caption_reading_load_with_short_cue(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 1.4,
                "subtitle_burn": True,
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                        "text": "灵剪能做短视频",
                        "lines": ["灵剪能做短视频"],
                    }
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_CAPTION_READING_LOAD_TOO_HIGH" not in codes


def test_strict_release_qa_blocks_caption_text_mismatch(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "subtitle_burn": True,
                "narration_text": "灵剪把脚本配音画面审查导出串起来",
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.2,
                        "text": "欢迎关注我们",
                        "lines": ["欢迎关注我们"],
                    }
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_CAPTION_TEXT_MISMATCH" for issue in report.hard_failures)


def test_release_qa_allows_caption_text_matching_narration(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.2,
                "subtitle_burn": True,
                "narration_text": "灵剪把脚本配音画面审查导出串起来",
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                        "text": "灵剪把脚本配音画面",
                        "lines": ["灵剪把脚本配音画面"],
                    },
                    {
                        "start_sec": 1.05,
                        "end_sec": 2.0,
                        "text": "审查导出串起来",
                        "lines": ["审查导出串起来"],
                    },
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_CAPTION_TEXT_MISMATCH" not in codes


def test_strict_release_qa_blocks_on_screen_text_repeating_narration(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    repeated_text = "灵剪把脚本配音画面审查导出串起来"
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "subtitle_burn": True,
                "narration_text": repeated_text,
                "on_screen_text": repeated_text,
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "text": "灵剪把脚本配音画面审查",
                        "lines": ["灵剪把脚本配音", "画面审查"],
                    },
                    {
                        "start_sec": 2.0,
                        "end_sec": 4.0,
                        "text": "导出串起来",
                        "lines": ["导出串起来"],
                    },
                ],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_ON_SCREEN_TEXT_DUPLICATES_NARRATION"
        for issue in report.hard_failures
    )


def test_release_qa_warns_on_screen_text_repeating_narration_in_non_strict(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    repeated_text = "灵剪把脚本配音画面审查导出串起来"
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "subtitle_burn": True,
                "narration_text": repeated_text,
                "on_screen_text": repeated_text,
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "text": "灵剪把脚本配音画面审查",
                        "lines": ["灵剪把脚本配音", "画面审查"],
                    },
                    {
                        "start_sec": 2.0,
                        "end_sec": 4.0,
                        "text": "导出串起来",
                        "lines": ["导出串起来"],
                    },
                ],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_ON_SCREEN_TEXT_DUPLICATES_NARRATION"
        for issue in report.warnings
    )


def test_release_qa_allows_short_visual_keyword_overlapping_narration(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "subtitle_burn": True,
                "narration_text": "灵剪把脚本配音画面审查导出串起来",
                "on_screen_text": "三审",
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "text": "灵剪把脚本配音画面审查",
                        "lines": ["灵剪把脚本配音", "画面审查"],
                    },
                    {
                        "start_sec": 2.0,
                        "end_sec": 4.0,
                        "text": "导出串起来",
                        "lines": ["导出串起来"],
                    },
                ],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_ON_SCREEN_TEXT_DUPLICATES_NARRATION" not in codes


def test_strict_release_qa_blocks_dense_on_screen_text(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "subtitle_burn": True,
                "narration_text": "灵剪让 AI 小白也能按流程做开源项目介绍短视频",
                "on_screen_text": "先写脚本再确认配音再确认画面最后导出发布包",
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "text": "灵剪让 AI 小白",
                        "lines": ["灵剪让 AI 小白"],
                    },
                    {
                        "start_sec": 2.0,
                        "end_sec": 4.0,
                        "text": "按流程做短视频",
                        "lines": ["按流程做短视频"],
                    },
                ],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_ON_SCREEN_TEXT_TOO_DENSE"
        for issue in report.hard_failures
    )


def test_release_qa_allows_compact_on_screen_keyword(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "subtitle_burn": True,
                "narration_text": "灵剪让 AI 小白也能按流程做开源项目介绍短视频",
                "on_screen_text": "三审导出",
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "text": "灵剪让 AI 小白",
                        "lines": ["灵剪让 AI 小白"],
                    },
                    {
                        "start_sec": 2.0,
                        "end_sec": 4.0,
                        "text": "按流程做短视频",
                        "lines": ["按流程做短视频"],
                    },
                ],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_ON_SCREEN_TEXT_TOO_DENSE" not in codes


def test_strict_release_qa_blocks_caption_cue_outside_scene_duration(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 1.8,
                "subtitle_burn": True,
                "caption_cues": [
                    {
                        "start_sec": 0.2,
                        "end_sec": 2.4,
                        "text": "字幕越过镜头",
                        "lines": ["字幕越过镜头"],
                    }
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_CAPTION_CUE_OUT_OF_SCENE"
        for issue in report.hard_failures
    )


def test_release_qa_allows_caption_cue_inside_scene_duration(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 1.8,
                "subtitle_burn": True,
                "caption_cues": [
                    {
                        "start_sec": 0.2,
                        "end_sec": 1.86,
                        "text": "字幕在镜头内",
                        "lines": ["字幕在镜头内"],
                    }
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_CAPTION_CUE_OUT_OF_SCENE" not in codes


def test_strict_release_qa_blocks_overlapping_caption_cues(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 3.0,
                "subtitle_burn": True,
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.2,
                        "text": "第一条字幕",
                        "lines": ["第一条字幕"],
                    },
                    {
                        "start_sec": 1.0,
                        "end_sec": 1.8,
                        "text": "第二条重叠",
                        "lines": ["第二条重叠"],
                    },
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(issue.code == "RELEASE_CAPTION_CUE_OVERLAP" for issue in report.hard_failures)


def test_release_qa_allows_ordered_caption_cues(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 3.0,
                "subtitle_burn": True,
                "caption_cues": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                        "text": "第一条字幕",
                        "lines": ["第一条字幕"],
                    },
                    {
                        "start_sec": 1.03,
                        "end_sec": 1.8,
                        "text": "第二条字幕",
                        "lines": ["第二条字幕"],
                    },
                ],
            }
        ],
    )
    (project.path / "assets" / "scenes").mkdir(parents=True)
    (project.path / "assets" / "scenes" / "s1.mp4").write_bytes(b"scene video")
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_CAPTION_CUE_OVERLAP" not in codes


def test_strict_release_qa_blocks_planned_transition_without_rendering(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "transition_rendering": {"rendered": False, "mode": "hard_concat"},
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "transition_plan": {"family": "ticker-crash"},
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "render_source": "video",
                        "transition_plan": {"family": "focus-pull"},
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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
    assert any(issue.code == "RELEASE_TRANSITION_NOT_RENDERED" for issue in report.hard_failures)


def test_strict_release_qa_allows_manifest_verified_transition_rendering(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "transition_rendering": {
                    "rendered": True,
                    "mode": "xfade",
                    "transition_count": 1,
                    "transitions": [
                            {
                                "from_scene_id": "s1",
                                "to_scene_id": "s2",
                                "family": "focus-pull",
                                "xfade": "radial",
                                "duration_sec": 0.35,
                                "offset_sec": 2.65,
                            }
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "ticker-crash"},
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "focus-pull"},
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)
    _patch_transition_pixel_evidence_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert not any(
        issue.code.startswith("RELEASE_TRANSITION_")
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_unverifiable_transition_pixel_evidence(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        transition_rendering=_one_transition_rendering(),
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "transition_plan": {"family": "transition-1"},
            },
            {
                "scene_id": "s2",
                "asset_path": "assets/scenes/s2.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "transition_plan": {"family": "transition-2"},
            },
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._sample_frame_rgb", lambda path, timestamp: None)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_TRANSITION_PIXEL_EVIDENCE_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_flat_transition_pixel_evidence(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        transition_rendering=_one_transition_rendering(),
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "transition_plan": {"family": "transition-1"},
            },
            {
                "scene_id": "s2",
                "asset_path": "assets/scenes/s2.mp4",
                "render_source": "video",
                "duration_sec": 2.0,
                "transition_plan": {"family": "transition-2"},
            },
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_rgb",
        lambda path, timestamp: _solid_frame(96),
    )

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_TRANSITION_PIXEL_EVIDENCE_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_transition_cutting_caption_cue(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        transition_rendering={
            "rendered": True,
            "mode": "xfade",
            "transition_count": 1,
            "transitions": [
                {
                    "from_scene_id": "s1",
                    "to_scene_id": "s2",
                    "family": "focus-pull",
                    "xfade": "radial",
                    "duration_sec": 0.35,
                    "offset_sec": 2.65,
                }
            ],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 3.0,
                "subtitle_burn": True,
                "caption_timing": {
                    "source": "voice_duration_aligned",
                    "timing_basis": "real_segment_duration",
                },
                "caption_cues": [
                    {
                        "start_sec": 1.8,
                        "end_sec": 2.9,
                        "text": "第一句",
                        "lines": ["第一句"],
                        "source": "voice_duration_aligned",
                        "timing_basis": "real_segment_duration",
                    }
                ],
                "transition_plan": {"family": "ticker-crash"},
            },
            {
                "scene_id": "s2",
                "asset_path": "assets/scenes/s2.mp4",
                "render_source": "video",
                "duration_sec": 3.0,
                "subtitle_burn": True,
                "caption_timing": {
                    "source": "voice_duration_aligned",
                    "timing_basis": "real_segment_duration",
                },
                "caption_cues": [
                    {
                        "start_sec": 0.45,
                        "end_sec": 1.2,
                        "text": "第二句",
                        "lines": ["第二句"],
                        "source": "voice_duration_aligned",
                        "timing_basis": "real_segment_duration",
                    }
                ],
                "transition_plan": {"family": "focus-pull"},
            },
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_TRANSITION_CAPTION_CUTS_CUE"
        for issue in report.hard_failures
    )


def test_release_qa_allows_transition_when_captions_avoid_overlap(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    _write_minimal_release_manifest(
        project,
        visual_total=2,
        visual_real_count=2,
        transition_rendering={
            "rendered": True,
            "mode": "xfade",
            "transition_count": 1,
            "transitions": [
                {
                    "from_scene_id": "s1",
                    "to_scene_id": "s2",
                    "family": "focus-pull",
                    "xfade": "radial",
                    "duration_sec": 0.35,
                    "offset_sec": 2.65,
                }
            ],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 3.0,
                "subtitle_burn": True,
                "caption_timing": {
                    "source": "voice_duration_aligned",
                    "timing_basis": "real_segment_duration",
                },
                "caption_cues": [
                    {
                        "start_sec": 1.4,
                        "end_sec": 2.5,
                        "text": "第一句",
                        "lines": ["第一句"],
                        "source": "voice_duration_aligned",
                        "timing_basis": "real_segment_duration",
                    }
                ],
                "transition_plan": {"family": "ticker-crash"},
            },
            {
                "scene_id": "s2",
                "asset_path": "assets/scenes/s2.mp4",
                "render_source": "video",
                "duration_sec": 3.0,
                "subtitle_burn": True,
                "caption_timing": {
                    "source": "voice_duration_aligned",
                    "timing_basis": "real_segment_duration",
                },
                "caption_cues": [
                    {
                        "start_sec": 0.45,
                        "end_sec": 1.2,
                        "text": "第二句",
                        "lines": ["第二句"],
                        "source": "voice_duration_aligned",
                        "timing_basis": "real_segment_duration",
                    }
                ],
                "transition_plan": {"family": "focus-pull"},
            },
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    _patch_transition_pixel_evidence_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures + report.warnings}
    assert "RELEASE_TRANSITION_CAPTION_CUTS_CUE" not in codes


def test_strict_release_qa_blocks_transition_semantic_mismatch(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "transition_rendering": {
                    "rendered": True,
                    "mode": "xfade",
                    "transition_count": 1,
                    "transitions": [
                        {
                            "from_scene_id": "s1",
                            "to_scene_id": "s2",
                            "family": "focus-pull",
                            "xfade": "fade",
                            "duration_sec": 0.35,
                            "offset_sec": 2.65,
                        }
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "ticker-crash"},
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "focus-pull"},
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_TRANSITION_SEMANTIC_MISMATCH"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_incomplete_transition_rendering_manifest(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "transition_rendering": {"rendered": True, "mode": "xfade"},
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "transition_plan": {"family": "ticker-crash"},
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "render_source": "video",
                        "transition_plan": {"family": "focus-pull"},
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_TRANSITION_RENDERING_INCOMPLETE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_uniform_rendered_xfade_transitions(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 3,
                "visual_real_count": 3,
                "transition_rendering": {
                    "rendered": True,
                    "mode": "xfade",
                    "transition_count": 2,
                    "transitions": [
                            {
                                "from_scene_id": "s1",
                                "to_scene_id": "s2",
                                "family": "focus-pull",
                                "xfade": "radial",
                                "duration_sec": 0.35,
                                "offset_sec": 2.65,
                            },
                            {
                                "from_scene_id": "s2",
                                "to_scene_id": "s3",
                                "family": "focus-pull",
                                "xfade": "radial",
                                "duration_sec": 0.35,
                                "offset_sec": 5.65,
                            },
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "ticker-crash"},
                    },
                    {
                            "scene_id": "s2",
                            "asset_path": "assets/scenes/s2.mp4",
                            "render_source": "video",
                            "duration_sec": 3.0,
                            "transition_plan": {"family": "focus-pull"},
                    },
                    {
                            "scene_id": "s3",
                            "asset_path": "assets/scenes/s3.mp4",
                            "render_source": "video",
                            "duration_sec": 3.0,
                            "transition_plan": {"family": "focus-pull"},
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_TRANSITION_VISUAL_TOO_UNIFORM"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_thin_rendered_xfade_variety(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 4,
                "visual_real_count": 4,
                "transition_rendering": {
                    "rendered": True,
                    "mode": "xfade",
                    "transition_count": 3,
                    "transitions": [
                        {
                            "from_scene_id": "s1",
                            "to_scene_id": "s2",
                            "family": "focus-pull",
                            "xfade": "radial",
                            "duration_sec": 0.35,
                            "offset_sec": 2.65,
                        },
                        {
                            "from_scene_id": "s2",
                            "to_scene_id": "s3",
                            "family": "clean-wipe",
                            "xfade": "wipeleft",
                            "duration_sec": 0.35,
                            "offset_sec": 5.65,
                        },
                        {
                            "from_scene_id": "s3",
                            "to_scene_id": "s4",
                            "family": "focus-pull",
                            "xfade": "radial",
                            "duration_sec": 0.35,
                            "offset_sec": 8.65,
                        },
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "ticker-crash"},
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "focus-pull"},
                    },
                    {
                        "scene_id": "s3",
                        "asset_path": "assets/scenes/s3.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "clean-wipe"},
                    },
                    {
                        "scene_id": "s4",
                        "asset_path": "assets/scenes/s4.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "focus-pull"},
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_TRANSITION_VISUAL_TOO_UNIFORM"
        for issue in report.hard_failures
    )


def test_strict_release_qa_allows_three_distinct_rendered_xfade_transitions(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 4,
                "visual_real_count": 4,
                "transition_rendering": {
                    "rendered": True,
                    "mode": "xfade",
                    "transition_count": 3,
                    "transitions": [
                        {
                            "from_scene_id": "s1",
                            "to_scene_id": "s2",
                            "family": "focus-pull",
                            "xfade": "radial",
                            "duration_sec": 0.35,
                            "offset_sec": 2.65,
                        },
                        {
                            "from_scene_id": "s2",
                            "to_scene_id": "s3",
                            "family": "clean-wipe",
                            "xfade": "wipeleft",
                            "duration_sec": 0.35,
                            "offset_sec": 5.65,
                        },
                        {
                            "from_scene_id": "s3",
                            "to_scene_id": "s4",
                            "family": "cta-morph",
                            "xfade": "circleclose",
                            "duration_sec": 0.35,
                            "offset_sec": 8.65,
                        },
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "ticker-crash"},
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "focus-pull"},
                    },
                    {
                        "scene_id": "s3",
                        "asset_path": "assets/scenes/s3.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "clean-wipe"},
                    },
                    {
                        "scene_id": "s4",
                        "asset_path": "assets/scenes/s4.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "cta-morph"},
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)
    _patch_transition_pixel_evidence_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_TRANSITION_VISUAL_TOO_UNIFORM" not in codes


def test_strict_release_qa_blocks_unverifiable_transition_timing(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "transition_rendering": {
                    "rendered": True,
                    "mode": "xfade",
                    "transition_count": 1,
                    "transitions": [
                            {
                                "from_scene_id": "s1",
                                "to_scene_id": "s2",
                                "family": "focus-pull",
                                "xfade": "radial",
                                "duration_sec": 0.35,
                                "offset_sec": 9.0,
                            }
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "ticker-crash"},
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "focus-pull"},
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_TRANSITION_TIMING_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_transition_too_short_to_perceive(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "transition_rendering": {
                    "rendered": True,
                    "mode": "xfade",
                    "transition_count": 1,
                    "transitions": [
                        {
                            "from_scene_id": "s1",
                            "to_scene_id": "s2",
                            "family": "focus-pull",
                            "xfade": "radial",
                            "duration_sec": 0.04,
                            "offset_sec": 2.65,
                        }
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "ticker-crash"},
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "focus-pull"},
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_TRANSITION_TIMING_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_transition_scene_mismatch(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 2,
                "visual_real_count": 2,
                "transition_rendering": {
                    "rendered": True,
                    "mode": "xfade",
                    "transition_count": 1,
                    "transitions": [
                            {
                                "from_scene_id": "s9",
                                "to_scene_id": "s2",
                                "family": "focus-pull",
                                "xfade": "radial",
                                "duration_sec": 0.35,
                                "offset_sec": 2.65,
                            }
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "ticker-crash"},
                    },
                    {
                        "scene_id": "s2",
                        "asset_path": "assets/scenes/s2.mp4",
                        "render_source": "video",
                        "duration_sec": 3.0,
                        "transition_plan": {"family": "focus-pull"},
                    },
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_TRANSITION_TIMING_NOT_VERIFIABLE"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_missing_visual_evidence_assets(tmp_path, monkeypatch):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["GitHub repo", "README", "QA"],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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
        issue.code == "RELEASE_VISUAL_EVIDENCE_ASSETS_MISSING"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_thin_or_unbound_visual_evidence_assets(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "version": "v1",
                    "assets": [{"id": "readme", "evidence_type": "readme_install_entry"}],
                    "evidence_types": ["readme_install_entry"],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["GitHub repo", "README", "QA"],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VISUAL_EVIDENCE_ASSETS_TOO_THIN" in codes
    assert "RELEASE_SCENE_EVIDENCE_ASSET_UNBOUND" in codes


def test_strict_release_qa_blocks_unmaterialized_visual_evidence_video(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_refs = [
        {"id": "github", "evidence_type": "github_repo"},
        {"id": "readme", "evidence_type": "readme_install_entry"},
        {"id": "qa", "evidence_type": "qa_report_artifact"},
    ]
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "version": "v1",
                    "assets": evidence_refs,
                    "evidence_types": [
                        "github_repo",
                        "readme_install_entry",
                        "qa_report_artifact",
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["GitHub repo", "README", "QA"],
                        "evidence_asset_refs": evidence_refs,
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VISUAL_EVIDENCE_ASSETS_TOO_THIN" not in codes
    assert "RELEASE_SCENE_EVIDENCE_ASSET_UNBOUND" not in codes
    assert "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED" in codes


def test_strict_release_qa_blocks_missing_visual_evidence_video_file(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_refs = [
        {
            "id": "github",
            "evidence_type": "github_repo",
            "evidence_clip_path": "assets/evidence/clips/github.mp4",
            "evidence_clip_status": "generated",
            "evidence_clip_style": "github_repo_card",
        },
        {
            "id": "readme",
            "evidence_type": "readme_install_entry",
            "evidence_clip_path": "assets/evidence/clips/readme.mp4",
            "evidence_clip_status": "generated",
            "evidence_clip_style": "readme_install_scroll",
        },
        {
            "id": "qa",
            "evidence_type": "qa_report_artifact",
            "evidence_clip_path": "assets/evidence/clips/qa.mp4",
            "evidence_clip_status": "generated",
            "evidence_clip_style": "qa_status_panel",
        },
    ]
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "version": "v1",
                    "assets": evidence_refs,
                    "evidence_types": [
                        "github_repo",
                        "readme_install_entry",
                        "qa_report_artifact",
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["GitHub repo", "README", "QA"],
                        "evidence_asset_refs": evidence_refs,
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VISUAL_EVIDENCE_ASSETS_TOO_THIN" not in codes
    assert "RELEASE_SCENE_EVIDENCE_ASSET_UNBOUND" not in codes
    assert "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED" in codes


def test_strict_release_qa_blocks_text_card_only_visual_evidence_video(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_refs = [
        {
            "id": "github",
            "evidence_type": "github_repo",
            "evidence_clip_path": "assets/evidence/clips/github.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "text_card",
            "evidence_clip_style": "github_repo_card",
        },
        {
            "id": "readme",
            "evidence_type": "readme_install_entry",
            "evidence_clip_path": "assets/evidence/clips/readme.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "text_card",
            "evidence_clip_style": "readme_install_scroll",
        },
        {
            "id": "qa",
            "evidence_type": "qa_report_artifact",
            "evidence_clip_path": "assets/evidence/clips/qa.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "text_card",
            "evidence_clip_style": "qa_status_panel",
        },
    ]
    for ref in evidence_refs:
        clip_path = project.path / str(ref["evidence_clip_path"])
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        clip_path.write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "version": "v1",
                    "assets": evidence_refs,
                    "evidence_types": [
                        "github_repo",
                        "readme_install_entry",
                        "qa_report_artifact",
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["GitHub repo", "README", "QA"],
                        "evidence_asset_refs": evidence_refs,
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED" not in codes
    assert "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC" in codes


def test_strict_release_qa_blocks_open_source_evidence_without_recording_source(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_refs = [
        {
            "id": "github",
            "evidence_type": "github_repo",
            "evidence_clip_path": "assets/evidence/clips/github.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "source_image",
            "evidence_clip_style": "github_repo_card",
        },
        {
            "id": "readme",
            "evidence_type": "readme_install_entry",
            "evidence_clip_path": "assets/evidence/clips/readme.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "terminal_transcript",
            "evidence_clip_style": "readme_install_scroll",
        },
        {
            "id": "qa",
            "evidence_type": "qa_report_artifact",
            "evidence_clip_path": "assets/evidence/clips/qa.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "source_image",
            "evidence_clip_style": "qa_status_panel",
        },
    ]
    for ref in evidence_refs:
        clip_path = project.path / str(ref["evidence_clip_path"])
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        clip_path.write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "version": "v1",
                    "assets": evidence_refs,
                    "evidence_types": [
                        "github_repo",
                        "readme_install_entry",
                        "qa_report_artifact",
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["GitHub repo", "README", "QA"],
                        "evidence_asset_refs": evidence_refs,
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC" not in codes
    assert "RELEASE_VISUAL_EVIDENCE_RECORDING_MISSING" in codes


def test_release_qa_warns_open_source_evidence_without_recording_source_in_non_strict(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_refs = [
        {
            "id": "github",
            "evidence_type": "github_repo",
            "evidence_clip_path": "assets/evidence/clips/github.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "source_image",
            "evidence_clip_style": "github_repo_card",
        },
        {
            "id": "readme",
            "evidence_type": "readme_install_entry",
            "evidence_clip_path": "assets/evidence/clips/readme.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "terminal_transcript",
            "evidence_clip_style": "readme_install_scroll",
        },
        {
            "id": "qa",
            "evidence_type": "qa_report_artifact",
            "evidence_clip_path": "assets/evidence/clips/qa.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "source_image",
            "evidence_clip_style": "qa_status_panel",
        },
    ]
    for ref in evidence_refs:
        clip_path = project.path / str(ref["evidence_clip_path"])
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        clip_path.write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "version": "v1",
                    "assets": evidence_refs,
                    "evidence_types": [
                        "github_repo",
                        "readme_install_entry",
                        "qa_report_artifact",
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["GitHub repo", "README", "QA"],
                        "evidence_asset_refs": evidence_refs,
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        "packages.core.qa.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
            stderr="",
        ),
    )

    report = run_qa(project, release=True, strict=False)

    warning_codes = {issue.code for issue in report.warnings}
    assert "RELEASE_VISUAL_EVIDENCE_RECORDING_MISSING" in warning_codes
    assert not any(
        issue.code == "RELEASE_VISUAL_EVIDENCE_RECORDING_MISSING"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_scene_without_bound_recording_evidence(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    scene_refs = [
        {
            "id": "github",
            "evidence_type": "github_repo",
            "evidence_clip_path": "assets/evidence/clips/github.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "source_image",
            "evidence_clip_style": "github_repo_card",
        },
        {
            "id": "readme",
            "evidence_type": "readme_install_entry",
            "evidence_clip_path": "assets/evidence/clips/readme.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "terminal_transcript",
            "evidence_clip_style": "readme_install_scroll",
        },
    ]
    recording_ref = {
        "id": "qa-recording",
        "evidence_type": "qa_report_artifact",
        "evidence_clip_path": "assets/evidence/clips/qa-recording.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "web_recording_video",
        "evidence_clip_style": "qa_status_panel",
    }
    evidence_refs = [*scene_refs, recording_ref]
    for ref in evidence_refs:
        clip_path = project.path / str(ref["evidence_clip_path"])
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        clip_path.write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "version": "v1",
                    "assets": evidence_refs,
                    "evidence_types": [
                        "github_repo",
                        "readme_install_entry",
                        "qa_report_artifact",
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["GitHub repo", "README"],
                        "evidence_asset_refs": scene_refs,
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VISUAL_EVIDENCE_RECORDING_MISSING" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_MISSING" in codes


def test_strict_release_qa_blocks_bound_recording_not_used_as_primary_visual(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "codex-recording",
        "evidence_type": "codex_operation_recording",
        "evidence_clip_path": "assets/evidence/clips/codex-recording.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "codex_operation_video",
        "evidence_clip_style": "codex_operation_recording",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示 Codex app 中一句话触发 lingjian-video 并进入能力门诊",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["codex_operation_recording"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/template-loop.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "requires_real_evidence_asset": True,
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "director_knowledge_refs": {"profile": "open_source_project_intro"},
                "expected_real_evidence": ["Codex app 操作画面"],
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 2.4)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_PRIMARY_VISUAL_NOT_CONSUMED" in codes


def test_strict_release_qa_allows_recording_evidence_as_primary_visual(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "codex-recording",
        "evidence_type": "codex_operation_recording",
        "evidence_clip_path": "assets/evidence/clips/codex-recording.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "codex_operation_video",
        "evidence_clip_style": "codex_operation_recording",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示 Codex app 中一句话触发 lingjian-video 并进入能力门诊",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["codex_operation_recording"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/codex-recording.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "requires_real_evidence_asset": True,
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "director_knowledge_refs": {"profile": "open_source_project_intro"},
                "expected_real_evidence": ["Codex app 操作画面"],
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 2.4)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_PRIMARY_VISUAL_NOT_CONSUMED" not in codes


def test_strict_release_qa_allows_host_contract_primary_visual_for_recording_evidence(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    evidence_ref = {
        "id": "codex-recording",
        "type": "codex_operation_recording",
        "evidence_type": "codex_operation_recording",
        "evidence_clip_path": "assets/evidence/clips/codex-recording.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "codex_operation_video",
        "evidence_clip_style": "codex_operation_recording",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示 Codex app 中一句话触发 lingjian-video 并进入能力门诊",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    scene = _host_generated_director_scene(
        {
            "adapter": "lingjian_hyperframes_director",
            "blueprint_id": "hook_codex_prompt",
            "visual_archetype": "hook",
            "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
            "material_key": "dark-ui",
            "layout_signature": "hook-layout",
            "transition_family": "push-slide",
            "motion_rule_ids": ["screen-pan", "callout-pop"],
            "keyframe_count": 3,
            "keyframe_state_count": 3,
            "evidence_ref_count": 1,
            "evidence_media_count": 1,
            "evidence_media_hero_kind": "video",
            "evidence_media_hero_role": "primary_visual",
            "template_body_suppressed_for_evidence": True,
            "contract_confirmed_by_generator": True,
        }
    )
    scene.update(
        {
            "requires_real_evidence_asset": True,
            "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
            "director_knowledge_refs": {"profile": "open_source_project_intro"},
            "expected_real_evidence": ["Codex app 操作画面"],
            "evidence_asset_refs": [evidence_ref],
        }
    )
    _write_minimal_release_manifest(
        project,
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["codex_operation_recording"],
        },
        scenes=[scene],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 2.4)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_PRIMARY_VISUAL_NOT_CONSUMED" not in codes
    assert "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE" not in codes


def test_strict_release_qa_blocks_visual_evidence_type_mismatch(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_refs = [
        {
            "id": "github",
            "evidence_type": "github_repo",
            "evidence_clip_path": "assets/evidence/clips/github.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "source_image",
            "evidence_clip_style": "github_repo_card",
        },
        {
            "id": "readme",
            "evidence_type": "readme_install_entry",
            "evidence_clip_path": "assets/evidence/clips/readme.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "terminal_transcript",
            "evidence_clip_style": "readme_install_scroll",
        },
        {
            "id": "qa",
            "evidence_type": "qa_report_artifact",
            "evidence_clip_path": "assets/evidence/clips/qa.mp4",
            "evidence_clip_status": "captured",
            "evidence_visual_source": "web_recording_video",
            "evidence_clip_style": "qa_status_panel",
        },
    ]
    for ref in evidence_refs:
        clip_path = project.path / str(ref["evidence_clip_path"])
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        clip_path.write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "version": "v1",
                    "assets": evidence_refs,
                    "evidence_types": [
                        "github_repo",
                        "readme_install_entry",
                        "qa_report_artifact",
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["Codex app 操作画面"],
                        "evidence_asset_refs": evidence_refs,
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED" not in codes
    assert "RELEASE_SCENE_EVIDENCE_SOURCE_TOO_SYNTHETIC" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_TYPE_MISMATCH" in codes
    assert "RELEASE_SCENE_EVIDENCE_TYPE_MISMATCH" in codes


def test_strict_release_qa_blocks_uniform_visual_evidence_clip_styles(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_refs = [
        {
            "id": "github",
            "evidence_type": "github_repo",
            "evidence_clip_path": "assets/evidence/clips/github.mp4",
            "evidence_clip_status": "generated",
            "evidence_clip_style": "generic_evidence_card",
        },
        {
            "id": "readme",
            "evidence_type": "readme_install_entry",
            "evidence_clip_path": "assets/evidence/clips/readme.mp4",
            "evidence_clip_status": "generated",
            "evidence_clip_style": "generic_evidence_card",
        },
        {
            "id": "qa",
            "evidence_type": "qa_report_artifact",
            "evidence_clip_path": "assets/evidence/clips/qa.mp4",
            "evidence_clip_status": "generated",
            "evidence_clip_style": "generic_evidence_card",
        },
    ]
    for ref in evidence_refs:
        clip_path = project.path / str(ref["evidence_clip_path"])
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        clip_path.write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "version": "v1",
                    "assets": evidence_refs,
                    "evidence_types": [
                        "github_repo",
                        "readme_install_entry",
                        "qa_report_artifact",
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["GitHub repo", "README", "QA"],
                        "evidence_asset_refs": evidence_refs,
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
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

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VISUAL_EVIDENCE_CLIPS_TOO_UNIFORM" in codes


def test_strict_release_qa_allows_bound_open_source_visual_evidence_assets(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_refs = [
        {
            "id": "github",
            "evidence_type": "github_repo",
            "evidence_clip_path": "assets/evidence/clips/github.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "source_image",
            "evidence_clip_style": "github_repo_card",
        },
        {
            "id": "github-recording",
            "evidence_type": "web_recording_capture",
            "evidence_clip_path": "assets/evidence/clips/github-recording.mp4",
            "evidence_clip_status": "captured",
            "evidence_visual_source": "web_recording_video",
            "evidence_clip_style": "github_page_recording",
            "target_scene_id": "s1",
        },
        {
            "id": "readme",
            "evidence_type": "readme_install_entry",
            "evidence_clip_path": "assets/evidence/clips/readme.mp4",
            "evidence_clip_status": "generated",
            "evidence_visual_source": "terminal_transcript",
            "evidence_clip_style": "readme_install_scroll",
        },
        {
            "id": "readme-recording",
            "evidence_type": "terminal_recording_capture",
            "evidence_clip_path": "assets/evidence/clips/readme-recording.mp4",
            "evidence_clip_status": "captured",
            "evidence_visual_source": "terminal_recording_video",
            "evidence_clip_style": "readme_terminal_recording",
            "target_scene_id": "s1",
        },
        {
            "id": "qa",
            "evidence_type": "qa_report_artifact",
            "evidence_clip_path": "assets/evidence/clips/qa.mp4",
            "evidence_clip_status": "captured",
            "evidence_visual_source": "web_recording_video",
            "evidence_clip_style": "qa_status_panel",
            "target_scene_id": "s1",
        },
        {
            "id": "qa-recording",
            "evidence_type": "screen_recording_capture",
            "evidence_clip_path": "assets/evidence/clips/qa-recording.mp4",
            "evidence_clip_status": "captured",
            "evidence_visual_source": "screen_recording_video",
            "evidence_clip_style": "qa_screen_recording",
            "target_scene_id": "s1",
        },
    ]
    for ref in evidence_refs:
        clip_path = project.path / str(ref["evidence_clip_path"])
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        clip_path.write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "visual_evidence_assets": {
                    "version": "v1",
                    "assets": evidence_refs,
                    "evidence_types": [
                        "github_repo",
                        "web_recording_capture",
                        "readme_install_entry",
                        "terminal_recording_capture",
                        "qa_report_artifact",
                        "screen_recording_capture",
                    ],
                },
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "requires_real_evidence_asset": True,
                        "director_knowledge_refs": {"profile": "open_source_project_intro"},
                        "expected_real_evidence": ["GitHub repo", "README", "QA"],
                        "evidence_asset_refs": evidence_refs,
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        "packages.core.qa.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
            stderr="",
        ),
    )
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 8.0)
    monkeypatch.setattr("packages.core.qa._sample_frame_motion_delta", lambda path: 12.0)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_motion_segment_deltas",
        lambda path: [12.0, 12.0],
    )

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_VISUAL_EVIDENCE_ASSETS_MISSING" not in codes
    assert "RELEASE_VISUAL_EVIDENCE_ASSETS_TOO_THIN" not in codes
    assert "RELEASE_SCENE_EVIDENCE_ASSET_UNBOUND" not in codes
    assert "RELEASE_SCENE_EVIDENCE_VIDEO_UNMATERIALIZED" not in codes
    assert "RELEASE_VISUAL_EVIDENCE_RECORDING_MISSING" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_TOO_SHORT" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_DURATION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_DETECTED" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_VERIFIABLE" not in codes


def test_strict_release_qa_blocks_too_short_recording_evidence(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_refs = [
        {
            "id": "github-recording",
            "evidence_type": "web_recording_capture",
            "evidence_clip_path": "assets/evidence/clips/github-recording.mp4",
            "evidence_clip_status": "captured",
            "evidence_visual_source": "web_recording_video",
            "evidence_clip_style": "github_page_recording",
        },
        {
            "id": "readme-recording",
            "evidence_type": "terminal_recording_capture",
            "evidence_clip_path": "assets/evidence/clips/readme-recording.mp4",
            "evidence_clip_status": "captured",
            "evidence_visual_source": "terminal_recording_video",
            "evidence_clip_style": "readme_terminal_recording",
        },
        {
            "id": "qa-recording",
            "evidence_type": "screen_recording_capture",
            "evidence_clip_path": "assets/evidence/clips/qa-recording.mp4",
            "evidence_clip_status": "captured",
            "evidence_visual_source": "screen_recording_video",
            "evidence_clip_style": "qa_screen_recording",
        },
    ]
    for ref in evidence_refs:
        clip_path = project.path / str(ref["evidence_clip_path"])
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        visual_evidence_assets={
            "version": "v1",
            "assets": evidence_refs,
            "evidence_types": [
                "web_recording_capture",
                "terminal_recording_capture",
                "screen_recording_capture",
            ],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 6.0,
                "requires_real_evidence_asset": True,
                "director_knowledge_refs": {"profile": "open_source_project_intro"},
                "expected_real_evidence": ["GitHub repo", "README", "QA"],
                "evidence_asset_refs": evidence_refs,
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 1.0)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_TOO_SHORT" in codes


def test_strict_release_qa_blocks_unverifiable_recording_evidence_duration(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_ref = {
        "id": "codex-recording",
        "evidence_type": "codex_operation_recording",
        "evidence_clip_path": "assets/evidence/clips/codex-recording.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "codex_operation_video",
        "evidence_clip_style": "codex_operation_recording",
        "target_scene_id": "s1",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["codex_operation_recording"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "requires_real_evidence_asset": True,
                "director_knowledge_refs": {"profile": "open_source_project_intro"},
                "expected_real_evidence": ["Codex app 操作画面"],
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: None)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_DURATION_NOT_VERIFIABLE" in codes


def test_strict_release_qa_blocks_static_recording_evidence_motion(
    tmp_path,
    monkeypatch,
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_ref = {
        "id": "codex-recording",
        "evidence_type": "codex_operation_recording",
        "evidence_clip_path": "assets/evidence/clips/codex-recording.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "codex_operation_video",
        "evidence_clip_style": "codex_operation_recording",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示 Codex app 中一句话触发 lingjian-video 并进入能力门诊",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["codex_operation_recording"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "requires_real_evidence_asset": True,
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "director_knowledge_refs": {"profile": "open_source_project_intro"},
                "expected_real_evidence": ["Codex app 操作画面"],
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 2.4)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_motion_delta",
        lambda path: 0.2 if str(path).endswith("codex-recording.mp4") else 12.0,
    )

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_DETECTED" in codes


def test_strict_release_qa_blocks_codex_recording_without_matching_task_intent(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_ref = {
        "id": "codex-recording",
        "evidence_type": "codex_operation_recording",
        "evidence_clip_path": "assets/evidence/clips/codex-recording.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "codex_operation_video",
        "evidence_clip_style": "codex_operation_recording",
        "target_scene_id": "s1",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["codex_operation_recording"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "requires_real_evidence_asset": True,
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "director_knowledge_refs": {"profile": "open_source_project_intro"},
                "expected_real_evidence": ["Codex app 操作画面"],
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 2.4)
    monkeypatch.setattr("packages.core.qa._sample_frame_motion_delta", lambda path: 12.0)
    monkeypatch.setattr(
        "packages.core.qa._sample_frame_motion_segment_deltas",
        lambda path: [12.0, 12.0],
    )

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE" in codes


def test_strict_release_qa_blocks_codex_recording_without_consent_evidence(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_ref = {
        "id": "codex-recording",
        "evidence_type": "codex_operation_recording",
        "evidence_clip_path": "assets/evidence/clips/codex-recording.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "codex_operation_video",
        "evidence_clip_style": "codex_operation_recording",
        "target_scene_id": "s1",
        "recording_status": "captured",
        "recording_task_redacted": "展示 Codex app 中一句话触发 lingjian-video 并进入能力门诊",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["codex_operation_recording"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/evidence/clips/codex-recording.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "requires_real_evidence_asset": True,
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "director_knowledge_refs": {"profile": "open_source_project_intro"},
                "expected_real_evidence": ["Codex app 操作画面"],
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_SCREEN_RECORDING_CONSENT_NOT_VERIFIABLE" in codes


def test_strict_release_qa_allows_codex_recording_with_matching_task_intent(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_ref = {
        "id": "codex-recording",
        "evidence_type": "codex_operation_recording",
        "evidence_clip_path": "assets/evidence/clips/codex-recording.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "codex_operation_video",
        "evidence_clip_style": "codex_operation_recording",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示 Codex app 中一句话触发 lingjian-video 并进入能力门诊",
        "screen_recording_consent_required": True,
        "screen_recording_consent": True,
        "privacy_notice_zh": "请确认当前屏幕没有私密信息。",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["codex_operation_recording"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "requires_real_evidence_asset": True,
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "director_knowledge_refs": {"profile": "open_source_project_intro"},
                "expected_real_evidence": ["Codex app 操作画面"],
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 2.4)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_SCREEN_RECORDING_CONSENT_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_SCREEN_RECORDING_CONSENT_MISSING" not in codes


def test_strict_release_qa_allows_sufficient_recording_evidence_duration(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    evidence_ref = {
        "id": "codex-recording",
        "evidence_type": "codex_operation_recording",
        "evidence_clip_path": "assets/evidence/clips/codex-recording.mp4",
        "evidence_clip_status": "captured",
        "evidence_visual_source": "codex_operation_video",
        "evidence_clip_style": "codex_operation_recording",
        "target_scene_id": "s1",
        "recording_task_redacted": "展示 Codex app 中一句话触发 lingjian-video 并进入能力门诊",
        "screen_recording_consent_required": True,
        "screen_recording_consent": True,
        "privacy_notice_zh": "请确认当前屏幕没有私密信息。",
    }
    clip_path = project.path / str(evidence_ref["evidence_clip_path"])
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"not a stub")
    _write_minimal_release_manifest(
        project,
        visual_evidence_assets={
            "version": "v1",
            "assets": [evidence_ref],
            "evidence_types": ["codex_operation_recording"],
        },
        scenes=[
            {
                "scene_id": "s1",
                "asset_path": "assets/scenes/s1.mp4",
                "render_source": "video",
                "duration_sec": 4.0,
                "requires_real_evidence_asset": True,
                "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
                "director_knowledge_refs": {"profile": "open_source_project_intro"},
                "expected_real_evidence": ["Codex app 操作画面"],
                "evidence_asset_refs": [evidence_ref],
            }
        ],
    )
    _patch_release_media_checks_ok(monkeypatch)
    monkeypatch.setattr("packages.core.qa._media_duration_sec", lambda path: 2.4)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_TOO_SHORT" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_DURATION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_INTENT_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_DETECTED" not in codes
    assert "RELEASE_SCENE_EVIDENCE_RECORDING_MOTION_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_SCREEN_RECORDING_CONSENT_NOT_VERIFIABLE" not in codes
    assert "RELEASE_SCENE_EVIDENCE_SCREEN_RECORDING_CONSENT_MISSING" not in codes


def test_strict_release_qa_blocks_low_subtitle_contrast_from_sampled_frame(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            raw = bytes([32, 32, 32]) * FRAME_SAMPLE_WIDTH * FRAME_SAMPLE_HEIGHT
            return subprocess.CompletedProcess(command, 0, stdout=raw, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_SUBTITLE_CONTRAST_LOW"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_caption_pixels_outside_safe_area(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "subtitle_burn": True,
                        "caption_cues": [
                            {
                                "text": "灵剪底部字幕",
                                "lines": ["灵剪底部字幕"],
                                "start_sec": 0.0,
                                "end_sec": 1.2,
                            }
                        ],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_frame = _caption_band_frame(center_caption=True)
    moving_frame = _motion_variant(raw_frame)

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            raw = moving_frame if "0.70" in command else raw_frame
            return subprocess.CompletedProcess(command, 0, stdout=raw, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_CAPTION_PIXEL_OUTSIDE_SAFE_AREA"
        for issue in report.hard_failures
    )


def test_strict_release_qa_samples_later_caption_cue_pixels(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "duration_sec": 3.0,
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "subtitle_burn": True,
                        "caption_cues": [
                            {
                                "text": "灵剪底部字幕",
                                "lines": ["灵剪底部字幕"],
                                "start_sec": 0.0,
                                "end_sec": 0.8,
                            },
                            {
                                "text": "后续字幕出界",
                                "lines": ["后续字幕出界"],
                                "start_sec": 1.3,
                                "end_sec": 1.8,
                            },
                        ],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    safe_frame = _caption_band_frame(center_caption=False)
    leaked_frame = _caption_band_frame(center_caption=True)
    moving_frame = _motion_variant(safe_frame)

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            timestamp = command[command.index("-ss") + 1] if "-ss" in command else ""
            if timestamp == "0.70":
                raw = moving_frame
            elif timestamp == "1.55":
                raw = leaked_frame
            else:
                raw = safe_frame
            return subprocess.CompletedProcess(command, 0, stdout=raw, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_CAPTION_PIXEL_OUTSIDE_SAFE_AREA"
        for issue in report.hard_failures
    )


def test_strict_release_qa_blocks_missing_caption_pixels_in_safe_area(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "subtitle_burn": True,
                        "caption_cues": [
                            {
                                "text": "灵剪底部字幕",
                                "lines": ["灵剪底部字幕"],
                                "start_sec": 0.0,
                                "end_sec": 1.2,
                            }
                        ],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_frame = _half_tone_frame(inverted=False)
    moving_frame = _motion_variant(raw_frame)

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            raw = moving_frame if "0.70" in command else raw_frame
            return subprocess.CompletedProcess(command, 0, stdout=raw, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=True)

    assert any(
        issue.code == "RELEASE_CAPTION_PIXEL_NOT_DETECTED"
        for issue in report.hard_failures
    )


def test_release_qa_warns_missing_caption_pixels_in_safe_area_in_non_strict(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "subtitle_burn": True,
                        "caption_cues": [
                            {
                                "text": "灵剪底部字幕",
                                "lines": ["灵剪底部字幕"],
                                "start_sec": 0.0,
                                "end_sec": 1.2,
                            }
                        ],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_frame = _half_tone_frame(inverted=False)
    moving_frame = _motion_variant(raw_frame)

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            raw = moving_frame if "0.70" in command else raw_frame
            return subprocess.CompletedProcess(command, 0, stdout=raw, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=False)

    assert report.release_ready is True
    assert any(
        issue.code == "RELEASE_CAPTION_PIXEL_NOT_DETECTED"
        for issue in report.warnings
    )


def test_strict_release_qa_blocks_caption_pixels_inside_subject_region(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    contract = layout_contract(1, "9:16", "hook")
    contract["subjectRect"] = {"x": 0, "y": 620, "w": 1080, "h": 360}
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "subtitle_burn": True,
                        "layout_contract": contract,
                        "caption_contract": {
                            "position": "底部安全区",
                            "avoid_subject_and_cta": True,
                        },
                        "caption_cues": [
                            {
                                "text": "灵剪底部字幕",
                                "lines": ["灵剪底部字幕"],
                                "start_sec": 0.0,
                                "end_sec": 1.2,
                            }
                        ],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_frame = _caption_band_frame(center_caption=True)
    moving_frame = _motion_variant(raw_frame)

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            raw = moving_frame if "0.70" in command else raw_frame
            return subprocess.CompletedProcess(command, 0, stdout=raw, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=True)
    codes = {issue.code for issue in report.hard_failures}

    assert "RELEASE_CAPTION_PIXEL_OVERLAPS_SUBJECT" in codes


def test_strict_release_qa_uses_review_sheet_v2_subject_region_for_caption_overlap(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "subtitle_burn": True,
                        "director_review_sheet_v2": {
                            "subject_region": {
                                "x": 0,
                                "y": 620,
                                "w": 1080,
                                "h": 360,
                            }
                        },
                        "caption_contract": {
                            "position": "底部安全区",
                            "avoid_subject_and_cta": True,
                        },
                        "caption_cues": [
                            {
                                "text": "灵剪底部字幕",
                                "lines": ["灵剪底部字幕"],
                                "start_sec": 0.0,
                                "end_sec": 1.2,
                            }
                        ],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_frame = _caption_band_frame(center_caption=True)
    moving_frame = _motion_variant(raw_frame)

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            raw = moving_frame if "0.70" in command else raw_frame
            return subprocess.CompletedProcess(command, 0, stdout=raw, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=True)
    codes = {issue.code for issue in report.hard_failures}

    assert "RELEASE_CAPTION_PIXEL_OVERLAPS_SUBJECT" in codes


def test_strict_release_qa_blocks_caption_pixels_inside_cta_region(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    contract = layout_contract(1, "9:16", "cta")
    contract["subjectRect"] = {"x": 96, "y": 220, "w": 888, "h": 520}
    contract["ctaRect"] = {"x": 160, "y": 1450, "w": 760, "h": 220}
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "subtitle_burn": True,
                        "layout_contract": contract,
                        "caption_contract": {
                            "position": "底部安全区",
                            "avoid_subject_and_cta": True,
                        },
                        "caption_cues": [
                            {
                                "text": "关注并 star 灵剪",
                                "lines": ["关注并 star 灵剪"],
                                "start_sec": 0.0,
                                "end_sec": 1.2,
                            }
                        ],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_frame = _caption_band_frame(center_caption=False)
    moving_frame = _motion_variant(raw_frame)

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            raw = moving_frame if "0.70" in command else raw_frame
            return subprocess.CompletedProcess(command, 0, stdout=raw, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=True)
    codes = {issue.code for issue in report.hard_failures}

    assert "RELEASE_CAPTION_PIXEL_OVERLAPS_CTA" in codes


def test_strict_release_qa_allows_caption_pixels_in_bottom_safe_area(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    contract = layout_contract(1, "9:16", "hook")
    contract["subjectRect"] = {"x": 96, "y": 220, "w": 888, "h": 520}
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "subtitle_burn": True,
                        "layout_contract": contract,
                        "caption_contract": {
                            "position": "底部安全区",
                            "avoid_subject_and_cta": True,
                        },
                        "caption_cues": [
                            {
                                "text": "灵剪底部字幕",
                                "lines": ["灵剪底部字幕"],
                                "start_sec": 0.0,
                                "end_sec": 1.2,
                            }
                        ],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_frame = _caption_band_frame(center_caption=False)
    moving_frame = _motion_variant(raw_frame)

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            raw = moving_frame if "0.70" in command else raw_frame
            return subprocess.CompletedProcess(command, 0, stdout=raw, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_CAPTION_PIXEL_OUTSIDE_SAFE_AREA" not in codes
    assert "RELEASE_CAPTION_PIXEL_OVERLAPS_SUBJECT" not in codes
    assert "RELEASE_CAPTION_PIXEL_OVERLAPS_CTA" not in codes
    assert "RELEASE_CAPTION_PIXEL_NOT_DETECTED" not in codes


def test_strict_release_qa_prefers_caption_bbox_for_overlap_geometry(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    contract = layout_contract(1, "16:9", "hook")
    contract["subjectRect"] = {"x": 820, "y": 110, "w": 960, "h": 660}
    contract["ctaRect"] = {"x": 1360, "y": 760, "w": 360, "h": 110}
    caption_bbox = {
        "x": 211,
        "y": 881,
        "w": 1497,
        "h": 108,
        "canvas_width": 1920,
        "canvas_height": 1080,
        "unit": "px",
    }
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "16:9",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                        "render_width": 1920,
                        "render_height": 1080,
                        "subtitle_burn": True,
                        "layout_contract": contract,
                        "caption_contract": {
                            "position": "底部安全区",
                            "avoid_subject_and_cta": True,
                        },
                        "caption_cues": [
                            {
                                "text": "灵剪底部字幕",
                                "lines": ["灵剪底部字幕"],
                                "start_sec": 0.0,
                                "end_sec": 1.2,
                                "caption_bbox": caption_bbox,
                            }
                        ],
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_frame = _caption_band_frame(center_caption=True)
    moving_frame = _motion_variant(raw_frame)

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            raw = moving_frame if "0.70" in command else raw_frame
            return subprocess.CompletedProcess(command, 0, stdout=raw, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=True)

    codes = {issue.code for issue in report.hard_failures}
    assert "RELEASE_CAPTION_PIXEL_OUTSIDE_SAFE_AREA" not in codes
    assert "RELEASE_CAPTION_PIXEL_OVERLAPS_SUBJECT" not in codes
    assert "RELEASE_CAPTION_PIXEL_OVERLAPS_CTA" not in codes
    assert "RELEASE_CAPTION_PIXEL_NOT_DETECTED" not in codes


def test_strict_release_qa_blocks_static_video_from_sampled_frames(
    tmp_path, monkeypatch
):
    project = ProjectRef(tmp_path / "project", "project")
    release_dir = project.path / "renders" / "release" / "douyin"
    release_dir.mkdir(parents=True)
    (release_dir / "video.mp4").write_bytes(b"not a stub")
    (release_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "mode": "release",
                "platform": "douyin",
                "language": "zh-CN",
                "ratio": "9:16",
                "video_path": "renders/release/douyin/video.mp4",
                "visual_total": 1,
                "visual_real_count": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "asset_path": "assets/scenes/s1.mp4",
                        "render_source": "video",
                    }
                ],
                "providers": [
                    {"id": "real_llm", "kind": "llm", "is_mock": False},
                    {"id": "volcengine_tts", "kind": "tts", "is_mock": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_frame = _high_contrast_static_frame()

    def fake_run(command, **kwargs):
        if "-show_entries" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
                stderr="",
            )
        if "rawvideo" in command:
            return subprocess.CompletedProcess(command, 0, stdout=raw_frame, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("packages.core.qa.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("packages.core.qa.subprocess.run", fake_run)

    report = run_qa(project, release=True, strict=True)

    assert report.release_ready is False
    assert any(
        issue.code == "RELEASE_VISUAL_MOTION_NOT_DETECTED"
        for issue in report.hard_failures
    )
