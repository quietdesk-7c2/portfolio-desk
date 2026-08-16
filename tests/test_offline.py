"""
Offline end-to-end test. No network required.

Feeds deterministic prices through the real engine and checks the arithmetic by
hand, then verifies every hard rule in IPS.md actually blocks what it claims to.
Run: python -m tests.test_offline
"""
import json, os, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# redirect state to a temp dir BEFORE importing the engine
TMP = tempfile.mkdtemp(prefix="desk-test-")
import engine.config as cfg
cfg.STATE_DIR = os.path.join(TMP, "state")
cfg.HISTORY_DIR = os.path.join(cfg.STATE_DIR, "history")
cfg.DOCS_DIR = os.path.join(TMP, "docs")
cfg.ORDERS_DIR = os.path.join(TMP, "orders")
cfg.RESEARCH_DIR = os.path.join(TMP, "research")
for d in (cfg.STATE_DIR, cfg.HISTORY_DIR, cfg.DOCS_DIR, cfg.ORDERS_DIR, cfg.RESEARCH_DIR):
    os.makedirs(d, exist_ok=True)

import engine.portfolio as pmod
import engine.rules as rules
import engine.report as report
pmod.STATE_DIR = cfg.STATE_DIR
pmod.HISTORY_DIR = cfg.HISTORY_DIR
report.DOCS_DIR = cfg.DOCS_DIR
report.HISTORY_DIR = cfg.HISTORY_DIR
report.STATE_DIR = cfg.STATE_DIR
report.RESEARCH_DIR = cfg.RESEARCH_DIR
report.BENCH_CACHE = os.path.join(cfg.STATE_DIR, "benchmarks.json")

from engine.portfolio import Portfolio

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + detail) if detail and not cond else ""))

def q(prices):
    return {t: {"ticker": t, "price": p, "asof": "2026-08-14", "source": "test"}
            for t, p in prices.items()}

print("\n=== 1. Buy arithmetic, slippage, cash ===")
pf = Portfolio.load("core")
pf.mark(q({"AAPL": 100.0}))
rec = pf.buy("AAPL", 8000.0, 100.0, reason="test", thesis_id="aapl")
fill = 100.0 * (1 + cfg.SLIPPAGE_BPS/10_000)
check("fill price includes adverse slippage", abs(rec["price"] - fill) < 1e-9,
      f"{rec['price']} vs {fill}")
check("shares = dollars / fill", abs(rec["shares"] - round(8000.0/fill, 4)) < 1e-4)
check("cash reduced by exactly the notional",
      abs(pf.cash - (100_000 - rec["shares"]*fill)) < 0.02, f"cash={pf.cash}")
pf.mark(q({"AAPL": 100.0}))
check("equity ~ unchanged right after a fill (only slippage lost)",
      abs(pf.equity() - 100_000) < 10, f"equity={pf.equity():,.2f}")

print("\n=== 2. Mark to market ===")
pf.mark(q({"AAPL": 150.0}))
mv = pf.position_value("AAPL")
check("position value tracks price", abs(mv - rec["shares"]*150.0) < 0.01)
check("unrealized pnl correct", abs(pf.unrealized_pnl() - (mv - pf.positions["AAPL"]["cost_basis"])) < 0.01)
check("total return positive after a 50% move", pf.total_return() > 0.03,
      f"{pf.total_return():.4f}")

print("\n=== 3. Position-size cap is a HARD rule ===")
pf2 = Portfolio.load("core"); pf2.mark(q({"MSFT": 50.0}))
probs = rules.validate_order(
    {"portfolio":"core","action":"BUY","ticker":"MSFT","dollars":20_000,
     "reason":"too big","thesis_id":"msft"}, pf2, 50.0, {"core": pf2})
check("20% position in Core is blocked (8% cap)", any("cap at cost" in p for p in probs), str(probs))
probs = rules.validate_order(
    {"portfolio":"core","action":"BUY","ticker":"MSFT","dollars":20_000,
     "reason":"too big","thesis_id":"msft","tags":["OVERRIDE"],
     "override_justification":"I really want to"}, pf2, 50.0, {"core": pf2})
check("OVERRIDE cannot bypass the size cap", any("cap at cost" in p for p in probs), str(probs))

