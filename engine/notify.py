"""
ntfy push notifications. Trades only -- no daily noise, by design.

If NTFY_TOPIC is unset, everything here becomes a no-op that prints to the log,
so the system still runs fine before you've set notifications up.
"""
from __future__ import annotations

import base64
import json
import urllib.request

from .config import NTFY_SERVER, NTFY_TOPIC, PORTFOLIOS


def _header_safe(s: str) -> str:
    """HTTP headers are ASCII/Latin-1 only, so a title with an em-dash or emoji
    (both outside that range) crashes urllib before the request is even sent.
    ntfy's own spec requires RFC 2047 word-encoding for non-ASCII headers --
    see https://docs.ntfy.sh/publish/#limitations -- not just any UTF-8-safe
    workaround, so that the server decodes it correctly on the other end."""
    try:
        s.encode("ascii")
        return s
    except UnicodeEncodeError:
        b64 = base64.b64encode(s.encode("utf-8")).decode("ascii")
        return f"=?UTF-8?B?{b64}?="


def _send(title: str, body: str, *, priority: str = "default",
          tags: str = "chart_with_upwards_trend", click: str = "") -> bool:
    if not NTFY_TOPIC:
        print(f"[ntfy disabled] {title} :: {body}")
        return False
    headers = {
        "Title": _header_safe(title),
        "Priority": priority,
        "Tags": tags,
        "Markdown": "yes",
    }
    if click:
        headers["Click"] = click
    req = urllib.request.Request(
        f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        print(f"  ! ntfy failed: {type(exc).__name__}: {exc}")
        return False


def trade(rec: dict, portfolio_equity: float, dashboard_url: str = "") -> bool:
    """One push per fill. Ticker, size, price, and why."""
    spec = PORTFOLIOS[rec["portfolio"]]
    side = rec["action"]
    emoji = "large_green_circle" if side == "BUY" else "red_circle"
    is_auto = "AUTO" in rec.get("tags", [])
    if "HOUSE_MONEY" in rec.get("tags", []):
        emoji = "moneybag"
    elif "STOP" in rec.get("tags", []):
        emoji = "octagonal_sign"

    weight = rec["value"] / portfolio_equity if portfolio_equity else 0
    title = f"{side} {rec['ticker']} — {spec.name}"
    lines = [
        f"**{rec['shares']:,.4g} sh @ ${rec['price']:,.2f}**  = ${rec['value']:,.0f}"
        f"  ({weight:.1%} of book)",
        "",
        rec["reason"],
    ]
    if "OVERRIDE" in rec.get("tags", []):
        lines.append("")
        lines.append("⚑ RULE OVERRIDE — see dashboard for justification")
    if is_auto:
        lines.append("")
        lines.append("_Automatic rule execution, not a discretionary call._")

    return _send(title, "\n".join(lines), tags=emoji,
                 priority="default" if is_auto else "high",
                 click=dashboard_url)


def breaker(portfolio_key: str, note: str, dashboard_url: str = "") -> bool:
    spec = PORTFOLIOS[portfolio_key]
    return _send(f"⚠️ Circuit breaker — {spec.name}", note,
                 priority="urgent", tags="warning", click=dashboard_url)


def message(title: str, body: str, dashboard_url: str = "") -> bool:
    return _send(title, body, click=dashboard_url)
