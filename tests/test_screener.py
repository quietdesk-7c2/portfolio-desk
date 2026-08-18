"""
Offline tests for the Moonshot screener. No network.

Everything that decides which companies become candidates is tested here with
synthetic Form 4 documents. Only the fetch_* functions touch SEC servers, and
those are validated separately by running the screener live.
Run: python -m tests.test_screener
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.screener import (accession_parts, apply_ips_filters, extract_xml_names,
                             find_clusters, open_market_purchases, parse_form4,
                             parse_form_index, role_weight, score_cluster)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   -> {detail}" if detail and not cond else ""))


def form4(ticker, insider, code="P", shares=1000, price=50.0, date="2026-08-10",
          acquired="A", director=False, officer=False, title="", ten_pct=False):
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000123456</issuerCik>
    <issuerName>{ticker} Corp</issuerName>
    <issuerTradingSymbol>{ticker}</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>{insider}</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>{'1' if director else '0'}</isDirector>
      <isOfficer>{'1' if officer else '0'}</isOfficer>
      <isTenPercentOwner>{'1' if ten_pct else '0'}</isTenPercentOwner>
      <officerTitle>{title}</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>{date}</value></transactionDate>
      <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>{acquired}</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


print("\n=== 1. Form 4 parsing ===")
r = parse_form4(form4("ACME", "Smith Jane", officer=True, title="CEO"))
check("parses issuer and ticker", r and r["ticker"] == "ACME" and "ACME" in r["issuer"], str(r))
check("parses insider name", r["insider"] == "Smith Jane", r["insider"])
check("captures officer title", any("CEO" in x for x in r["roles"]), str(r["roles"]))
check("parses shares, price and computed value",
      r["transactions"][0]["shares"] == 1000 and r["transactions"][0]["value"] == 50000.0,
      str(r["transactions"][0]))
check("malformed XML returns None, does not raise", parse_form4("<not xml") is None)
check("empty document returns None", parse_form4("") is None)

print("\n=== 2. THE critical filter: grants are not purchases ===")
buy = parse_form4(form4("ACME", "A", code="P", acquired="A"))
grant = parse_form4(form4("ACME", "A", code="A", acquired="A"))
exercise = parse_form4(form4("ACME", "A", code="M", acquired="A"))
sale = parse_form4(form4("ACME", "A", code="S", acquired="D"))
withheld = parse_form4(form4("ACME", "A", code="F", acquired="D"))
check("code P acquired = open-market PURCHASE", len(open_market_purchases(buy)) == 1)
check("code A (grant) is NOT a purchase", len(open_market_purchases(grant)) == 0)
check("code M (option exercise) is NOT a purchase", len(open_market_purchases(exercise)) == 0)
check("code S (sale) is NOT a purchase", len(open_market_purchases(sale)) == 0)
check("code F (tax withholding) is NOT a purchase", len(open_market_purchases(withheld)) == 0)
check("zero-price P is excluded (no real money moved)",
      len(open_market_purchases(parse_form4(form4("ACME", "A", price=0)))) == 0)

print("\n=== 3. Role weighting ===")
check("CEO outranks director", role_weight(["officer", "CEO"]) > role_weight(["director"]))
check("director outranks 10% owner", role_weight(["director"]) > role_weight(["10% owner"]))
check("unknown role gets the floor, not zero", role_weight([]) == 1.0)
check("title is case-insensitive", role_weight(["Chief Financial Officer"]) >= 2.5)

print("\n=== 4. Clustering ===")
recs = [parse_form4(form4("CLUS", "Person One", officer=True, title="CEO", date="2026-08-10")),
        parse_form4(form4("CLUS", "Person Two", director=True, date="2026-08-12")),
        parse_form4(form4("SOLO", "Only Person", director=True, date="2026-08-11"))]
cl = find_clusters(recs)
tickers = {c["ticker"] for c in cl}
check("two distinct insiders form a cluster", "CLUS" in tickers, str(tickers))
check("a single insider does NOT form a cluster", "SOLO" not in tickers, str(tickers))

same = [parse_form4(form4("SAME", "Repeat Buyer", director=True, date=d))
        for d in ("2026-08-01", "2026-08-05", "2026-08-09")]
check("one person buying three times is NOT a cluster",
      "SAME" not in {c["ticker"] for c in find_clusters(same)},
      "distinct people is the whole point")

wide = [parse_form4(form4("OLD", "P1", director=True, date="2026-01-05")),
        parse_form4(form4("OLD", "P2", director=True, date="2026-08-10"))]
check("buys outside the 90-day window do not cluster together",
      "OLD" not in {c["ticker"] for c in find_clusters(wide, window_days=90)})
check("the same buys DO cluster with a wide enough window",
      "OLD" in {c["ticker"] for c in find_clusters(wide, window_days=400)})

print("\n=== 5. Scoring ===")
broad = {"n_insiders": 5, "weighted_spend": 500_000}
narrow = {"n_insiders": 2, "weighted_spend": 500_000}
big_narrow = {"n_insiders": 2, "weighted_spend": 50_000_000}
check("more insiders scores higher at equal dollars",
      score_cluster(broad) > score_cluster(narrow))
check("breadth beats a single huge cheque",
      score_cluster(broad) > score_cluster(big_narrow),
      f"broad={score_cluster(broad)} big_narrow={score_cluster(big_narrow)}")
check("score stays within 0..1",
      0 <= score_cluster({"n_insiders": 99, "weighted_spend": 1e12}) <= 1.0)

print("\n=== 6. IPS filters ===")
cand = [{"ticker": "SMALL", "n_insiders": 3, "total_spend": 500_000, "weighted_spend": 900_000},
        {"ticker": "MEGA", "n_insiders": 3, "total_spend": 500_000, "weighted_spend": 900_000},
        {"ticker": "TINY", "n_insiders": 2, "total_spend": 5_000, "weighted_spend": 6_000},
        {"ticker": "NOCAP", "n_insiders": 2, "total_spend": 400_000, "weighted_spend": 500_000}]
caps = {"SMALL": 3e9, "MEGA": 900e9}
out = apply_ips_filters(cand, market_caps=caps)
keys = {c["ticker"] for c in out}
check("small cap kept", "SMALL" in keys, str(keys))
check("mega cap dropped (cluster is noise at that size)", "MEGA" not in keys, str(keys))
check("trivial spend dropped", "TINY" not in keys, str(keys))
check("unknown market cap is KEPT and flagged, not silently dropped",
      "NOCAP" in keys and next(c for c in out if c["ticker"] == "NOCAP")["cap_unknown"])
check("output is ranked by score",
      all(out[i]["score"] >= out[i+1]["score"] for i in range(len(out)-1)))

print("\n=== 7. Daily index parsing ===")
idx = """Description:           Daily Index of EDGAR Dissemination Feed
Form Type   Company Name                     CIK        Date Filed  File Name
----------------------------------------------------------------------------
4           ACME CORP                        1234567    2026-08-14  edgar/data/1234567/0001-26-1.txt
4           BETA INDUSTRIES INC              7654321    2026-08-14  edgar/data/7654321/0002-26-2.txt
8-K         GAMMA CO                         1111111    2026-08-14  edgar/data/1111111/0003-26-3.txt
10-Q        DELTA LLC                        2222222    2026-08-14  edgar/data/2222222/0004-26-4.txt
"""
rows = parse_form_index(idx)
check("extracts only Form 4 rows", len(rows) == 2, f"{len(rows)} rows")
check("captures the filing path", rows[0]["path"].endswith(".txt"), str(rows[0]))
check("captures multi-word company names",
      "BETA" in rows[1]["company"], str(rows[1]))
check("ignores 8-K and 10-Q", all(r["path"].endswith(".txt") for r in rows))
check("empty index returns empty list", parse_form_index("") == [])

print("\n=== 8. URL construction (the part I cannot test live) ===")
# A real EDGAR accession is 18 digits: 0001234567-26-000123
_p = "edgar/data/1234567/0001234567-26-000123.txt"
check("splits a real-format index path",
      accession_parts(_p) == ("1234567", "000123456726000123"),
      str(accession_parts(_p)))
check("accession has no dashes and keeps every digit",
      len(accession_parts(_p)[1]) == 18, accession_parts(_p)[1])
check("rejects a malformed path", accession_parts("not/a/path") is None)
check("rejects an empty path", accession_parts("") is None)
listing = {"directory": {"item": [{"name": "xslF345X03/doc4.xml"}, {"name": "doc4.xml"},
                                  {"name": "0001.txt"}, {"name": "primary_doc.xml"}]}}
names = extract_xml_names(listing)
check("prefers the ownership document over other xml",
      names[0].endswith("doc4.xml"), str(names))
check("still returns other xml as fallback", "primary_doc.xml" in names, str(names))
check("no xml in listing returns empty",
      extract_xml_names({"directory": {"item": [{"name": "a.txt"}]}}) == [])

print("\n" + "=" * 64)
print(f"  {len(PASS)} passed, {len(FAIL)} failed")
for f in FAIL:
    print("   FAILED: " + f)
print("=" * 64)
sys.exit(1 if FAIL else 0)