print("\n=== 4. Cash floor is a HARD rule ===")
pf3 = Portfolio.load("moonshot"); pf3.mark(q({"XYZ": 10.0}))
probs = rules.validate_order(
    {"portfolio":"moonshot","action":"BUY","ticker":"XYZ","dollars":95_000,
     "reason":"all in","thesis_id":"xyz"}, pf3, 10.0, {"moonshot": pf3})
check("breaching the 10% cash floor is blocked", any("cash floor" in p or "floor" in p for p in probs), str(probs))

print("\n=== 5. Thesis + reason required ===")
probs = rules.validate_order(
    {"portfolio":"core","action":"BUY","ticker":"ABC","dollars":1000,"reason":""},
    pf2, 10.0, {"core": pf2})
check("no reason -> blocked", any("no written reason" in p for p in probs))
check("no thesis_id -> blocked", any("no thesis_id" in p for p in probs))

print("\n=== 6. Stop-loss fires only where the IPS says it should ===")
ms = Portfolio.load("moonshot"); ms.mark(q({"RISK": 100.0}))
ms.buy("RISK", 9000.0, 100.0, reason="t", thesis_id="risk")
ms.mark(q({"RISK": 80.0}))
check("no stop at -20% in Moonshot (limit is -25%)", len(rules.check_stops(ms)) == 0)
ms.mark(q({"RISK": 70.0}))
stops = rules.check_stops(ms)
check("stop fires at -30% in Moonshot", len(stops) == 1, str(stops))
core = Portfolio.load("core"); core.mark(q({"SLOW": 100.0}))
core.buy("SLOW", 5000.0, 100.0, reason="t", thesis_id="slow")
core.mark(q({"SLOW": 40.0}))
check("Core has NO price stop even at -60% (thesis-driven only)", len(rules.check_stops(core)) == 0)

print("\n=== 7. House money rule ===")
hm = Portfolio.load("moonshot"); hm.mark(q({"WIN": 10.0}))
hm.buy("WIN", 5000.0, 10.0, reason="t", thesis_id="win")
initial_cost = hm.positions["WIN"]["initial_cost"]
hm.mark(q({"WIN": 19.0}))
check("no house-money trim at +90%", len(rules.check_house_money(hm)) == 0)
hm.mark(q({"WIN": 20.00}))
check("does NOT fire at exactly 2x the quoted entry (real cost includes slippage)",
      len(rules.check_house_money(hm)) == 0)
hm.mark(q({"WIN": 20.02}))
acts = rules.check_house_money(hm)
check("house money fires once the position is truly +100% on cost",
      len(acts) == 1, str(acts))
if acts:
    a = acts[0]
    cash_before = hm.cash
    hm.sell(a["ticker"], a["shares"], a["price"], reason=a["reason"], tags=["AUTO","HOUSE_MONEY"])
    recovered = hm.cash - cash_before
    check("recovers ~the original dollars invested", abs(recovered - initial_cost) < initial_cost*0.01,
          f"recovered {recovered:.2f} vs cost {initial_cost:.2f}")
    check("still holds shares afterwards", hm.positions["WIN"]["shares"] > 0)
    hm.positions["WIN"]["house_money_taken"] = True
    check("does not re-fire", len(rules.check_house_money(hm)) == 0)

print("\n=== 8. Drawdown circuit breaker ===")
db = Portfolio.load("ai"); db.mark(q({"AI": 100.0}))
db.buy("AI", 90_000.0, 100.0, reason="t", thesis_id="ai")
db.mark(q({"AI": 100.0})); db.update_high_water()
db.mark(q({"AI": 84.0}))
check("book down 14.4% does not trip the 15% warn", rules.check_drawdown(db) is None,
      f"dd={db.drawdown():.4f}")
db.mark(q({"AI": 82.0}))
ev = rules.check_drawdown(db)
check("book down >15% warns but does not halt",
      ev and ev.get("warn") and ev["status"]=="active", f"dd={db.drawdown():.4f} ev={ev}")
db.d["warned_15"] = True
db.mark(q({"AI": 70.0}))
ev = rules.check_drawdown(db)
check("-25% halts new buys", ev and ev["status"]=="halted", str(ev))
db.d["status"] = "halted"
probs = rules.validate_order({"portfolio":"ai","action":"BUY","ticker":"AI","dollars":1000,
                              "reason":"averaging down","thesis_id":"ai"}, db, 71.0, {"ai": db})
