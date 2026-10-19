# Free Google vacancy discovery — setup and safety

The optional `serpapi_google` adapter supplements free ATS and public feed
adapters; it does not replace them. The live Vacature Register remains the
**sole source of truth** for source activation and policy. Only its active
`google-jobs` row authorizes discovery.

## 1. Configure the secrets

1. Create or use your free [SerpApi](https://serpapi.com/) account.
2. In [GitHub Actions secrets](https://github.com/Yolol100/vacature-engine/settings/secrets/actions)
   add `SERPAPI_API_KEY` with your SerpApi API key.
3. For a real Google search **from GitHub**, also provide the existing
   read-only `GOOGLE_SERVICE_ACCOUNT_JSON` credential with access to
   the Vacature Register. Without it, source activation cannot be
   verified and the scan is blocked. Never paste secrets into chat,
   commits, logs, issue comments or source specs.

## 2. Use the manual GitHub workflow

Open [Actions](https://github.com/Yolol100/vacature-engine/actions),
select **Free Google vacancy discovery**, and click **Run workflow**.

- `check` (default): verifies that a key is configured and the SerpApi
  account API confirms an active, **zero-price Free Plan**. **No paid
  Google search request** is sent.
- `1 page per query`: up to four Google search requests.
- `3 pages per query`: up to twelve requests.
- `10 pages per query`: up to forty requests.

The adapter confirms remaining monthly free searches, an additional
10-search reserve and the hourly quota before issuing a search. Only
an active free account with `plan_id=free`, a zero monthly price and
at most 250 included monthly searches is accepted. Unknown, expired
or paid plans fail closed. SerpApi's free-account lookup is itself
free according to the provider. <https://serpapi.com/account-api>

The workflow is manual-only, serialized and has `contents:read`
permissions. No timer, recurring task or automated application is
started. It produces an optional temporary artifact containing
**unverified discovery observations**, not an application list.
It does not update the Vacature Register.

## 3. Local execution (with registry preflight)

Use a Python >=3.11 environment with `vacature-ingestion` installed.
Supply both secrets via a local secret manager or environment,
never a committed file.

```bash
python -m vacature_ingestion filter-specs \
  --specs ingestion/source-specs.google-optional.json \
  --spreadsheet-id "$VACATURE_REGISTER_ID" \
  --out /tmp/active-google-specs.json

python -m vacature_ingestion ingest-many \
  --specs /tmp/active-google-specs.json \
  --state /tmp/google-discovery-state.sqlite3 \
  --out /tmp/google-discoveries.json
```

The first command requires `GOOGLE_SERVICE_ACCOUNT_JSON` with read-only
access to the live Register; otherwise the scan must **not** proceed.

## 4. What discovery actually means

- Up to ten Google organic-results pages per search term (the four-query example allows up to 400 unique candidates), subject to
  the explicit overall request budget and real search availability.
- Pages are visited **round-robin across distinct search terms** so
  the first term cannot starve the rest. Duplicate URLs and tracking
  parameters are removed.
- `time_range=day|week` uses `tbs=qdr:d|w`. Google result dates,
  indexed dates, sitemap dates and first-seen times **never** establish
  the employer's original job-posting date.
- Results carry optional ATS URL hints (e.g. Ashby, Greenhouse, Lever)
  without automatically activating the employer or proving legitimacy.
- Search result omissions, errors or incomplete pagination never
  mark an employer's vacancy as closed.
- Every promising result still requires official role/employer evidence,
  a current application route, verified publication date, fully remote
  work possible from the Netherlands, Dutch/English language,
  CandidateEvidence fit and deduplication with `Vacatures`,
  `Applications` and `Feedback` before it can be recommended.

## 5. Why not scrape Google with Playwright?

The older `Yolol100/browser-search` project documented Google
blocking automated traffic. This implementation does not attempt
CAPTCHA bypass, proxy rotation, fingerprint spoofing or anti-bot
circumvention. Free ATS APIs and feeds remain the default discovery
route. Never activate a paid SerpApi plan to make this work.

The independent JobHive manifest was checked in October 2026 and
reported a September 2, 2026 generation date. Its historical
snapshot is **not** used as proof of current publication dates.

## Testing

```bash
python -m unittest discover -s ingestion/tests -p 'test_*.py'
python -m unittest discover -s tests -p 'test_*.py'
python scripts/mutation_smoke.py
```

The regression suite uses mocks; it never spends API quota. A real
search must be initiated manually and requires a currently valid key
and active registered source.
