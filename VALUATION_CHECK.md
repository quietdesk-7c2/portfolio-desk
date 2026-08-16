# Is it already priced in? — the check you asked for

**Short answer on GE Vernova: yes. It was priced in. I've cancelled the order.**

You caught a real error. Here's the full work.

---

## The mistake I made

My GEV thesis called it "the best-verified position on the desk" — $176B backlog,
orders +88%, gas sold out through 2030, all confirmed. Every number was right.

That was the problem. **A verified fact is not an edge.** The backlog is the most
public thing about that company, 38 analysts have modeled it, and it is sitting
in the price. I had confused *confidence in a fact* with *the fact being
mispriced*. Those are completely different things, and only one of them makes
money.

---

## What the numbers say about GEV

| Metric | Value | Read |
|---|---|---|
| Price | $1,063.25 | |
| Trailing P/E | 30.03 | |
| **Forward P/E** | **49.31** | **higher than trailing** |
| Revenue growth | +13.0% | lowest on the desk |
| Growth-adjusted multiple | 3.79 | limit is 2.0 |
| Consensus upside | +16.5% | 38 analysts |

The killer is the third row. **Forward P/E above trailing P/E means consensus
expects earnings to fall.** Trailing net income was up 724% year over year — that
is not a repeatable number, so the friendly-looking 30x is an illusion and the
real multiple is 49x. Forty-nine times earnings for 13% revenue growth.

Three more things I found:

- An independent DCF puts pure fair value at **$295–491**. The blended base case
  is **$1,019 — below the $1,063 price.** The model says it's worth slightly less
  than it costs.
- Adjusted EPS **missed consensus by ~19% last quarter despite a revenue beat.**
  That is precisely the backlog-to-earnings conversion risk, showing up in the
  actual results.
- Wind orders **-40% y/y**, an unresolved drag I never mentioned.

I owed you that third bullet in the original thesis and didn't give it to you.

---

## Applying the same test to everything else

Once the test existed I had to run it on the whole roster. Four more names failed.

### Rejected

| | Fwd P/E | Upside | Growth-adj | Why |
|---|---|---|---|---|
| **GEV** | 49.31 | +16.5% | 3.79 | earnings expected to fall |
| **ETN** | 30.72 | **+4.1%** | — | worst upside on the desk; EPS -1.2% |
| **COST** | 43.89 | +12.1% | 3.43 | 44x for 9% growth |
| **LIN** | 25.82 | +13.3% | 2.53 | wonderful business, full price |
| **JPM** | 15.03 | **+3.2%** | 0.77 | cheapest multiple rejected — see below |

JPM is the instructive one. 15x forward and a 0.77 growth-adjusted figure look
like value, right up until you notice **3.23% implied upside**. A low multiple
isn't an opportunity when the entire street already agrees the stock is worth
what it costs.

### The pattern

Every rejected name is a *value* or *quality-industrial* name. Every survivor is
a growth name. That is not a coincidence and it's worth stating plainly: **the
2026 value rotation already happened and re-rated those stocks.** The upside that
existed in February has been paid out. Meanwhile the names doing the actual
growing still carry upside — Micron at 6.6x forward, Nvidia at 22.6x with 70%
revenue growth. That inverts the usual intuition, and it's what the data says.

---

## It's now enforced in code, not intention

`research/valuation.json` holds a dated record for every ticker.
`engine.rules.check_valuation()` refuses any buy whose ticker lacks a record or
whose gate doesn't read PASS. **Missing data is a rejection, not a pass.**

Three tests, all in IPS §3a:

1. **≥15% implied upside** to consensus
2. **Growth-adjusted multiple ≤ 2.0** (forward P/E ÷ growth rate)
3. **Earnings-direction flag** if forward P/E exceeds trailing

Exempt: index ETFs, and unprofitable companies — a business with no earnings has
no P/E, so those are governed by the Moonshot screen instead.

I can override the gate, but it costs one of my two monthly override slots and
requires a written justification that shows up on your dashboard in its own
section, so you can grade my overrides separately from my rule-following. Five
new tests cover all of this; the suite is at 49 checks.

I also wrote the turnaround method (`implied growth = trailing P/E ÷ forward P/E
− 1`) into the rules **before** applying it to UNH, specifically so I can't
invent a formula later to rescue a name I've fallen for.

---

## What replaced them

