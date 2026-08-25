"""
Tests for the browser-side live quote layer.

The live layer recomputes real money numbers -- book value, day change,
unrealized gain, position weights -- in JavaScript, in the browser, outside
anything Python can see. That is exactly the kind of code that quietly drifts
out of agreement with the engine and shows you a number that is wrong in a
believable way.

So this test builds a synthetic book with Python, generates the real
dashboard, pulls applyQuotes() straight out of the generated HTML, and runs it
under node against assertions written from the Python definitions. If the JS
and the engine ever disagree about what "unrealized gain" means, this fails.

Requires node. Skips cleanly if node is absent.
Run: python -m tests.test_live
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Positions priced so every derived figure is checkable by hand.
BOOK = {
    "core":     [("META", 12000, 700.0), ("GOOGL", 9000, 205.0), ("MSFT", 11000, 430.0)],
    "moonshot": [("CBRS", 8000, 31.5)],
    "ai":       [("NVDA", 15000, 178.0), ("MU", 9000, 118.0), ("AVGO", 8000, 340.0)],
}

HARNESS = r"""
const before = JSON.parse(JSON.stringify(DATA));
let ok = true;
const chk=(n,c,d="")=>{if(!c)ok=false;console.log((c?"  PASS  ":"  FAIL  ")+n+(c?"":"   -> "+d));};

const p0 = DATA.portfolios["core"], h0 = p0.holdings[0];

// Quote everything 10% above the static mark; prev close = the static mark.
const px={};
for (const k of DATA.order)
  for (const h of DATA.portfolios[k].holdings)
    if (h.price!=null) px[h.ticker]={c:h.price*1.10, pc:h.price};

console.log("=== full live coverage ===");
chk("reports live", applyQuotes(px)===true);
chk("price took the quote",
    Math.abs(h0.price-before.portfolios.core.holdings[0].price*1.10)<1e-6, String(h0.price));
chk("market value = shares x price", Math.abs(h0.market_value-h0.shares*h0.price)<0.01);
chk("unrealized = value - cost basis",
    Math.abs(h0.unrealized-(h0.market_value-h0.cost_basis))<0.01);
chk("day % is exactly +10%", Math.abs(h0.day_change_pct-0.10)<1e-9, String(h0.day_change_pct));
chk("day $ = shares x (price - prev)",
    Math.abs(h0.day_change-h0.shares*(h0.price-h0.prev_close))<0.01);
const mv=p0.holdings.reduce((s,h)=>s+h.market_value,0);
chk("equity = cash + positions", Math.abs(p0.equity-(p0.cash+mv))<0.01,
    p0.equity+" vs "+(p0.cash+mv));
chk("equity rose on a +10% move", p0.equity>before.portfolios.core.equity);
chk("weights + cash = 100%",
    Math.abs(p0.holdings.reduce((s,h)=>s+h.weight,0)+p0.cash_pct-1)<1e-6);
chk("total return recomputed",
    Math.abs(p0.total_return-(p0.equity-p0.starting_cash)/p0.starting_cash)<1e-9);
// Matches Portfolio.day_change(): delta / (cash + prior value of comparable names)
chk("book day % = day $ / prior equity",
    Math.abs(p0.day_change_pct - p0.day_change/(p0.cash+
      p0.holdings.reduce((s,h)=>s+h.shares*h.prev_close,0)))<1e-9);
chk("grand total = sum of books",
    Math.abs(DATA.total.equity-DATA.order.reduce((s,k)=>s+DATA.portfolios[k].equity,0))<0.01);

console.log("\n=== the live layer must never write ===");
chk("cash is never touched by a quote", p0.cash===before.portfolios.core.cash);
chk("trade log untouched",
    JSON.stringify(p0.trades)===JSON.stringify(before.portfolios.core.trades));
chk("nav history untouched (the chart stays end-of-day)",
    JSON.stringify(p0.nav_history)===JSON.stringify(before.portfolios.core.nav_history));
chk("cost basis untouched", h0.cost_basis===before.portfolios.core.holdings[0].cost_basis);
chk("share count untouched", h0.shares===before.portfolios.core.holdings[0].shares);
chk("not flagged partial when everything quoted", DATA._partial===false);

console.log("\n=== partial coverage: one ticker quotes, the rest fail ===");
Object.assign(DATA, JSON.parse(JSON.stringify(before)));
applyQuotes({"META":{c:900.0, pc:700.0}});
const c2=DATA.portfolios.core;
chk("quoted name updates", c2.holdings.find(h=>h.ticker==="META").price===900.0);
chk("un-quoted names keep their static price, not a blank",
    c2.holdings.filter(h=>h.ticker!=="META").every(h=>
      h.price===before.portfolios.core.holdings.find(x=>x.ticker===h.ticker).price));
