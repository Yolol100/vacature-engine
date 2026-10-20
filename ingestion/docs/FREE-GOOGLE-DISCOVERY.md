# Free Google discovery (ChatGPT-only)

The active `Vacature Register` is the only source of truth for source activation.
Only an active `google-jobs` row allows the optional SerpApi adapter.
There is **no GitHub Actions vacancy search** and no recurring scheduler.

## On-demand route

1. The user explicitly asks ChatGPT `vacature-search` to find vacancies.
2. Read live `Config`, active `Bronnen`, vacancy/application history and
   authorized CandidateEvidence.
3. Search official employer/ATS roles, then supplement with fresh Google/X-ray
   discovery. When SerpApi is available, use a verified zero-price Free Plan
   with a bounded quota check; never incur paid API charges. Without it, use
   approved alternative current web discovery, not a GitHub workflow.
4. Verify employer, exact official role, original posting date, fully remote
   execution from the Netherlands, NL/EN language and evidence-backed fit.
   Search snippets, first-seen and provider `updated_at` are not proof.
5. Deduplicate and rank with the deterministic engine; show only fully
   verified qualifying vacancies. No auto-submit, mailbox mutation or source
   activation.

`ingestion/source-specs.google-optional.json` is only a technical adapter
specification. Credentials must stay in a secret manager or an authorized
runtime, never in GitHub, chat, logs or this repository.

Offline tests (do not use credits):

```bash
python -m unittest discover -s ingestion/tests -p 'test_*.py'
python -m unittest discover -s tests -p 'test_*.py'
```
