# Sources — Ingestion Specs

All three return the normalized shape:
```
{
  "id": str,            # stable unique id (source-prefixed, e.g. "hn_38291023")
  "source": str,        # "hn" | "reddit" | "ph"
  "title": str,
  "url": str,
  "snippet": str,       # comment text / self-text / tagline, truncated ~300 chars
  "signal_score": float,# normalized 0-1 within this source's own scale
  "raw_signal": dict,   # points/upvotes/comments/votes, kept for display only
  "created_at": str     # ISO 8601
}
```

## 1. Hacker News (no auth required)
Use the **Algolia HN Search API**: `https://hn.algolia.com/api/v1/search_by_date`

- Query for `Show HN` posts specifically first — these skew toward indie-built,
  revenue-curious projects rather than general tech news:
  `tags=show_hn&numericFilters=created_at_i>{unix_timestamp_24h_ago}`
- Also pull front-page discussion posts as a secondary query
  (`tags=story`, sorted by points) to catch demand/pain-point discussions,
  not just launches.
- `signal_score`: normalize `points` — e.g. `min(points / 200, 1.0)`.
- Respect the API's rate limits; this endpoint is generous for this volume
  (a few requests/day), no special handling needed.

## 2. Reddit (RSS feeds — no OAuth needed)
Use each subreddit's public RSS/JSON feed rather than the full Reddit API —
avoids OAuth app registration entirely for a read-only, low-volume use case:
`https://www.reddit.com/r/{subreddit}/new.json?limit=25`
(set a descriptive `User-Agent` header — Reddit blocks default/empty ones)

Starter subreddit list (tune after a few weeks of real results):
`SaaS, microsaas, SideProject, EntrepreneurRideAlong, startups, SomebodyMakeThis, AppIdeas`

- `signal_score`: normalize using `ups` and `num_comments` combined, e.g.
  `min((ups + num_comments*2) / 100, 1.0)` — comments weighted higher since
  they indicate discussion/validation, not just passive agreement.
- Filter out obvious noise before it reaches the LLM: posts under a minimum
  length, removed/deleted posts, pure meme/image posts.

## 3. Product Hunt (GraphQL API — requires a free developer token)
`https://api.producthunt.com/v2/api/graphql`
- Query today's posts filtered by topic slug. Starter categories:
  `developer-tools, artificial-intelligence, saas, productivity, no-code`
  (closest fit to the FastAPI/Next.js/Supabase/Stripe stack)
- `snippet` = tagline + first ~200 chars of description.
- `signal_score`: normalize `votesCount`, e.g. `min(votes / 300, 1.0)`.
- Token setup: register a PH app at https://www.producthunt.com/v2/oauth/applications
  (free), use the developer token (no user OAuth flow needed for public data).

## What NOT to send to the LLM
Don't pass raw scraped HTML or full comment threads — snippet fields only,
truncated. This keeps scoring batches small and cheap (see doc 03) and avoids
wasting tokens on noise the model doesn't need to make a call.
