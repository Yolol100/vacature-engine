# Safe Google Apps Script API sync from GitHub

This is **code synchronization only**. It does not create a script, timer, scanner, candidate, application, or vacancy search. The existing **one** `runVacatureRadar` timer remains owned by the original spreadsheet-bound Apps Script project. The [Vacature Register](https://docs.google.com/spreadsheets/d/1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0/edit) remains authoritative.

## Safeguards

- Automatic sync from `main` is **disabled** until repository variable `VACATURE_RADAR_AUTO_DEPLOY` is explicitly set to `true`.
- Manual `workflow_dispatch` defaults to `inspect` (no writes).
- First `deploy` requires the **exact current live scanner SHA256** from `inspect`. Future automatic sync compares live code to the *previous* main commit's scanner. Any mismatch stops the write.
- The Google project must be bound to the [existing Radar spreadsheet](https://docs.google.com/spreadsheets/d/1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ/edit); scanner code must contain the expected Radar and Register IDs. Extra script files and `appsscript.json` are preserved.
- Only Apps Script HEAD code changes. Neither script creation nor trigger changes occur. The full set of project files is read back after writing.
- A successful sync **does not** prove that the next scheduled scan ran successfully or that exactly one timer exists. Verify those independently.
- PRs run mock tests only; they cannot deploy to Google.

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
7. Verify the intended change, then run `deploy` manually using the exact **Live SHA256** from the most recent `inspect`. Successful results are `PASS: updated existing scanner file` or `NO_CHANGE`.
8. In Apps Script check **Triggers**: exactly one `runVacatureRadar` every 15 minutes. Check **Executions** and the [Radar Dashboard](https://docs.google.com/spreadsheets/d/1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ/edit) after the next real source check. Existing source cooldown is not automatically a fresh failure.
9. Only after an initially verified deployment and live smoke test, set repository **variable** `VACATURE_RADAR_AUTO_DEPLOY=true`. Subsequent merges modifying `Code.gs` on `main` attempt to update **that same script**, refusing live drift.

## Security, boundaries and recovery

- The broad `script.projects` OAuth scope may edit **any script project accessible** to this Google account. Use a dedicated OAuth client, protect GitHub repository access and `main`, and rotate credentials if compromised. The script ID and scope are secrets, not Git-tracked data.
- Google OAuth consent in **External / Testing** mode usually yields refresh tokens that expire after **7 days** for these scopes. Configure a suitable published/approved consent status or organization-specific internal client for long-lived automation. Google account policies and consent requirements still apply.
- Google `projects.updateContent` replaces **all project files**. The helper copies back every existing file, replacing only the unique Radar scanner file, and verifies the result. Google offers no atomic compare-and-swap for concurrent Apps Script editor changes, so freeze editor writes during a rollout.
- If `deploy` fails after the PUT, **do not retry blindly**. Run `inspect` and compare against the saved original. Restore the prior reviewed source (from an approved Git revision or Apps Script backup), then verify script executions. No speculative automatic rollback is attempted.
- A code update can introduce OAuth scopes requiring the trigger owner's reauthorization. This workflow does not change or count triggers.
- It cannot verify vacancy candidates, applications, or outbound notifications. It does not create a second scheduler, issue any job-board queries, or purchase provider services.

Official documentation: [Apps Script API access](https://developers.google.com/apps-script/api/how-tos/enable), [manage projects](https://developers.google.com/apps-script/api/how-tos/manage-projects), [Google OAuth](https://developers.google.com/identity/protocols/oauth2).
