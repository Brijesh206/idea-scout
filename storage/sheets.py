"""Google Sheets read/write — the single source of truth (docs/05-storage-sheets.md).

All Sheet access goes through this module. Authenticates with a Google Cloud
service account (JSON key) shared as editor on the target Sheet — no browser
OAuth, so the same code works unattended in GitHub Actions.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import config

log = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column order for the "Idea Candidates" tab (doc 05). The header row is created
# on first write if the tab is empty.
CANDIDATES_HEADER = [
    "date_found",
    "source",
    "title",
    "url",
    "score",
    "verdict",
    "rationale",
    "mvp_scope",
    "est_build_days",
    "model_used",
    "status",
    "candidate_id",
]

_client = None  # cached gspread client


def _credentials():
    from google.oauth2.service_account import Credentials

    # Strip a leading UTF-8 BOM (﻿) — some secret-upload paths (e.g. piping
    # through PowerShell) can prepend one, which would otherwise break the
    # startswith("{") check below and misroute a JSON blob through the
    # file-path branch (confirmed live in GitHub Actions 2026-07-12).
    raw_json = config.GOOGLE_SERVICE_ACCOUNT_JSON.lstrip("﻿").strip()
    if raw_json.startswith("{"):
        info = json.loads(raw_json)
        return Credentials.from_service_account_info(info, scopes=_SCOPES)
    path = config.GOOGLE_SERVICE_ACCOUNT_FILE or config.GOOGLE_SERVICE_ACCOUNT_JSON
    if not path:
        raise RuntimeError(
            "No Google credentials. Set GOOGLE_SERVICE_ACCOUNT_JSON (raw JSON) or "
            "GOOGLE_SERVICE_ACCOUNT_FILE (path to key file). See .env.example."
        )
    return Credentials.from_service_account_file(path, scopes=_SCOPES)


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        import gspread
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("The 'gspread' package is required. pip install gspread") from exc
    _client = gspread.authorize(_credentials())
    return _client


def _candidates_worksheet():
    if not config.GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID is not set (see .env.example).")
    sheet = _get_client().open_by_key(config.GOOGLE_SHEET_ID)
    ws = sheet.worksheet(config.SHEET_TAB_CANDIDATES)
    # Ensure a header row exists on a fresh tab. Check row 1 specifically —
    # get_all_values() returns [[]] (truthy) for an empty tab, not []. Use named
    # args: gspread 6.x swapped update()'s positional order vs 5.x.
    if not ws.row_values(1):
        ws.update(range_name="A1", values=[CANDIDATES_HEADER])
    return ws


def recent_candidate_ids(lookback_days: int | None = None) -> set[str]:
    """candidate_id values written in the last N days, for dedupe (doc 05).

    Returns an empty set (and logs) if Sheets isn't configured, so the rest of
    the pipeline can still run during local --dry-run testing without a service
    account set up yet."""
    if not config.sheets_configured():
        log.warning("Sheets not configured; skipping dedupe (no candidate history).")
        return set()

    lookback_days = lookback_days if lookback_days is not None else config.DEDUPE_LOOKBACK_DAYS
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date()

    ws = _candidates_worksheet()
    rows = ws.get_all_records()  # list of dicts keyed by header
    ids: set[str] = set()
    for row in rows:
        cid = str(row.get("candidate_id", "")).strip()
        if not cid:
            continue
        date_str = str(row.get("date_found", "")).strip()
        parsed = _parse_date(date_str)
        if parsed is None or parsed >= cutoff:
            ids.add(cid)  # keep if within window or date unparseable (fail safe)
    log.info("Dedupe: %d candidate_ids seen in last %d days", len(ids), lookback_days)
    return ids


def _parse_date(value: str):
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%m/%d/%Y"):
        try:
            return datetime.strptime(value[: len(fmt) + 6], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _to_row(scored: dict, date_found: str) -> list:
    return [
        date_found,
        scored.get("source", ""),
        scored.get("title", ""),
        scored.get("url", ""),
        scored.get("score", ""),
        scored.get("verdict", ""),
        scored.get("rationale", ""),
        scored.get("mvp_scope", ""),
        scored.get("est_build_days", ""),
        scored.get("model_used", ""),
        "new",  # status starts at new; edited by hand thereafter (doc 05)
        scored.get("id", ""),
    ]


def append_candidates(scored: list[dict]) -> int:
    """Append scored rows (caller has already filtered to score >= SHEET_THRESHOLD).
    Returns the number of rows written."""
    if not scored:
        return 0
    ws = _candidates_worksheet()
    today = datetime.now(timezone.utc).date().isoformat()
    rows = [_to_row(s, today) for s in scored]
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    log.info("Wrote %d rows to '%s'", len(rows), config.SHEET_TAB_CANDIDATES)
    return len(rows)
