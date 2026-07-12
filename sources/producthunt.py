"""Product Hunt ingestion via the GraphQL API (docs/02-sources.md).

Requires a free developer token (PRODUCTHUNT_API_TOKEN) — register an app at
https://www.producthunt.com/v2/oauth/applications, no user OAuth flow needed
for public data.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import requests

import config

log = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"
VOTES_NORMALIZER = 300  # signal_score = min(votes / 300, 1.0) (doc 02)
SNIPPET_MAX = 300

_QUERY = """
query TopicPosts($topic: String!, $postedAfter: DateTime!) {
  posts(topic: $topic, postedAfter: $postedAfter, order: VOTES, first: 20) {
    edges {
      node {
        id
        name
        tagline
        description
        url
        website
        votesCount
        commentsCount
        createdAt
      }
    }
  }
}
"""


def _clean(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str) -> str:
    if len(text) > SNIPPET_MAX:
        return text[:SNIPPET_MAX].rstrip() + "…"
    return text


def _strip_tracking_params(url: str) -> str:
    if not url:
        return url
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _normalize(node: dict) -> dict | None:
    post_id = node.get("id")
    name = _clean(node.get("name") or "")
    if not post_id or not name:
        return None

    votes = node.get("votesCount") or 0
    tagline = _clean(node.get("tagline") or "")
    description = _clean(node.get("description") or "")
    snippet = _truncate(f"{tagline}. {description}" if description else tagline)

    # Both 'url' and 'website' from the API are PH click-tracking redirects, not
    # raw external links (confirmed 2026-07-12) — 'url' (the PH product page,
    # e.g. /products/qlane) is the more stable, human-readable one of the two.
    # Strip the utm_* tracking params identifying our app before storing/sending.
    url = _strip_tracking_params(node.get("url") or node.get("website") or "")

    return {
        "id": f"ph_{post_id}",
        "source": "ph",
        "title": name,
        "url": url,
        "snippet": snippet,
        "signal_score": min(votes / VOTES_NORMALIZER, 1.0),
        "raw_signal": {
            "votes": votes,
            "comments": node.get("commentsCount") or 0,
        },
        "created_at": node.get("createdAt") or "",
    }


def _query_topic(topic: str, posted_after_iso: str) -> list[dict]:
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": _QUERY, "variables": {"topic": topic, "postedAfter": posted_after_iso}},
        headers={
            "Authorization": f"Bearer {config.PRODUCTHUNT_API_TOKEN}",
            "Content-Type": "application/json",
        },
        timeout=config.HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        raise RuntimeError(f"Product Hunt GraphQL error for topic '{topic}': {body['errors']}")
    edges = body.get("data", {}).get("posts", {}).get("edges", [])
    return [e["node"] for e in edges if "node" in e]


def fetch(topics: list[str] | None = None, lookback_hours: int | None = None) -> list[dict]:
    """Fetch today's posts across the configured topic list. A single topic
    failing is logged and skipped; only raises if every topic fails."""
    if not config.PRODUCTHUNT_API_TOKEN:
        raise RuntimeError(
            "PRODUCTHUNT_API_TOKEN is not set (see .env.example). Register a free "
            "app at https://www.producthunt.com/v2/oauth/applications."
        )

    topics = topics or config.PRODUCTHUNT_TOPICS
    lookback_hours = lookback_hours or config.PH_LOOKBACK_HOURS
    posted_after = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    posted_after_iso = posted_after.strftime("%Y-%m-%dT%H:%M:%SZ")

    candidates: dict[str, dict] = {}
    failures = 0
    for topic in topics:
        try:
            nodes = _query_topic(topic, posted_after_iso)
        except Exception as exc:  # noqa: BLE001 - isolate per-topic failures
            log.warning("Product Hunt topic '%s' failed: %s", topic, exc)
            failures += 1
            continue
        kept = 0
        for node in nodes:
            norm = _normalize(node)
            if norm is not None:
                candidates[norm["id"]] = norm
                kept += 1
        log.info("PH topic '%s': %d posts -> %d kept", topic, len(nodes), kept)

    if failures == len(topics):
        raise RuntimeError(f"All {len(topics)} configured PH topics failed to fetch")

    return list(candidates.values())
