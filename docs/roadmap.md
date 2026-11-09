# Roadmap

## Shipped foundation

Single-user local workspace, intake, editable plan, persisted jobs, read-only SEO crawl, source-note-based video drafts, manual export/review, expiring draft schedules, stop switch and offline tests.

## Phase 1 — SEO optimization

- **1A · Website diagnosis (implemented on this branch):** nested sitemap coverage, internal-link status/referrers, canonical targets, redirects, structural JSON-LD checks, duplicate metadata and optional mobile/desktop PageSpeed. Markdown and JSON evidence exports. Read-only; no publishing.
- **1B · Search and sales data (next):** official GSC/GA4 reporting adapters with scoped access and clear attribution limits. Ask for credentials only when implementing this milestone.
- **1C · Keyword opportunities:** configured search/keyword APIs, sourced volumes, intent classification and clustering. No invented demand or difficulty.
- **1D · Recommendations:** source-backed content briefs and page-specific improvement proposals; separate fact-check.
- **1E · Implementation:** approved code changes through PRs, regression tests and deployed-result verification. No direct production writes.

## Phase 2 — Research and original scripts

Configured research-provider interfaces, citations, topic discovery, audience briefs and content calendars. Improve the current source-note-based script adapter with independent research and fact-checking.

## Phase 3 — Reference-video analysis

Permitted video ingestion, transcription and timestamped visual analysis. Produce original creative briefs; the current notes field is not audiovisual analysis.

## Phase 4 — Video production

TTS and renderer interfaces, provenance manifests, original permitted assets, captions and real output validation.

## Phase 5 — Publishing and recurring workflows

YouTube/Instagram/CMS OAuth adapters with content-hash approval, idempotent upload ledger, platform disclosure and publication limits. Separate consent for recurring research, paid generation and external publication; monetary budget enforcement before paid schedules.

## Phase 6 — Measurement and improvement

Evidence-backed weekly search, sales and video reports. Compare against baselines and recommend the next iteration without guaranteeing outcomes.

Finish and test each milestone before advancing. This branch implements 1A only; the rest are not shipped.

## Before hosting

Authentication, encrypted credential store, user isolation, secure uploads, billing limits, task sandboxing, durable worker infrastructure and an externally audited permission boundary.

Work incrementally. Do not mark roadmap integrations connected merely because the UI can describe them.
