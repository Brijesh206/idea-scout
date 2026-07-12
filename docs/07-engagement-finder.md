# Engagement Finder

Separate workflow from idea discovery — different goal (build presence in
communities relevant to what you're building/shipping, not source new ideas),
different rubric, different Sheet tab. **Never posts anything automatically.**
Every output is a draft sitting in `Engagement Queue` with status=`pending`
until you personally review, edit if needed, and post it yourself.

## Thread discovery
Pull recent threads (RSS, same method as doc 02) from a configurable list of
subreddits — start with the same list used for idea discovery plus any
subreddit specific to whatever you've actually shipped/are building, since
this list will shift over time as your active products change (unlike the
idea-discovery subreddit list, which should stay fairly stable).

Filter to threads matching either:
- Keyword match against terms relevant to your current shipped
  product(s)/niche (config list, you maintain it)
- Threads that are *questions or pain-point descriptions* rather than
  announcements/promotions — engaging on someone else's launch post reads as
  self-promotion; engaging on a genuine question reads as helpful.

## Reply drafting
LLM prompt should optimize for **genuinely useful, non-salesy** replies:
```
Draft a short Reddit reply to this thread. Rules:
- Answer or add value to what they actually asked/described first.
- Only mention a product/tool if it's directly relevant, and mention it
  briefly, factually, without a pitch tone.
- No emoji, no "Check out my product!", no link unless directly asked.
- Sound like a developer replying casually, not a marketer.
- 2-4 sentences max.
```
- Keep drafts short — long AI-sounding replies are themselves a signal that
  gets communities suspicious; brevity is part of what makes it read as human.
- Write the thread URL and drafted text to `Engagement Queue`
  (see doc 05) with status=`pending`.

## Delivery
Simple Telegram notification listing new pending items with links — you
open the Sheet, read/edit the draft, and post manually from your own Reddit
account, in your own time. No "approve" button or automation shortcut here
by design — the manual step is a deliberate safeguard, not a gap to close
later. Reddit specifically penalizes accounts that read as automated, and a
human posting a human-sounding, manually-reviewed reply is the actual point.

## What this explicitly does not do
- Does not track karma, does not auto-schedule posting times, does not
  attempt to game visibility. Keep scope narrow: find relevant threads,
  draft a genuinely useful reply, stop.
