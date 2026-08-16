"""
Market data with a fallback chain.

Free data sources break. All of them, eventually. So we never depend on one:
we try sources in order and use the first that answers with something sane.

Order for quotes:      Stooq (no key) -> yfinance -> Finnhub -> Alpha Vantage
Order for history:     Stooq (no key) -> yfinance -> Alpha Vantage

Every price we use is stamped with which source produced it, and that stamp goes
into the state file. If the track record is ever questioned, you can see exactly
where each mark came from.
"""
from __future__ import annotations

import csv
import io
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from .config import ALPHAVANTAGE_KEY, FINNHUB_KEY, STATE_DIR

UA = "Mozilla/5.0 (compatible; paper-portfolio/1.0)"
CACHE_PATH = os.path.join(STATE_DIR, "price_cache.json")
CACHE_TTL_SECONDS = 60 * 45


class PriceUnavailable(Exception):
    """Raised when every source failed. Callers must NOT invent a price."""


# --------------------------------------------------------------------------
# tiny disk cache so we don't hammer free tiers
# --------------------------------------------------------------------------
def _load_cache() -> dict:
    try:
        with open(CACHE_PATH) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cache, fh)
    os.replace(tmp, CACHE_PATH)


def _http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# source: Stooq  (no API key, generous, EOD + delayed intraday)
# --------------------------------------------------------------------------
def _stooq_symbol(ticker: str) -> str:
    return f"{ticker.lower().replace('.', '-')}.us"


def _quote_stooq(ticker: str) -> tuple[float, str] | None:
    url = f"https://stooq.com/q/l/?s={_stooq_symbol(ticker)}&f=sd2t2ohlcv&h&e=csv"
    try:
        text = _http_get(url)
    except Exception:
        return None
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return None
    close = rows[0].get("Close")
    date = rows[0].get("Date", "")
    if not close or close in ("N/D", ""):
        return None
    try:
        return float(close), date
    except ValueError:
        return None


def _history_stooq(ticker: str) -> list[tuple[str, float]] | None:
    url = f"https://stooq.com/q/d/l/?s={_stooq_symbol(ticker)}&i=d"
    try:
        text = _http_get(url)
    except Exception:
        return None
    rows = list(csv.DictReader(io.StringIO(text)))
    out = []
    for r in rows:
        try:
            out.append((r["Date"], float(r["Close"])))
        except (KeyError, ValueError, TypeError):
            continue
    return out or None


# --------------------------------------------------------------------------
# source: yfinance  (unofficial; flaky in 2026 but still often works)
# --------------------------------------------------------------------------
def _quote_yfinance(ticker: str) -> tuple[float, str] | None:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        hist = yf.Ticker(ticker).history(period="5d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        last = hist.iloc[-1]
        date = hist.index[-1].strftime("%Y-%m-%d")
        return float(last["Close"]), date
    except Exception:
        return None


def _history_yfinance(ticker: str, period: str = "2y") -> list[tuple[str, float]] | None:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=False)
        if hist is None or hist.empty:
            return None
        return [(idx.strftime("%Y-%m-%d"), float(row["Close"])) for idx, row in hist.iterrows()]
    except Exception:
        return None


# --------------------------------------------------------------------------
# source: Finnhub  (free key, 60/min)
# --------------------------------------------------------------------------
def _quote_finnhub(ticker: str) -> tuple[float, str] | None:
    if not FINNHUB_KEY:
        return None
    url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_KEY}"
    try:
        data = json.loads(_http_get(url))
    except Exception:
        return None
    price = data.get("c")
    if not price:
        return None
    ts = data.get("t") or time.time()
    date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    return float(price), date


# --------------------------------------------------------------------------
# source: Alpha Vantage  (free key, 5/min -- last resort, it is slow)
# --------------------------------------------------------------------------
def _quote_alphavantage(ticker: str) -> tuple[float, str] | None:
    if not ALPHAVANTAGE_KEY:
        return None
    url = ("https://www.alphavantage.co/query?function=GLOBAL_QUOTE"
           f"&symbol={ticker}&apikey={ALPHAVANTAGE_KEY}")
    try:
        data = json.loads(_http_get(url)).get("Global Quote", {})
    except Exception:
        return None
    price = data.get("05. price")
    date = data.get("07. latest trading day", "")
    if not price:
        return None
    try:
        return float(price), date
    except ValueError:
        return None


