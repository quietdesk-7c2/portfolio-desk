# Portfolio Desk

Three paper-money portfolios, $100,000 each, managed by Claude under the rules
in [`IPS.md`](IPS.md). Runs itself on GitHub Actions, publishes a dashboard to
GitHub Pages, and pushes a phone notification on every trade.

**Start here: [`SETUP.md`](SETUP.md).**

| Book | Mandate | Benchmark |
|---|---|---|
| **Core** | Diversified stocks + ETFs. Beat the S&P, look boring doing it. | SPY |
| **Moonshot** | High credible price targets + accelerating customer sentiment. | ARKK |
| **AI Trade** | The whole AI stack — semis, networking, power, hyperscale, apps. | SOXX |

## How it works

```
research  ->  orders/pending.json  ->  rules gate  ->  fills  ->  state/*.json
                                                          |            |
                                                       ntfy push   docs/index.html
```

Nothing is bought without a written thesis whose claims were checked against
primary sources. Every trade is a git commit, so the track record cannot be
quietly edited after the fact.

## Commands

```bash
python3 -m engine.run selftest    # which data sources are alive right now
python3 -m engine.run daily       # mark to market, apply rules, publish
python3 -m engine.run execute     # fill orders/pending.json
python3 -m tests.test_offline     # 41 checks, no network needed
```

## The emerging-theme radar

Every two weeks I sweep six sources ranked by how far ahead of published opinion
they sit — technical conference proceedings, regulatory filings, private funding
rounds, supply-chain lead times, hyperscaler capex commentary, and sentiment
acceleration off a *low* base. Themes are tracked in
[`research/watchlist.json`](research/watchlist.json) and scored on chatter,
trajectory, whether capital has actually committed, **vehicle quality**, and time
to P&L. Research runs biweekly; trading frequency is unchanged — more looking,
the same acting. See IPS §3b.

## The valuation gate

Every new position must clear three tests before the engine will fill it
(IPS 3a): at least 15% implied upside to consensus, a growth-adjusted multiple
(forward P/E / growth) of 2.0 or less, and an explicit comment if forward P/E
sits above trailing. Data lives in `research/valuation.json`; a ticker with no
record is rejected, because missing data is not a pass. See
[`VALUATION_CHECK.md`](VALUATION_CHECK.md) — it documents the five names this
gate rejected from the opening roster, including one I had called the
best-verified position on the desk.

## The rules, briefly

Position caps of 8/10/12% per book · cash floors of 5/10/5% · hard stops of
none/-25%/-20% · automatic cost-basis recovery at +100% · a drawdown circuit
breaker at -15/-25/-35% · a cap of 8 discretionary trades a month · and at most
2 rule overrides a month, each requiring a written justification that shows up
on the dashboard so they can be graded separately.

Full detail in [`IPS.md`](IPS.md).

---

Paper money. Not investment advice.
