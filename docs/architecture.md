# Architecture and boundaries

## State machine

A project has a workflow template, saved intake and an editable plan. Missing required fields block execution. Rule-based goal classification is intentionally modest; custom goals produce a manual brief, not arbitrary code execution.

Jobs transition queued → running → done/blocked/failed. Active jobs are unique per project. Their input snapshots are immutable so edits do not silently change the material approved for a queued paid request. Interrupted running jobs require owner review before retrying.

Drafts are immutable. Review stores their SHA-256 and explicitly applies to export only. It grants no authority for website publication or social uploads. No publisher exists yet.

A single worker polls a SQLite queue. Approved schedules enqueue only draft jobs, expire after seven days or seven runs and are invalidated by project edits. Schedule row updates and job insertion share one transaction. The app must remain running; no OS cron registration or automatic deployment occurs.

## Network boundary

Public website fetching permits HTTPS:443 only, rejects credentials, validates all DNS addresses as global and pins the TLS connection to a validated address while retaining hostname certificate validation. Every same-host redirect is checked; off-host redirects require the owner to supply the final URL. Responses are bounded to 512 KB. Robots failure stops crawling. At most ten sitemap page URLs are inspected. This is not a full crawler or JS renderer.

The model adapter accepts only a server-operator-configured HTTPS base URL. It never follows redirects and never accepts an endpoint from a web page or model output. It sends user-approved source notes to that destination once, with a completion-token cap. Provider compatibility and fees remain the operator's responsibility. Additional providers should implement a separate adapter with the same consent and logging contract.

## Integration lifecycle

1. Explain which capability is needed and why.
2. Describe data destination, permissions and cost.
3. Request credentials through secure configuration or OAuth when implemented.
4. Verify access without implying it implements an unsupported capability.
5. Request exact-task approval for paid actions; content publication needs a separate gate.

In v0.1, only the public crawler and Chat Completions model adapter execute external requests. GSC, GA4, search, audiovisual analysis, TTS, rendering, GitHub and social publishing are future adapters, explicitly marked planned.

## Security limits

This is a local personal development tool, not a hardened hosted service. Local API token authentication is optional; Host and Origin checks protect browser-driven cross-origin requests, but do not protect against another process or user on the same machine. There is no encryption-at-rest beyond the operating system, account system, TLS termination, OAuth vault or tenant isolation. Runtime files must not enter git or public CI artifacts.
