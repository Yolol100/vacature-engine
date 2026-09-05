# First-Seen Vacancy Radar

The radar is a transport-only discovery layer. It does not own vacancy policy, fit scoring, application decisions, or source activation.

## Runtime

- Poll `source-specs.radar.json` every five minutes through GitHub Actions.
- Resolve active sources against `Vacature Register:Bronnen` before every poll.
- Persist technical state on the isolated `radar-state` branch.
- Bootstrap the first run without emitting historical vacancies as new alerts.
- Add only observations whose persisted `first_seen_at` matches the current ingestion timestamp.
- Keep pending first-seen items for 72 hours unless acknowledged.
- Preserve acknowledgements across concurrent radar persistence and external review writes.

## Evidence boundary

`first_seen_at` means when this ingestion system first observed the vacancy. It is not the same as `published_at` and must never be presented as the employer's publication timestamp unless separate canonical evidence proves that timestamp.

Every candidate still requires the normal `vacature-search` canonical employer/ATS verification and hard gates before it may be shown as a strong match. The radar never submits an application.
