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

## Wat nog moet worden gekoppeld — menselijke beheeractie

1. Maak een gratis [Cloudflare-account](https://dash.cloudflare.com/sign-up) aan en autoriseer beheer via het gekozen veilige kanaal. Er is momenteel geen verbonden Cloudflare-connector.
2. Maak in Cloudflare D1 een database `webactueel-vacature-radar-state` aan (`npx wrangler d1 create webactueel-vacature-radar-state`). Zet de toegewezen **database ID** in `wrangler.jsonc` in plaats van `REPLACE_WITH_D1_DATABASE_ID`.
3. Gebruik een Google-serviceaccount dat in Google Cloud de Sheets API mag gebruiken. Geef dit serviceaccount uitsluitend **Lezer**-toegang op het oorspronkelijke Vacature Register en **Bewerker**-toegang op de aparte `Vacature Radar - Nieuwe Vacatures` Sheet. De Worker gebruikt Sheets OAuth; Google Drive bestandsrechten zorgen voor het onderscheid tussen lezen en schrijven. Maak geen serviceaccount-JSON openbaar en plaats sleutels nooit in Git, Sheets of ChatGPT-tekst.
4. Configureer de Cloudflare Worker-secret, bij voorkeur lokaal met `npx wrangler secret put GOOGLE_SERVICE_ACCOUNT_JSON`. Secret bevat de JSON van het serviceaccount. Verifieer de rechten op de twee exacte spreadsheet-ID's.
5. `cd cloudflare-radar && npm ci` (na commit van lockfile) of `npm install`; controleer `npm test` en `npm run check`.
6. Maak de D1-tabellen aan met `npx wrangler d1 execute webactueel-vacature-radar-state --remote --file ./schema.sql`.
7. Deploy met `npx wrangler deploy` **met `RADAR_ENABLED=0`**. Controleer dat de Worker publieke HTTP-verzoeken met 404 afwijst.
8. Voer een veilige proefrun uit in een gecontroleerde omgeving, eerst baselining van bestaande vacatures, dan een gecontroleerde nieuwe vermelding / testbron zonder echte gebruikersdata. Controleer D1-state, Drive-resultaat en fouten in `Runs`; maak geen fictieve productie-vacatures aan.
9. Pas na aantoonbaar bewezen eindsucces, zichtbare `Runs`, D1-profiel en limietcontrole `RADAR_ENABLED` aan naar `1`. Pas dan ook `Vacature Register:Config` productie- en activatiestatus aan. Houd de oude GitHub-radar uit om dubbele schedulers te voorkomen. Koppel een alert op terugkerende errors; een één-minuutschema is niet gegarandeerd exact op tijd en de upstream publicatiedatum blijft onafhankelijk.

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

**Vrijgave blijft NO-GO:** er is nog geen live Cloudflare/D1-runtime, serviceaccount, bronbevraging vanuit de Worker, echte Sheets-write of CPU-/quota-bewijs. De configuratie blijft `RADAR_ENABLED=0`, de PR blijft draft. Eén Cron per minuut betekent bij drie actieve bronnen circa één broncontrole per drie minuten, geen directe melding.
