from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import typer

from packages.core.approvals import approve_target, validate_render_gate
from packages.core.capabilities import detect_capabilities
from packages.core.credentials import credential_status, forget_credential
from packages.core.doctor import run_doctor
from packages.core.errors import LingjianError
from packages.core.exporting import export_project
from packages.core.project import ProjectRef, init_project, reindex_project, status_project
from packages.core.qa import run_qa
from packages.core.rendering import render_project
from providers.registry import resolve_provider

app = typer.Typer(no_args_is_help=True)
ingest_app = typer.Typer()
approve_app = typer.Typer()
credentials_app = typer.Typer(no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")
app.add_typer(approve_app, name="approve")
app.add_typer(credentials_app, name="credentials")


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        typer.echo(payload)


def _fail(exc: LingjianError, as_json: bool) -> None:
    _emit(
        {
            "ok": False,
            "error_code": exc.error_code,
            "message_zh": exc.message_zh,
            "hint": exc.hint,
            **exc.details,
        },
        as_json,
    )
    raise typer.Exit(1)


def _approval_exists(project: ProjectRef, target: str) -> bool:
    approvals_path = project.path / "artifacts" / "approvals.json"
    if not approvals_path.exists():
        return False
    approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    return target in approvals


def _pause_for_approval(project: ProjectRef, target: str, artifact: str, as_json: bool) -> None:
    next_command = f"uv run lj approve {target} {project.path} --approved-by <用户> --json"
    _emit(
        {
            "ok": True,
            "status": "awaiting_approval",
            "current_step": target,
            "artifact": artifact,
            "message_zh": f"已生成 {target} 产物,请人工审阅后再批准或驳回。",
            "actions": [
                {"label": "查看", "command": f"cat {project.path / artifact}"},
                {"label": "批准", "command": next_command},
                {"label": "驳回", "command": f"重新运行 lj {target} 或修改输入后再跑 lj run"},
            ],
            "next_command": next_command,
        },
        as_json,
    )


def _ensure_text_input(project: ProjectRef, input_file: Path | None) -> bool:
    assets_path = project.path / "assets" / "input_assets.json"
    if assets_path.exists():
        return False
    if input_file is None:
        raise LingjianError(
            "INPUT_REQUIRED",
            "缺少输入素材。",
            "首次运行 lj run 时请传入 --input-file。",
        )
    assets_path.parent.mkdir(parents=True, exist_ok=True)
    text = input_file.read_text(encoding="utf-8")
    assets_path.write_text(
        json.dumps(
            [{"type": "text", "source_uri": str(input_file), "language_hint": None, "text": text}],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return True


def _write_script_for_run(
    project: ProjectRef,
    type_: str,
    platform: str,
    language: str,
    ratio: str,
    duration: int,
    provider: str,
) -> bool:
    from packages.core.artifacts import artifact_path, read_json, write_artifact

    current_path = artifact_path(project, "script")
    if current_path.exists():
        return False
    provider_ref = resolve_provider(provider, "llm")
    scenes = [{"id": "s1", "narration_text": "这是一段测试脚本。"}]
    generate_script = getattr(provider_ref, "generate_script", None)
    if callable(generate_script):
        generated = generate_script(
            {
                "type": type_,
                "platform": platform,
                "language": language,
                "ratio": ratio,
                "target_duration_sec": duration,
            }
        )
        if isinstance(generated.get("scenes"), list) and generated["scenes"]:
            scenes = generated["scenes"]
    revision = read_json(current_path).get("revision", 0) + 1 if current_path.exists() else 1
    write_artifact(
        project,
        "script",
        {
            "id": "script",
            "revision": revision,
            "type": type_,
            "platform": platform,
            "language": language,
            "ratio": ratio,
            "target_duration_sec": duration,
            "provider_id": provider_ref.id,
            "provider_is_mock": provider_ref.is_mock,
            "scenes": scenes,
        },
    )
    return True


def _write_voice_for_run(project: ProjectRef, provider: str, voice_id: str) -> bool:
    return _write_voice_plan(project, provider, voice_id, None)


def _probe_audio_duration(audio_path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 1.0
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
                str(audio_path),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1.0
    if completed.returncode != 0:
        return 1.0
    try:
        payload = json.loads(completed.stdout or "{}")
        duration = float(payload.get("format", {}).get("duration") or 1.0)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 1.0
    return max(duration, 1.0)


def _script_scene_ids(project: ProjectRef) -> list[str]:
    from packages.core.artifacts import artifact_path, read_json

    script_path = artifact_path(project, "script")
    if not script_path.exists():
        return ["s1"]
    script_data = read_json(script_path)
    scene_ids = [
        str(scene.get("id") or scene.get("scene_id") or f"s{index}")
        for index, scene in enumerate(script_data.get("scenes", []), start=1)
        if isinstance(scene, dict)
    ]
    return scene_ids or ["s1"]


def _write_user_audio_voice_plan(project: ProjectRef, audio_file: Path) -> None:
    from packages.core.artifacts import write_artifact

    if not audio_file.exists() or not audio_file.is_file():
        raise LingjianError(
            "USER_AUDIO_NOT_FOUND",
            "未找到用户提供的口播音频。",
            "请传入本机存在的 wav/mp3/m4a/aiff 音频文件。",
            {"audio_file": str(audio_file)},
        )
    suffix = audio_file.suffix if audio_file.suffix else ".audio"
    audio_path = project.path / "artifacts" / "voice_segments" / f"user_audio{suffix}"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(audio_file, audio_path)
    duration = _probe_audio_duration(audio_path)
    scene_ids = _script_scene_ids(project)
    per_scene_duration = max(duration / max(len(scene_ids), 1), 0.5)
    segments = []
    for index, scene_id in enumerate(scene_ids):
        segment = {"scene_id": scene_id, "duration_sec": per_scene_duration}
        if index == 0:
            segment["audio_path"] = str(audio_path.relative_to(project.path))
        segments.append(segment)
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "user_audio",
            "provider_is_mock": False,
            "source_type": "user-recorded-audio",
            "voice_id": "user-recorded",
            "segments": segments,
            "total_duration_sec": duration,
        },
    )


def _write_voice_plan(
    project: ProjectRef,
    provider: str,
    voice_id: str,
    audio_file: Path | None,
) -> bool:
    from packages.core.artifacts import artifact_path, read_json, write_artifact

    current_path = artifact_path(project, "voice")
    if current_path.exists():
        return False
    if audio_file is not None:
        _write_user_audio_voice_plan(project, audio_file)
        return True
    provider_ref = _resolve_tts_provider(provider)
    audio_path = project.path / "artifacts" / "voice_segments" / "s1.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    duration = 1.0
    synthesize = getattr(provider_ref, "synthesize", None)
    if callable(synthesize):
        script_path = artifact_path(project, "script")
        script_data = read_json(script_path) if script_path.exists() else {"scenes": []}
        narration = " ".join(
            str(scene.get("narration_text", ""))
            for scene in script_data.get("scenes", [])
            if isinstance(scene, dict)
        ).strip()
        audio_bytes, duration = synthesize({"voice": voice_id, "text": narration})
        audio_path.write_bytes(audio_bytes)
    else:
        audio_path.write_bytes(b"mock audio")
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": provider_ref.id,
            "provider_is_mock": provider_ref.is_mock,
            "voice_id": voice_id,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": duration,
                }
            ],
            "total_duration_sec": duration,
        },
    )
    return True


