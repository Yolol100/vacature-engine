# Webactueel Vacature Radar — slim Worker Free CPU audit (17 October 2026)

## Source and baseline

Live project truth remains the Google Vacature Register; GitHub is implementation evidence. The existing Cloudflare `vacature-radar` Worker must remain `RADAR_ENABLED=0` and `RADAR_PIPELINE_MODE=off`. Current optimized code from PR #121 uses one Worker, one `* * * * *` Cron, 16-row paged review-only D1 checkpoints and a dedicated `src/review-worker.mjs` deployment entrypoint. The same Google OAuth and official ATS read helpers are shared with the older compatibility tests. No second scanner, paid upgrade, new scheduler, public test endpoint or business Google Sheets writes.

Previous Free-tier CPU evidence: full legacy bundle **57.05 KiB**, optimized review-only bundle **42.28 KiB**, approximately **26% smaller**. Older 16-row history invocations measured **10.685 ms** and **11.297 ms**, hard NO-GO against the Free 10ms per-Cron limit.

## Safe short private canary after PR #121

Temporary PR #129 added two independent activation conditions to the existing disabled Worker: `RADAR_CPU_CANARY=1` binding and exact private D1 marker `micro:v2:cpu_canary` with kind `slim-review-cpu-oct17`. The lease began **2026-10-16T23:24:22.461Z** and expired at **23:28:22.461Z**; the marker was revoked promptly. Neither production switch was ever enabled.

| UTC | Observed review-only stage | Cloudflare GraphQL CPU |
|---|---|---:|
| 23:25:02 | D1-only cycle initialization | **4.081 ms** |
| 23:26:02 | Google source gate | **7.883 ms** |
| 23:27:02 | Vacancy history ID-bound check | **6.816 ms** |
| 23:28:02 | First history page, 16 rows | **7.533 ms** |

All four minute buckets had **exactly one** request and zero reported errors. Independent invocation logs rounded these to **4, 7, 6 and 7 ms** respectively; the definitive precise values above come from `workersInvocationsAdaptive` `quantiles.cpuTimeP99` in microseconds, divided by 1000. This is a successful **partial CPU canary**, not a full-chain performance GO. The next ~22 history pages and downstream `application_rows`, `event_rows`, `application_index`, `radar_history`, `official_ats`, `candidate_screen`, `review_only` were NOT reached in the short test. Even repeated previous pages sometimes exceeded the Free cap: do not extrapolate.

Cleanup verified: the private marker removed, the entire `micro:v2:` test namespace emptied, all **26 baseline** observations unchanged; non-canary Worker version `8ec3b696-4ce2-409c-8fa4-4c398d7a08d9` explicitly restored by deployment `12b65578-9221-4f65-8070-f5ac51b5de15`. PR #130 restores the three temporary code/config/preview test files **byte-identically** to the pre-canary main; final Cloudflare settings readback must confirm the diagnostic binding is absent.

## Official and practitioner evidence; fastest defensible next decision

- Cloudflare Free enforces **10ms CPU per Cron invocation**; network/D1 wait time does not count, but RSA/JWT/JSON/normalization/JS computation does. Isolates tolerate occasional overages, and `outcome=ok` does not prove <10ms: https://developers.cloudflare.com/workers/platform/limits/
- Cloudflare Workers Paid starts at **US$5/month** (potential extra usage costs). For an every-minute Cron it allows **30 seconds** CPU per invocation, not the Free 10ms. This removes the *budget* blocker without requiring CPU use itself to remain under 10ms, but **does not turn read-only review into a production delivery pipeline**. Do not upgrade without user approval: https://developers.cloudflare.com/workers/platform/pricing/
- Cloudflare supports **production CPU flamegraphs/profiles** to locate expensive function call paths: https://developers.cloudflare.com/workers/observability/profiling-in-production/
- Cloudflare's own Workers Cache bypasses **scheduled** events; enabling `cache.enabled` therefore cannot cure this Cron's CPU use: https://developers.cloudflare.com/workers/cache/
- Independent developer example, Yunseon Hong, `Ten Milliseconds of CPU: I Broke the Cron by Making It Run More Often` (23 August 2026): increasing cadence from ten minutes to one minute triggered repeated CPU-limit failures; profiling showed actual hot paths differed from initial assumptions. This is a case study, not platform authority: https://ondelva.com/blog/2026/08/workers-free-tier-10ms-cpu-limit

## Final QA matrix and release position

| Gate | Result |
|---|---|
| Main Worker / no extra scanner or Cron | PASS |
| Source/employer allowlist unchanged | PASS by regression + real source gate |
| No implicit activation, public test endpoint or applications | PASS |
| D1 26 baseline preservation and no v2 test markers | PASS |
| OAuth/secret never persisted to D1 | PASS |
| 4 short live stages strictly below 10ms | PASS |
| Full 353-row cycle and every downstream stage repeatedly below 10ms | **NOT TESTED / BLOCKED** |
| Representative cold/warm sustained tests with CPU reserve | **NOT TESTED / BLOCKED** |
| Production idempotent Google Sheet delivery / submission safety | **NOT TESTED / separate approval required** |

**Formal verdict: safe slim bundle deployed; short canary successful; Cloudflare Free strict under-10ms GO is still BLOCKED.**

Fastest reliable operational alternative is to request explicit user authorization for Workers Paid (minimum US$5/month), validate billing/limits and then perform a full protected review-only cycle, not a production rollout. If Free is mandatory, use production CPU profiler, optimize proven hot functions and run repeated GraphQL-backed samples before claiming any GO. No automatic applications or Radar Sheet publication on either route.
