# vacature-engine repository agent contract

## Scope
- This repository provides deterministic vacancy normalization, filtering/ranking helpers and an isolated public-ingestion component for `vacature-search`.
- The live Vacature Register and `vacature-search` remain authoritative for candidate evidence, source policy, application state and user-facing application content.
- `webactueel-workflow` remains the cross-skill controller; this repository must not become a second scheduler or policy owner.
- Never infer candidate experience, application status, work authorization or sensitive facts.

## Agent capability and impact policy
- Classify every intended action as `read_only`, `safe_write` or `high_risk_write`.
- `read_only`: inspect/search/test without external mutation.
- `safe_write`: bounded, reversible repository/runtime changes with preflight, deterministic inputs and exact readback.
- `high_risk_write`: submissions, mailbox mutation, account creation, destructive changes, permission/security changes, production deploys or broad external mutation. These remain outside the engine unless an owning workflow explicitly authorizes them.
- Tool availability or green CI never expands repository authority.

Before non-trivial source changes, build a bounded impact context from changed paths, direct imports/dependencies, contracts and affected tests. Generated code graphs or indexes are commit-bound evidence/cache only and never replace the Vacature Register, project sources or candidate evidence.

GitHub Trending and external repositories are discovery-only. Reuse patterns only after owner-fit, current primary/official verification where needed and license/usage-rights review. Do not import job-board source policy, candidate data or mutable platform assumptions from trend repositories.

## Validation
Run the repository's existing deterministic, boundary, property/metamorphic and adversarial tests for every affected behavior. Preserve the separation between ingestion state, engine policy and caller-owned application workflows.
