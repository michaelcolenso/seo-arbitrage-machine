"""Deterministic 1,000,000-keyword public-data opportunity universe.

The generated metrics are *priors*, never provider measurements.  They exist to
make the first million-row pass cheap and reproducible.  Radar's promotion gate
requires verified metrics before any generated candidate may reach PROMOTE.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterator

from .models import KeywordCandidate


@dataclass(frozen=True)
class OpportunityFamily:
    id: str
    topic: str
    score: int
    buyer_group: str
    data_source_name: str
    data_source_url: str | None
    decision: str
    product_pattern: str


BUYER_GROUPS: dict[str, tuple[str, ...]] = {
    "construction": ("contractors", "subcontractors", "estimators", "developers", "property managers"),
    "immigration": ("visa applicants", "recruiters", "immigration attorneys", "HR teams", "employers"),
    "consumer_home": ("homeowners", "homebuyers", "property managers", "insurers", "contractors"),
    "healthcare": ("patients", "families", "providers", "recruiters", "healthcare attorneys"),
    "hospitality": ("diners", "restaurant owners", "suppliers", "insurers", "commercial brokers"),
    "compliance": ("compliance officers", "attorneys", "insurers", "lenders", "consultants"),
    "government_sales": ("government contractors", "grant writers", "investors", "suppliers", "consultants"),
    "environmental": ("developers", "environmental consultants", "insurers", "lenders", "property owners"),
    "legal_property": ("real estate investors", "attorneys", "lenders", "title companies", "property managers"),
    "travel": ("travelers", "travel agents", "hotels", "tour operators", "travel insurers"),
    "cyber": ("security teams", "MSPs", "cyber insurers", "compliance teams", "software vendors"),
    "finance": ("plan sponsors", "advisors", "brokers", "insurers", "consultants"),
    "benefits": ("benefit applicants", "nonprofits", "retailers", "agencies", "policy analysts"),
    "public_safety": ("residents", "insurers", "attorneys", "property managers", "researchers"),
    "business": ("founders", "lenders", "attorneys", "sales teams", "investors"),
}


FAMILIES: tuple[OpportunityFamily, ...] = (
    OpportunityFamily("contractor-license", "contractor license verification", 9, "construction", "State contractor licensing boards", None, "verify whether a contractor is licensed, bonded and eligible to work", "verification + lead intelligence"),
    OpportunityFamily("h1b-employer", "H-1B employer sponsorship", 9, "immigration", "DOL OFLC disclosure data", "https://www.dol.gov/agencies/eta/foreign-labor/performance", "identify employers, roles and wages with real sponsorship history", "employer intelligence + attorney leads"),
    OpportunityFamily("prevailing-wage", "Davis-Bacon prevailing wage", 8, "construction", "SAM.gov Wage Determinations", "https://sam.gov/content/wage-determinations", "price labor correctly before bidding federally funded work", "lookup + bid calculator + alerts"),
    OpportunityFamily("drinking-water", "drinking water quality", 8, "consumer_home", "EPA ECHO / SDWIS", "https://echo.epa.gov/tools/web-services", "understand local drinking-water violations and risk", "local risk lookup + affiliate"),
    OpportunityFamily("treatment-locator", "substance abuse treatment facility", 8, "healthcare", "SAMHSA FindTreatment", "https://findtreatment.gov/locator", "find an appropriate treatment provider quickly", "directory + qualified lead generation"),
    OpportunityFamily("restaurant-inspection", "restaurant health inspection", 8, "hospitality", "Local health department open data", None, "assess restaurant inspection history and risk", "national inspection aggregator"),
    OpportunityFamily("building-permits", "building permit intelligence", 8, "construction", "Census BPS + municipal permit portals", "https://www.census.gov/construction/bps/", "spot construction activity, competitors and project leads early", "permit intelligence + lead feed"),
    OpportunityFamily("sanctions-screening", "OFAC BIS sanctions screening", 8, "compliance", "U.S. Consolidated Screening List", "https://www.trade.gov/consolidated-screening-list", "screen counterparties before a regulated transaction", "screening API + monitoring"),
    OpportunityFamily("sbir-awards", "SBIR STTR awards", 8, "government_sales", "SBIR.gov awards", "https://www.sbir.gov/awards", "identify funded companies, topics and follow-on opportunity", "award intelligence + alerts"),
    OpportunityFamily("pesticide-residue", "pesticide residue food safety", 8, "consumer_home", "USDA Pesticide Data Program", "https://www.ams.usda.gov/datasets/pdp", "compare food residue risk and make purchasing decisions", "food risk pages + affiliate"),
    OpportunityFamily("environmental-risk", "EPA environmental facility risk", 7, "environmental", "EPA ECHO", "https://echo.epa.gov/tools/web-services", "evaluate regulated-facility and property environmental risk", "address risk intelligence"),
    OpportunityFamily("endangered-species", "endangered species compliance", 8, "environmental", "USFWS ECOS / IPaC", "https://ecos.fws.gov/ecp/", "screen development sites for species and habitat constraints", "project compliance checker + consultant leads"),
    OpportunityFamily("drug-adverse-events", "drug adverse event reports", 7, "healthcare", "openFDA FAERS", "https://open.fda.gov/apis/drug/event/", "understand reported adverse-event patterns for a drug", "evidence pages + legal/consumer leads"),
    OpportunityFamily("park-crowds", "national park crowd levels", 7, "travel", "NPS visitor statistics", "https://irma.nps.gov/Stats/", "choose lower-crowd dates and destinations", "crowd forecast + travel affiliate"),
    OpportunityFamily("campaign-contracts", "campaign finance government contractor", 7, "government_sales", "OpenFEC + USAspending", "https://api.open.fec.gov/developers/", "trace relationships between political giving and federal contracting", "research intelligence + export"),
    OpportunityFamily("per-diem", "GSA per diem rates", 7, "travel", "GSA Per Diem API", "https://open.gsa.gov/api/perdiem/", "calculate reimbursable travel rates by place and date", "calculator + travel affiliate"),
    OpportunityFamily("fair-market-rents", "HUD fair market rents", 6, "legal_property", "HUD FMR data", "https://www.huduser.gov/portal/datasets/fmr.html", "compare rent benchmarks for underwriting and housing decisions", "local rent lookup + lead gen"),
    OpportunityFamily("tax-delinquent", "tax delinquent properties", 7, "legal_property", "County treasurer delinquency lists", None, "find distressed property before auction or foreclosure", "deal feed + investor subscription"),
    OpportunityFamily("nursing-home", "nursing home quality ratings", 6, "healthcare", "CMS Care Compare datasets", "https://data.cms.gov/provider-data/topics/nursing-homes", "compare nursing-home quality, staffing and enforcement history", "facility research + referral"),
    OpportunityFamily("kev", "known exploited vulnerabilities", 6, "cyber", "CISA KEV Catalog", "https://www.cisa.gov/known-exploited-vulnerabilities-catalog", "prioritize vulnerabilities known to be exploited", "security prioritization + alerts"),
    OpportunityFamily("form-5500", "Form 5500 pension plan", 7, "finance", "DOL Form 5500 datasets", "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets", "identify plan sponsors, fees and advisory opportunities", "prospecting + plan intelligence"),
    OpportunityFamily("fha-203k", "FHA 203k renovation", 6, "construction", "HUD FHA 203(k)", "https://www.hud.gov/hud-partners/single-family-203k", "estimate renovation financing feasibility and cost", "renovation calculator + lender leads"),
    OpportunityFamily("timber-sales", "Forest Service timber sales", 7, "construction", "USFS timber sales", "https://www.fs.usda.gov/forest-management/products/timber-sales", "find timber-sale supply and procurement opportunities", "sale finder + supplier intelligence"),
    OpportunityFamily("mechanics-liens", "mechanics liens", 7, "legal_property", "County recorder lien filings", None, "detect payment distress and lien exposure early", "property risk + legal/lending leads"),
    OpportunityFamily("passport-times", "passport processing times", 7, "travel", "U.S. State Department", "https://travel.state.gov/content/travel/en/passports/how-apply/processing-times.html", "estimate passport timing before travel", "tracker + travel affiliate"),
    OpportunityFamily("osha-safety", "OSHA workplace safety", 6, "compliance", "OSHA enforcement data", "https://www.osha.gov/data", "assess employer inspection and safety history", "employer risk lookup + leads"),
    OpportunityFamily("snap-retailers", "SNAP retailer", 6, "benefits", "USDA FNS SNAP retailer data", "https://www.fns.usda.gov/snap/retailer", "find authorized benefit retailers and market coverage gaps", "locator + market intelligence"),
    OpportunityFamily("broadband", "broadband availability", 6, "consumer_home", "FCC Broadband Data Collection", "https://broadbandmap.fcc.gov/data-download", "compare service availability and providers by location", "availability lookup + affiliate"),
    OpportunityFamily("fara", "FARA foreign lobbying", 6, "compliance", "DOJ FARA filings", "https://efile.fara.gov/", "research foreign-principal representation and lobbying activity", "entity intelligence + alerts"),
    OpportunityFamily("campus-safety", "campus safety Clery Act", 5, "public_safety", "U.S. Education Campus Safety", "https://ope.ed.gov/campussafety/", "compare campus crime and safety history", "college safety research"),
    OpportunityFamily("nuclear-safety", "nuclear plant safety", 6, "compliance", "U.S. NRC public data", "https://www.nrc.gov/data", "monitor plant events, inspections and enforcement", "facility safety intelligence"),
    OpportunityFamily("fha-condo", "FHA condo approval", 5, "legal_property", "HUD FHA condo lookup", "https://entp.hud.gov/idapp/html/condlook.cfm", "check whether a condo project is FHA approved", "approval lookup + mortgage leads"),
    OpportunityFamily("hud-inspection", "HUD REAC inspection scores", 5, "legal_property", "HUD physical inspection data", "https://www.huduser.gov/portal/datasets/pis.html", "assess affordable-housing property inspection risk", "property due diligence"),
    OpportunityFamily("blm-leases", "BLM oil gas leases", 5, "finance", "BLM land and mineral records", "https://www.blm.gov/services/land-records", "monitor federal lease positions and upcoming activity", "lease intelligence + alerts"),
    OpportunityFamily("water-supply", "western water supply", 6, "environmental", "Bureau of Reclamation water data", "https://www.usbr.gov/water/", "monitor water availability for operating and investment decisions", "supply dashboard + alerts"),
    OpportunityFamily("cpsc-recalls", "CPSC product recalls", 7, "consumer_home", "U.S. CPSC recalls", "https://www.cpsc.gov/Recalls", "identify recalled products and affected brands quickly", "recall lookup + monitoring"),
    OpportunityFamily("business-entity", "business entity registration", 6, "business", "State Secretary of State registries", None, "verify entity status, officers and registration history", "entity search + B2B intelligence"),
    OpportunityFamily("airline-ontime", "airline on-time performance", 8, "travel", "BTS TranStats", "https://www.transtats.bts.gov/", "compare route and carrier reliability before booking", "route reliability + travel affiliate"),
    OpportunityFamily("police-incidents", "police incident data", 5, "public_safety", "Municipal police open-data portals", None, "understand local incident patterns and property risk", "local safety maps"),
    OpportunityFamily("military-bah", "military BAH rates", 5, "consumer_home", "DoD BAH tables", "https://www.travel.dod.mil/Allowances/Basic-Allowance-for-Housing/BAH-Rate-Lookup/", "calculate housing allowance by duty station and status", "calculator + relocation leads"),
)


STATES: tuple[str, ...] = (
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
    "Wisconsin", "Wyoming",
)

INTENT_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("lookup", "commercial", "{topic} lookup {state} {modifier} for {buyer}"),
    ("database", "commercial", "{state} {topic} database {modifier} for {buyer}"),
    ("alerts", "transactional", "{topic} alerts {state} {modifier} for {buyer}"),
    ("tracker", "commercial", "{state} {topic} tracker {modifier} for {buyer}"),
    ("report", "comparison", "{topic} report {state} {modifier} for {buyer}"),
    ("search", "commercial", "search {state} {topic} {modifier} for {buyer}"),
    ("compliance", "transactional", "{state} {topic} compliance {modifier} for {buyer}"),
    ("leads", "transactional", "{topic} leads {state} {modifier} for {buyer}"),
    ("api", "commercial", "{state} {topic} API {modifier} for {buyer}"),
    ("download", "informational", "download {state} {topic} data {modifier} for {buyer}"),
)

MODIFIERS: tuple[str, ...] = (
    "2026", "by city", "by county", "requirements", "violations",
    "pricing", "free", "near me", "list", "data",
)

UNIVERSE_SIZE = len(FAMILIES) * len(STATES) * 5 * len(INTENT_PATTERNS) * len(MODIFIERS)
assert UNIVERSE_SIZE == 1_000_000


def _stable_unit(value: str) -> float:
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


def _prior_metrics(family: OpportunityFamily, keyword: str) -> tuple[int, float, float]:
    """Return ranking priors, not claimed search-provider measurements."""
    u = _stable_unit(keyword)
    v = _stable_unit(keyword + "|cpc")
    w = _stable_unit(keyword + "|kd")
    base_volume = {9: 3500, 8: 2200, 7: 1200, 6: 650, 5: 300}[family.score]
    volume = int(base_volume * (0.25 + 2.5 * u))
    cpc = max(0.05, (family.score - 4) * 0.75 * (0.4 + 1.4 * v))
    kd = max(5.0, min(90.0, (10 - family.score) * 7 + 45 * w))
    return volume, round(cpc, 4), round(kd, 4)


def _business_priors(family: OpportunityFamily) -> dict[str, float]:
    score = float(family.score)
    return {
        "decision_value": min(10.0, score),
        "monetization_ease": max(5.0, score - 0.5),
        "defensibility": min(9.0, 5.0 + max(0.0, score - 5.0) * 0.9),
        "complexity": max(2.0, 11.0 - score),
        "data_leverage": min(10.0, score),
        "evidence_quality": max(5.0, min(8.5, score - 0.5)),
    }


def iter_keyword_universe(limit: int | None = None) -> Iterator[KeywordCandidate]:
    """Yield the canonical deterministic million-row discovery universe."""
    emitted = 0
    for family in FAMILIES:
        buyers = BUYER_GROUPS[family.buyer_group]
        priors = _business_priors(family)
        for state in STATES:
            for buyer in buyers:
                for _intent_name, intent, template in INTENT_PATTERNS:
                    for modifier in MODIFIERS:
                        keyword = template.format(
                            topic=family.topic, state=state, modifier=modifier, buyer=buyer
                        )
                        volume, cpc, kd = _prior_metrics(family, keyword)
                        yield KeywordCandidate(
                            keyword=keyword,
                            source="generated-public-data-universe:v1",
                            volume=volume,
                            cpc=cpc,
                            kd=kd,
                            intent=intent,
                            metrics_source="deterministic-prior:v1",
                            metrics_verified=False,
                            family_id=family.id,
                            geography=state,
                            decision=family.decision,
                            product_pattern=family.product_pattern,
                            data_source_name=family.data_source_name,
                            data_source_url=family.data_source_url,
                            buyer=buyer,
                            business_evidence_verified=False,
                            **priors,
                        )
                        emitted += 1
                        if limit is not None and emitted >= limit:
                            return


def family_by_id(family_id: str | None) -> OpportunityFamily | None:
    if not family_id:
        return None
    return next((family for family in FAMILIES if family.id == family_id), None)
