# GeM Source Feasibility Report

Inspection date: **2026-10-17** (requests made from a single workstation, manually paced, ≤ 15 requests in total).
Everything below was observed directly; nothing is inferred from third-party "GeM scraping API" vendors.

## 1. Summary

| Source | URL | Access | Decision |
|---|---|---|---|
| Ongoing Bids/RA – Products | `https://bidplus.gem.gov.in/all-bids` → XHR `POST /all-bids-data` (`byType=product`) | Public page, no login, no CAPTCHA, not disallowed by robots.txt — **but automated clients are blocked by GeM's security gateway** (§3a) | **Adapter implemented and tested on synthetic fixtures; DISABLED** — no permitted automated access today |
| Ongoing Bids/RA – Services | same, `byType=service` | same | same |
| Bid/RA Status, Cancelled Bids | same page, other `bidStatusType` values | Public | Not implemented (out of initial scope; same adapter could support it) |
| View Contracts | `https://gem.gov.in/view_contracts` | **CAPTCHA-protected** (`/view_contracts/encryptCaptcha`) | **Excluded** – CAPTCHAs must not be bypassed |
| CPPP tenders | `https://gem.gov.in/cppp` | Mirrors the Central Public Procurement Portal (a different publisher) | Excluded – not GeM-originated data |
| Forward auctions | `https://forwardauction.gem.gov.in/eprocure/home` | Separate system; `robots.txt` returns 404 | Not assessed in depth; left disabled |
| Bid documents (PDF) | `https://bidplus.gem.gov.in/showbidDocument/{b_id}` | Public PDF (`Content-Type: application/pdf`) | Only **linked**, never downloaded or parsed |
| Official API / open data feed | — | No public bid-listing API or official data feed was found. GeM offers API integration to government buyer systems under MoU; that is not a public channel. | Not available |
| GeM statistics page | `https://gem.gov.in/statistics` | Same security-gateway block page for an honest User-Agent | Excluded |
| data.gov.in (Open Government Data) | `https://api.data.gov.in/lists` | Catalog API answers without a key; **website robots.txt disallows everything**; dataset rows require a free API key | Only 3 GeM datasets, all aggregates — **no bid listings** (§7) |
| Operator CSV/JSON files | local file | — | **Implemented** (`--import-file`, origin `imported`) |
| Synthetic demo data | generated | — | **Implemented** (`scraper.synthetic`, origin `synthetic`) |

## 2. Robots directives (fetched 2026-10-17)

* `https://gem.gov.in/robots.txt` – `User-agent: *` disallows only `/cgi-bin/` and `/resources/`.
* `https://bidplus.gem.gov.in/robots.txt` – disallows `/resources/` and three `/bg_emd/epbgservice/...` paths.
  `/all-bids` and `/all-bids-data` are **not** disallowed.
* `https://mkp.gem.gov.in/robots.txt` – comment only, no rules.

## 3. Technical findings – `all-bids-data`

The public "All Bids" page renders an empty shell and loads its listing via jQuery:

```
POST https://bidplus.gem.gov.in/all-bids-data
Content-Type: application/x-www-form-urlencoded
payload=<JSON>&csrf_bd_gem_nk=<token embedded in the /all-bids page>
```

* **Session/CSRF**: the CSRF token is printed into the public page's JavaScript and is tied to the session
  cookie set when the page is loaded. The collector does exactly what a browser does: GET the page, read the
  token, POST with the same cookie jar. No login, no CAPTCHA, no credential is involved.
* **JavaScript rendering**: not required – the XHR returns JSON (`{status, code, message, response:{response:{numFound,start,docs}}}`),
  so Playwright is not needed. Requests is sufficient; BeautifulSoup is not needed because no HTML is parsed.
