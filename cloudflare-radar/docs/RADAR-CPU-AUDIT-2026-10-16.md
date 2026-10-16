# Webactueel Vacature Radar — functionele QA, CPU en release-audit

Datum: 2026-10-16. Controller: `webactueel-workflow`; domeinowner: `vacature-search`.
Repository: `Yolol100/vacature-engine/cloudflare-radar`.

## Scope, gezag en veilige nulmeting

Dit rapport betreft uitsluitend de bestaande **review-only** Cloudflare D1-gecheckpointte pipeline. Het werk is niet de productie-Google-Sheets delivery-route en verstuurt geen sollicitaties. Operationele bronwaarheid blijft live `Vacature Register` (Config, Bronnen, Vacatures, Applications, ApplicationEvents); Cloudflare D1 bewaart 26 eerder geverifieerde baseline-observaties. GitHub is implementatie- en testbewijs, niet de zakelijke bron van waarheid.

Live vóór de integrale canary:
- `RADAR_ENABLED=0`; `RADAR_PIPELINE_MODE=off`; Google OAuth blijft een `secret_text`-binding.
- Exact één bestaande `* * * * *` Cron, geen publiek triggerendpoint.
- 26 `baseline` records in `radar_observations`, nul eerdere `micro:v2:` testrecords.
- Live register: 353 Vacatures-rijen (351 ID's), 196 Applications-rijen (192 ID's), 167 ApplicationEvents-rijen.
- Google Radar outputtabs `Nieuwe vacatures` en `Runs` bevatten uitsluitend kolomkoppen.
- Formeel CPU-budget: Cloudflare Free Cron **10 ms per invocation**; D1 Free **50 subrequests per Worker invocation**. Een Cloudflare `outcome=ok` bij `cpuTimeMs>=10` is geen pass.

Documentatie: https://developers.cloudflare.com/workers/platform/limits/ ; https://developers.cloudflare.com/d1/platform/limits/ ; https://developers.cloudflare.com/d1/best-practices/use-indexes/ ; https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGet .

## Testscenario's en acceptatieregels

| ID | Scenario | Oracle/evidence | Geldige uitkomst |
|---|---|---|---|
| A01 | Disabled / gedeeltelijke schakelaars | `preview-gate.test.mjs`, live bindings | Geen D1, Google of ATS-I/O |
| A02 | Geen publieke testtrigger of extra Cron | HTTP `fetch` 404, live schedules | Eén Cron, geen externe uitvoerroute |
| A03 | Geheimhouding Google-auth | OAuth unit tests + Worker bindings | Geen credentials/tokens in D1, repo, logs |
| A04 | Bronstatus bron én werkgever | Active/inactive/duplicate header tests | Alleen actuele allowlisted bronpaar |
| A05 | 353 Vacatures-rijen in pagina's | 353-rijen integratiefixture, echte paginacheckpoints | Elke rij behouden; max 32 per Cron |
| A06 | Capaciteitsoverschrijding of verkeerde header | Fail-closed grens-/headertests | Geen ATS, geen review-receipt |
| A07 | Missing vacancy-ID bij submitted application | Strong URL-key regressie | Geen herpublicatie van ingediende rol |
| A08 | Radar-URL bij lege observation_key | URL-only regressie | Geen dubbele rol |
| A09 | Applied/known via events, Applications, Vacatures | Integratie tegen URL/role keys | Exclude applied & previously known |
| A10 | Overlap en interrupted D1-claim | Race, lease, replay, forged-claim fixtures | Single writer, max één retry |
| A11 | Crash na opgeslagen historiepagina | Persisterende page CAS test | Hervatten volgende pagina zonder reread |
| A12 | 429, 503, corrupt payload of verlopen cyclus | Fault-injection fixtures | Fail closed; 5xx hoogstens één retry |
| A13 | Nieuwe kandidatuur alleen voorlopig | `candidate_screen`, `review_only` | `manual_review_required=true`; geen applicant action |
| A14 | Eenmalige tijdelijke CPU-test | D1 marker én testvariabele, exact expiry | Nooit tweede broncyclus, geen publiek endpoint |
| A15 | Geen testresten of zakelijke writes | Live D1 + Google Sheets + bindings/schedules | 26 intact, geen v2, nul output |
| A16 | CPU Free prestatienorm | Observability `$workers.cpuTimeMs` per fase | Elke representatieve invocation strikt **<10 ms**, streven <=7 |
| A17 | CI en beveiliging | GitHub Radar, CodeQL, Python matrix, Wrangler bundle | Alles groen, geen vermeden fouten |

