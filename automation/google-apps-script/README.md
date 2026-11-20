# Vacature Radar zonder Cloudflare

**Doel:** eens per 15 minuten een snelle openbare API-/RSS-ronde en nieuwe
WordPress-vacature**kandidaten** centraal bewaren. Geen automatische
sollicitaties, geen automatische verificatieclaims, geen eigen tweede
vacature-register, geen betaalde provider.

## Wereldwijde vacatures, Nederland als werkland

De ontdekking doorzoekt openbare werkgevers- en ATS-bronnen in Amerika, Europa,
Azie en internationale remote-hubs, onafhankelijk van de vestigingsplaats.
Het live Register moet remote_scope=worldwide en allowed_work_locations=NL
hanteren. De radar bewaart voorlopige kandidaten maar meldt alleen recente,
mogelijk 100% remote vanuit Nederland uitvoerbare functies. W2/US-only,
verplichte lokale aanwezigheid, management, pure AI/automation-only en talen
anders dan NL/EN zijn geen geverifieerde matches.
De officiele werkgever/ATS moet daarna de oorspronkelijke plaatsingsdatum,
Nederlandse contract-/werktoelating, werktijden en CandidateEvidence bevestigen.

Verschillende functies op dezelfde algemene careers-pagina, op ATS-tenantroots
of op pagineringspagina's krijgen afzonderlijke kandidaatidentiteiten op basis
van werkgever, functie en specifieke job-ID indien beschikbaar. Bestaande
historische kandidaten worden niet verwijderd.

## Huidige toestand

- Centrale beleidsbron: [Vacature Register](https://docs.google.com/spreadsheets/d/1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0/edit), tabbladen
  \`Config\`, \`Bronnen\`, \`Vacatures\`, \`Applications\`, \`JobSnapshots\`.
- Technische wachtrij: [Vacature Radar](https://docs.google.com/spreadsheets/d/1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ/edit), tabbladen
  \`Bronvondsten\`, \`Nieuwe vacatures\` en \`Dashboard\`.
- \`Code.gs\` gebruikt de **bestaande** \`ingestion/source-specs.deploy.json\`
  van \`main\` plus iedere keer de **actuele** actieve IDs uit het Register.
  Een repo-brondefinitie is nooit op zichzelf autorisatie.
- Ondersteunde snelle adapters: Greenhouse, Ashby, Lever (globaal en expliciet
  EU), Workable, Personio, SmartRecruiters, de officiële Teamtailor RSS van Servebolt,
  WordPress Jobs, We Work Remotely,
  Remote OK, Himalayas, Jobicy en Remotive. De actuele aantallen staan op het dashboard.
  De resterende actieve Register-bronnen blijven
  bestemd voor een **aparte volledige zoekopdracht** door \`vacature-search\`.
- Maximaal 35 bronrondes en 150 nieuwe kandidaten per run. Langzamere
  aggregators worden minder vaak bevraagd. Grote Greenhouse-JSON-antwoorden
  zijn begrensd op 4,25 MB, met een officiële metadatafallback boven de limiet.
  Workable gebruikt direct het openbare officiele HTTPS-widgetendpoint; de oude 302-doorverwijzing wordt niet meer gebruikt. Bij HTTP 429 of 503 houdt de radar rekening met `Retry-After` en de bestaande wachttijd.
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

## Bronconfiguratie: audit en statusbewijs

De live scanner leest \`ingestion/source-specs.deploy.json\` op \`main\` bij
iedere scan. Dit is **een afzonderlijk productie-invoerkanaal**: een wijziging
kan nieuwe ATS-accounts, selectie of requestgedrag veroorzaken zonder
\`Code.gs\` te wijzigen. De bestaande code-SHA256-healthcheck detecteert
dit **niet**. De bestaande CI test daarom de bronconfiguratie tegen een
allowlist van adapters, bron-ID's, expliciete HTTPS-doelen, schema en
dubbele \`(source_id, account)\`-instanties. CODEOWNERS en PR-provenance
zijn aanvullend; een solo-codeowner is geen onafhankelijke reviewer.

Bij een toekomstige release moeten **twee hashes** worden vastgelegd,
beide voor de daadwerkelijk gebruikte ruwe bestandsbytes:
- \`code_sha256\`: de Apps Script-code, live versus GitHub.
- \`source_specs_sha256\`: bronconfiguratie op GitHub, vergeleken met
  de bronconfiguratie die de scanner werkelijk ophaalt zodra die
  runtime-meting na een aparte release beschikbaar is.

Een Git-blob-SHA is niet hetzelfde als SHA256. Tot de runtime-meting
is geïmplementeerd: \`source_specs_sha256=NOT_MEASURED_AT_RUNTIME\`.
Claim daarom geen volledige bronpariteit op basis van alleen de codehash.
Geen automatische pin, rewrite, rollback of deploy door deze controles.

**Brondekking is een trechter, geen synoniem voor succesvol scannen:**
Register totaal → Register actief → GitHub-specificaties → technisch
fastlane-geschikt → in deze bronronde due → geprobeerd → geslaagd /
mislukt → in cooldown. De aantallen worden per controle dynamisch
berekend; historische dashboardteksten (zoals 223) zijn niet leidend.
Eén bronspecificatie kan een provider en een werkgeversbron binden.
De fastlane omvat niet alle actieve Registerbronnen.

Voor iedere broninstantie \`source_id/account\` leg je afzonderlijk vast:
\`last_actual_attempt_utc\`, \`last_success_utc\`, \`last_failure_utc\`,
\`last_http_status_if_logged\`, \`failure_count\`, \`retry_at_utc\`,
\`state\` (\`SUCCESS\`, \`FAILED\`, \`COOLDOWN\`, \`NOT_DUE\`,
\`NOT_ATTEMPTED\`), en de herkomst van het bewijs.
Een oude \`Bronnen.last_success_at\` is **geen** bewijs van een recente
Apps Script-vraag. \`COOLDOWN\` betekent niet dat nul vacatures
beschikbaar zijn. Alleen een bewezen bronopvraag mag als geslaagd worden
geteld; nieuwe kandidaten en officieel geverifieerde vacatures zijn
aparte aantallen.

**Productiegrens:** deze documentatie en offline CI schrijven niet naar
Google Sheets of Apps Script en wijzigen geen triggers of cooldowns.
Nieuwe runtimevelden vragen een afzonderlijk geautoriseerde
\`Code.gs\`-release met nulmeting, back-up en rollback.

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
- GitHub Actions gebruikt standaard alleen **CI**. Een apart, optioneel en
  standaard uitgeschakeld Apps Script API-synchronisatiepad kan de bestaande
  scriptcode na expliciete OAuth-autorisatie en live-hashcontrole bijwerken.
  Zie [SYNC.md](./SYNC.md). Er wordt **geen tweede live vacature-scheduler**
  aangemaakt.
