# GitHub Actions Vacature Radar

Independent read-only technical review using the 11 official ATS tenants from `ingestion/source-specs.radar.json`.

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

The original `[radar] review 5` issue command and default manual workflow still review only the 11 validated official ATS tenants. To expand manually, start the existing workflow with `discovery_scope=tiered` and `persist_review=false`, or open an owner-authored issue titled `[radar] discover 5` or `[radar] discover 10`. No schedule is enabled.

The same Sheets baseline, live source statuses, Config `direct_discovery_order` / `high_source_order`, vacancy/application deduplication and ATS checks run first. When the preliminary review queue is not full, the existing deploy manifest supplies up to five read-only public API/RSS sources: Jobicy, Remotive, Himalayas, We Work Remotely and Remote OK, ordered by the live register class and priority. Inactive/retired sources are skipped, unavailable providers become explicit errors, and further feeds stop when the limited **manual lead queue** is full. Untested web-only boards are **not** advertised as automated. The optional `discovery.manual_fallback_sources` contains still-active high-priority web sources (e.g. LinkedIn, Indeed, Google Jobs and The WP World) that require a separate official-role search/verification; these entries have **not** been fetched by Radar.

The extra output is `discovery.candidates` with `discovery_url`, a visible provider attribution link, and `discovery_only` status. These are **not verified or eligible vacancies**: validate the exact employer-owned ATS/careers role, full remote/NL execution, language and fit under Vacature Search before showing or saving. No discovery lead can create a checkpoint receipt, write Google Sheets, apply, send email or turn on an ingestion writer. `persist_review=true` with `discovery_scope=tiered` fails closed. Existing normal ATS checkpoint recovery remains unchanged. For source contracts and attribution respect [Himalayas](https://himalayas.app/docs/remote-jobs-api), [Remotive](https://remotive.com/remote-jobs/api), [Jobicy](https://github.com/Jobicy/remote-jobs-api) and [We Work Remotely](https://weworkremotely.com/remote-job-rss-feed).
