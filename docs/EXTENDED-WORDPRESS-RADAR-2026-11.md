# Uitgebreide WordPress-vacatureradar — implementatie en grenzen (16 november 2026)

## Doel
Zo veel mogelijk **echte** WordPress-, WooCommerce-, Elementor-, Gutenberg-,
PHP-/WordPress-supportvacatures vinden; direct op de *exacte* officiële
werkgever-/ATS-pagina controleren; alleen geschikte remote-vacatures die
vanuit Nederland uitvoerbaar zijn met één persoonlijk sollicitatiepakket
per rol aanbieden. **Geen automatisch solliciteren, e-mailen of nieuwe
kandidaatervaring verzinnen.**

## Bronnen en huidige basis
- **Bron van waarheid:** bestaand Vacature Register, tabbladen `Config`,
  `Bronnen`, `Vacatures`, `Applications`, `ApplicationEvents`,
  `Feedback`, `CandidateEvidence` en `JobSnapshots`.
- **Bestaande adapters:** Greenhouse, Ashby, Lever, Workable, Personio,
  SmartRecruiters, WordPress Jobs-categorie-RSS, We Work Remotely RSS,
  Himalayas, Jobicy, Remote OK, Remotive, Working Nomads en overige
  geregistreerde publieke bronnen.
- **Bestaande bronnen:** WordPress Jobs, Post Status, EU Remote Jobs,
  We Work Remotely, Himalayas, Working Nomads, Recruitee, Personio,
  BambooHR, Breezy HR, SmartRecruiters, Automattic, Syde, Human Made,
  10up, Kinsta, enzovoort. *Niet dubbel registreren.*
- **Nieuwe geregistreerde werkgever:** Level Level, exact
  `https://level-level.com/team/werken-bij/`. Geen geverifieerde
  huidige volledig remote functie geclaimd.
- **Niet geactiveerd:** WP Hired, omdat `wphired.com` bij de
  controle niet bereikbaar was; Codeable is een toelatingsplatform
  voor experts, geen open vacaturesfeed. Freelance.nl/Hoofdkraan
  vereisen een afzonderlijke, expliciete B2B-opt-in; het bestaande
  `exclude_freelance_marketplaces=TRUE` blijft gelden.
- Recruitee Careers API vereist mogelijk een accounttoken. Geen
  authenticatie of onbewezen JSON-endpoint aannemen.

## Geïmplementeerde verbeteringen in deze PR
1. **Greenhouse**: `?content=true` was aanwezig. Behoud
   `first_published` apart van `updated_at`. Wanneer de lijst
   geen oorspronkelijke datum bevat, vraag voor maximaal acht
   relevante WordPress-/webfuncties per goedgekeurde werkgever het
   officiële individuele vacature-endpoint op. Falende detailcontrole
   betekent *datum onbekend*, niet *gesloten*; mismatch op functie-ID
   wordt genegeerd. Geen massale extra requests.
2. **Ashby**: `includeCompensation=true` en `isListed=false`-filter
   waren aanwezig. `isRemote=true` geldt ook voor hybride; alleen
   `workplaceType=Remote` geeft de technische remote-pass.
   `publishedAt` is *laatst gepubliceerd* en **geen bewijs van eerste
   publicatie**. Bewaar afzonderlijke datumherkomst.
3. **Lever**: expliciete optie `options.api_region=eu` voor
   `https://api.eu.lever.co`; de standaard blijft de globale API.
   Geen ongerichte cross-region fallback. `createdAt` blijft
   bronmetadata, **niet** oorspronkelijke publicatiedatum.

## Voorgestelde twee zoekroutes (NIET geactiveerd)
**A. Snelle signalering (ontwerp):** eenmaal per 15–30 minuten via
een aparte geautoriseerde scheduler, uitsluitend al bevestigde
openbare werkgever-/ATS-API's en lichte RSS-feeds. Per tenant
ETag/Last-Modified indien ondersteund, rate-limit/backoff,
maximale concurrency, idempotent stable provider-ID/URL en
`first_seen_at` los van `first_published`. Meldingen alleen als
nieuwe en officieel gecontroleerde kansen bekend zijn.
Een ChatGPT-taak kan niet elke 15 minuten draaien; GitHub Actions
kent vertraging en mag volgens het huidige Register alleen offline
CI-tests draaien.

**B. Uitgebreide on-demand inventarisatie:** bij expliciet verzoek
alle `Bronnen.status=active` proberen met bounded API-adapters,
RSS, officiële carrièrepagina's en als aanvulling Google-ontdekking
binnen providerquota. De bestaande kandidaatlimiet van 500
en maximaal 100 officiële pagina's blijven gelden. Meer hits dan
een budget zijn *onafgehandeld*, niet *geen vacatures*.
Begin bij een **eenmalige backfill** met nog openstaande oudere
vacatures als *review-only* in aparte inventaris, maar maak deze
nooit automatisch `verified` of `cv-ready` zolang
`Config.max_posting_age_days=7` actief is. Verander die
policy pas met gecoördineerde expliciete goedkeuring en regressies.

## Kandidaten- en sollicitatieflow
1. Verzamel alleen actieve register-bronnen; per poging
   bron-ID, datum, succes/foutcategorie, resultaat en provenance.
2. Bewaar kandidaatobservaties los van de geverifieerde shortlist.
   Maak onderscheid tussen `first_seen`, `last_seen`,
   `updated_at`, `last_published` en `first_published`.
3. Dedupe op werkgever-tenanted ATS-job-ID of exacte canonieke
   functie-URL; vergelijk met bestaande Applications, Feedback,
   expliciet overgeslagen en afgewezen vacatures; nooit verlies
   van die historie.
4. Controleer de exacte officiële pagina, actieve toepassing,
   oorspronkelijke datum, inhoudelijke WordPress-werkzaamheden,
   taal NL/EN, salarisonzekerheid, volledig remote en **expliciete
   uitvoerbaarheid vanuit Nederland**. B2B of EOR is een
   contractmogelijkheid, geen automatisch bewijs van toelating.
5. Status in dashboardweergave:
   `gevonden_ongeverifieerd` → `controle_nodig` →
   `geverifieerd` → `cv_klaar` → `door_gebruiker_ingediend`
   → `reactie`. Afgekeurd, al eerder gezien en mogelijk
   gesloten worden **met reden en bronbewijs** bewaard.
   Een feeditem dat ontbreekt is geen sluitingsbewijs; volledig
   betrouwbare snapshots en meerdere onafhankelijke pogingen
   zijn vereist.
6. Alleen per geverifieerde functie een **canoniek V6-gebaseerd
   DOCX-cv van één pagina** (render + visuele QA), twee
   eenvoudige motivatiealinea's, portfolio en GitHub.
   Batch in afgebakende stukken, bijvoorbeeld tien tegelijk.
   Vermeld ontbrekende knock-out-eisen zichtbaar, zonder
   ervaring te verzinnen. Sluit pas af nadat de gebruiker
   de daadwerkelijke sollicitatie bevestigt.

## Deploy-/bevoegdheidsgate
Dit is een **code- en bronnenverbetering**, geen live-jobradar.
`Config.ingestion_schedule=on_demand_chatgpt_only` is niet
aangepast. Activering van frequent achtergrondzoeken vereist
een apart goedgekeurd operationeel ontwerp, live provider-/runtime-
toegang, veilige opslag, observability, budgetlimieten en een
bevestigd meldkanaal. Geen GitHub Actions-jobscanner of
ongevraagde mailbox-/Sheets-writes. Eerst offline regression,
dan kleine gecontroleerde provider-smoketest en bron-readback.
