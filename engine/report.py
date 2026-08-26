"""
Dashboard builder.

Produces a single self-contained docs/index.html with the data embedded, so it
works from GitHub Pages, from a file:// URL, or off your phone with no server.

Chart design follows a validated categorical palette (blue / orange / aqua),
one y-axis per chart, benchmarks indexed to the same base as the portfolio so
they share a scale, and a holdings table so nothing depends on color alone.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .config import DOCS_DIR, HISTORY_DIR, PORTFOLIOS, RESEARCH_DIR, STATE_DIR
from .data import get_history

BENCH_CACHE = os.path.join(STATE_DIR, "benchmarks.json")

# Optional browser-side live quotes.
#
# If LIVE_QUOTE_KEY is set at build time, it is written into the page so the
# browser can re-quote every holding on load. That is a deliberate, visible
# publication of the key -- it is passed as a repo *variable*, never a secret,
# so nobody is fooled into thinking it is protected. Use a free Finnhub key
# and nothing else: it is read-only, rate-limited, and carries no account.
#
# Left unset, the page is a plain static file marked at the last build. Every
# number still renders; it is just as fresh as the last workflow run.
LIVE_QUOTE_KEY = os.environ.get("LIVE_QUOTE_KEY", "").strip()


def _read_nav_history(key: str) -> list[dict]:
    path = os.path.join(HISTORY_DIR, f"{key}.csv")
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as fh:
        lines = [l.strip() for l in fh if l.strip()]
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            out.append({"date": parts[0], "equity": float(parts[1])})
        except ValueError:
            continue
    return sorted(out, key=lambda r: r["date"])


def _benchmark_series(tickers: list[str], since: str) -> dict[str, dict[str, float]]:
    """Fetch and cache benchmark closes so we don't re-pull every run."""
    cache = {}
    if os.path.exists(BENCH_CACHE):
        try:
            with open(BENCH_CACHE) as fh:
                cache = json.load(fh)
        except Exception:
            cache = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for t in tickers:
        entry = cache.get(t)
        if entry and entry.get("updated") == today:
            continue
        series = get_history(t, days=800)
        if series:
            cache[t] = {"updated": today,
                        "closes": {d: p for d, p in series if d >= since}}
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(BENCH_CACHE, "w") as fh:
            json.dump(cache, fh)
    except Exception:
        pass
    return {t: cache.get(t, {}).get("closes", {}) for t in tickers}


def _load_watchlist() -> dict:
    """research/watchlist.json becomes the Radar tab."""
    try:
        with open(os.path.join(RESEARCH_DIR, "watchlist.json")) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _load_moonshot_candidates() -> dict:
    """research/moonshot_candidates.json (engine/screener.py) becomes the
    Candidates tab. Sourcing only -- these still need analyst upside, a dated
    catalyst and sentiment acceleration before anything is bought (IPS 1)."""
    try:
        with open(os.path.join(RESEARCH_DIR, "moonshot_candidates.json")) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _load_theses() -> dict:
    """research/<thesis_id>.md files become the 'why do we own this' panel."""
    out = {}
    if not os.path.isdir(RESEARCH_DIR):
        return out
    for fn in sorted(os.listdir(RESEARCH_DIR)):
        if not fn.endswith(".md"):
            continue
        try:
            with open(os.path.join(RESEARCH_DIR, fn)) as fh:
                out[fn[:-3].lower()] = fh.read()
        except Exception:
            continue
    return out


def _total_day_pct(snaps: dict) -> float | None:
    """Day % across all three books, weighted by yesterday's equity."""
    delta = sum(s.get("day_change") or 0 for s in snaps.values())
    prior = 0.0
    seen = False
    for s in snaps.values():
        if s.get("day_change") is None:
            continue
        prior += (s["equity"] - (s.get("day_change") or 0))
        seen = True
    return round(delta / prior, 5) if (seen and prior) else None


