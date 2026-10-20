# Fases 5-6: evidence-only brongezondheid en private specialistische beoordeling

**Bron van waarheid:** live Google Sheet Vacature Register; tabbladen Config,
Bronnen, CandidateEvidence, Vacatures, Applications, ApplicationEvents,
Feedback en JobSnapshots.

**Read-only uitvoering:** de bestaande GitHub Actions-zoekworkflow behoudt
contents: read, gebruikt alleen publieke ATS-/feedroutes en uitsluitend
geverifieerde gratis Google-quota. De workflow heeft geen Sheets-schrijfrechten.

## Fase 5 - Bronpoging en brongezondheid

De functie source_health_handoff levert in vacancy-review.json een sectie
source_health. Dat is **een voorstel, geen automatisch uitgevoerde mutatie**.
Voor een echt, geregistreerd provider- of ATS-verzoek met geldige UTC-tijd:

- source_id, evidence_timestamp, outcome en kind;
- uitsluitend expected/proposed veldwaarden voor last_success_at,
  last_failure_at, failure_category en consecutive_failures;
- aantallen echte pogingen en neutraal overgeslagen gevallen.

Er zijn geen wijzigingen aan bronstatussen, prioriteiten, next_retry_at,
onvolledige inventarisatietellingen, vacatures, sollicitaties of kandidaatclaims.
Gemengde provideruitkomsten, foutieve/toekomstige timestamps, bronpogingen die
ouder zijn dan de bestaande gezondheidsregistratie, onbekende bronnen en
uitsluitend Google-ontdekte sites leiden niet tot een mutatievoorstel.

De 50 actieve bronnen zonder geregistreerd succes- of faaltijdstip blijven
**onbekend/neutraal** totdat een echte brongebonden poging is vastgelegd.
Het live beleid source_health_min_observations=5 en
neutral_until_min_observations blijft ongewijzigd.

### Uitsluitend na expliciete goedkeuring

1. Download een recent GitHub Actions-artifact van een echte uitvoeringsrun.
2. Vergelijk elk expected-veld met de actuele Google Sheets-cel.
3. Bij afwijking: stop; geen automatische reconciliatie of overschrijving.
4. Vraag goedkeuring voor precies de relevante gezondheidsvelden.
5. Schrijf alleen die geautoriseerde cellen via de Sheets-connector en lees
   alle cellen en hun naburige velden terug.
6. Bewaar het herleidbare bewijs en de voor-/nawaarden.

## Fase 6 - Gratis X-ray-prioritering

De zoekplanning respecteert live direct_discovery_order, high_source_order,
de huidige bronstatus en prioriteit. Bij een budget van acht, voldoende
geregistreerde publieke bronsites en X-ray combinaties, plant ze:

- drie roulerende geregistreerde publieke brondomeinen;
- vier roulerende X-ray-combinaties van domein en rolzoekterm;
- een bestaande statische Google-seedquery.

Ontbreken X-ray-domeinen, dan worden vrije plaatsen gebruikt voor
geregistreerde bronqueries. De gratis-account/quota/rate-gate, maximaal 20
queries en 50 requests blijven ongewijzigd. Check-modus heeft nul zoekrequests.
Een Google-hit is nooit voldoende bewijs voor een actuele officiële vacature.

## Privacygrens voor specialistische beoordeling

De sectie specialist_handoff bevat alleen:
- opgeschoonde publieke HTTPS-rol-URL zonder tracking/signed querytokens;
- een strikt allowlisted pakket SHA-256-contextdigests van de bron;
- veilige machinecodes van nog benodigde verificatiestappen.

Deze overdracht bevat geen CV-claimteksten, bewijs-ID's, bronlocators,
persoonlijke werkervaring, taalniveaus, privébestanden, scores of sollicitaties.
Het systeem vermeldt private_specialist_required en een ontbrekende score
totdat een onafhankelijke, geautoriseerde specialist bewijs heeft geleverd.

De bestaande final_review.validate_assessment blijft de enige definitieve
poort. De vakowner moet buiten GitHub private CandidateEvidence en CV-bronnen
controleren, exacte werkgever/ATS en sollicitatieroute inspecteren, de echte
publicatiedatum bewijzen, volledig remote werken vanuit Nederland en de
werk-/sollicitatietaal bevestigen, en de rolvereisten met bewijs vergelijken.

De al aanwezige CLI-optie --verified-assessments kan uitsluitend in een
apart geautoriseerd lokaal proces worden gebruikt, met een private file
buiten de repository en buiten GitHub Actions. Deze publieke workflow kan
geen private beoordelingen ontvangen of automatisch scores autoriseren.
De bestaande kandidaat- en sollicitatiestatussen blijven ongewijzigd.

## Acceptatiebeperkingen

Vereist: groene Python 3.11, 3.12 en 3.13 tests, mutation-regressies, merge
naar beschermde main en daarna commit-/blob-readback en CI.
Een nieuwe echte check- en page-1-run blijven afzonderlijke acceptatiepoorten.
De beschikbare GitHub-koppeling heeft hier geen workflow_dispatch-actie.
Zonder run-ID en artifact mag live uitvoer niet als geslaagd worden gemeld.
Geen automatische e-mail/sollicitatie, betaalde provider of stille Sheets-write.
