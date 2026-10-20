# Register-brede brondekking en gratis Google-rondes

**Bron van waarheid:** het live Google Sheet Vacature Register (Config en Bronnen).
De repo bevat publieke uitvoeringsadapters en code; het is geen tweede
bronregister. Sollicitatiehistorie, CV-bewijs en remote-/NL-regels blijven behouden.

## Werking

- Classificeert alle Register-rijen, ook actieve, retired, consolidated en
  application_evidence. Inactieve bronnen worden niet gezocht.
- Publieke ATS/feed-adapters blijven directe broncontrole. Maximaal 20
  instances per ronde, in batches van hoogstens 8. Het venster roteert per
  ronde, zodat ook instances na plek 20 later aan bod kunnen komen.
- Andere actieve vacaturebronnen met een veilig publiek domein krijgen een
  **Google-site-discovery-wachtrij**. Een X-ray query is slechts ontdekking;
  zonder aparte adapter wordt de website niet rechtstreeks gecrawld.
  Inlogbeveiliging en robots-/providerbeperkingen worden niet omzeild.
- Het live Register bevat 35 gespecialiseerde zoektermen en 29 Google X-ray
  domeinen (stand op 20 oktober 2026). De code leest de actuele configuratie,
  gebruikt roulerende site/term-combinaties en neemt de vier oudere
  Google-seedqueries mee als aanvullend ontdekkingstype.
- Maximaal 20 Google-queries en 50 requests per ronde, verder beperkt door de
  gekozen pagina's en de **geverifieerde SerpApi Free-plan/quota/rate-gate** met
  reserve 10. Bij onbereikbare, ontbrekende of onveilige gratis toestemming
  loopt de publieke ATS/feed-fallback door; er is nooit een betaalde fallback.
- Geen automatische wijzigingen van Registerbronstatussen, CV-bewijs,
  applicaties, historiek, ranking of geverifieerde vacatureuitkomsten.

## Handmatige GitHub Actions

Workflow: **One-pass vacancy discovery and review (free sources)**

1. Kies mode check voor een bron- en queryplan zonder zoekrequests.
2. Kies page-1 voor een begrensde zoekronde. page-3 en page-10 kosten meer
   gratis requests; de code dwingt maximaal 50 requests per run af.
3. google_queries_per_run staat standaard op 8; toegestaan 1 tot 20.
4. discovery_round=auto gebruikt de Amsterdamse kalenderdag. Gebruik
   expliciet 0, 1, 2, enz. voor meerdere reproduceerbare vensters op één dag.
   Er ontstaat hiermee geen achtergrondtaak of periodieke zoekopdracht.
5. Download het artifact register-coverage-and-vacancy-review-readonly
   (retentie één dag). Ook de check mode maakt dit artifact.

De aparte oudere workflow **Free Google vacancy discovery** blijft voor
historische compatibiliteit bestaan en gebruikt nog vier statische queries.
Voor gecombineerde roterende dekking gebruik de one-pass workflow.

## Eerlijke status per bron

Elke Registerbron staat in de bronlijst onder coverage.sources en de
tellingen onder coverage.summary en coverage.execution_counts.

- direct_attempt_succeeded: bestaande publieke adapter daadwerkelijk
  geprobeerd en succesvol, zonder claim van volledige vacature-inventaris.
- direct_attempt_failed: concrete adapterpoging mislukt; geen vacatures sluiten.
- not_selected_within_round_limit: actieve adapter viel buiten dit venster.
- google_query_planned_not_executed: Google-query voorbereid; niet uitgevoerd.
- google_batch_succeeded_query_unconfirmed: totale Google-batch slaagde,
  maar individuele bronquery-uitvoering en rechtstreekse crawl onbewezen.
- google_query_not_executed_or_provider_blocked: Google niet toegestaan,
  niet beschikbaar of mislukt.
- not_attempted: bron nog in de wachtrij of zonder veilige adapter.
- excluded: retired, consolidated of onbekende status.
- not_applicable: bewijsbron, geen actuele vacaturediscovery.

Google-resultaten bewijzen nooit op zichzelf officiële vacature-identiteit,
actualiteit, volledig remote werken vanuit Nederland, taal of matchscore.

## Acceptatie en beperkingen

- Voer alle Python-regressies uit op 3.11/3.12/3.13 en behoud golden- en
  mutatietests. Geen productie-merge zonder groen bewijs.
- Geen enkele ronde crawlt daadwerkelijk alle actieve 221 Registerbronnen.
  Verschillende websites, toegang en quota maken dat onmogelijk. De nieuwe
  laag verantwoordt iedere bron afzonderlijk en roteert toegang die wél
  veilig beschikbaar is.
- De X-ray domein/zoektermcombinaties vormen een planningsuniversum.
  Duplicaten, variabele gratis quota en provider-response kunnen verhinderen
  dat ieder geplande query werkelijk is uitgevoerd.
- De output blijft read-only, handmatig gestart en bevat uitsluitend
  discovery-/QA-bewijs. Geen automatische sollicitaties of e-mails.
