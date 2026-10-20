# Source coverage and bounded Google discovery

**Operational truth:** Live `Vacature Register` tabs `Config` and `Bronnen`.
GitHub is not a vacancy-search entrypoint. GitHub Actions runs only CI.

On an explicit ChatGPT `vacature-search` request:
1. Read the live policy and active source IDs; record real attempts, not
   theoretical or cached counts.
2. Search employer/ATS first; Google and existing free feeds are supplemental
   and never automatically prove authenticity, age, NL eligibility or fit.
3. Use bounded, rotating X-ray/source expansion. Stop once the verified output
   target is met; unverified observations must not stop expansion.
4. If a provider fails, report `unknown/blocked`, never zero opportunities.
   Do not modify source priority from a failed index check.
5. Keep public source observations separate from private CandidateEvidence.
   Source-health updates require owner authorization and readback.

The optional `scripts/one_pass_vacancies.py` is a technical helper called only
within an authorized on-demand workflow. It is not a scheduler or separate
policy owner. `source-specs.deploy.json` and `source-specs.google-optional.json`
are technical source targets filtered by the Register, not a second registry.
