# Top-25 Radar validation — 2026-09-05

This report separates three things that must not be conflated:

1. **Radar prior rank** — deterministic discovery economics used to cheaply rank the 1M universe.
2. **Current-market business validation** — public data availability, buyer urgency, monetization, competition, operator edge and execution/regulatory risk.
3. **Provider keyword metrics** — real Ahrefs metrics when the one-shot validator has credentials. Until that artifact exists, they remain explicitly unverified.

The top 25 below are the exact highest `max_scan_score` buyer clusters reproduced from the canonical generator/scorer at the 55 REVIEW threshold.

## Business-validation ranking

The `Business validation` score is a decision aid, not a measured market size. It weights buyer urgency, willingness to pay, data leverage, competitive whitespace, operator/distribution edge and implementation/regulatory risk.

| Business rank | Radar rank | Cluster | Business validation | Disposition | Why now |
|---:|---:|---|---:|---|---|
| 1 | 16 | `building-permits|subcontractors` | **86/100** | **BUILD / TEST** | Strong construction-domain edge; permit data is abundant but a tiny trade-specific daily opportunity feed is still a distinct job. Seattle offers a defensible launch market. |
| 2 | 11 | `sbir-awards|consultants` | **82/100** | **BUILD / TEST** | Official data is rich and downloadable; broad search exists, but “award → likely next commercial action” remains a sharper paid workflow for consultants/capture teams. |
| 3 | 15 | `sbir-awards|investors` | **78/100** | TEST NEXT | Same data advantage; investor use is real but less direct than consultant/capture workflow. Cross-reference follow-on contracts and repeat-award signals. |
| 4 | 12 | `endangered-species|insurers` | **76/100** | TEST AS BROADER SITE SCREEN | Official IPaC is strong, so do not compete with consultation. Test batch site triage + cross-source environmental context before formal diligence. |
| 5 | 21 | `prevailing-wage|developers` | **75/100** | TEST DIFFERENT BUYER/WEDGE | WageFinder already owns free lookup/API. The useful wedge is bid-impact/estimating workflow and wage-change alerts; estimators/contractors are probably better buyers than developers. |
| 6 | 22 | `sbir-awards|suppliers` | **73/100** | WATCH / SAMPLE | Strong follow-on supplier logic; likely viable as a segment inside SBIR Signal rather than a separate product. |
| 7 | 19 | `sanctions-screening|lenders` | **70/100** | WATCH | High-value decision and free authoritative feed, but mature vendors and high compliance stakes make this a harder first product. |
| 8 | 9 | `contractor-license|property-managers` | **69/100** | PIVOT TO MONITORING | Generic lookup is crowded. Ongoing vendor/license/bond/discipline monitoring for a portfolio is more defensible than one-off verification. |
| 9 | 1 | `contractor-license|developers` | **66/100** | PIVOT | Same crowding problem; useful only when bundled into permit/project/vendor intelligence. |
| 10 | 3 | `h1b-employer|recruiters` | **63/100** | WATCH / NICHE ONLY | Buyer is clear, but H-1B sponsor search has many mature 2026 databases and even free job-board browser extensions. Need a recruiter workflow beyond search. |
| 11 | 14 | `sanctions-screening|consultants` | 62/100 | WATCH | Consultants have recurring need, but official CSL plus established screening platforms compresses the generic API opportunity. |
| 12 | 2 | `h1b-employer|immigration-attorneys` | 61/100 | WATCH | Data is valuable but heavily productized; attorney acquisition/benchmarking would need a narrower decision product. |
| 13 | 4 | `contractor-license|estimators` | 60/100 | BUNDLE | License status matters to prequalification, but not enough to justify a standalone estimator product. Bundle with permit/bid intelligence. |
| 14 | 6 | `contractor-license|contractors` | 59/100 | BUNDLE | Crowded one-off verification; potentially useful for subcontractor/vendor prequalification monitoring. |
| 15 | 10 | `h1b-employer|HR-teams` | 58/100 | WATCH | Existing sponsor databases cover the raw data. A compliance/recruiting-ops use case would need proprietary workflow integration. |
| 16 | 5 | `h1b-employer|employers` | 57/100 | WATCH | Employers already own their sponsorship history; limited reason to buy a generic external database. |
| 17 | 7 | `h1b-employer|visa-applicants` | 55/100 | DO NOT BUILD FIRST | Very high consumer interest but exceptionally crowded and many free alternatives. |
| 18 | 8 | `contractor-license|subcontractors` | 54/100 | BUNDLE | Verification alone is commodity-like; better as a trust/prequalification field inside PermitSignal. |
| 19 | 17 | `restaurant-inspection|restaurant-owners` | 52/100 | DO NOT BUILD FIRST | Yelp already publishes health scores using local-government and Ecolab/HDI data. Owner workflow could exist, but national aggregation is not empty whitespace. |
| 20 | 23 | `restaurant-inspection|commercial-brokers` | 51/100 | WATCH | Interesting property/distress signal, but indirect and fragmented. Better as one feature in broader commercial-property intelligence. |
| 21 | 25 | `pesticide-residue|homeowners` | 49/100 | DO NOT BUILD FIRST | USDA data is strong, but EWG owns consumer mindshare and monetization would lean heavily on affiliate/content economics. |
| 22 | 18 | `treatment-locator|recruiters` | 46/100 | DO NOT BUILD | Recovery.com has a very large provider network and professional referral workflow. High regulatory/ethical burden for a weak wedge. |
| 23 | 20 | `treatment-locator|healthcare-attorneys` | 45/100 | DO NOT BUILD | Same market saturation plus sensitive/high-stakes user decisions. |
| 24 | 24 | `treatment-locator|providers` | 44/100 | DO NOT BUILD | Recovery.com already monetizes provider profiles/advertising and reports a large engaged treatment-seeker audience. |
| 25 | 13 | `airline-ontime|hotels` | 42/100 | DO NOT BUILD | Cirium has a long-established on-time-performance product/reporting franchise; the hotel-buyer connection is too indirect. |

