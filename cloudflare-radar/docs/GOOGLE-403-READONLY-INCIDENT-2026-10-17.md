# Google Sheets 403 – read-only integration incident (2026-10-17)

## Verified integration state
- PR #134 merged into main at commit `2a42bc6f5dc96f2dbb812a9b700c29d7b539d0c6`.
- GitHub's owner-authored issue trigger reached the new `review` job successfully.
- Read-only issue run IDs `38992282867`, `38992307705` and `38992312781` failed before ATS discovery with `Sheets read HTTP 403`. They are **NOT** successful search runs.
- Logs confirm the GitHub service-account secret was present and OAuth token acquisition succeeded. The exception happened on Sheets `values:batchGet`.
- Both authoritative Sheets are shared with the same established Radar service-account principal. Existing Drive metadata lists Register permission `reader` and Radar result permission `writer` for that principal. The identity held by the GitHub secret has **not yet been proven equal** to that established grantee.
- No new vacancy, run, application, D1 baseline, Git technical checkpoint or email writes were made by these read-only job attempts.
- The old Cloudflare `RADAR_ENABLED=0` / `RADAR_PIPELINE_MODE=off` settings remain unchanged.

## Restricted diagnostics in this change
- Two `values:batchGet` reads, one per spreadsheet, replace seven separate requests.
- If any source fails, ATS polling is completely blocked and only `register=...` / `radar=...` status is logged. The API reason is a restricted allowlist, never free-form server error bodies.
- The workflow logs only a boolean for whether the configured GitHub service-account identity matches the known shared grantee. The secret JSON, email contents from the GitHub secret, OAuth token, and private key are never logged.
- No permissions are changed; no unapproved additional service account is granted access.
- Existing Cloudflare OAuth behavior and the shared legacy default scope remain untouched; GitHub review continues to request `spreadsheets.readonly`.

## Decision tree
1. If `radar_service_account_matches_existing_sheet_reader:false`, verify and reconcile the GitHub Actions secret identity with Google Drive sharing under the owner's access policy. **Do not copy Cloudflare private keys into the repository or logs.**
2. If identity matches but only one workbook reports 403, inspect that exact workbook's permission and Google API reason; do not broadly grant access to Drive.
3. If both workbooks 403 with matching principal, verify Google Sheets API enablement, account policy and token scopes. Distinguish `PERMISSION_DENIED`, `ACCESS_TOKEN_SCOPE_INSUFFICIENT`, and rate limits.
4. After the narrow, approved permission repair, perform **one** owner-initiated read-only issue run and immediately verify D1/Google history, jobs and lack of unintended writes.
5. The migration remains NO-GO for full production until successful live ATS review, durable state acceptance and vacature-search eligibility checks.

The existence of a green CI job does not override a failed real live run.