check("halted book refuses new buys", any("HALTED" in p for p in probs), str(probs))
db.mark(q({"AI": 60.0}))
ev = rules.check_drawdown(db)
check("-35% escalates to full stop", ev and ev["status"]=="fullstop", str(ev))

print("\n=== 9. Turnover cap ===")
tc = Portfolio.load("core"); tc.mark(q({"T": 10.0}))
for i in range(cfg.MAX_DISCRETIONARY_TRADES_PER_MONTH):
    tc.d["trades"].append({"date": __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).strftime("%Y-%m-%d"),
        "tags": [], "action":"BUY","ticker":"T"})
probs = rules.validate_order({"portfolio":"core","action":"BUY","ticker":"T","dollars":1000,
                              "reason":"one more","thesis_id":"t"}, tc, 10.0, {"core": tc})
check(f"blocked after {cfg.MAX_DISCRETIONARY_TRADES_PER_MONTH} discretionary trades",
      any("turnover cap" in p for p in probs), str(probs))

print("\n=== 9b. Inception exemption is single-use ===")
inc = Portfolio(cfg.PORTFOLIOS["core"], Portfolio._blank(cfg.PORTFOLIOS["core"]))
inc.mark(q({"I": 10.0}))
for i in range(cfg.MAX_DISCRETIONARY_TRADES_PER_MONTH + 4):
    inc.d["trades"].append({"date": __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).strftime("%Y-%m-%d"),
        "tags": ["INCEPTION"], "action":"BUY","ticker":"I"})
probs = rules.validate_order({"portfolio":"core","action":"BUY","ticker":"I","dollars":1000,
                              "reason":"r","thesis_id":"i","tags":["INCEPTION"]},
                             inc, 10.0, {"core": inc})
check("many INCEPTION orders on the SAME day are all allowed (one deployment)",
      not any("already used its one INCEPTION" in p for p in probs), str(probs))
for tr in inc.d["trades"]:
    tr["date"] = "2026-01-02"          # pretend the deployment was months ago
probs = rules.validate_order({"portfolio":"core","action":"BUY","ticker":"I","dollars":1000,
                              "reason":"r","thesis_id":"i","tags":["INCEPTION"]},
                             inc, 10.0, {"core": inc})
check("an INCEPTION deployment beyond the 7-day window is refused",
      any("already used its one INCEPTION" in p for p in probs), str(probs))
import datetime as _dt
recent = Portfolio(cfg.PORTFOLIOS["core"], Portfolio._blank(cfg.PORTFOLIOS["core"]))
recent.mark(q({"I": 10.0}))
_two_days_ago = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=2)).strftime("%Y-%m-%d")
recent.d["trades"].append({"date": _two_days_ago, "tags": ["INCEPTION"],
                           "action": "BUY", "ticker": "I"})
probs = rules.validate_order({"portfolio":"core","action":"BUY","ticker":"I","dollars":1000,
                              "reason":"r","thesis_id":"i","tags":["INCEPTION"]},
                             recent, 10.0, {"core": recent})
check("finishing a deployment 2 days later is still allowed (7-day window)",
      not any("already used its one INCEPTION" in p for p in probs), str(probs))

fresh = Portfolio(cfg.PORTFOLIOS["core"], Portfolio._blank(cfg.PORTFOLIOS["core"]))
fresh.mark(q({"I": 10.0}))
for i in range(cfg.MAX_DISCRETIONARY_TRADES_PER_MONTH + 4):
    fresh.d["trades"].append({"date": __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).strftime("%Y-%m-%d"),
        "tags": ["INCEPTION"], "action":"BUY","ticker":"I"})
probs = rules.validate_order({"portfolio":"core","action":"BUY","ticker":"I","dollars":1000,
                              "reason":"r","thesis_id":"i"}, fresh, 10.0, {"core": fresh})
check("INCEPTION trades do not consume the monthly turnover budget",
      not any("turnover cap" in p for p in probs), str(probs))

print("\n=== 10. Sell accounting & realized P&L ===")
sp = Portfolio.load("moonshot"); sp.mark(q({"S": 10.0}))
sp.buy("S", 10_000.0, 10.0, reason="t", thesis_id="s")
shares = sp.positions["S"]["shares"]; avg = sp.positions["S"]["avg_cost"]
sp.mark(q({"S": 20.0}))
sp.sell("S", shares/2, 20.0, reason="trim")
expected = (shares/2) * (20.0*(1-cfg.SLIPPAGE_BPS/10_000)) - avg*(shares/2)
check("realized P&L on a half-sale is correct",
      abs(sp.positions["S"]["realized"] - expected) < 0.05,
      f"{sp.positions['S']['realized']:.2f} vs {expected:.2f}")
