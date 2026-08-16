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
        },
        "portfolios": snaps,
        "benchmarks": benches,
        "theses": _load_theses(),
        "watchlist": _load_watchlist(),
        "order": ["core", "moonshot", "ai"],
    }

    os.makedirs(DOCS_DIR, exist_ok=True)
    data_json = json.dumps(payload, separators=(",", ":"))
    html = TEMPLATE.replace("/*__DATA__*/null", data_json)
    out_path = os.path.join(DOCS_DIR, "index.html")
    with open(out_path, "w") as fh:
        fh.write(html)
    with open(os.path.join(DOCS_DIR, "data.json"), "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"  dashboard -> {out_path}")
    return out_path


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#1a1a19">
<title>Portfolio Desk</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{
  color-scheme: light;
  --surface-0:#f5f5f3; --surface-1:#fcfcfb; --surface-2:#efefec;
  --border:#e0e0db; --border-strong:#c9c9c2;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#83827c;
  --good:#0ca30c; --critical:#d03b3b; --warning:#fab219;
  --s-core:#2a78d6; --s-moon:#eb6834; --s-ai:#1baf7a; --s-bench:#83827c;
  --radius:14px;
}
@media (prefers-color-scheme: dark){
  :root:where(:not([data-theme="light"])){
    color-scheme: dark;
    --surface-0:#111110; --surface-1:#1a1a19; --surface-2:#242422;
    --border:#333331; --border-strong:#4a4a46;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8e8d85;
    --good:#0ca30c; --critical:#d03b3b; --warning:#fab219;
    --s-core:#3987e5; --s-moon:#d95926; --s-ai:#199e70; --s-bench:#8e8d85;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --surface-0:#111110; --surface-1:#1a1a19; --surface-2:#242422;
  --border:#333331; --border-strong:#4a4a46;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8e8d85;
  --s-core:#3987e5; --s-moon:#d95926; --s-ai:#199e70; --s-bench:#8e8d85;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{
  margin:0; background:var(--surface-0); color:var(--text-primary);
  font:15px/1.5 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  padding-bottom:env(safe-area-inset-bottom);
}
.wrap{max-width:1080px;margin:0 auto;padding:16px 14px 56px}
.mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}
.pos{color:var(--good)} .neg{color:var(--critical)}

header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:18px}
h1{font-size:17px;margin:0 0 2px;letter-spacing:-0.01em}
.sub{font-size:12px;color:var(--text-muted)}
.themebtn{background:var(--surface-2);border:1px solid var(--border);color:var(--text-secondary);
  border-radius:9px;padding:7px 11px;font-size:12px;cursor:pointer;flex:none}

/* hero */
.hero{background:var(--surface-1);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px;margin-bottom:14px}
.hero .big{font-size:34px;font-weight:650;letter-spacing:-0.02em;line-height:1.1}
.hero .chg{font-size:15px;margin-top:4px;font-weight:550}
.herorow{display:flex;gap:22px;flex-wrap:wrap;margin-top:14px;
  padding-top:14px;border-top:1px solid var(--border)}
.herorow div{font-size:12px;color:var(--text-muted)}
.herorow b{display:block;font-size:15px;color:var(--text-primary);font-weight:550;margin-top:2px}

/* tabs */
.tabs{display:flex;gap:6px;background:var(--surface-2);padding:4px;border-radius:11px;margin-bottom:14px}
.tab{flex:1;border:0;background:transparent;color:var(--text-secondary);padding:9px 6px;
  border-radius:8px;font-size:13px;font-weight:550;cursor:pointer;display:flex;
  align-items:center;justify-content:center;gap:6px;min-height:40px}
.tab .dot{width:8px;height:8px;border-radius:50%;flex:none}
.tab[aria-selected="true"]{background:var(--surface-1);color:var(--text-primary);
  box-shadow:0 1px 3px rgba(0,0,0,.10)}

.card{background:var(--surface-1);border:1px solid var(--border);border-radius:var(--radius);
  padding:16px;margin-bottom:14px}
.card h2{font-size:13px;margin:0 0 3px;font-weight:600;letter-spacing:.01em}
.card .note{font-size:12px;color:var(--text-muted);margin:0 0 14px}

