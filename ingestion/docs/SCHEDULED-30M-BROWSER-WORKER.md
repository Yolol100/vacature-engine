# Scheduled public vacancy discovery — 30 minute worker

Owner-requested extension (21 November 2026). The existing Google Apps Script
Radar remains the only writer of preliminary vacancy leads to the private
Google Sheet. The separate GitHub Actions job performs browser/network work
that exceeded Apps Script's six-minute execution limit.

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
- Google is **public HTML search, not an authenticated Google Jobs API**.
  If Google blocks or returns no readable results, that status is recorded.
  No paid services, proxies, cloudbrowser credits or CAPTCHA bypass.
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
