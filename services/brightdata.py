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
#   T5 — community / aggregator (capped at ~25% of the bundle)
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
        ".gov", ".mil", ".gov.uk", ".gov.ie", ".gov.au", ".gov.ca",
        ".europa.eu", ".eu", ".gov.eu",
        "oecd.org", "imf.org", "worldbank.org", "iea.org", "irena.org",
        "un.org", "who.int", "iso.org", "nist.gov", "noaa.gov", "ec.europa.eu",
        "ecb.europa.eu", "eea.europa.eu", "epa.gov",
        "sec.gov", "esma.europa.eu", "ec.europa.eu",
        "eur-lex.europa.eu", "europarl.europa.eu",
        "ons.gov.uk", "bls.gov", "fred.stlouisfed.org", "stlouisfed.org",
        "bea.gov", "statistics.gov.uk", "eurostat.ec.europa.eu",
    ),
    T2_ACADEMIC: (
        "scholar.google.com", "nature.com", "science.org", "sciencemag.org",
        "jstor.org", "arxiv.org", "ssrn.com", "pubmed.ncbi.nlm.nih.gov",
        "ncbi.nlm.nih.gov", "biorxiv.org", "medrxiv.org",
        "sciencedirect.com", "springer.com", "wiley.com", "tandfonline.com",
        "cambridge.org", "oup.com", "mit.edu", "stanford.edu", "harvard.edu",
        "ac.uk", "edu.au", ".edu",
        "researchgate.net", "academia.edu",
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
        # domain-agnostic fallback — the old V7.22 template (still useful as
        # a baseline for unknown industries)
        rendered = [
            (f'"{target}" review OR critique',                  SourceType.REVIEW),
            (f'"{target}" vs competitor OR comparison',         SourceType.REVIEW),
            (f'"{target}" outage OR downtime OR incident',      SourceType.NEWS),
            (f'"{target}" funding OR valuation OR Series',      SourceType.NEWS),
        ]

    return base + rendered


def build_bundle(
    target: str,
    client: BrightDataClient,
    urls: list[tuple[str, SourceType]] | None = None,
    cap_chars: int = 8000,
) -> SharedBundle:
    """Scrape once into a SharedBundle.

    Optional SERP discovery pass (only if a SERP zone is configured), then each
    explicitly-provided URL via Unlocker. Path A demos run with URLs only.
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
    for url, stype in urls or []:
        sources.append(
            SourceItem(
                source_type=stype,
                url=url,
                text=html_to_text(client.unlock(url))[:cap_chars],
            )
        )
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
]


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
        """For each concept group try synonym paths in order; first that
        clears the quality gate wins the concept."""
        root = _site_root(base_url)
        for concept_name, paths in SUB_PAGE_GROUPS:
            for path in paths:
                if _try_silent(root + path, subject):
                    if on_discover is not None:
                        try:
                            on_discover({
                                "url": root + path,
                                "concept": concept_name,
                                "subject": subject.value,
                            })
                        except Exception:
                            pass
                    break  # concept satisfied — move to next concept

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