def build(portfolios: dict, quotes: dict) -> str:
    snaps, bench_needed = {}, set()
    for key, pf in portfolios.items():
        s = pf.snapshot()
        s["nav_history"] = _read_nav_history(key)
        snaps[key] = s
        bench_needed.add(s["benchmark"])
        bench_needed.add(s["benchmark_secondary"])

    inception = min(s["inception"] for s in snaps.values())
    benches = _benchmark_series(sorted(bench_needed), inception)

    total_equity = sum(s["equity"] for s in snaps.values())
    total_start = sum(s["starting_cash"] for s in snaps.values())

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inception": inception,
        "total": {
            "equity": round(total_equity, 2),
            "starting": round(total_start, 2),
            "return": round((total_equity - total_start) / total_start, 4) if total_start else 0,
            "cash": round(sum(s["cash"] for s in snaps.values()), 2),
            "positions": sum(s["n_holdings"] for s in snaps.values()),
            "day_change": round(sum(s.get("day_change") or 0 for s in snaps.values()), 2),
            "day_change_pct": _total_day_pct(snaps),
        },
        "portfolios": snaps,
        "benchmarks": benches,
        "theses": _load_theses(),
        "watchlist": _load_watchlist(),
        "moonshot_candidates": _load_moonshot_candidates(),
        "order": ["core", "moonshot", "ai"],
    }

    os.makedirs(DOCS_DIR, exist_ok=True)
    data_json = json.dumps(payload, separators=(",", ":"))
    html = (TEMPLATE
            .replace("/*__DATA__*/null", data_json)
            .replace('"__LIVEKEY__"', json.dumps(LIVE_QUOTE_KEY)))
    out_path = os.path.join(DOCS_DIR, "index.html")
    with open(out_path, "w") as fh:
        fh.write(html)
    with open(os.path.join(DOCS_DIR, "data.json"), "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"  dashboard -> {out_path}")
    return out_path


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#0a0a0b">
<title>Portfolio Desk</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{
  color-scheme: dark;
  --bg:#0a0a0b; --surface-1:#141416; --surface-2:#1c1c1f; --surface-3:#26262a;
  --border:#2a2a2e; --border-2:#3a3a40; --grid:#1f1f23;
  --ink:#f2f2f4; --ink-2:#a8a8b3; --ink-3:#6e6e7a;
  --good:#22c55e; --bad:#ef4444; --warn:#fab219;
  --s-core:#3987e5; --s-moon:#d95926; --s-ai:#199e70; --s-bench:#7a7a85;
  --r:12px;
}
:root[data-theme="light"]{
  color-scheme: light;
  --bg:#f6f6f4; --surface-1:#ffffff; --surface-2:#f0f0ee; --surface-3:#e6e6e3;
  --border:#e2e2de; --border-2:#cfcfc9; --grid:#eaeae7;
  --ink:#0b0b0b; --ink-2:#55555c; --ink-3:#8a8a92;
  --good:#0ca30c; --bad:#d03b3b;
  --s-core:#2a78d6; --s-moon:#eb6834; --s-ai:#1baf7a; --s-bench:#83827c;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.5 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  padding-bottom:env(safe-area-inset-bottom);-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:14px 13px 60px}
.m{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}
.pos{color:var(--good)} .neg{color:var(--bad)} .dim{color:var(--ink-3)}
.lbl{font-size:9.5px;letter-spacing:.10em;text-transform:uppercase;color:var(--ink-3);font-weight:600}

header{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}
.brand{display:flex;align-items:center;gap:9px}
/* The header dot is a status light, not decoration. Grey by default: the page
   is static and honest about it. It only goes green, and only pulses, when
   live quotes actually came back. A light that is always green tells you
   nothing. */
.dotpulse{width:7px;height:7px;border-radius:50%;background:var(--ink-3);
  box-shadow:0 0 0 3px rgba(120,120,130,.12);transition:background .3s,box-shadow .3s}
.dotpulse.live{background:var(--good);box-shadow:0 0 0 3px rgba(34,197,94,.16);
  animation:pulse 2.4s ease-in-out infinite}
.dotpulse.partial{background:var(--warn);box-shadow:0 0 0 3px rgba(217,119,6,.16)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}
@media (prefers-reduced-motion:reduce){.dotpulse.live{animation:none}}
h1{font-size:14px;margin:0;letter-spacing:.02em;font-weight:650}
.stamp{font-size:10.5px;color:var(--ink-3);margin-top:1px}
.stamp.live{color:var(--good)}
.tbtn{background:var(--surface-2);border:1px solid var(--border);color:var(--ink-2);
  border-radius:8px;padding:6px 10px;font-size:11px;cursor:pointer;font-weight:600}

/* hero */
.hero{background:linear-gradient(180deg,var(--surface-1),var(--bg));
  border:1px solid var(--border);border-radius:var(--r);padding:18px;margin-bottom:12px}
.hero .big{font-size:clamp(30px,8vw,44px);font-weight:680;letter-spacing:-0.025em;line-height:1}
.deltas{display:flex;gap:16px;flex-wrap:wrap;margin-top:9px;align-items:baseline}
.delta{font-size:14px;font-weight:600}
.delta .lbl{display:block;margin-bottom:2px}
.strip{display:flex;gap:0;flex-wrap:wrap;margin-top:15px;padding-top:13px;
  border-top:1px solid var(--border)}
.strip>div{flex:1;min-width:88px;padding-right:12px}
.strip b{display:block;font-size:14px;font-weight:600;margin-top:3px}

/* tabs */
.tabs{display:flex;gap:4px;background:var(--surface-2);padding:3px;border-radius:10px;
  margin-bottom:12px;overflow-x:auto}
.tab{flex:1;min-width:82px;border:0;background:transparent;color:var(--ink-3);
  padding:9px 8px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;
  display:flex;align-items:center;justify-content:center;gap:6px;white-space:nowrap}
.tab .dot{width:6px;height:6px;border-radius:50%;flex:none}
.tab[aria-selected="true"]{background:var(--surface-3);color:var(--ink)}

.card{background:var(--surface-1);border:1px solid var(--border);border-radius:var(--r);
  padding:15px;margin-bottom:12px}
.card h2{font-size:12px;margin:0;font-weight:650;letter-spacing:.03em;text-transform:uppercase}
.note{font-size:11.5px;color:var(--ink-3);margin:5px 0 13px;line-height:1.5}

/* tiles */
.tiles{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:12px}
@media(min-width:700px){.tiles{grid-template-columns:repeat(4,1fr)}}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:11px;padding:11px 12px}
.tile .v{font-size:19px;font-weight:650;margin-top:4px;letter-spacing:-0.015em}
.tile .s{font-size:10.5px;color:var(--ink-3);margin-top:2px}

/* chart */
.chead{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.ranges{display:flex;gap:3px;background:var(--surface-2);padding:2px;border-radius:7px}
.rbtn{border:0;background:transparent;color:var(--ink-3);font-size:10.5px;font-weight:600;
  padding:5px 9px;border-radius:5px;cursor:pointer;font-family:inherit}
.rbtn[aria-pressed="true"]{background:var(--surface-3);color:var(--ink)}
.chartbox{position:relative;height:250px;margin-top:12px}
@media(min-width:700px){.chartbox{height:320px}}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--ink-2);margin-top:10px}
.legend i{display:inline-block;width:13px;height:2.5px;border-radius:2px;margin-right:6px;vertical-align:3px}
.legend i.dash{background:repeating-linear-gradient(90deg,var(--s-bench) 0 4px,transparent 4px 8px)}

/* allocation */
.alloc{display:flex;flex-direction:column;gap:6px}
.arow{display:grid;grid-template-columns:52px 1fr 52px;align-items:center;gap:8px;font-size:11.5px}
.abar{height:13px;background:var(--surface-2);border-radius:3px;overflow:hidden}
.abar span{display:block;height:100%;border-radius:3px}

