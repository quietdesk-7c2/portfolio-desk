# Investment Policy Statement

**Client:** Joshua
**Manager:** Claude (`claude-opus-5`)
**Capital:** $300,000 paper money — $100,000 in each of three portfolios
**Inception:** 2026-08-14
**Governing rule:** This document is authoritative. If code and this document disagree, this document is the intent and the code is the bug.

---

## 0. Purpose

This is the contract I operate under. It exists so that a year from now you can
tell the difference between *"the manager was right"* and *"the manager got lucky
and is now rationalizing."* Every constraint below is enforced in code, logged to
git, and auditable by you at any time.

I am managing paper money. Nothing here is a recommendation to you, and I am not
a licensed financial advisor. Treat the track record as an experiment, not advice.

---

## 1. The three mandates

### Portfolio 1 — CORE ("the charitable trust")
**Objective:** Beat the S&P 500 over rolling 12-month periods with comparable or
lower volatility. This is the book that is supposed to look boring and win anyway.

- Starting capital: $100,000
- Target holdings: 18–25 names, mix of individual stocks and ETFs
- Max position: 8% of book at cost, 12% hard ceiling after appreciation
- Min cash: 5% at all times. Target cash 5–15%.
- Expected turnover: **~1–2 trades per month.** This book should hardly change.
- Horizon: multi-year. Positions are expected to survive bad quarters.
- Benchmark: S&P 500 (SPY), secondary: 60/40 (SPY/AGG)
- Position-level stop-loss: **none.** Exits here are thesis-driven, not price-driven.

### Portfolio 2 — MOONSHOT
**Objective:** Asymmetric upside from names with (a) credible high price targets
and (b) genuine and *accelerating* customer/user sentiment. No sector constraint.

**The screen (the "RVMD test").** Pre-revenue is explicitly permitted. What is
required is **institutional conviction ahead of revenue** — and the point is to
catch it *before* the crowd, not after. Revolution Medicines is the reference
case for the pattern and a deliberate example of being too late: as of
2026-08-14 it trades at $202.81 with a $43.5B market cap and a consensus target
of $221.90 across 22 analysts. Twenty-two Strong Buys and only 9% of implied
upside means the conviction is real but the opportunity is already priced. That
is the shape I am hunting, one to two years earlier.

A Moonshot candidate must show **all four**:
1. **Analyst conviction concentration** — a high ratio of Buy ratings, with
   *meaningful* implied upside remaining (target >35%, not 9%).
2. **Smart-money accumulation** — insider open-market buying, or 13F
   accumulation by managers with domain-specific records.
3. **A dated, identifiable catalyst** within 18 months — a readout, an approval,
   a contract award, a capacity milestone. "The story gets better eventually"
   is not a catalyst.
4. **Sentiment *acceleration*, not sentiment level** — mention velocity rising
   off a low base. If it is already the loudest ticker on the internet, I am the
   exit liquidity, not the early money.

**Disqualifier:** already up >200% in the trailing three months.

- Starting capital: $100,000
- Target holdings: 10–14 names
- Max position: 10% of book at cost
- Min cash: 10% at all times — dry powder is part of the strategy here
- Expected turnover: ~1–2 trades per month
- Horizon: **12 months.** Every position must have a written one-year thesis.
- Benchmark: ARKK, secondary: Russell 2000 Growth (IWO)
- Position-level stop-loss: **-25% from cost**, evaluated on closing prices only

### Portfolio 3 — AI TRADE
**Objective:** Own where the AI buildout is actually going, not where it has been.
Explicitly spans the whole stack: semis → networking → power/cooling → hyperscale
→ software/apps → the picks-and-shovels nobody has noticed yet.

- Starting capital: $100,000
- Target holdings: 12–18 names
- Max position: 12% of book at cost
- Min cash: 5% at all times
- Expected turnover: ~1–2 trades per month
- Horizon: **12 months**, with multi-year positions permitted
- Benchmark: SOXX, secondary: an equal-weight AI basket
- Position-level stop-loss: **-20% from cost**, closing prices only

---

## 2. Trading cadence

This is not a day-trading system and the code will not let it become one.

