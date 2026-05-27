"""Bright Data client — the live web data layer.

Wraps the Bright Data unified request API (SERP, Web Unlocker, Scraper zones).
Reads credentials from .env. A SpendTracker enforces TAKI_BD_SPEND_CAP so an
unattended run can never burn the whole credit.

Wired but live calls need BRIGHTDATA_API_KEY + zones. Pure helpers (payload,
spend tracking, html->text) are unit-tested offline; the live smoke test is
gated on keys.
"""

from __future__ import annotations

import os
import re
import urllib.parse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.schemas import SharedBundle, SourceItem, SourceSubject, SourceType
from services.url_audit import is_low_quality

_API = "https://api.brightdata.com/request"


class BudgetExceeded(RuntimeError):
    pass


class SpendTracker:
    """Soft spend guard. Estimates cost per request and refuses to exceed the cap."""

    def __init__(self, cap_usd: float, cost_per_request: float = 0.001):
        self.cap_usd = cap_usd
        self.cost_per_request = cost_per_request
        self.spent = 0.0

    def charge(self) -> None:
        if self.spent + self.cost_per_request > self.cap_usd:
            raise BudgetExceeded(
                f"Bright Data spend cap ${self.cap_usd} would be exceeded "
                f"(spent ${self.spent:.3f})."
            )
        self.spent += self.cost_per_request


