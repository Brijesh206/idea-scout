# Deployment — GitHub Actions

No server. This runs as a scheduled job in your own GitHub repo (private
repo — API keys and Sheet contents shouldn't be public), using GitHub
Actions' free tier for scheduled cron jobs on a private repo at this
frequency (well within free minutes/month for a job that runs a few minutes,
twice daily).

## Two workflow files
- `.github/workflows/discovery.yml` — runs `main_discovery.py`
- `.github/workflows/engagement.yml` — runs `main_engagement.py`

Keep them separate so a failure or change in one doesn't affect the other,
and so you can trigger either manually via `workflow_dispatch` when testing
changes without waiting for the schedule.

## Schedule (cron is UTC — convert from your local time, IST = UTC+5:30)
- Discovery: twice daily, timed so a digest lands shortly before each dev
  window realistically opens — e.g. once in the early evening (before your
  8:30/9 PM start) and once mid-morning on weekends (before your ~10 AM
  start). Exact times are a config detail to nail down once you know your
  actual GitHub Actions account's timezone handling — don't hardcode a guess
  here, verify against real run timestamps in the Actions log during setup.
- Engagement: once daily, similar timing logic — before a dev window, not
  during office hours when you can't act on it from your laptop anyway
  (you can still read it on the Claude mobile app, but posting still needs
  to wait until you're at a keyboard).
- `workflow_dispatch: {}` on both, so you can manually trigger a run from
  GitHub's UI (or ask Claude Code to trigger it) while testing.

## Secrets (GitHub repo → Settings → Secrets and variables → Actions)
- `LLM_PROVIDER` (nvidia / openrouter / anthropic)
- `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` (only the
  active one is required at runtime, but fine to store all three)
- `GOOGLE_SERVICE_ACCOUNT_JSON` (see doc 05)
- `GOOGLE_SHEET_ID`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `PRODUCTHUNT_API_TOKEN`

## Workflow shape (spec, not literal YAML — have Claude Code generate the
actual file from this)
1. Checkout repo
2. Set up Python (pin a specific version, e.g. 3.12)
3. Install dependencies from `requirements.txt` (cache pip deps between runs
   to keep runs fast)
4. Run `python main_discovery.py` (or `main_engagement.py`), all secrets
   passed as env vars
5. On failure, the job should fail loudly (non-zero exit code) so GitHub
   surfaces it in the Actions tab and can optionally email you — don't
   swallow exceptions at the top level.

## Local-first development
Every script should run identically locally (via `.env` file, gitignored)
and in Actions (via injected secrets) — same env var names in both places.
This is what lets you build and debug entirely in Claude Code on your laptop
during dev windows, and only touch GitHub Actions once a slice is working
locally with `--dry-run` removed.