De testset is een deterministische functionele en adversariële oracle. Zij is geen vervanging voor runtime-CPU-telemetrie. De bijbehorende implementatie-PR's: #107 (OAuth en bronstatus), #110 (D1-only bootstrap), #113 (paged crash recovery), #114 (URL-only duplicaten), #115 (tijdelijke volledige CPU-audit). De testcode van de tijdelijke canary wordt door #116 verwijderd; de 353-rijen regressietest blijft.

## Historisch runtime-CPU-bewijs

| Fase | Eerdere live CPU-waarden | Interpretatie |
|---|---|---|
| `source_gate` inclusief eerste cyclus | 18, 10, 13 ms | Harde Free NO-GO |
| 64-rijen geschiedenis-pagina | 7, 9, 8, **11 ms** | Naar 32 rijen verlaagd |
| D1-only cyclusbootstrap | 3 ms | Eén succes, niet representatief |
| `source_gate` ná D1-only bootstrap | 9 ms | Eén succes, weinig marge |
| Eerste pagina van 32 rijen | 9 ms | Eén succes, weinig marge |
| Geschiedenis-ID-grenscontrole | Wel checkpoint, geen gekoppeld CPU-log | Niet bewezen |
| Alle overige fasen | Nog niet volledig live gemeten | Blokkade voor GO |

## Integrale ketenmeting en formele einduitspraak

De privé canary onder #115 gebruikt een uit zichzelf aflopende D1-marker (maximaal 29 minuten) en slechts één cyclus. Zonder marker is hij inert. Bij een runtime-overtreding: marker direct intrekken; test-eigen `micro:v2:`-sleutels opruimen; vorige geverifieerde non-canary Worker herstellen; 26 D1-baselines, Sheet-headers, bindings en Cron teruglezen; canarycode en configuratie via #116 opruimen.

**Status tot er herhaald live bewijs is voor álle fasen: NO-GO.** Ook succesvolle review-only tests leveren geen automatische vacaturepublicatie; productieactivatie en idempotente delivery vereisen een afzonderlijke expliciete vrijgave en bronhercontrole. Een mathematische garantie onder 10 ms voor willekeurig grote of veranderende cloudworkloads bestaat niet.

## Post-task leermoment en regressiebeleid

Bewaar goedgekeurde fixture-tests voor bewezen incidentklassen: onderbroken paginacheckpoints, lege vacature-ID met sterk URL-bewijs, Radar-URL zonder key. Houd `NO_CHANGE` voor reeds groene scopes. Een nieuwe CPU-hypothese vereist eerst primaire platformdocumentatie en een reproduceerbare failure, daarna minimale fix, CI, beperkte runtime-canary, rollback en een aparte auditclaim.


## Integrale audituitvoering 18:33–18:43 UTC: NO-GO met veilig herstel

De eerste acht minuten van de volledige één-cyclusproef zijn door de bestaande Cron uitgevoerd. D1 bevestigde de eerste vijf geschiedenischeckpoints en Cloudflare Observability registreerde:

- 18:34 bootstrap **3 ms**; 18:35 `source_gate` **9 ms**; 18:36 grenzen **9 ms**.
- 18:37 eerste historiepagina **7 ms**; 18:38 tweede pagina **7 ms**; 18:39 derde pagina **7 ms**.
- 18:40 vierde pagina checkpointed, **geen gekoppelde CPU-log** (niet als pass tellen).
- **18:41:05: 10 ms CPU** bij de historiepagina na `history_next=129` (dus geen marge).

De stop- en rollbackgate is uitgevoerd: 18:41:37 D1-permit weg; alle zeven tijdelijke v2-checkpoints gewist; 26 observaties status `baseline` intact; Worker terug naar non-canary versie `ab2afcf7-6b5b-4293-8d72-9962ddfa934a` via Cloudflare deployment `c770b3a4-cb15-4fb6-a8bd-204d4bf00544`. Een tijdelijke testvariabele mag na GitHub-cleanup niet meer in de Worker-settings voorkomen (expliciete post-deploy readback vereist). Niets is naar de business-Google-Sheets geschreven.

