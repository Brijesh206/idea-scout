"""Scoring — the actual product of this system (see docs/03-scoring-rubric.md).

Takes normalized candidates, calls the LLM in batches through the provider-
agnostic llm module, parses and validates the JSON response, and returns scored
results. Malformed items are logged and skipped rather than crashing the batch.
"""
from __future__ import annotations

import json
import logging
import re

import config
import llm

log = logging.getLogger(__name__)

# System prompt skeleton from docs/03-scoring-rubric.md, used verbatim (stack and
# timeframe are already filled in per doc 00). Do not rewrite the scoring
# instructions — iterate on the rubric doc, then mirror changes here.
SYSTEM_PROMPT = """You are scoring product ideas sourced from Hacker News, Reddit, and Product
Hunt for a solo indie developer. Stack: FastAPI backend, Next.js frontend,
Supabase database, Stripe payments. Available time: ~2-3 hrs on weeknights,
full days on weekends. Goal: $500+ MRR within 3 months of launch.

For each candidate below, score strictly against these criteria:
1. EVIDENCE OF DEMAND: does the source material show real people describing
   a real, current pain point or willingness to pay — not just "interesting
   idea," but someone saying "I would pay for this" or describing active
   workaround pain.
2. BUILDABLE SOLO, FAST: could a solo dev ship a defensible MVP on this stack
   within roughly 2-4 weeks at the stated time budget?
3. MONETIZATION IS OBVIOUS: is there a clear, standard SaaS pricing model
   (subscription, usage-based) rather than requiring a novel business model,
   enterprise sales, or marketplace liquidity to work?
4. COMPETITIVE REALITY: if strong incumbents already dominate this exact
   niche, score down hard unless there's a specific, stated wedge.
5. $500+ MRR IN 3 MONTHS IS PLAUSIBLE: given realistic indie pricing and
   realistic solo-founder distribution (not viral assumptions), could this
   plausibly reach $500 MRR in 3 months? Be skeptical by default.

Return ONLY valid JSON, no prose, in this exact shape:
{"results": [
  {
    "id": "<candidate id, unchanged>",
    "score": <integer 0-100>,
    "verdict": "<strong|maybe|pass>",
    "rationale": "<max 2 sentences, cite the specific evidence from the source>",
    "mvp_scope": "<max 2 sentences, concrete build scope on the given stack>",
    "est_build_days": <integer>
  },
  ...
]}

Score honestly. Most candidates should score below 50 — this is by design,
most sourced content is not a viable product idea. Do not inflate scores to
be encouraging."""

_REQUIRED_FIELDS = ("id", "score", "verdict", "rationale", "mvp_scope", "est_build_days")
_VALID_VERDICTS = {"strong", "maybe", "pass"}
_WORD_RE = re.compile(r"[a-z0-9]+")
# very common tokens that don't prove the rationale is grounded in the source
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "have", "would", "could", "your",
    "you", "are", "not", "but", "from", "app", "tool", "idea", "product", "users",
    "user", "saas", "build", "building", "make", "solo", "market", "into", "some",
}


def _batches(items: list[dict], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _candidate_payload(candidates: list[dict]) -> str:
    """Only fields the model needs to score — no raw HTML/full threads (doc 02)."""
    slim = [
        {
            "id": c["id"],
            "source": c["source"],
            "title": c["title"],
            "url": c["url"],
            "snippet": c["snippet"],
            "signal_score": round(c.get("signal_score", 0.0), 3),
            "raw_signal": c.get("raw_signal", {}),
        }
        for c in candidates
    ]
    return "Candidates to score:\n" + json.dumps(slim, ensure_ascii=False, indent=2)


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 3} - _STOPWORDS


def _is_grounded(rationale: str, candidate: dict) -> bool:
    """Heuristic guard (doc 03): does the rationale reference the actual source
    material? Flags likely-hallucinated results from smaller free models."""
    source_tokens = _tokens(candidate.get("title", "")) | _tokens(candidate.get("snippet", ""))
    rationale_tokens = _tokens(rationale)
    if not source_tokens or not rationale_tokens:
        return True  # nothing to compare against; don't penalize
    return bool(source_tokens & rationale_tokens)


