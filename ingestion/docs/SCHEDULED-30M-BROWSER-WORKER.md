# Scheduled public vacancy discovery — 30 minute worker

Owner-requested extension (21 November 2026). The existing Google Apps Script
Radar remains the only writer of preliminary vacancy leads to the private
Google Sheet. The separate GitHub Actions job performs browser/network work
that exceeded Apps Script's six-minute execution limit.

## Local SearXNG multi-engine discovery

After checkout (never as a pre-checkout Actions service), the runner starts
a private Docker container with the trusted \`searxng/settings.yml\` mounted
read-only. Docker exposes **only 127.0.0.1:8080**, never a public port.
\`use_default_settings: true\` preserves SearXNG's built-in engine settings
and timeouts; \`search.formats\` explicitly enables JSON.

Every half-hour run with a healthy container adds four targeted WordPress,
WooCommerce, Elementor and website/frontend queries to SearXNG. It requests
results from DuckDuckGo, Brave, Bing and Google, subject to upstream engines'
actual availability. If Google or another engine blocks the runner IP,
the remaining engines may still supply results. SearXNG **cannot guarantee**
that any engine will return results and does not provide permission to
circumvent CAPTCHAs, access restrictions or paid APIs.

Only links with explicit remote and material web-role evidence become
**unverified** candidates. Search-index snippets are not evidence of employer
authenticity, original posting date or permission to work from the Netherlands.
Failures are labeled \`searxng_unavailable_or_invalid_json\` or
\`searxng_no_results_or_engines_blocked\`, not silently treated as zero jobs.
If Docker fails, the approved official ATS/RSS sources keep running.
The existing SerpApi Free Plan route remains optional, at its separate
4-hour, verified-zero-cost limit. No new API keys or subscriptions are needed.

## Flow

1. \`Vacature Register:Bronnen\` remains authoritative. This repository contains
   a **public URL-only snapshot** of the 233 active IDs, with no private
   applications, candidate evidence, emails, or credentials. When the live
   active ID/URL list changes, update this snapshot via an authorized
   register-to-repo sync before declaring coverage complete. Apps Script checks
   the full current active list against each worker report and **refuses
   stale/mismatched inventories**.
2. GitHub Actions \`vacature-public-browser-30m.yml\` is scheduled at minutes
   07 and 37 UTC. It tries the public HTTPS entrypoint of every registered
   active source, parses role-specific JobPosting/remote links, uses
   headless Chromium on a rotating subset of pages requiring JavaScript,
   and additionally performs five targeted public Google searches.
   Every source gets an honest status and browser coverage label.
3. GitHub writes **only public job observations** to the isolated
   \`radar-public-data\` branch as \`latest.json\`; no personal history is
   fetched or published. Job pages, titles, URLs and search queries are public.
4. The existing Apps Script \`runVacatureRadar\` 30-minute trigger imports
   the most recent snapshot by fixed GitHub Raw URL. It validates timestamp,
   all 233 identities/URLs, role scope, remote evidence, per-source provenance
   and duplicates against \`Vacatures\`, \`Applications\`, \`JobSnapshots\`
   and \`Radar:Bronvondsten\`. New leads are written to **unverified**
   \`Bronvondsten\` only; \`Broncontrole 30m\` records source coverage.
   No automated sending, applications, or promotion to verified roles.

## Limits and safety

- Public source homepages, generic ATS roots, search results and directories
  are **not full job catalogues**. \`http_200\` means the page was reachable,
  not that all openings were reviewed. Unavailable/captcha/403/429 sites
  are recorded as incomplete, never bypassed or labeled empty.
- Headless Chrome is an actual JS renderer on the GitHub-hosted runner.
  Browser rendering is rotated across up to 90 relevant pages per run,
  with strict timeouts. The remainder may be visited in later runs.
  Browsers may be absent, blocked or delayed; the report says so.
- Google HTML scraping is disabled. A Google Jobs search runs via the
  existing SerpApi account only when it has a verified zero-price Free Plan,
  no extra credits, and at least 20 searches left. At most one search every
  four hours (six per day, maximum 186 in a 31-day month). Other half-hour
  runs are explicitly reported as not scheduled. The account-only preflight
  costs zero search credits. The service must not spend paid API credits,
  bypass CAPTCHA, reveal the API key, or store private applicant data.
- GitHub schedules can be delayed, so the private Apps Script importer may
  show results from the previous scan. Results older than three hours
  are rejected. The fallback 27 approved ATS/feed adapters continue.
- Only fully remote, material WordPress/WooCommerce/Elementor or frontend/
  website roles can become pending leads. Unknown original date, contract,
  salary and NL work permission remain missing evidence. **No result is
  automatically marked suitable to apply from the Netherlands**.
- GitHub Actions standard runners are free in this public repository,
  subject to GitHub's service limits and policies. Publish uses the built-in
  \`GITHUB_TOKEN\` with contents:write only in the isolated worker job,
  and only after browsing is complete. Keep no secrets in public outputs.

## Verification

- Run \`python -m unittest discover -s ingestion/tests -p test_scheduled_worker.py\`.
- Run \`node --test automation/google-apps-script/radar.test.cjs\`.
- Manual GitHub smoke: \`gh workflow run vacature-public-browser-30m.yml -f mode=smoke\`.
- Manual real run: \`gh workflow run vacature-public-browser-30m.yml -f mode=full\`.
  Correlate the GitHub run with \`radar-public-data/latest.json\`.
- After the existing Apps Script trigger: confirm an updated
  \`Dashboard\`, \`Broncontrole 30m\` and deduplicated \`Bronvondsten\`.
  **Never claim GO from local tests or a GitHub run alone.**
