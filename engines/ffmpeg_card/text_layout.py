from __future__ import annotations

import re

LATIN_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*")


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    for match in LATIN_WORD.finditer(text):
        if match.start() > index:
            tokens.extend(list(text[index : match.start()]))
        tokens.append(match.group(0))
        index = match.end()
    if index < len(text):
        tokens.extend(list(text[index:]))
    return [token for token in tokens if token.strip()]


def break_cjk_text(text: str, max_chars: int, max_lines: int) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    current = ""
    warnings: list[str] = []

    for token in _tokens(text):
        next_line = current + token
        limit = max(max_chars, len(token))
        if current and len(next_line) > limit:
            lines.append(current)
            current = token
            if len(lines) == max_lines:
                warnings.append("TEXT_TRUNCATED")
                return lines, warnings
        else:
            current = next_line

    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) > max_lines:
        warnings.append("TEXT_TRUNCATED")
        lines = lines[:max_lines]
    if text and "".join(lines) != "".join(_tokens(text)):
        warnings.append("TEXT_TRUNCATED")
    return lines, warnings