/* holdings */
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 -15px;padding:0 15px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:right;font-weight:600;color:var(--ink-3);font-size:9.5px;letter-spacing:.07em;
  text-transform:uppercase;padding:0 0 9px 10px;border-bottom:1px solid var(--border);white-space:nowrap}
th:first-child,td:first-child{text-align:left;padding-left:0}
td{padding:10px 0 10px 10px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover td{background:var(--surface-2)}
.tk{display:flex;align-items:center;gap:8px;font-weight:650}
.tk .sw{width:3px;height:16px;border-radius:2px;flex:none}
.pill{display:inline-block;font-size:8.5px;padding:2px 5px;border-radius:4px;margin-left:6px;
  font-weight:700;letter-spacing:.05em;vertical-align:1px;background:var(--surface-3);color:var(--ink-2)}
.pill.hm{background:rgba(34,197,94,.16);color:var(--good)}
.pill.ov{background:rgba(250,178,25,.16);color:var(--warn)}
.pcards{display:none;flex-direction:column;gap:8px}
.pcard{background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:11px 12px}
.pc1{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.pc1 .tk{font-size:13.5px}
.pc1 .px{font-size:13.5px;font-weight:650}
.pc2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
.pcell{background:var(--surface-1);border-radius:7px;padding:7px 9px}
.pcell .v{display:block;font-size:12.5px;font-weight:650;margin-top:2px}
.pc3{display:flex;gap:14px;margin-top:9px;font-size:10.5px;color:var(--ink-3)}
.pc3 b{color:var(--ink-2);font-weight:600}
@media(max-width:700px){
  th.opt,td.opt{display:none}
  .tw{display:none}
  .pcards{display:flex}
}

/* trades */
.trade{display:flex;gap:10px;padding:11px 0;border-bottom:1px solid var(--grid);font-size:12px}
.trade:last-child{border-bottom:0}
.side{font-size:9px;font-weight:800;padding:3px 6px;border-radius:4px;height:fit-content;
  flex:none;letter-spacing:.06em;min-width:38px;text-align:center}
.side.BUY{background:rgba(34,197,94,.14);color:var(--good)}
.side.SELL{background:rgba(239,68,68,.14);color:var(--bad)}
.tb{flex:1;min-width:0}
.th2{display:flex;justify-content:space-between;gap:10px;margin-bottom:3px;font-weight:650}
.rsn{color:var(--ink-2);font-size:11.5px;line-height:1.5}
.meta{color:var(--ink-3);font-size:10.5px;margin-top:4px}

.banner{border-radius:10px;padding:11px 13px;font-size:12px;margin-bottom:12px;line-height:1.5}
.banner.halt{background:rgba(239,68,68,.10);border:1px solid rgba(239,68,68,.32)}
.banner.warn{background:rgba(250,178,25,.10);border:1px solid rgba(250,178,25,.32)}
.empty{color:var(--ink-3);font-size:12px;padding:22px 0;text-align:center;line-height:1.7}
details{margin-top:9px}
summary{cursor:pointer;font-size:11.5px;color:var(--ink-2);padding:7px 0;font-weight:600}
.thesis{font-size:11.5px;color:var(--ink-2);line-height:1.7;white-space:pre-wrap;
  background:var(--surface-2);border-radius:9px;padding:13px;margin-top:7px;
  max-height:340px;overflow:auto;font-family:ui-monospace,Menlo,monospace}

/* radar */
.rhead{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap}
.rhead h2{flex:1 1 60%;min-width:0}
.spill{font-size:8.5px;font-weight:700;letter-spacing:.05em;padding:3px 7px;border-radius:5px;
  max-width:100%;white-space:normal;line-height:1.4;background:var(--surface-3);color:var(--ink-2)}
.spill.bought{background:rgba(34,197,94,.16);color:var(--good)}
.spill.rej{background:rgba(239,68,68,.13);color:var(--bad)}
.rgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:7px;margin-top:11px}
@media(min-width:700px){.rgrid{grid-template-columns:repeat(4,1fr)}}
.rm{background:var(--surface-2);border-radius:8px;padding:8px 10px}
.rm .v{display:block;font-size:11.5px;font-weight:650;margin-top:3px;line-height:1.35}
.rsec{margin-top:12px}
.rtext{font-size:11.5px;color:var(--ink-2);line-height:1.6}
.veh{font-size:11.5px;color:var(--ink-2);line-height:1.55;padding:7px 0;border-bottom:1px solid var(--grid)}
.veh:last-child{border-bottom:0}
.veh b{color:var(--ink);font-family:ui-monospace,Menlo,monospace}
.rlist{margin:0;padding-left:17px;font-size:11.5px;color:var(--ink-2);line-height:1.8}
footer{text-align:center;color:var(--ink-3);font-size:10.5px;margin-top:26px;line-height:1.8}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <span class="dotpulse"></span>
      <div><h1>PORTFOLIO DESK</h1><div class="stamp" id="gen"></div></div>
    </div>
    <button class="tbtn" id="tbtn" type="button">◐</button>
  </header>

  <div class="hero">
    <div class="lbl">Total · three books</div>
    <div class="big m" id="tv">—</div>
    <div class="deltas">
      <div class="delta"><span class="lbl">Today</span><span class="m" id="td">—</span></div>
      <div class="delta"><span class="lbl">Total</span><span class="m" id="tt">—</span></div>
    </div>
    <div class="strip">
      <div><span class="lbl">Deployed</span><b class="m" id="sdep">—</b></div>
      <div><span class="lbl">Cash</span><b class="m" id="scash">—</b></div>
      <div><span class="lbl">Positions</span><b class="m" id="spos">—</b></div>
      <div><span class="lbl">Since</span><b class="m" id="sinc">—</b></div>
    </div>
  </div>

  <div class="tabs" id="tabs" role="tablist"></div>
  <div id="panel"></div>

  <footer>
    Paper money · managed under <code>IPS.md</code> · every trade is a git commit<br>
    Not investment advice.
  </footer>
</div>

<script>
const DATA = /*__DATA__*/null;
const LIVE_KEY = "__LIVEKEY__";
function initialTab(){
  const h=(location.hash||"").slice(1);
  const valid=h&&(h==="radar"||h==="candidates"||(DATA&&DATA.order&&DATA.order.includes(h)));
  return valid?h:((DATA&&DATA.order&&DATA.order[0])||"core");
}
let chart=null, active=initialTab(), range="ALL";
const SV={core:"--s-core",moonshot:"--s-moon",ai:"--s-ai"};
const cv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const money=v=>(v<0?"-":"")+"$"+Math.abs(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
const m0=v=>(v<0?"-":"")+"$"+Math.abs(v).toLocaleString("en-US",{maximumFractionDigits:0});
const sgn=v=>(v>=0?"+":"")+money(v);
const sgn0=v=>(v>=0?"+":"")+m0(v);
const pct=v=>(v>=0?"+":"")+(v*100).toFixed(2)+"%";
const cls=v=>v>=0?"pos":"neg";
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const dash='<span class="dim">—</span>';

function head(){
  const t=DATA.total;
  document.getElementById("gen").textContent="Updated "+new Date(DATA.generated)
    .toLocaleString("en-US",{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
  document.getElementById("tv").textContent=money(t.equity);
  const d=document.getElementById("td");
  if(t.day_change==null||!t.day_change_pct&&t.day_change===0&&t.day_pending){d.innerHTML=dash;}
  else{d.textContent=sgn0(t.day_change)+(t.day_change_pct!=null?"  "+pct(t.day_change_pct):"");
       d.className="m "+cls(t.day_change);}
  const tt=document.getElementById("tt");
  tt.textContent=sgn0(t.equity-t.starting)+"  "+pct(t.return);
  tt.className="m "+cls(t.return);
  document.getElementById("sdep").textContent=m0(t.equity-t.cash);
  document.getElementById("scash").textContent=m0(t.cash);
  document.getElementById("spos").textContent=t.positions;
  document.getElementById("sinc").textContent=new Date(DATA.inception+"T12:00:00")
    .toLocaleDateString("en-US",{month:"short",day:"numeric",year:"2-digit"});
}

function tabs(){
  const el=document.getElementById("tabs");
  const wl=(DATA.watchlist&&DATA.watchlist.themes)||[];
  const cand=(DATA.moonshot_candidates&&DATA.moonshot_candidates.candidates)||[];
  el.innerHTML=DATA.order.map(k=>{const p=DATA.portfolios[k];
    return `<button class="tab" role="tab" data-k="${k}" aria-selected="${k===active}">
      <span class="dot" style="background:var(${SV[k]})"></span>${esc(p.name)}</button>`}).join("")
    +(cand.length?`<button class="tab" role="tab" data-k="candidates" aria-selected="${active==="candidates"}">
      <span class="dot" style="background:var(--s-moon)"></span>Candidates</button>`:"")
    +(wl.length?`<button class="tab" role="tab" data-k="radar" aria-selected="${active==="radar"}">
      <span class="dot" style="background:var(--ink-3)"></span>Radar</button>`:"");
  el.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{active=b.dataset.k;location.hash=active;tabs();panel()});
}

function series(p){
  let nav=p.nav_history||[];
  if(nav.length<2) return null;
  const cut={ "1M":30, "3M":90, "6M":180 }[range];
  if(cut){ const d=new Date(); d.setDate(d.getDate()-cut);
    const iso=d.toISOString().slice(0,10);
    const f=nav.filter(r=>r.date>=iso); if(f.length>=2) nav=f; }
  const base=nav[0].equity||p.starting_cash;
  const labels=nav.map(r=>r.date), eq=nav.map(r=>r.equity);
  const port=eq.map(v=>(v/base)*100);
  const mk=tk=>{const c=(DATA.benchmarks||{})[tk]||{};let b0=null,last=null;
    const o=labels.map(d=>{if(c[d]!=null)last=c[d];if(last==null)return null;
      if(b0==null)b0=last;return (last/b0)*100});
    return o.some(v=>v!=null)?o:null};
  return {labels,port,eq,base,bench:mk(p.benchmark),bn:p.benchmark};
}

function drawChart(p){
  const el=document.getElementById("eq"); if(!el) return;
  if(chart){chart.destroy();chart=null}
  const s=series(p); if(!s) return;
  const col=cv(SV[p.key]), bc=cv("--s-bench"), grid=cv("--grid"), ink=cv("--ink-3");
  const g=el.getContext("2d").createLinearGradient(0,0,0,el.height||300);
  g.addColorStop(0,col+"38"); g.addColorStop(1,col+"03");
  const ds=[{label:p.name,data:s.port,borderColor:col,backgroundColor:g,borderWidth:2,
    pointRadius:0,pointHoverRadius:4,pointHoverBackgroundColor:col,
    pointHoverBorderColor:cv("--bg"),pointHoverBorderWidth:2,tension:.16,fill:true,order:1}];
  if(s.bench)ds.push({label:s.bn,data:s.bench,borderColor:bc,borderWidth:1.5,borderDash:[4,4],
    pointRadius:0,pointHoverRadius:4,tension:.16,fill:false,order:2,spanGaps:true});
  chart=new Chart(el,{type:"line",data:{labels:s.labels,datasets:ds},options:{
    responsive:true,maintainAspectRatio:false,
    interaction:{mode:"index",intersect:false},
    plugins:{legend:{display:false},tooltip:{
      backgroundColor:cv("--surface-1"),titleColor:cv("--ink"),bodyColor:cv("--ink-2"),
      borderColor:cv("--border-2"),borderWidth:1,padding:11,cornerRadius:9,
      displayColors:true,boxWidth:7,boxHeight:7,usePointStyle:true,
      titleFont:{size:11},bodyFont:{size:12,family:"ui-monospace,Menlo,monospace"},
      callbacks:{
        title:it=>new Date(it[0].label+"T12:00:00")
          .toLocaleDateString("en-US",{weekday:"short",month:"short",day:"numeric",year:"numeric"}),
        label:c=>{const d=(c.parsed.y-100);
          if(c.datasetIndex===0){const v=s.eq[c.dataIndex];
            return "  "+c.dataset.label+"   "+money(v)+"   "+(d>=0?"+":"")+d.toFixed(2)+"%"}
          return "  "+c.dataset.label+"   "+(d>=0?"+":"")+d.toFixed(2)+"%"}
      }}},
    scales:{x:{grid:{display:false},border:{color:grid},
        ticks:{color:ink,maxTicksLimit:5,font:{size:9.5},maxRotation:0}},
      y:{grid:{color:grid,drawTicks:false},border:{display:false},
        ticks:{color:ink,font:{size:9.5},padding:6,
          callback:v=>((v-100)>=0?"+":"")+(v-100).toFixed(0)+"%"}}}
  }});
}

function panel(){
  if(active==="candidates"){candidates();return}
  if(active==="radar"){radar();return}
  const p=DATA.portfolios[active], c=`var(${SV[active]})`;
  const eq=p.equity, hold=p.holdings||[];

  let ban="";
  if(p.status==="halted"||p.status==="fullstop")
    ban=`<div class="banner halt"><b>⚠ Circuit breaker · ${esc(p.status)}</b><br>${esc(p.status_note)}</div>`;
  else if(p.drawdown<=-0.15)
    ban=`<div class="banner warn">${esc(p.name)} is ${pct(p.drawdown)} below its high-water mark. Trading continues; a written review is owed.</div>`;

  const dayHtml = p.day_change==null ? dash
    : `<span class="${cls(p.day_change)}">${sgn0(p.day_change)}</span>`;
  const dayPct = p.day_change_pct==null ? "awaiting a prior close"
    : pct(p.day_change_pct)+" today";

  const tiles=`<div class="tiles">
    <div class="tile"><div class="lbl">Book value</div><div class="v m">${m0(eq)}</div>
      <div class="s">from ${m0(p.starting_cash)}</div></div>
    <div class="tile"><div class="lbl">Today</div><div class="v m">${dayHtml}</div>
      <div class="s">${dayPct}</div></div>
    <div class="tile"><div class="lbl">Total return</div>
      <div class="v m ${cls(p.total_return)}">${pct(p.total_return)}</div>
      <div class="s">vs ${esc(p.benchmark)}</div></div>
    <div class="tile"><div class="lbl">Cash</div><div class="v m">${(p.cash_pct*100).toFixed(1)}%</div>
      <div class="s">${m0(p.cash)} dry powder</div></div>
  </div>`;

  const hasNav=(p.nav_history||[]).length>1;
  const chart=`<div class="card">
    <div class="chead"><div><h2>Performance</h2>
      <p class="note" style="margin:5px 0 0">Indexed to the first day. Hover for book value and return.</p></div>
      <div class="ranges">${["1M","3M","6M","ALL"].map(r=>
        `<button class="rbtn" data-r="${r}" aria-pressed="${r===range}">${r}</button>`).join("")}</div>
    </div>
    ${hasNav?`<div class="chartbox"><canvas id="eq"></canvas></div>
      <div class="legend"><span><i style="background:${c}"></i>${esc(p.name)}</span>
      <span><i class="dash"></i>${esc(p.benchmark)}</span></div>`
    :`<div class="empty">The curve appears once there are two days of history.<br>It fills in after each daily run.</div>`}
  </div>`;

  let alloc="";
  if(hold.length){
    const mx=Math.max(...hold.map(h=>h.weight),p.cash_pct);
    alloc=`<div class="card"><h2>Allocation</h2><p class="note">Position weights, plus cash.</p>
      <div class="alloc">${hold.map(h=>`<div class="arow">
        <span class="m">${esc(h.ticker)}</span>
        <span class="abar"><span style="width:${(h.weight/mx*100).toFixed(1)}%;background:${c}"></span></span>
        <span class="m dim" style="text-align:right">${(h.weight*100).toFixed(1)}%</span></div>`).join("")}
        <div class="arow"><span class="m dim">CASH</span>
          <span class="abar"><span style="width:${(p.cash_pct/mx*100).toFixed(1)}%;background:var(--border-2)"></span></span>
          <span class="m dim" style="text-align:right">${(p.cash_pct*100).toFixed(1)}%</span></div>
      </div></div>`;
  }

  const rows=hold.map(h=>`<tr>
    <td><div class="tk"><span class="sw" style="background:${c}"></span>${esc(h.ticker)}${
      h.house_money_taken?'<span class="pill hm">HOUSE $</span>':""}</div></td>
    <td class="m">${h.shares.toLocaleString("en-US",{maximumFractionDigits:2})}</td>
    <td class="m">${money(h.avg_cost)}</td>
    <td class="m">${h.price==null?dash:money(h.price)}</td>
    <td class="m ${h.day_change==null?"":cls(h.day_change)}">${h.day_change==null?dash:sgn(h.day_change)}</td>
    <td class="m ${h.day_change_pct==null?"":cls(h.day_change_pct)}">${h.day_change_pct==null?dash:pct(h.day_change_pct)}</td>
    <td class="m ${cls(h.unrealized)}">${sgn(h.unrealized)}</td>
    <td class="m ${cls(h.unrealized)}">${pct(h.unrealized_pct)}</td>
    <td class="m opt">${m0(h.market_value)}</td>
    <td class="m dim opt">${(h.weight*100).toFixed(1)}%</td></tr>`).join("");

  const holdings=`<div class="card"><h2>Positions</h2>
    <p class="note">${!hold.length?"Nothing owned yet."
      :DATA._partial?"Live prices where available; the rest are marked at the last close."
      :DATA._live?"Live prices, refreshed in your browser."
      :"Marked at the last available price."}</p>
    ${hold.length?`<div class="pcards">${hold.map(h=>`
      <div class="pcard">
        <div class="pc1">
          <span class="tk"><span class="sw" style="background:${c}"></span>${esc(h.ticker)}${
            h.house_money_taken?'<span class="pill hm">HOUSE $</span>':""}</span>
          <span class="px m">${h.price==null?dash:money(h.price)}</span>
        </div>
        <div class="pc2">
          <div class="pcell"><span class="lbl">Today</span>
            <span class="v m ${h.day_change==null?"dim":cls(h.day_change)}">${
              h.day_change==null?"—":sgn(h.day_change)+"  "+pct(h.day_change_pct)}</span></div>
          <div class="pcell"><span class="lbl">Total</span>
            <span class="v m ${cls(h.unrealized)}">${sgn(h.unrealized)}  ${pct(h.unrealized_pct)}</span></div>
        </div>
        <div class="pc3"><span>Qty <b class="m">${h.shares.toLocaleString("en-US",{maximumFractionDigits:2})}</b></span>
          <span>Avg <b class="m">${money(h.avg_cost)}</b></span>
          <span>Value <b class="m">${m0(h.market_value)}</b></span>
          <span>Wt <b class="m">${(h.weight*100).toFixed(1)}%</b></span></div>
      </div>`).join("")}</div>
    <div class="tw"><table>
      <thead><tr><th>Ticker</th><th>Qty</th><th>Avg cost</th><th>Last</th>
        <th>Day $</th><th>Day %</th><th>Total $</th><th>Total %</th>
        <th class="opt">Value</th><th class="opt">Wt</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`
    :`<div class="empty">No positions yet.<br>Cash is a position too.</div>`}</div>`;

  const tr=(p.trades||[]).slice().reverse();
  const trades=`<div class="card"><h2>Trade log</h2>
    <p class="note">Every fill, with the reason. Nothing is deleted.</p>
    ${tr.length?tr.map(t=>{
      const pills=(t.tags||[]).filter(x=>x!=="AUTO")
        .map(x=>`<span class="pill ${x==="OVERRIDE"?"ov":""}">${esc(x)}</span>`).join("");
      return `<div class="trade"><span class="side ${esc(t.action)}">${esc(t.action)}</span>
        <div class="tb"><div class="th2"><span>${esc(t.ticker)}${pills}</span>
          <span class="m dim" style="font-size:10.5px">${esc(t.date)}</span></div>
        <div class="rsn">${esc(t.reason)}</div>
        ${t.override_justification?`<div class="rsn" style="margin-top:5px"><b>Override:</b> ${esc(t.override_justification)}</div>`:""}
        <div class="meta m">${t.shares.toLocaleString("en-US",{maximumFractionDigits:4})} sh @ ${money(t.price)} = ${m0(t.value)}${t.price_source?" · "+esc(t.price_source):""}</div>
        </div></div>`}).join(""):`<div class="empty">No trades yet.</div>`}</div>`;

  const ids=[...new Set(hold.map(h=>h.thesis_id).filter(Boolean))];
  const th=ids.map(id=>{const t=(DATA.theses||{})[String(id).toLowerCase()];
    return t?`<details><summary>${esc(id.toUpperCase())} — why we own it</summary>
      <div class="thesis">${esc(t)}</div></details>`:""}).join("");

  document.getElementById("panel").innerHTML=ban+tiles+chart+alloc+holdings+trades
    +(th?`<div class="card"><h2>Theses</h2>
      <p class="note">The written case for each position, with every claim's verification status.</p>${th}</div>`:"");

  document.querySelectorAll(".rbtn").forEach(b=>b.onclick=()=>{range=b.dataset.r;panel()});
  drawChart(p);
}

function radar(){
  if(chart){chart.destroy();chart=null}
  const wl=DATA.watchlist||{}, th=wl.themes||[];
  const bd=(l,v)=>{const s=String(v||"").toUpperCase();let col="var(--ink-2)";
    if(s.startsWith("LOW")||s.startsWith("RISING")||s==="GOOD")col="var(--good)";
    else if(s.startsWith("HIGH")||s.startsWith("FALLING")||s==="NONE")col="var(--bad)";
    else if(s==="DILUTED"||s.startsWith("MEDIUM"))col="var(--warn)";
    return `<div class="rm"><span class="lbl">${esc(l)}</span>
      <span class="v" style="color:${col}">${esc(v||"—")}</span></div>`};
  const cards=th.map(t=>{const st=String(t.status||"").toUpperCase();
    const pc=st.startsWith("BOUGHT")?"bought":st.startsWith("REJECTED")?"rej":"";
    const veh=Object.entries(t.vehicles||{}).filter(([k])=>!k.startsWith("_"))
      .map(([k,v])=>`<div class="veh"><b>${esc(k)}</b> ${esc(v)}</div>`).join("");
    const todo=(t.vehicles||{})._todo;
    return `<div class="card">
      <div class="rhead"><h2>${esc(t.name)}</h2>
        <span class="spill ${pc}">${esc(t.status||"WATCHING")}</span></div>
      <p class="note" style="margin:9px 0 0">${esc(t.thesis||"")}</p>
      <div class="rgrid">${bd("Chatter",t.chatter)}${bd("Trajectory",t.trajectory)}
        ${bd("Vehicle",t.vehicle_quality)}${bd("Time to P&L",t.time_to_pnl)}</div>
      ${t.capital_committed?`<div class="rsec"><span class="lbl">Capital committed</span>
        <div class="rtext" style="margin-top:5px">${esc(t.capital_committed)}</div></div>`:""}
      ${veh?`<div class="rsec"><span class="lbl">Vehicles</span>${veh}</div>`:""}
      ${todo?`<div class="rsec"><span class="lbl">Next</span><div class="rtext" style="margin-top:5px">${esc(todo)}</div></div>`:""}
      ${t.note?`<details><summary>Full note &amp; verification</summary><div class="thesis">${esc(t.note)}</div></details>`:""}
    </div>`}).join("");
  const oq=(wl._open_questions||[]).map(x=>`<li>${esc(x)}</li>`).join("");
  const ll=(wl._lesson_log||[]).map(l=>`<div class="rsec"><span class="lbl">${esc(l.date)} · cost: ${esc(l.cost||"n/a")}</span>
    <div class="rtext" style="margin-top:5px">${esc(l.lesson)}</div>
    ${l.fix?`<div class="rtext" style="margin-top:5px"><b>Fix:</b> ${esc(l.fix)}</div>`:""}</div>`).join("");
  document.getElementById("panel").innerHTML=
    `<div class="card"><h2>Emerging theme radar</h2>
      <p class="note">Low chatter, rising interest — what I'm hunting before it becomes a trade.</p>
      <div class="rgrid">${bd("Last review",wl._last_review)}${bd("Next review",wl._next_review)}
        ${bd("Tracked",String(th.length))}</div></div>`
    +cards
    +(oq?`<div class="card"><h2>Open questions</h2><p class="note">Carried into the next cycle.</p><ul class="rlist">${oq}</ul></div>`:"")
    +(ll?`<div class="card"><h2>Lesson log</h2><p class="note">Mistakes and what changed because of them. Public on purpose.</p>${ll}</div>`:"");
}

function candidates(){
  if(chart){chart.destroy();chart=null}
  const mc=DATA.moonshot_candidates||{}, list=mc.candidates||[];
  const money0=v=>"$"+Math.round(v||0).toLocaleString("en-US");
  const scoreCls=s=>s>=0.7?"bought":s>=0.4?"":"rej";
  const cards=list.map(c=>{
    const cap=c.market_cap?money0(c.market_cap):(c.cap_unknown?"unknown":"—");
    const merged={};
    (c.buys||[]).forEach(b=>{
      const k=(b.insider||"").toLowerCase();
      const m=merged[k]||(merged[k]={insider:b.insider,roles:new Set(),spend:0,dates:new Set()});
      (b.roles||[]).forEach(r=>m.roles.add(r));
      m.spend+=b.spend||0;
      (b.dates||[]).forEach(d=>m.dates.add(d));
    });
    const buys=Object.values(merged).map(b=>`<div class="veh"><b>${esc(b.insider||"")}</b>
      ${esc([...b.roles].join(", "))} — ${money0(b.spend)}
      <span class="dim">(${esc([...b.dates].join(", "))})</span></div>`).join("");
    const edgar=c.cik?`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${encodeURIComponent(c.cik)}&type=4`:"";
    return `<div class="card">
      <div class="rhead"><h2>${esc(c.ticker)} <span class="dim" style="font-weight:500;font-size:12px">${esc(c.issuer||"")}</span></h2>
        <span class="spill ${scoreCls(c.score)}">score ${(c.score??0).toFixed(2)}</span></div>
      <div class="rgrid">
        <div class="rm"><span class="lbl">Insiders</span><span class="v">${c.n_insiders??"—"}</span></div>
        <div class="rm"><span class="lbl">Total spend</span><span class="v">${money0(c.total_spend)}</span></div>
        <div class="rm"><span class="lbl">Market cap</span><span class="v">${esc(cap)}</span></div>
        <div class="rm"><span class="lbl">Latest buy</span><span class="v">${esc(c.latest_buy||"—")}</span></div>
      </div>
      ${buys?`<div class="rsec"><span class="lbl">Buys</span>${buys}</div>`:""}
      ${edgar?`<div class="rsec"><a href="${edgar}" target="_blank" rel="noopener" class="rtext">View Form 4 filings on EDGAR →</a></div>`:""}
    </div>`}).join("");
  document.getElementById("panel").innerHTML=
    `<div class="card"><h2>Moonshot candidates</h2>
      <p class="note">SEC Form 4 insider-cluster buys — sourcing only. Each still needs
        analyst upside &gt;35%, a dated catalyst inside 18 months, and sentiment
        acceleration (IPS 1) before anything is bought.</p>
      <div class="rgrid">
        <div class="rm"><span class="lbl">Scanned</span><span class="v">${mc.days_scanned??"—"} days</span></div>
        <div class="rm"><span class="lbl">Clusters</span><span class="v">${mc.clusters_found??"—"}</span></div>
        <div class="rm"><span class="lbl">Candidates</span><span class="v">${list.length}</span></div>
        <div class="rm"><span class="lbl">As of</span><span class="v">${mc.generated?new Date(mc.generated).toLocaleDateString("en-US",{month:"short",day:"numeric"}):"—"}</span></div>
      </div>
    </div>`
    +(cards||`<div class="card"><div class="empty">No candidates cleared the filters this run.</div></div>`);
}

/* ======================================================================
   Live quotes -- runs in your browser, costs nothing.

   This is the piece that makes a refresh actually mean something. It fetches
   a current price for every holding and recomputes the book from scratch:
   value, day change, unrealized gain, weights, cash percentage.

   Three rules govern it, and they matter more than the feature does:

   1. It never invents a number. A ticker that fails to quote keeps the price
      baked in at build time. A total that mixes live and stale marks says so.
   2. It never writes anything. State, history and the trade log are the
      server's job. This only changes what you are looking at.
   3. It never blocks the page. The static numbers render first, always. If
      the network is down, or the key is missing, or Finnhub is having a bad
      afternoon, you still get a working dashboard -- just an older one.

   The drawdown figure and the NAV curve deliberately stay at their last
   end-of-day values. The circuit breaker is enforced server-side against
   closing marks, and showing an intraday drawdown next to a rule that does
   not act on intraday drawdowns would be a lie of implication.
   ====================================================================== */
function applyQuotes(px){
  let tEq=0, tDay=0, tPriorBase=0, anyLive=false, anyStale=false;

  for(const k of DATA.order){
    const p=DATA.portfolios[k], hold=p.holdings||[];
    let mv=0, day=0, priorValue=0, dayCounted=false;

    for(const h of hold){
      const q=px[h.ticker];
      if(q){
        h.price=q.c;
        if(q.pc) h.prev_close=q.pc;
        h.mark_source="finnhub live";
        h.live=true;
        anyLive=true;
      }else{
        h.live=false;
        anyStale=true;
      }
      if(h.price!=null){
        h.market_value=h.shares*h.price;
        h.unrealized=h.market_value-h.cost_basis;
        h.unrealized_pct=h.cost_basis?h.unrealized/h.cost_basis:0;
      }
      if(h.price!=null&&h.prev_close){
        h.day_change=h.shares*(h.price-h.prev_close);
        h.day_change_pct=(h.price-h.prev_close)/h.prev_close;
        day+=h.day_change;
        priorValue+=h.shares*h.prev_close;
        dayCounted=true;
      }
      mv+=h.market_value||0;
    }

    p.equity=p.cash+mv;
    for(const h of hold) h.weight=p.equity?(h.market_value||0)/p.equity:0;
    p.cash_pct=p.equity?p.cash/p.equity:0;
    p.total_return=p.starting_cash?(p.equity-p.starting_cash)/p.starting_cash:0;

    /* Percent is measured against the book as it stood at yesterday's close,
       counting only the names we can actually compare. Same convention the
       Python side uses, so the two never disagree. */
    if(dayCounted){
      const priorEquity=p.cash+priorValue;
      p.day_change=day;
      p.day_change_pct=priorEquity?day/priorEquity:null;
      tDay+=day; tPriorBase+=priorEquity;
    }
    tEq+=p.equity;
  }

  DATA.total.equity=tEq;
  DATA.total.return=DATA.total.starting?(tEq-DATA.total.starting)/DATA.total.starting:0;
  if(tPriorBase){
    DATA.total.day_change=tDay;
    DATA.total.day_change_pct=tDay/tPriorBase;
  }
  DATA._live=anyLive;
  DATA._partial=anyLive&&anyStale;
  return anyLive;
}

async function liveQuotes(){
  if(!LIVE_KEY||!DATA) return;
  const tks=[...new Set(DATA.order.flatMap(k=>(DATA.portfolios[k].holdings||[])
    .map(h=>h.ticker)))];
  if(!tks.length) return;

  /* Rebuild the "as built" text from the payload rather than reading whatever
     is on screen -- otherwise a failed second pull appends "unavailable" to a
     stamp that already says "Live", which reads as a contradiction. */
  const stamp=document.getElementById("gen");
  const built="Updated "+new Date(DATA.generated)
    .toLocaleString("en-US",{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
  if(stamp){stamp.textContent="Fetching live prices…"; stamp.classList.remove("live");}

  /* Finnhub's free tier allows 60 calls a minute. Sixteen positions is well
     inside that, but fetch in small waves anyway so a larger book later does
     not quietly start getting throttled and showing stale names. */
  const px={};
  const WAVE=8;
  for(let i=0;i<tks.length;i+=WAVE){
    await Promise.all(tks.slice(i,i+WAVE).map(async t=>{
      try{
        const r=await fetch("https://finnhub.io/api/v1/quote?symbol="+
          encodeURIComponent(t)+"&token="+encodeURIComponent(LIVE_KEY),
          {cache:"no-store"});
        if(!r.ok) return;
        const j=await r.json();
        if(j&&typeof j.c==="number"&&j.c>0)
          px[t]={c:j.c, pc:(typeof j.pc==="number"&&j.pc>0)?j.pc:null};
      }catch(e){ /* one bad ticker must never take down the page */ }
    }));
  }

  const got=Object.keys(px).length;
  if(!got||!applyQuotes(px)){
    if(stamp) stamp.textContent=built+" · live prices unavailable";
    const d=document.querySelector(".dotpulse");
    if(d) d.classList.remove("live","partial");
    return;
  }

  head(); panel();
  const s=document.getElementById("gen");
  if(s){
    const now=new Date().toLocaleTimeString("en-US",{hour:"numeric",minute:"2-digit"});
    s.textContent="Live · "+now+(got<tks.length?"  · "+got+"/"+tks.length+" quoted":"");
    s.classList.toggle("live",!DATA._partial);
  }
  const dot=document.querySelector(".dotpulse");
  if(dot){dot.classList.toggle("live",!DATA._partial);
          dot.classList.toggle("partial",!!DATA._partial);}
}

document.getElementById("tbtn").onclick=()=>{
  const cur=document.documentElement.getAttribute("data-theme")==="light"?"dark":"light";
  document.documentElement.setAttribute("data-theme",cur);
  if(DATA)panel();
};

if(DATA){
  head(); tabs(); panel();
  liveQuotes();
  /* Coming back to an already-open tab should not show yesterday's prices.
     Throttled to a minute so leaving it open on a second monitor does not
     hammer the free tier. */
  let lastPull=Date.now();
  document.addEventListener("visibilitychange",()=>{
    if(document.visibilityState==="visible"&&Date.now()-lastPull>60000){
      lastPull=Date.now(); liveQuotes();
    }
  });
}
else document.getElementById("panel").innerHTML=
  '<div class="card"><div class="empty">No data yet. Run <code>python -m engine.run daily</code>.</div></div>';
</script>
</body>
</html>
"""