**Open CPU-work (hard):** reduceer geschiedenis naar maximaal **16 rijen per Cron**, controleer duur/capaciteit en optimaliseer de latere paginaconcentratie tot één begrensde `SELECT ... IN (?,...)`-query (PR #117). De resterende procesfasen `application_rows`, `event_rows`, `application_index`, `radar_history`, `official_ats`, `candidate_screen` en `review_only` zijn **niet live in deze cyclus bereikt**. De eindstatus blijft expliciet **BLOCKED/NO-GO voor Free-budgetvrijgave**, ook bij groene functionele tests.

De bijgevoegde 353-rijen integratietest blijft na het verwijderen van de tijdelijke canary bestaan om toekomstige regressies aantoonbaar te stoppen.


## Correctie na CPU-grens, versie 16-rijen (PR #118)

Na de 10ms-uitvoering met 32 rijen op 18:41 UTC is de **volgende niet-automatisch geactiveerde codeversie** gewijzigd naar maximaal 16 Google-historierijen per Cron. Het blijft één bestaande Cron; de dag- en broncontroles zijn niet omzeild. Om de oorspronkelijke maximale 1.536 geschiedenislijnen volledig te blijven scannen, is uitsluitend de review-only cyclus-TTL op 135 minuten gebracht; er is een expliciete fail-closed grens boven 1.536. Dat langere interval is **niet** geschikt als atomaire bronwaarheid voor toekomstige levering, waarvoor een nieuwe live status-/sollicitatiecheck vereist is.

De eindassemblage gebruikt nu één geïndexeerde `SELECT name,value ... WHERE name IN (?,...)`-query met hoogstens 96 D1-parameters in plaats van 96 losse Free-subrequests. Per pagina worden cyclus-ID, verwachte rijlengte en de volledigheid gecontroleerd; één ontbrekende pagina verhindert een review-receipt en elke ATS-call. Een nieuwe gesimuleerde maximum-capaciteitstest verifieert 1.536 rijen en één D1-assemblagequery.

Dit is een functionele/budgetmatige codewijziging. **Zij bewijst nog geen echte CPU <10ms voor alle fasen.** De formele GO-poort blijft geblokkeerd totdat een volgende controle met herhaalde koud/warm-samples en alle 9 fasen (met acceptabele marge) slaagt.


## Hercontrole 16-rijenversie, 19:42–19:55 UTC: GraphQL ontdekt gemiste CPU-overtredingen

Na [PR #118](https://github.com/Yolol100/vacature-engine/pull/118) werd de 16-rijenversie zelfstandig op de echte Cloudflare Free Worker beproefd via tijdelijke privé-PR #119, zonder productieradar, extra Cron, publicatie of sollicitatie. De D1-marker had de exacte waarde `one-16row-review-20261016` en een vaste vervaltijd. De code mocht slechts één review-cyclus starten. De permanente gegevens (26 `radar_observations` in status `baseline`) bleven onaangeroerd.

**Belangrijk nieuw meetinzicht:** Cloudflare Workers invocation logs kunnen bij een gewone `events`-query ontbreken of laat binnenkomen. Een onafhankelijke tweede bron, de **Cloudflare GraphQL Analytics API** `workersInvocationsAdaptive` met `dimensions.datetime`, maakte de CPU-tijd **per echte minuutuitvoering** zichtbaar. De `cpuTimeP99`-waarden zijn in **microseconden**; bij één request per tijdstip geeft het gedeeld door 1.000 de CPU-milliseconden.

| UTC | Review-only stap | GraphQL werkelijke CPU |
|---|---|---:|
| 19:42 | D1 bootstrap | 5,052 ms |
| 19:43 | Live geregistreerde broncontrole | 7,626 ms |
| 19:44 | Historie ID-grenscontrole | 6,717 ms |
| 19:45 | Pagina 1–16 | 9,613 ms |
| 19:46 | Pagina 17–32 | 8,765 ms |
| 19:47 | Pagina 33–48 | 8,044 ms |
| 19:48 | Pagina 49–64 | 8,409 ms |
| 19:49 | Pagina 65–80 | 8,117 ms |
| 19:50 | Pagina 81–96 | 7,811 ms |
| 19:51 | Pagina 97–112 | 7,503 ms |
| 19:52 | Pagina 113–128 | 8,596 ms |
| 19:53 | Pagina 129–144 | **10,685 ms — NO-GO** |
| 19:54 | Pagina 145–160 | **11,297 ms — NO-GO** |

Voor alle 13 getelde GraphQL-uitvoeringen werden **nul errors** gerapporteerd. Juist daarom is `outcome=ok`, `errors=0` of ontbrekende invocation-log **niet gelijk aan CPU-compliance**. GraphQL is nu verplicht als onafhankelijke CPU-controle in elke toekomstige canary. Dit is géén afgeronde nine-stage review: de proef stopte nog in de historiepagina's en bereikte `application_rows`, `event_rows`, `application_index`, `radar_history`, `official_ats`, `candidate_screen` en `review_only` niet.

**Veilig herstel (uitgevoerd):** de privémarker is om 19:55:17 UTC ingetrokken; de geverifieerde non-canary Worker `711358ea-e181-4c67-8eae-1143c038d478` werd teruggezet via Cloudflare deployment `d9730936-a6a1-46ce-a5a5-01e9b614e354`; daarna zijn **13** test-eigen `micro:v2:`-record(s) verwijderd en alle **26 baseline-records** blijven staan. Cleanup-PR #120 herstelt de vijf tijdelijke repository-bestanden byte-identiek naar de vorige non-canary commit. Een finale settings-readback moet tevens de tijdelijke `RADAR_CPU_CANARY`-binding verwijderen.

**Einduitspraak: HARD NO-GO op Cloudflare Free.** Ook 16 rijen kunnen 10 ms overschrijden. Verdere halvering of paginering is geen mathematische garantie op altijd minder dan 10 ms vanwege vaste OAuth-/runtimekosten en cold starts; niet blind productie activeren. Een nieuw ontwerp zou apart de te hoge CPU van koude externe bronleesstappen moeten verminderen, historieverwerking/aggregatie fijnmaziger maken en herhaald runtimebewijs voor elke fase leveren, zonder geheimen in D1 of ontbrekende historie. Review-only is bovendien geen geteste idempotente productie-outputroute. Het eerlijk geverifieerde eindresultaat is daarom **veilige code-/regressieverbeteringen afgerond, Free CPU-activering geblokkeerd**.

Primaire bronnen:
- https://developers.cloudflare.com/workers/platform/limits/ (Free scheduled 10ms CPU; `ok` kan tijdelijke flexibiliteit bevatten).
- https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-workers-metrics/ (per-invocatie GraphQL dimensie en CPU-kwantielen).
- https://developers.cloudflare.com/d1/platform/limits/ (D1 Free-query's per Worker en max 100 parameters).


## Isolatie van de actieve Workers-bundle (nieuwe optimalisatie)

Aanleiding is de live GraphQL-afwijking **10,685/11,297 ms** terwijl 16-rijenpagina's volledig functioneel bleven. De actieve Worker bundelde eerder onnodig de oude `tick`-bezorgcode en de daarin gebruikte append-/reconciliationfuncties. Meetbasis uit de eerdere GitHub Actions `wrangler deploy --dry-run`: **57,05 KiB**, gzip **14,54 KiB**.

De nieuwe `src/review-worker.mjs` is geen extra scanner/Worker of scheduler. Het is de enige deployment-ingang van de bestaande `vacature-radar`; hij importeert uitsluitend bestaande review-only processor, bestaande gezondheidssanitizer en hergebruikte Google/ATS-leeshelpers. `src/index.mjs` behoudt de oudere `tick` voor tests als compatibiliteitsmodule, maar is **niet** de Worker-`main`. Helpers zijn gedeeld zodat auth-, bron- en idempotentiegedrag niet gedupliceerd worden. Het testschema verifieert exact één Cron, beide productieschakelaars op uit, geen publiek endpoint, afwezigheid van import uit de legacy-ingang en functiegelijkheid bij de OAuth-/Sheets-tests.

Deze refactor lost potentieel onnodige koude V8-compile/initialisatiekosten op maar **garandeert geen reductie van HTTP-, Google-serviceaccountsleutel- of D1-CPU**. Vrijgave vereist vooraf een kleinere, groene bundle, vervolgens een strikt aflopende afgeschermde real-world CPU-proef met log én GraphQL (per datetime één invocation), de originele 26 baselinewaarnemingen, geen Google-Sheetrijen, alle foutscenario's en rollback bij **>=10ms**. Productieradar blijft NO-GO.


## Afzonderlijke D1-checkpointoptimalisatie — hypotheses, geen CPU-vrijgave

De reeds gemeten 16-rijen- en slankere-bundle-cpu-proeven bleven hard **NO-GO** (respectievelijk historie 10,685/11,297 ms en Google `source_gate` 11,700 ms). Een nieuw, strikt minimaal checkpointverbeterpunt: schrijf paginaresultaat plus verwachte control-CAS met één `db.batch()` naar D1. De eerste statement bevat een conditionele `EXISTS(name=control, value=claim)` om te voorkomen dat een verloren claim toch een paginarecord opslaat; de tweede verplaatst de cursor. De API is volgens de officiële D1-documentatie transactioneel, met rollback bij mislukte SQL-statements. Negatieve tests simuleren precies het verloren eigendom en een mislukking tussen beide SQL-statements. De bestaande harde garanties blijven: 26 D1-baselines, geen dubbele sollicitatie, geen Google-Radarwijziging en beide prodflags uit. Dit verlaagt mogelijk D1-latentie/orchestration, maar is **niet** hetzelfde als bewezen 10ms CPU-compliance of voltooiing van nog niet gemeten reviewfasen.
