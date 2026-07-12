# Telegram Digest

## Setup
Create a bot via `@BotFather` in Telegram (2 minutes), get the bot token,
send it one message from your own account, then fetch `getUpdates` once to
find your `chat_id`. Both go in GitHub Actions secrets — no OAuth needed.

## When it sends
Twice a day, timed around your actual dev windows (see doc 08 for exact
cron), not at fixed clock times — the goal is a shortlist waiting for you
when a dev window opens, not an interruption during office hours.

## Format
Keep it scannable on a phone screen — this is read standing up or between
meetings, not analyzed at length:

```
📊 Idea Scout — {date}

3 new ideas scored 70+:

1. [82] {title}
   {one-line rationale}
   Est. {est_build_days}d · {source}
   {url}

2. [76] {title}
   ...

Full list + "maybe" tier: {sheet_link}
```

- If zero candidates cleared the digest threshold that run, still send a
  short message ("0 ideas above threshold today — X candidates scored,
  highest was Y") rather than silently sending nothing — silence is
  indistinguishable from "the pipeline broke," and you want to be able to
  tell the difference from your phone without opening GitHub Actions logs.
- Include a direct link to the Google Sheet in every message so the "maybe"
  tier (40-70) is one tap away when you have more time to browse.

## Failure visibility
If a source fetch or the scoring call fails entirely for a run (see doc 01
error handling), the Telegram message should say so explicitly rather than
just sending a partial/empty digest silently — e.g. "⚠️ Product Hunt fetch
failed this run, HN + Reddit results below." You're checking this from your
phone during office hours; a failure you can't see from there is a failure
you can't act on until much later.
