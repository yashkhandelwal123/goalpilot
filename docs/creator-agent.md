# Content creator agent: research → design → voice → Reel

This is a **local CLI production harness**, separate from the existing web UI. It creates drafts only. It cannot publish or schedule social posts. Keep real briefs, research, photos, renders and keys in ignored `runtime/`, never this public repository. The included brief is fictional.

Run `python -m goalpilot.creator doctor` to list missing model/voice configuration and media tools without exposing secrets or making API calls.

## Start offline

```bash
mkdir -p runtime/creator
cp examples/creator-brief.json runtime/creator/my-brief.json
python -m goalpilot.creator prepare runtime/creator/my-brief.json --out runtime/creator/draft-01
```

Replace all fictional details in your private brief. Each fact needs an ID, exact supported statement and source (current pack label, owned product page or founder-supplied fact). Add photos as `{"path":"assets/product.jpg","rights_confirmed":true}` relative to the brief. Do not use competitor media. Photo assets currently supported: JPEG/PNG. Clips go through the editor handoff; automatic clip selection/analysis is not implemented.

`prepare` writes research evidence, a package template, voiceover and caption placeholders, an editable HTML post source, Canva/Adobe handoffs, review checklist and JSON manifest. Offline results are clearly marked and cannot be voiced. `--format-index 0` through `6` rotates snack occasion, ingredient explainer, comparison, myth/fact, product introduction, office snack idea and founder story. Select formats supported by your facts; this does not invent comparisons or founder history.

## Public competitor research

Put up to five public post/page URLs in `research_urls`, then run a fresh `prepare` with `--research`. This is an explicit read-only network action, at most five robots checks and five page fetches (each fetch has bounded redirects and a 512 KB limit). It reads only public initial-HTML title/meta information. Instagram login walls, restricted pages, video/audio, rankings and engagement metrics are not bypassed or inferred. It is not a discovery/search engine. Research unavailable? Paste your own permitted observations into private facts/source notes, or use research from your connected assistant. Competitor material informs formats, never product claims or copying.

## Generate the creative script

Configure environment variables in your shell (the app does not auto-load `.env`):

- `LLM_BASE_URL`: your OpenAI-compatible API base URL
- `LLM_MODEL`: a currently supported Chat Completions model
- `LLM_API_KEY`: secret, environment only

```bash
python -m goalpilot.creator draft runtime/creator/draft-01
# Review brief.json, research.json and the fixed system prompt in creator.py.
# The command prints an exact-request consent hash without sending a request.
python -m goalpilot.creator draft runtime/creator/draft-01 --consent HASH_FROM_PREVIOUS_COMMAND
```

One call with 2,200 completion tokens maximum. JSON validation enforces length, four scenes and valid fact IDs; it does **not** prove factual accuracy. Read `claim_checks` separately against originals. All package content remains unverified. `needs_from_owner` flags missing information. Live output includes a hook, 45–85-word voiceover, caption, source checklist and four-scene storyboard. Timing depends on language and voice. No automatic paid batches or retries. Use provider-side spending limits.

## Canva and Adobe Express

Open `design.html` using the connected Canva import capability in your assistant, or import it through a supported Canva workflow. The source contains separately editable typography plus the original photo, not an AI-redrawn pack. Use `design-handoff.json` for the Adobe search/edit steps. Select an Express template, apply the prompt plus permitted product image, and review/export the design. The local Python app has **no access to ChatGPT connector sessions**. These are honest human/assistant handoffs, not background API integrations. Store export links/files privately in the draft folder. Actual unattended integrations require separate app/API credentials and implementations; do not scrape authenticated editors.

Design review: clear hook, one visual focus, readable type, contrast, platform safe areas, accurate packaging, one CTA. Never invent testimonials, nutrition values or product features. Do not represent AI-created product scenes as real footage.

## Add a natural voice

Use an OpenAI-compatible **speech** endpoint, rather than expecting a text LLM to return audio. Configure:

- `TTS_BASE_URL`, `TTS_API_KEY`: speech provider base/key
- `TTS_MODEL`, `TTS_VOICE`: currently supported model and a licensed stock voice
- optional `TTS_INSTRUCTIONS`: only if that provider/model supports instructions, for example: `Warm conversational English with a light Indian accent. Relaxed pacing, short pauses, clear product pronunciation. Avoid an exaggerated advertising voice.`

```bash
python -m goalpilot.creator voice runtime/creator/draft-01
# Review package.json voiceover and the configured voice/model; copy the exact-request hash.
python -m goalpilot.creator voice runtime/creator/draft-01 --consent HASH_FROM_PREVIOUS_COMMAND
```

No voice cloning or impersonation. Audition the result; a natural delivery cannot be guaranteed. The draft captions and video disclose the AI voice. Requests are limited to 20 MB audio responses and 60 seconds. Existing attempt ledgers block repeat/unknown calls; they are not automatically cleared after failures. Inspect provider usage and recover manually rather than risk duplicate charges.

Speech API reference: https://developers.openai.com/api/docs/guides/text-to-speech (verify model availability in your account; no hardcoded model default).

## Render the voiced photo Reel

Install FFmpeg/FFprobe with `drawtext`, H.264 and AAC support. Supply a font that covers your language:

```bash
python -m goalpilot.creator render runtime/creator/draft-01 --font /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
```

Creates `reel.mp4` (1080×1920, 25fps), four photo/text scenes, AI-voice disclosure and `captions.srt`. Voice must measure 20–40 seconds and match the current package hash. SRT phrase timings are estimates, not forced alignment; check them in your editor. Spoken captions are sidecar SRT, not burned in. No music is added. Film-like motion, real-action footage, automatic B-roll generation, precise forced alignment and autonomous creative quality review are future adapters. Use your editor for these, then review the final export.

## Safety and operation

`touch PAUSE` at the repository root stops new stages and work at the next boundary. A provider call or FFmpeg subprocess already in progress may finish (maximum timeout 60/180 seconds); outputs are not accepted after a pause. All actions/API attempts log only stage/status/timestamp under ignored `runtime/creator/run-log.jsonl`, with separate per-request ledgers. Provider errors and keys are redacted. Changing the script, voice, endpoint or model changes consent. Nothing here publishes, writes profile data or starts a cron job. Existing draft scheduler behavior is unchanged. Do not schedule paid generation until bounded per-item consent/budget management is implemented.

Approval sequence: fact/label and rights check → pronunciation/timing/caption/design review → final exact media and caption approval → a separately authorized publisher. The publisher is deliberately absent in this milestone.
