# Cloudflare Free CPU: evidence-based execution plan
Date: 2026-10-16. Controller: webactueel-workflow. Domain owner: vacature-search.
Repo: Yolol100/vacature-engine/cloudflare-radar.

## Objective and hard constraints
- Aim for **under 10 ms CPU per individual scheduled Worker invocation**, with an engineering guard band (target <= 7 ms in repeated runs) on Cloudflare Workers Free.
- A mathematical/absolute guarantee under unbounded work or noisy cloud scheduling is impossible. Never state GO based on a one-off successful response, a code test or a local wall-clock benchmark.
- Keep `RADAR_ENABLED=0`, `RADAR_PIPELINE_MODE=off`. Do not create a public trigger, extra Cron, API key, paid service, automatic application, automatic message, or Sheet delivery.
- Preserve all 26 existing D1 `radar_observations` baseline entries and historical `micro:v1:` receipts. Keep the Google service account in a secret binding.
- The Vacature Register is the authoritative policy and history source. Incomplete/failed history reads must **fail closed**, never silently omit applied jobs or declare a review ready.

## Context and evidence
- Prior live first-stage Cron CPU: 18 ms initially, 10 ms after removing redundant health D1 operations.
- Prior `vacancy_history` Cron observation: 16 ms at 2026-10-16 16:12:05 UTC, even though Worker outcome was `ok`; an `ok` event can exploit Cloudflare's limit rollover.
- Current history spans about 353 allocated/displayed rows with roughly 351 nonempty IDs, whereas the Google Sheet grid has 994 rows. The old `vacancy_history` read was one unbounded batch of `Vacatures!A:B` and `Vacatures!G:H`.
- Official sources:
  - https://developers.cloudflare.com/workers/platform/limits/
  - https://developers.cloudflare.com/workers/observability/metrics-and-analytics/
  - https://developers.cloudflare.com/workers/runtime-apis/performance/ (in deployed Workers, `performance.now()` is frozen between I/O; do not claim this is a CPU profiler)
  - https://developers.cloudflare.com/d1/worker-api/d1-database/
  - https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGet

## Prompt strategy: goal, decomposition, constraints, oracle and repair
```text
Act as a careful Cloudflare Workers Free performance engineer for Webactueel Vacature Radar.
Retrieve current authoritative source state and repo history; do not trust stale snapshots.
First verify worker disabled, one Cron, 26 D1 baselines, zero pending review-control
snapshots, no sheets rows, and active GitHub HEAD. Read official Cloudflare/GSheets docs.
Decompose CPU-heavy work into one small, bounded, D1-checkpointed unit per scheduled
invocation. Preserve full vacancy, application and event coverage; never silently skip
rows or relax applied/known identity gates. Use input limits and fail closed rather
than pretending unbounded work can be guaranteed below 10 ms.
Use deterministic unit/property/adversarial tests, CI, Wrangler dry-run and real
Cloudflare invocation log cpuTimeMs. Iterate page size and algorithms based on evidence.
A single <10-ms run is not enough: require repeated distinct representative invocations,
including cold starts and worst-case rows. Investigate any >=10-ms or exceededCpu event;
NO-GO until all stages are repeatedly proven with headroom, source integrity and
review-only behavior. Never enable RADAR_ENABLED or send applications.
Keep all canary controls private, single-cycle and expiring. Revoke marker,
purge only test-owned micro:v2 checkpoints, remove canary code/config, restore
known-safe version, and read back all preservation invariants.
Provide an honest phase-by-phase verification ledger and measured CPU distribution.
```

## Execution gates
1. **Discover and baseline:** source register + skills + repo + Library + prior context + official docs. Verify bindings, D1 counts, Sheet headers, old CPU timestamps.
2. **Bound history:** an ID-only bounds read, followed by one at-most-64-row page per Cron and D1 page checkpoints. Keep exact row offsets and blank gaps; fail closed at capacity. Do not create a review receipt until all pages are reconstructed. Preserve v2 fallback tests. Increase only the review-only paged cycle lease to cover the bounded work.
3. **Security and functional tests:** old invariants (no submissions or Sheets writes, race claim, retry limits, 429, no duplicate candidates), new paging coverage, gaps, header errors, stale control and cleanup. All CI green before merge.
4. **Measure privately:** short-lived D1-only canary, exactly one review cycle; Cloudflare logs per invocation using `$workers.cpuTimeMs`, not `performance.now()`. Stop on any overrun/failed integrity gate.
5. **Iterate bottlenecks:** if OAuth/bounds or index construction exceeds budget, split again, cache imported CryptoKey only inside an isolate without persisting secrets, and/or index incrementally across checkpoints. Review any tradeoffs in freshness (multi-minute Sheet reads are not atomic).
6. **Cleanup and handoff:** revoke markers, restore non-canary code in GitHub/Cloudflare, validate 26 baselines and empty output Sheets. **Do not activate delivery or monitoring** until a separate full GO review of all stages and idempotent Sheet delivery.

## Known limitation
The current nine-stage review-only pipeline is not the automated delivery path.
Sharded scans may take more Cron minutes, and intervening Google Sheets edits can
make a multi-phase view non-atomic. Any future delivery must revalidate source
status, application history and deduplication against a fresh authoritative
snapshot; it cannot rely solely on these test receipts.

## Exit criteria
Every stage has repeated live samples strictly below 10 ms, with practical
margin below 7 ms at p99 where measurable; failures halt before any output.
Only then consider a separate approval for a read-only operational review.
Automatic Sheet writes and application submissions remain independently blocked.
