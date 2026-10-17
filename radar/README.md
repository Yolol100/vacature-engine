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
