"""Dedupe incoming candidates against what's already in the Sheet (doc 05).

Drops candidates whose id was written in the last N days so the same HN post
isn't rescored and re-sent every run.
"""
from __future__ import annotations

import logging

import config
from storage import sheets

log = logging.getLogger(__name__)


def filter_new(candidates: list[dict], lookback_days: int | None = None) -> list[dict]:
    """Return only candidates not seen in the Sheet within the lookback window.

    If Sheets isn't configured, `recent_candidate_ids` returns an empty set and
    everything passes through (with a warning) — useful for local --dry-run
    testing before the service account is set up."""
    if not candidates:
        return []
    seen = sheets.recent_candidate_ids(lookback_days or config.DEDUPE_LOOKBACK_DAYS)
    if not seen:
        return candidates
    fresh = [c for c in candidates if c["id"] not in seen]
    log.info("Dedupe: %d in -> %d new (%d already seen)",
             len(candidates), len(fresh), len(candidates) - len(fresh))
    return fresh
