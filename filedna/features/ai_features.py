"""
FileDNA – AI-powered features with resilient orchestration.

Every LLM call goes through the orchestration layer:

    Primary provider → retry with exponential backoff
         ↓ (exhausted or hard failure)
    Fallback provider 1 → retry with exponential backoff
         ↓ (exhausted or hard failure)
    Fallback provider 2 → ...
         ↓ (all exhausted)
    AIError raised with full audit trail

Error classification:
    RATE_LIMIT     → retry with backoff (server is busy, will recover)
    SERVER_ERROR   → retry with backoff (transient 5xx)
    NETWORK        → retry with backoff (connection issues)
    AUTH           → skip to next fallback immediately (retrying won't help)
    CONTEXT_LENGTH → truncate input and retry once
    INVALID_REQUEST→ skip to next fallback (bad model/params)
    UNKNOWN        → retry with backoff (conservative default)

Setup:
    from filedna.features.ai_features import AIConfig

    # Single provider
    config = AIConfig(provider="openai", model="gpt-4o-mini")

    # With fallbacks
    config = AIConfig(
        provider="openai",
        model="gpt-4o-mini",
        fallbacks=[
            AIConfig(provider="anthropic", model="claude-haiku-4-5"),
            AIConfig(provider="gemini",    model="gemini-1.5-flash"),
        ]
    )

Usage:
    result = classify_content(text, config=config)
    print(result.value)          # the actual answer
    print(result.provider_used)  # which provider served it
    print(result.attempts)       # full attempt history
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("filedna.ai")


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class ErrorKind(Enum):
    RATE_LIMIT      = "rate_limit"      # 429 — retry with backoff
    SERVER_ERROR    = "server_error"    # 5xx — retry with backoff
    NETWORK         = "network"         # connection error — retry
    AUTH            = "auth"            # 401/403 — skip to fallback
    CONTEXT_LENGTH  = "context_length"  # input too long — truncate + retry
    INVALID_REQUEST = "invalid_request" # bad model/params — skip to fallback
    UNKNOWN         = "unknown"         # conservative: retry


def _classify_error(exc: Exception) -> ErrorKind:
    """Classify an exception into an ErrorKind for retry/fallback decisions."""
    msg = str(exc).lower()

    # litellm wraps errors with these class names
    cls = type(exc).__name__.lower()

    if "ratelimit" in cls or "rate_limit" in cls or "429" in msg or "rate limit" in msg:
        return ErrorKind.RATE_LIMIT
    if "autherror" in cls or "authenticationerror" in cls or "401" in msg or "403" in msg:
        return ErrorKind.AUTH
    if "contextwindow" in cls or "contextlength" in cls or "context" in msg and "length" in msg:
        return ErrorKind.CONTEXT_LENGTH
    if "badrequest" in cls or "400" in msg or "invalid" in msg and "model" in msg:
        return ErrorKind.INVALID_REQUEST
    if "serviceunavailable" in cls or "500" in msg or "502" in msg or "503" in msg or "504" in msg:
        return ErrorKind.SERVER_ERROR
    if "connection" in msg or "timeout" in msg or "network" in msg or "connect" in cls:
        return ErrorKind.NETWORK

    return ErrorKind.UNKNOWN


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    """
    Controls retry behaviour within a single provider.

    Uses exponential backoff with full jitter:
        wait = random(0, min(cap, base * 2 ^ attempt))

    Full jitter avoids thundering herd when multiple processes retry
    at the same time after a rate limit.
    """
    max_attempts: int = 3           # total attempts (1 = no retry)
    base_delay: float = 1.0         # seconds for first retry
    max_delay: float = 30.0         # cap on backoff
    jitter: bool = True             # randomise wait time

    # Which error kinds to retry (AUTH and INVALID_REQUEST are never retried)
    retryable: frozenset[ErrorKind] = field(default_factory=lambda: frozenset({
        ErrorKind.RATE_LIMIT,
        ErrorKind.SERVER_ERROR,
        ErrorKind.NETWORK,
        ErrorKind.UNKNOWN,
    }))

    def wait_time(self, attempt: int) -> float:
        """Compute wait time for attempt N (0-based)."""
        exponential = self.base_delay * (2 ** attempt)
        capped = min(self.max_delay, exponential)
        if self.jitter:
            return random.uniform(0, capped)
        return capped


# ---------------------------------------------------------------------------
# AIConfig
# ---------------------------------------------------------------------------

@dataclass
class AIConfig:
    """
    LLM provider configuration with fallback chain support.

    Args:
        provider:  Provider name. Supported: openai, anthropic, gemini,
                   mistral, cohere, ollama, azure, groq, together, and
                   anything litellm supports.
        model:     Model name (e.g. "gpt-4o-mini", "claude-haiku-4-5").
        api_key:   API key. If None, reads from environment variable.
        max_tokens: Max tokens to generate.
        temperature: Sampling temperature (0.0–2.0). Use 0.1 for structured output.
        fallbacks: Ordered list of fallback AIConfig instances to try if
                   this provider fails.
        retry:     Retry policy for this provider.
    """
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.1
    fallbacks: list["AIConfig"] = field(default_factory=list)
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    # Env var mapping: provider → env var name
    _ENV_KEYS: dict[str, str] = field(default_factory=lambda: {
        "openai":    "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini":    "GOOGLE_API_KEY",
        "google":    "GOOGLE_API_KEY",
        "mistral":   "MISTRAL_API_KEY",
        "cohere":    "COHERE_API_KEY",
        "groq":      "GROQ_API_KEY",
        "together":  "TOGETHER_API_KEY",
        "azure":     "AZURE_API_KEY",
    }, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            env_var = self._ENV_KEYS.get(self.provider.lower())
            if env_var:
                self.api_key = os.environ.get(env_var)

    @property
    def litellm_model(self) -> str:
        """Return the litellm model string."""
        p = self.provider.lower()
        if p == "openai":
            return self.model
        if p in ("gemini", "google"):
            return f"gemini/{self.model}" if "/" not in self.model else self.model
        if p == "anthropic":
            return f"anthropic/{self.model}" if "/" not in self.model else self.model
        if p == "ollama":
            return f"ollama/{self.model}" if "/" not in self.model else self.model
        if p == "groq":
            return f"groq/{self.model}" if "/" not in self.model else self.model
        return self.model

    @property
    def display_name(self) -> str:
        return f"{self.provider}/{self.model}"


# ---------------------------------------------------------------------------
# Attempt record — full audit trail
# ---------------------------------------------------------------------------

@dataclass
class AttemptRecord:
    """Record of a single LLM call attempt."""
    provider: str
    model: str
    attempt_number: int         # within this provider (1-based)
    error_kind: ErrorKind | None = None
    error_message: str | None = None
    duration_ms: float = 0.0
    wait_before_ms: float = 0.0  # backoff sleep before this attempt
    succeeded: bool = False
    is_fallback: bool = False    # True if this was a fallback provider, not the primary

    def __str__(self) -> str:
        fallback_tag = " [fallback]" if self.is_fallback else ""
        if self.succeeded:
            return f"  ✓ {self.provider}/{self.model}{fallback_tag} attempt {self.attempt_number} ({self.duration_ms:.0f}ms)"
        return (
            f"  ✗ {self.provider}/{self.model}{fallback_tag} attempt {self.attempt_number} "
            f"[{self.error_kind.value if self.error_kind else 'unknown'}] "
            f"{self.error_message or ''}"
        )


# ---------------------------------------------------------------------------
# AIResponse — wraps every result
# ---------------------------------------------------------------------------

@dataclass
class AIResponse:
    """
    Result of an AI operation.

    Always returned — even on failure (check .success before using .value).
    Contains the full attempt history so developers can see exactly what happened.
    """
    value: Any = None                           # the actual answer
    success: bool = False
    provider_used: str | None = None            # e.g. "openai/gpt-4o-mini"
    attempts: list[AttemptRecord] = field(default_factory=list)
    total_duration_ms: float = 0.0
    error: str | None = None                    # human-readable error summary

    @property
    def used_fallback(self) -> bool:
        """True if a fallback provider served the successful response."""
        return any(a.succeeded and a.is_fallback for a in self.attempts)

    @property
    def retry_count(self) -> int:
        return max(0, len(self.attempts) - 1)

    def summary(self) -> str:
        lines = [f"AI call {'succeeded' if self.success else 'FAILED'} "
                 f"({self.total_duration_ms:.0f}ms total)"]
        for a in self.attempts:
            lines.append(str(a))
        if self.error:
            lines.append(f"  Final error: {self.error}")
        return "\n".join(lines)

    def raise_if_failed(self) -> "AIResponse":
        """Raise AIError if this response is a failure. Returns self otherwise."""
        if not self.success:
            raise AIError(self.error or "AI call failed", response=self)
        return self


# ---------------------------------------------------------------------------
# AIError
# ---------------------------------------------------------------------------

class AIError(Exception):
    """Raised when all providers and fallbacks are exhausted."""
    def __init__(self, message: str, response: AIResponse | None = None):
        super().__init__(message)
        self.response = response

    def __str__(self) -> str:
        base = super().__str__()
        if self.response:
            return base + "\n" + self.response.summary()
        return base


# ---------------------------------------------------------------------------
# Core orchestration engine
# ---------------------------------------------------------------------------

def _call_with_retry(
    prompt: str,
    system: str,
    config: AIConfig,
    attempt_log: list[AttemptRecord],
    is_fallback: bool = False,
) -> str | None:
    """
    Try a single provider with retry + backoff.

    Returns the response string on success, None if all attempts failed.
    Appends AttemptRecord entries to attempt_log for full audit trail.
    """
    try:
        import litellm  # type: ignore
        litellm.set_verbose = False
    except ImportError:
        raise ImportError(
            "litellm is required for AI features. "
            "Install with: pip install 'filedna[ai]' or pip install litellm"
        )

    policy = config.retry
    current_prompt = prompt

    for attempt_num in range(1, policy.max_attempts + 1):
        wait_ms = 0.0

        # Backoff sleep (not before first attempt)
        if attempt_num > 1:
            wait_sec = policy.wait_time(attempt_num - 2)  # 0-based exponent
            wait_ms = wait_sec * 1000
            logger.debug(
                "FileDNA AI: retrying %s/%s (attempt %d/%d) after %.1fs backoff",
                config.provider, config.model, attempt_num, policy.max_attempts, wait_sec,
            )
            time.sleep(wait_sec)

        record = AttemptRecord(
            provider=config.provider,
            model=config.model,
            attempt_number=attempt_num,
            wait_before_ms=wait_ms,
            is_fallback=is_fallback,
        )

        t_start = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {
                "model": config.litellm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": current_prompt},
                ],
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
            }
            if config.api_key:
                kwargs["api_key"] = config.api_key

            response = litellm.completion(**kwargs)
            text = response.choices[0].message.content or ""

            record.duration_ms = (time.perf_counter() - t_start) * 1000
            record.succeeded = True
            attempt_log.append(record)

            logger.debug(
                "FileDNA AI: %s/%s succeeded on attempt %d (%.0fms)",
                config.provider, config.model, attempt_num, record.duration_ms,
            )
            return text

        except Exception as exc:
            record.duration_ms = (time.perf_counter() - t_start) * 1000
            kind = _classify_error(exc)
            record.error_kind = kind
            record.error_message = str(exc)[:200]
            attempt_log.append(record)

            logger.warning(
                "FileDNA AI: %s/%s attempt %d/%d failed [%s]: %s",
                config.provider, config.model, attempt_num,
                policy.max_attempts, kind.value, str(exc)[:120],
            )

            # Hard failures — don't retry, move to fallback immediately
            if kind in (ErrorKind.AUTH, ErrorKind.INVALID_REQUEST):
                logger.info(
                    "FileDNA AI: %s error on %s/%s — skipping to fallback",
                    kind.value, config.provider, config.model,
                )
                return None

            # Context length — truncate and retry once
            if kind == ErrorKind.CONTEXT_LENGTH and attempt_num == 1:
                logger.info("FileDNA AI: context too long — truncating prompt by 30%% and retrying")
                current_prompt = current_prompt[: int(len(current_prompt) * 0.7)]
                continue

            # Retryable — but only if we have attempts left
            if kind not in policy.retryable:
                return None

            # Last attempt — no more retries
            if attempt_num == policy.max_attempts:
                return None

    return None


def _orchestrate(prompt: str, system: str, config: AIConfig) -> AIResponse:
    """
    Full orchestration: primary provider → fallbacks → AIResponse.

    Never raises. Always returns an AIResponse.
    Check .success before using .value.
    """
    t_start = time.perf_counter()
    attempts: list[AttemptRecord] = []

    # Build ordered list: primary first, then fallbacks
    providers = [config] + list(config.fallbacks)

    for i, provider_cfg in enumerate(providers):
        is_fallback = i > 0
        if is_fallback:
            logger.info(
                "FileDNA AI: primary provider exhausted — trying fallback %d: %s",
                i, provider_cfg.display_name,
            )

        result = _call_with_retry(prompt, system, provider_cfg, attempts, is_fallback=is_fallback)

        if result is not None:
            total_ms = (time.perf_counter() - t_start) * 1000
            return AIResponse(
                value=result,
                success=True,
                provider_used=provider_cfg.display_name,
                attempts=attempts,
                total_duration_ms=round(total_ms, 1),
            )

    # All providers exhausted
    total_ms = (time.perf_counter() - t_start) * 1000

    # Build a clear error message for the user
    failed_providers = []
    seen = set()
    for a in attempts:
        key = f"{a.provider}/{a.model}"
        if key not in seen:
            seen.add(key)
            failed_providers.append(key)

    error_msg = (
        f"All AI providers failed after {len(attempts)} total attempt(s). "
        f"Tried: {', '.join(failed_providers)}. "
        "Check your API keys and network connection. "
        "See .attempts for the full error log."
    )

    logger.error("FileDNA AI: %s", error_msg)

    return AIResponse(
        value=None,
        success=False,
        provider_used=None,
        attempts=attempts,
        total_duration_ms=round(total_ms, 1),
        error=error_msg,
    )


# ---------------------------------------------------------------------------
# Public AI functions
# ---------------------------------------------------------------------------

_DEFAULT_LABELS = [
    "invoice", "legal contract", "financial report", "resume / CV",
    "research paper", "technical documentation", "news article",
    "email", "meeting notes", "presentation", "spreadsheet data",
    "code", "medical document", "receipt", "other",
]


def classify_content(
    text: str,
    *,
    config: AIConfig,
    custom_labels: list[str] | None = None,
    top_k: int = 1,
) -> AIResponse:
    """
    Classify document content type.

    Returns AIResponse where .value is:
        {"label": "invoice", "confidence": "high", "reasoning": "..."}

    Always returns AIResponse — check .success before using .value.
    If all providers fail, .success=False and .error explains what happened.
    """
    labels = custom_labels or _DEFAULT_LABELS
    label_list = "\n".join(f"- {l}" for l in labels)

    system = (
        "You are a document classification expert. "
        "Return only valid JSON. No markdown, no explanation outside the JSON."
    )
    prompt = f"""Classify this document into one of the following categories:

{label_list}

Return JSON in this exact format:
{{
  "label": "<best matching label from the list above>",
  "confidence": "<high|medium|low>",
  "reasoning": "<one sentence>"
}}

Document (first 2000 characters):
{text[:2000]}"""

    response = _orchestrate(prompt, system, config)

    if response.success:
        try:
            clean = re.sub(r"```(?:json)?\s*|\s*```", "", response.value).strip()
            response.value = json.loads(clean)
        except Exception:
            response.value = {
                "label": "unknown",
                "confidence": "low",
                "reasoning": response.value[:200],
            }

    return response


def extract_structured(
    text: str,
    schema: dict[str, str],
    *,
    config: AIConfig,
    strict: bool = False,
) -> AIResponse:
    """
    Extract structured fields from unstructured document text.

    Returns AIResponse where .value is a dict matching the schema keys.
    Missing fields are null in the dict.

    If strict=True and required fields are missing, raises ValueError.

    Example:
        result = extract_structured(
            text,
            schema={
                "invoice_number": "string",
                "total_amount":   "float",
                "vendor_name":    "string",
            },
            config=config,
        )
        if result.success:
            print(result.value["invoice_number"])
        else:
            print(result.error)          # human-readable failure summary
            print(result.summary())      # full attempt log
    """
    schema_desc = "\n".join(f"  - {k}: {v}" for k, v in schema.items())

    system = (
        "You are a data extraction specialist. "
        "Extract the requested fields from the document. "
        "Return only valid JSON. Use null for missing fields. "
        "No markdown, no explanation outside the JSON."
    )
    prompt = f"""Extract the following fields from this document:

{schema_desc}

Return a JSON object with exactly these keys: {list(schema.keys())}

Document:
{text[:4000]}"""

    response = _orchestrate(prompt, system, config)

    if response.success:
        try:
            clean = re.sub(r"```(?:json)?\s*|\s*```", "", response.value).strip()
            parsed = json.loads(clean)
            response.value = parsed
        except json.JSONDecodeError:
            response.value = {"_raw": response.value, "_parse_error": True}
            return response

        if strict:
            missing = [k for k in schema if k not in parsed or parsed[k] is None]
            if missing:
                raise ValueError(
                    f"Required fields missing from extraction: {missing}. "
                    f"Provider: {response.provider_used}"
                )

    return response


def clean_document(
    text: str,
    *,
    config: AIConfig,
    instructions: str | None = None,
) -> AIResponse:
    """
    Remove headers, footers, page numbers, watermarks, boilerplate.

    Returns AIResponse where .value is the cleaned text string.
    """
    extra = f"\nAdditional instructions: {instructions}" if instructions else ""

    system = (
        "You are a document cleaning specialist. "
        "Return only the cleaned text. No JSON, no explanation."
    )
    prompt = f"""Clean the following document text by:
1. Removing page headers and footers (page numbers, document titles repeated on every page)
2. Removing watermarks and confidentiality stamps
3. Removing navigation menus and boilerplate
4. Fixing broken line breaks from PDF extraction
5. Preserving all actual content, tables, and structure{extra}

