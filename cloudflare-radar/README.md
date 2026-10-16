# Cloudflare Vacature Radar — voorbereid, niet live

Een **beperkte** Cloudflare Workers Cron-pilot die nieuwe openbare vacatures ophaalt, technische identiteiten bewaart in D1 en ontdekkingen in een afzonderlijke Google Sheet zet. Deze directory staat los van het Python-package `vacature_engine`; het bestaande Vacature Register blijft de enige bron voor beleid, bronstatus en sollicitatiehistorie.

**Huidige configuratie: `RADAR_ENABLED=0`.** Dit is geen live monitor, geen direct-apply-systeem en geen claim van volledige bron- of minuutdekking.

## Bewaakte proefbronnen

De pilot heeft precies drie geregistreerde werkgever-/ATS-routes uit `ingestion/source-specs.radar.json`: Automattic/Greenhouse, Kinsta/Lever en Zapier/Ashby. **Eén bron per cronuitvoering** wordt in een vaste rotatie gecontroleerd: bij drie actieve bronnen dus elke drie minuten per bron, terwijl de cron zelf elke minuut start. De bron én de werkgever moeten `active` zijn in live `Bronnen`. Status, headers en ATS-linkhost moeten geldig blijven. Buiten de whitelist worden geen andere bronnen bevraagd. Een API-fout, onbekende host, datalimiet of rate-limit wordt zichtbaar afgehandeld met source-specifieke cooldown. De radar gebruikt geen scraping, login of omzeiling.

## Resultaat

- Drive: `Vacatures/05 - Vacature Radar - Nieuwe matches`
- Sheet: `Vacature Radar - Nieuwe Vacatures` (tab `Nieuwe vacatures`), plus `Runs` en `Uitleg`.
- Nieuwe technische detecties zijn **geen** bevestigde geschikte vacatures. Alleen `vacature-search` controleert werkgever/ATS, volledig remote, uitvoerbaar vanuit Nederland, NL/EN en matchscore.
- `eerste_detectie_utc` is observatietijd, **niet** publicatietijd. `publicatie_bevestigd_utc` blijft leeg zonder officiële publicatie-evidence.
- Geen persoonlijk cv, sollicitatietekst of geadresseerde mailboxdata in Cloudflare; uitsluitend kandidaatvrije URL-/statushistorie uit het Register. Geen automatische verzending of sollicitatie.
- Eerder ingediende sollicitaties worden uit `Vacatures`, `Applications` én `ApplicationEvents` herleid. Nieuwe detecties worden alleen op sterke rolidentiteit uitgesloten. Als je later op een reeds gevonden vacature solliciteert, wijzigen uitsluitend de velden `sollicitatiehistorie` en `actie` in de radarrij; bestaande handmatige beoordelingen blijven behouden.

## Actuele Cloudflare-inrichting en veilige proef (2026-10-16)

- **GitHub:** `Yolol100/vacature-engine` op `main` is de broncode; Cloudflare Builds gebruikt al deze repository met root `cloudflare-radar`. Extra MCP of repository niet nodig.
- **Cloudflare:** Worker `vacature-radar`, eenminuut-Cron en D1 `vacature-radar-state` (EU) bestaan. De tabellen `radar_observations` en `radar_metadata` zijn ingericht.
- **Google Sheets:** `GOOGLE_SERVICE_ACCOUNT_JSON` is een Cloudflare **Secret**. Het serviceaccount is Lezer op Vacature Register en Bewerker op Vacature Radar. De API-toegang vanuit de daadwerkelijke Worker is op 16 oktober 2026 tijdens de eenmalige proef bewezen.
- **Uitgeschakeld:** `RADAR_ENABLED=0`, oorspronkelijke Register-config `radar_enabled=FALSE`. Dit mag voor de smoke-test **niet** op `1`.
- **Geen R2**, geen extra Cron, geen tweede monitor en geen automatische sollicitaties.

### Eerdere afgeschermde smoke-test (afgerond)

Op 16 oktober 2026 is de eenmalige privétest van Cloudflare, Google OAuth, lezen/schrijven/wissen van een lege testcel en Kinsta/Lever geslaagd. Het resultaat staat in D1 onder `smoke_result:2026-10-16`. De tijdelijke testcode en private D1-trigger zijn **na de tweede proef verwijderd uit de runtime**; er bestaat geen publieke testendpoint. De bewijsrecords blijven bewaard.

### Live testbewijs — 16 oktober 2026

**Bevestigd geslaagd**, daadwerkelijk uitgevoerd door de gedeployde Cloudflare Worker (GitHub-commit `07963d8aab138fa08595fe343c22f4427c728fb6`). De eenmalige Cron-proef begon `2026-10-16T09:00:03.530Z` en eindigde `09:00:09.251Z`. Het duurzame D1-resultaat `smoke_result:2026-10-16` vermeldt `status=ok`, `google_auth=ok`, `sheets_read=ok`, `sheets_write=ok`, `cleanup=ok`, `ats=ok` en **3** jobs van `lever:kinsta`. De aanvraag staat op `done`, zodat de Cron dit niet herhaalt. De testcode heeft geen openbare endpoint en verloopt na 17 oktober.

