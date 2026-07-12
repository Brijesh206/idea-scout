# Scoring Rubric — the actual product of this system

Everything else in this project is plumbing. This rubric is what determines
whether the digest is useful or noise. Iterate on this file more than any
other part of the codebase.

## Target bar
An idea should have a **believable path to $500+ MRR within 3 months of
launch**, built and launched solo, using FastAPI + Next.js + Supabase + Stripe,
inside ~2–3 hrs on weeknights and full weekend days.

$500+ MRR in 3 months is a real bar, not a token gesture — it implies either
~10-50 paying users at realistic indie SaaS pricing ($10-50/mo), or a smaller
number of higher-ticket customers. The rubric should actively fail ideas that
are technically interesting but have no visible path to that many paying users
that fast (e.g. things that need enterprise sales cycles, heavy compliance,
or a large pre-existing audience the candidate doesn't have evidence of).

## Batch scoring call — input
Send ~20 normalized candidates per call (see doc 01) plus this system prompt
skeleton (fill in the stack/timeframe from doc 00, keep the scoring
instructions below intact):

```
You are scoring product ideas sourced from Hacker News, Reddit, and Product
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
be encouraging.
```

## Output validation
- Parse and validate against the schema before writing to the Sheet. If the
  LLM returns malformed JSON or a missing field for an item, log it and skip
  that item rather than crashing the whole batch.
- Reject/flag any result where `score` is present but `rationale` doesn't
  reference anything from the actual source snippet — a sign the model is
  guessing rather than grounding in the input (more likely on smaller free
  models used for plumbing testing; check for this specifically when you
  swap in the free-tier model).

## Filtering into the digest
- **Digest threshold**: score >= 70 → included in Telegram digest.
- **Sheet threshold**: score >= 40 → written to the Sheet (so you can browse
  the "maybe" tier on demand via the Claude app without it clogging Telegram).
- Below 40 → discard, don't store (keeps the Sheet from growing unbounded).
- Make the digest threshold a config value (see doc 01) — you'll likely tune
  it after the first week once you see real score distributions.

## Calibration step (before going live on paid Claude API)
Run the same batch of ~20 real candidates through both the free testing model
and Claude Haiku. Compare: do scores land in a similar range? Does Haiku's
rationale reference the source material more precisely? This is the check
that catches "the pipeline runs" vs "the pipeline is actually useful" — do
not skip it before switching the cron job to the paid provider.
