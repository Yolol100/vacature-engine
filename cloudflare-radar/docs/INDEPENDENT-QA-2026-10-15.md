# Onafhankelijke QA van Cloudflare Vacature Radar — 15 oktober 2026

Status: CODE- EN MOCK-QA PASS; productie NO-GO totdat een geautoriseerde Cloudflare/D1/Google Sheets proefrun aantoonbaar slaagt.

Scope: uitsluitend de afzonderlijke cloudflare-radar-code in concept-PR 80 van Yolol100/vacature-engine. Main is niet gewijzigd. De originele radar blijft uit. Er worden geen sollicitaties automatisch verstuurd.

## Zeven bronklassen gecontroleerd

1. Projectwaarheid: het bestaande Vacature Register (Config, Bronnen, Vacatures, Applications, ApplicationEvents) en de aparte radar-Sheet (Nieuwe vacatures, Runs, Uitleg) zijn met de Google Drive-koppeling vergeleken. Config houdt radar_enabled op FALSE en de afgeleide radarbron is blocked.
2. Skills: webactueel-workflow, vacature-search, transcribeer en Google Drive/Sheets. Bronacquisitie, definitieve geschiktheid en sollicitatiehistorie behouden gescheiden eigenaren.
3. GitHub: alleen feature/cloudflare-vacature-radar-20261015; draft PR 80. De bestaande Python-ingestie en source-specs zijn de referentie, niet een tweede productiesysteem.
4. Library: Production-Grade Remote Job Ingestion and Matching System for vacature-engine. De principes over sterke tenant/job-identiteit, ruwe bewijsprovenance, aparte first-seen/publication timestamps en incrementele controle zijn beoordeeld.
5. YouTube-corpus: Library-master v15 en originele transcript-/commentshards gericht gelezen. Creatorinzichten zijn uitsluitend aanvullende praktijkervaring.
6. Online primair: Cloudflare Workers/Cron/D1, Google Sheets quota en de officiële Greenhouse-, Lever- en Ashby-interface/documentatie en carrièresites.
7. QA: nieuwe tegenvoorbeeldtests, parametermatrix, integratietests, GitHub Actions, exacte Google Sheet-readback en toetsing van open productiestops.

### YouTube-evidence, niet promoten tot platformwaarheid

- A Life After Layoff, 14 januari 2026, Why Mass Applying Is Killing Your Job Search, video EpnNZJDZbPg: ASR-transcriptie plus 50 opgeslagen top-level comments. Advies om gerichter te solliciteren; sommige reacties betwisten hoe uitvoerbaar dat is.
- Self Made Millennial, 12 februari 2026, This Cover Letter Formula Actually Gets Interviews, video 4PK-qQSknxk: transcriptie plus 24 reacties. Praktijkadvies over vacaturegerichte motivatie; geen bewijs voor een concreet ATS-contract.
- Work It Daily, 3 maart 2026, I am using AI to help thousands of job seekers get contacted by recruiters, video 6jpu7SeaMAk: transcriptie en 2 reacties; LinkedIn-creatorclaims blijven onbevestigde praktijkinformatie.

Er zijn geen sollicitatiescore, bron-API-feiten, publicatietijden of hard gates uit YouTube-commentaren afgeleid.

## Defects uit aanvalstests en herstel

- Titel-false-negatives: Web Developer, Experienced Software Engineer, Engineer Applied AI en Senior Product Designer kwamen onterecht niet eens in de technische detectie. De kandidaatfilter is verbreed. Alleen vacature-search keurt een concrete rol uiteindelijk goed.
- Tenantspoofing: correcte Lever/Greenhouse/Ashby-host met een verkeerde werkgevers-tenant werd ten onrechte geaccepteerd; nu moet ook de tenant overeenkomen. Meer dan 100 cross-tenant gevallen getest.
- HTTP 429 met wachttijd van 48 uur werd ten onrechte afgeknipt op 24 uur; nu gerespecteerd tot de expliciete veiligheidsgrens. Tests controleren oplopende cooldowns.
- Later ingediende sollicitaties werden wel bijgewerkt in de radarrij, maar niet correct meegenomen in de runstatistiek; verholpen.
- Een volledig overgeslagen poll door rate-limit-cooldown mocht niet als succesvolle broncontrole tellen. Nieuwe outcome: cooldown.
- De Google Sheets-idempotentie is getest wanneer de server een nieuwe vacature heeft opgeslagen maar de HTTP-bevestiging verloren gaat: geen dubbele rij bij een volgende run.
- Gelijktijdige Cron-runs worden via de lease geweerd. Een beschadigd ATS-response mag de eerste baseline niet als succesvol registreren.
- Er zijn ruim 200 provider/URL-identiteitsvarianten, 21 tracking/fragmentgevallen, titelvarianten en een gesimuleerde 160-vacaturebelasting getest.

