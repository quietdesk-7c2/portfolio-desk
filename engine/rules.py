"""
Risk rules. The part of the system that does not have opinions.

Everything here runs daily, automatically, with zero discretion. The manager
(me) cannot disable, delay, or argue with any of it. That is the entire point:
judgment is useful for choosing what to own and useless for deciding when to
admit you were wrong.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .config import RESEARCH_DIR
from .config import (DRAWDOWN_FULLSTOP, DRAWDOWN_HALT, DRAWDOWN_WARN,
                     MAX_DISCRETIONARY_TRADES_PER_MONTH, MAX_OVERRIDES_PER_MONTH,
                     MIN_PRICE)
from .portfolio import Portfolio


# ==========================================================================
# Automatic actions (IPS 1, 6A, 7)
# ==========================================================================
def check_stops(pf: Portfolio) -> list[dict]:
    """
    Hard stop-loss on closing prices. Core has no stops by design -- its exits
    are thesis-driven, so a drawdown alone never forces a sale there.
    """
    stop = pf.spec.stop_loss_pct
    if stop is None:
        return []
    actions = []
    for ticker, pos in list(pf.positions.items()):
        price = pf.price_of(ticker)
        if price is None or pos["avg_cost"] <= 0:
            continue
        ret = (price - pos["avg_cost"]) / pos["avg_cost"]
        if ret <= stop:
            actions.append({
                "type": "STOP",
                "ticker": ticker,
                "shares": pos["shares"],
                "price": price,
                "reason": (f"STOP-LOSS: {ticker} at {ret:+.1%} vs cost "
                           f"${pos['avg_cost']:.2f}, breaching the {stop:.0%} "
                           f"limit for {pf.spec.name}. Automatic, not discretionary."),
            })
    return actions


def check_house_money(pf: Portfolio) -> list[dict]:
    """
    IPS 6A. At +100%, sell exactly enough to recover the original dollars.
    The rest rides at zero net cost. This is the 'play with house money' rule.
    """
    trigger = pf.spec.house_money_at
    if trigger is None:
        return []
    actions = []
    for ticker, pos in list(pf.positions.items()):
        if pos.get("house_money_taken"):
            continue
        price = pf.price_of(ticker)
        if price is None or pos["avg_cost"] <= 0:
            continue
        ret = (price - pos["avg_cost"]) / pos["avg_cost"]
        if ret < trigger:
            continue
        initial = float(pos.get("initial_cost") or pos["cost_basis"])
        shares_to_sell = round(initial / price, 4)
        if shares_to_sell >= pos["shares"]:
            continue  # would liquidate the whole thing; not the intent
        actions.append({
            "type": "HOUSE_MONEY",
            "ticker": ticker,
            "shares": shares_to_sell,
            "price": price,
            "reason": (f"HOUSE MONEY: {ticker} is {ret:+.0%}. Selling "
                       f"{shares_to_sell} shares to recover the original "
                       f"${initial:,.0f}. Remaining {pos['shares']-shares_to_sell:.4f} "
                       f"shares now ride at zero net cost."),
        })
    return actions


def check_drawdown(pf: Portfolio) -> dict | None:
    """
    IPS 7 circuit breaker. Returns a state change if a threshold was newly
    crossed, else None. Recovery re-arms the breaker one level at a time.
    """
    dd = pf.drawdown()
    current = pf.d.get("status", "active")

    if dd <= DRAWDOWN_FULLSTOP and current != "fullstop":
        return {"status": "fullstop", "drawdown": dd, "level": DRAWDOWN_FULLSTOP,
                "note": (f"{pf.spec.name} is {dd:.1%} below its high-water mark. "
                         "FULL STOP: liquidating to 50% cash. You decide whether "
                         "I keep managing this book.")}

    if dd <= DRAWDOWN_HALT and current == "active":
        return {"status": "halted", "drawdown": dd, "level": DRAWDOWN_HALT,
                "note": (f"{pf.spec.name} is {dd:.1%} below its high-water mark. "
                         "NEW BUYS HALTED. Existing positions held. I owe you a "
                         "written post-mortem before this book buys anything again.")}

    if dd <= DRAWDOWN_WARN and current == "active" and not pf.d.get("warned_15"):
        return {"status": "active", "drawdown": dd, "level": DRAWDOWN_WARN,
                "warn": True,
                "note": (f"{pf.spec.name} is {dd:.1%} below its high-water mark. "
                         "Trading continues. I owe you a written review.")}

    if dd > DRAWDOWN_WARN and current == "active" and pf.d.get("warned_15"):
        pf.d["warned_15"] = False

    return None


def check_concentration(pf: Portfolio) -> list[dict]:
    """
    A winner that grows past the hard ceiling gets trimmed back to the soft
    target. Not a punishment for winning -- just a cap on single-name blowup risk.
    """
    eq = pf.equity()
    if eq <= 0:
        return []
    actions = []
    for ticker in list(pf.positions):
        weight = pf.position_value(ticker) / eq
        if weight <= pf.spec.max_position_pct_hard:
            continue
        price = pf.price_of(ticker)
        if price is None:
            continue
        target_value = pf.spec.max_position_pct * eq
        excess = pf.position_value(ticker) - target_value
        shares = round(excess / price, 4)
        if shares <= 0:
            continue
        actions.append({
            "type": "TRIM",
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "reason": (f"CONCENTRATION TRIM: {ticker} grew to {weight:.1%} of "
                       f"{pf.spec.name}, above the {pf.spec.max_position_pct_hard:.0%} "
                       f"ceiling. Trimming back to {pf.spec.max_position_pct:.0%}."),
        })
    return actions


# ==========================================================================
# Valuation gate (IPS 3a)
# ==========================================================================
VALUATION_PATH = os.path.join(RESEARCH_DIR, "valuation.json")

MIN_CONSENSUS_UPSIDE = 0.15      # implied upside to consensus target
MAX_GROWTH_ADJ_MULTIPLE = 2.0    # forward P/E divided by growth rate


def _load_valuations() -> dict:
    try:
        with open(VALUATION_PATH) as fh:
            return json.load(fh).get("tickers", {})
    except Exception:
        return {}


def check_valuation(ticker: str, tags: list[str]) -> list[str]:
    """
    A great company at a fully-priced multiple is not a great investment.

    Every new BUY must carry a valuation record whose gate reads PASS, N/A
    (index funds), or MOONSHOT-PENDING (unprofitable names, which the Moonshot
    screen governs instead). Anything else blocks unless explicitly overridden
    with a written justification.
    """
    vals = _load_valuations()
    entry = vals.get(ticker.upper())

    if entry is None:
        return [f"{ticker}: no valuation record in research/valuation.json. "
                f"Every position must be checked against what is already priced "
                f"in before it is bought (IPS 3a)"]

    gate = str(entry.get("gate", "")).upper()
    if gate in ("PASS", "N/A", "MOONSHOT-CLEARED"):
        # MOONSHOT-CLEARED: a pre-profit company has no P/E, so the valuation
        # gate cannot apply. Those names are governed by the Moonshot screen in
        # IPS 1 instead, and this status means that screen has been satisfied.
        return []
    if gate == "MOONSHOT-PENDING":
        return [f"{ticker}: flagged MOONSHOT-PENDING -- not yet cleared by the "
                f"Moonshot screen (IPS 1). Not buyable until it is."]
    if gate == "PENDING":
        return [f"{ticker}: valuation verification still PENDING. "
                f"'Probably fine' is not a verification (IPS 3a)"]

    reasons = []
    upside = entry.get("upside")
    if upside is not None and upside < MIN_CONSENSUS_UPSIDE:
        reasons.append(f"only {upside:.1%} implied upside vs the "
                       f"{MIN_CONSENSUS_UPSIDE:.0%} floor")
    ga = entry.get("ga_multiple")
    if ga is not None and ga > MAX_GROWTH_ADJ_MULTIPLE:
        reasons.append(f"growth-adjusted multiple {ga:.2f} vs the "
                       f"{MAX_GROWTH_ADJ_MULTIPLE:.1f} limit")
    fpe, tpe = entry.get("forward_pe"), entry.get("pe")
    if fpe and tpe and fpe > tpe:
        reasons.append(f"forward P/E {fpe:.1f} above trailing {tpe:.1f} "
                       f"(consensus expects earnings to FALL)")

    detail = "; ".join(reasons) if reasons else "gate marked FAIL"
    return [f"{ticker}: FAILS the valuation gate -- {detail}. "
            f"The good news is already in the price (IPS 3a)"]


# ==========================================================================
# Order validation (IPS 3, 5, 8) -- gates every discretionary trade
# ==========================================================================
# Tags that do not count as discretionary turnover.
#   AUTO      -- the engine's own rule executions (stops, house money, trims)
#   INCEPTION -- building the initial book is not turnover. This exemption is
#                available ONCE per portfolio, on its first deployment, and the
#                engine enforces that: see inception_used().
NON_TURNOVER_TAGS = ("AUTO", "INCEPTION")


def _is_turnover(trade: dict) -> bool:
    return not any(tag in trade.get("tags", []) for tag in NON_TURNOVER_TAGS)


def inception_used(pf: Portfolio) -> bool:
    """
    True once this book has already spent its one INCEPTION deployment.

    A deployment is a single DAY, not a single trade -- building a book takes
    a dozen orders and they all land together. So the exemption stays open for
    every order dated the same day as the first one, and closes permanently
    the moment a later date shows up.
    """
    dates = {t.get("date") for t in pf.d["trades"] if "INCEPTION" in t.get("tags", [])}
    dates.discard(None)
    if not dates:
        return False
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return any(d != today for d in dates)


def trades_this_month(portfolios: dict[str, Portfolio]) -> int:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    n = 0
    for pf in portfolios.values():
        for t in pf.d["trades"]:
            if t.get("date", "").startswith(month) and _is_turnover(t):
                n += 1
    return n


def overrides_this_month(portfolios: dict[str, Portfolio]) -> int:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    n = 0
    for pf in portfolios.values():
        for t in pf.d["trades"]:
            if t.get("date", "").startswith(month) and "OVERRIDE" in t.get("tags", []):
                n += 1
    return n


def validate_order(order: dict, pf: Portfolio, price: float,
                   portfolios: dict[str, Portfolio]) -> list[str]:
    """Return a list of blocking problems. Empty list means the order is legal."""
    problems: list[str] = []
    action = order.get("action", "").upper()
    ticker = order.get("ticker", "").upper()
    tags = order.get("tags", [])
    is_auto = "AUTO" in tags
    is_inception = "INCEPTION" in tags

    # The inception exemption is single-use per book. After the first deployment
    # it is dead, so it can never become a back door around the turnover cap.
    if is_inception and inception_used(pf):
        problems.append(
            f"{ticker}: {pf.spec.name} has already used its one INCEPTION "
            f"deployment. This trade counts as normal turnover (IPS 2)")
        tags = [t for t in tags if t != "INCEPTION"]
        is_inception = False

    # --- hard prohibitions (IPS 8) ---
    if price is not None and price < MIN_PRICE:
        problems.append(f"{ticker}: price ${price:.2f} is below the ${MIN_PRICE:.2f} floor (IPS 8)")

    if not order.get("reason"):
        problems.append(f"{ticker}: no written reason. Every trade needs one (IPS 8)")

    if action == "BUY" and not is_auto:
        # Valuation gate runs FIRST -- before sizing, before cash, before
        # anything. If the good news is already priced in, nothing else matters.
        if "OVERRIDE" not in tags:
            problems.extend(check_valuation(ticker, tags))

        if not order.get("thesis_id"):
            problems.append(f"{ticker}: no thesis_id. No position without a written thesis (IPS 8)")

        # circuit breaker
        if pf.d.get("status") in ("halted", "fullstop"):
            problems.append(
                f"{pf.spec.name}: buys are HALTED by the drawdown breaker "
                f"(status={pf.d['status']}). Post-mortem required first (IPS 7)")

        eq = pf.equity()
        dollars = float(order.get("dollars") or 0)

        # position sizing ceiling
        existing = pf.position_value(ticker)
        new_weight = (existing + dollars) / eq if eq else 1.0
        if new_weight > pf.spec.max_position_pct + 1e-6:
            problems.append(
                f"{ticker}: would be {new_weight:.1%} of {pf.spec.name}, above the "
                f"{pf.spec.max_position_pct:.0%} cap at cost (IPS 1, hard rule)")

        # cash floor
        cash_after = pf.cash - dollars
        if eq and (cash_after / eq) < pf.spec.min_cash_pct - 1e-6:
            problems.append(
                f"{ticker}: would leave {cash_after/eq:.1%} cash, below the "
                f"{pf.spec.min_cash_pct:.0%} floor for {pf.spec.name} (IPS 1, hard rule)")

        if dollars > pf.cash:
            problems.append(
                f"{ticker}: needs ${dollars:,.0f} but {pf.spec.name} holds "
                f"${pf.cash:,.0f} cash")

        # holdings count
        if ticker not in pf.positions and len(pf.positions) >= pf.spec.target_holdings[1]:
            if "OVERRIDE" not in tags:
                problems.append(
                    f"{ticker}: {pf.spec.name} already holds {len(pf.positions)} names, "
                    f"at the {pf.spec.target_holdings[1]} target ceiling. Tag OVERRIDE "
                    f"with a justification, or close something first (IPS 5, soft rule)")

    if action == "SELL" and ticker not in pf.positions:
        problems.append(f"{ticker}: no position to sell in {pf.spec.name}")

    # --- turnover + override budgets (IPS 2, 5) ---
    if not is_auto and not is_inception:
        if trades_this_month(portfolios) >= MAX_DISCRETIONARY_TRADES_PER_MONTH:
            problems.append(
                f"Monthly turnover cap reached "
                f"({MAX_DISCRETIONARY_TRADES_PER_MONTH} discretionary trades). "
                f"No more until next month (IPS 2, hard rule)")
        if "OVERRIDE" in tags:
            if overrides_this_month(portfolios) >= MAX_OVERRIDES_PER_MONTH:
                problems.append(
                    f"Override budget exhausted ({MAX_OVERRIDES_PER_MONTH}/month) (IPS 5)")
            if not order.get("override_justification"):
                problems.append(
                    f"{ticker}: OVERRIDE tag requires override_justification "
                    f"explaining what I see that the rule doesn't (IPS 5)")

    return problems
