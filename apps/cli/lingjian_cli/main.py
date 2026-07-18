from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import typer

from packages.core.approvals import approve_target, validate_render_gate
from packages.core.capabilities import detect_capabilities
from packages.core.credentials import (
    credential_status,
    forget_credential,
    inject_stored_credentials,
)
from packages.core.director_contract import DEFAULT_STYLE as _DEFAULT_STYLE
from packages.core.director_contract import STYLE_LOCKS as _STYLE_LOCKS
from packages.core.director_contract import (
    asset_diagnosis,
    asset_diagnosis_summary,
    director_board,
    director_knowledge_base_v1,
    director_review_sheet_markdown,
    director_review_sheet_v2,
    director_route_policy,
    infer_content_profile,
    paid_engine_notice,
    plan_summary,
    profile_preset,
    remotion_license_notice,
    scene_director_contract,
    script_generation_contract,
    self_check_visual_scenes,
    visual_brief,
)
from packages.core.doctor import run_doctor
from packages.core.errors import LingjianError
from packages.core.evidence_assets import (
    EVIDENCE_MATERIALIZATION_PROFILES,
    collect_evidence_assets,
    evidence_assets_for_scene,
    materialize_evidence_clips,
)
from packages.core.exporting import export_project
from packages.core.project import ProjectRef, init_project, reindex_project, status_project
from packages.core.qa import QAReport, audio_recovery_metadata, run_qa
from packages.core.rendering import render_project
from providers.registry import resolve_provider

app = typer.Typer(no_args_is_help=True)


@app.callback()
def _bootstrap() -> None:
    """CLI 启动注入:把系统安全存储里的凭据注入本进程环境。

    让用户把 key 存进钥匙串后,后续跑 lj 无需每次手动 export。
    """
    try:
        inject_stored_credentials()
    except Exception:  # noqa: BLE001 — 注入失败不应阻断 CLI
        pass


