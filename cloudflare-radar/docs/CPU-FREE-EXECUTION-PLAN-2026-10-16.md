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
2. **Bound history:** an ID-only bounds read, followed by one at-most-32-row page per Cron and D1 page checkpoints. Keep exact row offsets and blank gaps; fail closed at capacity. Do not create a review receipt until all pages are reconstructed. Preserve v2 fallback tests. Increase only the review-only paged cycle lease to cover the bounded work.
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

## Private runtime finding (16 October 2026)
The first paged CPU canary used up to 64 history rows per Cron. Real Cloudflare logs read 8 ms (source gate), 9 ms (ID bound), then 7, 9, 8 and **11 ms** for pages starting with rows 1, 65, 129 and 193. The 11 ms page was a Free CPU **NO-GO**, regardless of the `ok` outcome. All private `micro:v2` marker and snapshots were removed, the 26 baseline records stayed intact, and the pre-canary optimized version was restored.

Phase 2 reduces the page maximum to 32 and allows up to a 75-minute **review-only** cycle, so that <=1536 historical rows can still be scanned across minute-by-minute checkpoints without reading them all in one CPU-heavy event. Multi-minute review snapshots are NOT proof of freshness for a future delivery. Repeat isolated runtime tests and keep radar disabled.


## Additional source-gate optimization — 16 October 2026

A later private CPU canary measured `source_gate` at **10 ms** on 2026-10-16T17:37:06Z, so the 32-row history optimization did not yet prove a reliable Free CPU budget. The canary was disarmed, its private v2 metadata deleted and a safe non-canary build restored before making further changes.

New gap-only changes in this iteration:
- `source_gate` directly scans the two registered `Bronnen` columns, keeps only six allowlisted source/employer IDs and retains last-row-wins duplicate semantics; it no longer creates many sparse 13-column arrays. Header mismatch and inactive employer are still fail-closed.
- Google OAuth keeps its non-extractable RSA `CryptoKey` and a single in-flight token refresh in **memory of the current isolate only**, and invalidates on credential change. A cold isolate still performs the RSA import/signature. No raw keys, tokens or credentials are persisted to D1, KV, logs or files.
- Google Sheets uses the official partial-response `fields=valueRanges(values)` parameter to omit extraneous range metadata while preserving all requested values and their order.

Source authority:
- Cloudflare Web Crypto API: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- Cloudflare Free 10ms Cron limit and rollover: https://developers.cloudflare.com/workers/platform/limits/
- Google Sheets partial response guidance: https://developers.google.com/workspace/sheets/api/guides/performance
- Google Sheets values batchGet: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGet

The changes are **not** guaranteed to reduce cold-start CPU below 10 ms or to persist across isolates. Require green regression/security tests, a fresh short-lived D1-gated private Cron canary, Cloudflare `cpuTimeMs` readback for repeated source-gate and history-page invocations, and immediate rollback upon a budget miss. `RADAR_ENABLED=0` and `RADAR_PIPELINE_MODE=off` remain the enforced default. Still **NO-GO** until every stage has repeated headroom.


## D1-only bootstrap experiment (after source-gate 13 ms failure)

Prior private test on 2026-10-16T17:54:06Z measured **13 ms CPU** in the optimized source gate; caching a CryptoKey within an isolate cannot guarantee cold-start headroom. The test was halted, D1 canary marker and v2 snapshots deleted, all 26 baselines preserved, and the optimized non-canary Worker version restored.

Next minimal, separate patch: when `ops.splitBootstrap` is enabled in the dual-gated review-only scheduled handler, the **first Cron invocation only atomically creates the D1 cycle control** and returns `initialized`. The next scheduled invocation (one minute later) runs the unchanged `source_gate` including Google OAuth and live Bronnen source policy. No secrets/tokens are saved in D1 and no additional scheduler is added. A crash or overlap is governed by the same existing atomic control and two-minute stage claim lease. Nine policy phases remain unchanged; the D1 pre-step is not counted as one of the nine.

Tests must verify zero Google calls on initialization, exactly one source scan on the following Cron, and fail-closed concurrent initialization. This is **CPU hypothesis only**: measure the standalone bootstrap and next source gate through Cloudflare `$workers.cpuTimeMs` with production gates disabled. Fail any >=10ms or invalid source and rollback the private test. No GO or Sheet/application operations without full nine-phase CPU and fresh-history proofs.