def _resolve_tts_provider(provider: str):
    if provider != "auto":
        return resolve_provider(provider, "tts")
    try:
        return resolve_provider("auto", "tts")
    except LingjianError:
        return resolve_provider("mock", "tts")


def _visual_generator_for_scene(project: ProjectRef, scene_id: str) -> dict:
    assets_dir = project.path / "assets" / "scenes"
    video_asset = assets_dir / f"{scene_id}.mp4"
    image_asset = assets_dir / f"{scene_id}.png"
    if video_asset.exists():
        return {
            "generator": "user-asset",
            "asset_path": str(video_asset.relative_to(project.path)),
            "expected_asset_path": str(video_asset.relative_to(project.path)),
            "subtitle_burn": False,
            "motion": {"main": "asset_video", "one_main_only": True},
            "motion_spec": {"main": "asset_video", "one_main_only": True},
        }
    if image_asset.exists():
        return {
            "generator": "user-asset",
            "asset_path": str(image_asset.relative_to(project.path)),
            "expected_asset_path": str(image_asset.relative_to(project.path)),
            "subtitle_burn": True,
            "motion": {"main": "kenburns_zoom_in", "one_main_only": True},
            "motion_spec": {"main": "kenburns_zoom_in", "one_main_only": True},
        }
    capabilities = detect_capabilities()
    best_visual = capabilities.groups["visuals"].best.id
    if best_visual == "host_hyperframes":
        return {
            "generator": "hyperframes",
            "asset_path": f"assets/scenes/{scene_id}.mp4",
            "expected_asset_path": f"assets/scenes/{scene_id}.mp4",
            "subtitle_burn": True,
            "motion": {"main": "kinetic_reveal", "one_main_only": True},
            "motion_spec": {"main": "kinetic_reveal", "one_main_only": True},
        }
    if best_visual == "host_remotion":
        return {
            "generator": "remotion",
            "asset_path": f"assets/scenes/{scene_id}.mp4",
            "expected_asset_path": f"assets/scenes/{scene_id}.mp4",
            "subtitle_burn": True,
            "motion": {"main": "programmatic_scene", "one_main_only": True},
            "motion_spec": {"main": "programmatic_scene", "one_main_only": True},
        }
    if best_visual == "host_imagegen":
        return {
            "generator": "image-gen",
            "asset_path": f"assets/scenes/{scene_id}.png",
            "expected_asset_path": f"assets/scenes/{scene_id}.png",
            "subtitle_burn": True,
            "motion": {"main": "kenburns_zoom_in", "one_main_only": True},
            "motion_spec": {"main": "kenburns_zoom_in", "one_main_only": True},
        }
    return {
        "generator": "fallback_solid",
        "asset_path": None,
        "expected_asset_path": None,
        "subtitle_burn": True,
        "motion": {"main": "solid_card", "one_main_only": True},
        "motion_spec": {"main": "solid_card", "one_main_only": True},
    }


