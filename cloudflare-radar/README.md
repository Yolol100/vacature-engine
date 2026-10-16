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

**Belangrijke Free-tier CPU-gate: NO-GO voor permanent activeren.** Cloudflare GraphQL `workersInvocationsAdaptive` rapporteerde bij de eerste twee echte baseline-Crons `cpuTimeP99=35376` en `38266` (ongeveer **35,4 ms** en **38,3 ms**), elk bij één uitvoering, zonder geregistreerde fouten. Dat is boven de nominale **10 ms CPU per Cron-uitvoering** van Workers Free. De geslaagde beperkte baseline mag daarom **niet** worden geïnterpreteerd als bewezen langdurig betrouwbare gratis monitoring. Eerst CPU-optimalisatie en een aparte representatieve quota-/Free-test, anders geen `RADAR_ENABLED=1` zonder expliciete nieuwe goedkeuring.

De eenmalige baselinecode, D1-triggerroute en bijbehorende tijdelijke tests zijn na de proef uit de actieve broncode verwijderd; alleen de onafhankelijke auditresultaten blijven bewaard. De bestaande foutlogging, D1-healthbewaking en broncooldowns blijven beschikbaar voor een eventuele latere goedgekeurde productieactivatie.

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