Onafhankelijke readback na afloop: `Runs!L1000` leeg, `Nieuwe vacatures` en `Runs` hebben uitsluitend hun kolomkoppen, `radar_observations` heeft 0 rijen, Cloudflare-secret `secret_text`, `RADAR_ENABLED=0`. Alle GitHub Radar checks, CI en Release Evidence voor de testcommit zijn geslaagd.

**Geen productie-activering:** de eenmalige proof-of-connection is gereed, maar baseline-ingestie van alle drie de bronnen, foutlogs/alerts, gemiste uitvoeringen en Free-tier CPU/quota moeten vóór `RADAR_ENABLED=1` worden gevalideerd. Vermijd dubbele schedulers en voeg voorlopig geen R2 toe.

## Betrouwbaarheid, observability en drie-bronnenbewijs

- **Productierun alleen met `RADAR_ENABLED=1`.** Wanneer uitgeschakeld, doet de Worker helemaal geen D1-/Google-/ATS-verzoeken. `monitoredTick` schrijft tijdens actieve runs de UTC-heartbeat (`health:last_started_utc`), laatste resultaat (`health:last_result`), laatste succes (`health:last_ok_utc`), laatste fout (`health:last_failure`) en zo nodig een onderbreking boven zes minuten (`health:last_gap`). Er worden geen privésleutels, cv's, sollicitatieteksten of andere kandidaatdata in health-metadata gezet.
- **Cloudflare Workers Logs en Issues staan aan**, inclusief invocation-logs bij volledige sampling. Voor Workers Free zijn in oktober 2026 200.000 logevents/dag en drie dagen logretentie beschikbaar. Actieve foutafhandeling gebruikt de bestaande broncooldowns, D1-pending-outbox, re-check tegen het Vacature Register en de radar-Sheet. Issues groepeert fouten. Een Worker kan een totaal gestopte Cron niet zelf signaleren; dit vergt een externe gezondheidscontrole.
- **Tijdelijke diagnoses zijn afgevoerd:** de eenmalige Google-auth-smoke en de driestaps-test stonden alleen privé via D1 open. De bijbehorende D1-resultaten blijven bewaard, de diagnostische modules en hooks zijn uit de runtime verwijderd zodat de Free Worker minder werk verricht wanneer hij uitstaat.
- **Drie-bronnenproef, 16 oktober 2026:** `reliability_result:2026-10-16` bevat `status=ok`, Google-auth `ok`, Sheets-lezen `ok` en drie onafhankelijke Cron-resultaten: Automattic/Greenhouse **12**, Kinsta/Lever **3**, Zapier/Ashby **11** openbare vacatures; D1-aanvraag `done`. Er zijn daarbij geen vacatures of sollicitatiestatussen toegevoegd of gewijzigd.
- **Gratis-limieten:** het account is op Workers Free (Cloudflare weigerde een aangepaste `limits`-configuratie met fout `100328`; daarom is die verwijderd). De officiële plafonds zijn 100.000 Worker-requests/dag, circa **10 ms CPU per Cron-uitvoering** en 50 externe subrequests/uitvoering. De eenminuut-Cron vertegenwoordigt maximaal circa 1.440 geplande starts per dag (uitzonderingen mogelijk). D1 Free-daglimieten worden afgedwongen. Zie [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/) en [D1 Free enforcement](https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/).
- **CPU-waarschuwing:** Cloudflare `workersInvocationsAdaptive` registreerde voor de drie bronproeven `cpuTimeP99`-waarden van respectievelijk **12138, 13726 en 12366** (GraphQL CPU-tijdregistratie, circa 12–14 ms als microseconden). Het aantal invocation errors was **0**. Cloudflare documenteert dat de hoogste CPU-kwantielen door runtime rollover soms boven het nominale plafond liggen zonder errors. Dit bewijst nog geen langdurig stabiele baseline-/dedupeverwerking onder Free.

**Productieactivatie blijft NO-GO** totdat een afgebakende echte baseline-run, CPU-/D1-gebruikscontrole en gebruikersvrijgave zijn bevestigd. Geen tweede Cron, geen R2, geen nieuwe betaalde dienst, geen automatische sollicitaties. `RADAR_ENABLED=0` blijft gehandhaafd.

### Echte, begrensde live-baseline — geslaagd (16 oktober 2026)

Drie onafhankelijke Cron-uitvoeringen van de **echte** `tick`-verwerkingscode hebben de actuele eerste momentopname van de drie actieve officiële ATS-bronnen uitsluitend in D1 opgeslagen. Start `2026-10-16T10:29:03.372Z`, afgerond `10:31:07.456Z`. De private D1-aanvraag `baseline_control:2026-10-16` staat op `done:live_baseline_20261016_01` en het verifieerbare `baseline_receipt:2026-10-16` heeft `status=ok`.

| Actieve officiële bron | Nieuwe D1-rijen | D1-status |
| --- | ---: | --- |
| Automattic / Greenhouse | 12 | `baseline` |
| Kinsta / Lever | 3 | `baseline` |
| Zapier / Ashby | 11 | `baseline` |
| **Totaal** | **26** | **historische momentopname** |