| Window | What I may do |
|---|---|
| **Research cycle — Monday and Wednesday, after the close** | Full research sweep: theme radar (§3b), valuation gate re-run on every holding and candidate, thesis review. May open, close and rebalance positions. Full discretion within the rules. |
| **Other days** | Monitoring. May act *only* on: a triggered stop, a broken thesis, a house-money trim, or a genuinely time-sensitive opportunity (see §5). |
| **Daily** (automated, no judgment) | Mark to market, check stops, check drawdown thresholds, publish dashboard. |

**Research frequency and trading frequency are deliberately decoupled, and this
is the most important sentence in this section.** Research runs twice a week —
roughly nine sessions a month. The turnover cap stays at **8 trades a month with
a 4–6 target**, unchanged. So the overwhelming majority of research sessions will
correctly end with *no trade at all*, and a session that ends with nothing is a
successful session, not a wasted one.

The risk of a fast research cadence is not missing things. It is manufacturing
activity to justify the looking. A one-year-horizon portfolio reviewed twice a
week will present a reason to fiddle almost every time, and the cap exists to
make fiddling impossible. Being up to date is an information advantage; spending
it on turnover is how the advantage gets converted into transaction costs.

**Hard turnover cap: 8 discretionary trades per calendar month across all three
portfolios combined.** Target is 4–6. If I hit the cap, the engine refuses further
orders until the next month. Stops and house-money trims do not count against it.

Rationale: you asked for roughly one trade every one to two weeks. The cap is set
slightly above that so the rule binds only when I'm misbehaving, not when I'm
working normally.

**One exemption: inception.** Building a book from cash is not turnover, so the
initial deployment of each portfolio is tagged `INCEPTION` and does not count
against the cap. The engine allows this **once per portfolio, ever** — after a
book's first deployment the tag is rejected and the trade counts normally. It
cannot become a back door.

---

## 3. What I am allowed to buy on

A position needs **at least two independent confirmations** from the list below,
and at least one must come from tier A. "Two analysts said so" is not two signals.

### Tier A — hard evidence (someone acted, or a company committed on the record)
1. **SEC Form 4 insider buying** — open-market purchases only (transaction code P).
   Weighted by: cluster (2+ insiders in 90 days) > single large director buy
   (≥$1M) > CEO/CFO > other officers. **Used as conviction confirmation on a
   1-year thesis, never as an entry trigger** — 70–80% of the short-horizon return
   occurs before the filing is public.
2. **13F filings** — accumulation by managers with a defensible long-term record.
   45-day lag understood; used thematically, not for timing.
3. **Congressional / senior official disclosures** — STOCK Act periodic transaction
   reports. **45-day statutory lag.** Used *only* as a sector/theme tell about where
   people with policy visibility are allocating. Never a timing signal. Never the
   sole reason for a position.
4. **Company filings and guidance language** — 10-K/10-Q, 8-K, earnings call
   transcripts. Management's own numbers, cross-checked against what they said.

### Tier B — opinion and crowd (must be verified before use)
5. **Sell-side price targets and estimate revisions** — I care about *upward EPS
   estimate revisions* far more than headline price targets. A PT is a marketing
   document; a revision is an analyst admitting they were wrong.
6. **Retail sentiment** — Reddit/WSB/StockTwits mention **acceleration**, not raw
   volume. Raw volume finds the stock that already ran. Acceleration off a low base
   with a fundamental catalyst is the actual signal.
7. **Credible operators and specialists** — people with verifiable track records and
   domain depth. Their claim is an input, never a conclusion (see §4).

---

## 3a. The valuation gate — is it already priced in?

*Added 2026-08-14 at the client's instruction, after it caught a real error in
my first roster. This is the single most important rule in this document.*

A verified fact is not an edge. If a company's good news is public, analysts
have modeled it and it is in the price. GE Vernova's $176B backlog is the most
public fact about that company; 38 analysts have built it into their estimates.
Buying a stock *because* of a widely-reported backlog is buying consensus at
consensus prices.

**Every new position must clear all three tests, or it is not bought:**

1. **Consensus upside floor — at least 15% implied upside** to the consensus
   analyst target. Below that, the street already thinks it is worth roughly
   what it costs.
2. **Growth-adjusted multiple ≤ 2.0** — forward P/E divided by the growth rate
   being paid for. Where trailing growth is negative or distorted, implied
   forward growth is derived as `(trailing P/E ÷ forward P/E) − 1`. That method
   is written down here specifically so it cannot be applied selectively to
   rescue a name I have already decided I like.
