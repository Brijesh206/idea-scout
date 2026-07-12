# LLM Provider Interface

## Goal
Swap between free testing models and the paid Claude API by changing config,
not code. Nothing outside this module should know which provider is active.

## Providers to support
1. **NVIDIA Build API** — OpenAI-compatible endpoint, free tier.
   Base URL: `https://integrate.api.nvidia.com/v1`
   Suggested free model: `meta/llama-3.3-70b-instruct` (best free-tier
   reasoning quality available there — closer to Haiku's rubric-following
   than smaller free models).
2. **OpenRouter free tier** — OpenAI-compatible endpoint.
   Base URL: `https://openrouter.ai/api/v1`
   Use one of OpenRouter's `:free` suffixed models as a second free option
   (check current availability at build time — free model lineup rotates).
3. **Anthropic Claude API** (production) — native Anthropic SDK, not
   OpenAI-compatible. Model: `claude-haiku-4-5`.

## Interface shape
A single function, regardless of provider:
```
score_candidates(candidates: list[dict], provider: str) -> list[dict]
draft_reply(thread: dict, provider: str) -> str
```
`provider` is read from an environment variable (`LLM_PROVIDER=nvidia` /
`openrouter` / `anthropic`) with per-provider API key and model name also
in env vars. The two OpenAI-compatible providers (NVIDIA, OpenRouter) can
share one implementation since they speak the same API shape — only base URL,
API key, and model name differ. Anthropic needs its own implementation since
it's a different SDK/request format.

## Why this matters for your workflow specifically
- Local testing/debugging in Claude Code: set `LLM_PROVIDER=nvidia` (or
  `openrouter`), zero cost, iterate freely on prompts and parsing logic.
- Calibration pass (see doc 03): temporarily run the same batch through
  `LLM_PROVIDER=anthropic` to compare, small one-off spend.
- Production cron job: `LLM_PROVIDER=anthropic` set as a GitHub Actions
  secret/env var, only real spend is the scheduled runs.

## Things to handle regardless of provider
- Retries with backoff on rate-limit/5xx errors (free tiers are more prone
  to throttling than the paid API — this matters more during testing than
  production).
- Timeout per request — don't let one slow batch hang the whole run.
- Strip markdown code fences (```json) from responses before parsing — some
  models wrap JSON output in them even when told not to; the paid Claude API
  is more reliable about following the "return only JSON" instruction than
  most free models, so this defensive parsing matters more during testing.
- Log which provider/model produced each scored result (a column in the
  Sheet) — useful for spotting quality differences later.