## Exact Radar top-25 order

| Radar rank | Cluster | REVIEW keywords | Max prior scan | Avg REVIEW scan |
|---:|---|---:|---:|---:|
| 1 | contractor license verification for developers | 4,975 | 92.06 | 75.83 |
| 2 | H-1B employer sponsorship for immigration attorneys | 4,968 | 92.05 | 75.83 |
| 3 | H-1B employer sponsorship for recruiters | 4,967 | 92.00 | 75.85 |
| 4 | contractor license verification for estimators | 4,975 | 91.96 | 75.99 |
| 5 | H-1B employer sponsorship for employers | 4,964 | 91.91 | 75.70 |
| 6 | contractor license verification for contractors | 4,969 | 91.81 | 75.80 |
| 7 | H-1B employer sponsorship for visa applicants | 4,966 | 91.73 | 75.80 |
| 8 | contractor license verification for subcontractors | 4,969 | 91.55 | 75.78 |
| 9 | contractor license verification for property managers | 4,981 | 91.54 | 75.94 |
| 10 | H-1B employer sponsorship for HR teams | 4,978 | 91.52 | 75.68 |
| 11 | SBIR/STTR awards for consultants | 4,798 | 89.11 | 70.22 |
| 12 | endangered-species compliance for insurers | 4,803 | 89.04 | 70.11 |
| 13 | airline on-time performance for hotels | 4,793 | 89.04 | 69.98 |
| 14 | OFAC/BIS sanctions screening for consultants | 4,812 | 89.03 | 70.22 |
| 15 | SBIR/STTR awards for investors | 4,804 | 88.99 | 69.97 |
| 16 | building-permit intelligence for subcontractors | 4,800 | 88.98 | 70.21 |
| 17 | restaurant health inspection for restaurant owners | 4,833 | 88.97 | 70.25 |
| 18 | substance-abuse treatment facilities for recruiters | 4,803 | 88.93 | 70.14 |
| 19 | OFAC/BIS sanctions screening for lenders | 4,815 | 88.90 | 70.17 |
| 20 | substance-abuse treatment facilities for healthcare attorneys | 4,798 | 88.89 | 70.22 |
| 21 | Davis-Bacon prevailing wage for developers | 4,792 | 88.89 | 70.19 |
| 22 | SBIR/STTR awards for suppliers | 4,807 | 88.88 | 70.27 |
| 23 | restaurant health inspection for commercial brokers | 4,814 | 88.88 | 70.06 |
| 24 | substance-abuse treatment facilities for providers | 4,811 | 88.88 | 70.01 |
| 25 | pesticide-residue food safety for homeowners | 4,808 | 88.87 | 70.26 |

## Current-market evidence that changed the raw Radar ordering

### Contractor-license verification — downgraded

The raw data-fragmentation thesis is still true, but the aggregation gap is no longer empty. Current products include:

- LicenseLayer — 50-state contractor verification API: https://licenselayer.net/
- TradesAPI — 50 states + DC and municipal boards: https://www.tradesapi.com/docs
- CheckLicensed — 50-state real-time verification API: https://checklicensed.com/license

**Implication:** do not build another generic lookup. Use license status as a feature in vendor monitoring, permit intelligence, prequalification or insurance/lending workflows.

### H-1B employer data — substantially downgraded

2026 competition is dense:

- H1BGrader reports 6M+ historical records and has a free sponsor checker extension for LinkedIn/Indeed/Glassdoor/Dice/Google Jobs: https://h1bgrader.com/
- MyVisaJobs has long-running employer/sponsor search: https://www.myvisajobs.com/employers/search.aspx
- H1BScope, H1BTrack, H1BInfo and other current databases expose sponsors, salaries and approvals.

**Implication:** high search interest does not equal a good new product. A recruiter/attorney workflow would need to solve something materially beyond sponsor search.

### Building permits — promoted to #1 business test

