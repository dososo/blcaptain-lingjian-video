from __future__ import annotations

import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci._scan import iter_text_files, repo_root
from scripts.ci.check_ffmpeg_card_scope import check_ffmpeg_card_scope
from scripts.ci.check_forbidden_imports import check_forbidden_imports
from scripts.ci.check_no_force import check_no_force
from scripts.ci.check_render_engine_m1 import check_render_engine_m1


@dataclass(slots=True)
class ScanResult:
    id: str
    title: str
    ok: bool
    findings: list[str]


def _text(rel_path: str) -> str:
    return (repo_root() / rel_path).read_text(encoding="utf-8", errors="ignore")


def _tree(rel_path: str) -> ast.Module:
    return ast.parse(_text(rel_path), filename=rel_path)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _constant_strings(node: ast.AST) -> set[str]:
    return {
        item.value
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }


def _raises_lingjian_error(rel_path: str, error_code: str) -> list[str]:
    tree = _tree(rel_path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if _call_name(node.exc.func) != "LingjianError":
            continue
        first_arg = node.exc.args[0] if node.exc.args else None
        if isinstance(first_arg, ast.Constant) and first_arg.value == error_code:
            return []
    return [f"{rel_path}:missing raise LingjianError({error_code})"]


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _function_calls(rel_path: str, function_name: str, called_name: str) -> list[str]:
    tree = _tree(rel_path)
    function = _function_node(tree, function_name)
    if function is None:
        return [f"{rel_path}:missing function {function_name}"]
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and _call_name(node.func) == called_name:
            return []
    return [f"{rel_path}:{function_name} missing call {called_name}"]


def _sqlite_index_findings() -> list[str]:
    tree = _tree("packages/core/project.py")
    write_index = _function_node(tree, "_write_index")
    if write_index is None:
        return ["packages/core/project.py:missing function _write_index"]
    findings = _function_calls("packages/core/project.py", "reindex_project", "_write_index")
    if "index.sqlite" not in _constant_strings(write_index):
        findings.append("packages/core/project.py:_write_index missing index.sqlite")
    return findings


def _test_coverage_findings() -> list[str]:
    tree = _tree("tests/test_core_gate.py")
    test_functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    has_stale_test = any("APPROVAL_STALE" in _constant_strings(node) for node in test_functions)
    has_reindex_test = any(
        any(
            isinstance(item, ast.Call) and _call_name(item.func) == "reindex_project"
            for item in ast.walk(node)
        )
        for node in test_functions
    )
    findings: list[str] = []
    if not has_stale_test:
        findings.append("tests/test_core_gate.py:missing APPROVAL_STALE behavior test")
    if not has_reindex_test:
        findings.append("tests/test_core_gate.py:missing reindex_project behavior test")
    return findings


def _doctor_release_provider_findings() -> list[str]:
    tree = _tree("packages/core/doctor.py")
    findings: list[str] = []
    for provider_id in ["real_llm_provider", "real_tts_provider"]:
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node.func) != "DoctorItem":
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "id"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value == provider_id
                ):
                    found = True
        if not found:
            findings.append(f"packages/core/doctor.py:missing DoctorItem id={provider_id}")
    method_status = _function_node(tree, "_method_status")
    if method_status is None:
        findings.append("packages/core/doctor.py:missing function _method_status")
    else:
        assigns_safe_for_release = any(
            isinstance(item, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "safe_for_release"
                for target in item.targets
            )
            for item in ast.walk(method_status)
        )
        returns_safe_for_release = any(
            isinstance(item, ast.keyword)
            and item.arg == "safe_for_release"
            and isinstance(item.value, ast.Name)
            and item.value.id == "safe_for_release"
            for item in ast.walk(method_status)
        )
        if not assigns_safe_for_release or not returns_safe_for_release:
            findings.append("packages/core/doctor.py:_method_status missing safe_for_release flow")
    return findings


def _scan_tokens(paths: list[str], tokens: list[str]) -> list[str]:
    findings: list[str] = []
    for path in iter_text_files(paths):
        if path.name == "check_false_success.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for token in tokens:
            if token.lower() in text:
                findings.append(f"{path.relative_to(repo_root())}:{token}")
    return findings


def _platform_branch_findings() -> list[str]:
    findings: list[str] = []
    for path in iter_text_files(["packages/core/rendering.py", "packages/core/exporting.py"]):
        rel_path = str(path.relative_to(repo_root()))
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=rel_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and _condition_mentions_platform_value(node.test):
                findings.append(f"{rel_path}:platform control flow")
            if (
                isinstance(node, ast.Match)
                and isinstance(node.subject, ast.Name)
                and node.subject.id == "platform"
            ):
                findings.append(f"{rel_path}:match platform")
    return findings


