# Evidence Validator v1

Radar generates hypotheses cheaply. Evidence Validator decides which deserve expensive validation.

## Score

Each dimension is 0–5:

- Demand 20% — observed recurring interest or trigger volume.
- Pain 20% — evidence the job is costly, urgent, risky, or repeatedly manual.
- Money 25% — existing spend, pricing, budgets, or explicit willingness to pay.
- SERP weakness 15% — current results fail the buyer's actual job; competition lowers this score.
- Buildability 20% — authoritative data access, refreshability, coverage, and product feasibility.

Score = weighted dimension total / 5 × 100.

Evidence grade is separate:
- A: behavioral/first-party outcome evidence (payment, repeat use, conversion).
- B: multiple independent current sources, including direct market/product evidence.
- C: credible but incomplete/mostly secondary evidence.
- D: weak, stale, synthetic, or circular evidence.

## Gates

- Money <2 => REJECTED.
- Buildability <2 => REJECTED.
- Grade D => REJECTED.
- Score >=80 + grade A/B => strong research case, but still EVIDENCE_GATHERING.
- Only payment or repeat use can produce VALIDATED in v1.

This intentionally prevents a high research score from masquerading as commercial validation.

## Manual calibration — 2026-09-27

Initial scores are research priors, not product approvals.

| Rank | Wedge | Score | Grade | Key finding |
|---|---|---:|:---:|---|
| 1 | Permit intelligence → specialty contractors | 83 | B | Strong demonstrated spend and easy public-data build; competition is much heavier than Radar implied. |
| 2 | Prevailing-wage bid/compliance intelligence | 80 | B | Pain and spend are proven; generic compliance is crowded, so pre-bid impact/decision workflow is the wedge. |
| 3 | Contractor/vendor compliance → property managers | 80 | B | Recurring operational pain and established vendors; differentiation must be narrower than generic COI tracking. |
| 4 | Environmental/site-constraint pre-screen | 79 | B | High-value diligence job with established products; defensibility and authoritative local coverage raise build difficulty. |
| 5 | Permit + contractor intelligence → developers | 78 | B | Buildable and monetizable, but must outperform existing permit-data products on decision utility. |
| 6 | Sanctions monitoring → lenders | 76 | B | Strong spend/pain but crowded, compliance-sensitive, and relatively poor underdog build economics. |
| 7 | H-1B employer intelligence → recruiters | 72 | B | Government-backed data and paid competitors exist; basic sponsor lookup is commoditized. |
| 8 | SBIR/STTR → consultants/capture teams | 70 | B | Excellent official dataset and paid capture-intelligence market; next-action value needs direct buyer proof. |
| 9 | SBIR/STTR → investors | 65 | C | Buildable dataset; weaker direct evidence that SBIR event intelligence alone drives investor spend. |
| 10 | SBIR/STTR → suppliers | 61 | C | Plausible trigger intelligence, but buyer/job evidence is still thin. |

## Current source observations

Permit market: PingPermit advertises a 19-market feed at $499/month; FieldBrief advertises trade/city briefs from $79/month; PermitStack sells jurisdiction CSVs from $39; other vendors publish permit intelligence from roughly $41/month into the hundreds. This proves spend while also proving competition.

Prevailing wage: Miter says it serves 1,500+ contractors with prevailing-wage/certified-payroll workflows. SkillSmart, Dili, PrevailComply and others target the same pain. The opportunity therefore needs a narrower pre-bid or impact-analysis wedge, not another payroll system.

Site diligence: LandTech markets 50+ data layers for zoning/wetlands/site assessment; Basepoint describes 89-layer fatal-flaw screening. The buyer job is real, but broad national diligence is not a cheap first build.

Vendor compliance: Yardi VendorShield, RealPage and newer products automate vendor credential/compliance monitoring. Demand and spend are credible; generic document tracking is not differentiated.

SBIR: SBIR.gov exposes awards, companies, topics and bulk downloads covering the program history. The API is currently under maintenance, so bulk files are the safer ingestion route today. HigherGov and SBIR-focused products demonstrate a paid intelligence category.

H-1B: commercial products license government-derived sponsor data; at least one publishes $14/$39/$149 monthly tiers. A new product needs trigger/workflow intelligence rather than sponsor lookup.