## Wat nog niet is bewezen

- Geen Cloudflare-beheerverbinding, echte Worker, D1-database of Wrangler-build/deploy-test uitgevoerd.
- Geen serviceaccountsecret of Google API-read/write vanuit een echte Worker getest. Het bestaande Register mag alleen leesrechten krijgen; alleen de radar-Sheet bewerkrechten.
- Echte CPU-bezetting onder Cloudflare Free (10 ms per Worker), 50 D1-querylimiet, 100 SQL-bindingslimiet, D1 dagrijquota en Google Sheets quotagebruik niet live gemeten.
- Officiële ATS-GET en herpublicatiedynamiek per tenant niet volledig in de echte Worker gemeten. Respecteer providervoorwaarden en rate-limits.
- Eerste bron-baseline onderdrukt bewust historische vacatures; er is geen garantie dat recent maar al bestaand werk direct een melding oplevert.
- Eén Cron-run is per minuut geconfigureerd, maar er wordt één van de drie pilotbronnen geselecteerd: ongeveer elke drie minuten per bron, niet elke bron iedere minuut.
- Bronnen met meer dan 160 posities worden zichtbaar geweigerd in plaats van incompleet ingestuurd; paginatie is nog niet gebouwd.
- Google Drive is een uitleesbare resultatenbron, geen gegarandeerd onmiddellijke pushmelding.
- Het veld laatste_detectie_utc wordt bij eerste detectie ingevuld, maar blijft zonder live refreshfunctie een initiële observatie; gebruik dit niet als actuele brongarantie.
- De gemeten prestaties zijn Node/GitHub-simulaties; een groene GitHub Action is GEEN release-/Cloudflare-bewijs.

## Vrijgavepoort

1. Laat pull request 80 op draft staan en laat RADAR_ENABLED op 0 staan.
2. Maak de Cloudflare- en D1-koppelingen geautoriseerd; sla secrets uitsluitend in Cloudflare op.
3. Geef een Google-serviceaccount leesrechten op het Register en bewerkrechten op de aparte radarsheet.
4. Verifieer de drie officiële bronnen, fetch-volume en toegestane pacing.
5. Draai een echte geplande baseline, een gecontroleerde nieuwe observatie, een retry en readback in Google Drive.
6. Meet CPU-/D1-/Google-quota gedurende de proef en test de storing-/duplicaatroute opnieuw.
7. Pas daarna een expliciet onderbouwde GO/NO-GO-beslissing.

## Officiële primaire documentatie

- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/
- https://developers.google.com/workspace/sheets/api/limits
- https://github.com/lever/postings-api
- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://job-boards.greenhouse.io/automatticcareers

Status contract: alleen geslaagde lokale/CI-QA; geen live-inrichting, geen nieuwe vacatureclaim, geen betaalde dienst geactiveerd.


## Aanvullende adversariele fase: 28 van 28 tests + Wrangler dry-run

- **27/27** tests op commit `10303b07514ae6e6e7026019ee122479d85b5c7c` inclusief gesimuleerde D1/Sheets-herstelroutes, ATS-tenant- en URL-spoofscenario's; Wrangler v4.151.0 kon de Worker zonder deployment bundelen.
- **28/28** tests op commit `8feb3e7435c22f118fabdebe58ec99abe3b1b4f8`, GitHub Actions [38809873759](https://github.com/Yolol100/vacature-engine/actions/runs/38809873759) SUCCESS, `wrangler deploy --dry-run` PASS, 27.32 KiB Workerbundle (gzip 8.12 KiB).
- Nieuw expliciet risico: een tijdelijk **lege eerste ATS-response** mocht niet als gezonde baseline worden bewaard. Nu wordt de bootstrap geweigerd en via een veilige cooldown opnieuw geprobeerd, zodat bij herstel geen historische banen onterecht als nieuw worden gemeld.
- Nieuw expliciet risico: D1-wachtrijitems van een inmiddels **geblokkeerde of inactieve werkgever/ATS-bron** mogen nooit vanuit de outbox alsnog in de radar worden gepubliceerd. De Worker controleert de actuele bron- én werkgeversstatus bij aflevering.
- Nieuwe rol-ID-verificatie: zowel de officiële Lever- als Greenhouse-host, tenant en provider-job-ID moeten overeenkomen met de exacte vacaturelink, tegen provider-ID-spoofing.
- Testbewijs blijft simulatie en echte Wrangler build-validation, **GEEN live Cloudflare-installatie, echte D1-operatie, Google Sheets API-write of garantiebewijs voor Free CPU**.
- De publieke job-API's en de Cloudflare serviceaccount/rate-limit contracten moeten vóór activering echt worden gevalideerd. Formele status blijft `prepared_not_live`, `RADAR_ENABLED=0`, PR draft en NO-GO.