def _visual_prompt(
    narration: str,
    ratio: str,
    visual_hint: str = "",
    on_screen_text: str = "",
) -> str:
    hint = f"场景提示:{visual_hint}。" if visual_hint else ""
    keyword = f"视觉关键词:{on_screen_text}。" if on_screen_text else ""
    return (
        "为竖屏短视频生成一镜画面。"
        f"画幅 {ratio},风格为干净的中文产品说明动态图形,主体清晰,背景简洁。"
        f"{hint}{keyword}"
        f"旁白/画面信息:{narration}"
    )


def _visual_scenes_for_project(project: ProjectRef, ratio: str) -> list[dict]:
    from packages.core.artifacts import artifact_path, read_json

    script_path = artifact_path(project, "script")
    voice_path = artifact_path(project, "voice")
    script = read_json(script_path) if script_path.exists() else {"scenes": []}
    voice = read_json(voice_path) if voice_path.exists() else {"segments": []}
    script_scenes = [
        scene for scene in script.get("scenes", []) if isinstance(scene, dict)
    ]
    voice_segments = [
        segment
        for segment in voice.get("segments", [])
        if isinstance(segment, dict) and segment.get("scene_id")
    ]
    voice_durations = {
        str(segment.get("scene_id")): float(segment.get("duration_sec") or 1.0)
        for segment in voice_segments
        if isinstance(segment, dict) and segment.get("scene_id")
    }
    use_voice_durations = len(voice_segments) == len(script_scenes)
    scenes = []
    for index, script_scene in enumerate(script_scenes, start=1):
        scene_id = str(script_scene.get("id") or script_scene.get("scene_id") or f"s{index}")
        route = _visual_generator_for_scene(project, scene_id)
        narration = str(script_scene.get("narration_text") or "")
        script_duration = float(script_scene.get("duration_sec") or 1.0)
        duration = (
            voice_durations.get(scene_id, script_duration)
            if use_voice_durations
            else script_duration
        )
        visual_hint = str(script_scene.get("visual_prompt") or "")
        on_screen_text = str(script_scene.get("on_screen_text") or "")
        scenes.append(
            {
                "scene_id": scene_id,
                "role": script_scene.get("role"),
                "on_screen_text": on_screen_text,
                "narration_text": narration,
                "duration_sec": max(duration, 0.5),
                "visual_prompt": _visual_prompt(narration, ratio, visual_hint, on_screen_text),
                "brief": {
                    "aspect": ratio,
                    "safe_zone": "下三分之一留字幕",
                    "forbidden": "画面别再嵌大段文字",
                },
                **route,
            }
        )
    return scenes or [
        {
            "scene_id": "s1",
            "narration_text": "灵剪",
            "duration_sec": 1.0,
            "visual_prompt": _visual_prompt("灵剪", ratio),
            "generator": "fallback_solid",
            "asset_path": None,
            "expected_asset_path": None,
            "motion": {"main": "solid_card", "one_main_only": True},
            "motion_spec": {"main": "solid_card", "one_main_only": True},
            "subtitle_burn": True,
            "brief": {
                "aspect": ratio,
                "safe_zone": "下三分之一留字幕",
                "forbidden": "画面别再嵌大段文字",
            },
        }
    ]


