# Idea Scout

Automated pipeline that finds product ideas from Hacker News (later: Reddit,
Product Hunt), scores them against a $500+ MRR-in-3-months bar with an LLM,
writes the results to a Google Sheet, and sends a short digest to Telegram.

See [`docs/`](docs/) for the full spec. This repo is being built **one slice at
a time** (see `docs/00-overview.md`).

## Current status — Slice 1

**HN ingestion → LLM scoring → Google Sheet write → Telegram digest.**

Reddit, Product Hunt, the Anthropic/Claude scoring provider, the engagement
finder, and GitHub Actions cron are **not built yet** — they're later slices.

```
sources/hackernews.py   HN ingestion (Algolia API, no auth)
llm/                    provider-agnostic LLM client (NVIDIA + OpenRouter)
scoring.py              rubric prompt, batching, JSON validation
dedupe.py               drop candidates already in the Sheet
storage/sheets.py       Google Sheets read/write (service account)
delivery/telegram.py    digest formatting + send
main_discovery.py       orchestrator (supports --dry-run)
config.py               all env-driven configuration
```

## Setup

### 1. Python & dependencies (Python 3.12)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # macOS/Linux
pip install -r requirements.txt
```

### 2. Create your `.env`

```powershell
copy .env.example .env              # Windows
# cp .env.example .env              # macOS/Linux
```

Then fill it in. `.env` is gitignored — never commit real keys.

**Minimum needed for a first `--dry-run`:** just an LLM provider + key. The
Sheet and Telegram are only touched on a live (non-dry) run, and dedupe skips
itself with a warning if Sheets isn't configured yet — so you can test
HN → scoring with nothing but an NVIDIA or OpenRouter key.

| Variable | Where to get it |
|---|---|
| `LLM_PROVIDER` | `nvidia` or `openrouter` |
| `NVIDIA_API_KEY` | https://build.nvidia.com (free tier) |
| `OPENROUTER_API_KEY` | https://openrouter.ai (free tier) |
| `OPENROUTER_MODEL` | a current `:free` model (the free lineup rotates) |
| `GOOGLE_SHEET_ID` | the `/d/<ID>/` part of your Sheet URL |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | path to your service-account JSON key |
| `TELEGRAM_BOT_TOKEN` | from `@BotFather` |
| `TELEGRAM_CHAT_ID` | see below |

### 3. Google Sheet (only for live runs)

1. Create a Google Cloud project, enable the **Google Sheets API**, create a
   **service account**, and download its JSON key. Put the file path in
   `GOOGLE_SERVICE_ACCOUNT_FILE` (or paste the raw JSON into
   `GOOGLE_SERVICE_ACCOUNT_JSON`).
2. Create a Google Sheet with a tab named **`Idea Candidates`**. (The header row
   is created automatically on first write if the tab is empty.)
3. **Share the Sheet as Editor** with the service account's email
   (`...@...iam.gserviceaccount.com`), or it can't write.
4. Put the Sheet ID in `GOOGLE_SHEET_ID`.

### 4. Telegram bot (only for live runs)

1. Message `@BotFather`, `/newbot`, copy the token → `TELEGRAM_BOT_TOKEN`.
2. Send your new bot any message from your own account.
3. Fetch your chat id:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
   Find `"chat":{"id":<number>}` → that number is `TELEGRAM_CHAT_ID`.

## Run

**Dry run** — full pipeline, but skips the Sheet write and Telegram send and
prints everything to stdout. This is what you use for local testing:

```powershell
python main_discovery.py --dry-run
python main_discovery.py --dry-run -v      # with debug logging
```

**Live run** — writes candidates (score ≥ 40) to the Sheet and sends the digest:

```powershell
python main_discovery.py
```

## How scoring works (short version)

- Every HN candidate is scored 0–100 by the LLM against the rubric in
  `docs/03-scoring-rubric.md` (system prompt used verbatim).
- **score ≥ 70** → included in the Telegram digest.
- **score ≥ 40** → written to the Sheet (the browsable "maybe" tier).
- **below 40** → discarded, not stored.

Tune thresholds and batch size via env vars (see `.env.example` / `config.py`).

## Maintenance note

Sheets performance degrades on very large sheets. With the score≥40 discard
threshold and dedupe in place growth is modest, but periodically archive/clear
`Idea Candidates` rows older than ~90 days.

## Not in this slice

Reddit • Product Hunt • Anthropic/Claude scoring provider • engagement finder •
GitHub Actions cron. These come in later slices per `docs/00-overview.md`.