Onafhankelijke readback na de proef: exact 3 `seeded:`-markeringen, 26 D1-waarnemingen allemaal met status `baseline`, **geen** `pending`, `delivered` of `excluded`; de tabs `Nieuwe vacatures` en `Runs` bevatten alleen hun kolomkoppen. Er zijn **geen** sollicitaties of Google-radarrijen verzonden of gewijzigd. De permanente Worker-schakelaar bleef `RADAR_ENABLED=0`. De bestaande Google-secret bleef een beveiligde `secret_text`. Workers Issues liet 0 issues zien.

**Belangrijke Free-tier CPU-gate: NO-GO voor permanent activeren.** Cloudflare GraphQL `workersInvocationsAdaptive` rapporteerde bij de drie echte baseline-Crons `cpuTimeP99=35376`, `38266` en `62247` (ongeveer **35,4 ms**, **38,3 ms** en **62,2 ms**), elk bij één uitvoering, zonder geregistreerde fouten. Dat is boven de nominale **10 ms CPU per Cron-uitvoering** van Workers Free. De geslaagde beperkte baseline mag daarom **niet** worden geïnterpreteerd als bewezen langdurig betrouwbare gratis monitoring. Eerst CPU-optimalisatie en een aparte representatieve quota-/Free-test, anders geen `RADAR_ENABLED=1` zonder expliciete nieuwe goedkeuring.

De eenmalige baselinecode, D1-triggerroute en bijbehorende tijdelijke tests zijn na de proef uit de actieve broncode verwijderd; alleen de onafhankelijke auditresultaten blijven bewaard. De bestaande foutlogging, D1-healthbewaking en broncooldowns blijven beschikbaar voor een eventuele latere goedgekeurde productieactivatie.

### CPU-optimalisatie zonder wijziging van vacaturebeleid (16 oktober 2026)

De Worker leest voortaan via één Google Sheets `values:batchGet` alleen de noodzakelijke kolommen van `Bronnen`, `Vacatures`, `Applications` en `ApplicationEvents`. Deze tien dunne kolomranges worden opnieuw samengevoegd tot dezelfde oorspronkelijke rijposities, zodat de bestaande checks voor actieve bronnen, officiële vacatures, historische sollicitaties en afmeldingen exact hetzelfde blijven. Uit de actuele registeromvang (228 bronrijen, 349 vacaturerijen, 192 application-rijen en 163 eventrijen) volgt ongeveer **173.331 versus 98.796 JSON-tekens aan rijwaarden**, een afname van ongeveer **43%** exclusief response-metadata. Dit is een payload-inschatting, **geen bewezen CPU-winst**.

Het zoeken van de drie actieve bronparen gebruikt één statusindex i.p.v. driemaal de volledige bronlijst te scannen. URL-canonicalisatie voor rol-deduplicatie gebruikt één gevalideerde URL-parser in plaats van dezelfde URL opnieuw te parsen. De tests vergelijken compacte reconstructie met de oorspronkelijke registerindex en bewaken dubieuze URL's, lege cellen en rijuitlijning.

**Vrijgave:** `RADAR_ENABLED=0` blijft staan. Historische 26 D1-baselinewaarnemingen blijven behouden. De bekende volledige baselines kostten circa 35, 38 en 62 ms CPU op Free, dus pas na herhaalde CPU-metingen op echte workloads en grenscontroles kan eventueel een nieuw activeringsvoorstel volgen. Geen betaalde upgrade of automatische sollicitaties.

### Werkelijke Free-tier CPU-meting na optimalisatie (16 oktober 2026)

De tijdelijke afgeschermde meetroute is **afgerond en verwijderd uit de productiecode**. De eenmalige D1-aanvraag `perf_request:2026-10-16` staat op `done:compact_cpu_20261016_once`. Het bewijs `perf_result:2026-10-16` vermeldt `status=ok` na drie verschillende geoptimaliseerde echte lees-/vergelijkingsuitvoeringen: Automattic/Greenhouse **12 van 12 bekende**, Kinsta/Lever **3 van 3 bekende**, Zapier/Ashby **11 van 11 bekende**; **nul** nieuwe kandidaten. De code heeft Google Sheets en D1-vacaturegegevens niet gewijzigd en heeft geen openbare route of automatische sollicitatie toegevoegd.

De door Cloudflare GraphQL beschikbare invocatie-CPU-metingen zijn onder andere **29.874 µs (29,9 ms)** voor Automattic om 11:06 UTC en **55.200 µs (55,2 ms)** voor Zapier om 11:08 UTC, elk met nul gerapporteerde invocatiefouten. De meting van Kinsta voor 11:07 UTC was bij deze readback nog niet beschikbaar. Deze meetroute bevat live Google OAuth, de compacte Sheets-kolommen, historische sollicitatie-indexering, D1-deduplicatie en het ophalen van vacatures, maar **niet** het volledige productiepad met nieuwe D1-inserts, meldingen en Google Sheets-outbox. Vergelijk deze waarden daarom niet één-op-één met de eerdere echte volledige baseline (circa 35/38/62 ms). De hoeveelheid benodigde registergegevens is wel onafhankelijk vastgesteld als circa 43% kleiner.

