# GitHub Actions Vacature Radar

Independent read-only technical review using the 13 official ATS tenants from `ingestion/source-specs.radar.json`.

- Entry point: `.github/workflows/vacature-radar.yml`
- Node CLI: `radar/src/actions-review-cli.mjs`
- State restoration: `radar/scripts/load-review-state.sh`
- Durable checkpoint: `radar/scripts/persist-review-state.sh` on existing `radar-state` branch
- Checkpoint requires manual `workflow_dispatch` by repository owner, `persist_review=true`, and `RADAR_PERSIST_APPROVED=yes`.
- No automated application, email, Google Sheets write or scheduled polling.
- Node checks: `cd radar && npm run check && npm test`.
- Node and focused Python regression jobs run in parallel in `.github/workflows/vacature-radar.yml` on code changes.
- Python regression: `python -m unittest discover -s ingestion/tests`.

## Cloudflare retirement (2026-10-17)

The project-owned Cloudflare Cron, Worker `vacature-radar`, and D1 database `vacature-radar-state` were **permanently deleted**, in that order, after passing the GitHub migration acceptance. Cloudflare account readback reported zero Workers and zero D1 databases. Legacy D1 metadata was intentionally not backed up, per explicit owner authorization. No unrelated account resources were changed.

Evidence:
- [Migration PR #163](https://github.com/Yolol100/vacature-engine/pull/163)
- [Post-migration owner-initiated read-only review](https://github.com/Yolol100/vacature-engine/actions/runs/39061114257): 11/11 active ATS sources, no failures; existing checkpoint restored
- [Post-deletion owner-initiated read-only review](https://github.com/Yolol100/vacature-engine/actions/runs/39061366550): 11/11 active ATS sources, no failures, zero Google Sheets writes and zero applications
- [Acceptance issue #165](https://github.com/Yolol100/vacature-engine/issues/165)

The preserved GitHub `radar-state` and `ingestion-state` branches and the live Google Sheets history remain authoritative for their respective records. No new scheduler, state store or delivery pipeline was introduced.

## Optional tiered discovery (read-only)

The original `[radar] review 5` issue command and default manual workflow still review only the 13 validated official ATS tenants. To expand manually, start the existing workflow with `discovery_scope=tiered` and `persist_review=false`, or open an owner-authored issue titled `[radar] discover 5` or `[radar] discover 10`. No schedule is enabled.

The same Sheets baseline, live source statuses, Config `direct_discovery_order` / `high_source_order`, vacancy/application deduplication and ATS checks run first. When the preliminary review queue is not full, the existing deploy manifest supplies up to eight read-only public API/RSS sources: Jobicy, Remotive, Himalayas, Remote Landers, RemoteJobs.org, Arbeitnow, We Work Remotely and Remote OK, ordered by live Register policy. Inactive/retired sources are skipped, unavailable providers become explicit errors, and further feeds stop when the limited **manual lead queue** is full. Untested web-only boards are **not** advertised as automated. The optional `discovery.manual_fallback_sources` contains still-active high-priority web sources (e.g. LinkedIn, Indeed, Google Jobs and The WP World) that require a separate official-role search/verification; these entries have **not** been fetched by Radar.

The extra output is `discovery.candidates` with `discovery_url`, a visible provider attribution link, and `discovery_only` status. These are **not verified or eligible vacancies**: validate the exact employer-owned ATS/careers role, full remote/NL execution, language and fit under Vacature Search before showing or saving. No discovery lead can create a checkpoint receipt, write Google Sheets, apply, send email or turn on an ingestion writer. `persist_review=true` with `discovery_scope=tiered` fails closed. Existing normal ATS checkpoint recovery remains unchanged. For source contracts and attribution respect [Himalayas](https://himalayas.app/docs/remote-jobs-api), [Remotive](https://remotive.com/remote-jobs/api), [Jobicy](https://github.com/Jobicy/remote-jobs-api) and [We Work Remotely](https://weworkremotely.com/remote-job-rss-feed).

## Maximum public-source coverage (manual, read-only)

Run **Actions → Vacature Radar → Run workflow**, choose `discovery_scope=maximum` and leave `persist_review=false`, or open an owner-authored issue titled `[radar] maximum 5` or `[radar] maximum 10`.

Maximum mode reads the same live Register policy, keeps the official ATS review first, then polls **all eight** previously registered public API/RSS connectors on the bounded deployment manifest: Jobicy, Remotive, Himalayas, Remote Landers, RemoteJobs.org, Arbeitnow, We Work Remotely and Remote OK. The public APIs are queried with narrow documented search/category limits and do not receive Google credentials. Maximum mode retains a separate 5/10-item **unverified public lead queue** even when the ATS queue is full, and counts further preliminary matches without claiming eligibility. The default quick `official_only` and opt-in fast `tiered` behavior remain unchanged.

Official ATS tenants now include both ElevenLabs and n8n Ashby company boards. Registered ATS *platforms* without a verified company tenant, web-only boards, directories, employer career pages and third-party searches are reported separately in `discovery.registry_coverage`, not falsely counted as polled. Use the existing Vacature Search live web/X-ray route for prioritized **manual** follow-up, with exact official employer/ATS verification and full Netherlands, remote, language, fit and dedupe gates. A registered source is not a licensed or publicly accessible API.

Do not enable a schedule, import applicant data, send email, automatically apply or persist leads from this technical review. Only the original owner-gated `official_only` checkpoint route can write technical receipts. Provider unavailability or HTTP 401/403/429 is a source failure, never silently interpreted as zero roles.