/* stat tiles */
.tiles{display:grid;grid-template-columns:repeat(2,1fr);gap:9px;margin-bottom:14px}
@media(min-width:620px){.tiles{grid-template-columns:repeat(4,1fr)}}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:11px;padding:12px 13px}
.tile .k{font-size:11px;color:var(--text-muted);letter-spacing:.02em}
.tile .v{font-size:19px;font-weight:600;margin-top:3px;letter-spacing:-0.01em}
.tile .m{font-size:11px;color:var(--text-muted);margin-top:1px}

.chartbox{position:relative;height:260px}
@media(min-width:620px){.chartbox{height:320px}}

/* allocation bars */
.alloc{display:flex;flex-direction:column;gap:7px}
.arow{display:grid;grid-template-columns:58px 1fr 62px;align-items:center;gap:9px;font-size:12px}
.abar{height:15px;background:var(--surface-2);border-radius:4px;overflow:hidden}
.abar span{display:block;height:100%;border-radius:4px}

/* table */
.tblwrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 -16px;padding:0 16px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
/* On a phone, shares and average cost are the least useful columns -- drop them
   so return, P&L and weight are visible without horizontal scrolling. */
@media(max-width:619px){
  th.opt,td.opt{display:none}
  table{font-size:12px}
}
th{text-align:right;font-weight:550;color:var(--text-muted);font-size:11px;
  padding:0 0 8px;border-bottom:1px solid var(--border);white-space:nowrap;letter-spacing:.02em}
