# Vacature Ingestion — bronadapters op verzoek

Dit Python-onderdeel leest publieke werkgever-, ATS-, API-, RSS- en JobPosting-informatie als technisch hulpmiddel bij **expliciet gestart** vacaturezoeken. Het draait niet automatisch. Er draaien geen automatische vacaturezoekrondes via GitHub Actions of Cloudflare; een pull-request-testworkflow mag uitsluitend offline regressietests uitvoeren.

## Bronwaarheid en werkwijze

1. Lees de actuele `Config` en **actieve** `Bronnen` uit het bestaande Vacature Register.
2. Gebruik alleen passende publieke adapters of gecontroleerde rechtstreekse webzoekopdrachten. Statische `source-specs.*.json` bevatten uitsluitend technische voorbeelden en mogen een inactieve bron nooit activeren.
3. De adapters leveren ruwe observaties. De skill `vacature-search` verifieert officiële vacature, werkbaarheid vanuit Nederland, taal, echte publicatiedatum, authenticiteit en bewezen kandidaatfit.
4. Vergelijk met het bestaande Register en Radar-overzicht; nooit een tweede canonieke vacature- of sollicitatiedatabase maken.
5. Alleen op een expliciete opdracht gegevens opslaan in bestaande geautoriseerde Sheets, met deduplicatie en readback. Geen automatische berichten, CV-bestanden of sollicitaties.

De code bevat provideradapters, normalisatie, HTTP-beperkingen en optionele lokale technische state voor gecontroleerd onderhoud. Die state is geen bronwaarheid en start nooit zelfstandig een scan.

## Code en tests

`src/vacature_ingestion/adapters/` bevat onder andere Greenhouse-, Lever-, Ashby-, Workable-, SmartRecruiters-, Personio- en publieke feedadapters. `cli.py` biedt handmatig te starten opties. Tests staan in `ingestion/tests/`.

De hoofdengine in `src/vacature_engine/` is gescheiden van deze publieke acquisitiecode.

## Optionele gratis Google-ontdekking

De bestaande publieke ATS/feed-zoekroutes blijven de standaard. Voor een expliciet
handmatig gestarte aanvullende Google-zoekronde is er nu een optionele
`serpapi_google`-adapter met gratis-plan/quota-blokkade en veilige paginering
(1–10 pagina's). Zonder API-sleutel blijft deze route uitgeschakeld.

Zie [FREE-GOOGLE-DISCOVERY.md](docs/FREE-GOOGLE-DISCOVERY.md). Zoekresultaten zijn
nooit geverifieerde vacatures; officiële werkgever/ATS-controle blijft vereist.
