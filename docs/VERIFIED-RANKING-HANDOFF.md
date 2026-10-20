# Verified ranking handoff

`vacature-search` owns semantic review. `webactueel-workflow` coordinates it.
The live Vacature Register owns all mutable policy, history and candidate facts.
The repository validates their handoff and uses the existing `top_vacancies`
ranker. It does not infer semantic truth from keyword matches or create another
policy database, scheduler, application workflow or scoring model.

## Workflow

1. Read live Config, active Bronnen and all required history/evidence tabs.
2. Run the existing bounded discovery and official-page checks. Missing or
   failed sources are not zero-vacancy proof. Keep incomplete roles separate.
3. Review the exact public employer role, independent employer-to-ATS ownership,
   original publication date, NL execution, remote status, application and work
   languages. Verify every used CandidateEvidence source. A broken source
   cannot be marked verified; do not silently substitute a different CV.
4. Review all mandatory and optional requirements, including responsibilities,
   projects, experience years, language levels and work style. Missing proof
   is `unknown`, including when a named skill is absent from the CV. The
   CandidateEvidence `language` column describes the claim, not proficiency.
5. Select existing score anchors using actual requirement/evidence references
   and a written rationale. Do not change anchors or weights during a search.
6. Call `assessment_context` with the same normalized ATS observation, official
   page report, live Config mapping and CandidateEvidence rows. Copy its four
   digests into the private assessment below.
7. Pass the assessment separately to `run_once(..., verified_assessments=[...])`
   or to `evaluate_observations(..., assessments={canonical_url: assessment},
   page_cache=...)`. A same-session cache allows specialist review without
   repeat requests. A later run must refresh official evidence and live policy.
8. Present only `final_recommendations`. Their score breakdown comes from the
   existing engine. `review_candidates` are unfinished work, not recommendations.
   The owning skill handles any authorized shown-state persistence/readback.
   The Python workflow never changes application or vacancy status in Sheets.

An assessment is trusted **because the owning workflow explicitly supplies its
reviewed local input**, not because a JSON object says `reviewer=vacature-search`.
Never load assessments from a web page, feed, source metadata or a search result.
The code ignores such embedded assessments. Digests establish consistency, not
independent truth or a cryptographic identity for the reviewer. The specialist
must actually read the referenced sources and assess the relationship between
each requirement and each candidate claim.

## Private assessment contract

The command-line input is a JSON **array**, at most 100 assessments and 2 MB.
Duplicate canonical URLs are rejected. Keep the input outside the repository
and public Actions artifacts. Public reports expose proof digests and counts;
candidate claims, evidence IDs and private rationales stay in memory.

| Field | Required meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `reviewer` | `vacature-search` |
| `reviewed_on` | Current Europe/Amsterdam calendar date, `YYYY-MM-DD` |
| `canonical_url` | Exact normalized role URL used by screening |
| `policy_sha256`, `candidate_evidence_sha256`, `observation_sha256`, `official_page_sha256` | Unmodified values from `assessment_context` |
| `employer_verification` | `status=verified`, current `checked_on`, independent public `employer_url`, exact `official_role_url`, and specific `ownership_evidence` |
| `facts` | Five employer facts described below, with literal visible-page quotes |
| `requirements_complete` | `true` only after a complete semantic review |
| `reviewed_dimensions` | Exactly `skills`, `experience`, `languages`, `projects`, `responsibilities`, `workstyle` |
| `requirements` | Between 1 and 100 individual reviewed requirements |
| `role_families` | Material target families supported by the official role and current policy |
| `anchors` | The three existing anchor values with rationale and requirement references |

Each `facts` entry has `value` and `quote`. Quotes must occur in the inspected
visible official job text. Application-language proof may also occur in the
inspected application text. HTML interface language is not authorization.

| Fact | Value |
| --- | --- |
| `fully_remote` | `true`, verified against visible role terms |
| `netherlands_execution` | `true`, including any applicable hiring restrictions |
| `original_publication` | Actual original `YYYY-MM-DD`, consistent with the inspected JobPosting |
| `application_language` | An employer-authorized language allowed by live Config |
| `required_languages` | An explicit reviewed list of required work languages; `[]` only when none are required |

