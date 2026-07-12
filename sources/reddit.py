"""Reddit ingestion via public per-subreddit Atom/RSS feeds.

DEVIATION FROM doc 02 (flagged, not silent): doc 02 specifies the `.json`
listing endpoint. As of testing (2026-07-12), Reddit returns HTTP 403 on every
`.json` path (subreddit listings AND individual posts) — confirmed both in the
dev sandbox and on a home network, so this is Reddit's current anti-bot policy,
not an IP-reputation fluke. Only the Atom feed at `/r/{sub}/new/.rss` is
reachable without OAuth.

Trade-off: the Atom feed gives title/body/permalink/author/timestamp but NOT
upvote or comment counts, so doc 02's exact signal_score formula
`(ups + comments*2) / 100` can't be computed from real data. signal_score is
set to a neutral 0.5 for every Reddit candidate instead (raw_signal notes why).
This still meets doc 02's real goal — no OAuth app registration — since the
rubric's actual judgment comes from reading title/snippet text against the
demand-evidence criteria; signal_score is supplementary context, not a gate.
If Reddit's vote signal turns out to matter, registering an official OAuth
"script" app is the upgrade path (bigger lift, not done here).
"""
from __future__ import annotations

import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

import config

log = logging.getLogger(__name__)

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
NEUTRAL_SIGNAL_SCORE = 0.5  # no vote/comment data available via RSS (see module docstring)
SNIPPET_MAX = 300
MIN_TITLE_LEN = 15  # below this + no selftext, treat as too thin to score

_IMAGE_EXT_RE = re.compile(r"\.(jpg|jpeg|png|gif|gifv|webp|mp4)(?:\?.*)?$", re.IGNORECASE)
# Reddit wraps self-text between these HTML comment markers in the Atom <content>.
_SELFTEXT_RE = re.compile(r"<!--\s*SC_OFF\s*-->(.*?)<!--\s*SC_ON\s*-->", re.DOTALL)
_LINK_HREF_RE = re.compile(r'<a href="([^"]+)">\s*\[link\]\s*</a>', re.IGNORECASE)
_COMMENTS_HREF_RE = re.compile(r'<a href="([^"]+)">\s*\[comments\]\s*</a>', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()


def _clean(text: str) -> str:
    if not text:
        return ""
    return html.unescape(text).strip()


def _truncate(text: str) -> str:
    if len(text) > SNIPPET_MAX:
        return text[:SNIPPET_MAX].rstrip() + "…"
    return text


def _extract_selftext(content_html: str) -> str:
    m = _SELFTEXT_RE.search(content_html)
    if not m:
        return ""
    return _clean(_strip_tags(m.group(1)))


def _extract_urls(content_html: str, fallback_permalink: str) -> str:
    """Prefer the external '[link]' target when it differs from the discussion
    permalink (i.e. this is a link post, not a self post)."""
    link_m = _LINK_HREF_RE.search(content_html)
    comments_m = _COMMENTS_HREF_RE.search(content_html)
    comments_url = html.unescape(comments_m.group(1)) if comments_m else fallback_permalink
    if link_m:
        link_url = html.unescape(link_m.group(1))
        if link_url and link_url != comments_url:
            return link_url
    return comments_url


def _text(entry: ET.Element, tag: str) -> str:
    el = entry.find(f"atom:{tag}", ATOM_NS)
    return el.text if el is not None and el.text else ""


def _is_noise(title: str, selftext: str, url: str) -> bool:
    if selftext.strip() in ("[removed]", "[deleted]"):
        return True
    if _IMAGE_EXT_RE.search(url or ""):
        return True
    if len(title.strip()) < MIN_TITLE_LEN and not selftext.strip():
        return True
    return False


def _normalize(entry: ET.Element, subreddit: str) -> dict | None:
    raw_id = _text(entry, "id")  # e.g. "t3_1uubbur"
    post_id = raw_id.split("_", 1)[-1] if raw_id else None
    title = _clean(_text(entry, "title"))
    if not post_id or not title:
        return None

    link_el = entry.find("atom:link", ATOM_NS)
    permalink = link_el.get("href") if link_el is not None else f"https://www.reddit.com/comments/{post_id}/"

    content_html = _text(entry, "content")
    selftext = _extract_selftext(content_html)
    url = _extract_urls(content_html, permalink)

    if _is_noise(title, selftext, url):
        return None

    snippet = _truncate(selftext) if selftext else title
    published = _text(entry, "published")
    try:
        created_at = datetime.fromisoformat(published).astimezone(timezone.utc).isoformat() if published else ""
    except ValueError:
        created_at = published

    return {
        "id": f"reddit_{post_id}",
        "source": "reddit",
        "title": title,
        "url": url,
        "snippet": snippet,
        "signal_score": NEUTRAL_SIGNAL_SCORE,
        "raw_signal": {
            "ups": None,
            "num_comments": None,
            "note": "vote/comment counts unavailable (Reddit blocks the JSON API; RSS doesn't expose them)",
            "permalink": permalink,
            "subreddit": subreddit,
        },
        "created_at": created_at,
    }


def _fetch_subreddit(subreddit: str, limit: int) -> list[ET.Element]:
    url = f"https://www.reddit.com/r/{subreddit}/new/.rss"
    resp = requests.get(
        url,
        params={"limit": limit},
        headers={"User-Agent": config.REDDIT_USER_AGENT},
        timeout=config.HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    return root.findall("atom:entry", ATOM_NS)


def fetch(subreddits: list[str] | None = None, limit: int | None = None) -> list[dict]:
    """Fetch recent posts across the configured subreddit list. A single
    subreddit failing is logged and skipped; only raises if every subreddit
    fails, so the caller can record Reddit as a failed source (doc 01)."""
    subreddits = subreddits or config.REDDIT_SUBREDDITS
    limit = limit or config.REDDIT_POSTS_PER_SUBREDDIT

    candidates: dict[str, dict] = {}
    failures = 0
    for i, sub in enumerate(subreddits):
        if i > 0:
            time.sleep(config.REDDIT_REQUEST_DELAY_SECONDS)  # avoid per-IP rate limiting
        try:
            entries = _fetch_subreddit(sub, limit)
        except Exception as exc:  # noqa: BLE001 - isolate per-subreddit failures
            log.warning("Reddit r/%s failed: %s", sub, exc)
            failures += 1
            continue
        kept = 0
        for entry in entries:
            norm = _normalize(entry, sub)
            if norm is not None:
                candidates[norm["id"]] = norm
                kept += 1
        log.info("Reddit r/%s: %d entries -> %d kept", sub, len(entries), kept)

    if failures == len(subreddits):
        raise RuntimeError(f"All {len(subreddits)} configured subreddits failed to fetch")

    return list(candidates.values())
