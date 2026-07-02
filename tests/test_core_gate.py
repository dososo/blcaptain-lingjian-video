import hashlib
import json
from pathlib import Path

from packages.core.approvals import approve_target, validate_render_gate
from packages.core.artifacts import read_json, write_artifact
from packages.core.errors import LingjianError
from packages.core.project import init_project, reindex_project, status_project


def test_render_requires_all_three_approvals(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    write_artifact(project, "script", {"id": "script-1", "scenes": []})

    error = validate_render_gate(project)

    assert error is not None
    assert error.error_code == "APPROVAL_REQUIRED"
    assert set(error.details["missing"]) == {"script", "voice", "visuals"}


def test_approval_becomes_stale_when_artifact_changes(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    write_artifact(project, "script", {"id": "script-1", "scenes": [{"text": "旧"}]})
    write_artifact(project, "voice", {"id": "voice-1", "segments": []})
    write_artifact(project, "visuals", {"id": "visuals-1", "scenes": []})
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")

    write_artifact(project, "script", {"id": "script-1", "scenes": [{"text": "新"}]})
    error = validate_render_gate(project)

    assert error is not None
    assert error.error_code == "APPROVAL_STALE"
    assert error.details["stale"] == ["script"]


def test_init_project_creates_random_private_approval_secret(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    secret_path = project.path / ".lingjian" / "approval_secret"
    legacy_path_hash = hashlib.sha256(str(project.path).encode("utf-8")).hexdigest()

    assert secret_path.exists()
    assert secret_path.read_text(encoding="utf-8") != legacy_path_hash
    assert secret_path.stat().st_mode & 0o777 == 0o600


def test_existing_approval_secret_is_reused(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    secret_path = project.path / ".lingjian" / "approval_secret"
    secret_path.write_text("legacy-secret", encoding="utf-8")
    write_artifact(project, "script", {"id": "script-1", "scenes": []})

    approve_target(project, "script", "tester")

    assert secret_path.read_text(encoding="utf-8") == "legacy-secret"


def test_tampered_approval_signature_marks_stale(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    write_artifact(project, "script", {"id": "script-1", "scenes": []})
    write_artifact(project, "voice", {"id": "voice-1", "segments": []})
    write_artifact(project, "visuals", {"id": "visuals-1", "scenes": []})
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")
    approvals_path = project.path / "artifacts" / "approvals.json"
    approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    approvals["script"]["approved_by"] = "attacker"
    approvals_path.write_text(json.dumps(approvals, ensure_ascii=False, indent=2), encoding="utf-8")

    error = validate_render_gate(project)

    assert error is not None
    assert error.error_code == "APPROVAL_STALE"
    assert error.details["stale"] == ["script"]


def test_artifact_overwrite_writes_history_snapshot(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    write_artifact(project, "script", {"version": 1})
    write_artifact(project, "script", {"version": 2})

    history_files = list((project.path / "history" / "script").glob("*.json"))

    assert len(history_files) == 1
    assert read_json(history_files[0])["version"] == 1


def test_reindex_restores_status_from_files_after_sqlite_delete(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    write_artifact(project, "script", {"id": "script-1"})
    index_path = project.path / ".lingjian" / "index.sqlite"
    index_path.unlink()

    reindex_project(project.path)
    status = status_project(project.path)

    assert index_path.exists()
    assert status["state"] == "script_review"
    assert status["artifacts"]["script"] is True


def test_rejects_paths_outside_project(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    outside = tmp_path / "outside.json"

    try:
        write_artifact(project, "../outside", {"bad": True}, explicit_path=outside)
    except LingjianError as exc:
        assert exc.error_code == "PATH_OUTSIDE_PROJECT"
    else:
        raise AssertionError("expected PATH_OUTSIDE_PROJECT")


def test_voice_approval_becomes_stale_when_audio_file_changes(tmp_path: Path):
    project = init_project(tmp_path / "p1", "项目")
    audio = project.path / "artifacts" / "voice_segments" / "s1.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"old audio")
    write_artifact(project, "script", {"id": "script-1", "scenes": []})
    write_artifact(
        project,
        "voice",
        {
            "id": "voice-1",
            "segments": [
                {
                    "scene_id": "s1",
                    "audio_path": "artifacts/voice_segments/s1.wav",
                    "duration_sec": 1.0,
                }
            ],
        },
    )
    write_artifact(project, "visuals", {"id": "visuals-1", "scenes": []})
    approve_target(project, "script", "tester")
    approve_target(project, "voice", "tester")
    approve_target(project, "visuals", "tester")

    audio.write_bytes(b"new audio")
    error = validate_render_gate(project)

    assert error is not None
    assert error.error_code == "APPROVAL_STALE"
    assert error.details["stale"] == ["voice"]
