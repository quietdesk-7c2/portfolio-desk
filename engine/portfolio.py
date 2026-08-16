"""
Portfolio state and trade execution.

State lives in plain JSON in state/. That is deliberate: you can open it in any
text editor, and every change is a git diff. There is no database to trust.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .config import (COMMISSION_PER_TRADE, HISTORY_DIR, INCEPTION, PORTFOLIOS,
                     SLIPPAGE_BPS, STATE_DIR, PortfolioSpec)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Portfolio:
    def __init__(self, spec: PortfolioSpec, data: dict):
        self.spec = spec
        self.d = data

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    @staticmethod
    def path(key: str) -> str:
        return os.path.join(STATE_DIR, f"{key}.json")

    @classmethod
    def load(cls, key: str) -> "Portfolio":
        spec = PORTFOLIOS[key]
        p = cls.path(key)
        if os.path.exists(p):
            with open(p) as fh:
                return cls(spec, json.load(fh))
        return cls(spec, cls._blank(spec))

    @staticmethod
    def _blank(spec: PortfolioSpec) -> dict:
        return {
            "key": spec.key,
            "name": spec.name,
            "inception": INCEPTION,
            "starting_cash": spec.starting_cash,
            "cash": spec.starting_cash,
            "positions": {},        # ticker -> position dict
            "closed": [],           # fully exited positions, for the record
            "trades": [],           # append-only execution log
            "high_water": spec.starting_cash,
            "status": "active",     # active | halted | fullstop
            "status_note": "",
            "last_marked": None,
            "marks": {},            # ticker -> {price, asof, source}
        }

    def save(self) -> None:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = self.path(self.spec.key) + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.d, fh, indent=2, sort_keys=False)
        os.replace(tmp, self.path(self.spec.key))

    # ------------------------------------------------------------------
    # valuation
    # ------------------------------------------------------------------
    @property
    def cash(self) -> float:
        return float(self.d["cash"])

    @property
    def positions(self) -> dict:
        return self.d["positions"]

    def mark(self, quotes: dict[str, dict]) -> None:
        """Attach latest prices. Positions without a quote keep their last mark."""
        for ticker in self.positions:
            q = quotes.get(ticker)
            if q:
                self.d["marks"][ticker] = {
                    "price": q["price"], "asof": q["asof"], "source": q["source"],
                }
        self.d["last_marked"] = _now()

    def price_of(self, ticker: str) -> float | None:
        m = self.d["marks"].get(ticker)
        return float(m["price"]) if m else None

    def position_value(self, ticker: str) -> float:
        pos = self.positions.get(ticker)
        price = self.price_of(ticker)
        if not pos or price is None:
            return 0.0
        return pos["shares"] * price

    def equity(self) -> float:
        """Total book value: cash + all positions marked to market."""
        return self.cash + sum(self.position_value(t) for t in self.positions)

    def invested(self) -> float:
        return sum(self.position_value(t) for t in self.positions)

    def cash_pct(self) -> float:
        eq = self.equity()
        return self.cash / eq if eq else 1.0

    def total_return(self) -> float:
        start = float(self.d["starting_cash"])
        return (self.equity() - start) / start if start else 0.0

    def realized_pnl(self) -> float:
        return sum(c.get("realized", 0.0) for c in self.d["closed"]) + sum(
            p.get("realized", 0.0) for p in self.positions.values())

    def unrealized_pnl(self) -> float:
        total = 0.0
        for t, pos in self.positions.items():
            price = self.price_of(t)
            if price is not None:
                total += pos["shares"] * price - pos["cost_basis"]
        return total

    def drawdown(self) -> float:
        hw = float(self.d.get("high_water") or self.d["starting_cash"])
        eq = self.equity()
        return (eq - hw) / hw if hw else 0.0

    def update_high_water(self) -> None:
        eq = self.equity()
        if eq > float(self.d.get("high_water") or 0):
            self.d["high_water"] = eq

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------
    @staticmethod
    def _fill_price(price: float, side: str) -> float:
        """Adverse slippage on both sides. Paper fills should not be free."""
        adj = SLIPPAGE_BPS / 10_000.0
        return price * (1 + adj) if side == "buy" else price * (1 - adj)

    def buy(self, ticker: str, dollars: float, price: float, *,
            reason: str, thesis_id: str = "", tags: list[str] | None = None,
            source: str = "") -> dict:
        ticker = ticker.upper()
        fill = self._fill_price(price, "buy")
        shares = round(dollars / fill, 4)
        cost = shares * fill + COMMISSION_PER_TRADE
        if cost > self.cash + 1e-6:
            raise ValueError(
                f"{self.spec.key}: buy {ticker} needs ${cost:,.2f} but cash is ${self.cash:,.2f}")

        pos = self.positions.get(ticker)
        if pos:
            pos["shares"] = round(pos["shares"] + shares, 4)
            pos["cost_basis"] = round(pos["cost_basis"] + shares * fill, 2)
            pos["avg_cost"] = round(pos["cost_basis"] / pos["shares"], 4)
            pos.setdefault("adds", []).append({"date": _today(), "shares": shares, "price": fill})
        else:
            self.positions[ticker] = {
                "ticker": ticker,
                "shares": shares,
                "cost_basis": round(shares * fill, 2),
                "avg_cost": round(fill, 4),
                "opened": _today(),
                "thesis_id": thesis_id or ticker.lower(),
                "house_money_taken": False,
                "realized": 0.0,
                "initial_cost": round(shares * fill, 2),
            }

        self.d["cash"] = round(self.cash - cost, 2)
        return self._log("BUY", ticker, shares, fill, reason, thesis_id, tags, source)

    def sell(self, ticker: str, shares: float, price: float, *,
             reason: str, thesis_id: str = "", tags: list[str] | None = None,
             source: str = "") -> dict:
        ticker = ticker.upper()
        pos = self.positions.get(ticker)
        if not pos:
            raise ValueError(f"{self.spec.key}: no position in {ticker}")
        shares = min(round(float(shares), 4), pos["shares"])
        fill = self._fill_price(price, "sell")
        proceeds = shares * fill - COMMISSION_PER_TRADE

        cost_out = pos["avg_cost"] * shares
        pos["realized"] = round(pos.get("realized", 0.0) + (proceeds - cost_out), 2)
        pos["shares"] = round(pos["shares"] - shares, 4)
        pos["cost_basis"] = round(max(pos["cost_basis"] - cost_out, 0.0), 2)
        self.d["cash"] = round(self.cash + proceeds, 2)

        if pos["shares"] <= 1e-6:
            closed = dict(pos)
            closed["closed"] = _today()
            closed["close_reason"] = reason
            self.d["closed"].append(closed)
            del self.positions[ticker]
            self.d["marks"].pop(ticker, None)

        return self._log("SELL", ticker, shares, fill, reason, thesis_id, tags, source)

    def _log(self, action, ticker, shares, price, reason, thesis_id, tags, source) -> dict:
        rec = {
            "id": f"{self.spec.key}-{len(self.d['trades'])+1:04d}",
            "ts": _now(),
            "date": _today(),
            "portfolio": self.spec.key,
            "action": action,
            "ticker": ticker,
            "shares": round(shares, 4),
            "price": round(price, 4),
            "value": round(shares * price, 2),
            "reason": reason,
            "thesis_id": thesis_id,
            "tags": tags or [],
            "price_source": source,
        }
        self.d["trades"].append(rec)
        return rec

    # ------------------------------------------------------------------
    # reporting helpers
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        eq = self.equity()
        rows = []
        for t, pos in sorted(self.positions.items()):
            price = self.price_of(t)
            mv = self.position_value(t)
            cost = pos["cost_basis"]
            rows.append({
                "ticker": t,
                "shares": pos["shares"],
                "avg_cost": pos["avg_cost"],
                "price": price,
                "market_value": round(mv, 2),
                "cost_basis": round(cost, 2),
                "unrealized": round(mv - cost, 2),
                "unrealized_pct": round((mv - cost) / cost, 4) if cost else 0.0,
                "weight": round(mv / eq, 4) if eq else 0.0,
                "opened": pos.get("opened"),
                "thesis_id": pos.get("thesis_id"),
                "house_money_taken": pos.get("house_money_taken", False),
                "realized": pos.get("realized", 0.0),
                "mark_source": (self.d["marks"].get(t) or {}).get("source", ""),
                "mark_asof": (self.d["marks"].get(t) or {}).get("asof", ""),
            })
        rows.sort(key=lambda r: r["market_value"], reverse=True)
        return {
            "key": self.spec.key,
            "name": self.spec.name,
            "tagline": self.spec.tagline,
            "color": self.spec.color,
            "benchmark": self.spec.benchmark,
            "benchmark_secondary": self.spec.benchmark_secondary,
            "status": self.d.get("status", "active"),
            "status_note": self.d.get("status_note", ""),
            "inception": self.d["inception"],
            "starting_cash": self.d["starting_cash"],
            "cash": round(self.cash, 2),
            "cash_pct": round(self.cash_pct(), 4),
            "equity": round(eq, 2),
            "invested": round(self.invested(), 2),
            "total_return": round(self.total_return(), 4),
            "realized_pnl": round(self.realized_pnl(), 2),
            "unrealized_pnl": round(self.unrealized_pnl(), 2),
            "high_water": round(float(self.d.get("high_water") or 0), 2),
            "drawdown": round(self.drawdown(), 4),
            "holdings": rows,
            "n_holdings": len(rows),
            "closed": self.d["closed"][-25:],
            "trades": self.d["trades"][-100:],
            "last_marked": self.d.get("last_marked"),
        }

    def append_history(self) -> None:
        """One NAV row per day per portfolio. This is the equity curve."""
        os.makedirs(HISTORY_DIR, exist_ok=True)
        path = os.path.join(HISTORY_DIR, f"{self.spec.key}.csv")
        today = _today()
        rows = []
        if os.path.exists(path):
            with open(path) as fh:
                rows = [l.rstrip("\n") for l in fh if l.strip()]
        # replace today's row if it already exists (idempotent re-runs)
        rows = [r for r in rows if not r.startswith(today + ",")]
        if not rows or not rows[0].startswith("date,"):
            rows.insert(0, "date,equity,cash,invested,drawdown")
        rows.append(f"{today},{self.equity():.2f},{self.cash:.2f},"
                    f"{self.invested():.2f},{self.drawdown():.6f}")
        header, body = rows[0], sorted(r for r in rows[1:] if not r.startswith("date,"))
        with open(path, "w") as fh:
            fh.write("\n".join([header] + body) + "\n")


def load_all() -> dict[str, Portfolio]:
    return {k: Portfolio.load(k) for k in PORTFOLIOS}