def build_payload(zone: str, url: str, fmt: str = "raw") -> dict:
    return {"zone": zone, "url": url, "format": fmt}


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class BrightDataClient:
    def __init__(
        self,
        api_key: str | None = None,
        serp_zone: str | None = None,
        unlocker_zone: str | None = None,
        scraper_zone: str | None = None,
        tracker: SpendTracker | None = None,
    ):
        self.api_key = api_key or os.environ.get("BRIGHTDATA_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "BRIGHTDATA_API_KEY not set — add it (and zones) to .env for live runs."
            )
        self.serp_zone = serp_zone or os.environ.get("BRIGHTDATA_SERP_ZONE", "")
        self.unlocker_zone = unlocker_zone or os.environ.get(
            "BRIGHTDATA_UNLOCKER_ZONE", ""
        )
        self.scraper_zone = scraper_zone or os.environ.get("BRIGHTDATA_SCRAPER_ZONE", "")
        self.tracker = tracker or SpendTracker(
            float(os.environ.get("TAKI_BD_SPEND_CAP", "50"))
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def _request(self, zone: str, url: str, fmt: str = "raw") -> str:
        # 30s per attempt (was 90s) — with 3 retries the worst-case is ~90s
        # per URL instead of 270s. Self-mode often runs 4+ URLs, so cutting
        # the per-URL ceiling makes a 'one bad URL' run finish in minutes
        # rather than freezing the entire cascade.
        self.tracker.charge()
        resp = httpx.post(
            _API,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=build_payload(zone, url, fmt),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text

    def serp(self, query: str) -> str:
        q = urllib.parse.quote(query)
        return self._request(self.serp_zone, f"https://www.google.com/search?q={q}")

    def unlock(self, url: str) -> str:
        return self._request(self.unlocker_zone, url)


# ─── V7.26 — Source-tier classifier + domain registry ────────────────────
#
# Each candidate URL is tagged with a quality tier so the SERP merge step
# can prefer high-signal domains and cap the share of community/aggregator
# noise. Tiers (lower number = more authoritative):
#
#   T1 — regulator, official statistic, intergovernmental body
#   T2 — academic / peer-reviewed
#   T3 — newspaper of record + top-tier analyst
#   T4 — trade publication + recognized expert column
#   T5 — community / aggregator (capped at ~30% of the bundle)
#   T6 — review aggregator (capped together w/ T5)
#   T0 — UNCLASSIFIED (treated as T4 fallback so we don't drop unknown
#        but plausible domains entirely)
#
# Substring match on host is sufficient — these are stable institutional
# domains; we don't need full PSL parsing.

T1_REGULATOR  = "T1"   # *.gov, *.europa.eu, sec.gov, eur-lex, iea, irena, ...
T2_ACADEMIC   = "T2"   # scholar, nature, science, jstor, arxiv, *.edu
T3_NEWS       = "T3"   # ft.com, bloomberg, reuters, economist, mckinsey
T4_TRADE      = "T4"   # techcrunch, theinformation, redmonk, industry trades
T5_COMMUNITY  = "T5"   # reddit, HN, medium, substack
T6_REVIEW     = "T6"   # g2, trustpilot, capterra, glassdoor
T0_UNKNOWN    = "T0"   # default fallback

TIER_WEIGHT = {
    T1_REGULATOR: 1.00,
    T2_ACADEMIC:  1.00,
    T3_NEWS:      0.85,
    T4_TRADE:     0.70,
    T5_COMMUNITY: 0.40,
    T6_REVIEW:    0.50,
    T0_UNKNOWN:   0.60,
}

# Suffixes match the END of the hostname (after `.`).
_TIER_SUFFIXES = {
    T1_REGULATOR: (
        # National + EU government / military domains
        ".gov", ".mil", ".gov.uk", ".gov.ie", ".gov.au", ".gov.ca",
        ".europa.eu", ".gov.eu",                # NOT ".eu" — too broad (matches orchid.eu etc.)
        # Intergovernmental + global statistic bodies
        "oecd.org", "imf.org", "worldbank.org", "iea.org", "irena.org",
        "un.org", "who.int", "iso.org", "nist.gov", "noaa.gov",
        "ec.europa.eu", "ecb.europa.eu", "eea.europa.eu", "epa.gov",
        "sec.gov", "esma.europa.eu",
        "eur-lex.europa.eu", "europarl.europa.eu",
        "ons.gov.uk", "bls.gov", "fred.stlouisfed.org", "stlouisfed.org",
        "bea.gov", "statistics.gov.uk", "eurostat.ec.europa.eu",
        # National regulators / TSOs / system operators (energy-relevant)
        "transelectrica.ro",                    # RO transmission grid
        "ofgem.gov.uk", "ferc.gov", "rte-france.com",
    ),
    T2_ACADEMIC: (
        "scholar.google.com", "nature.com", "science.org", "sciencemag.org",
        "jstor.org", "arxiv.org", "ssrn.com", "pubmed.ncbi.nlm.nih.gov",
        "ncbi.nlm.nih.gov", "biorxiv.org", "medrxiv.org",
        "sciencedirect.com", "springer.com", "wiley.com", "tandfonline.com",
        "cambridge.org", "oup.com", "mit.edu", "stanford.edu", "harvard.edu",
        "ac.uk", "edu.au", ".edu",
        "researchgate.net", "academia.edu",
        # Policy research institutes + environmental NGOs (academic-grade)
        "sei.org",       # Stockholm Environment Institute
        "eeb.org",       # European Environmental Bureau
        "wri.org",       # World Resources Institute
        "iiasa.ac.at",   # International Institute for Applied Systems Analysis
        "bruegel.org",   # EU policy think tank
        "rff.org",       # Resources for the Future
    ),
    T3_NEWS: (
        "ft.com", "bloomberg.com", "reuters.com", "wsj.com", "nytimes.com",
        "washingtonpost.com", "economist.com", "theguardian.com",
        "telegraph.co.uk", "bbc.co.uk", "bbc.com", "cnbc.com", "forbes.com",
        "businessinsider.com", "fortune.com", "axios.com",
        "mckinsey.com", "bcg.com", "bain.com", "deloitte.com", "pwc.com",
        "kpmg.com", "ey.com", "gartner.com", "forrester.com", "idc.com",
        "morningstar.com", "spglobal.com", "fitchratings.com", "moodys.com",
        "statista.com", "crunchbase.com", "pitchbook.com",
    ),
    T4_TRADE: (
        "techcrunch.com", "theinformation.com", "wired.com", "arstechnica.com",
        "theverge.com", "engadget.com", "venturebeat.com",
        "redmonk.com", "stratechery.com", "a16z.com",
        "hpcwire.com", "datanami.com", "bigdatawire.com",          # HPC / big data
        "infoq.com", "thenewstack.io", "registerm.com",            # software trade
        # industry trades — wind / solar / renewable
        "windpowermonthly.com", "renewableenergyworld.com",
        "rechargenews.com", "energypost.eu", "pv-magazine.com",
        "windpowerengineering.com", "windustry.org", "windeurope.org",
        "iea-wind.org", "ewea.org", "globalwindenergycouncil.com",
        "windenergyhamburg.com",                # industry exhibition
        "energynomics.ro",                      # Romanian energy trade press
        "energyworld.com",                      # global energy trade
        "rechargenews.com", "energy-storage.news",
        # industry trades — finance/SaaS
        "saastr.com", "fintech.com", "fintechnews.org",
        # industry trades — health/biotech
        "fiercebiotech.com", "biopharmadive.com", "endpointsnews.com",
        # industry trades — manufacturing
        "industryweek.com", "manufacturing.net",
        # market research firms (T4 tier — paywalled summary content)
        "futuremarketinsights.com", "technavio.com", "marketresearchfuture.com",
        "marketsandmarkets.com", "grandviewresearch.com", "alliedmarketresearch.com",
        "tracxn.com",
    ),
    T5_COMMUNITY: (
        "reddit.com", "news.ycombinator.com", "lobste.rs", "hackernews.com",
        "medium.com", "substack.com", "dev.to", "hashnode.com",
        "twitter.com", "x.com", "linkedin.com",  # social — caveat: behind walls
        "quora.com", "stackoverflow.com", "stackexchange.com",
    ),
    T6_REVIEW: (
        "g2.com", "trustpilot.com", "capterra.com", "softwareadvice.com",
        "glassdoor.com", "indeed.com", "comparably.com",
        "productpan.com", "producthunt.com",
    ),
}

# Hard blocklist — domains we never want in the bundle.
_BLOCKED_SUFFIXES = (
    "blogspot.com", "wordpress.com",   # untyped UGC
    "scribd.com", "slideshare.net",    # paywall/login-walled
    "facebook.com", "instagram.com", "tiktok.com", "pinterest.com",
)


def classify_url(url: str) -> str:
    """Return the tier code for a URL host. Substring suffix match."""
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return T0_UNKNOWN
    if not host:
        return T0_UNKNOWN
    # blocked → return a sentinel handled by caller
    for s in _BLOCKED_SUFFIXES:
        if host == s or host.endswith("." + s):
            return "BLOCKED"
    for tier, suffixes in _TIER_SUFFIXES.items():
        for s in suffixes:
            if host == s or host.endswith("." + s) or host.endswith(s):
                return tier
    return T0_UNKNOWN


# ─── V7.22 — SERP-based external source discovery ────────────────────────
#
# Surfaces non-target-domain perspectives (reviews, HN/Reddit threads,
# competitor comparisons, incident reports, funding news) so the cascade
# isn't restricted to scraping the target's own marketing copy.
#
# Uses the Web Unlocker zone against google.com/search rather than the
# SERP zone (which is often unconfigured in dev .env files) — google.com
# is just a regular URL to the unlocker.

_SERP_HREF_RE = re.compile(
    r'href="(?:/url\?q=)?(https?://[^"&<>\s]+)',
    re.IGNORECASE,
)

# Hosts that pollute SERP results without informational value.
_SERP_BLOCKLIST = (
    "google.", "gstatic.", "youtube.", "webcache.", "doubleclick.",
    "googleadservices.", "googlesyndication.",
)


def _clean_serp_url(url: str) -> str:
    """Strip text fragments (#:~:text=...) and one trailing slash. Preserve query."""
    u = url.split("#")[0]
    if u.endswith("/") and u.count("/") > 3:  # keep trailing on bare-domain (https://host/)
        u = u[:-1]
    return u


def parse_serp_results(
    html: str,
    exclude_hosts: set[str] | None = None,
    max_urls: int = 12,
) -> list[str]:
    """Extract external result URLs from a Google SERP page.

    Drops Google internals, the target's own domain (+subdomains), URL
    fragments, and duplicates. Order preserved as in the HTML so the
    higher-ranked results come first.
    """
    excl = {h.lower() for h in (exclude_hosts or set())}
    seen: set[str] = set()
    out: list[str] = []
    for u in _SERP_HREF_RE.findall(html):
        u = _clean_serp_url(u)
        if not u or u in seen:
            continue
        host = (urllib.parse.urlparse(u).hostname or "").lower()
        if not host:
            continue
        if any(part in host for part in _SERP_BLOCKLIST):
            continue
        if any(host == h or host.endswith("." + h) for h in excl):
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= max_urls:
            break
    return out


def discover_external_sources(
    target: str,
    client: BrightDataClient,
    queries: list[tuple[str, SourceType]],
    exclude_hosts: list[str] | None = None,
    n_per_query: int = 3,
    on_event=None,
    low_tier_cap: float = 0.30,
) -> list[tuple[str, SourceType]]:
    """Run each Google SERP query, extract top result URLs, tag w/ source_type.

    V7.26 — Each discovered URL is classified by domain tier (T1-T6) and
    BLOCKED hosts are dropped outright. Community + review hosts (T5+T6
    combined) are capped at low_tier_cap of the final bundle so Reddit /
    G2 can't drown out higher-signal sources.

    Returns deduplicated list of (url, source_type) tuples in query order.
    Per-query failures are reported via on_event but don't abort the pass.
    """
    excl = {h.lower() for h in (exclude_hosts or [])}
    candidates: list[tuple[str, SourceType, str]] = []   # (url, stype, tier)
    seen_urls: set[str] = set()
    tier_count: dict[str, int] = {}

    for query, stype in queries:
        if on_event:
            on_event({"status": "serp_start", "query": query})
        try:
            q = urllib.parse.quote(query)
            html = client.unlock(f"https://www.google.com/search?q={q}")
        except Exception as e:
            if on_event:
                on_event({
                    "status": "serp_error", "query": query,
                    "error": f"{type(e).__name__}: {e}",
                })
            continue
        urls = parse_serp_results(html, exclude_hosts=excl, max_urls=n_per_query * 6)
        picked_for_query = 0
        for u in urls:
            if u in seen_urls:
                continue
            tier = classify_url(u)
            if tier == "BLOCKED":
                continue
            seen_urls.add(u)
            candidates.append((u, stype, tier))
            tier_count[tier] = tier_count.get(tier, 0) + 1
            picked_for_query += 1
            if picked_for_query >= n_per_query:
                break
        if on_event:
            on_event({
                "status": "serp_done", "query": query,
                "found": picked_for_query, "source_type": stype.value,
            })

    # V7.26 — cap low-tier (T5 community + T6 review) share.
    total = len(candidates)
    if total == 0:
        return []
    low_tier_kept = 0
    low_tier_max = max(1, int(total * low_tier_cap))
    out: list[tuple[str, SourceType]] = []
    for u, st, tier in candidates:
        if tier in (T5_COMMUNITY, T6_REVIEW):
            if low_tier_kept >= low_tier_max:
                if on_event:
                    on_event({"status": "tier_dropped", "url": u, "tier": tier, "reason": "low-tier cap reached"})
                continue
            low_tier_kept += 1
        out.append((u, st))

    if on_event:
        on_event({
            "status": "tier_summary",
            "tiers": tier_count,
            "low_tier_cap": low_tier_cap,
            "kept": len(out),
            "dropped_for_cap": total - len(out),
        })
    return out


# V7.26 — industry-aware SERP query templates.
#
# Three layers:
#   - Base layer (always runs): filings, mainstream news of record, scholar
#   - Industry layer: queries derived from BusinessProfile.industry that
#     route to industry-specific trade publications + analyst firms
#   - Region layer: queries that add national/EU regulator context
#
# Industry keys are matched as substring tokens against the supplied
# `industry` string — so "wind turbines" / "wind energy" / "windpower"
# all hit the WIND_ENERGY templates.

_INDUSTRY_QUERIES: dict[str, list[tuple[str, SourceType]]] = {
    # Renewable / wind energy
    "wind": [
        ('"{target}" IRENA OR "wind energy"',                        SourceType.NEWS),
        ('"{target}" "Wind Power Monthly" OR "WindEurope"',          SourceType.NEWS),
        ('"wind energy {region}" market report 2024 OR 2025',        SourceType.NEWS),
        ('"EU Green Deal" wind OR renewable 2024 OR 2025',           SourceType.NEWS),
        ('site:iea.org OR site:irena.org "wind" {region}',           SourceType.NEWS),
        ('"{target}" filetype:pdf',                                   SourceType.NEWS),
    ],
    "solar": [
        ('"{target}" IRENA OR "PV Magazine" OR "solar power"',       SourceType.NEWS),
        ('"solar energy {region}" market report 2024 OR 2025',       SourceType.NEWS),
        ('site:iea.org OR site:irena.org "solar" {region}',          SourceType.NEWS),
        ('"{target}" filetype:pdf',                                   SourceType.NEWS),
    ],
    "renewable": [
        ('"{target}" IRENA OR "renewable energy"',                   SourceType.NEWS),
        ('"renewable energy {region}" capacity 2024 OR 2025',        SourceType.NEWS),
        ('"EU Green Deal" {region}',                                  SourceType.NEWS),
        ('"{target}" filetype:pdf',                                   SourceType.NEWS),
    ],
    # SaaS / Backend
    "backend": [
        ('"{target}" Gartner OR Forrester market research',          SourceType.REVIEW),
        ('"{target}" architecture limitations OR scalability',       SourceType.REVIEW),
        ('"backend-as-a-service" market size 2024 OR 2025',          SourceType.NEWS),
        ('"{target}" site:scholar.google.com',                       SourceType.OTHER),
    ],
    "database": [
        ('"{target}" Gartner OR Forrester database research',        SourceType.REVIEW),
        ('"database market" Postgres OR cloud 2024 OR 2025',         SourceType.NEWS),
        ('"{target}" site:scholar.google.com',                       SourceType.OTHER),
    ],
    "saas": [
        ('"{target}" SaaStr OR Forrester OR Gartner',                SourceType.REVIEW),
        ('"SaaS market" {region} 2024 OR 2025',                       SourceType.NEWS),
        ('"{target}" filetype:pdf annual report OR 10-K',            SourceType.NEWS),
    ],
    # Health / biotech
    "biotech": [
        ('"{target}" FierceBiotech OR Endpoints',                    SourceType.NEWS),
        ('"{target}" FDA filing OR EMA submission',                  SourceType.NEWS),
        ('"{target}" site:pubmed.ncbi.nlm.nih.gov OR site:arxiv.org', SourceType.OTHER),
    ],
    "health": [
        ('"{target}" "Endpoints News" OR "STAT News"',               SourceType.NEWS),
        ('"{target}" site:pubmed.ncbi.nlm.nih.gov',                  SourceType.OTHER),
        ('"healthcare market" {region} 2024 OR 2025',                 SourceType.NEWS),
    ],
    # Finance / fintech
    "fintech": [
        ('"{target}" "Financial Times" OR Bloomberg',                SourceType.NEWS),
        ('"{target}" CB Insights OR PitchBook',                      SourceType.NEWS),
        ('"fintech market" {region} 2024 OR 2025',                    SourceType.NEWS),
    ],
    # Manufacturing
    "manufacturing": [
        ('"{target}" "Industry Week" OR Manufacturing.net',          SourceType.NEWS),
        ('"manufacturing market" {region} 2024 OR 2025',              SourceType.NEWS),
        ('"{target}" "supply chain"',                                 SourceType.NEWS),
    ],
    # V7.28 — Pharma / large enterprise
    "pharma": [
        ('"{target}" FDA approval OR clinical trial OR ClinicalTrials.gov', SourceType.NEWS),
        ('"{target}" EMA OR "European Medicines Agency"',            SourceType.NEWS),
        ('"{target}" "Endpoints News" OR "STAT News" OR FiercePharma', SourceType.NEWS),
        ('"{target}" filetype:pdf 10-K OR annual report OR pipeline', SourceType.NEWS),
        ('"{target}" site:pubmed.ncbi.nlm.nih.gov',                   SourceType.OTHER),
        ('"{target}" Bloomberg OR Reuters drug pricing',              SourceType.NEWS),
    ],
    "pharmaceutical": [
        ('"{target}" FDA approval OR clinical trial OR ClinicalTrials.gov', SourceType.NEWS),
        ('"{target}" EMA OR "European Medicines Agency"',            SourceType.NEWS),
        ('"{target}" "Endpoints News" OR "STAT News"',               SourceType.NEWS),
        ('"{target}" filetype:pdf 10-K OR annual report OR pipeline', SourceType.NEWS),
    ],
    # V7.28 — Productivity / knowledge tools (Notion/Asana/Slack-like)
    "productivity": [
        ('"{target}" Gartner Magic Quadrant OR Forrester Wave',      SourceType.REVIEW),
        ('"{target}" G2 OR Capterra OR Trustpilot recent reviews',   SourceType.REVIEW),
        ('"{target}" enterprise plan OR Business plan pricing',      SourceType.PRICING),
        ('"{target}" SOC 2 OR ISO 27001 OR HIPAA compliance',        SourceType.NEWS),
        ('"{target}" Bloomberg OR TechCrunch OR The Information',    SourceType.NEWS),
    ],
    # V7.28 — Developer tools (broader than backend/database)
    "devtools": [
        ('"{target}" Gartner OR Forrester developer tools',          SourceType.REVIEW),
        ('"{target}" HackerNews OR Reddit r/programming',            SourceType.REVIEW),
        ('"{target}" site:github.com stars OR forks',                SourceType.OTHER),
        ('"{target}" "developer survey" OR "Stack Overflow"',        SourceType.OTHER),
    ],
    "developer": [
        ('"{target}" Gartner OR Forrester developer tools',          SourceType.REVIEW),
        ('"{target}" HackerNews OR Reddit',                          SourceType.REVIEW),
        ('"{target}" site:github.com',                                SourceType.OTHER),
    ],
    # V7.28 — E-commerce / retail / D2C
    "ecommerce": [
        ('"{target}" Shopify OR BigCommerce platform',               SourceType.NEWS),
        ('"{target}" GMV OR "gross merchandise value"',              SourceType.NEWS),
        ('"{target}" Trustpilot OR "consumer reviews"',              SourceType.REVIEW),
        ('"retail e-commerce market" {region} 2024 OR 2025',          SourceType.NEWS),
    ],
    "retail": [
        ('"{target}" Retail Dive OR Modern Retail',                  SourceType.NEWS),
        ('"{target}" Trustpilot OR consumer reviews',                SourceType.REVIEW),
        ('"retail market" {region} 2024 OR 2025',                     SourceType.NEWS),
    ],
    "d2c": [
        ('"{target}" Modern Retail OR Retail Brew DTC',              SourceType.NEWS),
        ('"{target}" Trustpilot OR Reddit reviews',                  SourceType.REVIEW),
    ],
    # V7.28 — Media / publishing
    "media": [
        ('"{target}" Press Gazette OR Digiday OR Adweek',            SourceType.NEWS),
        ('"{target}" Bloomberg OR Reuters media',                    SourceType.NEWS),
        ('"media industry" {region} 2024 OR 2025',                    SourceType.NEWS),
    ],
    "publishing": [
        ('"{target}" Press Gazette OR Publishers Weekly',            SourceType.NEWS),
        ('"{target}" Reuters Institute report',                      SourceType.NEWS),
    ],
    # V7.28 — Education / edtech
    "education": [
        ('"{target}" EdSurge OR "Inside Higher Ed"',                 SourceType.NEWS),
        ('"{target}" "Common Sense" OR "EdTechHub"',                 SourceType.NEWS),
        ('"edtech market" {region} 2024 OR 2025',                     SourceType.NEWS),
    ],
    "edtech": [
        ('"{target}" EdSurge OR "EdTechHub"',                        SourceType.NEWS),
        ('"{target}" Holon IQ OR "education investment"',            SourceType.NEWS),
    ],
    # V7.28 — Logistics / supply chain
    "logistics": [
        ('"{target}" Supply Chain Dive OR FreightWaves',             SourceType.NEWS),
        ('"{target}" "supply chain" OR "freight rates"',             SourceType.NEWS),
    ],
    "supply": [
        ('"{target}" Supply Chain Dive OR FreightWaves',             SourceType.NEWS),
        ('"{target}" Gartner supply chain',                          SourceType.NEWS),
    ],
    # V7.28 — Automotive
    "automotive": [
        ('"{target}" "Automotive News" OR Reuters Autos',            SourceType.NEWS),
        ('"{target}" EV OR "electric vehicle" 2024 OR 2025',          SourceType.NEWS),
    ],
    "auto": [
        ('"{target}" "Automotive News" OR Reuters Autos',            SourceType.NEWS),
        ('"{target}" EV OR "electric vehicle"',                       SourceType.NEWS),
    ],
    # V7.28 — Aerospace / defence
    "aerospace": [
        ('"{target}" "Aviation Week" OR Defense News',               SourceType.NEWS),
        ('"{target}" FAA OR EASA certification',                     SourceType.NEWS),
    ],
    "defense": [
        ('"{target}" Defense News OR Breaking Defense',              SourceType.NEWS),
        ('"{target}" DoD OR Pentagon contract',                      SourceType.NEWS),
    ],
    # V7.28 — Insurance / insurtech
    "insurance": [
        ('"{target}" "Insurance Journal" OR Reuters Insurance',      SourceType.NEWS),
        ('"insurtech market" {region} 2024 OR 2025',                  SourceType.NEWS),
    ],
    "insurtech": [
        ('"{target}" "Insurance Journal" OR Coverager',              SourceType.NEWS),
    ],
    # V7.28 — Crypto / blockchain
    "crypto": [
        ('"{target}" CoinDesk OR The Block OR Decrypt',              SourceType.NEWS),
        ('"{target}" SEC OR CFTC enforcement',                       SourceType.NEWS),
    ],
    "blockchain": [
        ('"{target}" CoinDesk OR The Block',                         SourceType.NEWS),
    ],
    # V7.28 — Real estate / proptech
    "real estate": [
        ('"{target}" Bisnow OR The Real Deal',                       SourceType.NEWS),
        ('"real estate market" {region} 2024 OR 2025',                SourceType.NEWS),
    ],
    "proptech": [
        ('"{target}" Bisnow OR PropTech Today',                      SourceType.NEWS),
    ],
    # V7.28 — Legal / lawtech
    "legal": [
        ('"{target}" "Law.com" OR "American Lawyer"',                SourceType.NEWS),
        ('"{target}" "Above the Law" OR LawSites',                   SourceType.NEWS),
    ],
    "law": [
        ('"{target}" "Law.com" OR "American Lawyer"',                SourceType.NEWS),
    ],
    # V7.28 — Consulting / professional services
    "consulting": [
        ('"{target}" Consultancy.eu OR Bloomberg consulting',        SourceType.NEWS),
        ('"{target}" "Big Four" OR partner promotion',               SourceType.NEWS),
    ],
    "agency": [
        ('"{target}" Adweek OR Campaign agency',                     SourceType.NEWS),
        ('"{target}" award OR client win',                            SourceType.NEWS),
    ],
    # V7.28 — Gaming
    "gaming": [
        ('"{target}" GamesIndustry.biz OR PocketGamer',              SourceType.NEWS),
        ('"{target}" Steam OR Twitch concurrent players',            SourceType.NEWS),
    ],
    "games": [
        ('"{target}" GamesIndustry.biz OR PocketGamer',              SourceType.NEWS),
    ],
}

# Region → expanded synonym list. Used as `{region}` placeholder fill.
_REGION_EXPAND = {
    "romania":      "Romania OR EU OR Eastern Europe",
    "ro":           "Romania OR EU OR Eastern Europe",
    "uk":           "United Kingdom OR UK OR Britain",
    "us":           "United States OR US OR USA",
    "germany":      "Germany OR DACH",
    "france":       "France OR EU",
    "eu":           "European Union OR EU",
}


def _industry_template_for(industry: str) -> list[tuple[str, SourceType]]:
    """Substring-match the industry against template keys. Returns first match's
    template list, or empty list if no industry signal."""
    if not industry:
        return []
    s = industry.lower()
    for key, tmpl in _INDUSTRY_QUERIES.items():
        if key in s:
            return tmpl
    return []


def default_external_queries(
    target: str,
    industry: str | None = None,
    region: str | None = None,
) -> list[tuple[str, SourceType]]:
    """Base + industry-aware + region-aware SERP query set (V7.26).

    Base queries always run — they hit filings, news of record, academic.
    Industry queries layer on if `industry` matches a known template
    (substring match — 'wind energy' / 'wind turbines' both hit 'wind').
    Region tokens (Romania / EU / US / etc.) get expanded into synonym
    lists so a Romanian wind-energy firm picks up both 'Romania' AND
    'Eastern Europe' coverage.

    When no industry / region is supplied, falls back to the canonical
    review/competitor/outage/funding template that's domain-agnostic.
    """
    region_token = _REGION_EXPAND.get((region or "").lower().strip(), region or "")

    base: list[tuple[str, SourceType]] = [
        # T1 — primary filing / regulatory
        (f'"{target}" filetype:pdf annual report OR 10-K OR prospectus',  SourceType.NEWS),
        # T3 — newspaper of record
        (f'"{target}" "Financial Times" OR Reuters OR Bloomberg',         SourceType.NEWS),
        # T2 — academic / scholar
        (f'"{target}" site:scholar.google.com OR site:arxiv.org OR study', SourceType.OTHER),
    ]

    industry_layer = _industry_template_for(industry or "")
    # fill {target} + {region} placeholders
    rendered: list[tuple[str, SourceType]] = []
    for q, st in industry_layer:
        rendered.append((
            q.replace("{target}", target).replace("{region}", region_token).strip(),
            st,
        ))

    if not industry_layer:
        # V7.28 — domain-agnostic fallback for arbitrary/unknown industries.
        # Expanded beyond V7.22 to cover the common ways a target leaks
        # information regardless of sector: reviews, hiring, compliance,
        # legal/regulatory surface, M&A, leadership, controversies.
        rendered = [
            # Customer voice — works for any sector with consumer/business
            # facing reviews
            (f'"{target}" Trustpilot OR G2 OR Capterra reviews',  SourceType.REVIEW),
            (f'"{target}" Glassdoor OR Indeed employee reviews',  SourceType.REVIEW),
            (f'"{target}" Reddit OR HackerNews discussion',       SourceType.REVIEW),
            # Competitive surface
            (f'"{target}" vs competitor OR alternative OR comparison', SourceType.REVIEW),
            # Operational / risk
            (f'"{target}" outage OR downtime OR security incident', SourceType.NEWS),
            (f'"{target}" lawsuit OR settlement OR investigation', SourceType.NEWS),
            (f'"{target}" GDPR OR HIPAA OR SOC2 OR compliance',  SourceType.NEWS),
            # Financial / growth
            (f'"{target}" funding OR valuation OR Series OR IPO', SourceType.NEWS),
            (f'"{target}" layoff OR hiring spree OR headcount',   SourceType.NEWS),
            (f'"{target}" acquisition OR merger 2024 OR 2025',    SourceType.NEWS),
            # Leadership / strategy
            (f'"{target}" CEO OR founder interview',              SourceType.NEWS),
            (f'"{target}" earnings call OR investor day',         SourceType.NEWS),
        ]

    return base + rendered


# ─── V7.30 — JS-rendered SPA chrome detection + Wikipedia/Wayback fallback ─
#
# Pfizer.com, Notion.so, and other SPAs return a thin shell to the Web
# Unlocker — navigation links and a "you need to enable JavaScript" stub
# — instead of body content. The shell passes is_low_quality (>150 chars,
# no Cloudflare phrases) but starves every downstream agent because the
# real product/news/about copy never lands in the bundle.
#
# Detection: trim known chrome boilerplate ("skip to main content",
# "toggle navigation", etc.), then mark as chrome if the surviving text
# is < _JS_CHROME_MAX_CHARS OR matches a hard JS-required phrase.
#
# Recovery: per chromed target URL, pull supplementary sources that don't
# need a JS runtime — the en.wikipedia.org entry for the target name and
# a Wayback Machine snapshot of the chromed URL. Both go through the
# existing Web Unlocker zone so spend tracking + retry still apply.
# Tagged SourceType.SITE / OTHER so existing tier-classifier handling
# works unchanged; the host (wikipedia.org / web.archive.org) makes
# provenance obvious in citations.

_JS_CHROME_MAX_CHARS = 1500

# Hard tells — these phrases appearing in the first 600 chars are nearly
# always JS-app shells. Tested against lowercased text.
_JS_CHROME_PATTERNS = (
    "you need to enable javascript to run this app",
    "this site requires javascript",
    "this website requires javascript",
    "javascript is required to view this site",
    "please enable javascript to continue",
    "sorry, this site requires javascript",
    "we're sorry but",  # vue-app default error shell ("we're sorry but X doesn't work properly without JavaScript enabled")
)

# Chrome / boilerplate phrases that pad the text without carrying signal —
# trimmed before the length test so a SPA shell whose REAL content is just
# nav + footer doesn't sneak past the threshold.
_CHROME_BOILERPLATE_RE = re.compile(
    r"(?i)\b("
    r"skip to (?:main )?content|"
    r"toggle navigation|toggle menu|"
    r"open(?: main)? menu|close(?: main)? menu|"
    r"main navigation|primary navigation|"
    r"back to top|jump to (?:main )?content|"
    r"loading\.{0,3}"
    r")\b"
)


def trim_chrome_boilerplate(text: str) -> str:
    """Strip common SPA-shell phrases that pad a JS-rendered response.

    Pure function — used by `looks_like_js_chrome` to get a fair length
    estimate before deciding whether the page is a chrome shell.
    """
    if not isinstance(text, str):
        return ""
    out = _CHROME_BOILERPLATE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", out).strip()


def looks_like_js_chrome(text: str) -> tuple[bool, str]:
    """Return (is_chrome?, reason).

    Designed to run AFTER `is_low_quality` passes — catches the next layer
    of broken-scrape responses where the text is long enough to look real
    but is actually navigation + a 'enable JavaScript' stub.

    Returns (False, "") on real content. Reason string is human-readable
    and surfaced via the on_chrome callback so the dashboard can show
    'falling back to Wikipedia/Wayback for <url>'.
    """
    if not isinstance(text, str):
        return False, ""
    head = text[:600].lower()
    for pat in _JS_CHROME_PATTERNS:
        if pat in head:
            return True, f"js-required phrase: '{pat}'"
    trimmed = trim_chrome_boilerplate(text)
    if len(trimmed) < _JS_CHROME_MAX_CHARS:
        return True, f"only {len(trimmed)} chars after trimming chrome (likely SPA shell)"
    return False, ""


def _wikipedia_url(target: str) -> str:
    """Canonical en.wikipedia URL for a target name. Spaces → underscores;
    non-ASCII percent-encoded. Returns the article URL even if the article
    does not exist — Wikipedia's not-found page is short and gets filtered
    by `is_low_quality` downstream."""
    slug = re.sub(r"\s+", "_", target.strip())
    slug = urllib.parse.quote(slug, safe="_")
    return f"https://en.wikipedia.org/wiki/{slug}"


def _wayback_url(url: str, year: str = "2025") -> str:
    """Wayback Machine wildcard URL. A partial timestamp redirects to the
    closest snapshot in that range — one request, no CDX lookup needed.
    `id_` suffix would strip the Wayback toolbar but breaks the wildcard
    form, so we accept a small amount of toolbar HTML in the scraped text
    (html_to_text discards it cleanly)."""
    return f"https://web.archive.org/web/{year}/{url}"


def fetch_js_chrome_fallbacks(
    target: str,
    chrome_url: str,
    client: BrightDataClient,
    cap_chars: int = 8000,
    on_event=None,
) -> list[SourceItem]:
    """Pull supplementary sources for a JS-blocked target URL.

    Tries en.wikipedia.org/{target} + web.archive.org snapshot of the
    chromed URL. Each attempt that scrapes + clears `is_low_quality` is
    appended to the result list. Failures (404, low-quality, network)
    are skipped silently — callers either get 0, 1, or 2 fallback items.

    `on_event` fires once per attempt with
        {url, status: 'ok'|'low_quality'|'error', reason?: str}
    so the dashboard can show fallback progress in real time.
    """
    out: list[SourceItem] = []
    candidates = [
        ("wikipedia", _wikipedia_url(target)),
        ("wayback",   _wayback_url(chrome_url)),
    ]
    for kind, fb_url in candidates:
        try:
            raw = client.unlock(fb_url)
        except Exception as exc:
            if on_event is not None:
                try:
                    on_event({
                        "url": fb_url, "kind": kind, "status": "error",
                        "reason": f"{type(exc).__name__}: {exc}",
                    })
                except Exception:
                    pass
            continue
        text = html_to_text(raw)[:cap_chars]
        bad, why = is_low_quality(text)
        if bad:
            if on_event is not None:
                try:
                    on_event({
                        "url": fb_url, "kind": kind,
                        "status": "low_quality", "reason": why,
                    })
                except Exception:
                    pass
            continue
        out.append(SourceItem(
            source_type=SourceType.SITE,
            url=fb_url,
            text=text,
        ))
        if on_event is not None:
            try:
                on_event({"url": fb_url, "kind": kind, "status": "ok"})
            except Exception:
                pass
    return out


def build_bundle(
    target: str,
    client: BrightDataClient,
    urls: list[tuple[str, SourceType]] | None = None,
    cap_chars: int = 8000,
    *,
    chrome_fallback: bool = True,
    on_chrome=None,
    expand_subpages: bool = True,
    expand_url: str | None = None,
    on_discover=None,
) -> SharedBundle:
    """Scrape once into a SharedBundle.

    Optional SERP discovery pass (only if a SERP zone is configured), then each
    explicitly-provided URL via Unlocker. Path A demos run with URLs only.

    V7.30 — when `chrome_fallback` is true (default), any user URL whose
    scraped text matches `looks_like_js_chrome` triggers a one-shot
    Wikipedia + Wayback enrichment pass. The fallback fires AT MOST ONCE
    per bundle (target is shared across user URLs) to cap spend. The
    thin original is kept in the bundle alongside the fallbacks — agents
    still see whatever brand copy did land, but now have real content to
    cite.

    V7.31 — when `expand_subpages` is true (default), walk concept groups
    (about / team / pricing / case-studies / careers / news / investors /
    research / blog / certifications / products / references) under
    `expand_url`'s site root and pick up the first synonym per concept
    that scrapes cleanly. `expand_url` should be the target's own URL
    (NOT a SERP-discovered external source like Reddit / news); callers
    in target-mode should pass `user_urls[0][0]`. If `expand_url` is
    None, falls back to `urls[0][0]`. Expansion is skipped automatically
    when the primary URL returned JS chrome — sub-pages on a JS-blocked
    SPA will be chrome too, wasting Unlocker spend.
    """
    sources: list[SourceItem] = []
    if client.serp_zone:
        sources.append(
            SourceItem(
                source_type=SourceType.SERP,
                url=f"serp:{target}",
                text=html_to_text(
                    client.serp(f"{target} pricing careers news")
                )[:cap_chars],
            )
        )
    first_chromed: str | None = None
    for url, stype in urls or []:
        text = html_to_text(client.unlock(url))[:cap_chars]
        sources.append(
            SourceItem(source_type=stype, url=url, text=text)
        )
        if chrome_fallback and first_chromed is None:
            is_chrome, reason = looks_like_js_chrome(text)
            if is_chrome:
                first_chromed = url
                if on_chrome is not None:
                    try:
                        on_chrome({"url": url, "reason": reason})
                    except Exception:
                        pass
    if chrome_fallback and first_chromed is not None:
        sources.extend(fetch_js_chrome_fallbacks(
            target=target,
            chrome_url=first_chromed,
            client=client,
            cap_chars=cap_chars,
            on_event=on_chrome,
        ))
    # V7.31 — auto-discover depth-pages on the target's own domain.
    # Only fires for healthy primary scrapes (chrome shells would yield
    # chrome sub-pages and burn Unlocker credit for no signal).
    if expand_subpages and first_chromed is None:
        base = expand_url or (urls[0][0] if urls else None)
        if base:
            skip = {s.url for s in sources}
            sources.extend(discover_subpages(
                base_url=base,
                client=client,
                subject=SourceSubject.TARGET,
                cap_chars=cap_chars,
                skip_urls=skip,
                on_discover=on_discover,
            ))
    return SharedBundle(target=target, sources=sources)


# V7.12 — concept-grouped sub-page discovery for self-mode. For each
# concept (about / projects / references / products / certifications /
# news) we try a short list of synonym paths in order; the first one that
# scrapes successfully + clears the post-scrape quality gate wins the
# concept. This gets us depth-pages (references / case studies /
# certifications) into the bundle so the Marketing + Strategy depts can
# surface proof-of-execution signals instead of stopping at the homepage.
SUB_PAGE_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("about",
        ("/about", "/about-us", "/company", "/our-story", "/who-we-are")),
    ("projects",
        ("/projects", "/case-studies", "/portfolio", "/our-work",
         "/installations", "/deployments", "/work")),
    ("references",
        ("/references", "/clients", "/customers", "/testimonials",
         "/success-stories")),
    ("products",
        ("/products", "/technology", "/solutions", "/services",
         "/platform")),
    ("certifications",
        ("/certifications", "/compliance", "/quality", "/standards",
         "/iso", "/trust")),
    ("news",
        ("/news", "/press", "/press-releases", "/media", "/blog/news")),
    # V7.31 — additional concepts surfaced primarily for target-mode
    # sub-page discovery. Additive only; self-mode picks them up too
    # since misses are silent and per-concept first-hit-wins caps spend.
    ("team",
        ("/team", "/leadership", "/people", "/about/team", "/management",
         "/our-team")),
    ("careers",
        ("/careers", "/jobs", "/join", "/join-us", "/work-with-us",
         "/careers/all")),
    ("pricing",
        ("/pricing", "/plans", "/pricing-plans", "/buy", "/subscribe")),
    ("investors",
        ("/investors", "/investor-relations", "/ir", "/financials",
         "/annual-report", "/shareholders")),
    ("research",
        # Sector-overlap: /clinical-trials hits pharma, /publications +
        # /papers hits academic-adjacent SaaS, /insights hits analyst-y
        # vendors. Cheap to try; misses are silent.
        ("/research", "/labs", "/insights", "/publications",
         "/clinical-trials", "/papers", "/science", "/r-and-d")),
    ("blog",
        ("/blog", "/articles", "/posts", "/insights/blog",
         "/newsroom/blog")),
]


def discover_subpages(
    base_url: str,
    client: BrightDataClient,
    *,
    subject: SourceSubject = SourceSubject.TARGET,
    cap_chars: int = 8000,
    skip_urls: set[str] | None = None,
    groups: list[tuple[str, tuple[str, ...]]] | None = None,
    on_discover=None,
    competitor_name: str = "",
) -> list[SourceItem]:
    """For each concept in `groups` (default SUB_PAGE_GROUPS), walk
    synonym paths under `base_url`'s site root in order. The first path
    that scrapes successfully + clears `is_low_quality` wins the concept;
    remaining synonyms in that group are skipped.

    Returns a list of newly-discovered SourceItem objects, tagged with
    `subject` (default TARGET so target-mode bundles cite cleanly).
    Misses are silent — 404s on attempted concept paths are routine.

    `skip_urls` lets the caller pass a shared set of URLs already in the
    bundle so a concept whose URL was supplied explicitly by the user
    doesn't re-trigger a scrape. The set is mutated as new URLs land.
    `on_discover` fires once per concept HIT for SSE/log streaming.
    """
    out: list[SourceItem] = []
    root = _site_root(base_url)
    skip = skip_urls if skip_urls is not None else set()
    for concept_name, paths in (groups or SUB_PAGE_GROUPS):
        for path in paths:
            url = root + path
            if url in skip:
                # Same URL already in bundle — concept covered; stop walking.
                break
            try:
                text = html_to_text(client.unlock(url))[:cap_chars]
            except Exception:
                continue
            bad, _ = is_low_quality(text)
            if bad:
                continue
            out.append(SourceItem(
                source_type=SourceType.SITE,
                url=url,
                text=text,
                subject=subject,
                competitor_name=competitor_name,
            ))
            skip.add(url)
            if on_discover is not None:
                try:
                    on_discover({
                        "url": url,
                        "concept": concept_name,
                        "subject": subject.value,
                    })
                except Exception:
                    pass
            break  # concept satisfied — move to next concept
    return out


def _site_root(url: str) -> str:
    """Return https://host (no path/query/fragment) for url."""
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme or "https", p.netloc, "", "", ""))


