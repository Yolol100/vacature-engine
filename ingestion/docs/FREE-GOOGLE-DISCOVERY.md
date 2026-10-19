# Gratis vacature-ontdekking (optionele Google-route)

Deze uitbreiding **vervangt de bestaande ATS- en openbare feedadapters niet**.
De live `Vacature Register`-tabbladen `Config` en `Bronnen` blijven leidend.
Gebruik uitsluitend een geactiveerde `google-jobs`-bron; dit voorbeeld voegt
geen bron toe of activeert een inactieve bron.

## Gratis uitvoering zonder abonnementskosten

1. Gebruik eerst de bestaande publieke ATS/JSON/RSS-adapters in `ingestion/`.
   Hiervoor is geen SerpApi-sleutel nodig. Google is aanvullende ontdekking.
2. Optioneel: maak zelf een **gratis** account op https://serpapi.com/ .
   Zet `SERPAPI_API_KEY` uitsluitend in een lokale omgeving/runnersecret.
   **Nooit in configuratie, een publiek issue, Git-log of broncode.**
3. Controleer de huidige gratis quotaregels van de aanbieder. De Google-adapter
   controleert vooraf `plan_name` en `total_searches_left`; bij een onbekend
   abonnement, betaald plan, ontbreken van tegoed of fout wordt **niets gezocht**.
   Deze controle is alleen een rem: wijzig geen abonnement, voeg geen betaalkaart
   toe en monitor het werkelijke quotaverbruik bij de aanbieder.
4. Activeer bewust een handmatige zoekronde. Er is **geen scheduler**, geen
   workflow met automatische kosten en geen automatische sollicitatie.

Installeer lokaal de bestaande `ingestion`-package en voer bij een expliciete
gebruikersopdracht eerst de live bronfilter uit. Daarna:

```bash
python -m vacature_ingestion filter-specs \
  --specs ingestion/source-specs.google-optional.json \
  --spreadsheet-id "$VACATURE_REGISTER_ID" \
  --out /tmp/active-google-specs.json
python -m vacature_ingestion ingest-many \
  --specs /tmp/active-google-specs.json \
  --state /tmp/vacature-state.sqlite3 \
  --out /tmp/google-discoveries.json
```

De `filter-specs`-stap vereist de al bestaande read-only Google
service-account-autorisatie (`GOOGLE_SERVICE_ACCOUNT_JSON`).
Zonder verbinding met het register mag er geen scan starten. De JSON-output
bevat **alleen ontdekkingskandidaten**, geen geverifieerde vacatures.
Het werkelijke aantal gratis zoekopdrachten kan per aanbieder en pagina variëren.

## Waarom geen rechtstreekse Google Playwright-scraper?

Het bestaande `Yolol100/browser-search` gebruikt al Chromium/Playwright en
documenteert automatische-verkeerblokkades. Geen CAPTCHA-oplossing, proxyrotatie,
fingerprintmanipulatie of omzeiling wordt toegevoegd.

## Gedrag en beperkingen

- `max_pages` 1–10, `max_requests_per_run` 1–50, `max_jobs` is de
  totale verwerkingscap. Elke extra Google-pagina kan een aparte zoekopdracht zijn.
- Zoek `start=0,10,...,90`, eerst recent met `tbs=qdr:w`; een indexdatum
  bewijst **niet** de eerste publicatiedatum bij de werkgever.
- Alleen `https`-links als kandidaten; geen automatische visits, sollicitaties,
  notificaties of toevoeging aan het sollicitatieregister.
- ATS-hints herkennen publieke tenant-URL's; ze bewijzen geen werkgeversidentiteit.
- Google-resultaten zijn **nooit volledige snapshots**. Een verdwenen zoekhit
  sluit daardoor niet automatisch een vacature in de SQLite-state.
- Ook na succesvolle ontdekking blijven officiële werkgeversverificatie,
  uitvoering vanuit Nederland, toegestane taal, actualiteit, sterke vacature-ID,
  CandidateEvidence-match en deduplicatie tegen `Vacatures`/`Applications`
  verplicht vóór een functie aan de gebruiker wordt aanbevolen.
- De in het vorige onderzoek gevonden externe JobHive-dataset wordt niet standaard
  ingeschakeld: het live manifest bleek op 2026-10-19 nog
  `generated_at=2026-09-02` te vermelden, ongeschikt om versheid te bewijzen.

## Tests

```bash
python -m unittest discover -s ingestion/tests -p 'test_free_google_discovery.py'
python -m unittest discover -s ingestion/tests
```

Voer regressies uit vanuit een omgeving waarin de `ingestion` package en
haar vastgepinde afhankelijkheden geïnstalleerd zijn. Testmocks doen geen
echte zoekopdrachten en gebruiken geen betaalde API.
