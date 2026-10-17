# Independent Vacature Radar acceptance — current evidence
Date: 2026-10-17. Scope: GitHub Actions manual technical review, NOT full vacancy matching or production persistence.
Live acceptance main: dafd8f191bdb551c23bdfa991771d8124dbdce0c. Status: READ-ONLY REVIEW GO; FULL MIGRATION NO-GO.

## Evidence legend
LIVE = actual GitHub/Google/Cloudflare readback; CI = isolated integration/regression test; BLOCKED = not executed under a separate required approval; PARTIAL = supported subset only.

| Scenario | Evidence / status |
| --- | --- |
| Successful ordinary owner request | LIVE PASS: issues #146/#147, runs 39047802494 / 39047804812, both review_ready |
| No new candidates | LIVE PASS: original 3-source run 39044976255 returned 0 new; CI fixture coverage |
| Bound at ten | LIVE PASS: issue #147 requested 10; ten technical observations, no verified vacancy claim |
| Inactive/invalid source | CI PASS: both live provider and employer status gates; manifest contract tests |
| Known vacancy | LIVE PASS: all 26 baseline jobs recognized as previously seen |
| Previous application / missing vacancy ID | CI PASS: exact official URL and lifecycle dedupe scenarios |
| Google read outage / 403 | CI PASS: sanitized fail-closed boundary diagnostics; historical real 403 fixed |
| Temporary ATS error / 429 / wrong host | CI PASS and LIVE FAIL-CLOSED: 39047475406 partial on two invalid host mappings; PR #145 quarantined |
| Missing/expired secret | CI PASS for missing/invalid; live access working, real expiry not forced |
| Interrupted run + restart | CI isolated Git/CLI PASS, real runner interruption and persistent recovery BLOCKED |
| Two nearly simultaneous starts | LIVE PASS: two separate owner issues #146/#147 serialized and completed |
| Duplicates / checkpoint replay | CI PASS; cross-run production persistence BLOCKED |
| History preservation | LIVE PASS: 26/26 exact D1–Sheet tuples; radar-state original five files unchanged |
| No automatic applications/emails | LIVE output submissions=0; static reviewer has no application or mail writer |
| Radar read-only Sheets writes | LIVE PASS: readonly OAuth and header-only result tabs after both runs. **Separate old ingestion** workflow attempted a Google Register sync, got HTTP 403 before initial batch update; no accepted write evidenced |
| ChatGPT → issue → Action → result | LIVE PASS: matching owner issue events, same main SHA, successful review logs |
| Adversarial invalid API/source + secret logs | CI PASS: malformed tenant, oversized payload, host mismatch, sanitized diagnostics |
| Persistent technical checkpoint and readback | BLOCKED: separate owner/variable approval; review-observations.json absent |
| Full official remote/NL/fit authenticity gates | BLOCKED/PARTIAL: technical candidates require vacancy-search semantic verification |
| Full source reach | PARTIAL: nine supported and live-reviewed; two Greenhouse tenants quarantined, no remaining unsupported adapters in the 11-entry manifest |
| Cloudflare retirement | BLOCKED: prior rollback deliberately preserved |

## Proof anchors
- https://github.com/Yolol100/vacature-engine/pull/143
- https://github.com/Yolol100/vacature-engine/pull/145
- https://github.com/Yolol100/vacature-engine/pull/150
- https://github.com/Yolol100/vacature-engine/actions/runs/39050720551 (owner issue #151, nine live source pairs, 295 observations, no failures)
- https://github.com/Yolol100/vacature-engine/actions/runs/39047475406
- https://github.com/Yolol100/vacature-engine/actions/runs/39047802494
- https://github.com/Yolol100/vacature-engine/actions/runs/39047804812
- https://github.com/Yolol100/vacature-engine/actions/runs/39047791175 (unrelated legacy ingestion push trigger; first Google write denied)
- Google Vacature Register and Radar result spreadsheet; live Cloudflare Worker settings and D1 readback; radar-state contents.

## Claim control
The current manual read-only preview is working for nine scoped sources; it does not create or verify production vacancy matches, does not persist new review observations, and cannot prove durable recovery from an interrupted write. The complete GitHub migration remains NO-GO until the separate approval and live proof gates are satisfied.
