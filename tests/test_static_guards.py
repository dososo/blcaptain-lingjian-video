import scripts.ci.check_false_success as false_success
from scripts.ci.check_false_success import run_false_success_scan
from scripts.ci.check_ffmpeg_card_scope import check_ffmpeg_card_scope
from scripts.ci.check_forbidden_imports import check_forbidden_imports
from scripts.ci.check_no_force import check_no_force
from scripts.ci.check_render_engine_m1 import check_render_engine_m1


def test_no_force_or_bypass_paths():
    assert check_no_force(["apps", "packages", "providers", "engines", "bin", "scripts"]) == []


def test_core_and_providers_do_not_import_forbidden_sdks():
    assert check_forbidden_imports(["packages/core", "providers"]) == []


def test_render_engine_only_allows_ffmpeg_card():
    assert check_render_engine_m1(["packages", "engines"]) == []


def test_ffmpeg_card_scope_freeze():
    assert check_ffmpeg_card_scope(["engines/ffmpeg_card"]) == []


def test_false_success_scan_has_no_findings():
    results = run_false_success_scan()

    assert all(result.ok for result in results)
    assert len(results) == 13


def test_false_success_scan_rejects_dead_error_code_string(monkeypatch):
    original_text = false_success._text
    exporting = original_text("packages/core/exporting.py")
    mutated = (
        exporting.replace('"MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE"', '"UNRELATED_CONSTANT"')
        + '\nDEAD_STRING = "MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE"\n'
    )

    def fake_text(rel_path: str) -> str:
        if rel_path == "packages/core/exporting.py":
            return mutated
        return original_text(rel_path)

    monkeypatch.setattr(false_success, "_text", fake_text)

    result = next(item for item in false_success.run_false_success_scan() if item.id == "FS-02")

    assert result.ok is False
    assert result.findings == [
        (
            "packages/core/exporting.py:missing raise "
            "LingjianError(MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE)"
        )
    ]


def test_platform_extra_files_whitelist_requires_static_strings(monkeypatch):
    original_text = false_success._text
    exporting = original_text("packages/core/exporting.py")
    mutated = exporting.replace(
        '"stub thumbnail\\n"',
        'make_thumbnail()',
    )

    def fake_text(rel_path: str) -> str:
        if rel_path == "packages/core/exporting.py":
            return mutated
        return original_text(rel_path)

    monkeypatch.setattr(false_success, "_text", fake_text)

    result = next(item for item in false_success.run_false_success_scan() if item.id == "FS-07")

    assert result.ok is False
    assert result.findings == [
        "packages/core/exporting.py:PLATFORM_EXTRA_FILES must be static strings"
    ]
