"""Hacker News ingestion via the Algolia HN Search API (no auth required).

See docs/02-sources.md. Returns the normalized candidate shape shared by all
sources:
    {id, source, title, url, snippet, signal_score, raw_signal, created_at}
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

import config

log = logging.getLogger(__name__)

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
POINTS_NORMALIZER = 200  # signal_score = min(points / 200, 1.0)  (doc 02)
SNIPPET_MAX = 300


def _normalize(hit: dict) -> dict | None:
    """Map a raw Algolia hit to the normalized candidate shape. Returns None
    for hits we can't build a usable candidate from."""
    object_id = hit.get("objectID")
    title = hit.get("title") or hit.get("story_title")
    if not object_id or not title:
        return None

    points = hit.get("points") or 0
    num_comments = hit.get("num_comments") or 0

    # HN discussion URL is the stable canonical link; story url may be external/absent.
    hn_url = f"https://news.ycombinator.com/item?id={object_id}"
    url = hit.get("url") or hn_url

    # snippet: prefer the post's own text (story_text / comment_text), fall back to title.
    raw_text = hit.get("story_text") or hit.get("comment_text") or ""
    snippet = _strip_and_truncate(raw_text) or title

    created_i = hit.get("created_at_i")
    if created_i is not None:
        created_at = datetime.fromtimestamp(created_i, tz=timezone.utc).isoformat()
    else:
        created_at = hit.get("created_at") or ""

    return {
        "id": f"hn_{object_id}",
        "source": "hn",
        "title": title,
        "url": url,
        "snippet": snippet,
        "signal_score": min(points / POINTS_NORMALIZER, 1.0),
        "raw_signal": {
            "points": points,
            "num_comments": num_comments,
            "hn_url": hn_url,
        },
        "created_at": created_at,
    }


def _strip_and_truncate(text: str) -> str:
    if not text:
        return ""
    # Algolia returns HTML entities / tags in *_text fields; do a light strip.
    import html
    import re

    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > SNIPPET_MAX:
        text = text[:SNIPPET_MAX].rstrip() + "…"
    return text


def _query(params: dict) -> list[dict]:
    resp = requests.get(SEARCH_URL, params=params, timeout=config.HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json().get("hits", [])


def fetch(lookback_hours: int | None = None, hits_per_page: int = 50) -> list[dict]:
    """Fetch recent HN candidates: 'Show HN' launches first, then front-page
    stories, deduped by objectID. Raises on network/API failure so the caller
    can record this source as failed (see doc 01 error handling)."""
    lookback_hours = lookback_hours or config.HN_LOOKBACK_HOURS
    since = int(time.time()) - lookback_hours * 3600
    numeric_filter = f"created_at_i>{since}"

    # 1. Show HN posts — skew indie-built / revenue-curious (doc 02).
    show_hn = _query(
        {
            "tags": "show_hn",
            "numericFilters": numeric_filter,
            "hitsPerPage": hits_per_page,
        }
    )
    # 2. Front-page discussion stories, sorted by points, to catch pain-point threads.
    stories = _query(
        {
            "tags": "story",
            "numericFilters": f"{numeric_filter},points>20",
            "hitsPerPage": hits_per_page,
        }
    )

    candidates: dict[str, dict] = {}
    for hit in show_hn + stories:
        norm = _normalize(hit)
        if norm is not None:
            candidates.setdefault(norm["id"], norm)  # first occurrence wins (Show HN)

    log.info(
        "HN: %d Show HN + %d stories -> %d unique candidates",
        len(show_hn),
        len(stories),
        len(candidates),
    )
    return list(candidates.values())