**NO-GO voor `RADAR_ENABLED=1` op Cloudflare Free:** ten minste twee gemeten leesuitvoeringen liggen fors boven de nominale 10 ms CPU/Cron-grens; zonder aantoonbare CPU-ruimte zou permanente productie onbetrouwbaar zijn. Behoud de 26 bestaande D1-baselinewaarnemingen; geen betaalde upgrade, geen R2, geen tweede Cron en geen automatische sollicitaties. Voor een volgende stap is verdere opsplitsing/architectuurverbetering en een nieuwe zelfstandige CPU-validatie nodig.

## Gefaseerde Cron-architectuur (oktober 2026)

**Code aanwezig, productie niet geactiveerd.** De nieuwe Worker heeft een tweede schakelaar: `RADAR_PIPELINE_MODE=off`. De bestaande `RADAR_ENABLED=0` blijft ook uit. De geplande Cron blijft exact `* * * * *`, zonder extra Worker, Queues, R2 of kosten. **Alleen beide expliciete waarden** `RADAR_ENABLED=1` én `RADAR_PIPELINE_MODE=staged_review` zouden de nieuwe verwerking starten. De oude zware `tick` kan via Cron niet per ongeluk worden gestart door alleen `RADAR_ENABLED` aan te zetten. Dit is expres een **review-only** fase: er worden geen rijen in Google Sheets geschreven, geen D1-vacaturewaarnemingen aangepast, en nooit sollicitaties verstuurd.

Een cyclus bestaat voortaan uit **negen** afzonderlijke Cron-uitvoeringen. De eerder gemeten zesstappenvariant had op enkele momenten circa 18,6, 32,3 en 13,1 ms CPU. Vooral de sollicitatie-index en het beoordelen zijn daarom verder gesplitst.

| Stap | Handeling |
| --- | --- |
| 1. `source_gate` | Lees actuele bron- en werkgeverstatus; controleer beide op `active`. |
| 2. `vacancy_history` | Lees uitsluitend noodzakelijke `Vacatures`-kolommen; bewaar de momentopname tijdelijk in D1. |
| 3. `application_rows` | Lees de gebruikte `Applications`-kolommen zonder de index meteen te bouwen. |
| 4. `event_rows` | Lees de gebruikte `ApplicationEvents`-kolommen afzonderlijk. |
| 5. `application_index` | Combineer D1-momentopnamen tot de bestaande `known`- en `applied`-index. |
| 6. `radar_history` | Lees radaridentiteiten, officiële vacature-URL's en statussen. |
| 7. `official_ats` | Lees één officiële ATS-bron en controleer reeds bekende D1-identiteiten. |
| 8. `candidate_screen` | Classificeer nieuw ontdekte banen tegen eerdere sollicitaties en de radarhistorie. |
| 9. `review_only` | Controleer het afgeschermde resultaat, sla alleen reviewgegevens in D1 op en verwijder tijdelijke snapshots. |

Bij drie bronparen komt dezelfde bron normaal ongeveer één keer per **27 minuten** aan de beurt. De cyclus heeft een vervaltijd van twaalf minuten, waardoor gemiste Cron-uitvoeringen een cyclus bewust kunnen blokkeren in plaats van stil te hervatten.

Deze wijziging gebruikt strikt gescheiden, nieuwe `micro:v2:`-checkpoints. De oude `micro:v1:`-bewijzen blijven behouden maar worden **nooit** hervat in de nieuwe stappenreeks. Dubbel gestarte stappen worden atomair geclaimd. Een fout legt de cyclus stil voor handmatige controle en schrijft nooit sollicitaties, vacaturemeldingen of nieuwe D1-vacaturewaarnemingen. Een vroegere tijdelijke D1-testoverride bij `RADAR_ENABLED=0` is verwijderd.

**Nog geen productie-vrijgave:** de negen stappen zijn code- en regressietests; er is nog geen nieuwe onafhankelijke CPU-meting per stap. Cloudflare Free hanteert nominaal 10 ms CPU per Cron. Met name Google OAuth, het lezen van de bronnen en de radarhistorie kunnen nog boven die grens uitkomen. Ook is een momentopname over meerdere Google Sheets-tabbladen en Cron-minuten niet atomair. Iedere toekomstige automatische aflevering vereist een actuele, volledige eindcontrole van bronstatus, sollicitatiehistorie en dubbele vacatures, plus een aparte geautoriseerde CPU- en afleverproef. `RADAR_ENABLED=0` en `RADAR_PIPELINE_MODE=off` blijven staan.

## Technisch contract

