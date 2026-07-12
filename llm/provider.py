"""Provider-agnostic LLM client (see docs/04-llm-provider-interface.md).

Goal: swap between free testing models and the paid Claude API by changing the
LLM_PROVIDER env var, not code. Nothing outside this package knows which
provider is active.

Two OpenAI-compatible free providers (NVIDIA Build, OpenRouter) share one
implementation (only base URL, key, model differ). Anthropic uses its own SDK
and request shape.
"""
from __future__ import annotations

import logging
import re
import time

import config

log = logging.getLogger(__name__)

# base URL / key / model per OpenAI-compatible provider
_OPENAI_COMPATIBLE = {
    "nvidia": lambda: (config.NVIDIA_BASE_URL, config.NVIDIA_API_KEY, config.NVIDIA_MODEL),
    "openrouter": lambda: (config.OPENROUTER_BASE_URL, config.OPENROUTER_API_KEY, config.OPENROUTER_MODEL),
}

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_RETRY_BACKOFF_SECONDS = 3


class _UpstreamEnvelopeError(RuntimeError):
    """Provider returned HTTP 200 with a malformed/error body (choices=None,
    an embedded upstream 5xx, etc). The SDK's own retry logic never sees these
    as failures since the HTTP status is 200 — retried at the application level
    instead (see `complete`)."""


def active_provider(provider: str | None = None) -> str:
    return (provider or config.LLM_PROVIDER).strip().lower()


def model_label(provider: str | None = None) -> str:
    """'<provider>:<model>' — written to the Sheet's model_used column (doc 04)."""
    p = active_provider(provider)
    if p in _OPENAI_COMPATIBLE:
        _, _, model = _OPENAI_COMPATIBLE[p]()
        return f"{p}:{model}"
    if p == "anthropic":
        return f"anthropic:{config.ANTHROPIC_MODEL}"
    return p


def _extract_content(resp) -> str:
    """Pull message text from a chat-completion response, tolerating the malformed
    envelopes free providers sometimes return with HTTP 200 (e.g. choices=None or
    an error payload). Raises a clear, retryable error instead of an opaque
    TypeError."""
    choices = getattr(resp, "choices", None)
    if not choices:
        err = getattr(resp, "error", None)
        raise _UpstreamEnvelopeError(f"LLM response had no choices (provider envelope: error={err!r})")
    return (choices[0].message.content or "").strip()


def _is_response_format_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "response_format" in msg or ("json" in msg and "not supported" in msg)


def _strip_fences(text: str) -> str:
    """Some free models wrap JSON in ```json fences even when told not to (doc 04)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_RE.sub("", stripped).strip()
    return stripped


def _openai_client(provider: str):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The 'openai' package is required for nvidia/openrouter providers. "
            "Install it: pip install openai"
        ) from exc

    base_url, api_key, model = _OPENAI_COMPATIBLE[provider]()
    if not api_key:
        raise RuntimeError(
            f"No API key set for provider '{provider}'. "
            f"Set {provider.upper()}_API_KEY in your .env (see .env.example)."
        )
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=config.HTTP_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,  # SDK retries rate-limit/5xx with backoff
    )
    return client, model


def _anthropic_client():
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The 'anthropic' package is required for the anthropic provider. "
            "Install it: pip install anthropic"
        ) from exc

    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "No API key set for provider 'anthropic'. "
            "Set ANTHROPIC_API_KEY in your .env (see .env.example)."
        )
    client = Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        timeout=config.HTTP_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,
    )
    return client, config.ANTHROPIC_MODEL


def _complete_openai_once(client, model: str, messages: list[dict], temperature: float) -> str:
    """One attempt: prefer JSON mode, but not every free model handles it — some
    reject the param with an error, others (notably reasoning models on
    OpenRouter) return HTTP 200 with EMPTY content or a malformed envelope. Falls
    back to a plain call and leans on the "return ONLY JSON" prompt + fence
    stripping. May raise `_UpstreamEnvelopeError` (retryable by the caller)."""
    content = ""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        content = _extract_content(resp)
        if not content:
            log.warning("%s returned empty content under JSON mode; retrying without it", model)
    except Exception as exc:  # noqa: BLE001 - narrow retry on unsupported param
        if not _is_response_format_error(exc):
            raise
        log.warning("%s rejected response_format; retrying without it", model)

    if not content:
        resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
        content = _extract_content(resp)
    return _strip_fences(content)


def complete(system_prompt: str, user_content: str, provider: str | None = None,
             temperature: float = 0) -> str:
    """Run one chat completion and return the model's text with code fences
    stripped. Retries/backoff and timeout are handled here so callers stay
    provider-agnostic.

    `temperature` defaults to 0 for consistent scoring. Callers retrying after a
    malformed/degenerate response (small free models occasionally fall into a
    repetition loop at temperature=0 — a known greedy-decoding failure mode) can
    pass a small nonzero value to break the loop."""
    p = active_provider(provider)

    if p in _OPENAI_COMPATIBLE:
        client, model = _openai_client(p)
        log.info("LLM call -> %s:%s (temperature=%s)", p, model, temperature)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        # The OpenAI SDK's own retry logic only fires on HTTP-level failures.
        # Free providers sometimes wrap an upstream error in an HTTP 200 body
        # (see _UpstreamEnvelopeError) — the SDK sees that as success, so retry
        # those explicitly at this layer.
        last_exc: Exception | None = None
        for attempt in range(1, config.LLM_MAX_RETRIES + 1):
            try:
                return _complete_openai_once(client, model, messages, temperature)
            except _UpstreamEnvelopeError as exc:
                last_exc = exc
                log.warning("%s:%s upstream envelope error (attempt %d/%d): %s",
                            p, model, attempt, config.LLM_MAX_RETRIES, exc)
                if attempt < config.LLM_MAX_RETRIES:
                    time.sleep(_RETRY_BACKOFF_SECONDS)
        raise RuntimeError(
            f"{p}:{model} kept returning malformed responses after "
            f"{config.LLM_MAX_RETRIES} attempts"
        ) from last_exc

    if p == "anthropic":
        client, model = _anthropic_client()
        log.info("LLM call -> anthropic:%s", model)
        # Anthropic has no JSON-mode toggle; the paid API is reliable about
        # following the "return ONLY JSON" instruction (doc 04), so fence
        # stripping is a defensive formality here rather than a load-bearing path.
        resp = client.messages.create(
            model=model,
            max_tokens=config.ANTHROPIC_MAX_TOKENS,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
        return _strip_fences(text)

    raise ValueError(
        f"Unknown LLM_PROVIDER '{p}'. Use 'nvidia', 'openrouter', or 'anthropic' "
        "(see .env.example)."
    )
