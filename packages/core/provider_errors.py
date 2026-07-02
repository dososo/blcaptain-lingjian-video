from __future__ import annotations


def classify_provider_error(status_code: int, body: str) -> str:
    normalized = body.lower()
    if status_code in {401, 403}:
        return "PROVIDER_AUTH_FAILED"
    if status_code == 429 or "rate limit" in normalized:
        return "LLM_RATE_LIMITED"
    if status_code in {402, 409} or "quota" in normalized:
        return "PROVIDER_QUOTA_EXCEEDED"
    if status_code == 200:
        return "LLM_INVALID_JSON"
    return "TTS_PROVIDER_ERROR"
