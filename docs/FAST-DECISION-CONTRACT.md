# Fast decision contract

Purpose: keep normal vacancy runs fast without moving source policy into the repository.

## One decision path

`Vacature Register -> fast-lane discovery -> dedupe -> official verification -> authenticity -> hard gates -> vacature-engine -> compact output`

- The live `Vacature Register` owns active sources, the fast-lane list, policy and cross-run state.
- `vacature-search` performs discovery, semantic verification, authenticity and candidate-evidence checks.
- The fast lane stops when the configured verified target is filled; if it is short, the Skill expands through the remaining active registry.
- `vacature_engine` receives only normalized candidates and applies deterministic canonicalization, hard gates, score anchors, selection and sorting.
- `ingestion/` may acquire technical observations only from sources that are active in the live registry.
- The repository never owns creator/YouTube advice, changing source priorities, candidate facts, application state or user-facing prose.

## Compact user result

The normal caller output is limited to:
`title, employer, fit reason, direct official URL, date, salary status, discovery source`.

Extra provenance remains internal unless it changes a decision or explains a warning/blocker.

## Safety

Early blockers should stop downstream work. No layer may weaken remote/geography/language/WordPress/authenticity/evidence gates to fill the requested result count.