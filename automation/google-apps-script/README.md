# Vacature Radar zonder Cloudflare

**Doel:** eens per 15 minuten een snelle openbare API-/RSS-ronde en nieuwe
WordPress-vacature**kandidaten** centraal bewaren. Geen automatische
sollicitaties, geen automatische verificatieclaims, geen eigen tweede
vacature-register, geen betaalde provider.

## Huidige toestand

- Centrale beleidsbron: [Vacature Register](https://docs.google.com/spreadsheets/d/1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0/edit), tabbladen
  \`Config\`, \`Bronnen\`, \`Vacatures\`, \`Applications\`, \`JobSnapshots\`.
- Technische wachtrij: [Vacature Radar](https://docs.google.com/spreadsheets/d/1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ/edit), tabbladen
  \`Bronvondsten\`, \`Nieuwe vacatures\` en \`Dashboard\`.
- \`Code.gs\` gebruikt de **bestaande** \`ingestion/source-specs.deploy.json\`
  van \`main\` plus iedere keer de **actuele** actieve IDs uit het Register.
  Een repo-brondefinitie is nooit op zichzelf autorisatie.
- Ondersteunde snelle adapters: Greenhouse, Ashby, Lever (globaal en expliciet
  EU), Workable, Personio, SmartRecruiters, WordPress Jobs, We Work Remotely,
  Remote OK, Himalayas, Jobicy en Remotive. Momenteel 22 technische
  broninstellingen van 26. De resterende actieve Register-bronnen blijven
  bestemd voor een **aparte volledige zoekopdracht** door \`vacature-search\`.
- Maximaal 35 bronrondes en 150 nieuwe kandidaten per run. Langzamere
  aggregators worden minder vaak bevraagd. Grote Greenhouse-JSON-antwoorden
  zijn begrensd op 4,25 MB, met een officiële metadatafallback boven de limiet.
  Workable gebruikt direct het openbare `apply.workable.com` widget-endpoint.
  Een lege of falende bron is **geen** bewijs dat er geen actuele vacatures zijn.
- `Bronvondsten.review_status` onderscheidt recent mogelijke remote-NL-kansen
  (`needs_official_review`) van `historical_review`,
  `date_unknown_review`, `remote_nl_unknown_review`,
  `geography_restricted_review`, `not_fully_remote_review` en
  `date_conflict_review`. Alle kandidaten blijven **ongeverifieerd**.
  Alleen nieuwe recente kandidaten met plausibele volledige remote-NL-signalen
  mogen een mailmelding opleveren. Oudere/missende datums worden bewaard, maar
  niet als verse kansen gemeld. De actuele 7-dagenregel komt uit Config.
- Het dashboard toont laatste scan, aantal gescande bronnen, fouten,
  nieuw ontdekte kandidaten, bekeken vacatures, alert-kandidaten en
  mislukte bron/accounts. De historische eerste 30 kandidaten blijven
  behouden en worden niet automatisch heringedeeld.
- Bij 0 bronnen aan de beurt meldt de radar `idle_no_sources_due`, niet
  een zogenaamd geslaagde verse broncontrole. De datum van de **laatste
  echte bronopvraag** staat los van de laatste triggeruitvoering. Het
  dashboard toont in rijen 19–22 scanstatus, laatste bronfetch, aantal
  ingestelde snelle bronnen en aantal bronnen dat aan de beurt was.
- Na een bronfout probeert de radar die bron niet elke 15 minuten opnieuw:
  backoff van 15, 30, 60, 120 tot 240 minuten. Een succesvolle bronopvraag
  herstelt de foutteller. Zo vermijden we onnodige verzoeken en API-blokkades.
- Werk vanuit Nederland wordt voor meldingen alleen als **mogelijk**
  beoordeeld als de locatie zelf Nederland/Europa/EMEA/wereldwijd vermeldt
  of een duidelijke toelatingszin voor NL/Europa aanwezig is. Vermelding
  van Europese klanten in een functietekst is nooit genoeg. De exacte
  officiële werkgeverspagina moet dit daarna bevestigen.

## Eénmalige gebruikersstap: daadwerkelijk in Google installeren

**Deze stap kan niet door alleen de GitHub/Drive-connector worden uitgevoerd.**
Google Apps Script-projecten, OAuth-toestemming en tijdtriggers vereisen
toegang tot de **Apps Script-editor** van het juiste Google-account.

1. Open [de bestaande Vacature Radar-sheet](https://docs.google.com/spreadsheets/d/1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ/edit).
2. Kies **Extensies → Apps Script**. Gebruik het reeds bestaande gekoppelde
   scriptproject als dat er is; creëer geen tweede scanner.
3. Kopieer de volledige inhoud van [Code.gs](./Code.gs) naar het scriptproject
   en sla op. Er zijn geen tokens of betaalde providerverbindingen nodig.
4. Selecteer de functie **\`enableVacatureRadar\`** en klik **Uitvoeren**.
   Controleer de gevraagde Google-rechten (Google Sheets lezen/schrijven,
   openbare UrlFetch, eventueel e-mailmeldingen, scripttrigger).
5. Controleer in Apps Script → **Triggers** dat precies één
   \`runVacatureRadar\`-trigger op **every 15 minutes** staat.
6. Controleer in het Register \`Config.ingestion_schedule\` dat de waarde
   \`apps_script_15m_fastlane_and_on_demand_deep\` is.
7. Voer eenmaal \`runVacatureRadar\` handmatig uit voor de eerste
   gecontroleerde rooktest, en kijk in \`Dashboard\`, \`Bronvondsten\`
   en Apps Script → **Uitvoeringen**. Een gevonden rol blijft
   \`needs_official_review\`.
8. Zet de mailmelding desgewenst naar een vast adres met **Apps Script →
   Projectinstellingen → Script properties**: \`VACATURE_RADAR_ALERT_EMAIL\`.
   Zonder die eigenschap probeert het script het adres van de eigenaar
   te gebruiken. Een mail betekent alleen dat er *te controleren kandidaten*
   zijn; geen geschikte/geverifieerde vacatures.

**Uitschakelen:** voer \`disableVacatureRadar\` uit. Dit verwijdert alleen
de eigen trigger en zet de live Config terug op \`on_demand_chatgpt_only\`;
vacatures, kandidaten en sollicitatiehistorie blijven bestaan.

## Hoe de voorbereiding van sollicitaties verloopt

Het script verzamelt uitsluitend kandidaten. De verificatie en
sollicitatiepakketten horen bewust bij de bestaande eigenaar
\`vacature-search\`: check per vacature de exacte officiële werkgever-
/ATS-link, werkelijke werkgever, oorspronkelijke plaatsingsdatum,
volledig remote en vanuit Nederland toegestaan, vereiste talen,
passende WordPress-werkzaamheden en \`CandidateEvidence\`. Vergelijk
ook met \`Applications\` en \`Feedback\`; afgewezen of reeds
ingediende rollen worden niet opnieuw voorbereid.

Pas na volledige verificatie: maak **een afzonderlijk, aantoonbaar correct
DOCX-CV van één pagina** op basis van de canonieke V6, met maximaal twee
korte motivatiealinea's, inclusief portfolio en GitHub. Geen feiten
verzinnen en ontbrekende knock-out-eisen zichtbaar houden. Een
voorbereid concept is nooit een ingediende sollicitatie. **Geen autosend.**

## Validatie en grenzen

- CI-tests: \`node --test automation/google-apps-script/radar.test.cjs\`.
  Ze gebruiken V8-mocks, doen geen live verzoeken en installeren geen trigger.
- Runtime: Google Apps Script (V8), \`UrlFetchApp\`, \`SpreadsheetApp\`,
  \`LockService\`, \`ScriptApp\` en optioneel \`MailApp\`.
- Maximale scriptlooptijd is begrensd op vier minuten; bronnen kunnen
  door quota, 403, 429 of gewijzigde feeds tijdelijk ontbreken.
- Bevestig Google-toestemming en een echte geslaagde Apps Script-run
  **voordat** je de radar als actief presenteert.
- GitHub Actions blijft **uitsluitend CI**: er wordt bewust geen
  tweede live vacature-scheduler aangemaakt.
