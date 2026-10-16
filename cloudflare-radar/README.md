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
- **Google Sheets:** `GOOGLE_SERVICE_ACCOUNT_JSON` is een Cloudflare **Secret**. Het serviceaccount is Lezer op Vacature Register en Bewerker op Vacature Radar. De API-toegang vanuit de daadwerkelijke Worker wordt met de eenmalige proef bewezen, niet afgeleid uit de aanwezigheid van de secret.
- **Uitgeschakeld:** `RADAR_ENABLED=0`, oorspronkelijke Register-config `radar_enabled=FALSE`. Dit mag voor de smoke-test **niet** op `1`.
- **Geen R2**, geen extra Cron, geen tweede monitor en geen automatische sollicitaties.

### Eenmalige, afgeschermde smoke-test

De tijdelijk geactiveerde diagnose in `src/selftest.mjs` draait alleen via de bestaande `scheduled`-handler terwijl de productieradar uitstaat. Er is **geen publieke test-URL**. Alleen een beheerder met D1-schrijfrechten kan via `radar_metadata` de eenmalige aanvraag `smoke_request:2026-10-16` met een unieke aanvraag-ID (12–64 letters/cijfers/`_`/`-`) plaatsen. De Worker claimt dit atoom en zet de aanvraag op `done`; herhaalde Crons draaien de proef niet opnieuw. De diagnose verloopt automatisch na 17 oktober 2026.

De test probeert achtereenvolgens Google OAuth, beide Sheets lezen, controleren van officiële kolomkoppen, een tijdelijke **lege** cel `Runs!L1000` schrijven/teruglezen/wissen, en **één** actieve ATS-bron uitlezen (voorkeur: Kinsta/Lever). De code weigert een gevulde testcel en probeert na elke schrijfpoging altijd op te ruimen. Er worden geen vacatures in de doel-Sheet gezet, geen sollicitatiestatussen gewijzigd en geen geheime of persoonlijke gegevens in de testuitkomst opgenomen.

De gezuiverde uitkomst staat na een run uitsluitend in `radar_metadata` bij `smoke_result:2026-10-16`. Vereiste acceptatie: `status=ok`, `google_auth=ok`, `sheets_read=ok`, `sheets_write=ok`, `cleanup=ok`, `ats=ok`, geen gewijzigde vacaturedata, en `RADAR_ENABLED=0` gebleven. Bij `failed`/`partial` blijft productie **NO-GO**. Bescherm oude privésleutels door ze bij Google Cloud in te trekken nadat een nieuwe Secret actief is.

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

**Vrijgave blijft NO-GO zolang de live smoke-test en limietcontrole niet aantoonbaar zijn afgerond.** Cloudflare/D1/Google Secret zijn aanwezig, maar inrichting alleen bewijst nog geen succesvolle Google OAuth vanuit de Worker, broncontrole of veilige Sheets-write. `RADAR_ENABLED=0` blijft staan. Eén Cron per minuut betekent bij drie actieve bronnen circa één broncontrole per drie minuten, geen directe melding.