sp.sell("S", sp.positions["S"]["shares"], 20.0, reason="exit")
check("full exit moves the position to closed[]", "S" not in sp.positions and len(sp.d["closed"])==1)

print("\n=== 11. Concentration trim ===")
cc = Portfolio.load("ai"); cc.mark(q({"BIG": 10.0}))
cc.buy("BIG", 12_000.0, 10.0, reason="t", thesis_id="big")
cc.mark(q({"BIG": 25.0}))
acts = rules.check_concentration(cc)
check("winner above the 20% ceiling gets trimmed", len(acts) == 1, str(acts))
if acts:
    cc.sell("BIG", acts[0]["shares"], 25.0, reason="trim", tags=["AUTO","TRIM"])
    cc.mark(q({"BIG": 25.0}))
    w = cc.position_value("BIG")/cc.equity()
    check("trimmed back to ~the 12% soft target", abs(w - 0.12) < 0.005, f"weight={w:.4f}")

print("\n=== 12. Persistence round-trip ===")
sp.save()
again = Portfolio.load("moonshot")
check("state reloads identically", again.d["trades"] == sp.d["trades"] and abs(again.cash - sp.cash) < 1e-6)

print("\n=== 13. Dashboard renders ===")
pf.save(); ms.save(); db.save()
pfs = {k: Portfolio.load(k) for k in cfg.PORTFOLIOS}
for k, x in pfs.items():
    x.mark(q({t: 100.0 for t in x.positions}))
    x.append_history()
report.get_history = lambda *a, **k: []   # no network in tests
out = report.build(pfs, {})
html = open(out).read()
check("html written", os.path.exists(out) and len(html) > 12_000, f"{len(html)} bytes")
check("data injected, placeholder gone", "/*__DATA__*/null" not in html and '"portfolios"' in html)
check("no unresolved template holes", "__DATA__" not in html)
payload = json.loads(open(os.path.join(cfg.DOCS_DIR, "data.json")).read())
check("all three books present", set(payload["portfolios"]) == set(cfg.PORTFOLIOS))
check("totals add up",
      abs(payload["total"]["equity"] - sum(p["equity"] for p in payload["portfolios"].values())) < 0.01)

print("\n=== 14. Automatic rules do not double-fire ===")
idem = Portfolio(cfg.PORTFOLIOS["moonshot"], Portfolio._blank(cfg.PORTFOLIOS["moonshot"]))
idem.mark(q({"D": 100.0}))
idem.buy("D", 9000.0, 100.0, reason="t", thesis_id="d")
idem.mark(q({"D": 70.0}))
first = rules.check_stops(idem)
check("stop fires the first time", len(first) == 1)
idem.sell(first[0]["ticker"], first[0]["shares"], first[0]["price"],
          reason="stop", tags=["AUTO","STOP"])
idem.mark(q({"D": 70.0}))
check("does not fire again after the position is gone", len(rules.check_stops(idem)) == 0)

hist = Portfolio(cfg.PORTFOLIOS["core"], Portfolio._blank(cfg.PORTFOLIOS["core"]))
hist.mark(q({}))
hist.append_history(); hist.append_history(); hist.append_history()
import csv as _csv
_p = os.path.join(cfg.HISTORY_DIR, "core.csv")
_rows = [r for r in open(_p).read().strip().split("\n") if r and not r.startswith("date,")]
check("re-running the same day writes ONE history row, not three",
      len(_rows) == 1, f"{len(_rows)} rows")

print("\n=== 13b. REGRESSION: batch buys must not shrink the equity denominator ===")
# The bug this catches: buy() used to create a position with no mark, so
# equity() counted only cash. Each buy in a batch then made the book look
# smaller, inflating the computed weight of the NEXT order until the position
# cap wrongly rejected it. Deliberately NO mark() call between buys.
batch = Portfolio(cfg.PORTFOLIOS["core"], Portfolio._blank(cfg.PORTFOLIOS["core"]))
batch.mark(q({"A": 100.0, "B": 100.0, "C": 100.0}))
check("equity starts at the full book", abs(batch.equity() - 100_000) < 1)
batch.buy("A", 7900.0, 100.0, reason="t", thesis_id="a")
check("equity is UNCHANGED right after a buy (cash converted to position)",
      abs(batch.equity() - 100_000) < 10, f"equity={batch.equity():,.2f}")
