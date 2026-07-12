# Idea Scout — Project Overview

## What this is
An automated pipeline that finds product ideas from Hacker News, Reddit, and
Product Hunt, scores them against a specific profitability bar, and delivers
a short daily digest to Telegram (and a Google Sheet you can query anytime).
A second, separate workflow finds Reddit threads worth engaging in and drafts
(but never posts) a reply for manual review.

This is a scheduled batch job, not a long-running service. It runs on a cron
schedule via GitHub Actions — free, no server to maintain, no SSH keys to lose.

## Why this architecture (read before changing it)
- **Not built inside Claude Code / Claude.ai.** Claude Code's 5-hour session
  window and message caps are for interactive coding, not for something that
  must run unattended twice a day. This pipeline calls the LLM API directly
  (metered separately, pay-per-token), completely decoupled from your Pro plan.
- **Not n8n.** You're a backend dev — a Python codebase you can run, test, and
  debug locally in Claude Code is a tighter loop than editing a visual canvas
  and re-importing JSON.
- **Not a persistent server.** The job runs twice a day for a few minutes.
  GitHub Actions cron covers that for free with zero maintenance.
- **Provider-agnostic LLM calls.** Built and debugged against free-tier models
  (OpenRouter free models, NVIDIA Build API — e.g. Llama 3.3 70B) so testing
  costs nothing. Production scoring runs on Claude Haiku via the real Anthropic
  API once the rubric is calibrated. One config value switches providers.

## Your constraints, restated (design against these)
- Stack for anything this pipeline recommends building: **FastAPI (backend) +
  Next.js (frontend) + Supabase (database) + Stripe (payments)**.
- Target bar: an idea should have a believable path to **$500+ MRR within 3
  months** of launch, buildable solo.
- Dev time available: ~2–3 hrs on weeknights (variable start time, 8:30–11:30
  PM or 9 PM–12 AM), full days on weekends (~10 AM–6/7 PM).
- Delivery: Telegram digest (passive, readable during office hours) +
  queryable via the Claude mobile app against the same Google Sheet.
- No Notion (out of credits) — Google Sheets is the source of truth.
- Twitter/X excluded from scope. Reddit + HN + Product Hunt only.
- No auto-posting, anywhere, ever. Every engagement reply is drafted for your
  manual review and manual posting.

## Sub-documents
1. `01-architecture.md` — system diagram, data flow, module boundaries
2. `02-sources.md` — HN, Reddit, Product Hunt ingestion specs
3. `03-scoring-rubric.md` — the exact scoring prompt/rubric and output schema
4. `04-llm-provider-interface.md` — provider-agnostic LLM client spec
5. `05-storage-sheets.md` — Google Sheet schema and access setup
6. `06-telegram-digest.md` — digest format and delivery logic
7. `07-engagement-finder.md` — thread discovery + reply drafting workflow
8. `08-deployment-github-actions.md` — cron schedule, secrets, workflow YAML spec
9. `09-setup-checklist.md` — every account/key you need before Claude Code can build this

## Build order (recommended)
Build and test each slice end-to-end before adding the next source — don't
build all three ingestion sources before you've seen one full pipeline run.

1. HN ingestion → scoring (on free model) → Sheet write → Telegram send
2. Add Reddit ingestion into the same scoring/delivery pipeline
3. Add Product Hunt ingestion
4. Switch scoring provider to Claude Haiku, run a calibration pass, compare
   scores against the free-model run on the same batch
5. Build the engagement finder as a separate, second workflow
6. Wire up GitHub Actions cron for both workflows
