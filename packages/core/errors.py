from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ErrorResult:
    error_code: str
    message_zh: str
    hint: str
    details: dict[str, Any] = field(default_factory=dict)


class LingjianError(Exception):
    def __init__(
        self,
        error_code: str,
        message_zh: str,
        hint: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message_zh)
        self.error_code = error_code
        self.message_zh = message_zh
        self.hint = hint
        self.details = details or {}

    def to_result(self) -> ErrorResult:
        return ErrorResult(self.error_code, self.message_zh, self.hint, self.details)
