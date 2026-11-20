# Safe Google Apps Script API sync from GitHub

This is **code synchronization only**. It does not create a script, timer, scanner, candidate, application, or vacancy search. The existing **one** `runVacatureRadar` timer remains owned by the original spreadsheet-bound Apps Script project. The [Vacature Register](https://docs.google.com/spreadsheets/d/1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0/edit) remains authoritative.

## Safeguards

- Automatic sync from `main` requires repository variable `VACATURE_RADAR_AUTO_DEPLOY=true` **and** that the head commit belongs to a merged pull request into `main`. A direct push, even by an administrator, is blocked from automatic Apps Script deployment. This is a provenance gate, **not** an independent code-review approval gate. Enforce reviews in repository protection when an independent reviewer is available.
- A **weekly Sunday 04:23 UTC** scheduled run performs a **strict read-only healthcheck** (project/hash check and Google OAuth refresh). A code mismatch or API/OAuth error fails the run. It does not trigger vacancy scans, create triggers, or modify Apps Script code. This also exercises a refresh token that could otherwise expire after six months without use.
- Manual `workflow_dispatch` defaults to `inspect` (no writes).
- Manual `healthcheck` uses the same strict read-only check as the schedule. Diagnostic `inspect` deliberately reports both hashes even when they differ, so it can establish a deployment baseline; `INSPECTED` alone does not mean the code matches.
- First `deploy` requires **both** the current live scanner SHA256 **and** the reviewed GitHub scanner SHA256 from the same `inspect`. Future automatic sync accepts live code matching a scanner version from the last 99 first-parent `main` commits, to tolerate skipped queued GitHub runs. Unrecognized live edits stop the write.
- The Google project must be bound to the [existing Radar spreadsheet](https://docs.google.com/spreadsheets/d/1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ/edit); scanner code must contain the expected Radar and Register IDs. Extra script files and `appsscript.json` are preserved.
- Only Apps Script HEAD code changes. Neither script creation nor trigger changes occur. The full set of project files is read back after writing.
- A successful sync **does not** prove that the next scheduled scan ran successfully or that exactly one timer exists. Verify those independently.
- PRs run mock tests only; they cannot deploy to Google. Push events must be attributable to a merged PR; `workflow_dispatch` with approved hashes remains available for a deliberately authorized emergency deployment.

## One-time setup by the authorized Google account owner

The connected Google Drive/Sheets tools do not expose Apps Script project code or OAuth approval. Complete these steps in your own logged-in Google/GitHub session:

1. Open the **existing** [Radar spreadsheet](https://docs.google.com/spreadsheets/d/1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ/edit) -> **Extensions -> Apps Script -> Project Settings**. Copy its **Script ID**. Do not create another script.
2. Enable Apps Script API access in your [Apps Script dashboard user settings](https://script.google.com/home/usersettings), understanding that an approved API client can edit your scripts.
3. In [Google Cloud Console](https://console.cloud.google.com/apis/library/script.googleapis.com), enable **Google Apps Script API**, configure an OAuth consent screen with your account authorized, and create an OAuth 2.0 **Web application** client with the redirect URI `https://developers.google.com/oauthplayground`.
4. In [OAuth Playground](https://developers.google.com/oauthplayground/), select the gear and **Use your own OAuth credentials**; provide your own client ID/secret, choose **Offline** access, authorize the specific scope `https://www.googleapis.com/auth/script.projects` with the Google account that owns/edits the script, and exchange the authorization code for a **refresh token**.
5. In GitHub repository **Settings -> Secrets and variables -> Actions**, add these encrypted **repository secrets** (do not commit or send them to ChatGPT):

   | Secret name | Value |
   | --- | --- |
   | `RADAR_SCRIPT_ID` | Existing bound Apps Script project Script ID |
   | `RADAR_GOOGLE_CLIENT_ID` | OAuth client ID |
   | `RADAR_GOOGLE_CLIENT_SECRET` | OAuth client secret |
   | `RADAR_GOOGLE_REFRESH_TOKEN` | OAuth refresh token |

   Leave repository variable `VACATURE_RADAR_AUTO_DEPLOY` **unset/false** for initial setup.
6. Once the PR is merged into `main`, open **GitHub -> Actions -> Vacature Radar - Apps Script code sync (no vacancy scans)**. Run `inspect`. It prints **Live SHA256** and **GitHub SHA256** after verifying the project identity. Preserve a copy of the current live script before changing it.
7. Verify the intended change, then run `deploy` manually using both **Live SHA256** and **GitHub SHA256** from the most recent `inspect`. The workflow refuses a changed GitHub source or live source. Successful results are `PASS: updated existing scanner file` or `NO_CHANGE`.
8. In Apps Script check **Triggers**: exactly one `runVacatureRadar` every 15 minutes. Check **Executions** and the [Radar Dashboard](https://docs.google.com/spreadsheets/d/1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ/edit) after the next real source check. Existing source cooldown is not automatically a fresh failure.
9. Only after an initially verified deployment and live smoke test, set repository **variable** `VACATURE_RADAR_AUTO_DEPLOY=true`. Subsequent **PR merges** modifying `Code.gs` on `main` attempt to update **that same script**, refusing live drift. Direct pushes do not auto-deploy. A successful weekly read-only `healthcheck` verifies code parity and refresh-token access, even without code changes.

## Security, boundaries and recovery

- The broad `script.projects` OAuth scope may edit **any script project accessible** to this Google account. Use a dedicated OAuth client, protect GitHub repository access and `main`, and rotate credentials if compromised. Keep credentials and the private project identifier out of Git; the scope name itself is public documentation.
- Google OAuth consent in **External / Testing** mode usually yields refresh tokens that expire after **7 days** for these scopes. The existing single-user OAuth consent app is now **External / In production**, which removes that specific 7-day testing restriction; this does not imply Google verification or guarantee indefinite token validity. An unused token may expire after six months, and revoked/compromised tokens may stop sooner. The weekly healthcheck reduces idle expiry and provides an early failure signal, not a guarantee. Rotate any token or client secret previously disclosed in a chat, including the refresh token; keep replacements only in encrypted GitHub secrets.
- Google `projects.updateContent` replaces **all project files**. The helper copies back every existing file, replacing only the unique Radar scanner file, and verifies the result. Google offers no atomic compare-and-swap for concurrent Apps Script editor changes, so freeze editor writes during a rollout.
- If `deploy` fails after the PUT, **do not retry blindly**. Run `inspect` and compare against the saved original. Restore the prior reviewed source (from an approved Git revision or Apps Script backup), then verify script executions. No speculative automatic rollback is attempted.
- A code update can introduce OAuth scopes requiring the trigger owner's reauthorization. This workflow does not change or count triggers.
- It cannot verify vacancy candidates, applications, or outbound notifications. It does not create a second scheduler, issue any job-board queries, or purchase provider services.

Official documentation: [Apps Script API access](https://developers.google.com/apps-script/api/how-tos/enable), [manage projects](https://developers.google.com/apps-script/api/how-tos/manage-projects), [Google OAuth](https://developers.google.com/identity/protocols/oauth2).

## Audit follow-up and owner actions (21 November 2026)

- The one-owner protection baseline requires a PR and all four regression checks, with up-to-date branches and administrator enforcement: `Apps Script V8 mock tests (no network)`, `unit-tests (Python 3.12)`, `python-regression (3.11)` and `python-regression (3.13)`. Every PR targeting `main` runs these checks, without path filters. Keep required approvals at zero while there is no second reviewer. These controls are not independent human review and cannot stop an owner from changing repository settings.
- The Apps Script `script.projects` permission can read and edit any Apps Script project the authorizing Google user can access. Restrict repository access and review workflow edits; avoid publishing Google credentials, refresh tokens, or private project identifiers.
- The three **public** WordPress pages for app description, privacy policy and terms on `andrewbaeten.nl` remain useful for the External OAuth branding. Do not remove them merely because Personal mode onboarding was considered and abandoned.
- If a scheduled healthcheck or auto-deploy fails, inspect the GitHub Actions run, keep `RADAR_PERSIST_APPROVED=no`, and investigate without retriggering vacancy searches or blind retries of Apps Script writes.

### Public-repository schedule limitation

- **GitHub automatically disables scheduled workflows in a public repository after 60 days of no repository activity.** This can disable the weekly read-only OAuth check despite an apparently healthy token. It is not an uptime guarantee or an external monitor. Inspect the [Actions workflow](https://github.com/Yolol100/vacature-engine/actions/workflows/vacature-radar-script-sync.yml) after an extended dormant period, verify the workflow is enabled, and explicitly re-enable it if needed. Do not manufacture commits or vacancy scans just to keep the schedule alive. [Official GitHub reference](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows).

- An independent ChatGPT monitoring task checks scheduled Actions runs on Monday mornings (Asia/Bangkok), after the Sunday healthcheck. It reports missing or unsuccessful scheduled checks, including possible inactivity shutdown. It reads public run metadata without secrets or repository writes. It does not re-enable a deliberately disabled workflow and is monitoring, not an uptime guarantee. Future delivery still depends on the monitoring service and connector access.
- A successful `healthcheck`, or an `inspect` explicitly showing `PASS: live code matches GitHub`, proves OAuth/API access and source parity only at that time. Neither proves Google Apps Script trigger execution, every external source, or automatic deploy on the first future code change. The existing radar's scheduled execution and error status must be read separately from Google Apps Script Executions and the Radar Dashboard.

### Replacing credentials that were disclosed

- Issuing another refresh token or adding another client secret does not prove the old token is invalid. GitHub does not expose stored secret values for comparison.
- For a dedicated client used only by this integration, create a new OAuth client in the same production project, authorize only `script.projects` with own credentials and Offline access, store all replacement credentials directly in GitHub secrets, and verify a read-only healthcheck. Then delete only the retired client and repeat the healthcheck. Google states that access and refresh tokens belonging to a deleted client stop working; the client remains restorable for 30 days.
- Do **not** then revoke the old token through `/revoke`: Google documents that revocation affects the user's grants and tokens across clients in that project and could invalidate the replacement. If the existing client must stay, revoke the existing grant first and obtain replacement authorization only afterward, accounting for processing delay and other consumers.
- Verify the actual live outcome before declaring rotation complete. Never print credentials in logs, commits, reports or chat. [Google client management](https://support.google.com/cloud/answer/15549257) and [token revocation](https://developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke).