def _hostname(url: str) -> str:
    try:
        h = urllib.parse.urlparse(url).hostname or url
        # strip leading www. so brands read clean
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return url


def build_self_bundle(
    business_name: str,
    self_urls: list[tuple[str, SourceType]],
    competitor_urls: list[tuple[str, SourceType]],
    client: BrightDataClient,
    cap_chars: int = 8000,
    on_error=None,
    expand_self: bool = True,
    on_discover=None,
) -> tuple[SharedBundle, list[dict]]:
    """Scrape the founder's own URLs (subject=self) + each competitor URL
    (subject=competitor, competitor_name = hostname) into one bundle.

    Resilient: individual URL failures (timeouts, 4xx/5xx, DNS errors) are
    captured and SKIPPED — the cascade continues on whatever sources did
    scrape. Returns (bundle, errors). Each error is a dict
    {url, subject, error}. The on_error callback fires per failed URL so a
    worker can surface them as SSE events in real time.

    V7.12 — when `expand_self` is true (default for self-mode), the
    function additionally tries to discover depth-pages on the founder's
    OWN domain: for each concept group (about / projects / references /
    products / certifications / news) it walks a short list of synonym
    paths and keeps the first one that scrapes + clears the quality
    gate. Sub-page misses are silent (404s are routine) — only sub-page
    HITS are reported via the `on_discover` callback. This is what
    feeds the Marketing + Strategy depts proof-of-execution evidence
    (named references, installed-project portfolios, certifications)
    instead of a homepage-only signal.

    If EVERY URL fails the function raises RuntimeError — at that point
    there's nothing for the depts to read.

    The bundle's target field is the founder's business name; the rest of
    the cascade keys off it for prompts and the dashboard label.
    """
    sources: list[SourceItem] = []
    errors: list[dict] = []

    def _scrape(url: str, stype: SourceType, subject: SourceSubject,
                competitor_name: str = "") -> None:
        try:
            text = html_to_text(client.unlock(url))[:cap_chars]
        except Exception as exc:
            ev = {
                "url": url,
                "subject": subject.value,
                "competitor": competitor_name or None,
                "error": f"{type(exc).__name__}: {exc}",
            }
            errors.append(ev)
            if on_error is not None:
                try:
                    on_error(ev)
                except Exception:
                    pass
            return
        # post-scrape quality gate (V7.7) — drop bot-challenge pages, 404s,
        # access-denied responses, and pages so short they're almost
        # certainly empty/blocked. The LLM downstream has no way to detect
        # this so we catch it here before grounding wastes cycles on it.
        bad, reason = is_low_quality(text)
        if bad:
            ev = {
                "url": url,
                "subject": subject.value,
                "competitor": competitor_name or None,
                "error": f"low-quality response: {reason}",
            }
            errors.append(ev)
            if on_error is not None:
                try:
                    on_error(ev)
                except Exception:
                    pass
            return
        sources.append(
            SourceItem(
                source_type=stype,
                url=url,
                text=text,
                subject=subject,
                competitor_name=competitor_name,
            )
        )

    def _try_silent(url: str, subject: SourceSubject,
                    competitor_name: str = "") -> bool:
        """Like _scrape but silent on failure — used for sub-page discovery
        where 404s on attempted concept paths are routine and shouldn't
        pollute the user-facing error log."""
        if any(s.url == url for s in sources):
            return False  # already scraped
        try:
            text = html_to_text(client.unlock(url))[:cap_chars]
        except Exception:
            return False
        bad, _ = is_low_quality(text)
        if bad:
            return False
        sources.append(
            SourceItem(
                source_type=SourceType.SITE,
                url=url,
                text=text,
                subject=subject,
                competitor_name=competitor_name,
            )
        )
        return True

    def _expand(base_url: str, subject: SourceSubject) -> None:
        """Delegate to the module-level `discover_subpages` helper.

        V7.31 — extracted so target-mode `build_bundle` can reuse the
        same concept-group walk. Local `_try_silent` no longer used by
        sub-page discovery (kept around in case other call sites depend
        on the per-URL silent-scrape primitive).
        """
        skip = {s.url for s in sources}
        sources.extend(discover_subpages(
            base_url=base_url,
            client=client,
            subject=subject,
            cap_chars=cap_chars,
            skip_urls=skip,
            on_discover=on_discover,
        ))

    for url, stype in self_urls or []:
        _scrape(url, stype, SourceSubject.SELF)
    for url, stype in competitor_urls or []:
        _scrape(url, stype, SourceSubject.COMPETITOR, competitor_name=_hostname(url))

    # V7.12 — auto-discover depth-pages on the founder's domain. Only the
    # FIRST self URL is expanded (cap cost; the user explicitly chose
    # the competitor URLs so we don't auto-expand those).
    if expand_self and self_urls:
        _expand(self_urls[0][0], SourceSubject.SELF)

    if not sources:
        msg = "; ".join(f"{e['url']}: {e['error']}" for e in errors) or "no URLs supplied"
        raise RuntimeError(f"every URL failed to scrape — {msg}")

    return SharedBundle(target=business_name, sources=sources), errors
