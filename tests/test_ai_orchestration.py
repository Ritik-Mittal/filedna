"""
Tests for FileDNA AI orchestration layer.

All tests run without a real API key — we mock litellm.completion
to simulate rate limits, auth failures, fallbacks, etc.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from filedna.features.ai_features import (
    AIConfig,
    AIError,
    AIResponse,
    AttemptRecord,
    ErrorKind,
    RetryPolicy,
    _call_with_retry,
    _classify_error,
    _orchestrate,
    classify_content,
    extract_structured,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(text: str) -> MagicMock:
    """Fake litellm response object."""
    r = MagicMock()
    r.choices[0].message.content = text
    return r


def _make_config(
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    max_attempts: int = 3,
    base_delay: float = 0.0,   # zero delay for tests
    fallbacks: list | None = None,
) -> AIConfig:
    return AIConfig(
        provider=provider,
        model=model,
        api_key="test-key",
        fallbacks=fallbacks or [],
        retry=RetryPolicy(
            max_attempts=max_attempts,
            base_delay=base_delay,
            jitter=False,
        ),
    )


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class TestErrorClassification:
    def test_rate_limit_by_class_name(self):
        class RateLimitError(Exception): pass
        assert _classify_error(RateLimitError()) == ErrorKind.RATE_LIMIT

    def test_rate_limit_by_message(self):
        assert _classify_error(Exception("HTTP 429 rate limit exceeded")) == ErrorKind.RATE_LIMIT

    def test_auth_by_status(self):
        assert _classify_error(Exception("401 Unauthorized")) == ErrorKind.AUTH

    def test_auth_by_class(self):
        class AuthenticationError(Exception): pass
        assert _classify_error(AuthenticationError()) == ErrorKind.AUTH

    def test_context_length(self):
        assert _classify_error(Exception("context length exceeded")) == ErrorKind.CONTEXT_LENGTH

    def test_server_error_503(self):
        assert _classify_error(Exception("503 service unavailable")) == ErrorKind.SERVER_ERROR

    def test_network_timeout(self):
        assert _classify_error(Exception("connection timeout")) == ErrorKind.NETWORK

    def test_unknown_default(self):
        assert _classify_error(Exception("something completely unexpected")) == ErrorKind.UNKNOWN


# ---------------------------------------------------------------------------
# RetryPolicy backoff math
# ---------------------------------------------------------------------------

class TestRetryPolicy:
    def test_exponential_no_jitter(self):
        p = RetryPolicy(base_delay=1.0, max_delay=100.0, jitter=False)
        assert p.wait_time(0) == 1.0
        assert p.wait_time(1) == 2.0
        assert p.wait_time(2) == 4.0
        assert p.wait_time(3) == 8.0

    def test_cap_enforced(self):
        p = RetryPolicy(base_delay=1.0, max_delay=5.0, jitter=False)
        assert p.wait_time(10) == 5.0

    def test_jitter_within_bounds(self):
        p = RetryPolicy(base_delay=1.0, max_delay=10.0, jitter=True)
        for _ in range(50):
            w = p.wait_time(2)  # uncapped = 4.0
            assert 0.0 <= w <= 4.0

    def test_retryable_set(self):
        p = RetryPolicy()
        assert ErrorKind.RATE_LIMIT in p.retryable
        assert ErrorKind.AUTH not in p.retryable
        assert ErrorKind.INVALID_REQUEST not in p.retryable


# ---------------------------------------------------------------------------
# AIConfig
# ---------------------------------------------------------------------------

class TestAIConfig:
    def test_litellm_model_openai(self):
        c = AIConfig(provider="openai", model="gpt-4o-mini")
        assert c.litellm_model == "gpt-4o-mini"

    def test_litellm_model_anthropic(self):
        c = AIConfig(provider="anthropic", model="claude-haiku-4-5")
        assert c.litellm_model == "anthropic/claude-haiku-4-5"

    def test_litellm_model_gemini(self):
        c = AIConfig(provider="gemini", model="gemini-1.5-flash")
        assert c.litellm_model == "gemini/gemini-1.5-flash"

    def test_litellm_model_no_double_prefix(self):
        c = AIConfig(provider="anthropic", model="anthropic/claude-haiku-4-5")
        assert c.litellm_model == "anthropic/claude-haiku-4-5"

    def test_display_name(self):
        c = AIConfig(provider="openai", model="gpt-4o-mini")
        assert c.display_name == "openai/gpt-4o-mini"

    def test_env_key_resolution(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-test")
        c = AIConfig(provider="openai", model="gpt-4o")
        assert c.api_key == "sk-env-test"

    def test_explicit_key_overrides_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-test")
        c = AIConfig(provider="openai", model="gpt-4o", api_key="sk-explicit")
        assert c.api_key == "sk-explicit"


# ---------------------------------------------------------------------------
# AIResponse
# ---------------------------------------------------------------------------

class TestAIResponse:
    def test_used_fallback_false_when_primary_succeeds(self):
        r = AIResponse(
            success=True,
            provider_used="openai/gpt-4o-mini",
            attempts=[
                AttemptRecord("openai", "gpt-4o-mini", 1, succeeded=True, is_fallback=False),
            ],
        )
        assert r.used_fallback is False

    def test_used_fallback_true_when_fallback_serves(self):
        r = AIResponse(
            success=True,
            provider_used="anthropic/claude-haiku-4-5",
            attempts=[
                AttemptRecord("openai", "gpt-4o-mini", 1,
                              error_kind=ErrorKind.AUTH, succeeded=False, is_fallback=False),
                AttemptRecord("anthropic", "claude-haiku-4-5", 1,
                              succeeded=True, is_fallback=True),
            ],
        )
        assert r.used_fallback is True

    def test_used_fallback_true_same_provider_different_config(self):
        """Critical: same provider/model but fallback config — must still detect as fallback."""
        r = AIResponse(
            success=True,
            provider_used="openai/gpt-4o-mini",
            attempts=[
                AttemptRecord("openai", "gpt-4o-mini", 1,
                              error_kind=ErrorKind.AUTH, succeeded=False, is_fallback=False),
                AttemptRecord("openai", "gpt-4o-mini", 1,
                              succeeded=True, is_fallback=True),
            ],
        )
        assert r.used_fallback is True

    def test_retry_count(self):
        r = AIResponse(attempts=[
            AttemptRecord("openai", "gpt-4o-mini", 1, succeeded=False),
            AttemptRecord("openai", "gpt-4o-mini", 2, succeeded=False),
            AttemptRecord("openai", "gpt-4o-mini", 3, succeeded=True),
        ])
        assert r.retry_count == 2

    def test_raise_if_failed_succeeds(self):
        r = AIResponse(success=True, value="hello")
        assert r.raise_if_failed() is r

    def test_raise_if_failed_raises(self):
        r = AIResponse(success=False, error="All providers failed")
        with pytest.raises(AIError) as exc_info:
            r.raise_if_failed()
        assert exc_info.value.response is r
        assert "All providers failed" in str(exc_info.value)

    def test_summary_contains_check_and_cross(self):
        r = AIResponse(
            success=True,
            attempts=[
                AttemptRecord("openai", "gpt-4o-mini", 1,
                              error_kind=ErrorKind.RATE_LIMIT, succeeded=False),
                AttemptRecord("openai", "gpt-4o-mini", 2, succeeded=True),
            ],
        )
        s = r.summary()
        assert "✓" in s
        assert "✗" in s
        assert "rate_limit" in s


# ---------------------------------------------------------------------------
# _call_with_retry — mock litellm
# ---------------------------------------------------------------------------

class TestCallWithRetry:
    def test_succeeds_first_attempt(self):
        config = _make_config(max_attempts=3)
        log: list[AttemptRecord] = []

        with patch("litellm.completion", return_value=_make_response("hello")):
            result = _call_with_retry("prompt", "system", config, log)

        assert result == "hello"
        assert len(log) == 1
        assert log[0].succeeded is True
        assert log[0].attempt_number == 1

    def test_retries_on_rate_limit(self):
        config = _make_config(max_attempts=3, base_delay=0.0)
        log: list[AttemptRecord] = []
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("429 rate limit exceeded")
            return _make_response("success after retries")

        with patch("litellm.completion", side_effect=side_effect):
            result = _call_with_retry("prompt", "system", config, log)

        assert result == "success after retries"
        assert call_count == 3
        assert len(log) == 3
        assert log[0].error_kind == ErrorKind.RATE_LIMIT
        assert log[1].error_kind == ErrorKind.RATE_LIMIT
        assert log[2].succeeded is True

    def test_auth_error_skips_immediately(self):
        config = _make_config(max_attempts=3)
        log: list[AttemptRecord] = []

        with patch("litellm.completion", side_effect=Exception("401 Unauthorized")):
            result = _call_with_retry("prompt", "system", config, log)

        assert result is None
        assert len(log) == 1   # only one attempt — no retry on auth errors
        assert log[0].error_kind == ErrorKind.AUTH

    def test_exhausts_all_attempts(self):
        config = _make_config(max_attempts=3, base_delay=0.0)
        log: list[AttemptRecord] = []

        with patch("litellm.completion", side_effect=Exception("503 server error")):
            result = _call_with_retry("prompt", "system", config, log)

        assert result is None
        assert len(log) == 3

    def test_context_length_truncates_and_retries(self):
        config = _make_config(max_attempts=3, base_delay=0.0)
        log: list[AttemptRecord] = []
        seen_prompts: list[str] = []

        def side_effect(**kwargs):
            seen_prompts.append(kwargs["messages"][1]["content"])
            if len(seen_prompts) == 1:
                raise Exception("context length exceeded")
            return _make_response("ok after truncation")

        with patch("litellm.completion", side_effect=side_effect):
            result = _call_with_retry("A" * 1000, "system", config, log)

        assert result == "ok after truncation"
        # Second prompt should be shorter
        assert len(seen_prompts[1]) < len(seen_prompts[0])

    def test_missing_litellm_raises_import_error(self):
        config = _make_config()
        log: list[AttemptRecord] = []

        with patch.dict("sys.modules", {"litellm": None}):
            with pytest.raises(ImportError, match="litellm"):
                _call_with_retry("prompt", "system", config, log)


# ---------------------------------------------------------------------------
# _orchestrate — full pipeline
# ---------------------------------------------------------------------------

class TestOrchestrate:
    def test_primary_succeeds_no_fallback_needed(self):
        config = _make_config()
        with patch("litellm.completion", return_value=_make_response("result")):
            r = _orchestrate("prompt", "system", config)

        assert r.success is True
        assert r.value == "result"
        assert r.used_fallback is False

    def test_falls_back_on_auth_error(self):
        primary = _make_config("openai", "gpt-4o-mini")
        fallback = _make_config("anthropic", "claude-haiku-4-5")
        primary.fallbacks = [fallback]

        call_count = 0
        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if "openai" in kwargs.get("model", "") or call_count == 1:
                raise Exception("401 Unauthorized")
            return _make_response("fallback answer")

        with patch("litellm.completion", side_effect=side_effect):
            r = _orchestrate("prompt", "system", primary)

        assert r.success is True
        assert r.used_fallback is True
        assert "anthropic" in r.provider_used

    def test_all_providers_fail_returns_failed_response(self):
        primary = _make_config("openai", "gpt-4o-mini", max_attempts=2)
        fallback = _make_config("anthropic", "claude-haiku-4-5", max_attempts=1)
        primary.fallbacks = [fallback]

        with patch("litellm.completion", side_effect=Exception("401 Unauthorized")):
            r = _orchestrate("prompt", "system", primary)

        assert r.success is False
        assert r.value is None
        assert r.error is not None
        assert "openai" in r.error
        assert "anthropic" in r.error

    def test_response_has_total_duration(self):
        config = _make_config()
        with patch("litellm.completion", return_value=_make_response("hello")):
            r = _orchestrate("prompt", "system", config)
        assert r.total_duration_ms >= 0

    def test_multiple_fallbacks_tried_in_order(self):
        f1 = _make_config("anthropic", "claude-haiku-4-5", max_attempts=1)
        f2 = _make_config("gemini", "gemini-1.5-flash", max_attempts=1)
        primary = _make_config("openai", "gpt-4o-mini", max_attempts=1)
        primary.fallbacks = [f1, f2]

        providers_tried: list[str] = []
        def side_effect(**kwargs):
            model = kwargs.get("model", "")
            providers_tried.append(model)
            if "gemini" in model:
                return _make_response("gemini succeeded")
            raise Exception("401 Unauthorized")

        with patch("litellm.completion", side_effect=side_effect):
            r = _orchestrate("prompt", "system", primary)

        assert r.success is True
        assert "gemini" in r.provider_used
        assert len(providers_tried) == 3  # tried all three in order


# ---------------------------------------------------------------------------
# Public AI function wrappers
# ---------------------------------------------------------------------------

class TestClassifyContent:
    def test_returns_ai_response(self):
        config = _make_config()
        valid_json = '{"label": "invoice", "confidence": "high", "reasoning": "has total"}'
        with patch("litellm.completion", return_value=_make_response(valid_json)):
            r = classify_content("some text", config=config)
        assert isinstance(r, AIResponse)
        assert r.success is True
        assert r.value["label"] == "invoice"

    def test_handles_json_parse_failure_gracefully(self):
        config = _make_config()
        with patch("litellm.completion", return_value=_make_response("not valid json !!")):
            r = classify_content("some text", config=config)
        assert r.success is True  # LLM call succeeded, parse is best-effort
        assert r.value["label"] == "unknown"

    def test_failure_has_error_message(self):
        config = _make_config(max_attempts=1)
        with patch("litellm.completion", side_effect=Exception("401 Unauthorized")):
            r = classify_content("some text", config=config)
        assert r.success is False
        assert r.error is not None
        assert "openai" in r.error


class TestExtractStructured:
    def test_extracts_fields(self):
        config = _make_config()
        json_resp = '{"invoice_number": "INV-001", "total": 99.99}'
        with patch("litellm.completion", return_value=_make_response(json_resp)):
            r = extract_structured(
                "Invoice INV-001, total $99.99",
                schema={"invoice_number": "string", "total": "float"},
                config=config,
            )
        assert r.success is True
        assert r.value["invoice_number"] == "INV-001"

    def test_strict_raises_on_missing_fields(self):
        config = _make_config()
        with patch("litellm.completion", return_value=_make_response('{"invoice_number": null}')):
            with pytest.raises(ValueError, match="Required fields missing"):
                extract_structured(
                    "some text",
                    schema={"invoice_number": "string"},
                    config=config,
                    strict=True,
                )

    def test_failed_response_no_raise_without_strict(self):
        config = _make_config(max_attempts=1)
        with patch("litellm.completion", side_effect=Exception("503 service unavailable")):
            r = extract_structured("text", schema={"k": "v"}, config=config)
        assert r.success is False


# summarize() was removed — content-core handles summarization.
# FileDNA AI focuses on: classify_content, extract_structured,
# clean_document, semantic_similarity.