probs = rules.validate_order(
    {"portfolio":"core","action":"BUY","ticker":"B","dollars":7900,
     "reason":"r","thesis_id":"b","tags":["INCEPTION"]}, batch, 100.0, {"core": batch})
check("a legal 7.9% order is NOT rejected after a prior buy in the same batch",
      not any("cap at cost" in p for p in probs), str(probs))
batch.buy("B", 7900.0, 100.0, reason="t", thesis_id="b")
probs = rules.validate_order(
    {"portfolio":"core","action":"BUY","ticker":"C","dollars":7800,
     "reason":"r","thesis_id":"c","tags":["INCEPTION"]}, batch, 100.0, {"core": batch})
check("still not rejected after TWO prior buys", 
      not any("cap at cost" in p for p in probs), str(probs))
batch.buy("C", 7800.0, 100.0, reason="t", thesis_id="c")
check("three buys land, book value intact",
      len(batch.positions) == 3 and abs(batch.equity() - 100_000) < 30,
      f"n={len(batch.positions)} equity={batch.equity():,.2f}")
over = rules.validate_order(
    {"portfolio":"core","action":"BUY","ticker":"D","dollars":9000,
     "reason":"r","thesis_id":"d","tags":["INCEPTION"]}, batch, 100.0, {"core": batch})
check("a genuinely oversized 9% order is STILL rejected (cap still works)",
      any("cap at cost" in p for p in over), str(over))

print("\n=== 14b. Valuation gate (IPS 3a) ===")
import engine.rules as _r
_r.VALUATION_PATH = os.path.join(ROOT, "research", "valuation.json")
vg = Portfolio(cfg.PORTFOLIOS["core"], Portfolio._blank(cfg.PORTFOLIOS["core"]))
vg.mark(q({"GEV": 1063.25, "NVDA": 225.16, "ZZZZ": 50.0, "XLV": 158.0}))
probs = rules.validate_order({"portfolio":"core","action":"BUY","ticker":"GEV","dollars":5000,
                              "reason":"great backlog","thesis_id":"gev"}, vg, 1063.25, {"core": vg})
check("a name whose good news is priced in is BLOCKED",
      any("valuation gate" in p for p in probs), str(probs))
probs = rules.validate_order({"portfolio":"core","action":"BUY","ticker":"NVDA","dollars":5000,
                              "reason":"cheap growth","thesis_id":"nvda"}, vg, 225.16, {"core": vg})
check("a name that passes the gate is allowed",
      not any("valuation gate" in p for p in probs), str(probs))
probs = rules.validate_order({"portfolio":"core","action":"BUY","ticker":"ZZZZ","dollars":5000,
                              "reason":"hunch","thesis_id":"zzzz"}, vg, 50.0, {"core": vg})
check("a ticker with NO valuation record is blocked (missing data is not a pass)",
      any("no valuation record" in p for p in probs), str(probs))
probs = rules.validate_order({"portfolio":"core","action":"BUY","ticker":"XLV","dollars":5000,
                              "reason":"sector exposure","thesis_id":"xlv"}, vg, 158.0, {"core": vg})
check("ETFs are exempt from the gate",
      not any("valuation gate" in p for p in probs), str(probs))
probs = rules.validate_order({"portfolio":"core","action":"BUY","ticker":"GEV","dollars":5000,
                              "reason":"conviction","thesis_id":"gev","tags":["OVERRIDE"],
                              "override_justification":"I see something the multiple does not"},
                             vg, 1063.25, {"core": vg})
check("OVERRIDE can bypass the gate (it is a soft rule, by design)",
      not any("valuation gate" in p for p in probs), str(probs))

print("\n=== 15. Refuses to invent prices ===")
from engine.data import PriceUnavailable
check("PriceUnavailable exists so a missing mark is never silently faked",
      issubclass(PriceUnavailable, Exception))

print("\n" + "="*64)
print(f"  {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for f in FAIL: print("   FAILED: " + f)
print("="*64)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
