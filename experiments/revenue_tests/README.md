# Revenue tests — September 2026

These are deliberately small demand tests for the strongest *currently defensible* opportunity wedges after the 1M Radar pass and current-market competition review.

They are not production products. Their job is to answer one question quickly: **will a specific buyer take a high-intent action at a plausible price?**

## Run locally

```bash
python experiments/revenue_tests/server.py
```

Open `http://127.0.0.1:8788/`.

Leads are stored in `experiments/revenue_tests/revenue_tests.sqlite` unless `DSF_EXPERIMENT_DB` is set. To export CSV, set `DSF_EXPERIMENT_ADMIN_TOKEN` and request `/admin/export.csv` with the same value in the `X-Admin-Token` header.

## 1. PermitSignal

**Buyer:** Seattle-area specialty contractors, estimators, owners and business-development staff.

**Offer:** a daily permit-to-opportunity feed filtered by trade, geography, project type, value and permit stage, with source provenance and business-only outreach signals.

**Price test:** $49/month beta; explicit secondary signal at $99+/month.

**Why this wedge instead of a permit database:** public permits are easy to find and permit-lead competitors exist. The hypothesis is that trade-specific filtering, timing, contractor context and a very small daily shortlist are worth paying for.

**Launch market:** Seattle first, where the City publishes daily/frequently refreshed building and trade-permit data and the operator has construction-domain knowledge and an existing BuildingSeattle distribution asset.

**Success gate (30 days):**
- 40+ qualified contractor visitors or direct prospects;
- 10 sample requests;
- 5 walkthrough requests;
- **3 explicit paid-beta intents OR 2 actual paying beta customers**.

**Kill/reshape signal:** fewer than two qualified paid intents after 75 targeted contractor conversations/visits.

## 2. SBIR Signal

**Buyer:** government-business-development consultants, capture teams, suppliers and investors.

**Offer:** detect significant SBIR/STTR awards, enrich the company/technology, and surface likely follow-on procurement, partnership, supplier or investment actions.

**Price test:** $99/month beta; explicit $249+/month signal for high-quality follow-on intelligence.

**Why this wedge instead of award search:** SBIR.gov, SBIR.org and broader government-intelligence platforms already make awards searchable. The hypothesis is that *award → likely next commercial action* is the paid layer.

**Success gate (30 days):**
- 30 qualified prospects;
- 8 sample-alert requests;
- 4 walkthroughs;
- **3 explicit $99+ paid intents OR 2 paying pilots**.

**Kill/reshape signal:** buyers praise the data but cannot name an action they would take from an alert.

## 3. SiteConstraint

**Buyer:** developers, acquisitions teams, environmental consultants, lenders and insurers screening multiple project sites.

**Offer:** a fast public-data pre-screen combining USFWS species/critical-habitat signals and EPA ECHO regulated-facility/compliance context, with source links and explicit uncertainty.

**Price test:** $39/project or $149/month for up to ten pre-screens.

**Why this wedge instead of competing with IPaC:** IPaC is the official USFWS project-planning/review tool and should remain the authoritative workflow. SiteConstraint tests a different job: **batch portfolio triage before formal diligence** and cross-source context outside a single regulatory system.

**Safety boundary:** the product must never present itself as an official species list, ESA determination, consultation, Phase I ESA, legal opinion, underwriting decision or regulatory approval.

**Success gate (30 days):**
- 20 qualified development/diligence prospects;
- 6 sample-site requests;
- 3 walkthroughs;
- **2 paid project intents OR 1 paying portfolio customer**.

**Kill/reshape signal:** users say they simply run every site through IPaC/ECHO manually and do not value portfolio triage, saved history, comparison or alerting.

## Evidence hierarchy

Revenue-test decisions use this order:

1. **Actual payment / signed pilot**
2. Explicit price intent from a named target buyer
3. Walkthrough/demo request
4. Sample request
5. Email signup / page engagement
6. Keyword/search estimates

A high Radar or Ahrefs score must not override a failed buyer/payment test.
