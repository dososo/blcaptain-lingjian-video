from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from packages.core.artifacts import artifact_path, read_json, safe_project_path
from packages.core.errors import ErrorResult
from packages.core.hash import canonical_json_hash
from packages.core.project import ProjectRef

ApprovalTarget = Literal["script", "voice", "visuals"]
TARGETS: tuple[ApprovalTarget, ...] = ("script", "voice", "visuals")


def _approvals_path(project: ProjectRef) -> Path:
    return project.path / "artifacts" / "approvals.json"


def _read_approvals(project: ProjectRef) -> dict[str, Any]:
    path = _approvals_path(project)
    if not path.exists():
        return {}
    return read_json(path)


def _approval_secret(project: ProjectRef) -> bytes:
    path = project.path / ".lingjian" / "approval_secret"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(os.urandom(32).hex(), encoding="utf-8")
    path.chmod(0o600)
    return path.read_text(encoding="utf-8").encode("utf-8")


def _signature(project: ProjectRef, approval: dict[str, Any]) -> str:
    payload = "|".join(
        [
            approval["target"],
            approval["artifact_path"],
            approval["artifact_sha256"],
            approval["approved_by"],
            approval["approved_at"],
        ]
    )
    return hmac.new(_approval_secret(project), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_for_hash(project: ProjectRef, target: ApprovalTarget) -> Any:
    artifact = read_json(artifact_path(project, target))
    if target != "voice":
        return artifact
    enriched = json.loads(json.dumps(artifact))
    for segment in enriched.get("segments", []):
        audio_path = segment.get("audio_path")
        if not audio_path:
            continue
        resolved = safe_project_path(project, project.path / audio_path)
        if resolved.exists():
            segment["audio_sha256"] = _file_sha256(resolved)
    return enriched


def _write_approvals(project: ProjectRef, approvals: dict[str, Any]) -> None:
    path = _approvals_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(approvals, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def approve_target(
    project: ProjectRef,
    target: ApprovalTarget,
    approved_by: str,
    comment: str | None = None,
) -> dict[str, Any]:
    target_path = artifact_path(project, target)
    artifact = _artifact_for_hash(project, target)
    approval = {
        "target": target,
        "artifact_path": str(target_path.relative_to(project.path)),
        "artifact_sha256": canonical_json_hash(artifact),
        "approved_by": approved_by,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "comment": comment,
    }
    approval["signature"] = _signature(project, approval)
    approvals = _read_approvals(project)
    approvals[target] = approval
    _write_approvals(project, approvals)
    return approval


def validate_render_gate(project: ProjectRef) -> ErrorResult | None:
    approvals = _read_approvals(project)
    missing = [target for target in TARGETS if target not in approvals]
    if missing:
        return ErrorResult(
            "APPROVAL_REQUIRED",
            "渲染前必须完成文案、语音和画面三项审批。",
            "请完成缺失审批后重试。",
            {"missing": missing},
        )

    stale: list[str] = []
    for target in TARGETS:
        approval = approvals[target]
        required = {
            "target",
            "artifact_path",
            "artifact_sha256",
            "approved_by",
            "approved_at",
            "signature",
        }
        if not required.issubset(approval):
            stale.append(target)
            continue
        if not hmac.compare_digest(approval["signature"], _signature(project, approval)):
            stale.append(target)
            continue
        artifact = _artifact_for_hash(project, target)
        if canonical_json_hash(artifact) != approval["artifact_sha256"]:
            stale.append(target)
    if stale:
        return ErrorResult(
            "APPROVAL_STALE",
            "审批对应的内容已经变更。",
            "请重新审核失效步骤后再渲染。",
            {"stale": stale},
        )
    return None