The Core book was down to three names after the cuts — not a diversified
portfolio. So I screened more candidates through the same gate rather than
shipping a thin book and calling it discipline.

**Added:** META (18.58x forward, +27.9% upside, forward *below* trailing —
the exact opposite of the GEV signature), AMZN (+24.2%, flagged as the least
comfortable pass at 1.81), UNH (+18.3%, the deliberate non-tech ballast).

**One honest concern:** Core is now four mega-cap tech names plus UNH and XLV,
and those four are AI beneficiaries too. Core owns the *demand* side
(hyperscalers), the AI book owns the *supply* side (silicon, memory, power).
That's a defensible split, but **both books will fall together in an AI
drawdown.** UNH and XLV are the only real diversifiers, and that isn't enough
yet. Finding non-tech names that clear the gate is a September priority.

---

## The AI book, rebuilt across the full stack

You asked for everything AI-adjacent. It now spans:

| Layer | Name | Fwd P/E | Upside |
|---|---|---|---|
| Compute | **NVDA** 12% | 22.60 | +34.5% |
| Foundry | **TSM** 10% | 19.22 | +28.3% |
| **Memory** | **MU** 10% | **6.61** | **+54.6%** |
| Custom silicon | **AVGO** 9.5% | 26.51 | +34.3% |
| Inference | **AMD** 8% | 43.49 | +19.1% |
| Power | **CEG** 7% | 23.53 | +22.4% |
| Thermal / rack | **VRT** 5.5% | 37.69 | +15.1% |

**Two changes the gate forced:**

**NVDA is now the largest position, not AMD.** My original reasoning — don't let
the book become a single-stock bet — was portfolio construction, and I let it
override price. NVDA at 22.60x forward with 70.7% revenue growth is dramatically
cheaper than AMD at 43.49x with 39.5%. AMD cut from $11,000 to $8,000. Same
conviction in the business, smaller size, because price matters.

**Micron is the new memory leg**, and the most interesting number on the desk:
**6.61x forward earnings** with revenue up 167% and +54.6% upside across 46
Strong Buys. The market is pricing these as peak-cycle earnings that collapse —
the standard memory discount, and historically it's often been right. My bet is
that HBM is contracted years forward rather than sold spot, so it shouldn't
behave like a commodity glut. **If I'm wrong, it's 6.6x on earnings that halve.**
That's why it's 10% and not the 12% cap.

### On space data centers

Real theme, and I want to be straight about the economics: orbital compute
currently runs **~4x terrestrial cost** ($8.64 vs $2.37 per GPU-hour), with
parity projected around **2038–2040**. This is 2027+ optionality, not a 2026
revenue story.

The good news is you **already own the investable exposure**:

- **NVDA** holds a disclosed **$21B stake in SpaceX** and is the compute partner
  for **Starmind AI1** (Vera CPUs, Rubin GPUs, NVL72 racks), targeted as early as
  2027
- **GOOGL** is running **Project Suncatcher** — radiation testing complete, two
  prototypes planned for early 2027

The pure-plays — RKLB, RDW, PL — are unprofitable and belong in Moonshot by
definition, not in the AI book. RKLB is logged at MOONSHOT-PENDING: it clears 2
of the 4 Moonshot criteria (40.8% upside across 18 Buys, dated sector catalysts)
but smart-money accumulation and sentiment acceleration are unverified. It gets
screened properly in September. Notably it trades **47% below its 52-week high**,
so it isn't disqualified for having already run.

**Still missing from the book:** networking (ANET), data-center REITs (DLR,
EQIX), and optical/interconnect. All need to clear the gate before they're
bought. September.

---

## Where it stands

**$112,943 deployed of $300,000 — 37.6%.** Lower than the first draft, because
the gate rejected five names and I'm not going to force-fit replacements to hit
a deployment target.

| | Deployed | Cash | Names |
|---|---|---|---|
| Core | $42,978 | 57.0% | 6 |
| AI Trade | $61,969 | 38.0% | 7 |
| Moonshot | $7,996 | 92.0% | 1 |

Holding 62% cash at a record-high market where most quality large-caps fail a
15%-upside screen isn't indecision. It's the screen telling you something, and
it's why staging in over three months was the right call before I knew any of
this.

---

*Every figure above is from stockanalysis.com as of 2026-08-14 and is recorded
with its date in `research/valuation.json`. If any of it is stale by the time you
read this, the file says so.*
