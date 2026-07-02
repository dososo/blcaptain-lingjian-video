from engines.ffmpeg_card.text_layout import break_cjk_text
from packages.core.provider_errors import classify_provider_error
from packages.core.validation import validate_input_body


def test_cjk_breaking_limits_lines_and_preserves_latin_words():
    lines, warnings = break_cjk_text("这是一个非常长的中文标题OpenAI-compatible provider", 8, 2)

    assert len(lines) == 2
    assert all(len(line) <= 20 for line in lines)
    assert all("compatib" not in line for line in lines)
    assert warnings


def test_thin_input_returns_warning_not_crash():
    result = validate_input_body("太短")

    assert result.ok is False
    assert result.severity == "warning"
    assert result.code == "INPUT_TOO_THIN"


def test_provider_error_classification_has_actionable_codes():
    assert classify_provider_error(status_code=401, body="bad key") == "PROVIDER_AUTH_FAILED"
    assert classify_provider_error(status_code=429, body="rate limit") == "LLM_RATE_LIMITED"
    assert (
        classify_provider_error(status_code=402, body="quota exceeded")
        == "PROVIDER_QUOTA_EXCEEDED"
    )
    assert classify_provider_error(status_code=200, body="not json") == "LLM_INVALID_JSON"
