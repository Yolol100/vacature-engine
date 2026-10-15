# Cloudflare Vacature Radar — voorbereid, niet live

Een **beperkte** Cloudflare Workers Cron-pilot die nieuwe openbare vacatures ophaalt, technische identiteiten bewaart in D1 en ontdekkingen in een afzonderlijke Google Sheet zet. Deze directory staat los van het Python-package `vacature_engine`; het bestaande Vacature Register blijft de enige bron voor beleid, bronstatus en sollicitatiehistorie.

**Huidige configuratie: `RADAR_ENABLED=0`.** Dit is geen live monitor, geen direct-apply-systeem en geen claim van volledige bron- of minuutdekking.

## Bewaakte proefbronnen

De eerste proef omvat precies drie bestaande, specifieke werkgever-/ATS-routes uit `ingestion/source-specs.radar.json`: Automattic/Greenhouse, Kinsta/Lever en Zapier/Ashby. Hun bron **en** werkgever moeten elke run `active` zijn in het live tabblad `Bronnen`. Andere bronnen worden *niet* stiekem op deze minuutschedule bevraagd. Als een publieke API wijzigt, wordt dit als fout gelogd; geen scraping/CAPTCHA/login-omzeiling.

## Resultaat

- Drive: `Vacatures/05 - Vacature Radar - Nieuwe matches`
- Sheet: `Vacature Radar - Nieuwe Vacatures` (tab `Nieuwe vacatures`), plus `Runs` en `Uitleg`.
- Nieuwe technische detecties zijn **geen** bevestigde geschikte vacatures. Alleen `vacature-search` controleert werkgever/ATS, volledig remote, uitvoerbaar vanuit Nederland, NL/EN en matchscore.
- `eerste_detectie_utc` is observatietijd, **niet** publicatietijd. `publicatie_bevestigd_utc` blijft leeg zonder officiële publicatie-evidence.
- Geen persoonlijk cv, sollicitatietekst of geadresseerde mailboxdata in Cloudflare; uitsluitend kandidaatvrije URL-/statushistorie uit het Register. Geen automatische verzending of sollicitatie.

## Wat nog moet worden gekoppeld — menselijke beheeractie

1. Maak een gratis [Cloudflare-account](https://dash.cloudflare.com/sign-up) aan en autoriseer beheer via het gekozen veilige kanaal. Er is momenteel geen verbonden Cloudflare-connector.
2. Maak in Cloudflare D1 een database `webactueel-vacature-radar-state` aan (`npx wrangler d1 create webactueel-vacature-radar-state`). Zet de toegewezen **database ID** in `wrangler.jsonc` in plaats van `REPLACE_WITH_D1_DATABASE_ID`.
3. Gebruik een Google-serviceaccount dat in Google Cloud de Sheets API mag gebruiken en dat expliciet editorrechten heeft op **beide** Sheets: het oorspronkelijke Vacature Register en het aparte radarresultatenbestand. Maak geen serviceaccount-JSON openbaar en zet die nooit in Git, Google Sheets of ChatGPT-tekst.
4. Configureer de Cloudflare Worker-secret, bij voorkeur lokaal met `npx wrangler secret put GOOGLE_SERVICE_ACCOUNT_JSON`. Secret bevat de JSON van het serviceaccount. Verifieer de rechten op de twee exacte spreadsheet-ID's.
5. `cd cloudflare-radar && npm ci` (na commit van lockfile) of `npm install`; controleer `npm test` en `npm run check`.
6. Maak de D1-tabellen aan met `npx wrangler d1 execute webactueel-vacature-radar-state --remote --file ./schema.sql`.
7. Deploy met `npx wrangler deploy` **met `RADAR_ENABLED=0`**. Controleer dat de Worker publieke HTTP-verzoeken met 404 afwijst.
8. Voer een veilige proefrun uit in een gecontroleerde omgeving, eerst baselining van bestaande vacatures, dan een gecontroleerde nieuwe vermelding / testbron zonder echte gebruikersdata. Controleer D1-state, Drive-resultaat en fouten in `Runs`; maak geen fictieve productie-vacatures aan.
9. Pas na aantoonbaar bewezen eindsucces en limietcontrole `RADAR_ENABLED` aan naar `1` en pas de eigen `Vacature Register:Config` productie- en activatiestatus aan. Houd de oude GitHub-radar uit om dubbele schedulers te voorkomen.

## Technisch contract

- Cron: `* * * * *` UTC (doel 1 minuut, geen publicatie-SLA).
- Schema: `schema.sql`. D1 vereist; de eerste geslaagde poll per bron doet uitsluitend baseline, **geen historische 'nieuwe vacatures'**.
- Dubbelcheck: exacte canonieke rol-URL én technische bron/vacature-ID, plus bestaande `Vacatures`/`Applications` en reeds in de radar opgeslagen URL's. Zwakke titels/werkgevercombinaties worden niet automatisch weggefilterd.
- D1 bewaart nieuwe nog niet geleverde resultaten in een persistent outbox; bij retry voorkomt Sheet-readback nogmaals toevoegen.
- `Runs`: alleen ieder heel UTC-uur en bij nieuwe resultaten/fouten, zodat de Drive-sheet niet elke minuut groeit.
- Geen betaalde API's, geen omzeilen van bronvoorwaarden. Cloudflare Free heeft o.a. 50 D1-querylimiet per invocatie en dagelijkse D1-limieten; de pilot is begrensd tot maximaal 160 banen per bron. Grotere of onduidelijke bronnen falen zichtbaar gesloten.

## Aanroepen in ChatGPT

> Controleer mijn Vacature Radar: lees de Google Sheet `Vacature Radar - Nieuwe Vacatures`, tab `Nieuwe vacatures`, en reconcilieer de records tegen het actuele Vacature Register (`Vacatures`, `Applications`, eventueel `ApplicationEvents`). Toon uitsluitend nieuw, officieel geverifieerd, volledig remote en vanuit Nederland uitvoerbaar werk binnen mijn doelrollen. Maak geen dubbele meldingen of sollicitaties.

Bronstatus mag alleen als `live_verified` worden aangemerkt na een daadwerkelijk uitgevoerde Cloudflare-cron en geverifieerde Drive-writes. Deze repositorybereiding zelf bewijst **geen** productie-uitvoering.