- Cron: `* * * * *` UTC (één technische uitvoering per minuut, niet één controle per bron per minuut; bij drie actieve bronnen één controle per bron per circa drie minuten). Geen publicatie-SLA.
- Schema: `schema.sql`. D1 vereist; de eerste geslaagde poll per bron doet uitsluitend baseline, **geen historische 'nieuwe vacatures'**.
- Dubbelcheck: rol-specifieke officiële ATS-URL, provider-/job-ID, bestaande `Vacatures`/`Applications`/`ApplicationEvents`, en eerdere radarrecords. Generieke carrièresites en zwakke titel- of werkgevercombinaties worden niet als sterke duplicate-identity behandeld. Bekend in de zoekhistorie en daadwerkelijk ingediend worden afzonderlijk geteld.
- D1 bewaart nieuwe nog niet geleverde resultaten in een persistent outbox; bij retry voorkomt Sheet-readback nogmaals toevoegen.
- `Runs`: alleen ieder heel UTC-uur en bij nieuwe resultaten, fouten of later herkende sollicitaties; de kolommen `bekende_records` en `historische_sollicitaties` tellen onderscheiden categorieën.
- Geen betaalde API's of omzeiling van bronvoorwaarden. De pilot is begrensd tot één bron per cron, maximaal 160 banen per bron en maximaal 16 D1-inserts (96 parameters) per query. Bronnen boven deze limiet falen zichtbaar zonder stil records te laten vallen. Een rate-limit (429) veroorzaakt een minimaal kwartier cooldown; 5xx/netwerkfouten krijgen oplopende cooldown. **Cloudflare Free CPU-tijd, D1-query-/rijlimieten, Google API-quota en echte officiële bronbeperkingen vereisen nog een geautoriseerde productieproef.**

## Aanroepen in ChatGPT

> Controleer mijn Vacature Radar: lees de Google Sheet `Vacature Radar - Nieuwe Vacatures`, tab `Nieuwe vacatures`, en reconcilieer de records tegen het actuele Vacature Register (`Vacatures`, `Applications`, eventueel `ApplicationEvents`). Toon uitsluitend nieuw, officieel geverifieerd, volledig remote en vanuit Nederland uitvoerbaar werk binnen mijn doelrollen. Maak geen dubbele meldingen of sollicitaties.

Bronstatus mag alleen als `live_verified` worden aangemerkt na een daadwerkelijk uitgevoerde Cloudflare-cron en geverifieerde Drive-writes. Deze repositorybereiding zelf bewijst **geen** productie-uitvoering.

## Aanvullende onafhankelijke aanvalstests (2026-10-15)

- ATS-job-IDs worden tegen de rol-specifieke URL gecontroleerd, ook wanneer providerhost en werkgevers-tenant al kloppen.
- Nieuwe rollen van een inmiddels `blocked`/niet-actieve bron mogen niet meer vanuit de D1-wachtrij naar Google Drive worden doorgestuurd.
- Een onverwacht **lege eerste API-response** geldt niet als een gezonde baseline; hiermee voorkomen we dat oudere vacatures na herstel als nieuwe plaatsingen worden aangeboden. De Worker doet later opnieuw een gecontroleerde poging.
- De testmatrix omvat titels, 21 trackingvarianten, 100 cross-tenant-spoofgevallen, 100 verschillende job-ID's, verlopen bronstatussen, API-schemafouten, wachttijden, overlap, idempotente Google-append en capaciteit van 160 vacatures.
- GitHub CI bevat ook een échte `wrangler deploy --dry-run`-bundelcontrole **zonder deployment**. De direct afhankelijke Wrangler-versie is vastgezet op `4.151.0`.
- Meer details: [onafhankelijk QA-rapport](docs/INDEPENDENT-QA-2026-10-15.md).

**Vrijgave blijft NO-GO voor reguliere monitoring totdat de resterende limiet-, baseline- en observability-controles zijn afgerond.** Google OAuth, beide Sheets en één ATS-bron zijn op 16 oktober 2026 wél live bewezen. `RADAR_ENABLED=0` blijft staan. Eén Cron per minuut betekent bij drie actieve bronnen circa één broncontrole per drie minuten, geen directe melding.


### Herstel van onderbroken negenstapsverwerking (PR #93)

De review-only v2-pijplijn heeft nu een D1-claim per fase met het oorspronkelijke cyclus-ID, het fasenummer, het claimmoment en het herpogingsnummer. De **bestaande 26 baseline-waarnemingen** en eerdere `micro:v1:`-receipts worden niet gewijzigd.

- Na twee minuten mag een vastgelopen *read-only* fase worden gecontroleerd. Is de D1-snapshot al opgeslagen, dan wordt de fase idempotent als voltooid gemarkeerd **zonder opnieuw ATS of Google te lezen**.
- Ontbreekt de snapshot, dan krijgt die fase hoogstens **één** extra poging. Bij een tijdelijke Google-/ATS-HTTP-5xx is de eerste herpoging minimaal één minuut vertraagd. HTTP 429, 4xx, onbekende fouten en ongeldige brongegevens stoppen fail-closed.
- Een review-eindresultaat met al opgeslagen D1-receipt kan zonder dubbele cursor of dubbele melding worden afgerond. Er is nog steeds **geen Google Sheets-outbox** in de review-only pijplijn.
- De volledige cyclus verloopt na twaalf minuten. Een tweede onderbreking, oude claim zonder tijdstempel of onherstelbare inconsistentie activeert **geen** onbeperkte retries; er is dan handmatige beoordeling nodig.
- Nieuwe testgevallen dekken checkpointrecovery, leasegrenzen, maximaal één retry, 429, verlopen cycli en veilige finalisatie. Github CI bevat Node-tests plus een Wrangler build-only test.

