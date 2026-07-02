import subprocess
from pathlib import Path

import scripts.ci.run_verification as verification


def _completed(command: list[str], returncode: int, stdout: str = "{}\n"):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


def _patch_evidence_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verification, "ROOT", tmp_path)
    monkeypatch.setattr(verification, "EVIDENCE_DIR", tmp_path / "verification" / "evidence")


def test_doctor_missing_command_sanitizes_inherited_environment(monkeypatch):
    monkeypatch.setattr(
        verification.shutil,
        "which",
        lambda name: "/tmp/uv" if name == "uv" else None,
    )

    command = verification._doctor_missing_command()

    assert "/tmp/uv" in command
    assert "PATH=/usr/bin:/bin:/usr/sbin:/sbin" in command
    assert command.count("-u") == len(verification.PROVIDER_ENV_KEYS)
    assert "OPENAI_API_KEY" in command
    assert "LINGJIAN_LLM_CLI" in command


def test_real_release_verification_blocks_when_doctor_not_ready(monkeypatch, tmp_path: Path):
    _patch_evidence_paths(monkeypatch, tmp_path)
    probe = verification.DoctorProbe(
        command=["uv", "run", "lj", "doctor", "--json"],
        completed=_completed(
            ["uv", "run", "lj", "doctor", "--json"],
            1,
            '{"ready": false, "required": [{"id": "ffmpeg", "ok": false}]}\n',
        ),
        payload={"ready": False, "required": [{"id": "ffmpeg", "ok": False}]},
        ready=False,
        missing=["ffmpeg"],
    )

    result = verification.real_release_verification(
        "20260701T000000Z",
        runner=lambda command: _completed(command, 0),
        doctor_probe=probe,
    )

    assert result.status == "BLOCKED_ENV"
    assert result.command == "uv run lj doctor --json"
    assert result.evidence_file == "verification/evidence/V-REAL-01.log"


def test_real_release_verification_runs_release_chain_when_ready(
    monkeypatch,
    tmp_path: Path,
):
    _patch_evidence_paths(monkeypatch, tmp_path)
    commands: list[list[str]] = []
    probe = verification.DoctorProbe(
        command=["uv", "run", "lj", "doctor", "--json"],
        completed=_completed(["uv", "run", "lj", "doctor", "--json"], 0, '{"ready": true}\n'),
        payload={
            "ready": True,
            "providers": {
                "llm": {
                    "methods": [
                        {"id": "llm_cli", "safe_for_release": True, "is_mock": False}
                    ]
                },
                "tts": {
                    "methods": [
                        {"id": "tts_cli", "safe_for_release": True, "is_mock": False}
                    ]
                },
            },
        },
        ready=True,
        missing=[],
    )

    def fake_runner(command: list[str]):
        commands.append(command)
        if command[0] == "ffprobe":
            return _completed(command, 0, '{"streams": [{"codec_type": "video"}]}\n')
        return _completed(command, 0, '{"ok": true}\n')

    result = verification.real_release_verification(
        "20260701T000000Z",
        runner=fake_runner,
        doctor_probe=probe,
    )
    flat_commands = [" ".join(command) for command in commands]

    assert result.status == "PASS"
    assert any("script projects/verify_real_20260701T000000Z" in item for item in flat_commands)
    assert any("--provider llm_cli" in item for item in flat_commands)
    assert any("--provider tts_cli" in item for item in flat_commands)
    assert "which ffmpeg" in flat_commands
    assert "ffmpeg -version" in flat_commands
    assert "ffprobe -version" in flat_commands
    assert any("grep drawtext" in item for item in flat_commands)
    assert any("sw_vers" in item and "uname -a" in item for item in flat_commands)
    assert any(
        "render projects/verify_real_20260701T000000Z" in item and "--release" in item
        for item in flat_commands
    )
    assert any(
        "qa projects/verify_real_20260701T000000Z --release" in item
        for item in flat_commands
    )
    assert any(
        "export projects/verify_real_20260701T000000Z" in item and "--release" in item
        for item in flat_commands
    )
    assert any(item.startswith("ffprobe ") for item in flat_commands)