3. **Earnings-direction check** — if forward P/E sits *above* trailing P/E,
   consensus expects earnings to **fall**. That requires an explicit written
   comment, because it usually means trailing earnings were flattered by
   something non-recurring.

**Exemptions:** index/sector ETFs (the test is not meaningful), and
unprofitable or pre-revenue names, which are governed by the Moonshot screen in
§1 instead — a company with no earnings cannot have a P/E.

**Enforcement.** The gate is code, not intention. `research/valuation.json`
holds a dated record for every ticker, and `engine.rules.check_valuation()`
refuses any BUY whose ticker lacks a record or whose gate does not read PASS.
Missing data is a rejection, not a pass — "probably fine" is not a verification.

**Overriding it** requires the `OVERRIDE` tag and a written justification, and
spends one of the two monthly override slots. Cheapness is not the objective;
paying less than the future is worth is.

---

## 3b. The emerging-theme radar

*Added 2026-08-14 at the client's instruction: "space data centers is something
only talked about a little. It is companies like that that end up having the
biggest upside to catch early."*

The point is not space data centers. The point is the **class** — themes with
**low absolute chatter and rising interest**. By the time a theme is on the
cover of a magazine, the multiple already contains it. The GE Vernova rejection
in §3a and this section are the same idea viewed from two ends: don't buy
consensus, and go find what isn't consensus yet.

**Every biweekly cycle, I sweep these sources — in this order.** They are ranked
by how far ahead of published opinion they sit:

1. **Technical conference proceedings** — OFC, Hot Chips, ISSCC, SC. Engineers
   describe the next bottleneck one to two years before analysts model it. The
   co-packaged optics position came from here.
2. **Regulatory and agency filings** — FCC applications, FERC interconnection
   queues, environmental permits. Blue Origin filing for 51,600 data center
   satellites is a fact with a docket number, not an opinion.
3. **Private funding rounds at step-change valuations** — private capital
   commits before public markets reprice. Starcloud at $1.1B is a signal about
   orbital compute regardless of whether it ever lists.
4. **Supply-chain lead times and pricing** — the least glamorous and often the
   most predictive. Transformer lead times going from ~104 to ~128 weeks is a
   quantitative fact about a constraint nobody is writing about.
5. **Hyperscaler capex commentary** — new line items and first-time mentions.
6. **Sentiment acceleration off a LOW absolute base** — mention velocity, via
   ApeWisdom. Deliberately *low base*: a ticker going from 5 mentions to 50
   matters; one going from 5,000 to 10,000 is already priced.

**Each theme is scored in `research/watchlist.json` on five axes:** chatter
level, trajectory, whether capital has actually committed, **vehicle quality**,
and time to P&L.

**Vehicle quality is the axis that kills most themes, and it is the one I will
be most tempted to fudge.** A correct theme with no investable vehicle is a
conversation, not a position. Cleveland-Cliffs is the worked example: the sole
domestic producer of the grain-oriented electrical steel that power transformers
require — a genuine monopoly on a genuine bottleneck — sitting inside $19.2B of
commodity steel revenue that mostly serves the auto industry, lossmaking, and
with a consensus target *below* the current price. Perfect narrative, wrong
vehicle. **An under-covered theme is only actionable when some company's
economics actually concentrate it.**

**Second-order use.** Themes are tracked as *risks* as well as opportunities.
The transformer shortage is simultaneously a possible long and a warning that
30–50% of announced data center capacity may slip — which would soften the
demand curve under positions this desk already holds. A radar that only ever
finds reasons to buy is not a radar.

**Nothing found by the radar bypasses anything.** A theme discovery still faces
the valuation gate (§3a), the verification rule (§4), and every sizing and
turnover limit. Being early is not a licence to overpay — Lumentum was rejected
on exactly this basis: right theme, up roughly 8x, wrong entry.

---

## 4. The verification rule

**No claim enters a thesis until I have checked it against a primary source.**

**This applies symmetrically to bearish claims.** On 2026-08-14 I flagged a
"30–50% of data center capacity will be cancelled" risk against this desk's own
AI book on the strength of one Medium post — in the same session I wrote this
rule. On verification the claim was substantially overstated and the most
credible source in the field had published a direct rebuttal. A caution is a
claim. Sounding prudent is not evidence, and scaring a client with unverified
research is a failure of the same kind as exciting one.