**Vrijgave blijft NO-GO.** De nieuwe CPU-kosten per individuele v2-fase zijn nog **niet live gemeten**. De huidige gepubliceerde Cloudflare Workers Free-limiet voor Cron CPU is 10 ms per uitvoering; een groene GitHub Actions-job meet geen echte Cloudflare CPU. Eerst een afgeschermde runtime-proef en waargenomen CPU/quota per fase, daarna afzonderlijke goedkeuring voordat ooit `RADAR_ENABLED=1` of een aflevermodus wordt ingeschakeld. Tot die tijd blijft `RADAR_PIPELINE_MODE=off`.


### Cloudflare Free CPU-praktijkmetingen 2026-10-16

Afgeschermde D1-marker-Croncanaries (geen publiek endpoint, geen extra Cron, geen Sheets-/sollicitatiewrites) hebben de **eerste** negenfasenstap `source_gate` werkelijk gemeten in Workers Observability (veld `$workers.cpuTimeMs`):

- 2026-10-16 15:32:07 UTC: **18 ms**, originele negenfasencode met extra `monitoredTick`-health-D1-reads/writes. [Tijdelijke canary PR #94](https://github.com/Yolol100/vacature-engine/pull/94), verwijderd in PR #95.
- 2026-10-16 15:50:07 UTC: **10 ms**, na [PR #96](https://github.com/Yolol100/vacature-engine/pull/96), waarbij alleen voor de al checkpointed review-only route de redundante health-D1-registratie is weggelaten. [Tijdelijke canary PR #97](https://github.com/Yolol100/vacature-engine/pull/97), verwijderd via PR #98.

Dit zijn twee afzonderlijke runtime-observaties, **geen statistisch robuust CPU-profiel** of bewijs dat alle negen stappen onder 10 ms blijven. De 10 ms van de tweede proef ligt precies op de gepubliceerde Free Cron-limiet en geeft geen marge voor cold starts, grotere datasets en incidentele fluctuaties. Cloudflare documenteert bovendien beperkte rolloverflexibiliteit waardoor een enkele overschrijding zonder `exceededCpu` kan voorkomen. Daarom blijft **NO-GO** voor activatie gelden. De overige acht stappen en een latere daadwerkelijke leveringsroute zijn niet bewezen.

Na beide tests: `RADAR_ENABLED=0` en `RADAR_PIPELINE_MODE=off`; de `micro:v2:cpu_canary`-marker en alle nieuwe `micro:v2:`-testcheckpoints opgeschoond, 26 D1-baselines intact, beide Radar Sheet-outputtabbladen alleen headers, en tijdelijke Worker-canary-code/config verwijderd. Er is geen automatische indiening, geen bronstatuswijziging en geen extra schedulering. Eerst meer CPU-marge, dan een opnieuw begrensde meervoudige proef met volledige readback; pas na apart besluit eventuele activering.


### Extra Free CPU-vergelijking op 16 oktober 2026 (PR #99 en #100)

De volgende kleine optimalisatie vermijdt na een geslaagde atomische D1-cyclusclaim een onnodige status-uitlezing. Bij gelijktijdige `INSERT OR IGNORE`-claims retourneert de verliezer veilig `overlap_skipped`. [PR #99](https://github.com/Yolol100/vacature-engine/pull/99) bevat de regressie- en concurrerende-claimtests; standaard blijft de Worker uitgeschakeld.

De daaropvolgende strikt private, eenmalige, via D1-marker toegestane [CPU-canary PR #100](https://github.com/Yolol100/vacature-engine/pull/100) gaf op de daadwerkelijke Cloudflare Cron rond **16:12:05 UTC 16 ms CPU** (`outcome=ok` dankzij platformflexibiliteit). Het D1-checkpoint bevestigde dat de tweede stap `vacancy_history` was voltooid. De broncontrole `source_gate` had ook een succesvol checkpoint, maar een afzonderlijke betrouwbaar gekoppelde CPU-meting voor die eerste stap ontbreekt in het ontvangen logresultaat. De proef is bij de 16 ms-overschrijding beëindigd, dus de rest van de negen fasen is **niet volledig** geprofileerd. Een geslaagde uitvoering met `outcome=ok` bewijst niet dat een CPU-budget onder Cloudflare Free structureel haalbaar is.

**NO-GO blijft bindend.** De Free-limiet is 10 ms CPU per Cron. De testmarker en de nieuwe `micro:v2:`-checkpoints zijn verwijderd, alle 26 oorspronkelijke `baseline`-records zijn ongewijzigd, en de bekende geoptimaliseerde non-canary Worker-versie is onmiddellijk opnieuw gedeployed. PR #101 verwijdert ook de tijdelijke testcode van de GitHub-hoofdtak. Geen extra Cron, geen publieke interface, geen Google Sheet-writes en geen sollicitatie-inzendingen.

Volgende technische stap: de omvangrijke `Vacatures`-historielezing/-snapshot in de tweede stap reduceren of veilig splitsen, zonder historische sollicitatie- of duplicaatbescherming te verzwakken; daarna eerst CPU opnieuw op echte Free-invocaties meten en pas veel later een GO-beoordeling.


### CPU-paginatest en 32-rijenherstel, 16 oktober 2026

Onder een tijdelijke private D1-marker (geen publiek endpoint, geen extra Cron, geen Sheet-/sollicitatiewrites) zijn de eerste zes fasen/subfasen van de review-only Worker daadwerkelijk op Cloudflare Free gemeten:

| UTC | Fase | CPU |
|---|---|---:|
| 16:45:08 | `source_gate` | 8 ms |
| 16:46:06 | `vacancy_history` ID-grenscontrole | 9 ms |
| 16:47:06 | Geschiedenis pagina 1–64 | 7 ms |
| 16:48:04 | Geschiedenis pagina 65–128 | 9 ms |
| 16:49:04 | Geschiedenis pagina 129–192 | 8 ms |
| 16:50:05 | Geschiedenis pagina 193–256 | **11 ms** |

Cloudflare Free is beperkt tot **10 ms CPU per Cron**; een `ok`-outcome bij 11 ms betekent niet dat de fase voldoende CPU-marge heeft. **NO-GO**. Na de overschrijding zijn de private marker en alle testcheckpoints meteen gewist en is de veilige non-canary-versie teruggezet. De 26 `baseline`-records zijn intact gebleven.

Daarom is de historiepaginagrootte daarna teruggebracht van 64 naar **32 rijen per Cron**, zonder rollen, statusfiltering of historische sollicitaties weg te laten. De review-only maximumduur is daarvoor verhoogd naar 75 minuten (met cap van 1.536 ID-rijen en fout bij overschrijding); dit is geen vrijgave of gegarandeerde diensttijd. De langere verzameltijd is **niet atomair** ten opzichte van tussentijdse Google Sheets-wijzigingen: iedere latere leveringsroute moet bronstatus en sollicitatiehistorie opnieuw valideren. De overige stappen zijn nog niet op stabiele CPU-marge aangetoond; regelmatige productie blijft uit: `RADAR_ENABLED=0`, `RADAR_PIPELINE_MODE=off`. Geen activering zonder aanvullende runtime-metingen.


### 32-row private CPU canary, 16 oktober 2026

De korte afgeschermde proef na PR #104/105 is gestart met de twee productieschakelaars op `RADAR_ENABLED=0` en `RADAR_PIPELINE_MODE=off`. Cloudflare Observability registreerde voor `source_gate` op **2026-10-16T17:37:06Z precies 10 ms CPU** met `outcome=ok`. Dat is **niet strikt onder** de 10 ms Free-limiet en biedt geen marge. De proef is onmiddellijk gestopt; alle `micro:v2:`-testgegevens (de private canary-toestemming, de fasecontrole en de snapshot) zijn verwijderd; D1 heeft nog alle **26 baseline-waarnemingen**. Worker-versie `9974f499-58ed-423e-b75b-89ad9958efd1` zonder canary is expliciet teruggezet. PR #106 verwijdert ook de tijdelijke code en omgevingsvariabele uit de repository.

**NO-GO blijft gelden.** De 32-rijenpagina's hebben in deze proef nog geen eigen CPU-observaties: de stop vond al in `source_gate` plaats. De volgende optimalisatie moet de vaste overhead (Google OAuth/bronselectie en cyclusinitialisatie) verlagen of in kleinere fases splitsen; daarna opnieuw gerichte echte Free-invocaties meten. De snapshot over meer dan één minuut is bovendien niet transactioneel met tussentijdse registerwijzigingen; levering moet opnieuw valideren.


### Private hercontrole van geoptimaliseerde `source_gate`, 16 oktober 2026

De codewijziging in [PR #107](https://github.com/Yolol100/vacature-engine/pull/107) verwijdert overbodige tijdelijke Bronnen-arrays, vraagt enkel Sheets-waarden op en houdt een niet-exporteerbare Google RSA-sleutel uitsluitend in het tijdelijke Worker-isolatiegeheugen. Tests inclusief geheimrotatie, OAuth-concurrency en bronpolicy zijn groen.

Daaropvolgende privacyveilige CPU-canary [PR #108](https://github.com/Yolol100/vacature-engine/pull/108) werd via een tijdelijke D1-marker gestart met `RADAR_ENABLED=0` en `RADAR_PIPELINE_MODE=off`. **Cloudflare Workers Observability registreerde `source_gate` op 2026-10-16T17:54:06Z met 13 ms CPU** (`outcome=ok`, dus de rollover is geen bewijs dat de 10 ms-limiet werd gehaald). De proef is bij deze eerste overschrijding beëindigd. Marker en v2-testsnapshots zijn gewist, alle **26 baseline-records** behouden, en de geverifieerde veilige non-canary Worker-versie `328b0813-1c52-4098-b10d-edafb992bd13` werd direct teruggezet. Opruim-PR #109 verwijdert de testcode en -variabele uit `main`.

**NO-GO blijft gelden.** Key-caching is per isolate en kan geen koude start onder 10 ms garanderen. Het volgende bewezen gat is vaste opstartoverhead: ontwerp een **aparte D1-only cyclusinitialisatie** vóór `source_gate`, zodat OAuth/bronselectie niet tevens de eerste D1-control-aanmaak draagt. Pas daarna opnieuw gemeten Free Cron-profiel, inclusief koude en warme starts en alle geschiedenispagina's. Geen Sheets-uitvoer of sollicitatieautomatisering activeren.


### D1-only bootstrap: afgeschermde CPU-meting op Cloudflare Free (16 oktober 2026)

Na [PR #110](https://github.com/Yolol100/vacature-engine/pull/110) is de D1-cyclusaanmaak opt-in gescheiden van Google `source_gate` binnen dezelfde, bestaande minuut-Cron (geen extra trigger). Een [private test in PR #111](https://github.com/Yolol100/vacature-engine/pull/111) gebruikte een tijdelijke D1-marker met automatische vervaldatum, terwijl `RADAR_ENABLED=0` en `RADAR_PIPELINE_MODE=off` bleven:

| UTC | Stap | Werkelijke Worker-CPU |
|---|---|---:|
| 18:05:04 | D1-only `cycle_bootstrap` | **3 ms** |
| 18:06:05 | live Google `source_gate` | **9 ms** |
| 18:07 | historische ID-grenscontrole | checkpoint voltooid, CPU-log **niet beschikbaar** |
| 18:08:05 | eerste geschiedenis-pagina van 32 rijen | **9 ms** |

Bewijs: Cloudflare Workers Observability `$workers.cpuTimeMs`, D1 `micro:v2:control` en `micro:v2:snapshot:cycle_1792173904020_0:vacancy_page_1`. Een ontbrekend CPU-log is **geen meting onder de limiet**.

De testtoestemming is ingetrokken, alle drie resterende `micro:v2:`-testrecords gewist, de **26 D1-baseline-waarnemingen** onaangeraakt gebleven en de geverifieerde non-canary Worker-versie `3b04b773-f77a-45a5-b339-58d7b79367e6` via deployment `81dc1e46-5e66-4f7b-9439-604feda5ee31` teruggezet. PR #112 verwijdert de tijdelijke diagnosecode uit `main`. Geheimen, bestaande Cron en Google Sheets zijn ongewijzigd.

**CPU GO = nog niet toegestaan.** De drie afzonderlijke gemeten uitvoeringen bleven onder 10 ms, maar zijn slechts eenmalige observaties, twee op 9 ms zonder voldoende marge. Het historische-ID-stadium en de overige bron-/index-/ATS-/review-stadia zijn nog niet volledig en herhaald gemeten; complete leverings- en sollicitatieprocessen blijven afzonderlijk uit. Verdere CPU-optimalisatie en betrouwbaarheidstests moeten voortbouwen op deze veilige uitgangspositie.


### Integrale privé-CPU-audit na PR #113/#114, 16 oktober 2026

Eenmalige read-only reviewcyclus gestart op **18:33:19 UTC** met expliciete D1-toestemming (maximaal 28 minuten), terwijl de productieradar op `RADAR_ENABLED=0` en `RADAR_PIPELINE_MODE=off` bleef. De tijdelijke [PR #115](https://github.com/Yolol100/vacature-engine/pull/115) bracht een 353-rijen integratietest en een strikt single-cycle-testpad; de [cleanup PR #116](https://github.com/Yolol100/vacature-engine/pull/116) verwijdert uitsluitend de testcode en behoudt de 353-rijen regressietest.

| UTC | Bevestigde stap | Cloudflare Worker CPU |
|---|---|---:|
| 18:34:04 | D1-only cyclusinitialisatie | 3 ms |
| 18:35:07 | Live `source_gate` | 9 ms |
| 18:36:06 | Vacatures-ID-grenscontrole | 9 ms |
| 18:37:05 | Historiepagina 1–32 | 7 ms |
| 18:38:06 | Historiepagina 33–64 | 7 ms |
| 18:39:05 | Historiepagina 65–96 | 7 ms |
| 18:40 | Pagina 97–128 checkpoint voltooid | CPU-log ontbreekt |
| 18:41:05 | Volgende historiepagina vanaf rij 129 | **10 ms — CPU NO-GO** |

Cloudflare Observability liet bij de 10ms-uitvoering `outcome=ok` zien; dat is geen bewijs van marge. De tijdelijke D1-toestemming is om 18:41:37 ingetrokken; daarna zijn alle **zeven resterende `micro:v2:`-testrecords** verwijderd. De 26 oorspronkelijke `baseline`-records zijn gecontroleerd intact. De vorige non-canary Worker-versie `ab2afcf7-6b5b-4293-8d72-9962ddfa934a` is via deployment `c770b3a4-cb15-4fb6-a8bd-204d4bf00544` teruggezet. Er zijn geen outputtabrijen, sollicitaties, extra Crons of nieuwe secrets ontstaan.

De uitkomst verplicht verdere verkleining van de historiepagina's (van 32 naar **maximaal 16 rijen per Cron**) en behoud van de 1.536-rijen-capaciteitsbescherming. Bij één afgebroken CPU-meting mag de resterende, niet-gemeten pipeline **niet** als succesvol worden beoordeeld. De langere paginacyclus is review-only en niet atomair met Google Sheets; elke toekomstige levering vergt actuele bron- en sollicitatiehercontrole. **Geen productie-GO.**