ingest_app = typer.Typer()
approve_app = typer.Typer()
credentials_app = typer.Typer(no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")
app.add_typer(approve_app, name="approve")
app.add_typer(credentials_app, name="credentials")

VIDEO_EVIDENCE_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
IMAGE_EVIDENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_ASSET_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac"}
COMMAND_EVIDENCE_TIMEOUT_SEC = 90
VOICE_CAPTION_MAX_CHARS = 12
VOICE_CAPTION_MIN_CUE_SEC = 0.45
VOICE_CAPTION_MAX_CUE_SEC = 1.8
VOICE_CAPTION_GAP_SEC = 0.05
BGM_TO_VOICE_DB_DEFAULT = -16.0
SFX_GAIN_DB_DEFAULT = -12.0


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


def _approve_next_command(project: ProjectRef, target: str) -> str:
    return (
        f"uv run lj approve {shlex.quote(target)} {shlex.quote(str(project.path))} "
        f"--approved-by {shlex.quote('你的名字')} --json"
    )


def _pause_for_approval(project: ProjectRef, target: str, artifact: str, as_json: bool) -> None:
    next_command = _approve_next_command(project, target)
    payload = {
        "ok": True,
        "status": "awaiting_approval",
        "current_step": target,
        "artifact": artifact,
        "message_zh": f"已生成 {target} 产物,请人工审阅后再批准或驳回。",
        "actions": [
            {"label": "查看", "command": f"cat {shlex.quote(str(project.path / artifact))}"},
            {"label": "批准", "command": next_command},
            {"label": "驳回", "command": f"重新运行 lj {target} 或修改输入后再跑 lj run"},
        ],
        "next_command": next_command,
    }
    if target == "visuals":
        review = _director_review_response(project)
        if review:
            payload.update(review)
            payload["message_zh"] = (
                "已生成完整导演分镜确认单。请先在对话里审阅每镜画面、素材、构图、"
                "关键帧、转场、字幕、声音、禁止项和验收点,再批准或修改。"
            )
            payload["actions"].insert(
                0,
                {
                    "label": "查看导演分镜确认单",
                    "command": (
                        "cat "
                        f"{shlex.quote(str(project.path / review['director_review_artifact']))}"
                    ),
                },
            )
            checklist = review.get("evidence_collection_checklist_artifact")
            if checklist:
                payload["actions"].insert(
                    1,
                    {
                        "label": "查看真实动态证据素材采集清单",
                        "command": f"cat {shlex.quote(str(project.path / checklist))}",
                    },
                )
    _emit(payload, as_json)


def _write_director_review_markdown(project: ProjectRef, visual_plan: dict) -> str:
    from packages.core.artifacts import artifact_path, read_json

    visual_plan = read_json(artifact_path(project, "visuals"))
    review_markdown = director_review_sheet_markdown(visual_plan)
    review_path = project.path / "artifacts" / "director_review_sheet.md"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(review_markdown, encoding="utf-8")
    return review_markdown


def _scene_arg(scene_id: object) -> str:
    scene = str(scene_id or "").strip()
    return f" --scene-id {shlex.quote(scene)}" if scene else ""


def _task_arg(task: object) -> str:
    task_text = str(task or "").strip()
    return f" --task {shlex.quote(task_text)}" if task_text else ""


def _manual_recording_role(evidence_types: list[str]) -> str:
    if "terminal_recording_capture" in evidence_types:
        return "terminal_recording"
    if "codex_operation_recording" in evidence_types:
        return "codex_recording"
    return "screen_recording"


def _codex_recording_task(asset_recipe_id: str, action_zh: str) -> str:
    tasks = {
        "codex_prompt_or_reconstructed_ui": (
            "展示在 Codex app 中一句话触发 lingjian-video 并进入能力门诊"
        ),
        "codex_operation_capture": "展示灵剪能力门诊、脚本、配音和画面三审过程",
        "visual_asset_generation_queue": (
            "展示 Codex app 或宿主插件生成每镜动态视频资产的队列过程"
        ),
        "repo_and_cli_flash": "展示 GitHub、Codex 和终端中的真实项目证据片段",
    }
    return tasks.get(asset_recipe_id, action_zh or "展示这一镜需要的 Codex app 操作过程")


def _codex_ingest_followup(
    project: ProjectRef,
    *,
    task_redacted: str,
    scene_id: str,
    recording_result: dict,
) -> dict[str, str]:
    project_arg = shlex.quote(str(project.path))
    scene_arg = _scene_arg(scene_id)
    task_arg = _task_arg(task_redacted)
    status = str(recording_result.get("recording_status") or "")
    if status == "captured":
        return {
            "next_action_zh": (
                "已获得可验证的 Codex 操作录屏。下一步重新运行灵剪主线,让 visuals "
                "重新计算素材绑定与缺口;如果还有其它镜头缺素材,按新清单继续补。"
            ),
            "next_command": f"uv run lj run {project_arg} --release --json",
            "screen_recording_consent_required": True,
            "privacy_notice_zh": _SCREEN_RECORDING_PRIVACY_NOTICE_ZH,
        }
    if status == "pending_user_consent":
        manual_fallback_command = (
            f"uv run lj ingest video {project_arg} --file "
            f"{shlex.quote('把录屏文件拖到这里.mp4')} --role codex_recording"
            f"{scene_arg}{task_arg} --json"
        )
        return {
            "next_action_zh": (
                "当前只登记了 Codex 操作录屏任务,尚未录屏。请确认当前屏幕无隐私内容后,"
                "用下一条命令授权录屏;或手动录好 mp4 后用 ingest video 绑定到本镜。"
            ),
            "next_command": (
                f"uv run lj ingest codex {project_arg} --task {shlex.quote(task_redacted)}"
                f"{scene_arg} --allow-screen-recording --json"
            ),
            "screen_recording_consent_required": True,
            "privacy_notice_zh": "请确认当前屏幕没有私密信息后再授权录屏。",
            "manual_fallback_command": manual_fallback_command,
            "manual_fallback_note_zh": "不授权录当前屏幕时,先手动录好 mp4 再导入同一镜头。",
        }
    role = "codex_recording"
    manual_fallback_command = (
        f"uv run lj ingest video {project_arg} --file "
        f"{shlex.quote('把录屏文件拖到这里.mp4')} --role {role}"
        f"{scene_arg}{task_arg} --json"
    )
    return {
        "next_action_zh": (
            "还没有形成可发布的 Codex 操作录屏。请修复录屏权限/工具后重试,"
            "或手动录屏并用下一条命令绑定到本镜。"
        ),
        "next_command": manual_fallback_command,
        "screen_recording_consent_required": True,
        "privacy_notice_zh": _SCREEN_RECORDING_PRIVACY_NOTICE_ZH,
        "manual_fallback_command": manual_fallback_command,
        "manual_fallback_note_zh": "自动录屏不可用或不可验证时,请手动录好 mp4 再导入同一镜头。",
    }


def _video_ingest_followup(
    project: ProjectRef,
    *,
    role: str,
    scene_id: str,
    probe_result: dict,
) -> dict[str, str]:
    project_arg = shlex.quote(str(project.path))
    scene_arg = _scene_arg(scene_id)
    if probe_result.get("source_video_has_video_stream"):
        return {
            "next_action_zh": (
                "已收到可验证的视频素材。下一步重新运行灵剪主线,让 visuals "
                "重新计算素材绑定与缺口;如果还有其它镜头缺素材,按新清单继续补。"
            ),
            "next_command": f"uv run lj run {project_arg} --release --json",
        }
    return {
        "next_action_zh": (
            "这个视频还不能作为发布级动态素材候选。请换一个能被 ffprobe 确认包含 "
            "video stream 的 mp4/mov/m4v/webm,再绑定到同一镜头。"
        ),
        "next_command": (
            f"uv run lj ingest video {project_arg} --file "
            f"{shlex.quote('换成可验证视频.mp4')} --role {shlex.quote(role)}"
            f"{scene_arg} --json"
        ),
    }


def _recording_task_metadata(task: str | None) -> dict[str, str]:
    task_redacted = _redact_sensitive_cli_text(str(task or "").strip())
    if not task_redacted:
        return {}
    return {
        "task_redacted": task_redacted,
        "recording_task_redacted": task_redacted,
    }


def _manual_video_screen_recording_consent_metadata(role: str) -> dict[str, object]:
    role_lowered = str(role or "").strip().lower()
    if role_lowered not in {
        "codex",
        "codex_operation",
        "codex_recording",
        "screen",
        "screen_capture",
        "screen_recording",
    }:
        return {}
    return {
        "screen_recording_consent_required": True,
        "screen_recording_consent": True,
        "privacy_notice_zh": (
            "用户已提供本地屏幕录屏文件;请确认该视频不包含私密信息、账号密钥、"
            "聊天内容或不可公开素材。"
        ),
    }


def _url_recording_followup(
    project: ProjectRef,
    *,
    scene_id: str,
    recording_result: dict,
) -> dict[str, str]:
    if not recording_result:
        return {}
    project_arg = shlex.quote(str(project.path))
    scene_arg = _scene_arg(scene_id)
    status = str(recording_result.get("recording_status") or "")
    if status == "captured" and recording_result.get("source_video_has_video_stream"):
        return {
            "next_action_zh": (
                "已获得可验证的网页动态录屏。下一步重新运行灵剪主线,让 visuals "
                "重新计算 URL 证据素材绑定;如果还有其它镜头缺素材,按新清单继续补。"
            ),
            "next_command": f"uv run lj run {project_arg} --release --json",
        }
    return {
        "next_action_zh": (
            "还没有形成可发布的网页动态录屏。请修复网页录屏工具后重试,"
            "或手动录屏并用下一条命令绑定到本镜。"
        ),
        "next_command": (
            f"uv run lj ingest video {project_arg} --file "
            f"{shlex.quote('把网页录屏文件拖到这里.mp4')} --role web_recording"
            f"{scene_arg} --json"
        ),
    }


def _terminal_recording_followup(
    project: ProjectRef,
    *,
    scene_id: str,
    recording_result: dict,
) -> dict[str, str]:
    if not recording_result:
        return {}
    project_arg = shlex.quote(str(project.path))
    scene_arg = _scene_arg(scene_id)
    status = str(recording_result.get("recording_status") or "")
    if status == "captured" and recording_result.get("source_video_has_video_stream"):
        return {
            "next_action_zh": (
                "已获得可验证的终端动态录屏。下一步重新运行灵剪主线,让 visuals "
                "重新计算终端/QA 证据素材绑定;如果还有其它镜头缺素材,按新清单继续补。"
            ),
            "next_command": f"uv run lj run {project_arg} --release --json",
        }
    return {
        "next_action_zh": (
            "还没有形成可发布的终端动态录屏。请修复终端录屏工具后重试,"
            "或手动录屏并用下一条命令绑定到本镜。"
        ),
        "next_command": (
            f"uv run lj ingest video {project_arg} --file "
            f"{shlex.quote('把终端录屏文件拖到这里.mp4')} --role terminal_recording"
            f"{scene_arg} --json"
        ),
    }


def _terminal_recording_command(asset_recipe_id: str, project_arg: str) -> str:
    if asset_recipe_id == "ffprobe_terminal_capture":
        return (
            "ffprobe -v error -select_streams v:0 -show_entries "
            "stream=codec_type,codec_name -of json <release-video.mp4>"
        )
    return f"uv run lj qa {project_arg} --release --strict --json"


def _web_recording_url(asset_recipe_id: str) -> str:
    urls = {
        "github_repo_star_capture": "https://github.com/dososo/blcaptain-lingjian-video",
        "readme_install_capture": "https://github.com/dososo/blcaptain-lingjian-video#readme",
        "repo_and_cli_flash": "https://github.com/dososo/blcaptain-lingjian-video",
    }
    return urls.get(asset_recipe_id, "请粘贴要录制的网页链接")


def _suggested_evidence_commands(
    project: ProjectRef,
    item: dict,
) -> list[dict[str, str]]:
    scene_arg = _scene_arg(item.get("scene_id"))
    project_arg = shlex.quote(str(project.path))
    asset_recipe_id = str(item.get("asset_recipe_id") or "")
    evidence_types = [str(value) for value in item.get("expected_evidence_types") or []]
    commands: list[dict[str, str]] = []

    if "codex_operation_recording" in evidence_types:
        task = _codex_recording_task(asset_recipe_id, str(item.get("action_zh") or ""))
        commands.append(
            {
                "label_zh": "优先:记录 Codex app 操作录屏任务",
                "command": (
                    f"uv run lj ingest codex {project_arg} --task {shlex.quote(task)}"
                    f" --allow-screen-recording{scene_arg} --json"
                ),
                "note_zh": (
                    "运行前请确认当前屏幕可被录制且没有隐私内容。只有宿主/系统录屏 CLI "
                    "成功落盘 mp4 后才算 captured;否则不会伪造录屏。"
                ),
            }
        )

    if "terminal_recording_capture" in evidence_types:
        command = _terminal_recording_command(asset_recipe_id, project_arg)
        commands.append(
            {
                "label_zh": "优先:录制终端命令证据",
                "command": (
                    f"uv run lj ingest command {project_arg} --command "
                    f"{shlex.quote(command)} --role terminal_recording --record"
                    f"{scene_arg} --json"
                ),
                "note_zh": "会真实执行这条命令并渲染终端动态证据视频;输出会做基础脱敏。",
            }
        )

    if "web_recording_capture" in evidence_types:
        url = _web_recording_url(asset_recipe_id)
        commands.append(
            {
                "label_zh": "优先:录制网页动态证据",
                "command": (
                    f"uv run lj ingest url {project_arg} --url {shlex.quote(url)}"
                    f" --record{scene_arg} --json"
                ),
                "note_zh": (
                    "适合 GitHub、README、Star/CTA 等网页证据;录屏失败时不会伪造 captured。"
                ),
            }
        )

    role = _manual_recording_role(evidence_types)
    manual_task = ""
    if "codex_operation_recording" in evidence_types:
        manual_task = _codex_recording_task(asset_recipe_id, str(item.get("action_zh") or ""))
    else:
        manual_task = str(item.get("action_zh") or "").strip()
    commands.append(
        {
            "label_zh": "兜底:把你手动录好的视频绑定到这一镜",
            "command": (
                f"uv run lj ingest video {project_arg} --file "
                f"{shlex.quote('把录屏文件拖到这里.mp4')} --role {role}"
                f"{scene_arg}{_task_arg(manual_task)} --json"
            ),
            "note_zh": (
                "如果上面的自动采集不可用,请手动录屏后用这一条把 mp4/mov/m4v/webm 绑定到本镜。"
            ),
        }
    )
    return commands


_SCREEN_RECORDING_PRIVACY_NOTICE_ZH = (
    "这条命令会录制当前屏幕。只有在你确认当前屏幕没有私密信息、账号密钥、"
    "聊天内容或不可公开素材时才执行;否则请先用手动录屏工具录好 mp4,"
    "再执行 manual_fallback_command 导入同一镜头。"
)


def _command_requires_screen_recording(command: str) -> bool:
    return "--allow-screen-recording" in command


def _find_manual_evidence_fallback(
    suggested_commands: list[dict],
) -> dict | None:
    for command_item in suggested_commands:
        command = str(command_item.get("command") or "")
        if " lj ingest video " in command or command.startswith("uv run lj ingest video "):
            return command_item
    return None


def _evidence_collection_checklist_payload(
    project: ProjectRef,
    scenes: list[dict],
) -> dict:
    items = []
    for scene in scenes:
        diagnosis = scene.get("asset_diagnosis")
        if not isinstance(diagnosis, dict):
            continue
        if diagnosis.get("asset_status") != "blocked_missing_matching_evidence_video":
            continue
        item = {
            "scene_id": scene.get("scene_id"),
            "scene_number": (scene.get("director_review_sheet_v2") or {}).get(
                "scene_number"
            ),
            "asset_recipe_id": scene.get("asset_recipe_id"),
            "expected_evidence_types": diagnosis.get("missing_evidence_types") or [],
            "action_zh": diagnosis.get("missing_evidence_action_zh") or "",
            "next_action_zh": diagnosis.get("next_action_zh") or "",
            "accepted_formats": ["mp4", "mov", "m4v", "webm"],
        }
        suggested_commands = _suggested_evidence_commands(project, item)
        item["suggested_commands"] = suggested_commands
        fallback = _find_manual_evidence_fallback(suggested_commands)
        if fallback:
            item["manual_fallback_command"] = fallback.get("command")
            item["manual_fallback_note_zh"] = fallback.get("note_zh")
        if any(
            _command_requires_screen_recording(str(command_item.get("command") or ""))
            for command_item in suggested_commands
        ):
            item["screen_recording_consent_required"] = True
            item["privacy_notice_zh"] = _SCREEN_RECORDING_PRIVACY_NOTICE_ZH
        items.append(item)
    return {
        "version": "v1",
        "markdown_artifact": "artifacts/evidence_collection_checklist.md",
        "total": len(items),
        "items": items,
    }


def _write_evidence_collection_checklist(project: ProjectRef, visual_plan: dict) -> str:
    scenes = visual_plan.get("scenes")
    checklist = (
        _evidence_collection_checklist_payload(project, scenes)
        if isinstance(scenes, list)
        else visual_plan.get("evidence_collection_checklist_v1") or {}
    )
    visual_plan["evidence_collection_checklist_v1"] = checklist
    items = [item for item in checklist.get("items", []) if isinstance(item, dict)]
    lines = [
        "# 真实动态证据素材采集清单 v1",
        "",
        "这份清单只列发布级画面当前缺的真实动态证据素材。请按顺序补齐,不要用静态图、无关网页滚动视频或生成式文字证据卡替代。",
        "",
    ]
    if not items:
        lines.extend(["当前没有待采集的匹配证据素材。", ""])
    for index, item in enumerate(items, start=1):
        scene_number = item.get("scene_number") or item.get("scene_id") or index
        lines.extend(
            [
                f"## {index}. 镜头 {scene_number}",
                "",
                f"- scene_id: {item.get('scene_id')}",
                f"- asset_recipe_id: {item.get('asset_recipe_id')}",
                f"- 应采集证据类型: {', '.join(item.get('expected_evidence_types') or [])}",
                f"- 采集动作: {item.get('action_zh')}",
                f"- 下一步: {item.get('next_action_zh')}",
                f"- 接受格式: {', '.join(item.get('accepted_formats') or [])}",
                "- 推荐采集命令:",
            ]
        )
        for command_item in item.get("suggested_commands") or []:
            if not isinstance(command_item, dict):
                continue
            lines.extend(
                [
                    f"  - {command_item.get('label_zh')}:",
                    f"    `{command_item.get('command')}`",
                    f"    说明: {command_item.get('note_zh')}",
                ]
            )
        lines.extend(
            [
                "",
            ]
        )
    markdown = "\n".join(lines).rstrip() + "\n"
    checklist_path = project.path / "artifacts" / "evidence_collection_checklist.md"
    checklist_path.parent.mkdir(parents=True, exist_ok=True)
    checklist_path.write_text(markdown, encoding="utf-8")
    return markdown


def _director_review_response(
    project: ProjectRef,
    *,
    regenerate_from_visual_plan: bool = False,
) -> dict | None:
    review_path = project.path / "artifacts" / "director_review_sheet.md"
    review_regenerated = False
    if regenerate_from_visual_plan:
        visual_plan_path = project.path / "artifacts" / "visual_plan.json"
        if visual_plan_path.exists():
            try:
                visual_plan = json.loads(visual_plan_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                visual_plan = {}
            if visual_plan:
                review_markdown = director_review_sheet_markdown(visual_plan)
                review_path.parent.mkdir(parents=True, exist_ok=True)
                review_path.write_text(review_markdown, encoding="utf-8")
                _write_evidence_collection_checklist(project, visual_plan)
                visual_plan_path.write_text(
                    json.dumps(visual_plan, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                review_regenerated = True
    if not review_path.exists():
        return None
    response = {
        "director_review_artifact": "artifacts/director_review_sheet.md",
        "director_review_markdown": review_path.read_text(encoding="utf-8"),
        "approval_instruction_zh": (
            "请把 director_review_markdown 原样展示给普通用户。用户批准的是这份完整导演"
            "执行契约;不能只给 visual_plan.json 路径或四项摘要。"
        ),
    }
    if review_regenerated:
        response["director_review_regenerated"] = True
        response["director_review_regenerated_message_zh"] = (
            "已按当前 visual_plan.json 重新生成导演分镜确认单;仍需用户重新审阅并批准 visuals。"
        )
    checklist_path = project.path / "artifacts" / "evidence_collection_checklist.md"
    if checklist_path.exists():
        response.update(
            {
                "evidence_collection_checklist_artifact": (
                    "artifacts/evidence_collection_checklist.md"
                ),
                "evidence_collection_checklist_markdown": checklist_path.read_text(
                    encoding="utf-8"
                ),
            }
        )
    return response


def _evidence_collection_next_step(project: ProjectRef) -> dict | None:
    visual_plan_path = project.path / "artifacts" / "visual_plan.json"
    if not visual_plan_path.exists():
        return None
    try:
        visual_plan = json.loads(visual_plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    summary = visual_plan.get("asset_diagnosis_summary")
    if not isinstance(summary, dict):
        return None
    try:
        non_publish_count = int(summary.get("non_publish_grade_count") or 0)
    except (TypeError, ValueError):
        non_publish_count = 0
    if non_publish_count <= 0:
        return None
    checklist = visual_plan.get("evidence_collection_checklist_v1")
    if not isinstance(checklist, dict):
        return None
    blockers = []
    first_step: dict | None = None
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
        fallback = _find_manual_evidence_fallback(suggested_commands)
        first_command_text = str(first_command.get("command") or "")
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
                    _SCREEN_RECORDING_PRIVACY_NOTICE_ZH
                    if _command_requires_screen_recording(first_command_text)
                    else None
                ),
                "manual_fallback_command": item.get("manual_fallback_command")
                or ((fallback or {}).get("command")),
                "manual_fallback_note_zh": item.get("manual_fallback_note_zh")
                or ((fallback or {}).get("note_zh")),
            }
        )
        if first_step is not None:
            continue
        for command_item in suggested_commands:
            command = str(command_item.get("command") or "").strip()
            if command:
                first_step = {
                    "scene_id": item.get("scene_id"),
                    "scene_number": item.get("scene_number"),
                    "next_action_zh": item.get("next_action_zh")
                    or item.get("action_zh")
                    or summary.get("single_next_action_zh"),
                    "next_command": command,
                    "next_command_label_zh": command_item.get("label_zh"),
                    "next_command_note_zh": command_item.get("note_zh"),
                    "alternative_next_commands": suggested_commands,
                }
                break
    if first_step:
        first_step["remaining_evidence_blockers"] = blockers
        return first_step
    return None


def _stale_approval_recovery_fields(project: ProjectRef, stale: object) -> dict:
    if not isinstance(stale, list):
        return {}
    targets = [
        str(target)
        for target in stale
        if str(target) in {"script", "voice", "visuals"}
    ]
    if not targets:
        return {}
    artifacts = {
        "script": "artifacts/script.json",
        "voice": "artifacts/voice_plan.json",
        "visuals": "artifacts/visual_plan.json",
    }
    commands = [
        {
            "target": target,
            "artifact": artifacts[target],
            "approval_command": _approve_next_command(project, target),
            "command": _approve_next_command(project, target),
        }
        for target in targets
    ]
    payload: dict = {
        "stale_approval_targets": targets,
        "stale_approval_commands": commands,
        "stale_approval_notice_zh": (
            "这些审批对应的产物已经变更。当前 next_command 仍只代表最短下一步;"
            "补齐素材或重新审阅后,还需要按 stale_approval_commands 逐项重新批准。"
        ),
    }
    if "voice" in targets:
        payload.update(
            {
                "voice_reapproval_required": True,
                "voice_approval_command": _approve_next_command(project, "voice"),
                "voice_reapproval_message_zh": (
                    "voice_plan 已变更,需要重新试听或审阅配音与字幕节奏后再批准 voice。"
                ),
            }
        )
    if "visuals" in targets:
        payload.update(
            {
                "visuals_reapproval_required": True,
                "visuals_approval_command": _approve_next_command(project, "visuals"),
            }
        )
    return payload


def _audio_asset_recovery_fields(
    project: ProjectRef,
    platform: str = "douyin",
    *,
    prefix: str = "",
) -> dict:
    metadata = audio_recovery_metadata(project, platform)
    blockers = metadata.get("remaining_audio_asset_blockers")
    if not isinstance(blockers, list) or not blockers:
        return {}
    first_action = ""
    first_command = ""
    first_command_label = ""
    first_suggested_commands = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        if not first_action and str(blocker.get("next_action_zh") or "").strip():
            first_action = str(blocker["next_action_zh"])
        if not first_command and str(blocker.get("first_command") or "").strip():
            first_command = str(blocker["first_command"])
            first_command_label = str(
                blocker.get("first_command_label_zh") or "补齐声音素材"
            )
        suggested = blocker.get("suggested_commands")
        if not first_suggested_commands and isinstance(suggested, list):
            first_suggested_commands = [
                item
                for item in suggested
                if isinstance(item, dict) and str(item.get("command") or "").strip()
            ]
        if first_action and first_command:
            break
    fields = {
        "remaining_audio_asset_blockers": blockers,
        "audio_asset_recovery_notice_zh": metadata.get(
            "audio_asset_recovery_notice_zh"
        ),
        "audio_asset_next_action_zh": first_action,
        "audio_asset_next_command": first_command,
        "audio_asset_next_command_label_zh": first_command_label,
        "audio_asset_suggested_commands": first_suggested_commands,
        "audio_asset_blocked_until_resolved_zh": (
            "当前分镜还缺 BGM/SFX 可验证音频素材或可信混音证据;"
            "当前 next_command 仍优先处理更早的审批或真实动态素材缺口,"
            "之后还需要按 remaining_audio_asset_blockers 补齐声音素材,"
            "或把分镜声音策略明确改为可无后重新审阅。"
        ),
    }
    fields = {key: value for key, value in fields.items() if value}
    if not prefix:
        return fields
    return {f"{prefix}_{key}": value for key, value in fields.items()}


def _voice_review_recovery_payload(
    project: ProjectRef,
    exc: LingjianError,
    platform: str = "douyin",
) -> dict | None:
    if exc.error_code != "APPROVAL_STALE":
        return None
    stale = exc.details.get("stale")
    if not isinstance(stale, list) or "voice" not in stale or "visuals" in stale:
        return None
    payload = {
        "ok": False,
        "error_code": exc.error_code,
        "message_zh": (
            "配音审批已经失效,需要重新试听或审阅配音与字幕节奏后再批准 voice。"
        ),
        "hint": (
            "请审阅 artifacts/voice_plan.json 和对应音频,"
            "确认 timed captions 后重新批准 voice。"
        ),
        **exc.details,
        "current_step": "voice",
        "artifact": "artifacts/voice_plan.json",
        "next_command": _approve_next_command(project, "voice"),
        "approval_command": _approve_next_command(project, "voice"),
        **_stale_approval_recovery_fields(project, stale),
    }
    evidence_next_step = _evidence_collection_next_step(project)
    if evidence_next_step:
        alternatives = evidence_next_step.get("alternative_next_commands") or []
        payload.update(
            {
                "post_voice_current_step": "visuals",
                "post_voice_next_action_zh": evidence_next_step.get("next_action_zh"),
                "post_voice_next_command_kind": "collect_evidence",
                "post_voice_next_command": evidence_next_step["next_command"],
                "post_voice_next_command_label_zh": evidence_next_step.get(
                    "next_command_label_zh"
                ),
                "post_voice_next_command_note_zh": evidence_next_step.get(
                    "next_command_note_zh"
                ),
                "post_voice_alternative_next_commands": alternatives,
                "post_voice_remaining_evidence_blockers": (
                    evidence_next_step.get("remaining_evidence_blockers") or []
                ),
                "post_voice_blocked_until_evidence_zh": (
                    "批准 voice 后仍有非发布级真实动态素材缺口;"
                    "请继续按 post_voice_next_command 采集并绑定素材,"
                    "素材补齐并重新生成/审阅画面后再批准 visuals。"
                ),
            }
        )
        post_voice_next_command = evidence_next_step["next_command"]
        if _command_requires_screen_recording(post_voice_next_command):
            fallback = _find_manual_evidence_fallback(alternatives)
            payload["post_voice_screen_recording_consent_required"] = True
            payload["post_voice_privacy_notice_zh"] = (
                _SCREEN_RECORDING_PRIVACY_NOTICE_ZH
            )
            if fallback:
                payload["post_voice_manual_fallback_command"] = fallback.get("command")
                payload["post_voice_manual_fallback_note_zh"] = fallback.get("note_zh")
    payload.update(_audio_asset_recovery_fields(project, platform, prefix="post_voice"))
    return payload


def _visuals_review_recovery_payload(
    project: ProjectRef,
    exc: LingjianError,
    platform: str = "douyin",
) -> dict | None:
    review_error_codes = {
        "DIRECTOR_REVIEW_SHEET_REQUIRED",
        "DIRECTOR_REVIEW_SHEET_STALE",
    }
    if exc.error_code == "APPROVAL_STALE":
        stale = exc.details.get("stale")
        if not isinstance(stale, list) or "visuals" not in stale:
            return None
        message_zh = "画面审批已经失效,需要重新审阅完整导演分镜确认单。"
        hint = (
            "请把 director_review_markdown 和 evidence_collection_checklist_markdown "
            "展示给用户;用户重新批准 visuals 后再继续 release。"
        )
    elif exc.error_code in review_error_codes:
        message_zh = "导演分镜确认单需要按当前 visual_plan.json 重新展示并审批。"
        hint = (
            "CLI 会重新生成当前导演分镜确认单,但不会替用户批准 visuals;"
            "请展示给用户审阅后再执行 approve visuals。"
        )
    else:
        return None
    payload = {
        "ok": False,
        "error_code": exc.error_code,
        "message_zh": message_zh,
        "hint": hint,
        **exc.details,
        "current_step": "visuals",
        "artifact": "artifacts/visual_plan.json",
        "next_command": _approve_next_command(project, "visuals"),
        "approval_command": _approve_next_command(project, "visuals"),
    }
    if exc.error_code == "APPROVAL_STALE":
        payload.update(_stale_approval_recovery_fields(project, exc.details.get("stale")))
    visual_plan_path = project.path / "artifacts" / "visual_plan.json"
    if visual_plan_path.exists():
        try:
            visual_plan = json.loads(visual_plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            visual_plan = {}
        summary = visual_plan.get("asset_diagnosis_summary")
        if isinstance(summary, dict):
            payload["single_next_action_zh"] = summary.get("single_next_action_zh")
            payload["asset_diagnosis_summary"] = summary
    review = _director_review_response(project, regenerate_from_visual_plan=True)
    if review:
        payload.update(review)
    evidence_next_step = _evidence_collection_next_step(project)
    if evidence_next_step:
        alternatives = evidence_next_step.get("alternative_next_commands") or []
        payload.update(
            {
                "next_command_kind": "collect_evidence",
                "next_command": evidence_next_step["next_command"],
                "next_command_label_zh": evidence_next_step.get(
                    "next_command_label_zh"
                ),
                "next_command_note_zh": evidence_next_step.get("next_command_note_zh"),
                "alternative_next_commands": alternatives,
                "remaining_evidence_blockers": evidence_next_step.get(
                    "remaining_evidence_blockers"
                )
                or [],
                "approval_blocked_until_evidence_zh": (
                    "当前仍有非发布级真实动态素材缺口;请先按 next_command 采集并绑定素材。"
                    "素材补齐并重新生成/审阅画面后,再执行 approval_command 批准 visuals。"
                ),
            }
        )
        if _command_requires_screen_recording(evidence_next_step["next_command"]):
            fallback = _find_manual_evidence_fallback(alternatives)
            payload["screen_recording_consent_required"] = True
            payload["privacy_notice_zh"] = _SCREEN_RECORDING_PRIVACY_NOTICE_ZH
            if fallback:
                payload["manual_fallback_command"] = fallback.get("command")
                payload["manual_fallback_note_zh"] = fallback.get("note_zh")
        if evidence_next_step.get("next_action_zh"):
            payload["single_next_action_zh"] = evidence_next_step["next_action_zh"]
    payload.update(_audio_asset_recovery_fields(project, platform))
    return payload


def _invalidate_visual_approval(project: ProjectRef) -> None:
    approvals_path = project.path / "artifacts" / "approvals.json"
    if not approvals_path.exists():
        return
    approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    if approvals.pop("visuals", None) is None:
        return
    approvals_path.write_text(json.dumps(approvals, ensure_ascii=False, indent=2), encoding="utf-8")


def _attempt_post_render_director_repair(
    project: ProjectRef,
    qa_report: QAReport,
    *,
    ratio: str,
    style: str,
) -> dict | None:
    from packages.core.artifacts import artifact_path, read_json, write_artifact

    repairable_codes = {
        "RELEASE_VISUAL_LAYOUT_CONTRACT_MISSING",
        "RELEASE_VISUAL_LAYOUT_CONFLICT",
        "RELEASE_VISUAL_TOO_MANY_PRIMARY_MOTIONS",
        "RELEASE_VISUAL_MOTION_TOO_WEAK",
        "RELEASE_VISUAL_FREEZES_AFTER_ENTRY",
    }
    reason_codes = [
        issue.code for issue in qa_report.hard_failures if issue.code in repairable_codes
    ]
    if not reason_codes:
        return None
    visuals_path = artifact_path(project, "visuals")
    if not visuals_path.exists():
        return None
    visual_plan = read_json(visuals_path)
    scenes = [scene for scene in visual_plan.get("scenes", []) if isinstance(scene, dict)]
    repaired_scenes, self_check = self_check_visual_scenes(scenes, ratio=ratio, style=style)
    if not self_check["attempts"]:
        return None
    visual_plan["scenes"] = repaired_scenes
    visual_plan["post_render_self_check"] = {
        **self_check,
        "reason_codes": reason_codes,
        "message_zh": "渲染后 QA 发现可修复导演契约问题,已生成修复草案并回到画面三审。",
    }
    write_artifact(project, "visuals", visual_plan)
    _write_director_review_markdown(project, visual_plan)
    _invalidate_visual_approval(project)
    return {
        "status": "awaiting_approval",
        "current_step": "visuals",
        "artifact": "artifacts/visual_plan.json",
        "message_zh": "渲染后自检已修复一个导演契约问题,请重新审阅画面计划后再批准。",
        "self_check": visual_plan["post_render_self_check"],
        "next_command": _approve_next_command(project, "visuals"),
    }


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


def _profile_for_project(
    project: ProjectRef,
    *,
    type_: str,
    platform: str,
    profile: str,
) -> str:
    assets_path = project.path / "assets" / "input_assets.json"
    text = ""
    if assets_path.exists():
        try:
            items = json.loads(assets_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            items = []
        if isinstance(items, list):
            text = " ".join(
                str(item.get("text") or "")
                for item in items
                if isinstance(item, dict)
            )
    return infer_content_profile(
        text=text,
        type_=type_,
        platform=platform,
        profile=profile,
    )


def _script_source_brief_for_project(
    project: ProjectRef,
    *,
    max_chars: int = 3000,
) -> dict | None:
    assets_path = project.path / "assets" / "input_assets.json"
    if not assets_path.exists():
        return None
    try:
        items = json.loads(assets_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None
    brief_items = []
    remaining = max_chars
    for item in items:
        if not isinstance(item, dict) or remaining <= 0:
            continue
        raw_parts = [
            str(item.get(key) or "")
            for key in (
                "text",
                "title",
                "summary",
                "task_redacted",
                "recording_task_redacted",
                "command_redacted",
            )
            if item.get(key)
        ]
        content = _redact_sensitive_cli_text(" ".join(" ".join(raw_parts).split()))
        if not content:
            continue
        clipped = content[:remaining]
        brief_items.append({"type": str(item.get("type") or "unknown"), "content": clipped})
        remaining -= len(clipped)
    if not brief_items:
        return None
    return {
        "items": brief_items,
        "instruction_zh": "必须围绕这些项目输入生成脚本,不得忽略输入里的强制边界和用户路径。",
    }


def _visual_profile_for_project(project: ProjectRef, profile: str) -> str:
    if profile != "douyin_product":
        return profile
    from packages.core.artifacts import artifact_path, read_json

    script_path = artifact_path(project, "script")
    if not script_path.exists():
        return profile
    script_profile = read_json(script_path).get("profile")
    return str(script_profile or profile)


def _no_recording_text(text: str) -> str:
    replacements = {
        "真实界面录屏": "真实项目文档动态化示意",
        "产品界面录屏": "产品界面示意",
        "逐步操作录屏": "逐步操作动态图形示意",
        "操作录屏": "操作流程动态图形示意",
        "界面录屏": "界面动态化示意",
        "录屏": "动态图形示意",
        "screen recording": "dynamic explainer",
        "recording": "dynamic explainer",
    }
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def _profile_preset_for_project(
    project: ProjectRef,
    *,
    profile: str,
    platform: str,
    ratio: str,
    duration: int | None = None,
    scene_count: int | None = None,
) -> dict:
    data = profile_preset(profile, platform)
    data["platform"] = platform
    data["ratio"] = ratio
    if duration is not None:
        data["duration_sec"] = int(duration)
    if scene_count is not None:
        data["scene_count"] = int(scene_count)
    if _project_disallows_recording_assets(project):
        data["recording_assets_allowed"] = False
        data["recording_policy_reason"] = "project_input_no_recording_boundary"
        for key in ("required_evidence", "visual_types", "forbidden", "qa_checkpoints"):
            values = data.get(key)
            if isinstance(values, list):
                data[key] = [
                    _no_recording_text(str(item)) for item in values if str(item).strip()
                ]
    return data


def _write_script_for_run(
    project: ProjectRef,
    type_: str,
    platform: str,
    language: str,
    ratio: str,
    duration: int,
    provider: str,
    style: str,
    profile: str,
) -> bool | str:
    from packages.core.artifacts import artifact_path, read_json, write_artifact

    current_path = artifact_path(project, "script")
    if current_path.exists():
        return False
    resolved_profile = _profile_for_project(
        project,
        type_=type_,
        platform=platform,
        profile=profile,
    )
    script_contract = script_generation_contract(
        type_=type_,
        platform=platform,
        language=language,
        ratio=ratio,
        duration=duration,
        style=style,
        profile=resolved_profile,
    )
    script_contract["profile_preset"] = _profile_preset_for_project(
        project,
        profile=resolved_profile,
        platform=platform,
        ratio=ratio,
        duration=duration,
    )
    source_brief = _script_source_brief_for_project(project)
    if source_brief:
        script_contract["source_brief"] = source_brief

    # 宿主自产(LLM 宿主首选):导出创作契约并暂停,由宿主 agent 按稿自产、
    # 再 `lj script --from-file` 回填。绝不 fork 外部 claude/codex CLI —— 宿主本身就是那个 LLM。
    if provider == "host":
        write_artifact(
            project,
            "script_contract",
            {
                "id": "script_contract",
                "type": type_,
                "platform": platform,
                "language": language,
                "ratio": ratio,
                "target_duration_sec": duration,
                **script_contract,
                "authoring_note_zh": (
                    "宿主 agent 直接按此契约创作脚本,写成 "
                    "{\"scenes\":[{\"id\":..,\"narration_text\":..}, ...]} 后用 "
                    "`lj script <项目> --from-file <脚本.json> ...` 回填,再继续 `lj run`。"
                ),
            },
        )
        return "awaiting_host_authoring"

    provider_ref = resolve_provider(provider, "llm")
    scenes = [{"id": "s1", "narration_text": "这是一段测试脚本。"}]
    generate_script = getattr(provider_ref, "generate_script", None)
    if callable(generate_script):
        generated = generate_script(script_contract)
        if isinstance(generated.get("scenes"), list) and generated["scenes"]:
            scenes = generated["scenes"]
    summary = plan_summary(
        platform=platform,
        ratio=ratio,
        duration=duration,
        scene_count=len(scenes),
        style=style,
        profile=resolved_profile,
    )
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
            "style": script_contract["style"],
            "profile": script_contract["profile"],
            "profile_preset": {
                **script_contract["profile_preset"],
                "duration_sec": duration,
                "scene_count": len(scenes),
            },
            "style_lock": script_contract["style_lock"],
            "hook_library": script_contract["hook_library"],
            "source_brief": script_contract.get("source_brief"),
            "plan_summary": summary,
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


def _script_voice_scenes(project: ProjectRef) -> list[dict[str, str]]:
    from packages.core.artifacts import artifact_path, read_json

    script_path = artifact_path(project, "script")
    if not script_path.exists():
        return [{"scene_id": "s1", "text": "灵剪"}]
    script_data = read_json(script_path)
    scenes: list[dict[str, str]] = []
    for index, scene in enumerate(script_data.get("scenes", []), start=1):
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("id") or scene.get("scene_id") or f"s{index}")
        text = str(scene.get("narration_text") or scene.get("on_screen_text") or "").strip()
        scenes.append({"scene_id": scene_id, "text": text or "灵剪"})
    return scenes or [{"scene_id": "s1", "text": "灵剪"}]


def _wav_pcm_payload(audio: bytes) -> tuple[tuple[int, int, int, str, str], bytes] | None:
    if len(audio) < 44 or audio[0:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return None
    offset = 12
    params: tuple[int, int, int, str, str] | None = None
    pcm: bytes | None = None
    while offset + 8 <= len(audio):
        chunk_id = audio[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", audio, offset + 4)[0]
        data_start = offset + 8
        actual_size = min(chunk_size, max(len(audio) - data_start, 0))
        if chunk_id == b"fmt " and actual_size >= 16:
            audio_format, channels, frame_rate, _, _, bits_per_sample = struct.unpack_from(
                "<HHIIHH", audio, data_start
            )
            if audio_format != 1 or bits_per_sample <= 0:
                return None
            params = (channels, bits_per_sample // 8, frame_rate, "NONE", "not compressed")
        elif chunk_id == b"data":
            pcm = audio[data_start : data_start + actual_size]
            break
        next_offset = data_start + chunk_size + (chunk_size % 2)
        if next_offset <= offset or next_offset > len(audio):
            break
        offset = next_offset
    if params is None or pcm is None:
        return None
    return params, pcm


def _write_full_audio_track(audio_paths: list[Path], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not audio_paths:
        output_path.write_bytes(b"")
        return
    try:
        parsed: list[tuple[tuple[int, int, int, str, str], bytes]] = []
        for audio_path in audio_paths:
            item = _wav_pcm_payload(audio_path.read_bytes())
            if item is None:
                raise wave.Error("unsupported voice segment wav")
            parsed.append(item)
        first_params = parsed[0][0]
        pcm_frames: list[bytes] = []
        for params, pcm in parsed:
            if params != first_params:
                raise wave.Error("voice segment wav format mismatch")
            pcm_frames.append(pcm)
        with wave.open(str(output_path), "wb") as full:
            channels, sample_width, frame_rate, compression, compression_name = first_params
            full.setnchannels(channels)
            full.setsampwidth(sample_width)
            full.setframerate(frame_rate)
            full.setcomptype(compression, compression_name)
            full.writeframes(b"".join(pcm_frames))
    except (EOFError, struct.error, wave.Error):
        output_path.write_bytes(b"".join(path.read_bytes() for path in audio_paths))


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
    scenes = _script_voice_scenes(project)
    per_scene_duration = max(duration / max(len(scenes), 1), 0.5)
    segments = []
    for index, scene in enumerate(scenes):
        segment = {
            "scene_id": scene["scene_id"],
            "duration_sec": per_scene_duration,
            "caption_cues": _voice_duration_aligned_caption_cues(
                scene["text"], per_scene_duration
            ),
        }
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


def _voiceless_scene_duration(text: str) -> float:
    """无旁白文字卡的镜时长:按文字卡阅读时长估(读字 + 看物件/光),最短 2.5s。"""
    chars = len(" ".join(str(text or "").split()))
    return round(max(chars / 3.5, 2.5), 2)


def _write_voiceless_voice_plan(project: ProjectRef) -> None:
    """无旁白模式(推文4 新客观主义:无配音、文字卡代旁白):不合成 TTS,
    文字卡(on_screen_text)承担叙事。产出 voiceless voice_plan(voiceover=False),
    segments 有镜时长 + 文字卡字幕、无音频;渲染音频 = BGM + SFX(无人声轨);
    QA 认 voiceover=False 不强制真实配音、字幕认 text_card。"""
    from packages.core.artifacts import write_artifact

    scenes = _script_voice_scenes(project)
    segments = []
    total = 0.0
    for scene in scenes:
        duration = _voiceless_scene_duration(scene["text"])
        total += duration
        segments.append(
            {
                "scene_id": scene["scene_id"],
                "duration_sec": duration,
                "caption_cues": _voice_duration_aligned_caption_cues(scene["text"], duration),
                "caption_cues_source": "text_card",
            }
        )
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": "voiceless",
            "provider_is_mock": False,
            "voiceover": False,
            "source_type": "text_card_narrative",
            "voice_id": "none",
            "segments": segments,
            "total_duration_sec": round(total, 2),
        },
    )


def _voice_sample_text(project: ProjectRef, sample_text: str | None) -> str:
    if sample_text:
        return sample_text.strip()[:80]
    from packages.core.artifacts import artifact_path, read_json

    script_path = artifact_path(project, "script")
    if script_path.exists():
        script_data = read_json(script_path)
        for scene in script_data.get("scenes", []):
            if isinstance(scene, dict):
                text = str(scene.get("narration_text") or "").strip()
                if text:
                    return text[:80]
    return "这是灵剪短视频配音试听。"


def _provider_effective_voice_id(provider_ref, voice_id: str) -> str:
    resolve_voice = getattr(provider_ref, "resolve_voice_id", None)
    if callable(resolve_voice):
        return str(resolve_voice(voice_id))
    return voice_id


def _provider_voice_label(provider_ref, voice_id: str) -> str:
    voice_label = getattr(provider_ref, "voice_label", None)
    if callable(voice_label):
        return str(voice_label(voice_id))
    return voice_id or "默认音色"


def _provider_voice_settings(provider_ref, voice_id: str) -> dict:
    voice_settings = getattr(provider_ref, "voice_settings", None)
    if callable(voice_settings):
        result = voice_settings(voice_id)
        if isinstance(result, dict):
            return result
    return {
        "provider_id": str(getattr(provider_ref, "id", "unknown")),
        "voice_id": voice_id or "default",
        "settings_source": "provider_voice_id_fallback",
    }


def _duration_weights_for_scenes(scenes: list[dict[str, str]]) -> list[float]:
    weights: list[float] = []
    for scene in scenes:
        text = "".join(ch for ch in scene["text"] if not ch.isspace())
        weights.append(max(float(len(text)), 1.0))
    return weights


def _allocate_durations_by_text(
    scenes: list[dict[str, str]],
    total_duration: float,
) -> list[float]:
    weights = _duration_weights_for_scenes(scenes)
    total_weight = sum(weights) or 1.0
    safe_total = max(float(total_duration), 1.0)
    return [safe_total * weight / total_weight for weight in weights]


def _voice_caption_chunks(text: str, max_chars: int = VOICE_CAPTION_MAX_CHARS) -> list[str]:
    clean = " ".join(str(text or "").split()).strip()
    if not clean:
        return ["灵剪"]
    chunks: list[str] = []
    current = ""
    break_chars = set("，。！？；、,.!?; ")
    for char in clean:
        current += char
        if char in break_chars or len(current) >= max_chars:
            chunk = current.strip(" ，。！？；、,.!?;")
            if chunk:
                chunks.append(chunk)
            current = ""
    tail = current.strip(" ，。！？；、,.!?;")
    if tail:
        chunks.append(tail)
    return chunks or [clean[:max_chars]]


def _voice_duration_aligned_caption_cues(text: str, duration: float) -> list[dict]:
    chunks = _voice_caption_chunks(text)
    safe_duration = max(float(duration), VOICE_CAPTION_MIN_CUE_SEC)
    weights = [max(len(chunk), 1) for chunk in chunks]
    total_weight = sum(weights) or 1
    total_gap = min(VOICE_CAPTION_GAP_SEC * max(len(chunks) - 1, 0), safe_duration * 0.1)
    available = max(safe_duration - total_gap, VOICE_CAPTION_MIN_CUE_SEC)
    cues: list[dict] = []
    elapsed = 0.0
    for index, (chunk, weight) in enumerate(zip(chunks, weights), start=1):
        if index == len(chunks):
            end = safe_duration
        else:
            remaining = len(chunks) - index
            max_end = safe_duration - remaining * (
                VOICE_CAPTION_MIN_CUE_SEC + VOICE_CAPTION_GAP_SEC
            )
            proportional = available * weight / total_weight
            cue_duration = min(
                max(proportional, VOICE_CAPTION_MIN_CUE_SEC),
                VOICE_CAPTION_MAX_CUE_SEC,
            )
            end = min(elapsed + cue_duration, max_end)
            end = max(end, elapsed + min(VOICE_CAPTION_MIN_CUE_SEC, safe_duration - elapsed))
        cues.append(
            {
                "index": index,
                "start_sec": round(elapsed, 3),
                "end_sec": round(max(end, elapsed + 0.01), 3),
                "text": chunk,
                "lines": [chunk],
                "max_chars_per_line": VOICE_CAPTION_MAX_CHARS,
                "source": "voice_duration_aligned",
                "timing_basis": "real_segment_duration",
            }
        )
        elapsed = min(end + VOICE_CAPTION_GAP_SEC, safe_duration)
    return cues


def _voice_plan_caption_cues_are_readable(raw_cues: object) -> bool:
    if not isinstance(raw_cues, list) or not raw_cues:
        return False
    for cue in raw_cues:
        if not isinstance(cue, dict):
            return False
        text = str(cue.get("text") or cue.get("caption") or "").strip()
        try:
            start = float(cue.get("start_sec", cue.get("start")))
            end = float(cue.get("end_sec", cue.get("end")))
        except (TypeError, ValueError):
            return False
        if not text or end <= start:
            return False
    return True


def _backfill_voice_plan_caption_cues(project: ProjectRef) -> dict | None:
    from packages.core.artifacts import artifact_path, read_json, write_artifact

    voice_path = artifact_path(project, "voice")
    if not voice_path.exists():
        return None
    voice_plan = read_json(voice_path)
    if not isinstance(voice_plan, dict) or voice_plan.get("provider_is_mock") is True:
        return None
    segments = voice_plan.get("segments")
    if not isinstance(segments, list) or not segments:
        return None
    script_text = {
        scene["scene_id"]: scene["text"]
        for scene in _script_voice_scenes(project)
        if isinstance(scene, dict)
    }
    repaired_scene_ids: list[str] = []
    skipped_scene_ids: list[str] = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            skipped_scene_ids.append(f"segment-{index}")
            continue
        scene_id = str(segment.get("scene_id") or f"s{index}")
        if _voice_plan_caption_cues_are_readable(segment.get("caption_cues")):
            continue
        if (
            "caption_cues" not in segment
            and _voice_plan_caption_cues_are_readable(segment.get("timed_captions"))
        ):
            continue
        try:
            duration = float(segment.get("duration_sec"))
        except (TypeError, ValueError):
            skipped_scene_ids.append(scene_id)
            continue
        if duration <= 0:
            skipped_scene_ids.append(scene_id)
            continue
        text = str(
            segment.get("narration_text")
            or segment.get("text")
            or script_text.get(scene_id)
            or ""
        ).strip()
        if not text:
            skipped_scene_ids.append(scene_id)
            continue
        segment["caption_cues"] = _voice_duration_aligned_caption_cues(text, duration)
        segment["caption_cues_source"] = "voice_duration_aligned"
        repaired_scene_ids.append(scene_id)
    if not repaired_scene_ids:
        return None
    repair = {
        "source": "voice_duration_aligned",
        "timing_basis": "real_segment_duration",
        "repaired_scene_ids": repaired_scene_ids,
        "repaired_scene_count": len(repaired_scene_ids),
        "skipped_scene_ids": skipped_scene_ids,
        "requires_voice_reapproval": True,
        "message_zh": (
            "已基于现有真实 voice_plan 分段时长回填 timed caption cues,"
            "请重新审阅并批准配音。"
        ),
    }
    voice_plan["timed_caption_repair"] = repair
    write_artifact(project, "voice", voice_plan)
    return repair


def _measure_voice_cadence(full_audio_path: Path) -> dict | None:
    """silencedetect 测配音停顿 → 语音段起点(卡点候选)。ffmpeg 即可,无重依赖,比字数估算准。

    与固化能力 `capabilities/cadence/cadence.py` 同一 silencedetect 逻辑与参数
    (noise=-30dB, d=0.05),主线在此复用,保证独立工具与主线口径一致。

    画面事件(砸词/揭示/节点点亮)的 start 卡这些点,可提前 0~0.1s 让「砸下」峰值压词;
    绝不早于语音段起点,否则画面比配音快(用户实测的病)。whisper 给段/词时间,cadence 给停顿节奏,互补。
    """
    if not full_audio_path.exists() or full_audio_path.stat().st_size < 2000:
        return None
    try:
        completed = subprocess.run(
            [
                "ffmpeg", "-i", str(full_audio_path),
                "-af", "silencedetect=noise=-30dB:d=0.05",
                "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    points = [0.0]
    for match in re.finditer(r"silence_end: ([0-9.]+)", completed.stderr):
        try:
            points.append(round(float(match.group(1)), 2))
        except ValueError:
            continue
    if len(points) <= 1:
        return None
    return {
        "beat_points": points,
        "source": "silencedetect",
        "rule_zh": "画面事件 start 卡这些点(可提前 0~0.1s 让砸下压词);绝不早于,否则画面比配音快。",
    }


def _whisper_align_adapter() -> Path:
    return Path(__file__).resolve().parents[3] / "scripts" / "providers" / "whisper_align_cli.py"


def _whisper_align_available() -> bool:
    adapter = _whisper_align_adapter()
    if not adapter.exists():
        return False
    try:
        completed = subprocess.run(
            [sys.executable, str(adapter), "--probe"],
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _whisper_full_track_cues(full_audio_path: Path) -> list[dict] | None:
    """对整段 full.wav 跑一次 whisper,返回全局时间轴 cues。不可用/失败返回 None。"""
    if not _whisper_align_available():
        return None
    if not full_audio_path.exists() or full_audio_path.stat().st_size < 2000:
        return None
    try:
        payload = json.dumps({"audio_path": str(full_audio_path.resolve()), "language": "zh"})
        completed = subprocess.run(
            [sys.executable, str(_whisper_align_adapter())],
            input=payload,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            return None
        cues = json.loads(completed.stdout or "{}").get("timed_captions")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return None
    if isinstance(cues, list) and cues:
        return [c for c in cues if isinstance(c, dict)]
    return None


def _shift_cues(full_cues: list[dict], scene_start: float, scene_end: float) -> list[dict]:
    """取落在 [scene_start, scene_end) 的 cues,平移为镜内相对时间(渲染消费镜内相对)。"""
    out: list[dict] = []
    span = max(scene_end - scene_start, 0.1)
    for cue in full_cues:
        cue_start = float(cue.get("start_sec") or 0.0)
        cue_end = float(cue.get("end_sec") or cue_start)
        if cue_start < scene_start - 0.01 or cue_start >= scene_end - 0.001:
            continue
        text = str(cue.get("text") or "").strip()
        if not text:
            continue
        rel_start = round(max(cue_start - scene_start, 0.0), 3)
        rel_end = round(min(cue_end - scene_start, span), 3)
        if rel_end <= rel_start:
            rel_end = round(min(rel_start + 0.2, span), 3)
        out.append(
            {
                "text": text,
                "start_sec": rel_start,
                "end_sec": rel_end,
                "source": "whisper",
                "timing_basis": "whisper_full_track_split",
            }
        )
    return out


def _split_full_track_by_whisper(
    scenes: list[dict[str, str]],
    full_cues: list[dict],
    total_duration: float,
) -> tuple[list[float], list[list[dict]]] | None:
    """用整段 whisper 时间轴把整条音轨切成各镜:镜边界**吸附到 whisper 句边界(=停顿)**,
    比按字数估准(治「字数估偏1秒逐镜错位」);各镜 timed_captions = 落在该镜区间的 cues。
    scenes/cues 为空返回 None(调用方回退字数估)。"""
    n = len(scenes)
    total = max(float(total_duration), 1.0)
    if n == 0 or not full_cues:
        return None
    if n == 1:
        return [round(total, 3)], [_shift_cues(full_cues, 0.0, total)]
    boundaries = sorted(
        {
            round(float(c.get("end_sec") or 0.0), 3)
            for c in full_cues
            if c.get("end_sec") is not None
        }
    )
    boundaries = [b for b in boundaries if 0.0 < b < total]
    weights = _duration_weights_for_scenes(scenes)
    total_weight = sum(weights) or 1.0
    scene_ends: list[float] = []
    acc = 0.0
    used: set[float] = set()
    for i in range(n - 1):
        acc += total * weights[i] / total_weight
        tol = max(1.0, 0.3 * total * weights[i] / total_weight)
        floor = scene_ends[-1] if scene_ends else 0.0
        cand = [b for b in boundaries if b not in used and b > floor]
        nearest = min(cand, key=lambda b: abs(b - acc)) if cand else None
        if nearest is not None and abs(nearest - acc) <= tol:
            scene_ends.append(round(nearest, 3))
            used.add(nearest)
        else:
            scene_ends.append(round(acc, 3))
    scene_ends.append(round(total, 3))
    durations: list[float] = []
    per_scene_cues: list[list[dict]] = []
    prev = 0.0
    for i in range(n):
        end = scene_ends[i]
        if end <= prev:
            end = round(prev + 0.1, 3)
        durations.append(round(end - prev, 3))
        per_scene_cues.append(_shift_cues(full_cues, prev, end))
        prev = end
    return durations, per_scene_cues


def _attach_whisper_timed_captions(
    project: ProjectRef, segments: list[dict], is_mock: bool
) -> int:
    """配音合成后:对每个真实音频段跑 whisper,挂真时间轴 timed_captions(渲染优先用它,替代字数估算)。

    非阻塞:whisper 不可用或某段失败,该段保留估算 caption_cues。返回成功挂上的段数。
    """
    if is_mock or not _whisper_align_available():
        return 0
    adapter = _whisper_align_adapter()
    attached = 0
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        if segment.get("caption_cues_source") == "whisper_full_track_split":
            continue  # 已由整段切分挂上 whisper 时间轴,别用单段再覆盖
        rel = segment.get("audio_path")
        if not rel:
            continue
        audio_abs = (project.path / str(rel)).resolve()
        if not audio_abs.exists() or audio_abs.stat().st_size < 2000:
            continue  # 跳过 mock/空音频
        try:
            payload = json.dumps({"audio_path": str(audio_abs), "language": "zh"})
            completed = subprocess.run(
                [sys.executable, str(adapter)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if completed.returncode != 0:
                continue
            data = json.loads(completed.stdout or "{}")
            cues = data.get("timed_captions")
            if isinstance(cues, list) and cues:
                segment["timed_captions"] = cues
                segment["caption_cues_source"] = "whisper_aligned"
                attached += 1
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
            continue
    return attached


def _write_voice_plan(
    project: ProjectRef,
    provider: str,
    voice_id: str,
    audio_file: Path | None,
    voiceover: bool = True,
) -> bool:
    from packages.core.artifacts import artifact_path, write_artifact

    current_path = artifact_path(project, "voice")
    if current_path.exists():
        return False
    if not voiceover:
        _write_voiceless_voice_plan(project)
        return True
    if audio_file is not None:
        _write_user_audio_voice_plan(project, audio_file)
        return True
    provider_ref = _resolve_tts_provider(provider)
    audio_dir = project.path / "artifacts" / "voice_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    synthesize = getattr(provider_ref, "synthesize", None)
    scenes = _script_voice_scenes(project)
    segments: list[dict] = []
    audio_paths: list[Path] = []
    total_duration = 0.0
    effective_voice_id = _provider_effective_voice_id(provider_ref, voice_id)
    provider_voice_settings = _provider_voice_settings(provider_ref, effective_voice_id)
    segment_voice_meta = {
        "voice_id": effective_voice_id,
        "provider_voice_settings": provider_voice_settings,
    }
    if callable(synthesize):
        prefer_full_track = bool(getattr(provider_ref, "prefer_continuous_full_track", False))
        if prefer_full_track and len(scenes) > 1:
            full_text = "\n".join(scene["text"] for scene in scenes)
            audio_bytes, total_duration = synthesize(
                {"voice": effective_voice_id, "text": full_text, "track": "full"}
            )
            full_audio_path = audio_dir / "full.wav"
            full_audio_path.write_bytes(audio_bytes)
            # P1-3: 整段 whisper 时间轴定镜边界(吸附句边界)+ 各镜字幕(优先),字数估兜底
            per_scene_cues: list[list[dict]] | None = None
            split = None
            if not getattr(provider_ref, "is_mock", False):
                full_cues = _whisper_full_track_cues(full_audio_path)
                if full_cues:
                    split = _split_full_track_by_whisper(
                        scenes, full_cues, float(total_duration)
                    )
            if split is not None:
                durations, per_scene_cues = split
            else:
                durations = _allocate_durations_by_text(scenes, float(total_duration))
            for index, (scene, duration) in enumerate(zip(scenes, durations), start=1):
                audio_path = audio_dir / f"s{index}.wav"
                segment = {
                    "scene_id": scene["scene_id"],
                    "duration_sec": float(duration),
                    "caption_cues": _voice_duration_aligned_caption_cues(
                        scene["text"], float(duration)
                    ),
                    **segment_voice_meta,
                }
                if per_scene_cues is not None and per_scene_cues[index - 1]:
                    segment["timed_captions"] = per_scene_cues[index - 1]
                    segment["caption_cues_source"] = "whisper_full_track_split"
                if index == 1:
                    audio_path.write_bytes(audio_bytes)
                    audio_paths.append(audio_path)
                    segment["audio_path"] = str(audio_path.relative_to(project.path))
                segments.append(segment)
        else:
            for index, scene in enumerate(scenes, start=1):
                audio_path = audio_dir / f"s{index}.wav"
                audio_bytes, duration = synthesize(
                    {
                        "voice": effective_voice_id,
                        "text": scene["text"],
                        "scene_id": scene["scene_id"],
                    }
                )
                audio_path.write_bytes(audio_bytes)
                audio_paths.append(audio_path)
                total_duration += float(duration)
                segments.append(
                    {
                        "scene_id": scene["scene_id"],
                        "audio_path": str(audio_path.relative_to(project.path)),
                        "duration_sec": float(duration),
                        "caption_cues": _voice_duration_aligned_caption_cues(
                            scene["text"], float(duration)
                        ),
                        **segment_voice_meta,
                    }
                )
    else:
        for index, scene in enumerate(scenes, start=1):
            audio_path = audio_dir / f"s{index}.wav"
            audio_path.write_bytes(b"mock audio")
            audio_paths.append(audio_path)
            total_duration += 1.0
            segments.append(
                {
                    "scene_id": scene["scene_id"],
                    "audio_path": str(audio_path.relative_to(project.path)),
                    "duration_sec": 1.0,
                    "caption_cues": _voice_duration_aligned_caption_cues(scene["text"], 1.0),
                    **segment_voice_meta,
                }
            )
    full_audio_path = audio_dir / "full.wav"
    if audio_paths:
        _write_full_audio_track(audio_paths, full_audio_path)
    # 配音合成后:whisper 挂真时间轴字幕 + silencedetect 测停顿卡点(替代字数估算,非阻塞)
    _attach_whisper_timed_captions(project, segments, provider_ref.is_mock)
    voice_cadence = None if provider_ref.is_mock else _measure_voice_cadence(full_audio_path)
    cost_notice = paid_engine_notice(provider_ref.id)
    write_artifact(
        project,
        "voice",
        {
            "id": "voice",
            "provider_id": provider_ref.id,
            "provider_is_mock": provider_ref.is_mock,
            "voice_id": effective_voice_id,
            "voice_label_zh": _provider_voice_label(provider_ref, effective_voice_id),
            "voice_selection_source": "user_selected" if voice_id else "provider_default",
            "provider_voice_settings": provider_voice_settings,
            "segments": segments,
            "full_audio_path": str(full_audio_path.relative_to(project.path)),
            "total_duration_sec": total_duration,
            "voice_cadence": voice_cadence,
            "cost_notices": [cost_notice] if cost_notice else [],
        },
    )
    return True


def _write_voice_options(
    project: ProjectRef,
    provider: str,
    sample_text: str | None,
    limit: int,
) -> dict:
    provider_ref = _resolve_tts_provider(provider)
    sample = _voice_sample_text(project, sample_text)
    discover = getattr(provider_ref, "discover_voice_options", None)
    if callable(discover):
        raw_options = discover(sample, limit=limit)
    else:
        synthesize = getattr(provider_ref, "synthesize", None)
        if not callable(synthesize):
            raise LingjianError(
                "TTS_VOICE_OPTIONS_UNAVAILABLE",
                "当前 TTS provider 不支持生成音色试听。",
                "请改用火山豆包 TTS 或直接提供用户录音。",
                {"provider": provider_ref.id},
            )
        audio_bytes, duration = synthesize({"voice": "", "text": sample})
        raw_options = [
            {
                "voice_id": "",
                "label_zh": "默认音色",
                "sample_text": sample,
                "audio_bytes": audio_bytes,
                "duration_sec": duration,
                "source": "default_probe",
            }
        ]
    output_dir = project.path / "artifacts" / "voice_options"
    output_dir.mkdir(parents=True, exist_ok=True)
    options: list[dict] = []
    for index, option in enumerate(raw_options[:limit], start=1):
        audio_bytes = option.pop("audio_bytes")
        voice_id = str(option.get("voice_id") or "")
        audio_path = output_dir / f"option_{index}.wav"
        audio_path.write_bytes(audio_bytes)
        options.append(
            {
                "index": index,
                "voice_id": voice_id,
                "label_zh": str(option.get("label_zh") or voice_id or "默认音色"),
                "audio_path": str(audio_path.relative_to(project.path)),
                "duration_sec": float(option.get("duration_sec") or 1.0),
                "sample_text": sample,
                "source": str(option.get("source") or "synthesis_probe"),
            }
        )
    payload = {
        "id": "voice_options",
        "provider_id": provider_ref.id,
        "provider_is_mock": provider_ref.is_mock,
        "sample_text": sample,
        "options": options,
        "message_zh": "请试听后选择一个音色,再用 --voice <voice_id> 生成正式配音。",
    }
    (project.path / "artifacts").mkdir(parents=True, exist_ok=True)
    (project.path / "artifacts" / "voice_options.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _voice_choice_response(project: Path, payload: dict) -> dict:
    actions = []
    for option in payload["options"]:
        voice_part = f" --voice {option['voice_id']}" if option["voice_id"] else ""
        actions.append(
            {
                "label": f"选择 {option['index']} 号音色",
                "command": (
                    "uv run lj run "
                    f"{project} --voice-provider {payload['provider_id']}"
                    f"{voice_part} --json"
                ),
            }
        )
    return {
        "ok": True,
        "status": "awaiting_voice_choice",
        "current_step": "voice_options",
        "artifact": "artifacts/voice_options.json",
        "message_zh": payload["message_zh"],
        "options": payload["options"],
        "actions": actions,
    }


def _resolve_tts_provider(provider: str):
    if provider != "auto":
        return resolve_provider(provider, "tts")
    try:
        return resolve_provider("auto", "tts")
    except LingjianError:
        return resolve_provider("mock", "tts")


def _preferred_visual_for_generation(report) -> str:
    for candidate in report.groups["visuals"].candidates:
        if (
            candidate.id in {"host_seedance", "host_hyperframes", "host_remotion"}
            and candidate.configured
        ):
            return candidate.id
    return report.groups["visuals"].best.id


def _configured_visual_ids(report) -> set[str]:
    return {
        candidate.id
        for candidate in report.groups["visuals"].candidates
        if candidate.configured
    }


def _scene_prefers_remotion(scene_contract: dict) -> bool:
    tokens = " ".join(
        str(scene_contract.get(key) or "")
        for key in (
            "blueprint_id",
            "visual_archetype",
            "asset_recipe_id",
            "material_key",
        )
    ).lower()
    motion = scene_contract.get("motion_intent")
    if isinstance(motion, dict):
        motion_values = [
            motion.get("main_motion_intent"),
            motion.get("transition_family"),
            " ".join(str(item) for item in motion.get("motion_rule_ids") or []),
        ]
        tokens += " " + " ".join(str(item).lower() for item in motion_values if item)
    transition = scene_contract.get("transition_plan")
    if isinstance(transition, dict):
        tokens += " " + " ".join(str(item).lower() for item in transition.values())
    precision_terms = {
        "dataviz",
        "data",
        "dashboard",
        "timeline",
        "manifest",
        "ffprobe",
        "chart",
        "overlay",
        "transparent",
    }
    return any(term in tokens for term in precision_terms)


def _visual_generator_for_scene(
    project: ProjectRef,
    scene_id: str,
    best_visual: str | None = None,
    available_visuals: set[str] | None = None,
    scene_contract: dict | None = None,
) -> dict:
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
    if best_visual is None:
        capabilities = detect_capabilities()
        best_visual = _preferred_visual_for_generation(capabilities)
        available_visuals = _configured_visual_ids(capabilities)
    available_visuals = available_visuals or set()
    if (
        best_visual in {"host_hyperframes", "host_seedance"}
        and "host_remotion" in available_visuals
        and scene_contract is not None
        and _scene_prefers_remotion(scene_contract)
    ):
        # 精密镜(数据/图表/UI/timeline)交 Remotion 做精确执行;
        # Seedance 是默认真视频引擎,但这类镜用图形化更清楚,不被 Seedance 抢走。
        best_visual = "host_remotion"
    if best_visual == "host_seedance":
        return {
            "generator": "seedance",
            "asset_path": f"assets/scenes/{scene_id}.mp4",
            "expected_asset_path": f"assets/scenes/{scene_id}.mp4",
            "subtitle_burn": True,
            "motion": {"main": "seedance_text_to_video", "one_main_only": True},
            "motion_spec": {"main": "seedance_text_to_video", "one_main_only": True},
        }
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
    style: str = "clean_product",
) -> str:
    hint = f"场景提示:{visual_hint}。" if visual_hint else ""
    keyword = f"视觉关键词:{on_screen_text}。" if on_screen_text else ""
    surface = {
        "16:9": "横屏短视频",
        "9:16": "竖屏短视频",
        "1:1": "方形短视频",
        "3:4": "竖版短视频",
        "4:3": "横版短视频",
    }.get(ratio, "短视频")
    frame = "全屏画面" if ratio in {"16:9", "4:3"} else "画面"
    return (
        f"为{surface}生成一镜{frame}。"
        f"画幅 {ratio},风格预设 {style},主体清晰,背景简洁。"
        f"{hint}{keyword}"
        f"旁白/画面信息:{narration}"
    )


def _apply_visual_profile_to_scenes(
    scenes: list[dict],
    profile_data: dict,
) -> None:
    for scene in scenes:
        brief = scene.get("brief")
        if isinstance(brief, dict):
            brief["profile"] = dict(profile_data)


def _short_visual_text(text: str, limit: int = 24) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _script_visual_composition(visual_hint: str, ratio: str) -> str:
    layout = (
        "16:9 全屏横向构图,主体占画面中部或右侧,左侧/上方保留短标题和状态标签,"
        if ratio == "16:9"
        else "主体居中,上方保留短标题和状态标签,"
    )
    return f"{layout}底部字幕安全区保持干净。画面主体:{visual_hint}"


def _script_visual_keyframes(
    *,
    duration_sec: float,
    visual_hint: str,
    on_screen_text: str,
) -> list[dict]:
    label = _short_visual_text(on_screen_text or visual_hint or "本镜主画面")
    midpoint = round(max(duration_sec * 0.45, 0.6), 2)
    endpoint = round(max(duration_sec - 0.35, midpoint + 0.2), 2)
    return [
        {"time_sec": 0.0, "state": f"{label} 入场,先建立这一镜的清晰视觉焦点。"},
        {
            "time_sec": midpoint,
            "state": f"{visual_hint} 按口播节奏继续展开,主体保持持续运动而不是停成静帧。",
        },
        {
            "time_sec": endpoint,
            "state": f"画面收束到 {label},为下一镜语义转场留下明确锚点。",
        },
    ]


def _script_visual_transition(
    *,
    index: int,
    visual_hint: str,
    on_screen_text: str,
) -> dict:
    families = [
        "prompt-expand",
        "diagram-zoom",
        "diagnosis-tabs",
        "form-field-stack",
        "script-card-focus",
        "waveform-sweep",
        "storyboard-slide",
        "router-branch",
        "qa-scan",
        "status-layer-lock",
    ]
    label = _short_visual_text(on_screen_text or visual_hint)
    family = families[(index - 1) % len(families)]
    if index == 1:
        transition_in = f"从黑场淡入到「{label}」主视觉,第一秒建立入口。"
    else:
        transition_in = f"承接上一镜收束锚点,用 {family} 进入「{label}」。"
    transition_out = f"把「{label}」收束成下一镜入口,切点避开口播词中。"
    return {
        "family": family,
        "in": transition_in,
        "out": transition_out,
        "semantic": "服务当前脚本节拍,转场动作必须对应本镜画面语义。",
        "cut_policy": "不在词中切,必要时 30ms 淡入淡出。",
        "diversity_policy": "相邻镜头不得复用同一 transition family。",
        "transition_index": index,
    }


def _script_visual_sfx(on_screen_text: str, visual_hint: str) -> str:
    label = _short_visual_text(on_screen_text or visual_hint)
    return (
        f"绑定「{label}」的轻提示音:节点点亮、卡片展开或状态落定;"
        "转场 whoosh 保持低音量,不抢人声。"
    )


def _apply_script_visual_intent(
    *,
    board: dict,
    contract: dict,
    index: int,
    visual_hint: str,
    on_screen_text: str,
    duration_sec: float,
    ratio: str,
) -> tuple[dict, dict]:
    visual_hint = str(visual_hint or "").strip()
    if not visual_hint:
        return board, contract
    required_elements = [
        _short_visual_text(on_screen_text or visual_hint),
        "口播动作点逐 beat 对齐",
        "底部字幕安全区",
    ]
    audio_notes = dict(board.get("audio_sfx_notes") or {})
    audio_notes["sfx"] = _script_visual_sfx(on_screen_text, visual_hint)
    board_update = {
        **board,
        "visual_content": visual_hint,
        "composition": _script_visual_composition(visual_hint, ratio),
        "required_elements": required_elements,
        "keyframes": _script_visual_keyframes(
            duration_sec=duration_sec,
            visual_hint=visual_hint,
            on_screen_text=on_screen_text,
        ),
        "transition": _script_visual_transition(
            index=index,
            visual_hint=visual_hint,
            on_screen_text=on_screen_text,
        ),
        "audio_sfx_notes": audio_notes,
    }
    contract_update = {
        **contract,
        "visual_content": visual_hint,
        "composition": board_update["composition"],
        "keyframes": board_update["keyframes"],
        "transition_plan": board_update["transition"],
    }
    return board_update, contract_update


def _route_with_evidence_clip(
    route: dict,
    evidence_refs: list[dict],
    *,
    profile: str,
    requires_real_evidence: bool,
    asset_recipe_id: str | None = None,
) -> dict:
    if (
        not requires_real_evidence
        and profile not in EVIDENCE_MATERIALIZATION_PROFILES
    ):
        return route
    clip_ref = _preferred_scene_evidence_clip(
        evidence_refs,
        profile=profile,
        asset_recipe_id=asset_recipe_id,
    )
    if not clip_ref:
        return route
    clip_path = str(clip_ref["evidence_clip_path"])
    return {
        **route,
        "generator": "user-asset",
        "asset_path": clip_path,
        "expected_asset_path": clip_path,
        "asset_origin": "evidence_dynamic_clip",
        "generation_status": "evidence_clip",
    }


def _preferred_scene_evidence_clip(
    evidence_refs: list[dict],
    *,
    profile: str,
    asset_recipe_id: str | None = None,
) -> dict | None:
    candidates = [
        ref
        for ref in evidence_refs
        if _evidence_clip_can_drive_scene(
            ref,
            profile=profile,
            asset_recipe_id=asset_recipe_id,
        )
    ]
    if not candidates:
        return None
    publish_grade = [
        ref for ref in candidates if bool(ref.get("publish_grade_evidence_video"))
    ]
    if publish_grade:
        return publish_grade[0]
    captured = [
        ref
        for ref in candidates
        if str(ref.get("evidence_clip_status") or "") == "captured"
    ]
    if captured:
        return captured[0]
    return candidates[0]


def _evidence_clip_can_drive_scene(
    ref: dict,
    *,
    profile: str,
    asset_recipe_id: str | None = None,
) -> bool:
    if not str(ref.get("evidence_clip_path") or "").endswith(".mp4"):
        return False
    status = str(ref.get("evidence_clip_status") or "")
    if status != "captured":
        return False
    evidence_type = str(ref.get("evidence_type") or "")
    if profile == "open_source_project_intro":
        allowed = _evidence_types_for_asset_recipe(asset_recipe_id)
        if allowed:
            return evidence_type in allowed
        if asset_recipe_id:
            return evidence_type == "screen_recording_capture"
        return evidence_type in {
            "codex_operation_recording",
            "screen_recording_capture",
            "terminal_recording_capture",
            "web_recording_capture",
        }
    if profile in EVIDENCE_MATERIALIZATION_PROFILES:
        return True
    return False


def _evidence_types_for_asset_recipe(asset_recipe_id: str | None) -> set[str]:
    recipe = str(asset_recipe_id or "")
    mapping = {
        "codex_prompt_or_reconstructed_ui": {
            "codex_operation_recording",
            "screen_recording_capture",
        },
        "codex_operation_capture": {
            "codex_operation_recording",
            "screen_recording_capture",
        },
        "ffprobe_terminal_capture": {
            "terminal_recording_capture",
            "screen_recording_capture",
        },
        "github_repo_star_capture": {
            "web_recording_capture",
            "screen_recording_capture",
        },
        "qa_report_capture": {
            "terminal_recording_capture",
            "screen_recording_capture",
        },
        "readme_install_capture": {
            "web_recording_capture",
            "screen_recording_capture",
        },
        "render_manifest_capture": {
            "terminal_recording_capture",
            "screen_recording_capture",
        },
        "repo_and_cli_flash": {
            "codex_operation_recording",
            "screen_recording_capture",
            "terminal_recording_capture",
            "web_recording_capture",
        },
        "visual_asset_generation_queue": {
            "codex_operation_recording",
            "screen_recording_capture",
        },
    }
    return mapping.get(recipe, set())


def _matching_evidence_gap_diagnosis(
    *,
    scene_contract: dict,
    evidence_refs: list[dict],
    profile: str,
    scene_index: int,
) -> dict | None:
    if not _scene_requires_matching_evidence(scene_contract, profile):
        return None
    asset_recipe_id = str(scene_contract.get("asset_recipe_id") or "")
    matched = _preferred_scene_evidence_clip(
        evidence_refs,
        profile=profile,
        asset_recipe_id=asset_recipe_id,
    )
    if matched:
        return None
    instruction = _missing_evidence_instruction(
        asset_recipe_id=asset_recipe_id,
        scene_index=scene_index,
    )
    return {
        "asset_status": "blocked_missing_matching_evidence_video",
        "asset_kind": "missing_matching_evidence_video",
        "publish_grade_visual": False,
        "source_zh": "这一镜需要与分镜意图匹配的真实动态证据素材。",
        "missing_evidence_types": instruction["evidence_types"],
        "missing_evidence_action_zh": instruction["action_zh"],
        "next_action_zh": instruction["next_action_zh"],
    }


def _json_string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_json_string_values(item))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_json_string_values(item))
        return values
    return []


def _project_disallows_recording_assets(project: ProjectRef) -> bool:
    texts: list[str] = []
    for path in [
        project.path / "assets" / "input_assets.json",
        project.path / "artifacts" / "script.json",
    ]:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        texts.extend(_json_string_values(payload))
    haystack = "\n".join(texts)
    phrases = [
        "不使用录屏素材",
        "不使用屏幕录制素材",
        "不允许使用录屏素材",
        "不允许屏幕录制",
        "禁止使用录屏素材",
        "禁止屏幕录制",
        "不录屏",
        "不录制屏幕",
        "不使用真实录屏",
        "不用录屏素材",
        "无录屏素材",
    ]
    return any(phrase in haystack for phrase in phrases)


def _no_recording_dynamic_generation_diagnosis(
    *,
    scene_contract: dict,
    route: dict,
) -> dict:
    path = str(route.get("expected_asset_path") or route.get("asset_path") or "")
    return {
        "asset_status": "pending_no_recording_dynamic_generation",
        "asset_kind": "dynamic_video",
        "publish_grade_visual": False,
        "source_zh": (
            "用户明确不使用录屏素材;这一镜改为动态图形、界面示意或检查清单动效候选。"
        ),
        "missing_evidence_types": [],
        "missing_evidence_action_zh": "",
        "next_action_zh": (
            f"按分镜生成 {path or 'assets/scenes/<scene_id>.mp4'} 动态图形视频;"
            "当前不要求录屏,但 release strict 仍需后续用真实动态素材或用户认可的"
            "发布级生成视频证明。"
        ),
        "recording_assets_allowed": False,
        "asset_recipe_id": "no_recording_dynamic_graphics",
    }


def _without_recording_evidence_markers(values: object) -> list:
    recording_markers = {
        "codex_operation_capture",
        "codex_prompt_or_reconstructed_ui",
        "ffprobe_terminal_capture",
        "github_repo_star_capture",
        "qa_report_capture",
        "readme_install_capture",
        "render_manifest_capture",
        "repo_and_cli_flash",
        "visual_asset_generation_queue",
        "screen_recording_capture",
        "terminal_recording_capture",
        "web_recording_capture",
        "codex_operation_recording",
    }
    if not isinstance(values, list):
        return []
    filtered = []
    for item in values:
        text = str(item or "")
        if text in recording_markers:
            continue
        if "录屏" in text or "recording" in text:
            continue
        filtered.append(item)
    return filtered


def _apply_no_recording_scene_boundary(scene_contract: dict) -> dict:
    updated = dict(scene_contract)
    updated["asset_recipe_id"] = "no_recording_dynamic_graphics"
    updated["requires_real_evidence_asset"] = False
    updated["expected_real_evidence"] = _without_recording_evidence_markers(
        updated.get("expected_real_evidence")
    )
    return updated


def _apply_no_recording_board_boundary(board: dict) -> dict:
    updated = dict(board)
    updated["asset_recipe_id"] = "no_recording_dynamic_graphics"
    return updated


def _scene_requires_matching_evidence(scene_contract: dict, profile: str) -> bool:
    if bool(scene_contract.get("requires_real_evidence_asset")):
        return True
    recipe = str(scene_contract.get("asset_recipe_id") or "")
    if profile == "open_source_project_intro" and recipe in {
        "codex_prompt_or_reconstructed_ui",
    }:
        return True
    return False


def _missing_evidence_instruction(
    *,
    asset_recipe_id: str,
    scene_index: int,
) -> dict:
    generic = {
        "evidence_types": sorted(_evidence_types_for_asset_recipe(asset_recipe_id))
        or ["screen_recording_capture"],
        "action_zh": "录制与这一镜画面内容一致的屏幕操作或真实视频证据。",
    }
    by_recipe = {
        "codex_prompt_or_reconstructed_ui": {
            "evidence_types": ["codex_operation_recording", "screen_recording_capture"],
            "action_zh": "录制 Codex app 里一句话触发 lingjian-video 的对话过程。",
        },
        "codex_operation_capture": {
            "evidence_types": ["codex_operation_recording", "screen_recording_capture"],
            "action_zh": "录制 Codex app 能力门诊、脚本/配音/画面三审的真实操作过程。",
        },
        "visual_asset_generation_queue": {
            "evidence_types": ["codex_operation_recording", "screen_recording_capture"],
            "action_zh": "录制 Codex app 或宿主插件生成每镜动态视频资产的队列/过程。",
        },
        "qa_report_capture": {
            "evidence_types": ["terminal_recording_capture", "screen_recording_capture"],
            "action_zh": "录制终端运行 QA/strict 检查或打开 QA 报告的过程。",
        },
        "ffprobe_terminal_capture": {
            "evidence_types": ["terminal_recording_capture", "screen_recording_capture"],
            "action_zh": "录制终端 ffprobe 输出,展示 h264/aac 与发布级体检证据。",
        },
        "render_manifest_capture": {
            "evidence_types": ["terminal_recording_capture", "screen_recording_capture"],
            "action_zh": "录制查看 render_manifest 或导出 manifest 证据的过程。",
        },
        "github_repo_star_capture": {
            "evidence_types": ["web_recording_capture", "screen_recording_capture"],
            "action_zh": "录制 GitHub 仓库页面、Star 按钮或项目 CTA 画面。",
        },
        "readme_install_capture": {
            "evidence_types": ["web_recording_capture", "screen_recording_capture"],
            "action_zh": "录制 README 顶部安装入口和首用说明页面。",
        },
        "repo_and_cli_flash": {
            "evidence_types": [
                "codex_operation_recording",
                "screen_recording_capture",
                "terminal_recording_capture",
                "web_recording_capture",
            ],
            "action_zh": "录制 GitHub、Codex 或终端中的真实项目证据片段。",
        },
    }
    instruction = by_recipe.get(asset_recipe_id, generic)
    action = instruction["action_zh"]
    return {
        "evidence_types": instruction["evidence_types"],
        "action_zh": action,
        "next_action_zh": (
            f"请为第 {scene_index} 镜{action}"
            "输出 mp4/mov/m4v;不要用无关网页滚动视频或生成式文字证据卡替代。"
        ),
    }


def _apply_evidence_gap_to_route_policy(
    route_policy: dict,
    diagnosis: dict,
) -> dict:
    updated = dict(route_policy)
    engine_policy = dict(updated.get("engine_policy") or {})
    engine_policy["publish_grade_candidate"] = False
    asset_strategy = dict(updated.get("asset_strategy_v2") or {})
    asset_strategy.update(
        {
            "current_asset_kind": diagnosis["asset_kind"],
            "current_asset_status": diagnosis["asset_status"],
            "publish_grade_visual": False,
            "next_action_zh": diagnosis["next_action_zh"],
        }
    )
    updated["engine_policy"] = engine_policy
    updated["asset_strategy_v2"] = asset_strategy
    route_reason = str(updated.get("route_reason") or "").strip()
    gap_reason = str(diagnosis["source_zh"] or "").strip()
    updated["route_reason"] = (
        f"{route_reason} 当前素材缺口:{gap_reason}" if route_reason else gap_reason
    )
    return updated


def _apply_no_recording_policy_to_route_policy(
    route_policy: dict,
    diagnosis: dict,
) -> dict:
    updated = dict(route_policy)
    engine_policy = dict(updated.get("engine_policy") or {})
    engine_policy["publish_grade_candidate"] = False
    asset_strategy = dict(updated.get("asset_strategy_v2") or {})
    asset_strategy.update(
        {
            "current_asset_kind": diagnosis["asset_kind"],
            "current_asset_status": diagnosis["asset_status"],
            "publish_grade_visual": False,
            "next_action_zh": diagnosis["next_action_zh"],
            "recording_assets_allowed": False,
        }
    )
    updated["engine_policy"] = engine_policy
    updated["asset_strategy_v2"] = asset_strategy
    updated["expected_real_evidence"] = _without_recording_evidence_markers(
        updated.get("expected_real_evidence")
    )
    route_reason = str(updated.get("route_reason") or "").strip()
    no_recording_reason = str(diagnosis["source_zh"] or "").strip()
    updated["route_reason"] = (
        f"{route_reason} 当前项目边界:{no_recording_reason}"
        if route_reason
        else no_recording_reason
    )
    return updated


def _visual_scenes_for_project(
    project: ProjectRef,
    ratio: str,
    style: str = "clean_product",
    profile: str = "douyin_product",
    platform: str = "douyin",
    engine: str = "ffmpeg_card",
    evidence_manifest: dict | None = None,
) -> list[dict]:
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
    capability_report = detect_capabilities()
    available_visuals = _configured_visual_ids(capability_report)
    best_visual = _preferred_visual_for_generation(capability_report)
    if engine == "remotion":
        best_visual = "host_remotion"
        available_visuals.add("host_remotion")
    elif engine == "hyperframes":
        best_visual = "host_hyperframes"
        available_visuals.add("host_hyperframes")
    elif engine == "seedance":
        best_visual = "host_seedance"
        available_visuals.add("host_seedance")
    no_recording_assets = _project_disallows_recording_assets(project)
    scenes = []
    for index, script_scene in enumerate(script_scenes, start=1):
        scene_id = str(script_scene.get("id") or script_scene.get("scene_id") or f"s{index}")
        narration = str(script_scene.get("narration_text") or "")
        script_duration = float(script_scene.get("duration_sec") or 1.0)
        duration = (
            voice_durations.get(scene_id, script_duration)
            if use_voice_durations
            else script_duration
        )
        visual_hint = str(
            script_scene.get("visual_prompt") or script_scene.get("visual_beat") or ""
        )
        on_screen_text = str(
            script_scene.get("on_screen_text") or script_scene.get("subtitle_text") or ""
        )
        role = script_scene.get("role")
        scene_contract = scene_director_contract(
            scene_id=scene_id,
            index=index,
            role=str(role) if role else None,
            ratio=ratio,
            style=style,
        )
        route = _visual_generator_for_scene(
            project,
            scene_id,
            best_visual,
            available_visuals=available_visuals,
            scene_contract=scene_contract,
        )
        route_policy = director_route_policy(
            generator=str(route.get("generator") or "fallback_solid"),
            profile=profile,
            platform=platform,
            blueprint_id=str(scene_contract["blueprint_id"]),
            expected_asset_path=route.get("expected_asset_path"),
            asset_path=route.get("asset_path"),
        )
        evidence_refs = evidence_assets_for_scene(
            evidence_manifest or {},
            expected_real_evidence=route_policy["expected_real_evidence"],
            asset_recipe_id=str(scene_contract.get("asset_recipe_id") or ""),
            scene_id=scene_id,
            project=project,
        )
        route = _route_with_evidence_clip(
            route,
            evidence_refs,
            profile=profile,
            requires_real_evidence=bool(scene_contract.get("requires_real_evidence_asset")),
            asset_recipe_id=str(scene_contract.get("asset_recipe_id") or ""),
        )
        route_policy = director_route_policy(
            generator=str(route.get("generator") or "fallback_solid"),
            profile=profile,
            platform=platform,
            blueprint_id=str(scene_contract["blueprint_id"]),
            expected_asset_path=route.get("expected_asset_path"),
            asset_path=route.get("asset_path"),
        )
        evidence_gap_diagnosis = (
            _matching_evidence_gap_diagnosis(
                scene_contract=scene_contract,
                evidence_refs=evidence_refs,
                profile=profile,
                scene_index=index,
            )
            if not no_recording_assets
            else None
        )
        no_recording_diagnosis = None
        if no_recording_assets and (
            _scene_requires_matching_evidence(scene_contract, profile)
            or str(route.get("generator") or "") in {"hyperframes", "remotion"}
        ):
            no_recording_diagnosis = _no_recording_dynamic_generation_diagnosis(
                scene_contract=scene_contract,
                route=route,
            )
            route_policy = _apply_no_recording_policy_to_route_policy(
                route_policy,
                no_recording_diagnosis,
            )
        elif evidence_gap_diagnosis:
            route_policy = _apply_evidence_gap_to_route_policy(
                route_policy,
                evidence_gap_diagnosis,
            )
        scene_contract = {
            **scene_contract,
            "director_route": route_policy,
            "recording_policy": {
                "recording_assets_allowed": not no_recording_assets,
                "source": (
                    "project_input_no_recording_boundary"
                    if no_recording_assets
                    else "default"
                ),
            },
        }
        duration = max(duration, 0.5)
        director_confirmation = director_board(
            scene_id=scene_id,
            index=index,
            role=str(role) if role else None,
            narration_text=narration,
            on_screen_text=on_screen_text,
            duration_sec=duration,
            generator=str(route.get("generator") or "fallback_solid"),
            expected_asset_path=route.get("expected_asset_path"),
            ratio=ratio,
            style=style,
            profile=profile,
            platform=platform,
        )
        director_confirmation, scene_contract = _apply_script_visual_intent(
            board=director_confirmation,
            contract=scene_contract,
            index=index,
            visual_hint=visual_hint,
            on_screen_text=on_screen_text,
            duration_sec=duration,
            ratio=ratio,
        )
        if no_recording_diagnosis:
            scene_contract = _apply_no_recording_scene_boundary(scene_contract)
            director_confirmation = _apply_no_recording_board_boundary(
                director_confirmation
            )
        scene_asset_diagnosis = asset_diagnosis(
            generator=str(route.get("generator") or "fallback_solid"),
            expected_asset_path=route.get("expected_asset_path"),
            asset_path=route.get("asset_path"),
        )
        if evidence_gap_diagnosis:
            scene_asset_diagnosis = evidence_gap_diagnosis
        elif no_recording_diagnosis:
            scene_asset_diagnosis = no_recording_diagnosis
        review_sheet = director_review_sheet_v2(
            scene_id=scene_id,
            index=index,
            role=str(role) if role else None,
            narration_text=narration,
            on_screen_text=on_screen_text,
            duration_sec=duration,
            generator=str(route.get("generator") or "fallback_solid"),
            expected_asset_path=route.get("expected_asset_path"),
            asset_path=route.get("asset_path"),
            ratio=ratio,
            style=style,
            profile=profile,
            platform=platform,
            board=director_confirmation,
            contract=scene_contract,
        )
        if evidence_gap_diagnosis:
            review_sheet = {
                **review_sheet,
                "asset_source": evidence_gap_diagnosis["source_zh"],
                "asset_status": evidence_gap_diagnosis,
                "asset_gap": evidence_gap_diagnosis["next_action_zh"],
                "route_reason": route_policy["route_reason"],
                "asset_strategy_v2": route_policy["asset_strategy_v2"],
            }
        elif no_recording_diagnosis:
            review_sheet = {
                **review_sheet,
                "asset_source": no_recording_diagnosis["source_zh"],
                "asset_status": no_recording_diagnosis,
                "asset_gap": no_recording_diagnosis["next_action_zh"],
                "route_reason": route_policy["route_reason"],
                "asset_strategy_v2": route_policy["asset_strategy_v2"],
            }
        scene_payload = {
            "scene_id": scene_id,
            "role": role,
            "on_screen_text": on_screen_text,
            "narration_text": narration,
            "duration_sec": duration,
            "visual_prompt": _visual_prompt(
                narration,
                ratio,
                visual_hint,
                on_screen_text,
                style,
            ),
            "brief": visual_brief(
                ratio=ratio,
                style=style,
                profile=profile,
                platform=platform,
            ),
            **route,
            **scene_contract,
            "asset_diagnosis": scene_asset_diagnosis,
            "engine_policy": route_policy["engine_policy"],
            "route_reason": route_policy["route_reason"],
            "asset_strategy_v2": route_policy["asset_strategy_v2"],
            "expected_real_evidence": route_policy["expected_real_evidence"],
            "evidence_asset_refs": evidence_refs,
            "evidence_asset_ids": [asset["id"] for asset in evidence_refs],
            "evidence_video_refs": [
                ref
                for ref in evidence_refs
                if ref.get("evidence_clip_status") in {"generated", "captured"}
            ],
            "director_knowledge_refs": route_policy["director_knowledge_refs"],
            "caption_contract": route_policy["caption_contract"],
            "director_board": director_confirmation,
            "director_review_sheet": review_sheet,
            "director_review_sheet_v2": review_sheet,
            "keyframe_beats": director_confirmation["keyframes"],
        }
        scenes.append(scene_payload)
    if scenes:
        return scenes
    fallback_contract = scene_director_contract(
        scene_id="s1",
        index=1,
        role="hook",
        ratio=ratio,
        style=style,
    )
    fallback_route = director_route_policy(
        generator="fallback_solid",
        profile=profile,
        platform=platform,
        blueprint_id=str(fallback_contract["blueprint_id"]),
        expected_asset_path=None,
        asset_path=None,
    )
    fallback_contract = {**fallback_contract, "director_route": fallback_route}
    fallback_board = director_board(
        scene_id="s1",
        index=1,
        role="hook",
        narration_text="灵剪",
        on_screen_text="灵剪",
        duration_sec=1.0,
        generator="fallback_solid",
        expected_asset_path=None,
        ratio=ratio,
        style=style,
        profile=profile,
        platform=platform,
    )
    fallback_diagnosis = asset_diagnosis(
        generator="fallback_solid",
        expected_asset_path=None,
        asset_path=None,
    )
    fallback_review_sheet = director_review_sheet_v2(
        scene_id="s1",
        index=1,
        role="hook",
        narration_text="灵剪",
        on_screen_text="灵剪",
        duration_sec=1.0,
        generator="fallback_solid",
        expected_asset_path=None,
        asset_path=None,
        ratio=ratio,
        style=style,
        profile=profile,
        platform=platform,
        board=fallback_board,
        contract=fallback_contract,
    )
    return [
        {
            "scene_id": "s1",
            "narration_text": "灵剪",
            "duration_sec": 1.0,
            "visual_prompt": _visual_prompt("灵剪", ratio, style=style),
            "generator": "fallback_solid",
            "asset_path": None,
            "expected_asset_path": None,
            "motion": {"main": "solid_card", "one_main_only": True},
            "motion_spec": {"main": "solid_card", "one_main_only": True},
            "subtitle_burn": True,
            "brief": visual_brief(
                ratio=ratio,
                style=style,
                profile=profile,
                platform=platform,
            ),
            **fallback_contract,
            "asset_diagnosis": fallback_diagnosis,
            "engine_policy": fallback_route["engine_policy"],
            "route_reason": fallback_route["route_reason"],
            "asset_strategy_v2": fallback_route["asset_strategy_v2"],
            "expected_real_evidence": fallback_route["expected_real_evidence"],
            "director_knowledge_refs": fallback_route["director_knowledge_refs"],
            "caption_contract": fallback_route["caption_contract"],
            "director_board": fallback_board,
            "director_review_sheet": fallback_review_sheet,
            "director_review_sheet_v2": fallback_review_sheet,
        }
    ]


def _write_visuals_for_run(
    project: ProjectRef,
    engine: str,
    template: str,
    ratio: str,
    style: str,
    profile: str,
    platform: str,
) -> bool:
    from packages.core.artifacts import artifact_path, write_artifact

    if artifact_path(project, "visuals").exists():
        return False
    profile = _visual_profile_for_project(project, profile)
    evidence_manifest = collect_evidence_assets(project, profile=profile)
    evidence_manifest = materialize_evidence_clips(project, evidence_manifest)
    scenes = _visual_scenes_for_project(
        project,
        ratio,
        style,
        profile,
        platform,
        engine,
        evidence_manifest=evidence_manifest,
    )
    scenes, self_check = self_check_visual_scenes(scenes, ratio=ratio, style=style)
    visual_real_count = sum(1 for scene in scenes if scene["generator"] != "fallback_solid")
    review_sheets = [scene.get("director_review_sheet") for scene in scenes]
    asset_summary = asset_diagnosis_summary(scenes)
    profile_data = _profile_preset_for_project(
        project,
        profile=profile,
        platform=platform,
        ratio=ratio,
        scene_count=len(scenes),
    )
    _apply_visual_profile_to_scenes(scenes, profile_data)
    cost_notices = [
        notice
        for notice in (paid_engine_notice(scene.get("generator", "")) for scene in scenes)
        if notice
    ]
    if engine == "remotion" or any(scene.get("generator") == "remotion" for scene in scenes):
        cost_notices.append(remotion_license_notice())
    evidence_checklist = _evidence_collection_checklist_payload(project, scenes)
    visual_plan = {
        "id": "visuals",
        "ratio": ratio,
        "engine": engine,
        "template": template,
        "style": style,
        "profile": profile,
        "profile_preset": profile_data,
        "profile_required_evidence": list(profile_data.get("required_evidence") or []),
        "director_knowledge_base_v1": director_knowledge_base_v1(),
        "evidence_assets": evidence_manifest,
        "scenes": scenes,
        "director_review_sheet_v2": {
            "version": "v2",
            "purpose": "画面三审给用户看的完整导演分镜确认单。",
            "markdown_artifact": "artifacts/director_review_sheet.md",
            "scenes": review_sheets,
        },
        "asset_diagnosis_summary": asset_summary,
        "evidence_collection_checklist_v1": evidence_checklist,
        "director_router_summary": {
            "version": "v1",
            "routes": [
                {
                    "scene_id": scene.get("scene_id"),
                    "selected_engine": (scene.get("engine_policy") or {}).get(
                        "selected_engine"
                    ),
                    "route_reason": scene.get("route_reason"),
                }
                for scene in scenes
            ],
        },
        "visual_real_count": visual_real_count,
        "visual_total": len(scenes),
        "cost_notices": cost_notices,
        "self_check": self_check,
    }
    write_artifact(project, "visuals", visual_plan)
    _write_director_review_markdown(project, visual_plan)
    _write_evidence_collection_checklist(project, visual_plan)
    return True


@app.command()
def setup(json_output: bool = typer.Option(False, "--json")) -> None:
    report = detect_capabilities()
    payload = report.public_dict()
    payload["user_guidance"] = _setup_user_guidance(payload)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return

    typer.echo("灵剪能力检测")
    typer.echo(report.summary_zh)
    typer.echo("预览档:零配置可用,使用 mock 只能预览,不能 release。")
    typer.echo(
        "发布档:需要真实 LLM、用户录音或自然中文云 TTS、真实画面、"
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
        if kind == "tts" and best.get("quality_tier") != "publish":
            missing.append(
                f"tts: 用户录音或自然中文云 TTS(当前 {best['label_zh']} 仅适合样片)"
            )
            continue
        configured_visual_ids = {
            candidate["id"]
            for candidate in group.get("candidates", [])
            if candidate.get("configured")
        }
        if (
            kind == "visuals"
            and "host_hyperframes" in configured_visual_ids
            and not best["safe_for_release"]
        ):
            missing.append(
                "visuals: 真实视频素材或宿主插件生成的内容画面"
                "(当前内置 HyperFrames 适配器只适合样片动效)"
            )
            continue
        if kind == "visuals" and not best["safe_for_release"]:
            missing.append("visuals: 真实画面插件或每镜 mp4/mov/m4v 视频素材")
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
    typer.echo("最短发布路径:")
    typer.echo(
        "- 配音:把你录好的口播音频拖给我,"
        "或让我引导你开通火山/OpenAI-compatible TTS。"
    )
    typer.echo(
        "- 没有录音时默认开通火山豆包 TTS:"
        "先打开 https://console.volcengine.com/speech/new/setting/activate?projectName=default "
        "开通服务/领取活动,再打开 "
        "https://console.volcengine.com/speech/new/setting/apikeys?projectName=default "
        "创建 API Key。只把 API Key 配到本机,不要发到聊天里。"
    )
    typer.echo(
        "- 画面:优先提供每镜 mp4/mov/m4v;"
        "没有素材时先启用真正的视频生成插件,不要用图片或模板冒充。"
    )
    typer.echo("- 复跑:能力补齐后再运行 `uv run lj run <项目> --release --yes --json`。")
    guidance = payload["user_guidance"]
    typer.echo("当前只做一步:")
    typer.echo(f"- {guidance['single_next_action_zh']}")
    if report.next_steps:
        typer.echo("下一步:")
        for step in report.next_steps:
            typer.echo(f"- {step}")
    typer.echo("说明:订阅 CLI 通常只提供 LLM;TTS 与 FFmpeg 仍可能需要本机能力或单独配置。")


def _setup_user_guidance(payload: dict) -> dict[str, object]:
    capabilities = payload.get("capabilities") if isinstance(payload, dict) else {}
    capabilities = capabilities if isinstance(capabilities, dict) else {}

    def best(kind: str) -> dict:
        group = capabilities.get(kind)
        if not isinstance(group, dict):
            return {}
        item = group.get("best")
        return item if isinstance(item, dict) else {}

    tts = best("tts")
    visuals = best("visuals")
    render = best("render")
    llm = best("llm")

    if tts.get("quality_tier") != "publish":
        single_action = (
            "先解决发布级配音:如果你有录好的口播音频,直接拖给我;"
            "如果没有录音,打开火山豆包新版开通页领取/开通服务,再到 API Key 管理页创建 API Key。"
            "拿到 key 后不要发到聊天里,按你的系统用标准命令存进安全存储"
            "(见 docs/ONBOARDING.md:macOS 钥匙串 / Linux secret-tool / Windows 用户环境变量)。"
        )
    elif visuals.get("safe_for_release") is not True:
        single_action = (
            "先解决发布级画面(三选一):①提供每镜 mp4/mov/m4v 真实视频素材;"
            "②开通火山方舟 Seedance 文生视频——先到方舟「开通管理」只勾 Seedance 模型"
            "(账户余额需 > 200 元,官方硬门槛),再到「API Key 管理」创建 Key,"
            "按 docs/ONBOARDING.md 的命令存进安全存储(不要发聊天里);"
            "③在宿主 agent(Codex app 等)启用能生成动态视频资产的插件。"
            "图片只能作参考,不能当发布级镜头。"
        )
    elif render.get("safe_for_release") is not True:
        single_action = (
            "先解决本机渲染环境:安装 FFmpeg/ffprobe,"
            "并确认 FFmpeg 支持 drawtext/libfreetype 与 AAC。"
        )
    elif llm.get("safe_for_release") is not True:
        single_action = (
            "先解决脚本生成能力:登录 Codex/Claude CLI 继承订阅能力,"
            "没有订阅 CLI 时再配置 OpenAI-compatible LLM。"
        )
    else:
        single_action = (
            "能力已够进入需求澄清:请告诉我平台、主题、内容依据、目标用户、"
            "希望观众做什么,以及你是否有视频素材和口播音频。"
        )

    return {
        "version": "v1",
        "principle_zh": "普通用户每次只做一个最短动作;Codex 负责解释、运行命令和检查结果。",
        "single_next_action_zh": single_action,
        "first_use_workflow_zh": [
            "安装/初始化灵剪 Skill 或 Plugin",
            "能力门诊:继承已有 LLM,检查发布级 TTS、真实动态画面、FFmpeg 与中文字体",
            "补齐当前唯一缺口",
            "确认内容依据:一句话、Markdown、PDF、PPT、网页、GitHub 仓库、已有脚本或截图",
            "生成并审阅脚本",
            "选择/确认音色,展示配音导演确认单,试听并批准配音",
            "展示完整导演分镜确认单 v2,确认每镜素材、构图、动效、转场、字幕、声音和验收点",
            "接入或生成每镜真实动态视频资产",
            "渲染底部 timed captions、合成音轨、跑 --release --strict QA",
            "QA 通过后导出发布包;失败则按 hard failure 逐项补齐",
        ],
        "do_not_zh": [
            "不要让普通用户直接读 doctor --json",
            "不要同时抛出一堆 provider/key/plugin 选择",
            "不要把图片、Ken Burns、模板循环或样片 TTS 说成发布级",
        ],
        "volcengine_links": {
            "activate": "https://console.volcengine.com/speech/new/setting/activate?projectName=default",
            "api_keys": "https://console.volcengine.com/speech/new/setting/apikeys?projectName=default",
        },
        "seedance_ark_links": {
            "open_management": "https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement",
            "api_key": "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
            "note_zh": (
                "开通只勾所需 Seedance 模型(别点全选);Seedance 2.0 开通硬门槛=账户余额 > 200 元;"
                "领 key 后按 docs/ONBOARDING.md 命令存入安全存储"
                "(service=account=lingjian:VOLCENGINE_ARK_API_KEY)。"
            ),
        },
        "stock_audio_zh": (
            "配乐/音效:Pixabay 无公开音乐 API,由宿主 agent 用浏览器能力(Chrome use / computer use)"
            "按情绪搜并下载,或你自带音频;经 `lj ingest audio --kind bgm/sfx` 挂载,渲染自动混音。"
        ),
    }


def _release_missing_actions(required_items: list) -> list[dict[str, str]]:
    missing_ids = {item.id for item in required_items}
    actions: list[dict[str, str]] = []
    if missing_ids & {"publish_tts_provider", "real_tts_provider"}:
        actions.append(
            {
                "need": "发布级中文配音",
                "user_action_zh": (
                    "把已录好的口播音频文件拖给我,"
                    "或打开火山豆包新版控制台开通服务并创建 API Key。"
                ),
                "example_zh": (
                    "没有录音时先打开开通页领取活动/开通服务,再进入 API Key 管理创建一个"
                    " Key;普通用户只需要配置 VOLCENGINE_TTS_API_KEY。"
                ),
                "open_url": (
                    "https://console.volcengine.com/speech/new/setting/activate?"
                    "projectName=default"
                ),
                "fallback_url": (
                    "https://console.volcengine.com/speech/new/setting/apikeys?"
                    "projectName=default"
                ),
            }
        )
    if missing_ids & {"real_llm_provider"}:
        actions.append(
            {
                "need": "真实脚本生成能力",
                "user_action_zh": "登录 Codex/Claude CLI,或提供 OpenAI-compatible LLM 配置。",
                "example_zh": "优先继承已登录的 Codex app/CLI,不要先填 key。",
            }
        )
    if missing_ids & {"ffmpeg", "ffprobe", "ffmpeg_drawtext", "cjk_font"}:
        actions.append(
            {
                "need": "本机渲染环境",
                "user_action_zh": "按 lj setup 的提示安装 FFmpeg/ffprobe/drawtext 与中文字体。",
                "example_zh": "macOS 通常用 Homebrew 安装带 drawtext 的 FFmpeg。",
            }
        )
    if missing_ids & {"publish_visual_provider"}:
        actions.append(
            {
                "need": "发布级真实画面",
                "user_action_zh": (
                    "三选一:①提供每镜 mp4/mov/m4v 视频素材;"
                    "②开通火山方舟 Seedance 文生视频(余额需 > 200 元),领 ARK key 后"
                    "按 docs/ONBOARDING.md 命令存好;"
                    "③让宿主 agent 引导你启用真正的视频生成插件。"
                ),
                "example_zh": "最简单:把每个镜头的视频文件拖给宿主 agent,不要用图片或模板动效。",
                "open_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement",
                "fallback_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
            }
        )
    if not actions:
        actions.append(
            {
                "need": "发布级素材",
                "user_action_zh": "按 lj setup 的必须补齐项逐项提供,补齐前不要继续生成发布片。",
                "example_zh": "缺什么补什么,补齐后再跑 release。",
            }
        )
    return actions


def _project_has_release_video_assets(project: ProjectRef) -> bool:
    assets_dir = project.path / "assets" / "scenes"
    if not assets_dir.exists():
        return False
    video_suffixes = {".mp4", ".mov", ".m4v"}
    return any(
        item.is_file() and item.suffix.lower() in video_suffixes
        for item in assets_dir.iterdir()
    )


def _project_has_existing_release_voice_asset(project: ProjectRef) -> bool:
    voice_path = project.path / "artifacts" / "voice_plan.json"
    if not voice_path.exists():
        return False
    try:
        voice_plan = json.loads(voice_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(voice_plan, dict) or voice_plan.get("provider_is_mock") is True:
        return False
    for raw_path in [voice_plan.get("full_audio_path")]:
        if _project_relative_file_exists(project, raw_path):
            return True
    for segment in voice_plan.get("segments", []):
        if isinstance(segment, dict) and _project_relative_file_exists(
            project,
            segment.get("audio_path"),
        ):
            return True
    return False


def _project_has_visual_plan_artifact(project: ProjectRef) -> bool:
    return (project.path / "artifacts" / "visual_plan.json").exists()


def _project_relative_file_exists(project: ProjectRef, raw_path: object) -> bool:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return False
    path = (project.path / raw_path).resolve()
    try:
        path.relative_to(project.path.resolve())
    except ValueError:
        return False
    return path.exists() and path.is_file()


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


def _capture_url_screenshot(project: ProjectRef, url: str) -> dict:
    command_prefix = _web_screenshot_command_prefix()
    if not command_prefix:
        return {
            "screenshot_status": "unavailable",
            "screenshot_hint_zh": (
                "未检测到 Playwright CLI;可安装宿主浏览器/截图能力后重新运行 "
                "`lj ingest url --screenshot`。"
            ),
        }
    output_rel = Path("assets") / "web_screenshots" / f"url-{_url_digest(url)}.png"
    output_path = project.path / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        *command_prefix,
        "--browser",
        "chromium",
        "--viewport-size",
        "1080,1920",
        "--timeout",
        "15000",
        url,
        str(output_path),
    ]
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "screenshot_status": "failed",
            "screenshot_error": str(exc)[:300],
            "screenshot_hint_zh": "网页截图命令执行失败;请检查浏览器/网络后重试。",
        }
    if completed.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return {
            "screenshot_status": "captured",
            "screenshot_path": str(output_rel),
            "screenshot_tool": _screenshot_tool_label(command_prefix),
            "asset_kind": "static_image_reference",
            "publish_grade_visual_candidate": False,
            "screenshot_note_zh": (
                "网页截图只能作为画面参考或证据线索;"
                "发布级镜头仍需要动态视频素材或真实视频生成器输出。"
            ),
        }
    return {
        "screenshot_status": "failed",
        "screenshot_error": _stderr_tail(completed.stderr),
        "screenshot_hint_zh": (
            "网页截图未成功落盘;不会把该 URL 伪装成已截图。"
            "如使用 Playwright,请先运行 `npx playwright install chromium` 后重试。"
        ),
    }


def _capture_url_recording(project: ProjectRef, url: str) -> dict:
    command_prefix = _web_record_command_prefix()
    if not command_prefix:
        return {
            "recording_status": "unavailable",
            "recording_hint_zh": (
                "未配置网页录屏 CLI。可提供 LINGJIAN_WEB_RECORD_CLI,该命令需接受 "
                "`<url> <output.mp4>` 两个参数并写出真实动态录屏。"
            ),
        }
    output_rel = Path("assets") / "web_recordings" / f"url-{_url_digest(url)}.mp4"
    output_path = project.path / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [*command_prefix, url, str(output_path)]
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "recording_status": "failed",
            "recording_error": str(exc)[:300],
            "recording_hint_zh": "网页录屏命令执行失败;不会把该 URL 伪装成已录屏。",
        }
    if completed.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return _verified_recording_result(
            output_rel=output_rel,
            output_path=output_path,
            command_prefix=command_prefix,
        )
    return {
        "recording_status": "failed",
        "recording_error": _stderr_tail(completed.stderr),
        "recording_hint_zh": "网页录屏未成功落盘;不会把该 URL 伪装成已录屏。",
    }


def _web_screenshot_command_prefix() -> list[str]:
    custom = os.environ.get("LINGJIAN_WEB_SCREENSHOT_CLI", "").strip()
    if custom:
        return [custom]
    playwright = shutil.which("playwright")
    if playwright:
        return [playwright, "screenshot"]
    npx = shutil.which("npx")
    if npx:
        return [npx, "--yes", "playwright", "screenshot"]
    return []


def _web_record_command_prefix() -> list[str]:
    custom = os.environ.get("LINGJIAN_WEB_RECORD_CLI", "").strip()
    if custom:
        return shlex.split(custom)
    if shutil.which("npx") and shutil.which("ffmpeg"):
        adapter = Path(__file__).resolve().parents[3] / "scripts" / "providers" / (
            "hyperframes_web_record_cli.py"
        )
        if adapter.exists():
            return [sys.executable, str(adapter)]
    return []


def _terminal_record_command_prefix() -> list[str]:
    custom = os.environ.get("LINGJIAN_TERMINAL_RECORD_CLI", "").strip()
    if custom:
        return shlex.split(custom)
    if shutil.which("ffmpeg"):
        adapter = Path(__file__).resolve().parents[3] / "scripts" / "providers" / (
            "terminal_record_cli.py"
        )
        if adapter.exists():
            return [sys.executable, str(adapter)]
    return []


def _codex_record_command_prefix() -> list[str]:
    custom = os.environ.get("LINGJIAN_CODEX_RECORD_CLI", "").strip()
    if custom:
        return shlex.split(custom)
    if sys.platform == "darwin" and shutil.which("screencapture") and shutil.which("ffprobe"):
        adapter = Path(__file__).resolve().parents[3] / "scripts" / "providers" / (
            "macos_screen_record_cli.py"
        )
        if adapter.exists():
            return [sys.executable, str(adapter)]
    return []


def _screenshot_tool_label(command_prefix: list[str]) -> str:
    if not command_prefix:
        return ""
    if "playwright" in Path(command_prefix[0]).name:
        return "playwright"
    if Path(command_prefix[0]).name == "npx":
        return "npx playwright"
    return Path(command_prefix[0]).name


def _recording_tool_label(command_prefix: list[str]) -> str:
    if not command_prefix:
        return ""
    if command_prefix[-1].endswith("hyperframes_web_record_cli.py"):
        return "hyperframes-capture-scroll"
    if command_prefix[-1].endswith("terminal_record_cli.py"):
        return "terminal-output-video"
    if command_prefix[-1].endswith("macos_screen_record_cli.py"):
        return "macos-screencapture"
    return Path(command_prefix[0]).name


def _verified_recording_result(
    *,
    output_rel: Path,
    output_path: Path,
    command_prefix: list[str],
    extra: dict | None = None,
) -> dict:
    probe_result = _probe_video_stream(output_path)
    has_video_stream = bool(probe_result.get("source_video_has_video_stream"))
    return {
        "recording_status": "captured" if has_video_stream else "not_verifiable",
        "recording_path": str(output_rel),
        "recording_tool": _recording_tool_label(command_prefix),
        "publish_grade_visual_candidate": has_video_stream,
        **(extra or {}),
        **probe_result,
    }


def _capture_terminal_recording(project: ProjectRef, command: str, role: str) -> dict:
    command_prefix = _terminal_record_command_prefix()
    if not command_prefix:
        return {
            "recording_status": "unavailable",
            "recording_hint_zh": (
                "未配置终端录屏 CLI。可提供 LINGJIAN_TERMINAL_RECORD_CLI,该命令需接受 "
                "`<command> <output.mp4>` 两个参数,自行在受控环境中执行并录制用户授权命令。"
            ),
        }
    output_rel = (
        Path("assets")
        / "evidence"
        / "videos"
        / f"{_safe_name(role or 'terminal_recording')}-{_text_digest(command)}.mp4"
    )
    output_path = project.path / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    recorder_command = [*command_prefix, command, str(output_path)]
    try:
        completed = subprocess.run(
            recorder_command,
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            check=False,
            timeout=COMMAND_EVIDENCE_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "recording_status": "failed",
            "recording_error": str(exc)[:300],
            "recording_hint_zh": "终端录屏命令执行失败;不会把该命令伪装成已录屏。",
        }
    if completed.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return _verified_recording_result(
            output_rel=output_rel,
            output_path=output_path,
            command_prefix=command_prefix,
            extra={
                "recording_evidence_type": "terminal_recording_capture",
                "recording_role": "terminal_recording",
            },
        )
    return {
        "recording_status": "failed",
        "recording_error": _stderr_tail(completed.stderr),
        "recording_hint_zh": "终端录屏未成功落盘;不会把该命令伪装成已录屏。",
    }


def _capture_codex_operation_recording(project: ProjectRef, task: str) -> dict:
    command_prefix = _codex_record_command_prefix()
    if not command_prefix:
        return {
            "recording_status": "unavailable",
            "recording_hint_zh": (
                "未配置 Codex 操作录屏 CLI。可提供 LINGJIAN_CODEX_RECORD_CLI,该命令需接受 "
                "`<task> <output.mp4>` 两个参数,由宿主在 Codex app 中录制真实操作过程。"
            ),
        }
    output_rel = (
        Path("assets")
        / "evidence"
        / "videos"
        / f"codex_operation-{_text_digest(task)}.mp4"
    )
    output_path = project.path / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    recorder_command = [*command_prefix, task, str(output_path)]
    try:
        completed = subprocess.run(
            recorder_command,
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            check=False,
            timeout=COMMAND_EVIDENCE_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "recording_status": "failed",
            "recording_error": str(exc)[:300],
            "recording_hint_zh": "Codex 操作录屏命令执行失败;不会把该任务伪装成已录屏。",
        }
    if completed.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return _verified_recording_result(
            output_rel=output_rel,
            output_path=output_path,
            command_prefix=command_prefix,
            extra={
                "recording_evidence_type": "codex_operation_recording",
                "recording_role": "codex_recording",
            },
        )
    return {
        "recording_status": "failed",
        "recording_error": _stderr_tail(completed.stderr),
        "recording_hint_zh": "Codex 操作录屏未成功落盘;不会把该任务伪装成已录屏。",
    }


def _url_digest(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _file_digest(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _probe_video_stream(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {
            "source_video_probe_status": "ffprobe_unavailable",
            "source_video_has_video_stream": False,
            "source_video_probe_hint_zh": (
                "未检测到 ffprobe;该视频已收进项目,"
                "但尚不能作为发布级动态证据候选。"
            ),
        }
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type:format=duration",
                "-of",
                "json",
                str(path),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "source_video_probe_status": "failed",
            "source_video_has_video_stream": False,
            "source_video_probe_error": str(exc)[:300],
            "source_video_probe_hint_zh": (
                "ffprobe 未能完成视频流探测;"
                "后续 strict QA 不会把它当作可验证动态证据。"
            ),
        }
    if completed.returncode != 0:
        return {
            "source_video_probe_status": "not_verifiable",
            "source_video_has_video_stream": False,
            "source_video_probe_error": _stderr_tail(completed.stderr),
            "source_video_probe_hint_zh": (
                "ffprobe 未能确认该文件包含有效视频流;"
                "请提供真实 mp4/mov/m4v/webm 录屏。"
            ),
        }
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {
            "source_video_probe_status": "not_verifiable",
            "source_video_has_video_stream": False,
            "source_video_probe_error": "ffprobe 输出不是合法 JSON。",
            "source_video_probe_hint_zh": (
                "ffprobe 未能确认该文件包含有效视频流;"
                "请重新提供视频素材。"
            ),
        }
    has_video = any(
        isinstance(stream, dict) and stream.get("codec_type") == "video"
        for stream in payload.get("streams", [])
    )
    if has_video:
        result = {
            "source_video_probe_status": "verifiable",
            "source_video_has_video_stream": True,
            "source_video_probe_tool": "ffprobe",
            "source_video_probe_hint_zh": (
                "ffprobe 已确认该文件包含视频流,"
                "可作为发布级动态证据候选。"
            ),
        }
        duration_sec = _probe_media_duration_sec(payload)
        if duration_sec is not None:
            result["source_video_duration_sec"] = duration_sec
        return result
    return {
        "source_video_probe_status": "not_verifiable",
        "source_video_has_video_stream": False,
        "source_video_probe_hint_zh": (
            "ffprobe 未发现 video stream;"
            "该文件不能作为发布级动态视频素材。"
        ),
    }


def _probe_audio_stream(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {
            "source_audio_probe_status": "ffprobe_unavailable",
            "source_audio_has_audio_stream": False,
            "source_audio_probe_hint_zh": (
                "未检测到 ffprobe;不能确认该声音素材包含有效音频流。"
            ),
        }
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type:format=duration",
                "-of",
                "json",
                str(path),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "source_audio_probe_status": "failed",
            "source_audio_has_audio_stream": False,
            "source_audio_probe_error": str(exc)[:300],
            "source_audio_probe_hint_zh": (
                "ffprobe 未能完成音频流探测;不会把它写入 BGM/SFX 执行链。"
            ),
        }
    if completed.returncode != 0:
        return {
            "source_audio_probe_status": "not_verifiable",
            "source_audio_has_audio_stream": False,
            "source_audio_probe_error": _stderr_tail(completed.stderr),
            "source_audio_probe_hint_zh": (
                "ffprobe 未能确认该文件包含有效音频流;请换成可播放的 wav/mp3/m4a/aac。"
            ),
        }
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {
            "source_audio_probe_status": "not_verifiable",
            "source_audio_has_audio_stream": False,
            "source_audio_probe_error": "ffprobe 输出不是合法 JSON。",
            "source_audio_probe_hint_zh": (
                "ffprobe 未能确认该文件包含有效音频流;请重新提供声音素材。"
            ),
        }
    has_audio = any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in payload.get("streams", [])
    )
    if has_audio:
        result = {
            "source_audio_probe_status": "verifiable",
            "source_audio_has_audio_stream": True,
            "source_audio_probe_tool": "ffprobe",
            "source_audio_probe_hint_zh": "ffprobe 已确认该文件包含音频流,可进入 BGM/SFX 执行链。",
        }
        duration_sec = _probe_media_duration_sec(payload)
        if duration_sec is not None:
            result["source_audio_duration_sec"] = duration_sec
        return result
    return {
        "source_audio_probe_status": "not_verifiable",
        "source_audio_has_audio_stream": False,
        "source_audio_probe_hint_zh": (
            "ffprobe 未发现 audio stream;该文件不能作为 BGM/SFX 声音素材。"
        ),
    }


def _probe_media_duration_sec(payload: dict) -> float | None:
    try:
        duration = float((payload.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        return None
    if duration <= 0:
        return None
    return round(duration, 3)


def _text_digest(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _load_input_assets(assets_path: Path) -> list[dict]:
    try:
        current = (
            json.loads(assets_path.read_text(encoding="utf-8"))
            if assets_path.exists()
            else []
        )
    except json.JSONDecodeError:
        current = []
    return current if isinstance(current, list) else []


def _safe_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)
    return safe.strip("-") or "evidence"


def _redact_sensitive_cli_text(value: str) -> str:
    import re

    redacted = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)\S+", r"\1***", value)
    redacted = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|token|secret)(\s*[:=]\s*)\S+",
        r"\1\2***",
        redacted,
    )
    redacted = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1***", redacted)
    return redacted


def _terminal_command_log_text(
    command: str,
    completed: subprocess.CompletedProcess[str] | None,
    error: str | None = None,
) -> str:
    command_redacted = _redact_sensitive_cli_text(command)
    if completed is None:
        return "\n".join(
            [
                "# 灵剪终端命令证据",
                f"command: {command_redacted}",
                "status: failed_to_start",
                f"error: {_redact_sensitive_cli_text(error or '')}",
                "",
            ]
        )
    stdout = _redact_sensitive_cli_text(completed.stdout or "")
    stderr = _redact_sensitive_cli_text(completed.stderr or "")
    return "\n".join(
        [
            "# 灵剪终端命令证据",
            f"command: {command_redacted}",
            f"exit_code: {completed.returncode}",
            "--- stdout ---",
            stdout,
            "--- stderr ---",
            stderr,
            "",
        ]
    )


def _stderr_tail(stderr: str) -> str:
    lines = [line for line in (stderr or "").splitlines() if line.strip()]
    return "\n".join(lines[-4:])[:400]


@ingest_app.command("url")
def ingest_url(
    project: Path,
    url: str = typer.Option(...),
    screenshot: bool = typer.Option(False, "--screenshot"),
    record: bool = typer.Option(False, "--record"),
    scene_id: Optional[str] = typer.Option(None, "--scene-id"),
    json_output: bool = typer.Option(False, "--json"),
):
    ref = ProjectRef(project, project.name)
    assets = ref.path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    screenshot_result = _capture_url_screenshot(ref, url) if screenshot else {}
    recording_result = _capture_url_recording(ref, url) if record else {}
    target_scene_id = str(scene_id or "").strip()
    followup = (
        _url_recording_followup(
            ref,
            scene_id=target_scene_id,
            recording_result=recording_result,
        )
        if record
        else {}
    )
    assets_path = assets / "input_assets.json"
    current = _load_input_assets(assets_path)
    current.append(
        {
            "type": "url",
            "source_uri": url,
            "screenshot_opt_in": screenshot,
            "recording_opt_in": record,
            "target_scene_id": target_scene_id,
            "is_untrusted_input": True,
            **screenshot_result,
            **recording_result,
            **followup,
        }
    )
    assets_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(
        {
            "ok": True,
            "status": "input_ready",
            "is_untrusted_input": True,
            "screenshot_opt_in": screenshot,
            "recording_opt_in": record,
            "target_scene_id": target_scene_id,
            **screenshot_result,
            **recording_result,
            **followup,
        },
        json_output,
    )


@ingest_app.command("command")
def ingest_command(
    project: Path,
    command: str = typer.Option(..., "--command"),
    role: str = typer.Option("terminal_log"),
    record: bool = typer.Option(False, "--record"),
    scene_id: Optional[str] = typer.Option(None, "--scene-id"),
    json_output: bool = typer.Option(False, "--json"),
):
    if not command.strip():
        _fail(
            LingjianError(
                "INPUT_COMMAND_EMPTY",
                "终端命令不能为空。",
                "请传入一条用户明确授权执行的本机命令。",
            ),
            json_output,
        )
    try:
        command_args = shlex.split(command)
    except ValueError as exc:
        _fail(
            LingjianError(
                "INPUT_COMMAND_INVALID",
                "终端命令无法解析。",
                "如果需要管道或复杂 shell 语法,请显式使用 `zsh -lc '...'`。",
                {"error": str(exc)[:200]},
            ),
            json_output,
        )
    if not command_args:
        _fail(
            LingjianError(
                "INPUT_COMMAND_EMPTY",
                "终端命令不能为空。",
                "请传入一条用户明确授权执行的本机命令。",
            ),
            json_output,
        )
    ref = ProjectRef(project, project.name)
    logs_dir = ref.path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    safe_role = _safe_name(role)
    output_rel = Path("logs") / f"{safe_role}-{_text_digest(command)}.log"
    output_path = ref.path / output_rel
    status = "captured"
    exit_code: int | None = None
    try:
        completed = subprocess.run(
            command_args,
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            check=False,
            timeout=COMMAND_EVIDENCE_TIMEOUT_SEC,
        )
        exit_code = completed.returncode
        output_path.write_text(
            _terminal_command_log_text(command, completed),
            encoding="utf-8",
        )
        if completed.returncode != 0:
            status = "captured_nonzero_exit"
    except subprocess.TimeoutExpired as exc:
        status = "timeout"
        output_path.write_text(
            _terminal_command_log_text(command, None, f"timeout: {exc}"),
            encoding="utf-8",
        )
    except OSError as exc:
        status = "failed_to_start"
        output_path.write_text(
            _terminal_command_log_text(command, None, str(exc)),
            encoding="utf-8",
    )
    recording_result = _capture_terminal_recording(ref, command, role) if record else {}
    target_scene_id = str(scene_id or "").strip()
    followup = (
        _terminal_recording_followup(
            ref,
            scene_id=target_scene_id,
            recording_result=recording_result,
        )
        if record
        else {}
    )
    assets = ref.path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    assets_path = assets / "input_assets.json"
    current = _load_input_assets(assets_path)
    current.append(
        {
            "type": "terminal_command",
            "source_uri": str(output_rel),
            "role": role,
            "command_redacted": _redact_sensitive_cli_text(command),
            "command_status": status,
            "command_exit_code": exit_code,
            "working_directory_redacted": True,
            "is_untrusted_input": True,
            "recording_opt_in": record,
            "target_scene_id": target_scene_id,
            **recording_result,
            **followup,
            "note_zh": "终端命令文本证据,可渲染为回放短片;不是屏幕录制。",
        }
    )
    assets_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(
        {
            "ok": True,
            "status": "input_ready",
            "command_status": status,
            "command_exit_code": exit_code,
            "log_path": str(output_rel),
            "command_redacted": _redact_sensitive_cli_text(command),
            "working_directory_redacted": True,
            "recording_opt_in": record,
            "target_scene_id": target_scene_id,
            **recording_result,
            **followup,
            "note_zh": "已保存为终端文本证据,不是屏幕录制。",
        },
        json_output,
    )


@ingest_app.command("codex")
def ingest_codex(
    project: Path,
    task: str = typer.Option(..., "--task"),
    scene_id: Optional[str] = typer.Option(None, "--scene-id"),
    allow_screen_recording: bool = typer.Option(False, "--allow-screen-recording"),
    json_output: bool = typer.Option(False, "--json"),
):
    if not task.strip():
        _fail(
            LingjianError(
                "INPUT_CODEX_TASK_EMPTY",
                "Codex 操作任务不能为空。",
                "请用一句话描述要录制的 Codex app 操作,"
                "例如“展示 lingjian-video 如何进入分镜三审”。",
            ),
            json_output,
        )
    ref = ProjectRef(project, project.name)
    recording_result = (
        _capture_codex_operation_recording(ref, task)
        if allow_screen_recording
        else {
            "recording_status": "pending_user_consent",
            "recording_hint_zh": (
                "已记录 Codex 操作录屏任务,但尚未获得录制当前屏幕的明确授权。"
                "确认屏幕无隐私内容后,重新运行本命令并加 --allow-screen-recording;或手动录屏后用 "
                "`lj ingest video --role codex_recording --scene-id ...` 绑定。"
            ),
        }
    )
    target_scene_id = str(scene_id or "").strip()
    task_redacted = _redact_sensitive_cli_text(task)
    followup = _codex_ingest_followup(
        ref,
        task_redacted=task_redacted,
        scene_id=target_scene_id,
        recording_result=recording_result,
    )
    assets = ref.path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    assets_path = assets / "input_assets.json"
    current = _load_input_assets(assets_path)
    current.append(
        {
            "type": "codex_operation",
            "source_uri": "",
            "role": "codex_recording",
            "task_redacted": task_redacted,
            "recording_task_redacted": task_redacted,
            "recording_opt_in": allow_screen_recording,
            "screen_recording_consent": allow_screen_recording,
            "target_scene_id": target_scene_id,
            **recording_result,
            **followup,
            "note_zh": (
                "Codex 操作录屏任务证据;只有 recording_status=captured 且后续 ffprobe "
                "确认视频流后,才可作为发布级动态证据候选。"
            ),
        }
    )
    assets_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(
        {
            "ok": True,
            "status": "input_ready",
            "task_redacted": task_redacted,
            "recording_task_redacted": task_redacted,
            "recording_opt_in": allow_screen_recording,
            "screen_recording_consent": allow_screen_recording,
            "target_scene_id": target_scene_id,
            **recording_result,
            **followup,
            "note_zh": "已记录 Codex 操作录屏任务;未成功落盘时不会伪造录屏证据。",
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
    if not file.exists() or not file.is_file():
        _fail(
            LingjianError(
                "INPUT_IMAGE_NOT_FOUND",
                "未找到用户提供的图片素材。",
                "请传入本机存在的 png/jpg/jpeg/webp 图片文件。",
                {"file": str(file)},
            ),
            json_output,
        )
    suffix = file.suffix.lower()
    if suffix not in IMAGE_EVIDENCE_SUFFIXES:
        _fail(
            LingjianError(
                "INPUT_IMAGE_UNSUPPORTED_FORMAT",
                "图片素材格式不支持。",
                "请提供 png、jpg、jpeg 或 webp 文件。",
                {"suffix": suffix or "(none)"},
            ),
            json_output,
        )
    ref = ProjectRef(project, project.name)
    assets = ref.path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    images_dir = assets / "reference_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    safe_role = _safe_name(role or "reference_image")
    output_rel = (
        Path("assets")
        / "reference_images"
        / f"{safe_role}-{_file_digest(file)}{suffix}"
    )
    output_path = ref.path / output_rel
    shutil.copyfile(file, output_path)
    image_item = {
        "type": "image",
        "source_uri": str(output_rel),
        "role": role,
        "copied_into_project": True,
        "original_path_redacted": True,
        "is_untrusted_input": True,
        "ocr_status": "not_requested",
        "publish_grade_visual": False,
        "publish_grade_visual_candidate": False,
        "asset_kind": "static_image_reference",
        "note_zh": "图片已作为静态参考收进项目;不能直接作为发布级视频镜头。",
        "next_action_zh": "发布级画面仍需要每镜动态视频素材或真实视频生成器输出 mp4/mov/m4v。",
    }
    assets_path = assets / "input_assets.json"
    current = _load_input_assets(assets_path)
    current.append(image_item)
    assets_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(
        {
            "ok": True,
            "status": "input_ready",
            "role": role,
            "image_path": str(output_rel),
            "original_path_redacted": True,
            "publish_grade_visual_candidate": False,
            "asset_kind": "static_image_reference",
            "note_zh": image_item["note_zh"],
            "next_action_zh": image_item["next_action_zh"],
        },
        json_output,
    )


@ingest_app.command("audio")
def ingest_audio(
    project: Path,
    file: Path = typer.Option(...),
    kind: str = typer.Option(..., "--kind"),
    scene_id: Optional[str] = typer.Option(None, "--scene-id"),
    at_sec: float = typer.Option(0.0, "--at-sec"),
    gain_db: float = typer.Option(SFX_GAIN_DB_DEFAULT, "--gain-db"),
    bgm_to_voice_db: float = typer.Option(BGM_TO_VOICE_DB_DEFAULT, "--bgm-to-voice-db"),
    action: Optional[str] = typer.Option(None, "--action"),
    purpose: Optional[str] = typer.Option(None, "--purpose"),
    visual_event: Optional[str] = typer.Option(None, "--visual-event"),
    json_output: bool = typer.Option(False, "--json"),
):
    if not file.exists() or not file.is_file():
        _fail(
            LingjianError(
                "INPUT_AUDIO_NOT_FOUND",
                "未找到用户提供的声音素材。",
                "请传入本机存在的 wav/mp3/m4a/aac 音频文件。",
                {"file": str(file)},
            ),
            json_output,
        )
    suffix = file.suffix.lower()
    if suffix not in AUDIO_ASSET_SUFFIXES:
        _fail(
            LingjianError(
                "INPUT_AUDIO_UNSUPPORTED_FORMAT",
                "声音素材格式不支持。",
                "请提供 wav、mp3、m4a 或 aac 文件。",
                {"suffix": suffix or "(none)"},
            ),
            json_output,
        )
    normalized_kind = kind.strip().lower()
    if normalized_kind not in {"bgm", "sfx"}:
        _fail(
            LingjianError(
                "INPUT_AUDIO_KIND_UNSUPPORTED",
                "声音素材类型不支持。",
                "请使用 --kind bgm 或 --kind sfx。",
                {"kind": kind},
            ),
            json_output,
        )
    target_scene_id = str(scene_id or "").strip()
    if normalized_kind == "sfx" and not target_scene_id:
        _fail(
            LingjianError(
                "INPUT_AUDIO_SCENE_REQUIRED",
                "SFX 音效素材必须绑定到具体镜头。",
                "请补充 --scene-id,让音效进入同镜 audio_mix.sfx_events。",
            ),
            json_output,
        )
    ref = ProjectRef(project, project.name)
    from packages.core.artifacts import artifact_path, read_json, write_artifact

    voice_path = artifact_path(ref, "voice")
    if not voice_path.exists():
        _fail(
            LingjianError(
                "VOICE_PLAN_REQUIRED_FOR_AUDIO_ASSET",
                "导入 BGM/SFX 前需要已有 voice_plan.json。",
                "请先完成配音阶段,再导入 BGM 或同镜 SFX 音效素材。",
            ),
            json_output,
        )
    voice_plan = read_json(voice_path)
    if not isinstance(voice_plan, dict):
        _fail(
            LingjianError(
                "VOICE_PLAN_INVALID",
                "voice_plan.json 不是合法对象。",
                "请重新生成配音计划后再导入 BGM/SFX。",
            ),
            json_output,
        )
    audio_probe = _probe_audio_stream(file)
    if audio_probe.get("source_audio_has_audio_stream") is not True:
        _fail(
            LingjianError(
                "INPUT_AUDIO_NOT_VERIFIABLE",
                "声音素材未通过 ffprobe 音频流校验。",
                "请换成可播放、可 ffprobe 验证的 wav/mp3/m4a/aac,再重新导入 BGM/SFX。",
                {
                    **audio_probe,
                    "original_path_redacted": True,
                    "suffix": suffix or "(none)",
                },
            ),
            json_output,
        )
    audio_dir = ref.path / "assets" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_rel = (
        Path("assets")
        / "audio"
        / f"{normalized_kind}-{_file_digest(file)}{suffix}"
    )
    output_path = ref.path / output_rel
    shutil.copyfile(file, output_path)
    audio_assets = voice_plan.get("audio_assets")
    if not isinstance(audio_assets, dict):
        audio_assets = {}
    if normalized_kind == "bgm":
        audio_assets["bgm"] = {
            "path": str(output_rel),
            "bgm_to_voice_db": float(bgm_to_voice_db),
            "source_type": "user-provided-audio",
            "original_path_redacted": True,
            **audio_probe,
        }
    else:
        sfx_events = audio_assets.get("sfx")
        if not isinstance(sfx_events, list):
            sfx_events = []
        local_at_sec = max(float(at_sec), 0.0)
        event = {
            "path": str(output_rel),
            "scene_id": target_scene_id,
            "at_sec": local_at_sec,
            "local_at_sec": local_at_sec,
            "time_basis": "scene_local",
            "gain_db": float(gain_db),
            "source_type": "user-provided-audio",
            "original_path_redacted": True,
            **audio_probe,
        }
        for key, value in {
            "action": action,
            "purpose": purpose,
            "visual_event": visual_event,
        }.items():
            text = str(value or "").strip()
            if text:
                event[key] = text
        sfx_events.append(event)
        audio_assets["sfx"] = sfx_events
    voice_plan["audio_assets"] = audio_assets
    write_artifact(ref, "voice", voice_plan)
    assets_path = ref.path / "assets" / "input_assets.json"
    current = _load_input_assets(assets_path)
    input_item = {
        "type": "audio",
        "source_uri": str(output_rel),
        "kind": normalized_kind,
        "copied_into_project": True,
        "original_path_redacted": True,
        "is_untrusted_input": True,
        **audio_probe,
        "note_zh": (
            "声音素材已复制到项目内 assets/audio,并写入 voice_plan.audio_assets;"
            "发布级仍需 render/QA 验证混音、音量和人声优先。"
        ),
    }
    if target_scene_id:
        input_item["target_scene_id"] = target_scene_id
    if normalized_kind == "sfx":
        input_item["at_sec"] = max(float(at_sec), 0.0)
        input_item["local_at_sec"] = max(float(at_sec), 0.0)
        input_item["time_basis"] = "scene_local"
    current.append(input_item)
    assets_path.parent.mkdir(parents=True, exist_ok=True)
    assets_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    approval_command = _approve_next_command(ref, "voice")
    payload = {
        "ok": True,
        "status": "audio_asset_ready",
        "kind": normalized_kind,
        "audio_path": str(output_rel),
        "original_path_redacted": True,
        **audio_probe,
        "voice_plan_updated": True,
        "voice_reapproval_required": True,
        "approval_command": approval_command,
        "next_action_zh": (
            "请重新试听/审阅 voice_plan.json 中的配音、timed captions 与 BGM/SFX 设计,"
            "确认后重新批准 voice,再重跑 render/QA。"
        ),
    }
    if normalized_kind == "bgm":
        payload["bgm_to_voice_db"] = float(bgm_to_voice_db)
    else:
        payload.update(
            {
                "scene_id": target_scene_id,
                "at_sec": max(float(at_sec), 0.0),
                "local_at_sec": max(float(at_sec), 0.0),
                "time_basis": "scene_local",
                "gain_db": float(gain_db),
            }
        )
    recovery_fields = _audio_asset_recovery_fields(ref)
    if recovery_fields:
        payload.update(recovery_fields)
        next_command = recovery_fields.get("audio_asset_next_command")
        if next_command:
            payload.update(
                {
                    "next_command_kind": "ingest_audio",
                    "next_command": next_command,
                    "audio_assets_remaining_before_voice_approval": True,
                    "approval_blocked_until_audio_assets_zh": (
                        "声音素材已导入,但分镜仍有 BGM/SFX 缺口;"
                        "请先继续按 next_command 补齐剩余声音素材。"
                        "全部补齐后仍必须重新试听并批准 voice。"
                    ),
                    "next_action_zh": (
                        "声音素材已复制到项目内,但分镜仍有 BGM/SFX 缺口;"
                        "请先执行 next_command 补齐下一条声音素材。"
                        "全部声音素材补齐后,再重新试听/批准 voice。"
                    ),
                }
            )
    else:
        payload.update(
            {
                "next_command_kind": "approve_voice",
                "next_command": approval_command,
            }
        )
    _emit(payload, json_output)


@ingest_app.command("video")
def ingest_video(
    project: Path,
    file: Path = typer.Option(...),
    role: str = typer.Option("screen_recording"),
    scene_id: Optional[str] = typer.Option(None, "--scene-id"),
    task: Optional[str] = typer.Option(None, "--task"),
    json_output: bool = typer.Option(False, "--json"),
):
    if not file.exists() or not file.is_file():
        _fail(
            LingjianError(
                "INPUT_VIDEO_NOT_FOUND",
                "未找到用户提供的视频素材。",
                "请传入本机存在的 mp4/mov/m4v/webm 视频文件。",
                {"file": str(file)},
            ),
            json_output,
        )
    suffix = file.suffix.lower()
    if suffix not in VIDEO_EVIDENCE_SUFFIXES:
        _fail(
            LingjianError(
                "INPUT_VIDEO_UNSUPPORTED_FORMAT",
                "视频素材格式不支持。",
                "请提供 mp4、mov、m4v 或 webm 文件。",
                {"suffix": suffix or "(none)"},
            ),
            json_output,
        )
    ref = ProjectRef(project, project.name)
    assets = ref.path / "assets"
    videos_dir = assets / "evidence" / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    safe_role = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in role)
    output_rel = (
        Path("assets")
        / "evidence"
        / "videos"
        / f"{safe_role}-{_file_digest(file)}{suffix}"
    )
    output_path = ref.path / output_rel
    shutil.copyfile(file, output_path)
    probe_result = _probe_video_stream(output_path)
    target_scene_id = str(scene_id or "").strip()
    followup = _video_ingest_followup(
        ref,
        role=role,
        scene_id=target_scene_id,
        probe_result=probe_result,
    )
    task_metadata = _recording_task_metadata(task)
    screen_recording_metadata = _manual_video_screen_recording_consent_metadata(role)
    recording_status = (
        "captured" if probe_result.get("source_video_has_video_stream") else "not_verifiable"
    )
    assets_path = assets / "input_assets.json"
    try:
        current = (
            json.loads(assets_path.read_text(encoding="utf-8"))
            if assets_path.exists()
            else []
        )
    except json.JSONDecodeError:
        current = []
    if not isinstance(current, list):
        current = []
    current.append(
        {
            "type": "video",
            "source_uri": str(output_rel),
            "role": role,
            "copied_into_project": True,
            "original_path_redacted": True,
            "is_untrusted_input": True,
            "target_scene_id": target_scene_id,
            "recording_status": recording_status,
            "publish_grade_visual_candidate": bool(
                probe_result.get("source_video_has_video_stream")
            ),
            **task_metadata,
            **screen_recording_metadata,
            **probe_result,
            **followup,
        }
    )
    assets_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(
        {
            "ok": True,
            "status": "input_ready",
            "role": role,
            "video_path": str(output_rel),
            "original_path_redacted": True,
            "target_scene_id": target_scene_id,
            "recording_status": recording_status,
            "publish_grade_visual_candidate": bool(
                probe_result.get("source_video_has_video_stream")
            ),
            **task_metadata,
            **screen_recording_metadata,
            **probe_result,
            **followup,
        },
        json_output,
    )


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
    style: str = typer.Option("clean_product", "--style"),
    profile: str = typer.Option("douyin_product", "--profile"),
    from_file: Optional[Path] = typer.Option(
        None,
        "--from-file",
        help="宿主 agent 自产脚本 JSON(含 scenes[]);LLM 宿主首选,优先于 provider,不 fork 外部 CLI",
    ),
    emit_contract: bool = typer.Option(
        False,
        "--emit-contract",
        help="只导出脚本创作契约(brief:钩子库/风格锁/素材摘要)供宿主 agent 按稿创作,不生成脚本。",
    ),
    json_output: bool = typer.Option(False, "--json"),
):
    from packages.core.artifacts import artifact_path, read_json, write_artifact

    ref = ProjectRef(project, project.name)
    resolved_profile = _profile_for_project(
        ref,
        type_=type,
        platform=platform,
        profile=profile,
    )
    script_contract = script_generation_contract(
        type_=type,
        platform=platform,
        language=language,
        ratio=ratio,
        duration=duration,
        style=style,
        profile=resolved_profile,
    )
    script_contract["profile_preset"] = _profile_preset_for_project(
        ref,
        profile=resolved_profile,
        platform=platform,
        ratio=ratio,
        duration=duration,
    )
    source_brief = _script_source_brief_for_project(ref)
    if source_brief:
        script_contract["source_brief"] = source_brief

    # --emit-contract:只导出创作契约(brief),供宿主 agent 按钩子库/风格锁/素材摘要自产脚本。
    if emit_contract:
        write_artifact(
            ref,
            "script_contract",
            {
                "id": "script_contract",
                "type": type,
                "platform": platform,
                "language": language,
                "ratio": ratio,
                "target_duration_sec": duration,
                **script_contract,
                "authoring_note_zh": (
                    "宿主 agent(Claude/Codex/Gemini 等 LLM)直接按此契约创作脚本,"
                    "写成 {\"scenes\":[{\"id\":..,\"narration_text\":..}, ...]} 后用 "
                    "`lj script ... --from-file <脚本.json>` 回填;"
                    "无需、也不应 fork 外部 claude/codex CLI。"
                ),
            },
        )
        _emit(
            {
                "ok": True,
                "status": "contract_emitted",
                "artifact": "artifacts/script_contract.json",
            },
            json_output,
        )
        return

    current_path = artifact_path(ref, "script")
    revision = read_json(current_path).get("revision", 0) + 1 if current_path.exists() else 1
    scenes = [{"id": "s1", "narration_text": "这是一段测试脚本。"}]

    if from_file is not None:
        # 宿主自产(第一优先级):宿主 agent 本身就是 LLM,直接产出脚本,不 fork 外部 CLI。
        from providers.validation import validate_script_output

        authored_path = from_file if from_file.is_absolute() else (Path.cwd() / from_file)
        if not authored_path.exists():
            _fail(
                LingjianError(
                    "INVALID_ARGUMENT",
                    "--from-file 指向的脚本文件不存在。",
                    f"请确认路径:{authored_path}",
                    {"path": str(from_file)},
                ),
                json_output,
            )
        try:
            authored = read_json(authored_path)
        except (ValueError, OSError) as exc:
            _fail(
                LingjianError(
                    "INVALID_ARGUMENT",
                    "--from-file 不是合法 JSON。",
                    "请确认文件是 UTF-8 JSON,且形如 {\"scenes\":[{\"narration_text\":..}, ...]}。",
                    {"error": str(exc)},
                ),
                json_output,
            )
        if isinstance(authored, dict) and isinstance(authored.get("scenes"), list):
            candidate = authored
        elif isinstance(authored, list):
            candidate = {"scenes": authored}
        else:
            candidate = {"scenes": []}
        try:
            validated = validate_script_output(candidate, "host_authored")
        except LingjianError as exc:
            _fail(exc, json_output)
        scenes = validated["scenes"]
        provider_id = "host_authored"
        provider_is_mock = False
    else:
        # provider 路径:claude_cli/codex_cli 等只给「宿主不是 LLM」的无头/CI 环境兜底。
        try:
            provider_ref = resolve_provider(provider, "llm")
        except LingjianError as exc:
            _fail(exc, json_output)
        generate_script = getattr(provider_ref, "generate_script", None)
        if callable(generate_script):
            try:
                generated = generate_script(script_contract)
            except LingjianError as exc:
                _fail(exc, json_output)
            if isinstance(generated.get("scenes"), list) and generated["scenes"]:
                scenes = generated["scenes"]
        provider_id = provider_ref.id
        provider_is_mock = provider_ref.is_mock

    summary = plan_summary(
        platform=platform,
        ratio=ratio,
        duration=duration,
        scene_count=len(scenes),
        style=style,
        profile=resolved_profile,
    )
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
            "style": script_contract["style"],
            "profile": script_contract["profile"],
            "profile_preset": {
                **script_contract["profile_preset"],
                "duration_sec": duration,
                "scene_count": len(scenes),
            },
            "style_lock": script_contract["style_lock"],
            "hook_library": script_contract["hook_library"],
            "source_brief": script_contract.get("source_brief"),
            "plan_summary": summary,
            "provider_id": provider_id,
            "provider_is_mock": provider_is_mock,
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


@app.command("voice-options")
def voice_options(
    project: Path,
    provider: str = typer.Option("auto", "--provider"),
    sample_text: Optional[str] = typer.Option(None, "--sample-text"),
    limit: int = typer.Option(5, "--limit", min=1, max=5),
    json_output: bool = typer.Option(False, "--json"),
):
    ref = ProjectRef(project, project.name)
    try:
        payload = _write_voice_options(ref, provider, sample_text, limit)
    except LingjianError as exc:
        _fail(exc, json_output)
    _emit(_voice_choice_response(project, payload), json_output)


@app.command()
def voice(
    project: Path,
    provider: str = typer.Option("auto"),
    voice: str = typer.Option("auto"),
    audio_file: Optional[Path] = typer.Option(None, "--audio-file"),
    no_voiceover: bool = typer.Option(
        False, "--no-voiceover", help="无旁白模式:不合成配音,文字卡代旁白承担叙事(新客观主义等)"
    ),
    json_output: bool = typer.Option(False, "--json"),
):
    ref = ProjectRef(project, project.name)
    try:
        wrote_voice = _write_voice_plan(
            ref, provider, voice, audio_file, voiceover=not no_voiceover
        )
        caption_repair = None if wrote_voice else _backfill_voice_plan_caption_cues(ref)
    except LingjianError as exc:
        _fail(exc, json_output)
    _emit(
        {
            "ok": True,
            "status": "awaiting_review",
            "artifact": "artifacts/voice_plan.json",
            "voice_caption_repair": caption_repair,
        },
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
    platform: str = typer.Option("douyin", "--platform"),
    style: str = typer.Option("clean_product", "--style"),
    profile: str = typer.Option("douyin_product", "--profile"),
    json_output: bool = typer.Option(False, "--json"),
):
    from packages.core.artifacts import write_artifact

    ref = ProjectRef(project, project.name)
    profile = _visual_profile_for_project(ref, profile)
    evidence_manifest = collect_evidence_assets(ref, profile=profile)
    evidence_manifest = materialize_evidence_clips(ref, evidence_manifest)
    scenes = _visual_scenes_for_project(
        ref,
        ratio,
        style,
        profile,
        platform,
        engine,
        evidence_manifest=evidence_manifest,
    )
    scenes, self_check = self_check_visual_scenes(scenes, ratio=ratio, style=style)
    visual_real_count = sum(1 for scene in scenes if scene["generator"] != "fallback_solid")
    review_sheets = [scene.get("director_review_sheet") for scene in scenes]
    asset_summary = asset_diagnosis_summary(scenes)
    profile_data = _profile_preset_for_project(
        ref,
        profile=profile,
        platform=platform,
        ratio=ratio,
        scene_count=len(scenes),
    )
    _apply_visual_profile_to_scenes(scenes, profile_data)
    cost_notices = [
        notice
        for notice in (paid_engine_notice(scene.get("generator", "")) for scene in scenes)
        if notice
    ]
    if engine == "remotion" or any(scene.get("generator") == "remotion" for scene in scenes):
        cost_notices.append(remotion_license_notice())
    evidence_checklist = _evidence_collection_checklist_payload(ref, scenes)
    visual_plan = {
        "id": "visuals",
        "ratio": ratio,
        "engine": engine,
        "template": template,
        "style": style,
        "profile": profile,
        "profile_preset": profile_data,
        "profile_required_evidence": list(profile_data.get("required_evidence") or []),
        "director_knowledge_base_v1": director_knowledge_base_v1(),
        "evidence_assets": evidence_manifest,
        "scenes": scenes,
        "director_review_sheet_v2": {
            "version": "v2",
            "purpose": "画面三审给用户看的完整导演分镜确认单。",
            "markdown_artifact": "artifacts/director_review_sheet.md",
            "scenes": review_sheets,
        },
        "asset_diagnosis_summary": asset_summary,
        "evidence_collection_checklist_v1": evidence_checklist,
        "director_router_summary": {
            "version": "v1",
            "routes": [
                {
                    "scene_id": scene.get("scene_id"),
                    "selected_engine": (scene.get("engine_policy") or {}).get(
                        "selected_engine"
                    ),
                    "route_reason": scene.get("route_reason"),
                }
                for scene in scenes
            ],
        },
        "visual_real_count": visual_real_count,
        "visual_total": len(scenes),
        "cost_notices": cost_notices,
        "self_check": self_check,
    }
    write_artifact(ref, "visuals", visual_plan)
    review_markdown = _write_director_review_markdown(ref, visual_plan)
    checklist_markdown = _write_evidence_collection_checklist(ref, visual_plan)
    _emit(
        {
            "ok": True,
            "status": "awaiting_review",
            "artifact": "artifacts/visual_plan.json",
            "director_review_artifact": "artifacts/director_review_sheet.md",
            "director_review_markdown": review_markdown,
            "evidence_collection_checklist_artifact": (
                "artifacts/evidence_collection_checklist.md"
            ),
            "evidence_collection_checklist_markdown": checklist_markdown,
            "message_zh": "已生成完整导演分镜确认单,请在批准 visuals 前展示给用户审阅。",
        },
        json_output,
    )


@approve_app.command("visuals")
def approve_visuals(
    project: Path,
    approved_by: str = typer.Option(...),
    comment: Optional[str] = typer.Option(None),
    json_output: bool = typer.Option(False, "--json"),
):
    try:
        approval = approve_target(
            ProjectRef(project, project.name),
            "visuals",
            approved_by,
            comment,
        )
    except LingjianError as exc:
        recovery_payload = _visuals_review_recovery_payload(
            ProjectRef(project, project.name),
            exc,
        )
        if recovery_payload:
            _emit(recovery_payload, json_output)
            raise typer.Exit(1)
        _fail(exc, json_output)
    _emit({"ok": True, "approval": approval}, json_output)


@app.command()
def render(
    project: Path,
    platform: str = typer.Option(...),
    language: str = typer.Option(...),
    ratio: str = typer.Option(...),
    release: bool = typer.Option(False, "--release"),
    strict: bool = typer.Option(False, "--strict"),
    real: bool = typer.Option(False, "--real"),
    json_output: bool = typer.Option(False, "--json"),
):
    ref = ProjectRef(project, project.name)
    error = validate_render_gate(ref)
    if error:
        exc = LingjianError(
            error.error_code,
            error.message_zh,
            error.hint,
            error.details,
        )
        recovery_payload = _visuals_review_recovery_payload(ref, exc, platform)
        if recovery_payload:
            _emit(recovery_payload, json_output)
            raise typer.Exit(1)
        recovery_payload = _voice_review_recovery_payload(ref, exc, platform)
        if recovery_payload:
            _emit(recovery_payload, json_output)
            raise typer.Exit(1)
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
            strict=strict,
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
            "metadata": report.metadata,
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
    style: str = typer.Option("clean_product", "--style"),
    profile: str = typer.Option("douyin_product", "--profile"),
    script_provider: str = typer.Option("mock", "--script-provider"),
    voice_provider: str = typer.Option("auto", "--voice-provider"),
    voice: str = typer.Option("", "--voice"),
    voice_audio_file: Optional[Path] = typer.Option(None, "--voice-audio-file"),
    no_voiceover: bool = typer.Option(
        False, "--no-voiceover", help="无旁白模式:文字卡代旁白承担叙事(新客观主义等)"
    ),
    engine: str = typer.Option("ffmpeg_card", "--engine"),
    template: str = typer.Option("product", "--template"),
    release: bool = typer.Option(False, "--release"),
    strict: bool = typer.Option(False, "--strict"),
    yes: bool = typer.Option(False, "--yes"),
    approved_by: str = typer.Option("ci", "--approved-by"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    if style and style not in _STYLE_LOCKS:
        typer.echo(
            f"⚠ 未知风格 '{style}',将回退默认 {_DEFAULT_STYLE};"
            f"可选:{', '.join(sorted(_STYLE_LOCKS))}"
        )
    ref = ProjectRef(project, name or project.name)
    steps: list[str] = []
    effective_strict = strict or release
    try:
        if release:
            doctor_result = run_doctor()
            required_items = list(doctor_result.required)
            if voice_audio_file is not None or _project_has_existing_release_voice_asset(ref):
                required_items = [
                    item
                    for item in required_items
                    if item.id not in {"real_tts_provider", "publish_tts_provider"}
                ]
            if _project_has_release_video_assets(ref) or _project_has_visual_plan_artifact(ref):
                required_items = [
                    item for item in required_items if item.id != "publish_visual_provider"
                ]
            if required_items:
                missing = [item.id for item in required_items]
                raise LingjianError(
                    "DOCTOR_NOT_READY",
                    "发布档需要 doctor ready 后才能运行。",
                    "请先按 required 缺项补齐能力。",
                    {
                        "missing": missing,
                        "actions": _release_missing_actions(required_items),
                    },
                )
        if not (ref.path / "project.yaml").exists():
            init_project(ref.path, ref.name)
            steps.append("init")
        if _ensure_text_input(ref, input_file):
            steps.append("ingest")
        steps.append("extract")
        script_result = _write_script_for_run(
            ref,
            type_,
            platform,
            language,
            ratio,
            duration,
            script_provider,
            style,
            profile,
        )
        if script_result == "awaiting_host_authoring":
            contract_path = ref.path / "artifacts" / "script_contract.json"
            _emit(
                {
                    "ok": True,
                    "status": "awaiting_host_authoring",
                    "current_step": "script",
                    "artifact": "artifacts/script_contract.json",
                    "steps": steps,
                    "message_zh": (
                        "脚本关:请宿主 agent(你自己,LLM)按创作契约直接产出脚本,"
                        "不要 fork 外部 claude/codex CLI。读 "
                        f"{contract_path},创作后写成 {{\"scenes\":[...]}} 存盘,"
                        "再运行 `lj script <项目> --from-file <脚本.json> "
                        "--type ... --platform ... --style ... --profile ...` 回填,"
                        "然后继续 `lj run`。"
                    ),
                },
                json_output,
            )
            return
        if script_result:
            steps.append("script")
        if not _approval_exists(ref, "script"):
            if not yes:
                _pause_for_approval(ref, "script", "artifacts/script.json", json_output)
                return
            approve_target(ref, "script", approved_by)
            steps.append("approve_script")
        voice_plan_exists = (ref.path / "artifacts" / "voice_plan.json").exists()
        if not voice and voice_audio_file is None and not voice_plan_exists:
            provider_ref = _resolve_tts_provider(voice_provider)
            if provider_ref.id == "volcengine_tts":
                payload = _write_voice_options(ref, voice_provider, None, 5)
                _emit(_voice_choice_response(ref.path, payload), json_output)
                return
        voice_caption_repair = None
        if _write_voice_plan(
            ref, voice_provider, voice, voice_audio_file, voiceover=not no_voiceover
        ):
            steps.append("voice")
        else:
            voice_caption_repair = _backfill_voice_plan_caption_cues(ref)
            if voice_caption_repair:
                steps.append("voice_caption_cues")
                if not yes:
                    next_command = _approve_next_command(ref, "voice")
                    payload = {
                        "ok": True,
                        "status": "awaiting_approval",
                        "current_step": "voice",
                        "artifact": "artifacts/voice_plan.json",
                        "steps": steps,
                        "voice_caption_repair": voice_caption_repair,
                        "message_zh": (
                            "已为旧 voice_plan 回填可审计 timed captions,"
                            "请先重新审阅配音与字幕节奏后批准 voice。"
                        ),
                        "next_command": next_command,
                    }
                    evidence_next_step = _evidence_collection_next_step(ref)
                    if evidence_next_step:
                        alternatives = (
                            evidence_next_step.get("alternative_next_commands") or []
                        )
                        payload.update(
                            {
                                "post_voice_current_step": "visuals",
                                "post_voice_next_action_zh": evidence_next_step.get(
                                    "next_action_zh"
                                ),
                                "post_voice_next_command_kind": "collect_evidence",
                                "post_voice_next_command": evidence_next_step[
                                    "next_command"
                                ],
                                "post_voice_next_command_label_zh": evidence_next_step.get(
                                    "next_command_label_zh"
                                ),
                                "post_voice_next_command_note_zh": evidence_next_step.get(
                                    "next_command_note_zh"
                                ),
                                "post_voice_alternative_next_commands": alternatives,
                                "post_voice_remaining_evidence_blockers": (
                                    evidence_next_step.get(
                                        "remaining_evidence_blockers"
                                    )
                                    or []
                                ),
                                "post_voice_blocked_until_evidence_zh": (
                                    "批准 voice 后仍有非发布级真实动态素材缺口;"
                                    "请继续按 post_voice_next_command 采集并绑定素材,"
                                    "素材补齐并重新生成/审阅画面后再批准 visuals。"
                                ),
                            }
                        )
                        post_voice_next_command = evidence_next_step["next_command"]
                        if _command_requires_screen_recording(post_voice_next_command):
                            fallback = _find_manual_evidence_fallback(alternatives)
                            payload["post_voice_screen_recording_consent_required"] = (
                                True
                            )
                            payload["post_voice_privacy_notice_zh"] = (
                                _SCREEN_RECORDING_PRIVACY_NOTICE_ZH
                            )
                            if fallback:
                                payload["post_voice_manual_fallback_command"] = (
                                    fallback.get("command")
                                )
                                payload["post_voice_manual_fallback_note_zh"] = (
                                    fallback.get("note_zh")
                                )
                    payload.update(
                        _audio_asset_recovery_fields(
                            ref,
                            platform,
                            prefix="post_voice",
                        )
                    )
                    _emit(payload, json_output)
                    return
                approve_target(ref, "voice", approved_by)
                steps.append("approve_voice")
        if not _approval_exists(ref, "voice"):
            if not yes:
                _pause_for_approval(ref, "voice", "artifacts/voice_plan.json", json_output)
                return
            approve_target(ref, "voice", approved_by)
            steps.append("approve_voice")
        if _write_visuals_for_run(ref, engine, template, ratio, style, profile, platform):
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
            strict=effective_strict,
        )
        steps.append("render")
        qa_report = run_qa(ref, release=release, platform=platform, strict=effective_strict)
        steps.append("qa")
        if qa_report.hard_failures:
            repair = _attempt_post_render_director_repair(
                ref,
                qa_report,
                ratio=ratio,
                style=style,
            )
            if repair is not None:
                _emit(
                    {
                        "ok": True,
                        "mode": render_result.mode,
                        "video_path": str(render_result.video_path),
                        "steps": steps + ["self_check_repair_visuals"],
                        **repair,
                    },
                    json_output,
                )
                return
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
                        "metadata": qa_report.metadata,
                    },
                },
                json_output,
            )
            raise typer.Exit(1)
        package = export_project(
            ref,
            platform,
            language,
            ratio,
            release=release,
            strict=effective_strict,
        )
        steps.append("export")
    except LingjianError as exc:
        recovery_payload = _visuals_review_recovery_payload(ref, exc, platform)
        if recovery_payload:
            _emit(recovery_payload, json_output)
            raise typer.Exit(1)
        recovery_payload = _voice_review_recovery_payload(ref, exc, platform)
        if recovery_payload:
            _emit(recovery_payload, json_output)
            raise typer.Exit(1)
        _fail(exc, json_output)
    _emit(
        {
            "ok": True,
            "status": "exported",
            "mode": "release" if release else "preview",
            "strict": effective_strict,
            "steps": steps,
            "video_path": str(render_result.video_path),
            "qa": {
                "release_ready": qa_report.release_ready,
                "hard_failures": [asdict(issue) for issue in qa_report.hard_failures],
                "warnings": [asdict(issue) for issue in qa_report.warnings],
                "info": [asdict(issue) for issue in qa_report.info],
                "metadata": qa_report.metadata,
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