chk("partial coverage is flagged so the page can say so", DATA._partial===true);
chk("equity still reconciles on a mixed book",
    Math.abs(c2.equity-(c2.cash+c2.holdings.reduce((s,h)=>s+h.market_value,0)))<0.01);

console.log("\n=== no coverage at all ===");
Object.assign(DATA, JSON.parse(JSON.stringify(before)));
chk("empty quote set reports not-live", applyQuotes({})===false);
chk("nothing moved when nothing quoted",
    Math.abs(DATA.portfolios.core.equity-before.portfolios.core.equity)<0.01);

console.log("\n=== a hostile payload must not corrupt the book ===");
Object.assign(DATA, JSON.parse(JSON.stringify(before)));
applyQuotes({"META":{c:0,pc:0}, "MSFT":{c:null,pc:null}, "ZZZZ":{c:5,pc:4}});
chk("no NaN reaches any displayed figure",
    DATA.order.every(k=>DATA.portfolios[k].holdings.every(h=>
      Number.isFinite(h.market_value)&&Number.isFinite(h.unrealized)&&
      Number.isFinite(h.weight))));
chk("a quote for a ticker we do not own is ignored",
    DATA.portfolios.core.holdings.length===before.portfolios.core.holdings.length);

console.log(ok?"\nALL CHECKS PASSED":"\nFAILURES PRESENT");
process.exit(ok?0:1);
"""


def build_synthetic_dashboard(workdir: str) -> str:
    """Build the real dashboard against a synthetic book, in a scratch copy."""
    for sub in ("engine", "research", "docs", "state", "orders"):
        src = os.path.join(ROOT, sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(workdir, sub), dirs_exist_ok=True)
    # Wipe any inherited state so the book is exactly what we define here.
    state = os.path.join(workdir, "state")
    shutil.rmtree(state, ignore_errors=True)
    os.makedirs(state, exist_ok=True)
    shutil.rmtree(os.path.join(workdir, "state", "history"), ignore_errors=True)

    script = f"""
import os, sys
sys.path.insert(0, {workdir!r})
os.chdir({workdir!r})
os.environ["LIVE_QUOTE_KEY"] = "TESTKEY"
from engine.portfolio import load_all
import engine.report as R
pfs = load_all()
book = {BOOK!r}
for key, rows in book.items():
    pf = pfs[key]
    for t, d, px in rows:
        pf.buy(t, d, px, reason="synthetic test position", tags=["TEST"], source="test")
    for t, d, px in rows:
        pf.set_previous_close(t, round(px * 0.98, 4), "2026-08-22")
    pf.update_high_water(); pf.append_history()
R.build(pfs, {{}})
"""
    subprocess.run([sys.executable, "-c", script], check=True,
                   capture_output=True, cwd=workdir)
    return os.path.join(workdir, "docs", "index.html")


def main() -> int:
    if not shutil.which("node"):
        print("node not available -- skipping the live-quote tests.")
        print("The layer is browser-only, so there is no Python path to test instead.")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        html_path = build_synthetic_dashboard(tmp)
        html = open(html_path).read()

        checks_ok = True

        def note(name, cond, detail=""):
            nonlocal checks_ok
            if not cond:
                checks_ok = False
            print(("  PASS  " if cond else "  FAIL  ") + name +
                  ("" if cond else f"   -> {detail}"))

        print("=== build-time key injection ===")
        note("the key placeholder is replaced, not left in the page",
             "__LIVEKEY__" not in html)
        note("the injected key reaches the page", '"TESTKEY"' in html)

        # And the inverse: with no key set, no live machinery should activate.
        empty = subprocess.run(
            [sys.executable, "-c",
             f"import os,sys;sys.path.insert(0,{tmp!r});os.chdir({tmp!r});"
             "os.environ.pop('LIVE_QUOTE_KEY',None);"
             "import engine.report as R;print(R.LIVE_QUOTE_KEY=='')"],
            capture_output=True, text=True, cwd=tmp)
        note("no key set means no key baked in", "True" in empty.stdout, empty.stderr)

        m_data = re.search(r"const DATA = (\{.*?\});\nconst LIVE_KEY", html, re.S)
        m_fn = re.search(r"(function applyQuotes\(px\)\{.*?\n\})\n\nasync function liveQuotes",
                         html, re.S)
        note("DATA payload is embedded and extractable", m_data is not None)
        note("applyQuotes is present in the page", m_fn is not None)
        if not (m_data and m_fn):
            return 1

        json.loads(m_data.group(1))          # raises if the payload is malformed
        note("embedded payload is valid JSON", True)

        js = os.path.join(tmp, "harness.js")
        with open(js, "w") as fh:
            fh.write(f"const DATA = {m_data.group(1)};\n{m_fn.group(1)}\n{HARNESS}")

        print()
        res = subprocess.run(["node", js], capture_output=True, text=True)
        print(res.stdout.strip())
        if res.stderr.strip():
            print(res.stderr.strip())

        return 0 if (checks_ok and res.returncode == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