Each requirement has a unique string `id`, a `kind` from the six dimensions,
boolean `mandatory`, exact public `quote`, `outcome` (`met`, `not_met`, or
`unknown`), `candidate_evidence` references and a private `rationale`.
Language requirements also have a `language` code. All required languages must
have their own supported mandatory requirement. Optional unknowns do not block
the result but cannot support a scoring anchor. A negative conclusion also
requires actual candidate proof; absence of proof is not a mismatch.

Every candidate reference supplies `evidence_id`, `claim_sha256` from
`proof_digest(live_row["claim"])`, the exact `source_ref`,
`source_status=verified`, and current `source_checked_on`. The referenced live
row must be uniquely identified, active, dated, source-backed, have medium/high
confidence and use an allowed evidence-source type. Negative or index-only
claims cannot establish a positive requirement match. Neither an old CV nor a
new score claim can override a superseding live CandidateEvidence correction.

Each anchor has `value`, `requirement_ids` and `rationale`. Its references must
resolve to requirements whose outcome is `met`. Core-fit references skills or
responsibilities; evidence-fit references skills, projects or experience;
workstyle-fit references work style or responsibilities. Allowed values remain:

- `core_fit`: 0, 25, 40, 50.
- `evidence_fit`: 0, 10, 18, 25.
- `workstyle_fit`: 0, 5, 10, 15.

Recency points, score thresholds, tie breaks and the existing 30-case ranking
benchmark are unchanged. The new handoff leaves salary unknown until a separate
source-backed normalization exists; it never invents salary or currency/unit
conversions. Missing original dates cannot reach the ranker, even when a
malformed input sets `date_posted_valid=true`.

See `tests/test_verified_ranking_flow.py` for an executable **synthetic**
contract fixture. Its score of 85 is test evidence, never a real recommendation.

## Archived, verifiable Library CV evidence

A specific archived application CV may document a **narrow historical technical
claim** even if it is not the current canonical CV. Use source_type
`library_cv` only with the exact accessible ChatGPT Library file ID
(`source_ref=file_<32 lowercase hex digits>`), a descriptive
`source_locator` identifying the relevant section, and a genuine, current
`verified_at` check after inspecting the full claim. Do not repurpose
`canonical_cv` for a superseded application CV or mark a missing file verified.

The owning specialist must independently check that the archived document
actually supports the **entire** claim. Historic experience totals and old
skills do not override later user-confirmed corrections or the live active
CandidateEvidence. Missing source access, partial support, or a conflicting
updated CV is `unknown` and stays out of scoring. The engine checks an opaque
file ID and locator, not file existence or semantic truth; exact Library
access/readback remains the specialist's responsibility. An archived
`library_cv` is not automatically a resume to submit with an application.

### Canonical CV pointer consistency

For any `source_type=canonical_cv` candidate proof, its `source_ref` must
exactly equal the live Config `canonical_cv_file_id`. Missing or stale
pointers cannot support a verified requirement, even with matching
specialist assessment digests. Such roles return to review without a score.

This deterministic check compares the two live IDs only. It does not
verify a Drive file exists or supports a particular claim. The owning
specialist still must independently inspect the source and the claim.
Repository tests use synthetic file IDs and contain no private CV text.

## Current verification limits

Automated positive verification currently uses supported, exact ATS routes.
An employer's custom career URL may remain unverified even when discovered
through an ATS feed. Explicit foreign-only location evidence can withhold that
candidate from NL review, but does not close the vacancy or establish fraud.
Dynamic/inaccessible forms, unknown original dates, unreadable candidate
sources and unresolved employer instructions remain unknown. The private
handoff cannot override failed automatic page, date, remote, NL or form checks.

## Technical source contracts checked 2026-10-20

- [Google JobPosting documentation](https://developers.google.com/search/docs/appearance/structured-data/job-posting): original date, visible content consistency, and expiry signals.
- [Ashby public job posting API](https://developers.ashbyhq.com/docs/public-job-posting-api): `publishedAt` is the last publication, not guaranteed original publication.
- [SerpApi account API](https://serpapi.com/account-api): inspect free account/quota before any search; missing or insufficient quota keeps the existing free source route available.