th:first-child,td:first-child{text-align:left}
td{padding:9px 0;border-bottom:1px solid var(--border);text-align:right;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
td:first-child{font-weight:600}
.tk{display:flex;align-items:center;gap:7px}
.tk .sw{width:3px;height:15px;border-radius:2px;flex:none}
.pill{display:inline-block;font-size:9.5px;padding:1.5px 5px;border-radius:4px;
  background:var(--surface-2);color:var(--text-secondary);margin-left:5px;
  font-weight:600;letter-spacing:.03em;vertical-align:1px}
.pill.hm{background:rgba(12,163,12,.15);color:var(--good)}
.pill.ov{background:rgba(250,178,25,.18);color:#8a5f00}
:root[data-theme="dark"] .pill.ov{color:var(--warning)}

/* trades */
.trade{display:flex;gap:11px;padding:11px 0;border-bottom:1px solid var(--border);font-size:12.5px}
.trade:last-child{border-bottom:0}
.tside{font-size:10px;font-weight:700;padding:3px 6px;border-radius:5px;height:fit-content;
  flex:none;letter-spacing:.04em;min-width:40px;text-align:center}
.tside.BUY{background:rgba(12,163,12,.15);color:var(--good)}
.tside.SELL{background:rgba(208,59,59,.15);color:var(--critical)}
.tbody-t{flex:1;min-width:0}
.thead-t{display:flex;justify-content:space-between;gap:10px;margin-bottom:2px}
.treason{color:var(--text-secondary);font-size:12px;line-height:1.45}
.tmeta{color:var(--text-muted);font-size:11px;margin-top:3px}

.banner{border-radius:11px;padding:12px 14px;font-size:12.5px;margin-bottom:14px;
  display:flex;gap:9px;align-items:flex-start;line-height:1.5}
.banner.halt{background:rgba(208,59,59,.12);border:1px solid rgba(208,59,59,.35);color:var(--text-primary)}
.banner.warn{background:rgba(250,178,25,.12);border:1px solid rgba(250,178,25,.4);color:var(--text-primary)}
.banner.info{background:var(--surface-2);border:1px solid var(--border);color:var(--text-secondary)}

.empty{color:var(--text-muted);font-size:12.5px;padding:18px 0;text-align:center;line-height:1.6}
details{margin-top:10px}
summary{cursor:pointer;font-size:12px;color:var(--text-secondary);padding:7px 0;font-weight:550}
.thesis{font-size:12.5px;color:var(--text-secondary);line-height:1.65;white-space:pre-wrap;
  background:var(--surface-2);border-radius:9px;padding:13px;margin-top:8px;
  max-height:340px;overflow:auto}
.rhead{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap}
.rhead h2{flex:1 1 60%;min-width:0}
.spill{font-size:9.5px;font-weight:700;letter-spacing:.04em;padding:3px 7px;border-radius:5px;
  max-width:100%;white-space:normal;line-height:1.35}
@media(max-width:619px){.rhead h2{flex:1 1 100%}}
.spill.bought{background:rgba(12,163,12,.15);color:var(--good)}
.spill.action{background:rgba(250,178,25,.18);color:#8a5f00}
:root[data-theme="dark"] .spill.action{color:var(--warning)}
.spill.watch{background:var(--surface-2);color:var(--text-secondary)}
.spill.rej{background:rgba(208,59,59,.13);color:var(--critical)}
.rgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
@media(min-width:620px){.rgrid{grid-template-columns:repeat(4,1fr)}}
.rmeta{background:var(--surface-2);border-radius:8px;padding:8px 10px}
.rmeta .k{display:block;font-size:10px;color:var(--text-muted);letter-spacing:.02em}
.rmeta .v{display:block;font-size:12px;font-weight:600;margin-top:2px;line-height:1.35}
.rsec{margin-top:12px}
.rsec .k{display:block;font-size:10px;color:var(--text-muted);letter-spacing:.03em;
  text-transform:uppercase;margin-bottom:5px}
.rtext{font-size:12.5px;color:var(--text-secondary);line-height:1.55}
.veh{font-size:12px;color:var(--text-secondary);line-height:1.5;padding:6px 0;
  border-bottom:1px solid var(--border)}
.veh:last-child{border-bottom:0}
.veh b{color:var(--text-primary);font-family:ui-monospace,Menlo,monospace}
.rlist{margin:0;padding-left:18px;font-size:12.5px;color:var(--text-secondary);line-height:1.7}
footer{text-align:center;color:var(--text-muted);font-size:11px;margin-top:26px;line-height:1.7}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--text-secondary);
  margin-bottom:10px;align-items:center}
.legend i{display:inline-block;width:14px;height:2.5px;border-radius:2px;margin-right:5px;vertical-align:3px}
.legend i.dash{background:repeating-linear-gradient(90deg,var(--s-bench) 0 4px,transparent 4px 8px)}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>Portfolio Desk</h1>
      <div class="sub" id="gen"></div>
    </div>
    <button class="themebtn" id="themebtn" type="button">Theme</button>
  </header>

  <div class="hero">
    <div class="sub">Total across all three portfolios</div>
    <div class="big mono" id="totalval">—</div>
    <div class="chg mono" id="totalchg">—</div>
    <div class="herorow">
      <div>Deployed<b class="mono" id="tdep">—</b></div>
      <div>Cash<b class="mono" id="tcash">—</b></div>
      <div>Positions<b class="mono" id="tpos">—</b></div>
      <div>Since<b class="mono" id="tinc">—</b></div>
    </div>
  </div>

  <div class="tabs" id="tabs" role="tablist"></div>
  <div id="panel"></div>

  <footer>
    Paper money. Managed by Claude under the rules in <code>IPS.md</code>.<br>
    Not investment advice. Every trade is a git commit — history is auditable.
  </footer>
</div>

<script>
const DATA = /*__DATA__*/null;
let chart = null;
let active = (DATA && DATA.order && DATA.order[0]) || "core";

const SERIES_VAR = {core:"--s-core", moonshot:"--s-moon", ai:"--s-ai"};
const cssvar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

const money = v => (v<0?"-":"") + "$" + Math.abs(v).toLocaleString("en-US",
  {minimumFractionDigits:2, maximumFractionDigits:2});
const money0 = v => (v<0?"-":"") + "$" + Math.abs(v).toLocaleString("en-US",
  {maximumFractionDigits:0});
const pct = v => (v>=0?"+":"") + (v*100).toFixed(2) + "%";
const cls = v => v>=0 ? "pos" : "neg";
const esc = s => String(s==null?"":s).replace(/[&<>"']/g,
  c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

/* ---------- header ---------- */
function renderHeader(){
  const t = DATA.total;
  document.getElementById("gen").textContent =
    "Updated " + new Date(DATA.generated).toLocaleString("en-US",
      {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
  document.getElementById("totalval").textContent = money(t.equity);
  const chg = document.getElementById("totalchg");
  chg.textContent = pct(t.return) + "  ·  " + money(t.equity - t.starting);
  chg.className = "chg mono " + cls(t.return);
  document.getElementById("tdep").textContent = money0(t.equity - t.cash);
  document.getElementById("tcash").textContent = money0(t.cash);
  document.getElementById("tpos").textContent = t.positions;
  document.getElementById("tinc").textContent =
    new Date(DATA.inception + "T12:00:00").toLocaleDateString("en-US",
      {month:"short", day:"numeric", year:"2-digit"});
}

/* ---------- tabs ---------- */
function renderTabs(){
  const tabs = document.getElementById("tabs");
  const wl = (DATA.watchlist && DATA.watchlist.themes) || [];
  tabs.innerHTML = DATA.order.map(k=>{
    const p = DATA.portfolios[k];
    return `<button class="tab" role="tab" data-k="${k}"
      aria-selected="${k===active}">
      <span class="dot" style="background:var(${SERIES_VAR[k]})"></span>${esc(p.name)}</button>`;
  }).join("") + (wl.length ? `<button class="tab" role="tab" data-k="radar"
      aria-selected="${active==="radar"}">
      <span class="dot" style="background:var(--text-muted)"></span>Radar</button>` : "");
  tabs.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{
    active = b.dataset.k; renderTabs(); renderPanel();
  });
}

/* ---------- equity curve, indexed to 100 ---------- */
function buildSeries(p){
  const nav = p.nav_history || [];
  if(!nav.length) return null;
  const base = nav[0].equity || p.starting_cash;
  const labels = nav.map(r=>r.date);
  const port = nav.map(r=> (r.equity/base)*100 );

  const mk = tk => {
    const closes = (DATA.benchmarks||{})[tk] || {};
    let b0 = null, last = null;
    const out = labels.map(d=>{
      if(closes[d]!=null) last = closes[d];
      if(last==null) return null;
      if(b0==null) b0 = last;
      return (last/b0)*100;
    });
    return out.some(v=>v!=null) ? out : null;
  };
  return {labels, port, bench: mk(p.benchmark), benchName: p.benchmark};
}

function renderChart(p){
  const el = document.getElementById("equity");
  if(!el) return;
  if(chart){ chart.destroy(); chart = null; }
  const s = buildSeries(p);
  if(!s) return;

  const color = cssvar(SERIES_VAR[p.key]);
  const benchC = cssvar("--s-bench");
  const grid = cssvar("--border");
  const ink = cssvar("--text-muted");

  const ds = [{
    label: p.name, data: s.port, borderColor: color, backgroundColor: color+"1f",
    borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: .15, fill: true, order: 1
  }];
  if(s.bench) ds.push({
    label: s.benchName, data: s.bench, borderColor: benchC, borderWidth: 2,
    borderDash: [5,4], pointRadius: 0, pointHoverRadius: 5, tension: .15,
    fill: false, order: 2, spanGaps: true
  });

  chart = new Chart(el, {
    type: "line",
    data: {labels: s.labels, datasets: ds},
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: {mode:"index", intersect:false},
      plugins: {
        legend: {display:false},
        tooltip: {
          backgroundColor: cssvar("--surface-1"), titleColor: cssvar("--text-primary"),
          bodyColor: cssvar("--text-secondary"), borderColor: cssvar("--border-strong"),
          borderWidth: 1, padding: 10, displayColors: true, boxWidth: 8, boxHeight: 8,
          usePointStyle: true, cornerRadius: 8,
          callbacks: {
            label: c => " " + c.dataset.label + "  " +
                    ((c.parsed.y-100)>=0?"+":"") + (c.parsed.y-100).toFixed(2) + "%"
          }
        }
      },
      scales: {
        x: {grid:{display:false}, border:{color:grid},
            ticks:{color:ink, maxTicksLimit:6, font:{size:10}}},
        y: {grid:{color:grid, drawTicks:false}, border:{display:false},
            ticks:{color:ink, font:{size:10},
                   callback:v=> ((v-100)>=0?"+":"") + (v-100).toFixed(0) + "%"}}
      }
    }
  });
}

/* ---------- panel ---------- */
function renderPanel(){
  if(active === "radar"){ renderRadar(); return; }
  const p = DATA.portfolios[active];
  const c = `var(${SERIES_VAR[active]})`;
  const eq = p.equity, hold = p.holdings || [];

  let banner = "";
  if(p.status === "halted" || p.status === "fullstop"){
    banner = `<div class="banner halt"><span>&#9888;</span><div><b>Circuit breaker: ${esc(p.status)}</b><br>${esc(p.status_note)}</div></div>`;
  } else if(p.drawdown <= -0.15){
    banner = `<div class="banner warn"><span>&#9888;</span><div>${esc(p.name)} is ${pct(p.drawdown)} below its high-water mark. Trading continues; a written review is owed.</div></div>`;
  }

  const tiles = `<div class="tiles">
    <div class="tile"><div class="k">BOOK VALUE</div><div class="v mono">${money0(eq)}</div>
      <div class="m">from ${money0(p.starting_cash)}</div></div>
    <div class="tile"><div class="k">TOTAL RETURN</div>
      <div class="v mono ${cls(p.total_return)}">${pct(p.total_return)}</div>
      <div class="m">vs ${esc(p.benchmark)}</div></div>
    <div class="tile"><div class="k">CASH</div><div class="v mono">${(p.cash_pct*100).toFixed(1)}%</div>
      <div class="m">${money0(p.cash)} dry powder</div></div>
    <div class="tile"><div class="k">DRAWDOWN</div>
      <div class="v mono ${p.drawdown < -0.001 ? "neg" : ""}">${pct(p.drawdown)}</div>
      <div class="m">${p.n_holdings} position${p.n_holdings===1?"":"s"}</div></div>
  </div>`;

  const legend = `<div class="legend">
    <span><i style="background:${c}"></i>${esc(p.name)}</span>
    <span><i class="dash"></i>${esc(p.benchmark)} (benchmark)</span></div>`;

  const hasNav = (p.nav_history||[]).length > 1;
  const chartCard = `<div class="card">
    <h2>Growth of $100</h2>
    <p class="note">Both lines start at zero on day one, so the gap is the only thing that matters.</p>
    ${hasNav ? legend + `<div class="chartbox"><canvas id="equity"></canvas></div>`
             : `<div class="empty">The equity curve appears once there are at least two days of history.<br>It fills in automatically after each daily run.</div>`}
  </div>`;

  let allocCard = "";
  if(hold.length){
    const max = Math.max(...hold.map(h=>h.weight), p.cash_pct);
    const rows = hold.map(h=>`<div class="arow">
        <span class="mono">${esc(h.ticker)}</span>
        <span class="abar"><span style="width:${(h.weight/max*100).toFixed(1)}%;background:${c}"></span></span>
        <span class="mono" style="text-align:right;color:var(--text-secondary)">${(h.weight*100).toFixed(1)}%</span>
      </div>`).join("");
    allocCard = `<div class="card"><h2>Allocation</h2>
      <p class="note">Weight of each position, plus uninvested cash.</p>
      <div class="alloc">${rows}
        <div class="arow"><span class="mono" style="color:var(--text-muted)">CASH</span>
          <span class="abar"><span style="width:${(p.cash_pct/max*100).toFixed(1)}%;background:var(--border-strong)"></span></span>
          <span class="mono" style="text-align:right;color:var(--text-secondary)">${(p.cash_pct*100).toFixed(1)}%</span>
        </div></div></div>`;
  }

  const holdRows = hold.map(h=>`<tr>
      <td><div class="tk"><span class="sw" style="background:${c}"></span>${esc(h.ticker)}${
        h.house_money_taken ? '<span class="pill hm">HOUSE&nbsp;$</span>' : ""}</div></td>
      <td class="mono opt">${h.shares.toLocaleString("en-US",{maximumFractionDigits:2})}</td>
      <td class="mono opt">${money(h.avg_cost)}</td>
      <td class="mono">${h.price==null?"—":money(h.price)}</td>
      <td class="mono">${money0(h.market_value)}</td>
      <td class="mono ${cls(h.unrealized)}">${pct(h.unrealized_pct)}</td>
      <td class="mono ${cls(h.unrealized)}">${money0(h.unrealized)}</td>
      <td class="mono" style="color:var(--text-muted)">${(h.weight*100).toFixed(1)}%</td>
    </tr>`).join("");

  const holdCard = `<div class="card"><h2>Holdings</h2>
    <p class="note">${hold.length ? "Marked at the last close from live market data." :
      "Nothing owned yet."}</p>
    ${hold.length ? `<div class="tblwrap"><table>
      <thead><tr><th>Ticker</th><th class="opt">Shares</th><th class="opt">Avg cost</th>
      <th>Last</th><th>Value</th><th>Return</th><th>P&amp;L</th><th>Weight</th></tr></thead>
      <tbody>${holdRows}</tbody></table></div>`
    : `<div class="empty">No positions yet.<br>Capital is staged in deliberately — cash is a position too.</div>`}
  </div>`;

  const trades = (p.trades||[]).slice().reverse();
  const tradeRows = trades.map(t=>{
    const tags = (t.tags||[]);
    const pills = tags.filter(x=>x!=="AUTO").map(x=>
      `<span class="pill ${x==="OVERRIDE"?"ov":""}">${esc(x)}</span>`).join("");
    return `<div class="trade">
      <span class="tside ${esc(t.action)}">${esc(t.action)}</span>
      <div class="tbody-t">
        <div class="thead-t"><b>${esc(t.ticker)}${pills}</b>
          <span class="mono" style="color:var(--text-muted);font-size:11.5px">${esc(t.date)}</span></div>
        <div class="treason">${esc(t.reason)}</div>
        ${t.override_justification ? `<div class="treason" style="margin-top:5px"><b>Override:</b> ${esc(t.override_justification)}</div>` : ""}
        <div class="tmeta mono">${t.shares.toLocaleString("en-US",{maximumFractionDigits:4})} sh @ ${money(t.price)} = ${money0(t.value)}${t.price_source?" · "+esc(t.price_source):""}</div>
      </div></div>`;
  }).join("");

  const tradeCard = `<div class="card"><h2>Trade log</h2>
    <p class="note">Every fill, with the reason it was made. Nothing is deleted.</p>
    ${trades.length ? tradeRows : `<div class="empty">No trades yet.</div>`}</div>`;

  const ids = [...new Set(hold.map(h=>h.thesis_id).filter(Boolean))];
  const theses = ids.map(id=>{
    const txt = (DATA.theses||{})[String(id).toLowerCase()];
    if(!txt) return "";
    return `<details><summary>${esc(id.toUpperCase())} — why we own it</summary>
      <div class="thesis">${esc(txt)}</div></details>`;
  }).join("");
  const thesisCard = theses ? `<div class="card"><h2>Theses</h2>
    <p class="note">The written case for each position, with every claim's verification status.</p>
    ${theses}</div>` : "";

  document.getElementById("panel").innerHTML =
    banner +
    `<div class="card" style="padding:14px 16px"><h2>${esc(p.name)}</h2>
      <p class="note" style="margin:0">${esc(p.tagline)}</p></div>` +
    tiles + chartCard + allocCard + holdCard + tradeCard + thesisCard;

  renderChart(p);
}

/* ---------- radar ---------- */
function renderRadar(){
  if(chart){ chart.destroy(); chart = null; }
  const wl = DATA.watchlist || {};
  const themes = wl.themes || [];

  const badge = (label, val) => {
    const v = String(val||"").toUpperCase();
    let c = "var(--text-secondary)";
    if(v.startsWith("LOW") || v.startsWith("RISING") || v==="GOOD") c = "var(--good)";
    else if(v.startsWith("HIGH") || v.startsWith("FALLING") || v==="NONE") c = "var(--critical)";
    else if(v==="DILUTED" || v.startsWith("MEDIUM")) c = "var(--warning)";
    return `<div class="rmeta"><span class="k">${esc(label)}</span>
      <span class="v" style="color:${c}">${esc(val||"—")}</span></div>`;
  };

  const cards = themes.map(t=>{
    const st = String(t.status||"").toUpperCase();
    let pill = "watch";
    if(st.startsWith("BOUGHT")) pill = "bought";
    else if(st.startsWith("ACTIONABLE")) pill = "action";
    else if(st.startsWith("REJECTED")) pill = "rej";
    const vehicles = Object.entries(t.vehicles||{})
      .filter(([k])=>!k.startsWith("_"))
      .map(([k,v])=>`<div class="veh"><b>${esc(k)}</b> ${esc(v)}</div>`).join("");
    const todo = (t.vehicles||{})._todo;
    return `<div class="card">
      <div class="rhead">
        <h2 style="margin:0">${esc(t.name)}</h2>
        <span class="spill ${pill}">${esc(t.status||"WATCHING")}</span>
      </div>
      <p class="note" style="margin:8px 0 12px">${esc(t.thesis||"")}</p>
      <div class="rgrid">
        ${badge("Chatter", t.chatter)}
        ${badge("Trajectory", t.trajectory)}
        ${badge("Vehicle", t.vehicle_quality)}
        ${badge("Time to P&L", t.time_to_pnl)}
      </div>
      ${t.capital_committed ? `<div class="rsec"><span class="k">Capital committed</span>
        <div class="rtext">${esc(t.capital_committed)}</div></div>` : ""}
      ${vehicles ? `<div class="rsec"><span class="k">Vehicles</span>${vehicles}</div>` : ""}
      ${todo ? `<div class="rsec"><span class="k">Next</span><div class="rtext">${esc(todo)}</div></div>` : ""}
      ${t.note ? `<details><summary>Full note &amp; verification</summary>
        <div class="thesis">${esc(t.note)}</div></details>` : ""}
    </div>`;
  }).join("");

  const oq = (wl._open_questions||[]).map(x=>`<li>${esc(x)}</li>`).join("");
  const lessons = (wl._lesson_log||[]).map(l=>`<div class="rsec">
      <span class="k">${esc(l.date)} — cost: ${esc(l.cost||"n/a")}</span>
      <div class="rtext">${esc(l.lesson)}</div>
      ${l.fix?`<div class="rtext" style="margin-top:5px"><b>Fix:</b> ${esc(l.fix)}</div>`:""}
    </div>`).join("");

  document.getElementById("panel").innerHTML =
    `<div class="card" style="padding:14px 16px"><h2>Emerging theme radar</h2>
      <p class="note" style="margin:0">Themes with low chatter and rising interest — what I'm hunting,
      before it becomes a trade. Reviewed every two weeks.</p>
      <div class="rgrid" style="margin-top:12px">
        ${badge("Last review", wl._last_review)}
        ${badge("Next review", wl._next_review)}
        ${badge("Tracked", String(themes.length))}
      </div></div>` +
    cards +
    (oq ? `<div class="card"><h2>Open questions</h2>
      <p class="note">Unanswered, carried into the next cycle.</p>
      <ul class="rlist">${oq}</ul></div>` : "") +
    (lessons ? `<div class="card"><h2>Lesson log</h2>
      <p class="note">Mistakes I made and what changed because of them. Kept public on purpose.</p>
      ${lessons}</div>` : "");
}

/* ---------- theme ---------- */
function applyTheme(t){
  if(t==="auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  if(DATA) renderPanel();
}
let themeState = "auto";
document.getElementById("themebtn").onclick = ()=>{
  themeState = themeState==="auto" ? "light" : themeState==="light" ? "dark" : "auto";
  document.getElementById("themebtn").textContent =
    themeState==="auto" ? "Theme" : themeState==="light" ? "Light" : "Dark";
  applyTheme(themeState);
};

if(DATA){ renderHeader(); renderTabs(); renderPanel(); }
else document.getElementById("panel").innerHTML =
  '<div class="card"><div class="empty">No data yet. Run <code>python -m engine.run daily</code>.</div></div>';
</script>
</body>
</html>
"""
