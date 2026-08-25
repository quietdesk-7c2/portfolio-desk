"""
Moonshot screener — insider cluster buying from SEC Form 4 filings.

WHY THIS EXISTS
The Moonshot book sat 92% in cash because the manager was finding candidates by
reading articles, and articles produce listicles and beaten-down value traps.
This replaces opinion with filings: who actually bought their own company's
stock with their own money, on the open market, recently, together.

WHAT IT LOOKS FOR (IPS 1, the "RVMD test")
A cluster buy: two or more insiders at the same company making OPEN-MARKET
PURCHASES (Form 4 transaction code P) within a 90-day window. Weighted toward
CEO/CFO/director buys and larger dollar amounts. Restricted to smaller companies,
where a cluster is a meaningful signal rather than noise.

WHAT IT DELIBERATELY DOES NOT DO
- It does not treat a filing as an entry trigger. 70-80% of the short-horizon
  return happens before the filing is public. This is CONVICTION CONFIRMATION on
  a one-year thesis, nothing more (IPS 3, tier A).
- It does not rank by raw dollar size. A $10M buy by a founder who already owns
  30% says less than three officers each buying $200k for the first time.
- It does not output positions. It outputs CANDIDATES, which must still clear
  the Moonshot screen's other three legs (analyst upside >35%, a dated catalyst,
  sentiment acceleration) and every sizing rule before anything is bought.

STRUCTURE
Everything that parses or scores is a pure function, tested offline in
tests/test_screener.py. Only fetch_* touches the network. That split exists so
the logic can be verified without hitting SEC servers.

SEC ACCESS RULES (https://www.sec.gov/os/webmaster-faq#developers)
- A User-Agent identifying you with a real contact address is REQUIRED.
- Max 10 requests/second. A shared, lock-protected throttle enforces this in
  aggregate across FETCH_WORKERS concurrent threads, staying a margin under it.
Set SEC_USER_AGENT env var, e.g. "jane doe jane@example.com".
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

SEC_UA = os.environ.get("SEC_USER_AGENT", "portfolio-desk research desk@example.com")
REQUESTS_PER_SECOND = 8          # SEC's published cap is 10/s; stay a margin under it
FETCH_WORKERS = 8                # concurrent filings in flight, all sharing the throttle below
_last_request = [0.0]
_throttle_lock = threading.Lock()

# Officer titles that carry the most signal, highest first.
ROLE_WEIGHT = {
    "ceo": 3.0, "chief executive": 3.0,
    "cfo": 2.5, "chief financial": 2.5,
    "coo": 2.0, "chief operating": 2.0,
    "president": 2.0,
    "chief": 1.8,          # any other C-level
    "director": 1.5,
    "officer": 1.2,
    "10%": 0.8,            # 10% owners buy for many reasons
}


# ==========================================================================
# Network layer -- the ONLY part that touches SEC servers
# ==========================================================================
def _throttle() -> None:
    """Global rate limit shared by every thread, so concurrent fetches never
    exceed REQUESTS_PER_SECOND in aggregate even though SEC calls now overlap."""
    gap = 1.0 / REQUESTS_PER_SECOND
    with _throttle_lock:
        delta = time.time() - _last_request[0]
        if delta < gap:
            time.sleep(gap - delta)
        _last_request[0] = time.time()


def _get(url: str, timeout: int = 30) -> bytes:
    _throttle()
    req = urllib.request.Request(url, headers={
        "User-Agent": SEC_UA,
        "Accept-Encoding": "gzip, deflate",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    if raw[:2] == b"\x1f\x8b":
        import gzip
        raw = gzip.decompress(raw)
    return raw


def fetch_daily_form4_index(day: str) -> list[dict]:
    """
    Every Form 4 filed on a given day (YYYY-MM-DD).

    Uses EDGAR's daily form index, which is a fixed-width text file listing
    every filing by form type. Returns [{cik, company, date, path}].
    """
    d = datetime.strptime(day, "%Y-%m-%d")
    qtr = (d.month - 1) // 3 + 1
    url = (f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{qtr}/"
           f"form.{d.strftime('%Y%m%d')}.idx")
    try:
        text = _get(url).decode("latin-1")
    except Exception:
        return []
    return parse_form_index(text)


def accession_parts(path: str) -> tuple[str, str] | None:
    """
    Split an index path like 'edgar/data/1234567/0001234-26-000123.txt' into
    (cik, accession-without-dashes). Pure, so it is unit tested.
    """
    parts = path.strip().split("/")
    if len(parts) < 4 or parts[0] != "edgar" or parts[1] != "data":
        return None
    cik = parts[2]
    accession = parts[-1].replace(".txt", "").replace("-", "")
    if not cik or not accession:
        return None
    return cik, accession


def extract_xml_names(listing: dict) -> list[str]:
    """
    Pick the ownership XML out of an EDGAR directory listing.

    A Form 4 folder holds several files; the ownership document is XML but so
    is the rendering stylesheet reference. Prefer names that look like a Form 4
    document, then fall back to any .xml. Pure, so it is unit tested.
    """
    names = [i.get("name", "") for i in listing.get("directory", {}).get("item", [])]
    xmls = [n for n in names if n.lower().endswith(".xml")]
    preferred = [n for n in xmls if any(k in n.lower() for k in ("form4", "doc4", "ownership"))]
    return preferred + [n for n in xmls if n not in preferred]


def fetch_filing_xml(path: str) -> str | None:
    """Given an index path, return the Form 4 ownership XML document body."""
    base = "https://www.sec.gov/Archives/"
    parts = accession_parts(path)
    if not parts:
        return None
    cik, accession = parts
    folder = f"{base}edgar/data/{cik}/{accession}"
    try:
        listing = json.loads(_get(f"{folder}/index.json"))
    except Exception:
        # Fall back to the combined submission text file, which embeds the XML.
        try:
            raw = _get(base + path).decode("utf-8", errors="replace")
        except Exception:
            return None
        start = raw.find("<ownershipDocument")
        end = raw.find("</ownershipDocument>")
        return raw[start:end + len("</ownershipDocument>")] if start != -1 and end != -1 else None

    for name in extract_xml_names(listing):
        try:
            body = _get(f"{folder}/{name}").decode("utf-8", errors="replace")
        except Exception:
            continue
        if "<ownershipDocument" in body:
            return body
    return None


# ==========================================================================
# Pure parsing -- fully testable offline
# ==========================================================================
def parse_form_index(text: str) -> list[dict]:
    """
    Parse an EDGAR daily form index into Form 4 rows.

    The file is fixed-width-ish with a header, then lines like:
      4  COMPANY NAME  1234567  2026-08-14  edgar/data/1234567/0001234-26-000123.txt
    """
    out = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("-") or line.lower().startswith("form type"):
            continue
        parts = line.split()
        if not parts or parts[0] != "4":
            continue
        # path is always the last token; cik and date sit just before it
        path = parts[-1]
        date = parts[-2] if len(parts) >= 3 else ""
        cik = parts[-3] if len(parts) >= 4 else ""
        company = " ".join(parts[1:-3]).strip()
        if not path.endswith(".txt"):
            continue
        out.append({"cik": cik, "company": company, "date": date, "path": path})
    return out


def _text(node, *names) -> str:
    """Pull the first matching child's text, tolerating EDGAR's <value> wrappers."""
    for name in names:
        found = node.find(f".//{name}")
        if found is None:
            continue
        val = found.find("value")
        target = val if val is not None else found
        if target.text:
            return target.text.strip()
    return ""


def parse_form4(xml_text: str) -> dict | None:
    """
    Turn one Form 4 XML document into a normalized record.

    Returns {issuer, ticker, cik, insider, roles[], transactions[]} or None if
    the document cannot be parsed. Each transaction is
    {date, code, shares, price, value, acquired}.
    """
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        return None

    issuer = root.find(".//issuer")
    owner = root.find(".//reportingOwner")
    if issuer is None:
        return None

    roles = []
    rel = root.find(".//reportingOwnerRelationship")
    if rel is not None:
        flags = {"isDirector": "director", "isOfficer": "officer",
                 "isTenPercentOwner": "10% owner", "isOther": "other"}
        for tag, label in flags.items():
            node = rel.find(tag)
            if node is not None and (node.text or "").strip() in ("1", "true", "TRUE"):
                roles.append(label)
        title = _text(rel, "officerTitle")
        if title:
            roles.append(title.strip())

    transactions = []
    for tx in root.findall(".//nonDerivativeTransaction"):
        code = _text(tx, "transactionCode")
        if not code:
            continue
        shares = _num(_text(tx, "transactionShares"))
        price = _num(_text(tx, "transactionPricePerShare"))
        acq = _text(tx, "transactionAcquiredDisposedCode")
        transactions.append({
            "date": _text(tx, "transactionDate"),
            "code": code.upper(),
            "shares": shares,
            "price": price,
            "value": round(shares * price, 2) if (shares and price) else 0.0,
            "acquired": acq.upper() == "A",
        })

    return {
        "issuer": _text(issuer, "issuerName"),
        "ticker": _text(issuer, "issuerTradingSymbol").upper(),
        "cik": _text(issuer, "issuerCik"),
        "insider": _text(owner, "rptOwnerName") if owner is not None else "",
        "roles": roles,
        "transactions": transactions,
    }


def _num(s: str) -> float:
    try:
        return float(str(s).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return 0.0


def open_market_purchases(record: dict) -> list[dict]:
    """
    Only transaction code P with acquired=True is an open-market purchase.

    This filter is the whole point. Code A is a grant, code M is an option
    exercise, code S is a sale, code F is shares withheld for tax. Treating a
    grant as a 'buy' is the single most common way insider data gets misread --
    it is compensation, not conviction.
    """
    return [t for t in record.get("transactions", [])
            if t.get("code") == "P" and t.get("acquired") and t.get("value", 0) > 0]


# ==========================================================================
# Clustering and scoring -- pure, testable
# ==========================================================================
def role_weight(roles: list[str]) -> float:
    """Highest-signal role wins; a CEO buying outranks a 10% owner buying."""
    best = 1.0
    joined = " ".join(roles).lower()
    for key, weight in ROLE_WEIGHT.items():
        if key in joined:
            best = max(best, weight)
    return best


def find_clusters(records: list[dict], window_days: int = 90,
                  min_insiders: int = 2) -> list[dict]:
    """
    Group open-market purchases by ticker and keep companies where at least
    `min_insiders` DISTINCT people bought inside the window.

    Distinct people matters: one executive buying three times in a week is one
    person's conviction reported thrice, not a cluster.
    """
    by_ticker: dict[str, list[dict]] = {}
    for rec in records:
        buys = open_market_purchases(rec)
        if not buys or not rec.get("ticker"):
            continue
        by_ticker.setdefault(rec["ticker"], []).append({**rec, "buys": buys})

    clusters = []
    for ticker, entries in by_ticker.items():
        dates = [b["date"] for e in entries for b in e["buys"] if b.get("date")]
        if not dates:
            continue
        newest = max(dates)
        try:
            cutoff = (datetime.strptime(newest, "%Y-%m-%d")
                      - timedelta(days=window_days)).strftime("%Y-%m-%d")
        except ValueError:
            continue

        insiders, total, weighted, buy_list = {}, 0.0, 0.0, []
        for e in entries:
            recent = [b for b in e["buys"] if b.get("date", "") >= cutoff]
            if not recent:
                continue
            spend = sum(b["value"] for b in recent)
            if spend <= 0:
                continue
            name = e.get("insider", "").strip().lower()
            insiders[name] = insiders.get(name, 0.0) + spend
            total += spend
            weighted += spend * role_weight(e.get("roles", []))
            buy_list.append({"insider": e.get("insider"), "roles": e.get("roles", []),
                             "spend": round(spend, 2),
                             "dates": sorted({b["date"] for b in recent})})

        if len(insiders) < min_insiders:
            continue
        clusters.append({
            "ticker": ticker,
            "issuer": entries[0].get("issuer", ""),
            "cik": entries[0].get("cik", ""),
            "n_insiders": len(insiders),
            "total_spend": round(total, 2),
            "weighted_spend": round(weighted, 2),
            "window_days": window_days,
            "latest_buy": newest,
            "buys": sorted(buy_list, key=lambda b: -b["spend"]),
        })
    return sorted(clusters, key=lambda c: -c["weighted_spend"])


def score_cluster(cluster: dict) -> float:
    """
    A single comparable number, so candidates can be ranked.

    Deliberately NOT just dollar size. Breadth (how many separate people) is
    weighted heavily, because independent agreement is the actual signal --
    one person can be wrong loudly; four people being wrong together is rarer.
    Dollars enter logarithmically so a single enormous buy cannot dominate.
    """
    import math
    breadth = min(cluster.get("n_insiders", 0), 6) / 6.0          # 0..1
    dollars = math.log10(max(cluster.get("weighted_spend", 0), 1)) / 7.0  # ~0..1
    return round(min(breadth * 0.6 + min(dollars, 1.0) * 0.4, 1.0), 4)


def apply_ips_filters(clusters: list[dict], max_market_cap: float = 10e9,
                      min_total_spend: float = 100_000,
                      market_caps: dict[str, float] | None = None) -> list[dict]:
    """
    IPS 1 and IPS 8 gates that can be applied without a price feed.

    Market caps are passed in rather than fetched, so this stays pure. A ticker
    with no known cap is KEPT and flagged, never silently dropped -- missing
    data should surface for review, not vanish.
    """
    caps = market_caps or {}
    out = []
    for c in clusters:
        if c.get("total_spend", 0) < min_total_spend:
            continue
        cap = caps.get(c["ticker"])
        c = dict(c)
        c["market_cap"] = cap
        if cap is not None and cap > max_market_cap:
            continue
        c["cap_unknown"] = cap is None
        c["score"] = score_cluster(c)
        out.append(c)
    return sorted(out, key=lambda c: -c["score"])


def _fetch_and_parse(path: str) -> dict | None:
    """One filing's fetch+parse, run on a worker thread. Never raises -- a
    single bad filing must not take down the rest of the pool."""
    try:
        xml = fetch_filing_xml(path)
        return parse_form4(xml) if xml else None
    except Exception:
        return None


# ==========================================================================
# Orchestration
# ==========================================================================
def run(days_back: int = 90, out_path: str | None = None,
        market_caps: dict[str, float] | None = None) -> dict:
    """
    Walk EDGAR's daily indexes, parse every Form 4, find clusters, rank them.

    Writes research/moonshot_candidates.json. Candidates are NOT positions --
    each still needs analyst upside >35%, a dated catalyst, and sentiment
    acceleration before it can be bought.
    """
    today = datetime.now(timezone.utc).date()
    records, days_scanned, filings_seen = [], 0, 0

    for i in range(days_back):
        day = (today - timedelta(days=i))
        if day.weekday() >= 5:
            continue
        rows = fetch_daily_form4_index(day.strftime("%Y-%m-%d"))
        if not rows:
            continue
        days_scanned += 1
        filings_seen += len(rows)
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            futures = [pool.submit(_fetch_and_parse, row["path"]) for row in rows]
            for future in as_completed(futures):
                rec = future.result()
                if rec and open_market_purchases(rec):
                    records.append(rec)

    clusters = find_clusters(records)
    ranked = apply_ips_filters(clusters, market_caps=market_caps)

    result = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "days_back": days_back,
        "days_scanned": days_scanned,
        "filings_seen": filings_seen,
        "purchase_filings": len(records),
        "clusters_found": len(clusters),
        "candidates": ranked[:40],
        "_note": ("Candidates, not positions. Each still needs >35% analyst upside, "
                  "a dated catalyst inside 18 months, and sentiment acceleration "
                  "(IPS 1) plus the valuation gate (IPS 3a) before purchase. "
                  "Insider filings are conviction confirmation on a one-year "
                  "thesis, never an entry trigger (IPS 3)."),
    }
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as fh:
            json.dump(result, fh, indent=2)
    return result


if __name__ == "__main__":
    import sys
    from .config import RESEARCH_DIR
    back = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    res = run(days_back=back,
              out_path=os.path.join(RESEARCH_DIR, "moonshot_candidates.json"))
    print(f"scanned {res['days_scanned']} days, {res['filings_seen']} Form 4s, "
          f"{res['purchase_filings']} with open-market buys, "
          f"{res['clusters_found']} clusters")
    for c in res["candidates"][:15]:
        cap = f"${c['market_cap']/1e9:.1f}B" if c.get("market_cap") else "cap?"
        print(f"  {c['score']:.3f}  {c['ticker']:<6} {c['n_insiders']} insiders  "
              f"${c['total_spend']:>12,.0f}  {cap:<8} {c['issuer'][:38]}")