For every factual assertion supporting a trade:
1. Identify the claim and who made it.
2. Find the primary source — the filing, the transcript, the disclosure, the dataset.
3. Record whether it **confirms**, **partially confirms**, or **contradicts** the claim.
4. If it contradicts, the claim is discarded and I note publicly that the source was wrong.

Every position's thesis file records its claims and their verification status.
If I could not verify something, the thesis says "UNVERIFIED" in plain text.
An unverified claim may not be the load-bearing reason for a position.

I will also record, for each source I rely on repeatedly, whether their prior
calls worked out. Reputation is earned in this system, not assumed.

---

## 5. Discretion and overrides

You explicitly asked that I be able to override a rule on conviction. That right
exists, and it is bounded:

**I may override any *soft* rule** (target holding count, cash target, cadence
window, signal-count minimum) **if I write a justification into the trade record
explaining what I see that the rule doesn't.** Overrides are tagged `OVERRIDE` in
the trade log and surfaced on the dashboard in a separate section, so you can grade
them independently. If my overrides underperform my rule-following trades over time,
that is data and I will act on it.

**I may not override the hard rules, ever:**
- Position size ceilings
- Minimum cash floors
- The monthly turnover cap
- The drawdown circuit breaker
- The verification rule (§4)
- Any prohibition in §8

**Override budget: 2 per calendar month.** A right I can use constantly is not
conviction, it's just noise with extra paperwork.

---

## 6. Selling discipline

You gave me three sell conditions. They are now rules.

**A. House money (automatic).** When a position reaches **+100%** from cost, the
engine automatically sells enough shares to recover the original dollars invested.
The remainder rides indefinitely at zero net cost. This is automatic, does not
require my judgment, does not count against the turnover cap, and pushes you a
notification. Applies to MOONSHOT and AI only — CORE compounds untouched.

**B. Taking a good profit (discretionary).** I may trim or exit when I judge the
return has front-run the fundamentals. Requires a written reason. Default posture
on a winner is *trim, don't exit* — I will not sell a compounding position simply
because it went up.

**C. Thesis or sentiment break (discretionary).** I exit when the reason I bought
it is no longer true: guidance cut, competitive position lost, management
credibility gone, accounting concerns, or the customer sentiment that justified a
moonshot has demonstrably reversed. Requires me to state which specific pillar of
the original thesis failed.

**Explicitly not a sell reason:** the price went down. You told me to buy things I
believe in and hold through turbulence. Volatility alone will never trigger a
discretionary exit. Only the hard stops in §1 do that, and CORE has none.

---

## 7. Drawdown circuit breaker

Measured per portfolio, from that portfolio's own high-water mark.

| Level | Consequence |
|---|---|
| **-15%** | Notification to you. I write a written review of what went wrong. Trading continues. |
| **-25%** | **New buys HALTED on that book.** Existing positions held. I must publish a post-mortem before buying resumes. |
| **-35%** | Full stop. Book liquidates to 50% cash. You decide whether I continue managing it. |

Portfolios are independent. MOONSHOT blowing up does not touch CORE.
The breaker cannot be overridden by me.

---

## 8. Prohibitions

No leverage. No margin. No options. No shorting. No crypto. No penny stocks
(< $1.00 or < $150M market cap). No OTC/pink sheets. No securities where the
average daily dollar volume is under $2M. No position opened without a written
thesis. No thesis without §4 verification. No trade executed at a price I cannot
source from live market data.

---

## 9. Reporting

- **Dashboard**: updated every trading day after the close, publicly readable by
  you on any device.
- **Notifications**: ntfy push on every fill and every house-money trim. Trades
  only — no daily noise.
- **Monthly letter**: what I did, what I got wrong, performance vs. benchmark,
  and the current state of every thesis.
- **Audit trail**: every trade is a git commit. I cannot retroactively edit history
  without it being visible.

---

## 10. How to fire me

Any of these, at your sole discretion, at any time:
- Underperformance of the relevant benchmark over a rolling 12-month period
- A circuit breaker trip you don't find adequately explained
- Any discovered instance of me stating an unverified claim as verified

*Last amended: 2026-08-14. Amendments require your approval and are logged in git.*
