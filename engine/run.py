"""
Entry points.

    python -m engine.run selftest    # which data sources are alive right now
    python -m engine.run init        # create blank state for all three books
    python -m engine.run execute     # process orders/pending.json
    python -m engine.run daily       # mark, enforce rules, publish, notify
    python -m engine.run report      # rebuild the dashboard only

`daily` is what the scheduler runs. It is safe to run repeatedly -- marking and
history are idempotent, and automatic rule actions only fire once per condition.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone

from . import notify
from .config import ALL_BENCHMARKS, ORDERS_DIR, PORTFOLIOS, RESEARCH_DIR
from .data import (PriceUnavailable, get_previous_close, get_quotes,
                   selftest as data_selftest)
from .portfolio import Portfolio, load_all
from .rules import (check_concentration, check_drawdown, check_house_money,
                    check_stops, validate_order)

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")
PENDING = os.path.join(ORDERS_DIR, "pending.json")
EXECUTED_DIR = os.path.join(ORDERS_DIR, "executed")


def _log(msg: str = "") -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------
def cmd_init() -> None:
    for key in PORTFOLIOS:
        pf = Portfolio.load(key)
        pf.save()
        _log(f"  initialised {key}: ${pf.cash:,.0f} cash")
    _log("\nState files written to state/. Nothing is invested yet.")


# --------------------------------------------------------------------------
def _all_tickers(pfs: dict[str, Portfolio]) -> list[str]:
    tickers = set(ALL_BENCHMARKS)
    for pf in pfs.values():
        tickers.update(pf.positions.keys())
    return sorted(tickers)


def cmd_execute() -> None:
    """Process orders/pending.json. This is how discretionary trades get in."""
    if not os.path.exists(PENDING):
        _log("No orders/pending.json. Nothing to execute.")
        return

    with open(PENDING) as fh:
        payload = json.load(fh)
    orders = payload.get("orders", [])
    if not orders:
        _log("orders/pending.json contains no orders.")
        return

    pfs = load_all()
    tickers = sorted({o["ticker"].upper() for o in orders} | set(_all_tickers(pfs)))
    _log(f"Fetching prices for {len(tickers)} symbols...")
    quotes = get_quotes(tickers)
    for pf in pfs.values():
        pf.mark(quotes)

    executed, rejected = [], []
    for order in orders:
        key = order["portfolio"]
        pf = pfs[key]
        ticker = order["ticker"].upper()
        q = quotes.get(ticker)
        if not q:
            rejected.append({"order": order, "problems": [
                f"{ticker}: no price from any data source. Refusing to trade "
                f"at an invented price (IPS 8)."]})
            continue
        price = q["price"]

        problems = validate_order(order, pf, price, pfs)
        if problems:
            rejected.append({"order": order, "problems": problems})
            continue

        try:
            if order["action"].upper() == "BUY":
                rec = pf.buy(ticker, float(order["dollars"]), price,
                             reason=order["reason"], thesis_id=order.get("thesis_id", ""),
                             tags=order.get("tags", []), source=q["source"])
            else:
                shares = order.get("shares")
                if shares in (None, "ALL", "all"):
                    shares = pf.positions[ticker]["shares"]
                elif order.get("dollars"):
                    shares = float(order["dollars"]) / price
                rec = pf.sell(ticker, float(shares), price,
                              reason=order["reason"], thesis_id=order.get("thesis_id", ""),
                              tags=order.get("tags", []), source=q["source"])
        except ValueError as exc:
            rejected.append({"order": order, "problems": [str(exc)]})
            continue

        if order.get("override_justification"):
            rec["override_justification"] = order["override_justification"]
        executed.append(rec)
        _log(f"  {rec['action']:<4} {rec['ticker']:<6} {rec['shares']:>10,.4g} sh "
             f"@ ${rec['price']:>9,.2f} = ${rec['value']:>10,.2f}  [{pf.spec.name}]")

    for pf in pfs.values():
        pf.update_high_water()
        pf.save()

    for rec in executed:
        notify.trade(rec, pfs[rec["portfolio"]].equity(), DASHBOARD_URL)

    if rejected:
        _log("\nREJECTED ORDERS:")
        for r in rejected:
            o = r["order"]
            _log(f"  {o.get('action')} {o.get('ticker')} [{o.get('portfolio')}]")
            for p in r["problems"]:
                _log(f"      - {p}")

    # archive
    os.makedirs(EXECUTED_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    payload["executed"] = executed
    payload["rejected"] = rejected
    with open(os.path.join(EXECUTED_DIR, f"{stamp}.json"), "w") as fh:
        json.dump(payload, fh, indent=2)
    os.remove(PENDING)

    _log(f"\n{len(executed)} executed, {len(rejected)} rejected. "
         f"Archived to orders/executed/{stamp}.json")
    cmd_daily(skip_execute_check=True)


# --------------------------------------------------------------------------
def cmd_daily(skip_execute_check: bool = False) -> None:
    """Mark to market, run the automatic rules, publish, notify."""
    if not skip_execute_check and os.path.exists(PENDING):
        _log("Pending orders found -- executing those first.\n")
        cmd_execute()
        return

    pfs = load_all()
    tickers = _all_tickers(pfs)
    _log(f"Marking {len(tickers)} symbols...")
    quotes = get_quotes(tickers)
    if not quotes:
        _log("! No prices from any source. Aborting rather than writing bad marks.")
        sys.exit(1)

    for pf in pfs.values():
        pf.mark(quotes)

    # Seed a previous close for anything that has never had one. Costs one
    # history fetch per ticker, once ever -- after that mark() rolls it forward.
    needs_prev = sorted({t for pf in pfs.values() for t in pf.positions
                         if pf.prev_price_of(t) is None})
    if needs_prev:
        _log(f"Seeding previous close for {len(needs_prev)} symbol(s)...")
        for t in needs_prev:
            try:
                res = get_previous_close(t)
            except Exception:
                res = None
            if res:
                for pf in pfs.values():
                    if t in pf.positions:
                        pf.set_previous_close(t, res[0], res[1])

    auto_trades = []
    for pf in pfs.values():
        actions = (check_stops(pf) + check_house_money(pf) + check_concentration(pf))
        for a in actions:
            tags = ["AUTO", a["type"]]
            try:
                rec = pf.sell(a["ticker"], a["shares"], a["price"],
                              reason=a["reason"], tags=tags,
                              source=(quotes.get(a["ticker"]) or {}).get("source", ""))
            except ValueError as exc:
                _log(f"  ! auto-action failed: {exc}")
                continue
            if a["type"] == "HOUSE_MONEY" and a["ticker"] in pf.positions:
                pf.positions[a["ticker"]]["house_money_taken"] = True
            auto_trades.append(rec)
            _log(f"  AUTO {a['type']}: {a['ticker']} ({pf.spec.name})")

    # circuit breaker
    breaker_events = []
    for pf in pfs.values():
        event = check_drawdown(pf)
        if not event:
            continue
        if event.get("warn"):
            pf.d["warned_15"] = True
        else:
            pf.d["status"] = event["status"]
            pf.d["status_note"] = event["note"]
        breaker_events.append((pf.spec.key, event["note"]))
        _log(f"  ! BREAKER {pf.spec.key}: {event['note']}")

    for pf in pfs.values():
        pf.update_high_water()
        pf.append_history()
        pf.save()

    for rec in auto_trades:
        notify.trade(rec, pfs[rec["portfolio"]].equity(), DASHBOARD_URL)
    for key, note in breaker_events:
        notify.breaker(key, note, DASHBOARD_URL)

    from .report import build
    build(pfs, quotes)

    _log("\n" + "=" * 62)
    for pf in pfs.values():
        _log(f"  {pf.spec.name:<10} ${pf.equity():>12,.2f}  "
             f"{pf.total_return():>+7.2%}  cash {pf.cash_pct():>5.1%}  "
             f"{len(pf.positions):>2} names  [{pf.d.get('status')}]")
    total = sum(p.equity() for p in pfs.values())
    start = sum(p.d["starting_cash"] for p in pfs.values())
    _log("-" * 62)
    _log(f"  {'TOTAL':<10} ${total:>12,.2f}  {(total-start)/start:>+7.2%}")
    _log("=" * 62)


# --------------------------------------------------------------------------
def cmd_report() -> None:
    pfs = load_all()
    quotes = get_quotes(_all_tickers(pfs))
    for pf in pfs.values():
        pf.mark(quotes)
    from .report import build
    build(pfs, quotes)


def main() -> None:
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "daily").lower()
    os.makedirs(ORDERS_DIR, exist_ok=True)
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    if cmd == "selftest":
        data_selftest()
    elif cmd == "init":
        cmd_init()
    elif cmd == "execute":
        cmd_execute()
    elif cmd == "report":
        cmd_report()
    elif cmd == "daily":
        cmd_daily()
    else:
        _log(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