def _history_alphavantage(ticker: str) -> list[tuple[str, float]] | None:
    if not ALPHAVANTAGE_KEY:
        return None
    url = ("https://www.alphavantage.co/query?function=TIME_SERIES_DAILY"
           f"&symbol={ticker}&outputsize=full&apikey={ALPHAVANTAGE_KEY}")
    try:
        series = json.loads(_http_get(url)).get("Time Series (Daily)", {})
    except Exception:
        return None
    out = []
    for date, row in sorted(series.items()):
        try:
            out.append((date, float(row["4. close"])))
        except (KeyError, ValueError):
            continue
    return out or None


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
QUOTE_SOURCES = [
    ("stooq", _quote_stooq),
    ("yfinance", _quote_yfinance),
    ("finnhub", _quote_finnhub),
    ("alphavantage", _quote_alphavantage),
]

HISTORY_SOURCES = [
    ("stooq", _history_stooq),
    ("yfinance", _history_yfinance),
    ("alphavantage", _history_alphavantage),
]


def get_quote(ticker: str, use_cache: bool = True) -> dict:
    """
    Return {'ticker','price','asof','source'} or raise PriceUnavailable.

    We deliberately do not fall back to a stale cached price silently past TTL --
    a wrong mark is worse than a missing one, because a wrong mark quietly
    corrupts the track record and nobody notices for months.
    """
    ticker = ticker.upper().strip()
    cache = _load_cache() if use_cache else {}
    entry = cache.get(ticker)
    if entry and (time.time() - entry.get("fetched_at", 0)) < CACHE_TTL_SECONDS:
        return {k: entry[k] for k in ("ticker", "price", "asof", "source")}

    errors = []
    for name, fn in QUOTE_SOURCES:
        try:
            result = fn(ticker)
        except Exception as exc:            # a source blowing up must not kill the run
            errors.append(f"{name}:{type(exc).__name__}")
            continue
        if result:
            price, asof = result
            if price and price > 0:
                rec = {"ticker": ticker, "price": round(float(price), 4),
                       "asof": asof, "source": name, "fetched_at": time.time()}
                cache[ticker] = rec
                _save_cache(cache)
                return {k: rec[k] for k in ("ticker", "price", "asof", "source")}
        errors.append(f"{name}:empty")

    if entry:
        # Stale, but flagged loudly as stale so it can never masquerade as fresh.
        return {"ticker": ticker, "price": entry["price"],
                "asof": entry.get("asof", ""), "source": entry["source"] + "-STALE"}

    raise PriceUnavailable(f"{ticker}: all sources failed ({', '.join(errors)})")


def get_quotes(tickers: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for t in tickers:
        try:
            out[t.upper()] = get_quote(t)
        except PriceUnavailable as exc:
            print(f"  ! {exc}")
    return out


def get_history(ticker: str, days: int = 400) -> list[tuple[str, float]]:
    """Daily closes, oldest first. Empty list if nothing worked."""
    ticker = ticker.upper().strip()
    for _name, fn in HISTORY_SOURCES:
        try:
            series = fn(ticker)
        except Exception:
            continue
        if series:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
            return [(d, p) for d, p in series if d >= cutoff]
    return []


def selftest(tickers: list[str] | None = None) -> None:
    """Run me after setup. Tells you which data sources are alive today."""
    tickers = tickers or ["AAPL", "SPY", "NVDA"]
    print("Data source self-test")
    print("-" * 60)
    for t in tickers:
        for name, fn in QUOTE_SOURCES:
            try:
                res = fn(t)
                status = f"OK   {res[0]:>10.2f}  ({res[1]})" if res else "none"
            except Exception as exc:
                status = f"ERR  {type(exc).__name__}"
            print(f"  {t:<6} {name:<14} {status}")
        print()
