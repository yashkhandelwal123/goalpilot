# Local API

All endpoints are same-origin JSON. If `GOALPILOT_TOKEN` is set, API calls need `Authorization: Bearer <token>`. No CORS is enabled. POST/PATCH bodies are limited to 100 KB. There are no publishing endpoints.

| Method | Route | Purpose |
|---|---|---|
| GET | /api/status | Pause and integration status; no secrets |
| GET / POST | /api/projects | List or create goals with `goal` and `kind` (auto/seo/video/custom) |
| GET / PATCH | /api/projects/:id | Inspect or update `inputs` and `plan` |
| POST | /api/projects/:id/runs | Enqueue with boolean `demo` and `allow_model` |
| POST | /api/projects/:id/schedules | Approve draft generation: boolean `APPROVED: true`, `interval_hours` (1–168), boolean `demo` |
| POST | /api/schedules/:id/disable | Disable, including while paused |
| GET | /api/artifacts/:id/report | Structured JSON diagnosis for SEO artifacts; older/non-SEO artifacts return a clear error |
| POST | /api/artifacts/:id/approve | Mark exact `sha256` reviewed for export; demo artifacts cannot be approved |
| GET | /api/artifacts/:id/export | Download Markdown; review is optional for local draft export |

SEO requires `website` and `audience`. Video requires `topic`, `audience` and `facts`; `language` and `reference` are optional. Custom requires `outcome`. Input edits affect future runs only; queued jobs preserve their snapshots.

A paid-model schedule is rejected even if manually approved in v0.1. Public-site audit schedules can run live; all schedules expire and require fresh approval after material input changes.

SEO inputs additionally accept `pagespeed`: `yes` or `no` (default no). Yes authorizes sending the target public URL to Google for lab measurements when the server key is configured. Changing this setting invalidates prior schedule approval like any other input edit. SEO artifacts include an optional `report` object, without a database migration; legacy artifacts continue to work.