def _validate_item(item: dict, by_id: dict[str, dict]) -> dict | None:
    if not isinstance(item, dict):
        return None
    missing = [f for f in _REQUIRED_FIELDS if f not in item]
    if missing:
        log.warning("Scored item missing fields %s; skipping: %r", missing, item)
        return None

    cid = item["id"]
    candidate = by_id.get(cid)
    if candidate is None:
        log.warning("Scored item id %r not in this batch; skipping", cid)
        return None

    try:
        score = int(item["score"])
        est_build_days = int(item["est_build_days"])
    except (TypeError, ValueError):
        log.warning("Non-integer score/est_build_days for %r; skipping", cid)
        return None

    verdict = str(item["verdict"]).strip().lower()
    if verdict not in _VALID_VERDICTS:
        log.warning("Invalid verdict %r for %r; skipping", verdict, cid)
        return None

    score = max(0, min(100, score))
    rationale = str(item["rationale"]).strip()
    grounded = _is_grounded(rationale, candidate)
    if not grounded:
        log.warning(
            "Rationale for %r does not reference the source snippet (possible "
            "hallucination): %r",
            cid,
            rationale,
        )

    # Merge model output onto the normalized candidate so downstream (sheets,
    # telegram) has everything it needs in one dict.
    return {
        **candidate,
        "score": score,
        "verdict": verdict,
        "rationale": rationale,
        "mvp_scope": str(item["mvp_scope"]).strip(),
        "est_build_days": est_build_days,
        "grounded": grounded,
        "model_used": llm.model_label(),
    }


_MAX_PARSE_ATTEMPTS = 2  # free models occasionally return garbage/non-JSON (doc 04); retry once
# Temperature per retry attempt. Small/free models sometimes fall into a
# repetition loop at temperature=0 (greedy decoding gets stuck) and repeat it
# deterministically on a naive retry; a touch of randomness breaks the loop.
_RETRY_TEMPERATURES = [0, 0.4]


def _call_and_parse(candidates: list[dict], temperature: float) -> list | None:
    """One LLM call + JSON parse attempt. Returns the 'results' list, or None
    (logged) if the response wasn't usable JSON."""
    raw = llm.complete(SYSTEM_PROMPT, _candidate_payload(candidates), temperature=temperature)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.error("LLM returned non-JSON for a batch of %d.\n%s", len(candidates), raw[:500])
        return None

    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(results, list):
        log.error("LLM JSON missing 'results' list. Got: %s", str(parsed)[:300])
        return None
    return results


def _score_batch(candidates: list[dict]) -> list[dict]:
    by_id = {c["id"]: c for c in candidates}

    results = None
    for attempt in range(1, _MAX_PARSE_ATTEMPTS + 1):
        temperature = _RETRY_TEMPERATURES[min(attempt - 1, len(_RETRY_TEMPERATURES) - 1)]
        results = _call_and_parse(candidates, temperature)
        if results is not None:
            break
        if attempt < _MAX_PARSE_ATTEMPTS:
            log.warning("Retrying batch of %d after unusable response (attempt %d/%d, temperature=%s)",
                        len(candidates), attempt, _MAX_PARSE_ATTEMPTS, _RETRY_TEMPERATURES[attempt])
    if results is None:
        log.error("Batch of %d unusable after %d attempts; skipping.",
                   len(candidates), _MAX_PARSE_ATTEMPTS)
        return []

    scored = []
    for item in results:
        validated = _validate_item(item, by_id)
        if validated is not None:
            scored.append(validated)
    return scored


def score_candidates(candidates: list[dict]) -> list[dict]:
    """Score all candidates in batches. Provider is chosen inside the llm module
    from LLM_PROVIDER (this function stays provider-agnostic per doc 04)."""
    if not candidates:
        return []

    scored: list[dict] = []
    batch_size = config.SCORING_BATCH_SIZE
    for i, batch in enumerate(_batches(candidates, batch_size), start=1):
        log.info("Scoring batch %d (%d candidates) via %s", i, len(batch), llm.model_label())
        try:
            scored.extend(_score_batch(batch))
        except Exception as exc:  # noqa: BLE001 - one failed batch shouldn't kill the run
            log.error("Batch %d failed to score: %s", i, exc)

    log.info("Scored %d/%d candidates successfully", len(scored), len(candidates))
    return scored
