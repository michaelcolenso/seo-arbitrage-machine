# Unified SEO Arbitrage Platform

## Purpose

Build a repeatable machine for finding commercially valuable information gaps, proving
that a buyer exists, turning the winning data into a useful product, and using SEO as
one distribution channel.

The system is not an autonomous content farm. The unit of optimization is the
**opportunity**, not the page.

## Architecture

```text
                 ┌──────────────────────────────────────┐
                 │             SIGNAL LAYER             │
                 │                                      │
 Keywords ──────▶│ Radar: cheap 1M-row triage          │
 Pain signals ──▶│ Community / workflow monitors        │
 Public data ───▶│ Scout: CKAN/Socrata/API adapters     │
                 └─────────────────┬────────────────────┘
                                   │
                                   ▼
                 ┌──────────────────────────────────────┐
                 │          OPPORTUNITY GRAPH           │
                 │ dataset ↔ signal ↔ decision ↔ buyer │
                 │ monetization ↔ evidence ↔ outcome   │
                 └─────────────────┬────────────────────┘
                                   │
                                   ▼
                 ┌──────────────────────────────────────┐
                 │            VALIDATION GATES          │
                 │ demand / SERP / buyer / data access │
                 │ decision value / economics / moat   │
                 └─────────────────┬────────────────────┘
                                   │
                         APPROVE   │   REJECT/WATCH
                                   ▼
                 ┌──────────────────────────────────────┐
                 │                FACTORY               │
                 │ product blueprint → data pipeline   │
                 │ → utility pages → quality gate      │
                 └─────────────────┬────────────────────┘
                                   │
                                   ▼
                 ┌──────────────────────────────────────┐
                 │           DEPLOY + MEASURE           │
                 │ Cloudflare / GSC / conversion / $   │
                 └─────────────────┬────────────────────┘
                                   │
                                   ▼
                 ┌──────────────────────────────────────┐
                 │          PORTFOLIO LEARNING          │
                 │ hold / accelerate / scale / cull    │
                 │ archive evidence and update priors  │
                 └──────────────────────────────────────┘
```

## Stage 0 — Radar: million-keyword triage

The first pass must be cheap and deterministic. Loading one million rows into an LLM
or doing expensive SERP research on every keyword is structurally wrong.

Radar therefore computes a scan score from:
- log-scaled demand
- CPC
- keyword difficulty / SEO feasibility
- search intent

This stage only decides `REJECT` vs `REVIEW`.

A candidate can reach `PROMOTE` only after it has:
- a named buyer
- decision value
- monetization ease
- defensibility
- implementation complexity
- data leverage
- evidence quality

The final score weights the business case above SEO economics.

## Stage 1 — Signal enrichment

For the REVIEW set, attach evidence from multiple discovery modes:

### Demand-first
- Ahrefs / keyword metrics
- SERP weakness
- Search Console where an owned property already has impressions
- community pain language

### Data-first
- data.gov / CKAN
- Socrata
- federal and state APIs
- licensing, permit, inspection and enforcement registries
- bulk public releases

### Money-first
- named buyer segments
- current spend / substitute products
- cost of late or bad decisions
- lead value / contract size / subscription willingness
- refresh frequency and recurrence

## Stage 2 — Opportunity Graph

The long-term moat is a graph rather than a flat list of keywords.

Core nodes:
- Signal
- KeywordCluster
- Dataset
- EntityType
- ExpensiveDecision
- BuyerSegment
- MonetizationPattern
- ProductHypothesis
- Deployment
- Outcome

Core edges:
- SIGNAL_SUPPORTS_OPPORTUNITY
- DATASET_INFORMS_DECISION
- BUYER_MAKES_DECISION
- PRODUCT_SERVES_BUYER
- PRODUCT_USES_DATASET
- DEPLOYMENT_TESTS_HYPOTHESIS
- OUTCOME_UPDATES_PRIOR

The graph allows the system to learn patterns such as "inspection-change feeds sold to
local service vendors outperform broad informational directories" across verticals.

## Stage 3 — Validation

A promoted opportunity is not approved to build until these gates pass:

### Hard gates
- specific buyer exists
- recurring or high-value decision is clear
- at least one usable source exists
- legal/licensing constraints are understood
- a monetization mechanism exists now, not hypothetically
- an MVP can be delivered without building a generalized platform first

### Score

Use the OpportunityForge form:

```text
(Demand × Decision Value × Monetization Ease × Defensibility) / Complexity
```

Then apply evidence/data-quality modifiers. Search volume is evidence of demand, not a
proxy for the entire opportunity.

## Stage 4 — Factory

The compiler should support multiple product shapes rather than assuming every winner
is a directory:

- searchable directory
- alert / watchlist
- ranked prospect list
- calculator
- compliance monitor
- comparison tool
- report / briefing
- API / data feed

The current Astro directory/calculator compiler is retained as the first implementation.
Additional product templates should be added only after repeated validated demand.

## Stage 5 — Quality gate

No generated page should deploy merely because a template rendered successfully.
Required checks should include:
- explicit intent match
- differentiation angle
- conversion path
- information gain
- evidence/claim support
- adequate unique data per route
- non-repetitive copy
- internal-link opportunity
- canonical/indexability correctness

Thin pages should be merged, noindexed or withheld rather than published to hit a page-count target.

## Stage 6 — Measurement

Separate vanity metrics from business metrics.

### Discovery metrics
- datasets indexed
- keyword rows scanned
- REVIEW rate
- PROMOTE rate
- cost per promoted hypothesis

### Validation metrics
- hypotheses tested
- approval rate
- time to decision
- buyer conversations / positive responses

### SEO metrics
- indexed pages
- impressions
- clicks
- CTR
- query coverage

### Business metrics
- leads
- qualified leads
- conversion rate
- revenue
- gross margin
- revenue per 1,000 organic visits
- revenue per deployed opportunity

The optimizer must never infer profitability from traffic alone.

## Stage 7 — Portfolio policy

Import the useful Mortician principle: weak experiments should not live forever.
But decisions must be based on verified measurements and configurable policy.

Possible outcomes:
- `METRICS_REQUIRED`
- `HOLD`
- `ACCELERATE`
- `SCALE`
- `CULL`

Culling should consider age, traffic trajectory, conversions, revenue and original
hypothesis, with no destructive action when metrics are absent.

## Cost discipline for 1M keywords

The pipeline should progressively spend more only on scarcer candidates:

```text
1,000,000 raw keywords
      ↓ deterministic local scoring
~50,000 REVIEW candidates
      ↓ clustering / dedupe
~5,000 clusters
      ↓ cheap source + buyer enrichment
~500 plausible opportunities
      ↓ SERP / competitor / data validation
~50 dossiers
      ↓ manual or agent deep research
~5 build candidates
      ↓ measured MVPs
1–2 scaled winners
```

The exact conversion rates are targets, not assumptions. Every run records actual funnel ratios.

## Repository policy

`seo-arbitrage-machine` is canonical. `agentic-arbitrage` and `codex-seo-machine`
remain reference archives until useful behavior has been ported and tested. New work
should not add another parallel orchestration stack.
