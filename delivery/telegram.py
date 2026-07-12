"""Telegram digest formatting + delivery (docs/06-telegram-digest.md).

Scannable on a phone. Always sends something — even "0 above threshold" — so
silence is never ambiguous between "nothing today" and "the pipeline broke".
Also surfaces source-fetch failures explicitly.
"""
from __future__ import annotations

import logging

import requests

import config

log = logging.getLogger(__name__)

_DIGEST_LIMIT = 10  # cap the number of items listed in one message


def build_message(
    scored: list[dict],
    date_str: str,
    source_errors: list[str] | None = None,
) -> str:
    """Format the digest. `scored` is the full scored set (any score); this
    function applies the digest threshold itself so callers don't duplicate it."""
    source_errors = source_errors or []
    threshold = config.DIGEST_THRESHOLD

    above = sorted(
        [s for s in scored if s.get("score", 0) >= threshold],
        key=lambda s: s["score"],
        reverse=True,
    )

    lines: list[str] = [f"📊 Idea Scout — {date_str}", ""]

    if source_errors:
        # e.g. "⚠️ Product Hunt fetch failed this run, HN + Reddit results below."
        lines.append("⚠️ " + " ".join(source_errors))
        lines.append("")

    if not above:
        scored_count = len(scored)
        if scored_count:
            top = max(scored, key=lambda s: s.get("score", 0))
            lines.append(
                f"0 ideas above threshold ({threshold}) today — "
                f"{scored_count} candidates scored, highest was {top.get('score', 0)} "
                f"({top.get('title', '')[:60]})."
            )
        else:
            lines.append(f"0 ideas above threshold ({threshold}) today — 0 candidates scored.")
    else:
        lines.append(f"{len(above)} new idea{'s' if len(above) != 1 else ''} scored {threshold}+:")
        lines.append("")
        for i, s in enumerate(above[:_DIGEST_LIMIT], start=1):
            source = s.get("source", "")
            lines.append(f"{i}. [{s['score']}] {s.get('title', '')}")
            lines.append(f"   {s.get('rationale', '')}")
            lines.append(f"   Est. {s.get('est_build_days', '?')}d · {source}")
            lines.append(f"   {s.get('url', '')}")
            lines.append("")
        if len(above) > _DIGEST_LIMIT:
            lines.append(f"…and {len(above) - _DIGEST_LIMIT} more in the Sheet.")
            lines.append("")

    sheet_link = config.sheet_url()
    if sheet_link:
        lines.append(f'Full list + "maybe" tier: {sheet_link}')

    return "\n".join(lines).rstrip()


def send(message: str) -> None:
    """Send a plain-text message to the configured chat. Raises on API failure
    (the run should fail loudly — doc 08)."""
    if not config.telegram_configured():
        raise RuntimeError(
            "Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
            "(see .env.example)."
        )
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=config.HTTP_TIMEOUT_SECONDS,
    )
    if not resp.ok:
        raise RuntimeError(f"Telegram send failed: {resp.status_code} {resp.text}")
    log.info("Telegram digest sent (%d chars)", len(message))