Document text:
{text[:6000]}"""

    return _orchestrate(prompt, system, config)


@dataclass
class SemanticSimilarity:
    score: float
    verdict: str
    reasoning: str


def semantic_similarity(
    text_a: str,
    text_b: str,
    *,
    config: AIConfig,
) -> AIResponse:
    """
    Compare two texts semantically.

    Returns AIResponse where .value is a SemanticSimilarity instance
    with .score (0.0–1.0), .verdict, and .reasoning.
    """
    system = (
        "You are a document comparison expert. "
        "Return only valid JSON. No markdown."
    )
    prompt = f"""Compare these two document excerpts for semantic similarity.

Document A (first 1500 chars):
{text_a[:1500]}

Document B (first 1500 chars):
{text_b[:1500]}

Return JSON:
{{
  "score": <float 0.0 to 1.0>,
  "verdict": "<identical|highly similar|related|different>",
  "reasoning": "<one sentence>"
}}"""

    response = _orchestrate(prompt, system, config)

    if response.success:
        try:
            clean = re.sub(r"```(?:json)?\s*|\s*```", "", response.value).strip()
            data = json.loads(clean)
            response.value = SemanticSimilarity(
                score=float(data.get("score", 0)),
                verdict=data.get("verdict", "unknown"),
                reasoning=data.get("reasoning", ""),
            )
        except Exception:
            response.value = SemanticSimilarity(
                score=0.0, verdict="unknown", reasoning=response.value[:200]
            )

    return response


# NOTE: summarize() was intentionally removed.
# content-core (https://github.com/lfnovo/content-core) already does this
# and does it better — with multiple extraction engines and MCP support.
# FileDNA's AI layer focuses on things content-core doesn't do:
# classify_content, extract_structured, clean_document, semantic_similarity.
