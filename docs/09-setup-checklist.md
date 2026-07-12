# Setup Checklist — do this before your first Claude Code session

Nothing here requires Claude Code or any tool access on Anthropic's side —
these are accounts/keys only you can create, since they're tied to your
identity and require credential flows Claude shouldn't perform on your
behalf.

- [ ] **Private GitHub repo** created for this project.
- [ ] **NVIDIA Build API key** — https://build.nvidia.com (free tier,
      for local testing per doc 04).
- [ ] **OpenRouter API key** — https://openrouter.ai (free tier models,
      second testing option per doc 04).
- [ ] **Anthropic API key** — https://console.anthropic.com, with your $3
      starting credit loaded and (recommended) a spend cap set under
      billing so a bug can't run away on you.
- [ ] **Product Hunt developer token** —
      https://www.producthunt.com/v2/oauth/applications (free).
- [ ] **Google Cloud service account** with a JSON key, Sheets API enabled
      on the project, and the key file downloaded (per doc 05).
- [ ] **Google Sheet** created with two tabs (`Idea Candidates`,
      `Engagement Queue`, columns per doc 05), shared with the service
      account's email as Editor.
- [ ] **Telegram bot** created via `@BotFather`, token saved, `chat_id`
      found (per doc 06).
- [ ] All of the above saved as **GitHub Actions repo secrets** (per doc 08)
      — not committed to the repo, and also saved in a local `.env` file
      (gitignored) for local testing.

Once these are in place, you have everything Claude Code needs to build
against — no more blocked-on-external-account steps once coding starts.
