# Vacature Engine — zoeken op verzoek

Dit project ondersteunt **handmatig gestart vacaturezoeken vanuit ChatGPT** met de skills `vacature-search` en `webactueel-workflow`. Er zijn geen GitHub Actions voor vacaturezoekrondes, cronruns, autonome Radar-scans, pushmeldingen of automatische sollicitaties. Een eventuele pull-request-testworkflow voert uitsluitend offline unit-tests uit.

## Bestaande bronnen en gegevens

- **Vacature Register**: https://docs.google.com/spreadsheets/d/1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0/edit
  - `Config`: actuele zoekregels
  - `Bronnen`: enige bronregister; doorzoek alleen `active`
  - `Vacatures`, `Feedback`, `Applications`, `ApplicationEvents`, `CandidateEvidence`, `JobSnapshots`: deduplicatie, uitkomsten en bewezen fit
- **Vacature Radar – Nieuwe Vacatures**: https://docs.google.com/spreadsheets/d/1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ/edit
  - Alleen bestaand tabblad `Nieuwe vacatures` als optioneel resultatenoverzicht. Geen tweede masterregister.

## Werkwijze bij een expliciete ChatGPT-opdracht

1. Lees `Config`, de actieve `Bronnen` en de bestaande vacatures en sollicitaties in het Register.
2. Zoek nieuwe WordPress/WooCommerce/Elementor/Gutenberg-, webdesign/frontend- en AI-workflowautomatiseringsvacatures. Begin bij officiële werkgever-/ATS-pagina's; gebruik goedgekeurde publieke API/RSS, webzoekopdrachten en jobboards aanvullend als ontdekking.
3. Controleer op de actuele officiële detailpagina dat de vacature **open**, **echt recent geplaatst** (standaard maximaal 7 dagen), **volledig remote vanuit Nederland uitvoerbaar** en **in het Nederlands of Engels** is. Een first-seen-, scrape- of update-datum is geen bewezen publicatiedatum.
4. Vergelijk op canonieke vacature-URL en ATS/provider-job-ID met `Vacatures`, `Applications`, `ApplicationEvents` en de bestaande Radar-rijen. Toon geen eerder getoonde, afgewezen, behandelde of ingediende rol opnieuw als nieuw.
5. Beoordeel match met alleen bewezen kandidaatervaring uit `CandidateEvidence`. Toon uitsluitend officieel geverifieerde passende vacatures met werkgever, functie, publicatiedatum, directe URL en matchreden. Schrijf uitsluitend volgens live Register-beleid en voorkom dubbele rijen.

**Voorbeeldopdracht:** 'Zoek nieuwe passende vacatures van de afgelopen zeven dagen.'

## Code die blijft

- `src/vacature_engine/`: deterministische normalisatie, harde filters, scoring, prioritering en optionele CV-metadata.

**Eigenaarsgrens:** The `vacature-engine` does not generate CV or motivation prose and does not infer candidate experience. De `vacature-search`-skill verzorgt inhoudelijke beoordelingen en gebruikt alleen gecontroleerd kandidaatbewijs.
- `ingestion/`: publieke ATS/API/feed-adapters voor expliciete, gecontroleerde scans; de bestanden `source-specs.*` zijn technische voorbeelden, **niet** de bronwaarheid. Het live Register bepaalt actieve bronnen.
- `tests/` en `ingestion/tests/`: onderhouds- en regressietests die lokaal kunnen worden uitgevoerd.

Geen GitHub-gestuurde scheduler, automatische statusbestanden of nieuwe Google Drive-bestanden. CV's, conceptmails of sollicitatievoorbereiding uitsluitend op aparte gebruikersopdracht; nooit automatisch verzenden of solliciteren.
