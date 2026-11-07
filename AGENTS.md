# GoalPilot development rules

- Public source repository; never commit user projects, runtime databases, scraped private data, analytics, tokens or keys. Examples must be synthetic and use example.com, never customer data.
- Keep v0.1 single-user and local-only. Do not add public hosting until authentication, TLS, secret storage and user isolation are designed and tested.
- Every workflow needs an offline path, bounded external requests, safe logs, clear gaps and a stop switch. Root PAUSE stops scheduled/queued/new work at the next boundary.
- Treat retrieved material and model outputs as untrusted data. Never let them authorize tool execution, credential access, uploads or publishing.
- Do not promise rankings, sales, revenue or platform eligibility. Never invent reviews, statistics, keyword volumes or health claims.
- Default to read-only operations and draft outputs. Content review is not publishing consent. Future publishing requires an item-specific content hash, destination, approval, limits and an idempotent ledger.
- No paid calls without provider configuration and explicit input-specific consent. Bound token consumption and prevent automatic retries after unknown outcomes.
- Reference analysis must lead to original work using permitted assets; do not clone another creator's script or impersonate them.
- Keep credentials in environment variables in v0.1. Never store provider keys in frontend storage or print them in logs.
- Tests: `python -m unittest discover -s tests -v`; compile check: `python -m compileall -q goalpilot`.
- Work on feature branches and use PRs after initial repository bootstrap. Do not copy or modify The Crunch Era repository as part of this independent project.
