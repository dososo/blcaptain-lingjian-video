from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Literal

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "verification" / "evidence"


@dataclass(slots=True)
class VerificationResult:
    id: str
    title: str
    command: str
    expect: str
    exit_code: int | None
    error_code: str | None
    status: Literal["PASS", "FAIL", "BLOCKED_ENV"]
    evidence_file: str | None
    notes: str


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]

PROVIDER_ENV_KEYS = [
    "LINGJIAN_LLM_CLI",
    "LINGJIAN_TTS_CLI",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_TTS_BASE_URL",
    "OPENAI_TTS_API_KEY",
    "OPENAI_TTS_MODEL",
]


@dataclass(slots=True)
class DoctorProbe:
    command: list[str]
    completed: subprocess.CompletedProcess[str]
    payload: dict
    ready: bool
    missing: list[str]


def _command_text(command: list[str]) -> str:
    return " ".join(command)


def _last_json(stdout: str) -> dict:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {}


def _write_log(
    log_path: Path, command: list[str], completed: subprocess.CompletedProcess[str]
) -> None:
    log_path.write_text(
        "\n".join(
            [
                f"command: {_command_text(command)}",
                f"exit_code: {completed.returncode}",
                "",
                "stdout:",
                completed.stdout,
                "",
                "stderr:",
                completed.stderr,
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_multi_log(
    log_path: Path,
    records: list[tuple[list[str], subprocess.CompletedProcess[str]]],
) -> None:
    chunks: list[str] = []
    for command, completed in records:
        chunks.extend(
            [
                f"command: {_command_text(command)}",
                f"exit_code: {completed.returncode}",
                "",
                "stdout:",
                completed.stdout,
                "",
                "stderr:",
                completed.stderr,
                "",
                "---",
                "",
            ]
        )
    log_path.write_text("\n".join(chunks), encoding="utf-8")


def _default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _doctor_missing_command() -> list[str]:
    uv_bin = shutil.which("uv") or "uv"
    command = ["/usr/bin/env"]
    for key in PROVIDER_ENV_KEYS:
        command.extend(["-u", key])
    command.extend(
        [
            "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            uv_bin,
            "run",
            "lj",
            "doctor",
            "--json",
        ]
    )
    return command


def run_command(
    item_id: str,
    title: str,
    command: list[str],
    expect: str,
    expected_exit: int | None = 0,
    expected_error_code: str | None = None,
    runner: CommandRunner = _default_runner,
) -> VerificationResult:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = EVIDENCE_DIR / f"{item_id}.log"
    completed = runner(command)
    _write_log(log_path, command, completed)
    payload = _last_json(completed.stdout)
    error_code = payload.get("error_code") if isinstance(payload, dict) else None
    exit_ok = (
        completed.returncode != 0
        if expected_exit is None
        else completed.returncode == expected_exit
    )
    error_ok = expected_error_code is None or error_code == expected_error_code
    status: Literal["PASS", "FAIL"] = "PASS" if exit_ok and error_ok else "FAIL"
    return VerificationResult(
        id=item_id,
        title=title,
        command=_command_text(command),
        expect=expect,
        exit_code=completed.returncode,
        error_code=error_code,
        status=status,
        evidence_file=str(log_path.relative_to(ROOT)),
        notes="",
    )


def _doctor_probe(runner: CommandRunner = _default_runner) -> DoctorProbe:
    command = ["uv", "run", "lj", "doctor", "--json"]
    completed = runner(command)
    payload = _last_json(completed.stdout)
    missing = [
        str(item.get("id"))
        for item in payload.get("required", [])
        if isinstance(item, dict) and not item.get("ok")
    ]
    return DoctorProbe(
        command=command,
        completed=completed,
        payload=payload,
        ready=completed.returncode == 0 and bool(payload.get("ready")),
        missing=missing,
    )


def _release_provider_id(payload: dict, kind: str, fallback: str) -> str:
    provider_group = payload.get("providers", {}).get(kind, {})
    for method in provider_group.get("methods", []):
        if method.get("safe_for_release") and not method.get("is_mock"):
            return str(method.get("id") or fallback)
    return fallback


def real_release_verification(
    stamp: str,
    runner: CommandRunner = _default_runner,
    doctor_probe: DoctorProbe | None = None,
) -> VerificationResult:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = EVIDENCE_DIR / "V-REAL-01.log"
    probe = doctor_probe or _doctor_probe(runner)
    records: list[tuple[list[str], subprocess.CompletedProcess[str]]] = [
        (probe.command, probe.completed)
    ]
    command_chain = [_command_text(probe.command)]
    if not probe.ready:
        _write_multi_log(log_path, records)
        missing = ", ".join(probe.missing) if probe.missing else "doctor 未 ready"
        return VerificationResult(
            id="V-REAL-01",
            title="真实 provider release 包补验",
            command=_command_text(probe.command),
            expect="doctor ready 后执行真实 release render/export/ffprobe",
            exit_code=probe.completed.returncode,
            error_code=None,
            status="BLOCKED_ENV",
            evidence_file=str(log_path.relative_to(ROOT)),
            notes=f"当前环境未满足真实 release 条件: {missing}。",
        )

    project = f"projects/verify_real_{stamp}"
    llm_provider = _release_provider_id(probe.payload, "llm", "openai_compatible")
    tts_provider = _release_provider_id(probe.payload, "tts", "openai_compatible_tts")
    commands = [
        ["which", "ffmpeg"],
        ["ffmpeg", "-version"],
        ["ffprobe", "-version"],
        ["sh", "-c", "ffmpeg -hide_banner -filters | grep drawtext"],
        ["sh", "-c", "sw_vers 2>/dev/null || uname -a"],
        ["uv", "run", "lj", "init", project, "--name", "真实发布补验", "--json"],
        [
            "uv",
            "run",
            "lj",
            "ingest",
            "text",
            project,
            "--file",
            "examples/product_intro_zh.txt",
            "--json",
        ],
        ["uv", "run", "lj", "extract", project, "--json"],
        [
            "uv",
            "run",
            "lj",
            "script",
            project,
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--duration",
            "45",
            "--provider",
            llm_provider,
            "--json",
        ],
        ["uv", "run", "lj", "approve", "script", project, "--approved-by", "ci", "--json"],
        [
            "uv",
            "run",
            "lj",
            "voice",
            project,
            "--provider",
            tts_provider,
            "--voice",
            "release-voice",
            "--json",
        ],
        ["uv", "run", "lj", "approve", "voice", project, "--approved-by", "ci", "--json"],
        [
            "uv",
            "run",
            "lj",
            "visuals",
            project,
            "--engine",
            "ffmpeg_card",
            "--template",
            "product",
            "--json",
        ],
        ["uv", "run", "lj", "approve", "visuals", project, "--approved-by", "ci", "--json"],
        [
            "uv",
            "run",
            "lj",
            "render",
            project,
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--release",
            "--json",
        ],
        ["uv", "run", "lj", "qa", project, "--release", "--platform", "douyin", "--json"],
        [
            "uv",
            "run",
            "lj",
            "export",
            project,
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--release",
            "--json",
        ],
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "json",
            f"exports/verify_real_{stamp}/douyin/zh-CN/9x16/video.mp4",
        ],
    ]
    for command in commands:
        completed = runner(command)
        records.append((command, completed))
        command_chain.append(_command_text(command))
        if completed.returncode != 0:
            _write_multi_log(log_path, records)
            payload = _last_json(completed.stdout)
            return VerificationResult(
                id="V-REAL-01",
                title="真实 provider release 包补验",
                command=" && ".join(command_chain),
                expect="doctor ready 后真实 release render/export/ffprobe 全链路通过",
                exit_code=completed.returncode,
                error_code=payload.get("error_code") if isinstance(payload, dict) else None,
                status="FAIL",
                evidence_file=str(log_path.relative_to(ROOT)),
                notes=f"doctor ready 后真实 release 补验失败: {_command_text(command)}",
            )
    _write_multi_log(log_path, records)
    return VerificationResult(
        id="V-REAL-01",
        title="真实 provider release 包补验",
        command=" && ".join(command_chain),
        expect="doctor ready 后真实 release render/export/ffprobe 全链路通过",
        exit_code=0,
        error_code=None,
        status="PASS",
        evidence_file=str(log_path.relative_to(ROOT)),
        notes="doctor ready,真实 release 补验已执行并通过。",
    )


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    project = f"projects/verify_m1_{stamp}"
    cn_project = f"projects/中文路径验证_{stamp}"
    url_project = f"projects/url_verify_{stamp}"
    export_dir = f"exports/verify_m1_{stamp}"
    results: list[VerificationResult] = []

    def add(*args, **kwargs) -> None:
        results.append(run_command(*args, **kwargs))

    add("V-BASE-01", "uv sync", ["uv", "sync"], "依赖同步成功")
    add("V-BASE-02", "pytest 离线全集", ["uv", "run", "pytest"], "测试全集通过")
    add("V-BASE-03", "ruff", ["uv", "run", "ruff", "check", "."], "ruff 通过")
    add(
        "V-BASE-04",
        "doctor required 缺失退出非零",
        _doctor_missing_command(),
        "无真实 provider 时返回非零并给 required",
        expected_exit=None,
    )
    add("V-WEB-01", "Web TypeScript", ["pnpm", "--dir", "apps/web", "lint"], "tsc 通过")
    add("V-WEB-02", "Web build", ["pnpm", "--dir", "apps/web", "build"], "Next build 通过")
    add("V-WEB-03", "Web smoke 截图", ["test", "-f", "output/playwright/web-smoke.png"], "截图存在")

    add(
        "V-GATE-00",
        "初始化项目",
        ["uv", "run", "lj", "init", project, "--name", "门禁测试", "--json"],
        "init 成功",
    )
    add(
        "V-GATE-01",
        "文本输入",
        [
            "uv",
            "run",
            "lj",
            "ingest",
            "text",
            project,
            "--file",
            "examples/product_intro_zh.txt",
            "--json",
        ],
        "input_ready",
    )
    add(
        "V-GATE-02",
        "extract 路由",
        ["uv", "run", "lj", "extract", project, "--json"],
        "extract 成功",
    )
    add(
        "V-GATE-03",
        "生成文案",
        [
            "uv",
            "run",
            "lj",
            "script",
            project,
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--duration",
            "45",
            "--provider",
            "mock",
            "--json",
        ],
        "script 进入待审",
    )
    add(
        "V-GATE-04",
        "未审批 render 阻断",
        [
            "uv",
            "run",
            "lj",
            "render",
            project,
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
        "APPROVAL_REQUIRED",
        expected_exit=1,
        expected_error_code="APPROVAL_REQUIRED",
    )
    add(
        "V-GATE-05",
        "审批文案",
        ["uv", "run", "lj", "approve", "script", project, "--approved-by", "tester", "--json"],
        "文案审批成功",
    )
    add(
        "V-GATE-05A",
        "生成语音以完成三审基线",
        [
            "uv",
            "run",
            "lj",
            "voice",
            project,
            "--provider",
            "mock",
            "--voice",
            "test-voice",
            "--json",
        ],
        "voice 待审",
    )
    add(
        "V-GATE-05B",
        "审批语音以完成三审基线",
        ["uv", "run", "lj", "approve", "voice", project, "--approved-by", "tester", "--json"],
        "语音审批成功",
    )
    add(
        "V-GATE-05C",
        "生成画面以完成三审基线",
        [
            "uv",
            "run",
            "lj",
            "visuals",
            project,
            "--engine",
            "ffmpeg_card",
            "--template",
            "product",
            "--json",
        ],
        "visuals 待审",
    )
    add(
        "V-GATE-05D",
        "审批画面以完成三审基线",
        ["uv", "run", "lj", "approve", "visuals", project, "--approved-by", "tester", "--json"],
        "画面审批成功",
    )
    add(
        "V-GATE-06",
        "改稿后下游 stale",
        [
            "uv",
            "run",
            "lj",
            "script",
            project,
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--duration",
            "45",
            "--provider",
            "mock",
            "--json",
        ],
        "第二版脚本生成",
    )
    add(
        "V-GATE-07",
        "stale render 阻断",
        [
            "uv",
            "run",
            "lj",
            "render",
            project,
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
        "APPROVAL_STALE",
        expected_exit=1,
        expected_error_code="APPROVAL_STALE",
    )
    add(
        "V-GATE-08",
        "重审文案",
        ["uv", "run", "lj", "approve", "script", project, "--approved-by", "tester", "--json"],
        "重审成功",
    )
    add(
        "V-GATE-09",
        "生成语音",
        [
            "uv",
            "run",
            "lj",
            "voice",
            project,
            "--provider",
            "mock",
            "--voice",
            "test-voice",
            "--json",
        ],
        "voice 待审",
    )
    add(
        "V-GATE-10",
        "审批语音",
        ["uv", "run", "lj", "approve", "voice", project, "--approved-by", "tester", "--json"],
        "语音审批成功",
    )
    add(
        "V-GATE-11",
        "生成画面",
        [
            "uv",
            "run",
            "lj",
            "visuals",
            project,
            "--engine",
            "ffmpeg_card",
            "--template",
            "product",
            "--json",
        ],
        "visuals 待审",
    )
    add(
        "V-GATE-12",
        "审批画面",
        ["uv", "run", "lj", "approve", "visuals", project, "--approved-by", "tester", "--json"],
        "画面审批成功",
    )
    add(
        "V-GATE-13",
        "三审后 preview render",
        [
            "uv",
            "run",
            "lj",
            "render",
            project,
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
        "render 成功",
    )
    add("V-QA-01", "QA", ["uv", "run", "lj", "qa", project, "--json"], "QA 执行成功")
    add(
        "V-REL-01",
        "mock release 阻断",
        [
            "uv",
            "run",
            "lj",
            "export",
            project,
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--release",
            "--json",
        ],
        "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE",
        expected_exit=1,
        expected_error_code="MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE",
    )
    add(
        "V-EXP-01",
        "canonical export",
        [
            "uv",
            "run",
            "lj",
            "export",
            project,
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
        "导出包成功",
    )
    for index, rel_path in enumerate(
        [
            "douyin/zh-CN/9x16/video.mp4",
            "douyin/zh-CN/9x16/captions/subtitles.srt",
            "douyin/zh-CN/9x16/captions/subtitles.vtt",
            "douyin/zh-CN/9x16/captions/subtitles.ass",
            "douyin/zh-CN/9x16/provider_manifest.json",
            "douyin/zh-CN/9x16/license_manifest.md",
            "douyin/zh-CN/9x16/export_manifest.json",
        ],
        start=1,
    ):
        add(
            f"V-EXP-STRUCT-{index:02d}",
            f"导出结构 {rel_path}",
            ["test", "-f", f"{export_dir}/{rel_path}"],
            "文件存在",
        )
    add(
        "V-EXP-02",
        "YouTube 附加文件",
        [
            "uv",
            "run",
            "lj",
            "export",
            project,
            "--platform",
            "youtube",
            "--language",
            "en-US",
            "--ratio",
            "16:9",
            "--json",
        ],
        "YouTube 导出成功",
    )
    for index, rel_path in enumerate(
        [
            "youtube/en-US/16x9/thumbnail.png",
            "youtube/en-US/16x9/description.md",
            "youtube/en-US/16x9/chapters.md",
        ],
        start=1,
    ):
        add(
            f"V-EXP-YT-{index:02d}",
            f"YouTube 文件 {rel_path}",
            ["test", "-f", f"{export_dir}/{rel_path}"],
            "文件存在",
        )
    add(
        "V-EXP-03",
        "多平台导出",
        [
            "uv",
            "run",
            "lj",
            "export",
            project,
            "--all-platforms",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--json",
        ],
        "多平台导出成功",
    )
    add(
        "V-REINDEX-01", "reindex", ["uv", "run", "lj", "reindex", project, "--json"], "索引重建成功"
    )
    add("V-REINDEX-02", "status", ["uv", "run", "lj", "status", project, "--json"], "状态可读")
    add(
        "V-CN-01",
        "中文路径 init",
        ["uv", "run", "lj", "init", cn_project, "--name", "中文路径", "--json"],
        "中文路径 init 成功",
    )
    add(
        "V-CN-02",
        "中文路径 script",
        [
            "uv",
            "run",
            "lj",
            "script",
            cn_project,
            "--type",
            "product",
            "--platform",
            "douyin",
            "--language",
            "zh-CN",
            "--ratio",
            "9:16",
            "--duration",
            "45",
            "--provider",
            "mock",
            "--json",
        ],
        "中文路径不乱码",
    )
    add(
        "V-URL-01",
        "URL 输入合规",
        ["uv", "run", "lj", "init", url_project, "--name", "URL合规", "--json"],
        "URL 项目 init",
    )
    add(
        "V-URL-02",
        "URL 不默认下载视频",
        [
            "uv",
            "run",
            "lj",
            "ingest",
            "url",
            url_project,
            "--url",
            "https://example.com/article",
            "--json",
        ],
        "URL 输入记录为不可信输入",
    )
    add(
        "V-FORBID-01",
        "13 项伪成功扫描",
        ["uv", "run", "python", "scripts/ci/check_false_success.py"],
        "全部 PASS",
    )
    add(
        "V-FORBID-02",
        "无门禁跳过扫描",
        ["uv", "run", "python", "scripts/ci/check_no_force.py"],
        "未发现",
    )
    add(
        "V-FORBID-03",
        "禁用 SDK import 扫描",
        ["uv", "run", "python", "scripts/ci/check_forbidden_imports.py"],
        "未发现",
    )
    add(
        "V-FORBID-04",
        "渲染引擎范围扫描",
        ["uv", "run", "python", "scripts/ci/check_render_engine_m1.py"],
        "未发现",
    )
    add(
        "V-FORBID-05",
        "ffmpeg_card 范围扫描",
        ["uv", "run", "python", "scripts/ci/check_ffmpeg_card_scope.py"],
        "未发现",
    )
    results.insert(0, real_release_verification(stamp))

    out_path = ROOT / "verification" / "results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    failed = [result for result in results if result.status == "FAIL"]
    print(json.dumps({"results": str(out_path), "failures": len(failed)}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
