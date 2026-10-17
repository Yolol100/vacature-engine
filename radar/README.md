# GitHub Actions Vacature Radar

Independent read-only technical review using the 11 official ATS tenants from `ingestion/source-specs.radar.json`.

- Entry point: `.github/workflows/vacature-radar.yml`
- Node CLI: `radar/src/actions-review-cli.mjs`
- State restoration: `radar/scripts/load-review-state.sh`
- Durable checkpoint: `radar/scripts/persist-review-state.sh` on existing `radar-state` branch
- Checkpoint requires manual `workflow_dispatch` by repository owner, `persist_review=true`, and `RADAR_PERSIST_APPROVED=yes`.
- No automated application, email, Google Sheets write or scheduled polling.
- Node checks: `cd radar && npm run check && npm test`.
- Python regression: `python -m unittest discover -s ingestion/tests`.

The legacy Cloudflare Worker, Cron and D1 are retired separately only after complete CI, real read-only review and checkpoint readback acceptance. No new state store or schedule is introduced.