* **Payload** (as built by the page's own `defaultLoad()`):
  `{"param":{"searchBid":"","searchType":"fullText"},"filter":{"bidStatusType":"ongoing_bids","byType":"all|product|service|…","highBidValue":"","byEndDate":{"from":"","to":""},"sort":"Bid-Start-Date-Latest|Bid-Start-Date-Oldest|Bid-End-Date-Latest|Bid-End-Date-Oldest"},"page":N}`
* **Pagination**: fixed 10 records per page (`page=2` → `start=10`, verified). On 2026-10-17 there were
  49,513 ongoing bids (37,181 product + 12,332 service – the two filters partition the set exactly).
  A full scan would be ~5,000 requests, so the collector is **incremental** (§5).
* **Response values are Solr multi-valued arrays** (e.g. `"b_bid_number": ["GEM/2026/R/753134"]`), and
  some fields are `null` (e.g. `bd_category_name`).
* **Timezone quirk (important)**: dates look like `2026-10-17T17:17:03Z`, but they are **IST wall-clock
  times mislabelled as UTC**. Evidence: with the list sorted by earliest end date, the first ongoing bid ended
  at `17:17:03Z` when the local time was 17:15 IST (11:45 UTC) – a UTC reading would mean it closed 5½ hours
  earlier yet was still "ongoing". The portal's own JS also formats these with `timeZone: 'UTC'` to show the raw
  wall-clock value. The normalizer therefore discards the `Z` and applies `Asia/Kolkata` explicitly.

### Fields available and mapping

| Dashboard field | Source field | Notes |
|---|---|---|
| Stable identifier | `b_id` (also `id`) | Numeric internal id; used as the dedup key |
| Bid number | `b_bid_number` | e.g. `GEM/2026/B/…` (bid) or `GEM/2026/R/…` (reverse auction) |
| Title/description | `b_category_name[0]` (+ `bbt_title` when present) | Item list; may be long |
| Buyer organisation | `ba_official_details_minName` + `ba_official_details_deptName` | Ministry / department; either may be null |
| Submission deadline | `final_end_date_sort` | IST, see quirk above |
| Bid start | `final_start_date_sort` | Can be in the future for scheduled RAs |
| Category | `b_type` (0 = Product, 1 = Service – confirmed by `byType` filter counts and `b_cat_id` prefix `services_`) | |
| Listing type | `b_bid_type` (1 = Bid, 2 = RA, 5 = Direct RA – from the page's JS) | |
| Quantity | `b_total_quantity` | |
| Original URL | Derived exactly as the page's JS does: `/showbidDocument/{b_id}` (bid), `/showradocumentPdf/{b_id}` or `/list-ra-schedules/{b_id}` (RA), `/showdirectradocumentPdf/{b_id}` (direct RA) on `bidplus.gem.gov.in` | Links to the official PDF/page |
| Estimated value, location, eligibility | **Not present** in the listing feed | Stored as null / not collected |

## 3a. Automated access is blocked (decisive finding)

The inspection requests in §3 were sent with a desktop-browser `User-Agent`, as a person using
a browser would. When the collector identified itself honestly
(`User-Agent: GeMIntelligenceCollector/1.0 (…)`, both via curl and via Python Requests), GeM answered
HTTP 200 with a block page instead of the listing:

> "GeM Information Security: The page is blocked due to Security Issue. Please contact Help Desk."
> (with a support ID)

This is an access control aimed at automated clients. Sending a browser `User-Agent` from a scheduled
bot to get past it would be impersonation to evade that control, so the collector **does not do it**.
The adapter recognises this block page, raises `SourceAccessBlocked`, marks the source `failed` and
stores nothing. Live, end-to-end collection by the scheduled collector has therefore **not** been
verified, and cannot be until GeM grants access.

**Path to enabling the source** (all of these are external actions only you can take):

1. Write to GeM SPV (helpdesk-gem@gov.in / the contact in the block page) describing the dashboard,
   asking for (a) written permission to reproduce bid listing data (§4), and (b) an approved access
   method: an official data feed/API, or allow-listing of the collector's honest User-Agent and
   GitHub Actions egress for one paced daily run.
2. Once granted, set `ENABLED_SOURCES`, `GEM_LIVE_ACCESS_APPROVED=true`,
   `GEM_REPRODUCTION_PERMISSION_CONFIRMED=true` and a
   `COLLECTOR_USER_AGENT` that matches what GeM approved, then run the workflow manually and check
   the run in the admin view.
3. If GeM provides a different (official) feed, add a new adapter in `scraper/sources/` and disable
   this one.

## 4. Terms of use and legal limitations (read before enabling)

From `https://gem.gov.in/websitePolicies` (fetched 2026-10-17):

1. **Copyright Policy** – "Contents of this website may not be reproduced partially or fully without due
   permission in writing in advance from the GeM SPV". Republishing listing data on a public website is
   reproduction. **Written permission from GeM SPV is required before the public dashboard shows GeM data.**
2. **Hyperlinking Policy** – linking directly is allowed without prior permission (GeM asks to be informed);
   framing is **not** permitted; pages must open in a new window. The dashboard opens GeM links in a new tab
   (`target="_blank" rel="noopener noreferrer"`) and never frames GeM pages.
3. **Caution Notice** on the same page states that providing hypertext links to gem.gov.in pages on other
   websites "is strictly prohibited" – this **contradicts** the Hyperlinking Policy. Seek clarification from
   GeM together with the copyright permission.
4. Marks/logos may not be used without consent – the dashboard uses no GeM logo or branding and states that it
   is independent and unofficial.
5. `https://gem.gov.in/terms-of-use` and `/termsCondition` link to buyer/seller transaction terms; no explicit
   clause on automated access was found.

**Live-request gate.** Until `GEM_LIVE_ACCESS_APPROVED=true` the CLI refuses to start a GeM adapter at
all, including `--dry-run`, so no request reaches GeM. If a GeM source is ever blocked during a run,
the other GeM sources in that run are marked "not attempted" instead of hitting the same host again, and
HTTP retries only cover 429/5xx/connection errors (the block page is HTTP 200 and is never retried).

**Consequence:** the GeM adapters are implemented and tested against synthetic fixtures modelled on the
observed response *structure*, but **no source is enabled by default**.
`ENABLED_SOURCES` must be set explicitly (and `GEM_REPRODUCTION_PERMISSION_CONFIRMED=true`) by the operator
after permission is obtained. This is not legal advice; consult counsel and GeM SPV.

## 5. Proposed collection method

* Python `requests`, one session per source, conservative pacing (default 3 s between requests),
  20 s timeout, bounded retries (3, exponential backoff) on 429/5xx/connection errors only.
* Identify honestly via a configurable `User-Agent` containing a contact address (never a browser string).
* **Incremental "new listings" pass**: sort `Bid-Start-Date-Latest`; stop when a whole page is older than the
  watermark (last successful run − 48 h overlap) or after `MAX_PAGES_PER_SOURCE` (default 100 = 1,000 records).
* **Bounded "closing soon" refresh pass**: `byEndDate` = today … today + `REFRESH_WINDOW_DAYS` (default 2),
  sort `Bid-End-Date-Oldest`, capped by `REFRESH_MAX_PAGES` (default 20). This re-observes listings near their
  deadline so deadline extensions are detected.
* Never delete or mark a listing closed because it was not seen in a run.
* Daily at 01:00 UTC via GitHub Actions.

## 6. Open items

* Obtain an approved automated access method from GeM (§3a) — the blocking issue.
* Obtain written permission from GeM SPV for reproduction (and clarify the hyperlink notice).
* The `all-bids-data` endpoint is undocumented: field names, the CSRF mechanism or the timezone quirk may change
  without notice. The adapter validates the response shape and fails the source loudly rather than storing
  malformed data.

## 7. Alternative public sources investigated (2026-10-17)

Each was checked with one or two requests using the honest collector User-Agent.

| Candidate | Result |
|---|---|
| `gem.gov.in/statistics` (aggregate GeM figures) | Blocked by the same security gateway as BidPlus. |
| `data.gov.in` website | `robots.txt` is `User-agent: * / Disallow: /` — the site must not be crawled. |
| `api.data.gov.in` (official OGD API) | `GET /lists?filters[title]=GeM` works without a key and lists **3** GeM datasets: state/UT-wise transactions 2017-18, MSE sellers registered (as on 25-11-2024), year-wise new suppliers. All are static aggregates; none contains bid listings, deadlines or buyers per bid. Reading rows needs a free registered API key (not obtained or tested). |
| CPPP (`eprocure.gov.in/cppp`) | Reachable, but it is a different publisher and its tender lists are CAPTCHA-protected (seen on `gem.gov.in/cppp`). Not usable. |

**Conclusion:** no public, permitted feed of GeM bid listings was found. The application therefore runs
on operator imports (`imported`) and synthetic demo data (`synthetic`) until an approved source exists.
A new source only needs a new adapter in `scraper/sources/` registered in `scraper/sources/__init__.py`;
the database schema and frontend already handle any origin.
