"""
Configuration for the three-portfolio paper trading desk.

Everything in this file is the machine-readable form of IPS.md.
If you change a number here, change it in IPS.md too, or the audit trail lies.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(ROOT, "state")
HISTORY_DIR = os.path.join(STATE_DIR, "history")
ORDERS_DIR = os.path.join(ROOT, "orders")
DOCS_DIR = os.path.join(ROOT, "docs")
RESEARCH_DIR = os.path.join(ROOT, "research")

INCEPTION = "2026-08-14"

# --------------------------------------------------------------------------
# Secrets / env  (all optional -- the system degrades gracefully without them)
# --------------------------------------------------------------------------
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_KEY", "")
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")


# --------------------------------------------------------------------------
# Portfolio definitions
# --------------------------------------------------------------------------
@dataclass
class PortfolioSpec:
    key: str
    name: str
    tagline: str
    starting_cash: float

    # sizing
    max_position_pct: float          # of book value, at cost
    max_position_pct_hard: float     # ceiling after appreciation before forced trim
    min_cash_pct: float
    target_holdings: tuple[int, int]

    # risk
    stop_loss_pct: float | None      # None = thesis-driven exits only
    house_money_at: float | None     # gain multiple that triggers cost recovery

    # benchmarks
    benchmark: str
    benchmark_secondary: str

    color: str = "#4c8dff"


PORTFOLIOS: dict[str, PortfolioSpec] = {
    "core": PortfolioSpec(
        key="core",
        name="Core",
        tagline="Diversified stocks + ETFs. Built to beat the S&P and look boring doing it.",
        starting_cash=100_000.0,
        max_position_pct=0.08,
        max_position_pct_hard=0.12,
        min_cash_pct=0.05,
        target_holdings=(18, 25),
        stop_loss_pct=None,          # IPS 1: no price stops in Core
        house_money_at=None,         # Core compounds untouched
        benchmark="SPY",
        benchmark_secondary="QQQ",
        color="#2a78d6",   # validated categorical slot 1 (blue)
    ),
    "moonshot": PortfolioSpec(
        key="moonshot",
        name="Moonshot",
        tagline="Asymmetric upside. High credible price targets + accelerating customer sentiment.",
        starting_cash=100_000.0,
        max_position_pct=0.10,
        max_position_pct_hard=0.18,
        min_cash_pct=0.10,
        target_holdings=(10, 14),
        stop_loss_pct=-0.25,
        house_money_at=1.00,         # +100% -> recover cost basis
        benchmark="ARKK",
        benchmark_secondary="IWO",
        color="#eb6834",   # validated categorical slot 2 (orange)
    ),
    "ai": PortfolioSpec(
        key="ai",
        name="AI Trade",
        tagline="The whole AI stack: semis, networking, power, hyperscale, apps.",
        starting_cash=100_000.0,
        max_position_pct=0.12,
        max_position_pct_hard=0.20,
        min_cash_pct=0.05,
        target_holdings=(12, 18),
        stop_loss_pct=-0.20,
        house_money_at=1.00,
        benchmark="SOXX",
        benchmark_secondary="QQQ",
        color="#1baf7a",   # validated categorical slot 3 (aqua)
    ),
}

# --------------------------------------------------------------------------
# Desk-wide rules (IPS sections 2, 5, 7, 8)
# --------------------------------------------------------------------------
MAX_DISCRETIONARY_TRADES_PER_MONTH = 8     # across all books combined
MAX_OVERRIDES_PER_MONTH = 2

DRAWDOWN_WARN = -0.15
DRAWDOWN_HALT = -0.25
DRAWDOWN_FULLSTOP = -0.35

# Prohibitions (IPS 8) -- enforced in rules.check_prohibitions
MIN_PRICE = 1.00
MIN_MARKET_CAP = 150_000_000
MIN_AVG_DOLLAR_VOLUME = 2_000_000

# Execution modelling: paper fills are not free.
# Applied as a haircut against the fill price so the track record isn't fantasy.
SLIPPAGE_BPS = 5          # 0.05% adverse on every fill
COMMISSION_PER_TRADE = 0.0

# Benchmarks we always fetch so the charts have comparison lines
ALL_BENCHMARKS = ["SPY", "QQQ", "ARKK", "IWO", "SOXX", "AGG"]


def portfolio_keys() -> list[str]:
    return list(PORTFOLIOS.keys())