def _write_visuals_for_run(project: ProjectRef, engine: str, template: str, ratio: str) -> bool:
    from packages.core.artifacts import artifact_path, write_artifact

    if artifact_path(project, "visuals").exists():
        return False
    scenes = _visual_scenes_for_project(project, ratio)
    visual_real_count = sum(1 for scene in scenes if scene["generator"] != "fallback_solid")
    write_artifact(
        project,
        "visuals",
        {
            "id": "visuals",
            "ratio": ratio,
            "engine": engine,
            "template": template,
            "scenes": scenes,
            "visual_real_count": visual_real_count,
            "visual_total": len(scenes),
        },
    )
    return True


@app.command()
def setup(json_output: bool = typer.Option(False, "--json")) -> None:
    report = detect_capabilities()
    payload = report.public_dict()
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return

    typer.echo("灵剪能力检测")
    typer.echo(report.summary_zh)
    typer.echo("预览档:零配置可用,使用 mock 只能预览,不能 release。")
    typer.echo(
        "发布档:需要真实 LLM、Kokoro/云 TTS 或用户录音、真实画面、"
        "FFmpeg/ffprobe/drawtext/AAC 与中文字体全部就绪。"
    )
    inherited = []
    equipped = []
    missing = []
    optional = []
    for kind, group in payload["capabilities"].items():
        best = group["best"]
        item = f"{kind}: {best['label_zh']} ({best['source_type']})"
        if best["source_type"] == "inherited-cli" and best["configured"]:
            inherited.append(item)
            continue
        if kind == "tts" and best.get("quality_tier") == "preview":
            missing.append(f"tts: Kokoro/云 TTS 或用户录音(当前 {best['label_zh']} 仅预览)")
            continue
        if kind == "visuals" and not best["safe_for_release"]:
            missing.append("visuals: 真实画面插件或每镜 mp4/png 素材")
            continue
        if best["safe_for_release"]:
            equipped.append(item)
        else:
            missing.append(item)
    optional.append("可选增强:平台模板、封面、多平台文案、更多画面/语音 provider")
    typer.echo("已继承:")
    for item in inherited or ["无"]:
        typer.echo(f"- {item}")
    typer.echo("已具备:")
    for item in equipped or ["无"]:
        typer.echo(f"- {item}")
    typer.echo("必须补齐:")
    for item in missing or ["无"]:
        typer.echo(f"- {item}")
    typer.echo("可选增强:")
    for item in optional:
        typer.echo(f"- {item}")
    if report.next_steps:
        typer.echo("下一步:")
        for step in report.next_steps:
            typer.echo(f"- {step}")
    typer.echo("说明:订阅 CLI 通常只提供 LLM;TTS 与 FFmpeg 仍可能需要本机能力或单独配置。")


@credentials_app.command("status")
def credentials_status(json_output: bool = typer.Option(False, "--json")) -> None:
    _emit(credential_status(), json_output)


@credentials_app.command("forget")
def credentials_forget(name: str, json_output: bool = typer.Option(False, "--json")) -> None:
    _emit(forget_credential(name), json_output)


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json")) -> None:
    result = run_doctor()
    if json_output:
        typer.echo(result.model_dump_json(exclude_none=True))
    else:
        typer.echo("ready" if result.ready else "not ready")
    raise typer.Exit(result.exit_code)


