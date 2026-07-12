"""Central configuration, loaded from environment variables / a local .env file.

Everything tunable lives here (see docs/01-architecture.md "Config, not code").
Same env var names are used locally (.env) and in GitHub Actions (secrets), so
scripts run identically in both places.
"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is a convenience; env vars may be injected directly (CI)
    pass


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


# --- LLM provider (see docs/04-llm-provider-interface.md) ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "nvidia").strip().lower()

# OpenAI-compatible providers share one implementation; only base URL, key, model differ.
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
# Free lineup rotates; pick a current :free model at build/test time (see doc 04).
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# Anthropic (production) — native SDK, not OpenAI-compatible.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
ANTHROPIC_MAX_TOKENS = _int("ANTHROPIC_MAX_TOKENS", 4096)

# --- Google Sheets (see docs/05-storage-sheets.md) ---
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
# Accept either raw JSON (CI secret) or a path to the key file (convenient locally).
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
SHEET_TAB_CANDIDATES = os.getenv("SHEET_TAB_CANDIDATES", "Idea Candidates")

# --- Telegram (see docs/06-telegram-digest.md) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Reddit (see docs/02-sources.md) ---
_DEFAULT_SUBREDDITS = "SaaS,microsaas,SideProject,EntrepreneurRideAlong,startups,SomebodyMakeThis,AppIdeas"
REDDIT_SUBREDDITS = [
    s.strip() for s in os.getenv("REDDIT_SUBREDDITS", _DEFAULT_SUBREDDITS).split(",") if s.strip()
]
REDDIT_POSTS_PER_SUBREDDIT = _int("REDDIT_POSTS_PER_SUBREDDIT", 25)
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "idea-scout/0.1 (personal project; contact via GitHub)")
# Reddit's anonymous RSS rate limit is ~1 request/60s, GLOBAL per IP (not
# per-subreddit) — confirmed empirically 2026-07-12 via x-ratelimit-* response
# headers. 65s gives a small safety buffer. With the 7-subreddit default list,
# Reddit ingestion alone takes ~7 minutes; size the caller's timeout accordingly
# (see .github/workflows/discovery.yml).
REDDIT_REQUEST_DELAY_SECONDS = _int("REDDIT_REQUEST_DELAY_SECONDS", 65)

# --- Product Hunt (see docs/02-sources.md) ---
PRODUCTHUNT_API_TOKEN = os.getenv("PRODUCTHUNT_API_TOKEN", "")
_DEFAULT_PH_TOPICS = "developer-tools,artificial-intelligence,saas,productivity,no-code"
PRODUCTHUNT_TOPICS = [
    t.strip() for t in os.getenv("PRODUCTHUNT_TOPICS", _DEFAULT_PH_TOPICS).split(",") if t.strip()
]
PH_LOOKBACK_HOURS = _int("PH_LOOKBACK_HOURS", 24)

# --- Tunables (see docs/01 and docs/03) ---
DIGEST_THRESHOLD = _int("DIGEST_THRESHOLD", 70)   # score >= this -> Telegram digest
SHEET_THRESHOLD = _int("SHEET_THRESHOLD", 40)     # score >= this -> written to Sheet
SCORING_BATCH_SIZE = _int("SCORING_BATCH_SIZE", 20)
DEDUPE_LOOKBACK_DAYS = _int("DEDUPE_LOOKBACK_DAYS", 14)
HN_LOOKBACK_HOURS = _int("HN_LOOKBACK_HOURS", 24)

# Request handling shared across LLM/HTTP calls
HTTP_TIMEOUT_SECONDS = _int("HTTP_TIMEOUT_SECONDS", 60)
LLM_MAX_RETRIES = _int("LLM_MAX_RETRIES", 4)


def sheet_url() -> str:
    """Link to the Google Sheet, included in every Telegram digest."""
    if not GOOGLE_SHEET_ID:
        return ""
    return f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"


def sheets_configured() -> bool:
    return bool(GOOGLE_SHEET_ID and (GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE))


def telegram_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
