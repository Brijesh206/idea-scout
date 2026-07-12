# Storage — Google Sheets

Replaces Notion (not currently usable — out of credits). Free, and both the
Telegram digest and on-demand queries from the Claude mobile app can read
from the same sheet, so there's one source of truth.

## Access method
Use a **Google Cloud service account** with a JSON key, shared as an editor
on the target Sheet — not OAuth user-login flow. This is what lets the
GitHub Actions cron job write to the Sheet unattended, with no browser login
step. Store the service account JSON as a GitHub Actions secret.

## Tab 1: `Idea Candidates`
| Column | Type | Notes |
|---|---|---|
| date_found | date | |
| source | text | hn / reddit / ph |
| title | text | |
| url | text | |
| score | int | 0-100 |
| verdict | text | strong / maybe / pass |
| rationale | text | |
| mvp_scope | text | |
| est_build_days | int | |
| model_used | text | which LLM scored it — see doc 04 |
| status | text | new / reviewed / building / shipped / discarded — you update this manually |
| candidate_id | text | source-prefixed unique id, used for dedupe |

- Only rows scoring >= 40 get written (see doc 03 for threshold reasoning).
- `status` starts at `new` and is the one column you edit by hand as you
  actually review and act on ideas — this turns the sheet into a lightweight
  personal Kanban, not just a log.

## Tab 2: `Engagement Queue`
| Column | Type | Notes |
|---|---|---|
| date_found | date | |
| subreddit | text | |
| thread_title | text | |
| thread_url | text | |
| drafted_reply | text | |
| status | text | pending / approved / posted / skipped — you update manually |

## Dedupe logic
Before scoring a new batch, read `candidate_id` values from the last 14 days
in `Idea Candidates` (config value, see doc 01) and drop anything already
present — prevents the same HN post or Reddit thread being rescored and
resent across multiple runs.

## Sheet growth / maintenance
At the discard threshold in doc 03 (score < 40 not stored), and with dedupe
in place, growth should be modest — but add a manual note in the README to
archive/clear rows older than ~90 days periodically, since Sheets performance
degrades on very large sheets and this isn't worth automating for the volume
involved.
