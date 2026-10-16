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

### Eenmalige, afgeschermde smoke-test

De tijdelijk geactiveerde diagnose in `src/selftest.mjs` draait alleen via de bestaande `scheduled`-handler terwijl de productieradar uitstaat. Er is **geen publieke test-URL**. Alleen een beheerder met D1-schrijfrechten kan via `radar_metadata` de eenmalige aanvraag `smoke_request:2026-10-16` met een unieke aanvraag-ID (12–64 letters/cijfers/`_`/`-`) plaatsen. De Worker claimt dit atoom en zet de aanvraag op `done`; herhaalde Crons draaien de proef niet opnieuw. De diagnose verloopt automatisch na 17 oktober 2026.

De test probeert achtereenvolgens Google OAuth, beide Sheets lezen, controleren van officiële kolomkoppen, een tijdelijke **lege** cel `Runs!L1000` schrijven/teruglezen/wissen, en **één** actieve ATS-bron uitlezen (voorkeur: Kinsta/Lever). De code weigert een gevulde testcel en probeert na elke schrijfpoging altijd op te ruimen. Er worden geen vacatures in de doel-Sheet gezet, geen sollicitatiestatussen gewijzigd en geen geheime of persoonlijke gegevens in de testuitkomst opgenomen.

De gezuiverde uitkomst staat na een run uitsluitend in `radar_metadata` bij `smoke_result:2026-10-16`. Vereiste acceptatie: `status=ok`, `google_auth=ok`, `sheets_read=ok`, `sheets_write=ok`, `cleanup=ok`, `ats=ok`, geen gewijzigde vacaturedata, en `RADAR_ENABLED=0` gebleven. Bij `failed`/`partial` blijft productie **NO-GO**. Bescherm oude privésleutels door ze bij Google Cloud in te trekken nadat een nieuwe Secret actief is.

### Live testbewijs — 16 oktober 2026

**Bevestigd geslaagd**, daadwerkelijk uitgevoerd door de gedeployde Cloudflare Worker (GitHub-commit `07963d8aab138fa08595fe343c22f4427c728fb6`). De eenmalige Cron-proef begon `2026-10-16T09:00:03.530Z` en eindigde `09:00:09.251Z`. Het duurzame D1-resultaat `smoke_result:2026-10-16` vermeldt `status=ok`, `google_auth=ok`, `sheets_read=ok`, `sheets_write=ok`, `cleanup=ok`, `ats=ok` en **3** jobs van `lever:kinsta`. De aanvraag staat op `done`, zodat de Cron dit niet herhaalt. De testcode heeft geen openbare endpoint en verloopt na 17 oktober.

Onafhankelijke readback na afloop: `Runs!L1000` leeg, `Nieuwe vacatures` en `Runs` hebben uitsluitend hun kolomkoppen, `radar_observations` heeft 0 rijen, Cloudflare-secret `secret_text`, `RADAR_ENABLED=0`. Alle GitHub Radar checks, CI en Release Evidence voor de testcommit zijn geslaagd.

**Geen productie-activering:** de eenmalige proof-of-connection is gereed, maar baseline-ingestie van alle drie de bronnen, foutlogs/alerts, gemiste uitvoeringen en Free-tier CPU/quota moeten vóór `RADAR_ENABLED=1` worden gevalideerd. Vermijd dubbele schedulers en voeg voorlopig geen R2 toe.

## Betrouwbaarheid, observability en broncontrole

De huidige release bevat **twee gescheiden paden**:

- Productiepad: uitsluitend bij \`RADAR_ENABLED=1\`. \`monitoredTick\` schrijft in D1 een UTC-heartbeat (\`health:last_started_utc\`), gesaneerd laatste resultaat (\`health:last_result\`), laatste succes (\`health:last_ok_utc\`), laatste fout (\`health:last_failure\`) en een mogelijke onderbreking van meer dan zes minuten (\`health:last_gap\`). Ontvangen of verzonden vacature-/sollicitatiegegevens worden nooit in deze healthvelden geplaatst. De bestaande foutcooldown per bron, D1-wachtrij, hercontrole tegen de Google Sheet en deduplicatie blijven actief. Een totale stop van Cron kan door een Worker alléén niet worden gedetecteerd; daarvoor is een externe watch/alert nodig. \`health:last_gap\` ontdekt gemiste minuten zodra Cron hervat.
- Eenmalig controlepad: uitsluitend bij \`RADAR_ENABLED=0\`, via beheerdersschrijfopdracht naar D1. \`reliability_request:2026-10-16\` wordt eenmalig ingevoerd als \`<unieke-test-ID>:0\`. Elke opeenvolgende Cron test precies één geregistreerde ATS-paarroute: Greenhouse/Automattic, Lever/Kinsta, Ashby/Zapier. De Worker verifieert Google OAuth en de Sheets-kolomkoppen, leest alleen openbare vacatures en slaat uitsluitend aantallen/gesaneerde fouten op in \`reliability_result:2026-10-16\`. Na fase 3 wordt de opdracht \`done:<ID>\`. Er worden **geen** vacatures, bronstatussen of sollicitaties geschreven. De diagnose verloopt automatisch na 18 oktober 2026. Een bron die nul vacatures retourneert, is niet als gezonde baseline bewezen.

### Logging en limieten

Wrangler schakelt \`observability.enabled=true\`, volledige **Workers Logs** (incl. Cron-invocations) en **Workers Issues** in. Externe subrequests zijn begrensd op 20 per uitvoering; D1-transacties, retries en Google Sheets-quota vereisen in productie aparte controle. De eerdere smoke-test heeft Google/OAuth en één ATS-bron bewezen; alleen na de volledige nieuwe drie-bronnenproef geldt \`3/3\` als live bevestigd.

Volgens de officiële Cloudflare-limieten (oktober 2026): op **Workers Free** maximaal 100.000 requests/dag, **10 ms CPU per Cron-uitvoering**, 50 externe subrequests per uitvoering (de eigen grens is lager), en 200.000 Workers-logevents/dag met drie dagen retentie. Een Cron iedere minuut telt technisch circa 1.440 invocations/dag, exclusief ander verkeer. Cloudflare bewaakt D1 Free-daglimieten sinds september 2026; zie [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [D1 Free enforcement](https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/) en [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/). CPU-budget en echte bronvolumes worden niet bewezen door configuratie of mocktests alleen.

**Productieactivering blijft afzonderlijk NO-GO:** voor \`RADAR_ENABLED=1\` zijn een geldige drie-bronnenproef, bevestiging van geen ongewenste writes, een gecontroleerde echte baselinefase, CPU-/quotametingen én expliciete gebruikersvrijgave nodig. De oorspronkelijke GitHub-radar wordt niet parallel ingepland. Geen nieuwe R2- of betaalde dienst.


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
