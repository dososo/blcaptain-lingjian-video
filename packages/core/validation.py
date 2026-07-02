from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    severity: str
    code: str
    message_zh: str


def validate_input_body(body: str, min_chars: int = 20) -> ValidationResult:
    if len(body.strip()) < min_chars:
        return ValidationResult(
            ok=False,
            severity="warning",
            code="INPUT_TOO_THIN",
            message_zh="输入内容过薄,建议补充正文、截图或缩短目标时长。",
        )
    return ValidationResult(ok=True, severity="info", code="INPUT_OK", message_zh="输入可用。")
