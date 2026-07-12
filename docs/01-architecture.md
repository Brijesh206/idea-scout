# Architecture

## Two independent workflows, same building blocks

### Workflow A — Idea Discovery (runs 2x/day: morning + evening)
```
[HN Algolia API]  \
[Reddit RSS feeds] -> ingest.py -> dedupe (vs Sheet history) -> scoring.py (LLM)
[Product Hunt API]/                                                   |
                                                                       v
                                                     Google Sheet ("Idea Candidates")
                                                                       |
                                                          filter (score >= threshold)
                                                                       |
                                                                       v
                                                              Telegram digest
```

### Workflow B — Engagement Finder (runs 1x/day)
```
[Reddit RSS: keyword-matched threads] -> engagement.py (LLM drafts reply)
                                                |
                                                v
                              Google Sheet ("Engagement Queue", status=pending)
                                                |
                                                v
                                       Telegram notification
                                                |
                                    (you review, edit, post manually)
```

## Module boundaries
Design as separate, independently testable modules — not one script. This
matters because Claude Code will build/debug these one at a time, and each
has a different failure mode:

- `sources/` — one file per source (hackernews.py, reddit.py, producthunt.py).
  Each exposes a single function returning a normalized list of dicts:
  `{id, source, title, url, snippet, signal_score, created_at}`.
  `signal_score` is source-specific (HN points, Reddit upvotes, PH votes) —
  normalize it to a 0–1 scale per source so scoring can weigh it consistently.
- `llm/` — provider-agnostic client (see doc 04). Nothing else in the codebase
  should import an SDK directly; everything calls through this module.
- `scoring.py` — takes normalized candidates, calls the LLM in batches, parses
  and validates the JSON response, returns scored results.
- `dedupe.py` — checks incoming candidate IDs/URLs against what's already in
  the Sheet (last N days) so the same HN post or Reddit thread isn't rescored
  and re-sent every run.
- `storage/sheets.py` — all Google Sheets read/write goes through here.
- `delivery/telegram.py` — formats and sends the digest message.
- `engagement.py` — separate from scoring.py; different rubric, different
  Sheet tab, different Telegram message format.
- `main_discovery.py` / `main_engagement.py` — thin orchestrators, one per
  GitHub Actions workflow. Each should be runnable standalone from the CLI
  with a `--dry-run` flag that skips the Sheet write and Telegram send and
  just prints results — this is what you'll use for local testing in Claude
  Code before trusting it to run unattended.

## Config, not code, for anything you'll want to tune
Put these in environment variables / a config file, not hardcoded, since
you'll adjust them after seeing real results:
- Score threshold for "make the digest" (start at 70/100 — see doc 03)
- Subreddit list, PH categories
- LLM provider + model name (see doc 04)
- Batch size for scoring calls (start at 20 items/call)
- Lookback window for dedupe (e.g. 14 days)

## Error handling expectations
Each source fetch should fail independently — if Product Hunt's API is down,
HN and Reddit results should still make it into the digest, with a note that
one source failed. Don't let one source's exception kill the whole run.
