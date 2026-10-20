# Register source health and private specialist boundary

Owner: live `Vacature Register:Bronnen`, coordinated by `webactueel-workflow`
with vacancy-domain decisions from `vacature-search`.

- Source health is evidence-only until authorized. Missing `last_success_at`
  is **unknown**, not proof of failure; preserve `active` under
  `source_health_unknown_policy=neutral_until_min_observations`.
- Do not retire or consolidate without the required real observation count,
  historical shown/submitted contribution check and verified replacement
  (when consolidating). Worldwide discovery must remain available.
- Use actual timestamped attempts, safe failure categories and direct
  employer/ATS verification. A search-index check is not an official listing
  check. Apply only approved changes, then read back exact rows.
- GitHub Actions is **offline CI only**. Previous public discovery workflows,
  downloadable Actions review queues and review artifacts are no longer
  operational sources.
- CandidateEvidence is private; do not commit, echo in public artifacts or
  infer candidate claims from GitHub output.
- `vacature-engine` can canonicalize, gate and rank normalized candidates;
  live policy, semantic verification and application outcomes remain in
  the Register/`vacature-search`.

Source review is requested through ChatGPT. No automated application, source
activation, or background vacancy search is permitted.

## Verschil tussen twee brongezondheidsmetingen (fase 26)

- `registry_active_sources_without_success`: aantal actieve bronnen zonder
  ooit geregistreerde `last_success_at`. Dit is de juiste telling voor de
  open auditlijst, niet automatisch een tekortkoming van de bron zelf.
- `registry_active_sources_with_failure_only`: deelverzameling daarvan met
  een geregistreerde `last_failure_at`. Een oude mislukking is geen bewijs
  van actuele irrelevantie, en een succesvolle website-opening zet geen teller.
- `registry_active_sources_without_health_time`: deelverzameling zonder
  zowel succes- als fouttijdstempel (oude, behouden indicator).

Voor de nulmeting op 2026-10-20 waren dit respectievelijk **53, 3, 50**.
Publieke endpoint-inspectie en een ATS-jobboardlinktelling zijn **bronbewijs**,
niet automatisch een gevalideerde `source_attempts` van de adapter.
De read-only `source_health_handoff` blijft `auto_write=false`, en kan
geen timestamps bijwerken zonder een geldige, aan de bron gebonden
provider-attempt. Historische bronnotities blijven behouden.

## Routegebonden gezondheidsindicatoren (fase 29)

Een bron zonder een `last_success_at` is niet vanzelf een defecte technische
adapter. De on-demand engine heeft alleen voor geregistreerde, goedgekeurde
provider-/werkgeverparen een directe technische route. Andere actieve
discoverybronnen lopen via openbare zoek-/X-ray-controle, niet via de adapter.

- `registry_active_sources_without_success_provider_routable` telt alleen
  bronnen in `public_adapter` of `free_google_optional` met nog ontbrekend
  bewijs. Verifieer vóór uitvoering altijd live `Bronnen.status`.
- `registry_active_sources_without_success_by_route` laat de onderverdeling
  van alle actief-onbemeten bronnen zien. Routes zonder bewezen dekking blijven
  `unclassified`, nooit automatisch `public_adapter`.
- De historische bruto `registry_active_sources_without_success` blijft
  bestaan voor backwards-compatibele rapportage. `auto_write=false` en
  de bestaande restricties voor health-tijdstempels blijven gehandhaafd.

Op 2026-10-20, na geslaagde fases 27–28: **50 actieve bronnen zonder
geregistreerd technisch succes, nul daarvan met een geconfigureerde directe
adapter**. Een begrensde openbare pagina-audit gaf 31 publieke antwoorden,
7 HTTP-fouten (waarvan vijf HTTP 403) en 12 netwerk-/TLS-fouten. Dat zijn
**paginaobservaties**, geen adapter-ingesties of mislukte provider-runs;
wijzig daardoor geen succes-/fouttellers en retire geen bron zonder het
voorgeschreven historische en actuele bewijs.