def _condition_mentions_platform_value(node: ast.AST) -> bool:
    if (
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "platform"
    ):
        return any(isinstance(comparator, ast.Constant) for comparator in node.comparators)
    if isinstance(node, ast.BoolOp):
        return any(_condition_mentions_platform_value(value) for value in node.values)
    if isinstance(node, ast.UnaryOp):
        return _condition_mentions_platform_value(node.operand)
    return False


def _static_string_dict(node: ast.AST) -> bool:
    if not isinstance(node, ast.Dict):
        return False
    for key, value in zip(node.keys, node.values, strict=True):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            return False
        if isinstance(value, ast.Dict):
            if not _static_string_dict(value):
                return False
        elif not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            return False
    return True


def _platform_extra_files_findings() -> list[str]:
    tree = _tree("packages/core/exporting.py")
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "PLATFORM_EXTRA_FILES"
            for target in node.targets
        ):
            if _static_string_dict(node.value):
                return []
            return ["packages/core/exporting.py:PLATFORM_EXTRA_FILES must be static strings"]
    return ["packages/core/exporting.py:missing PLATFORM_EXTRA_FILES whitelist"]


def run_false_success_scan() -> list[ScanResult]:
    no_force_findings = check_no_force(["apps", "packages", "providers", "engines", "bin"])
    forbidden_imports = check_forbidden_imports(["packages/core", "providers"])
    render_scope = check_render_engine_m1(["packages", "engines"])
    ffmpeg_scope = check_ffmpeg_card_scope(["engines/ffmpeg_card"])
    mock_release_missing = _raises_lingjian_error(
        "packages/core/exporting.py",
        "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE",
    )
    preview_release_missing = _raises_lingjian_error(
        "packages/core/exporting.py",
        "PREVIEW_ARTIFACT_NOT_RELEASABLE",
    )
    doctor_missing = _doctor_release_provider_findings()
    sqlite_missing = _sqlite_index_findings()
    tests_missing = _test_coverage_findings()
    platform_findings = _platform_branch_findings() + _platform_extra_files_findings()
    network_findings = _scan_tokens(["tests", "scripts/ci"], ["requests.", "httpx.", "socket."])
    third_party_findings = _scan_tokens(
        ["apps", "packages", "providers", "engines"],
        ["videolingo", "losslesscut", "motion-director"],
    )
    downloader_findings = _scan_tokens(
        ["apps", "packages", "providers", "engines"],
        ["yt-dlp", "youtube-dl"],
    )

    return [
        ScanResult("FS-01", "无强制跳过入口", not no_force_findings, no_force_findings),
        ScanResult(
            "FS-02", "release 遇 mock 有稳定错误码", not mock_release_missing, mock_release_missing
        ),
        ScanResult(
            "FS-03",
            "preview 产物不能被 release 引用",
            not preview_release_missing,
            preview_release_missing,
        ),
        ScanResult(
            "FS-04", "core/provider 无禁用引擎 SDK import", not forbidden_imports, forbidden_imports
        ),
        ScanResult("FS-05", "M1 渲染引擎范围冻结", not render_scope, render_scope),
        ScanResult("FS-06", "ffmpeg_card 无越界动效能力", not ffmpeg_scope, ffmpeg_scope),
        ScanResult(
            "FS-07",
            "render/export 无平台名控制流;静态 dict 为受控例外",
            not platform_findings,
            platform_findings,
        ),
        ScanResult("FS-08", "离线测试不依赖网络或真实 key", not network_findings, network_findings),
        ScanResult("FS-09", "SQLite 为派生索引且可重建", not sqlite_missing, sqlite_missing),
        ScanResult("FS-10", "审批 stale 与 reindex 有测试覆盖", not tests_missing, tests_missing),
        ScanResult(
            "FS-11", "未引入高风险第三方项目代码名", not third_party_findings, third_party_findings
        ),
        ScanResult(
            "FS-12", "默认路径未引入视频下载器", not downloader_findings, downloader_findings
        ),
        ScanResult("FS-13", "doctor 区分真实发布 provider", not doctor_missing, doctor_missing),
    ]


if __name__ == "__main__":
    results = run_false_success_scan()
    print(json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2))
    if not all(result.ok for result in results):
        raise SystemExit(1)
