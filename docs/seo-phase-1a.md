# Phase 1A — website diagnosis

## Run

1. Start `python -m goalpilot` and create an SEO project.
2. Supply a public HTTPS content URL and its audience; save the intake.
3. Try the offline demo first. It is synthetic and cannot be approved as a real deliverable.
4. Run a live task for the read-only diagnosis. Optionally opt into PageSpeed first and configure the server-side API key.
5. Review/download Markdown or **audit JSON**. Artifacts stay in ignored local runtime storage, not this public repo.

The implementation is on a feature branch stacked on the foundation branch until the foundation PR is merged. No PR is automatically merged or deployed.

## Evidence and checks

- Reads robots.txt first. Failure stops the run; it never assumes crawl permission. Honors `Sitemap:` directives and nested XML sitemap indexes with cycle detection.
- Audits up to ten same-host HTML URLs discovered from the input, sitemap and anchors. Reports sitemap URLs discovered, inspected and remaining. Non-HTML resources are not flagged for missing headings.
- Checks title/description presence and duplicates, H1 count, canonical count/target status, redirect chains, HTML and X-Robots-Tag noindex, and JSON-LD parsing.
- Inspects Product/ProductGroup, Offer, FAQPage and BreadcrumbList fields heuristically. It does not validate all Google requirements, require optional markup on every page or invent ratings/availability.
- Checks up to forty unique same-host link targets, using cached crawl responses where possible. Reports HTTP status and originating pages. Only confirmed HTTP errors are labelled failures; transport errors remain unverified.
- Resolves canonical targets within the same origin and shared budget; surfaces redirects, HTTP errors and conflicting noindex. A cross-site canonical is a manual-review item, not automatically a defect.
- Reports prioritized actions and explicit coverage gaps. A successful request does not establish Google indexing or a ranking result.

## Bounds and exclusions

Defaults: 10 HTML audit candidates, 6 sitemap documents, 40 internal-link checks, 80 logical site fetches and 120 seconds between action boundaries. Each logical fetch allows at most four HTTP attempts including redirects; all actual attempts are logged. A request already in flight can finish after the time boundary. Missing/blocked/non-HTML URLs count toward traversal limits, so fewer than ten HTML pages may be inspected. Exceeding a budget creates a partial report.

Logical fetches are paced by at least 250 ms and honor robots Crawl-delay / Request-rate when provided; PAUSE/time limits are checked during waiting.

Only HTTPS on port 443, same host, validated public DNS and pinned TLS IPs are allowed. Robots/action policy is reapplied on every redirect. Action paths, credentials, off-host URLs, query strings and fragments are excluded or normalized. This deliberately skips transactional, login and variant URLs. Compressed sitemap files, external links, broken fragment anchors, JavaScript rendering, schema-vs-visible-content matching and HTTP Link canonicals are not implemented. Audit findings can require manual review for intentional noindex, canonical consolidation or client-rendered pages.

An API key and saved per-project opt-in enable at most two official Google PageSpeed requests for the entered URL: mobile and desktop. No key or complete PSI request URL is logged. Results are lab scores/LCP/CLS/TBT; no field INP is fabricated. Runtime, quota and network failures yield unmeasured results. No paid model calls are needed for SEO diagnosis.

PAUSE stops new and running work at its next boundary. It must propagate without saving a partial artifact. Ordinary budget limits can save explicitly partial results.

## Validation

Tests use synthetic example.com fixtures and mock provider responses. They cover nested/cyclic sitemaps, extension-image URLs, robots exclusion, redirect guards/loops, broken/unverified links, canonical failures, duplicates, structural schemas, caps, pauses, JSON persistence, lab units and key redaction. Live PageSpeed is not claimed tested without credentials.

Official references:

- https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- https://developers.google.com/speed/docs/insights/v5/reference/pagespeedapi/runpagespeed