There is competition (including newpermits, Builtie, Shovels and broader construction-intelligence vendors), so raw permit access is not the wedge. However Seattle provides large public building/trade-permit datasets with frequent refreshes, and specialty contractors have a direct revenue action: identify work early and contact relevant businesses.

Sources/examples:

- Seattle Building Permits: https://data.seattle.gov/Built-Environment/Building-Permits/76t5-zqzr
- Seattle Trade Permits: https://data.seattle.gov/Built-Environment/Trade-Permits/c87v-5hwh
- Seattle Issued Building Permits: https://data.seattle.gov/Built-Environment/Issued-Building-Permits/8tqq-u7ib
- newpermits: https://newpermits.com/

**Wedge:** trade-specific shortlist + timing + contractor/project context + source provenance, starting in Seattle.

### SBIR/STTR — promoted

SBIR.gov currently exposes all historical awards as downloadable data; the main award file is refreshed monthly. The official site already does award/company search, and competitors such as SBIR.org and broad platforms such as HigherGov cover search/intelligence.

Sources:

- SBIR data resources: https://www.sbir.gov/data-resources
- SBIR awards: https://www.sbir.gov/awards
- SBIR.org: https://sbir.org/awards
- HigherGov market intelligence: https://www.highergov.com/ (or its market-intelligence product pages)

**Wedge:** not award search. Detect meaningful award events and connect them to the *next commercial action*: follow-on procurement, partners/suppliers, capture opportunities or investor watch signals.

### Endangered-species / environmental site screening — promoted as a broader pre-screen

USFWS IPaC is free and authoritative for the official species-review workflow; trying to replace it would be a poor thesis. But USFWS also exposes critical-habitat feature services and species data, while EPA ECHO provides live services and a weekly bulk file covering more than 1.5M regulated facilities.

Sources:

- IPaC: https://ipacb.ecosphere.fws.gov/
- USFWS ECOS data services: https://ecos.fws.gov/ecp/services
- EPA ECHO downloads: https://echo.epa.gov/tools/data-downloads
- EPA ECHO web services: https://echo.epa.gov/tools/web-services

**Wedge:** portfolio/batch triage and cross-source context *before* formal diligence. Never present the output as an official ESA determination, consultation, Phase I ESA, legal opinion or regulatory approval.

### Sanctions screening — economically attractive, operationally harder

The U.S. Consolidated Screening List provides free downloadable files and a fuzzy-search API, updated automatically. Commercial products such as sanctions.io already provide screening, monitoring and integrations.

- Official CSL: https://www.trade.gov/consolidated-screening-list
- sanctions.io pricing: https://help.sanctions.io/knowledge-base/resources/pricing-plans

**Implication:** potentially high willingness to pay, but not a good first validation build given compliance stakes and established vendors.

### Prevailing wage — real pain, narrower wedge required

WageFinder/HCM TradeSeal already provides free Davis-Bacon lookups, weekly updates and API/integration capabilities.

- https://wagefinder.org/

**Implication:** build only if the product moves into bid-impact calculation, estimator workflows, wage-change alerts and defensible payroll/estimate traceability.

### Restaurant inspection — downgraded

Yelp displays health scores using local-government partnerships and Ecolab/Health Department Intelligence; its LIVES program already solves a large portion of consumer discovery.

- https://biz.yelp.com/support-center/article/Where-does-Yelp-get-health-score-information
- https://trust.yelp.com/health-and-safety-data/

**Implication:** national consumer aggregation is not a whitespace opportunity. Restaurant distress / commercial-property intelligence may still be a feature elsewhere.

### Treatment directory — strongly downgraded

Recovery.com reports 25k+ provider listings and a large monthly engaged treatment-seeker audience, with professional referral tooling and provider monetization.

- https://recovery.com/pro/
- https://providers.recovery.com/

**Implication:** do not make this an early portfolio bet. It combines a powerful incumbent with sensitive/high-stakes user decisions.

### Airline OTP — downgraded

Cirium has maintained an on-time-performance franchise for more than 15 years and publishes current 2026 monthly reports.

- https://www.cirium.com/resources/on-time-performance/

The generated `hotels` buyer cluster does not expose a strong enough direct paid decision to justify competing here.

### Pesticide residue — downgraded

USDA PDP is a strong dataset, but EWG already owns substantial consumer awareness around pesticide/food-risk content. The likely economics are affiliate/content rather than an expensive recurring business decision.

## Provider-metric status

A one-shot GitHub Actions validator exists at `.github/workflows/top25-ahrefs-validation.yml`. It is capped at **25 representative Ahrefs calls**, stores no credential, and writes only sanitized metrics to a workflow artifact.

If `AHREFS_API_TOKEN` is not configured as a repository secret, it writes a `BLOCKED` artifact rather than replacing provider measurements with priors.

**Do not change the business-validation ranking merely because a keyword has high search volume.** Search demand is distribution evidence; payment and buyer action are product evidence.