@app.command()
def init(
    project: Path,
    name: str = typer.Option(...),
    json_output: bool = typer.Option(False, "--json"),
):
    ref = init_project(project, name)
    _emit({"ok": True, "project": str(ref.path), "name": ref.name}, json_output)


@ingest_app.command("text")
def ingest_text(
    project: Path,
    file: Path = typer.Option(...),
    language: Optional[str] = typer.Option(None),
    json_output: bool = typer.Option(False, "--json"),
):
    ref = ProjectRef(project, project.name)
    assets = ref.path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    text = file.read_text(encoding="utf-8")
    (assets / "input_assets.json").write_text(
        json.dumps(
            [{"type": "text", "source_uri": str(file), "language_hint": language, "text": text}],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _emit({"ok": True, "status": "input_ready"}, json_output)


@ingest_app.command("url")
def ingest_url(
    project: Path,
    url: str = typer.Option(...),
    screenshot: bool = typer.Option(False, "--screenshot"),
    json_output: bool = typer.Option(False, "--json"),
):
    ref = ProjectRef(project, project.name)
    assets = ref.path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "input_assets.json").write_text(
        json.dumps(
            [
                {
                    "type": "url",
                    "source_uri": url,
                    "screenshot_opt_in": screenshot,
                    "is_untrusted_input": True,
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _emit(
        {
            "ok": True,
            "status": "input_ready",
            "is_untrusted_input": True,
            "screenshot_opt_in": screenshot,
        },
        json_output,
    )


@ingest_app.command("image")
def ingest_image(
    project: Path,
    file: Path = typer.Option(...),
    role: str = typer.Option(...),
    json_output: bool = typer.Option(False, "--json"),
):
    ref = ProjectRef(project, project.name)
    assets = ref.path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "input_assets.json").write_text(
        json.dumps(
            [
                {
                    "type": "image",
                    "source_uri": str(file),
                    "role": role,
                    "ocr_status": "not_requested",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _emit({"ok": True, "status": "input_ready", "role": role}, json_output)


@app.command()
def extract(
    project: Path,
    provider: Optional[str] = typer.Option(None, "--provider"),
    url_extractor: Optional[str] = typer.Option(None, "--url-extractor"),
    ocr_provider: Optional[str] = typer.Option(None, "--ocr-provider"),
    json_output: bool = typer.Option(False, "--json"),
):
    _emit(
        {
            "ok": True,
            "status": "extracted",
            "project": str(project),
            "routing": {
                "legacy_provider": provider,
                "url_extractor": url_extractor or "trafilatura",
                "ocr_provider": ocr_provider or "none",
            },
        },
        json_output,
    )


@app.command()
def script(
    project: Path,
    type: str = typer.Option(...),
    platform: str = typer.Option(...),
    language: str = typer.Option(...),
    ratio: str = typer.Option(...),
    duration: int = typer.Option(45),
    provider: str = typer.Option("mock"),
    json_output: bool = typer.Option(False, "--json"),
):
    from packages.core.artifacts import artifact_path, read_json, write_artifact

    ref = ProjectRef(project, project.name)
    try:
        provider_ref = resolve_provider(provider, "llm")
    except LingjianError as exc:
        _fail(exc, json_output)
    current_path = artifact_path(ref, "script")
    revision = read_json(current_path).get("revision", 0) + 1 if current_path.exists() else 1
    scenes = [{"id": "s1", "narration_text": "这是一段测试脚本。"}]
    generate_script = getattr(provider_ref, "generate_script", None)
    if callable(generate_script):
        try:
            generated = generate_script(
                {
                    "type": type,
                    "platform": platform,
                    "language": language,
                    "ratio": ratio,
                    "target_duration_sec": duration,
                }
            )
        except LingjianError as exc:
            _fail(exc, json_output)
        if isinstance(generated.get("scenes"), list) and generated["scenes"]:
            scenes = generated["scenes"]
    write_artifact(
        ref,
        "script",
        {
            "id": "script",
            "revision": revision,
            "type": type,
            "platform": platform,
            "language": language,
            "ratio": ratio,
            "target_duration_sec": duration,
            "provider_id": provider_ref.id,
            "provider_is_mock": provider_ref.is_mock,
            "scenes": scenes,
        },
    )
    _emit(
        {"ok": True, "status": "awaiting_review", "artifact": "artifacts/script.json"},
        json_output,
    )


@approve_app.command("script")
def approve_script(
    project: Path,
    approved_by: str = typer.Option(...),
    comment: Optional[str] = typer.Option(None),
    json_output: bool = typer.Option(False, "--json"),
):
    approval = approve_target(ProjectRef(project, project.name), "script", approved_by, comment)
    _emit({"ok": True, "approval": approval}, json_output)


@app.command()
def voice(
    project: Path,
    provider: str = typer.Option("auto"),
    voice: str = typer.Option(...),
    audio_file: Optional[Path] = typer.Option(None, "--audio-file"),
    json_output: bool = typer.Option(False, "--json"),
):
    ref = ProjectRef(project, project.name)
    if audio_file is not None:
        try:
            _write_voice_plan(ref, provider, voice, audio_file)
        except LingjianError as exc:
            _fail(exc, json_output)
        _emit(
            {"ok": True, "status": "awaiting_review", "artifact": "artifacts/voice_plan.json"},
            json_output,
        )
        return
    from packages.core.artifacts import artifact_path, read_json, write_artifact

    try:
        provider_ref = _resolve_tts_provider(provider)
    except LingjianError as exc:
        _fail(exc, json_output)
    audio_path = ref.path / "artifacts" / "voice_segments" / "s1.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    duration = 1.0
    synthesize = getattr(provider_ref, "synthesize", None)
    if callable(synthesize):
        script_path = artifact_path(ref, "script")
        script = read_json(script_path) if script_path.exists() else {"scenes": []}
        narration = " ".join(
            str(scene.get("narration_text", ""))
            for scene in script.get("scenes", [])
            if isinstance(scene, dict)
        ).strip()
        try:
            audio_bytes, duration = synthesize({"voice": voice, "text": narration})
        except LingjianError as exc:
            _fail(exc, json_output)
        audio_path.write_bytes(audio_bytes)
    else:
        audio_path.write_bytes(b"mock audio")
    write_artifact(
        ref,
        "voice",
        {
            "id": "voice",
            "provider_id": provider_ref.id,
            "provider_is_mock": provider_ref.is_mock,
            "voice_id": voice,
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": duration,
                }
            ],
            "total_duration_sec": duration,
        },
    )
    _emit(
        {"ok": True, "status": "awaiting_review", "artifact": "artifacts/voice_plan.json"},
        json_output,
    )


@approve_app.command("voice")
def approve_voice(
    project: Path,
    approved_by: str = typer.Option(...),
    comment: Optional[str] = typer.Option(None),
    json_output: bool = typer.Option(False, "--json"),
):
    approval = approve_target(ProjectRef(project, project.name), "voice", approved_by, comment)
    _emit({"ok": True, "approval": approval}, json_output)


@app.command()
def visuals(
    project: Path,
    engine: str = typer.Option("ffmpeg_card"),
    template: str = typer.Option("card_default"),
    ratio: str = typer.Option("9:16"),
    json_output: bool = typer.Option(False, "--json"),
):
    from packages.core.artifacts import write_artifact

    ref = ProjectRef(project, project.name)
    scenes = _visual_scenes_for_project(ref, ratio)
    visual_real_count = sum(1 for scene in scenes if scene["generator"] != "fallback_solid")
    write_artifact(
        ref,
        "visuals",
        {
            "id": "visuals",
            "ratio": ratio,
            "engine": engine,
            "template": template,
            "scenes": scenes,
            "visual_real_count": visual_real_count,
            "visual_total": len(scenes),
        },
    )
    _emit(
        {"ok": True, "status": "awaiting_review", "artifact": "artifacts/visual_plan.json"},
        json_output,
    )


@approve_app.command("visuals")
def approve_visuals(
    project: Path,
    approved_by: str = typer.Option(...),
    comment: Optional[str] = typer.Option(None),
    json_output: bool = typer.Option(False, "--json"),
):
    approval = approve_target(ProjectRef(project, project.name), "visuals", approved_by, comment)
    _emit({"ok": True, "approval": approval}, json_output)


@app.command()
def render(
    project: Path,
    platform: str = typer.Option(...),
    language: str = typer.Option(...),
    ratio: str = typer.Option(...),
    release: bool = typer.Option(False, "--release"),
    real: bool = typer.Option(False, "--real"),
    json_output: bool = typer.Option(False, "--json"),
):
    ref = ProjectRef(project, project.name)
    error = validate_render_gate(ref)
    if error:
        payload = {
            "ok": False,
            "error_code": error.error_code,
            "message_zh": error.message_zh,
            "hint": error.hint,
            **error.details,
        }
        _emit(payload, json_output)
        raise typer.Exit(1)
    try:
        render_result = render_project(
            ref,
            platform,
            language,
            ratio,
            mode="release" if release else "preview",
            real_preview=real,
        )
    except LingjianError as exc:
        _fail(exc, json_output)
    _emit(
        {
            "ok": True,
            "status": "rendered",
            "mode": render_result.mode,
            "video_path": str(render_result.video_path),
            "platform": platform,
            "language": language,
            "ratio": ratio,
        },
        json_output,
    )


@app.command()
def preview(
    project: Path,
    platform: str = typer.Option(...),
    language: str = typer.Option(...),
    ratio: str = typer.Option(...),
    real: bool = typer.Option(False, "--real"),
    json_output: bool = typer.Option(False, "--json"),
):
    try:
        result = render_project(
            ProjectRef(project, project.name),
            platform,
            language,
            ratio,
            mode="preview",
            real_preview=real,
        )
    except LingjianError as exc:
        _fail(exc, json_output)
    _emit(
        {
            "ok": True,
            "mode": result.mode,
            "video_path": str(result.video_path),
            "manifest_path": str(result.manifest_path),
        },
        json_output,
    )


@app.command()
def qa(
    project: Path,
    release: bool = typer.Option(False, "--release"),
    strict: bool = typer.Option(False, "--strict"),
    platform: str = typer.Option("douyin"),
    json_output: bool = typer.Option(False, "--json"),
):
    report = run_qa(
        ProjectRef(project, project.name),
        release=release,
        platform=platform,
        strict=strict,
    )
    _emit(
        {
            "ok": True,
            "release_ready": report.release_ready,
            "hard_failures": [asdict(issue) for issue in report.hard_failures],
            "warnings": [asdict(issue) for issue in report.warnings],
            "info": [asdict(issue) for issue in report.info],
        },
        json_output,
    )


@app.command()
def export(
    project: Path,
    platform: Optional[str] = typer.Option(None),
    language: str = typer.Option("zh-CN"),
    ratio: str = typer.Option("9:16"),
    all_platforms: bool = typer.Option(False, "--all-platforms"),
    release: bool = typer.Option(False, "--release"),
    strict: bool = typer.Option(False, "--strict"),
    json_output: bool = typer.Option(False, "--json"),
):
    platforms = (
        ["douyin", "xiaohongshu", "bilibili", "youtube", "youtube_shorts"]
        if all_platforms
        else [platform]
    )
    if any(item is None for item in platforms):
        _fail(
            LingjianError(
                "INVALID_ARGUMENT",
                "缺少导出平台。",
                "请传入 --platform,或使用 --all-platforms。",
            ),
            json_output,
        )
    packages = []
    try:
        for item in platforms:
            package = export_project(
                ProjectRef(project, project.name),
                str(item),
                language,
                ratio,
                release=release,
                strict=strict,
            )
            packages.append(
                {
                    "platform": item,
                    "export_dir": str(package.export_dir),
                    "export_manifest": package.export_manifest,
                }
            )
    except LingjianError as exc:
        _fail(exc, json_output)
    _emit(
        {
            "ok": True,
            "export_dir": packages[0]["export_dir"],
            "exports": packages,
            "release": release,
            "strict": strict,
            "export_manifest": packages[0]["export_manifest"],
        },
        json_output,
    )


@app.command("run")
def run_workflow(
    project: Path,
    name: Optional[str] = typer.Option(None, "--name"),
    input_file: Optional[Path] = typer.Option(None, "--input-file"),
    type_: str = typer.Option("product", "--type"),
    platform: str = typer.Option("douyin", "--platform"),
    language: str = typer.Option("zh-CN", "--language"),
    ratio: str = typer.Option("9:16", "--ratio"),
    duration: int = typer.Option(45, "--duration"),
    script_provider: str = typer.Option("mock", "--script-provider"),
    voice_provider: str = typer.Option("auto", "--voice-provider"),
    voice: str = typer.Option("test-voice", "--voice"),
    voice_audio_file: Optional[Path] = typer.Option(None, "--voice-audio-file"),
    engine: str = typer.Option("ffmpeg_card", "--engine"),
    template: str = typer.Option("product", "--template"),
    release: bool = typer.Option(False, "--release"),
    strict: bool = typer.Option(False, "--strict"),
    yes: bool = typer.Option(False, "--yes"),
    approved_by: str = typer.Option("ci", "--approved-by"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    ref = ProjectRef(project, name or project.name)
    steps: list[str] = []
    try:
        if release:
            doctor_result = run_doctor()
            required_items = list(doctor_result.required)
            if voice_audio_file is not None:
                required_items = [
                    item for item in required_items if item.id != "real_tts_provider"
                ]
            if required_items:
                missing = [item.id for item in required_items]
                raise LingjianError(
                    "DOCTOR_NOT_READY",
                    "发布档需要 doctor ready 后才能运行。",
                    "请先按 required 缺项补齐能力。",
                    {"missing": missing},
                )
        if not (ref.path / "project.yaml").exists():
            init_project(ref.path, ref.name)
            steps.append("init")
        if _ensure_text_input(ref, input_file):
            steps.append("ingest")
        steps.append("extract")
        if _write_script_for_run(ref, type_, platform, language, ratio, duration, script_provider):
            steps.append("script")
        if not _approval_exists(ref, "script"):
            if not yes:
                _pause_for_approval(ref, "script", "artifacts/script.json", json_output)
                return
            approve_target(ref, "script", approved_by)
            steps.append("approve_script")
        if _write_voice_plan(ref, voice_provider, voice, voice_audio_file):
            steps.append("voice")
        if not _approval_exists(ref, "voice"):
            if not yes:
                _pause_for_approval(ref, "voice", "artifacts/voice_plan.json", json_output)
                return
            approve_target(ref, "voice", approved_by)
            steps.append("approve_voice")
        if _write_visuals_for_run(ref, engine, template, ratio):
            steps.append("visuals")
        if not _approval_exists(ref, "visuals"):
            if not yes:
                _pause_for_approval(ref, "visuals", "artifacts/visual_plan.json", json_output)
                return
            approve_target(ref, "visuals", approved_by)
            steps.append("approve_visuals")
        render_result = render_project(
            ref,
            platform,
            language,
            ratio,
            mode="release" if release else "preview",
        )
        steps.append("render")
        qa_report = run_qa(ref, release=release, platform=platform, strict=strict)
        steps.append("qa")
        if qa_report.hard_failures:
            _emit(
                {
                    "ok": False,
                    "status": "qa_blocking",
                    "mode": render_result.mode,
                    "video_path": str(render_result.video_path),
                    "steps": steps,
                    "qa": {
                        "release_ready": qa_report.release_ready,
                        "hard_failures": [asdict(issue) for issue in qa_report.hard_failures],
                        "warnings": [asdict(issue) for issue in qa_report.warnings],
                        "info": [asdict(issue) for issue in qa_report.info],
                    },
                },
                json_output,
            )
            raise typer.Exit(1)
        package = export_project(ref, platform, language, ratio, release=release, strict=strict)
        steps.append("export")
    except LingjianError as exc:
        _fail(exc, json_output)
    _emit(
        {
            "ok": True,
            "status": "exported",
            "mode": "release" if release else "preview",
            "strict": strict,
            "steps": steps,
            "video_path": str(render_result.video_path),
            "qa": {
                "release_ready": qa_report.release_ready,
                "hard_failures": [asdict(issue) for issue in qa_report.hard_failures],
                "warnings": [asdict(issue) for issue in qa_report.warnings],
                "info": [asdict(issue) for issue in qa_report.info],
            },
            "export_dir": str(package.export_dir),
            "export_manifest": package.export_manifest,
        },
        json_output,
    )


@app.command()
def reindex(project: Path, json_output: bool = typer.Option(False, "--json")):
    reindex_project(project)
    _emit({"ok": True, "status": status_project(project)}, json_output)


@app.command()
def status(project: Path, json_output: bool = typer.Option(False, "--json")):
    _emit({"ok": True, **status_project(project)}, json_output)


if __name__ == "__main__":
    sys.exit(app())
