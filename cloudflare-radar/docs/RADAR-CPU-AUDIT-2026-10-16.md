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
