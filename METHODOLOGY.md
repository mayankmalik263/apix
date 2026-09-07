# APIx Methodology

**Version 0.1** · 3 September 2026, revised 8 September 2026
Owner: **Mayank Malik**. Implemented by Bharat in `apix/index/engine.py`.

> **Independent check.** One day's APIx was recomputed from the Silver rows
> outside the engine, in a separate script, and compared against the published
> value. The two agree to 0.00004 index points. That check also settled a
> genuine disagreement between this document and the code: an earlier draft of
> section 3 excluded flagged rows from the median while the engine kept them.
> The engine's behaviour was adopted and this document corrected, because
> keeping them is what section 5 has always said and what the flag is for.
> No published value changed — the engine has always kept flagged rows, and
> 4 September has read 102.240 throughout. Had the earlier wording been followed
> instead, that day would read 102.669. The 0.43-point difference is recorded
> here so the choice is visible rather than absorbed silently.

---

## 1. What is being measured

APIx is a **daily, route-level price index for Indian domestic airfares**.

It is not a fare predictor and not a price-comparison tool. It measures how
airfares move, in a form that can sit inside a Consumer Price Index.

**Observation unit:** one *cell* = one (route, booking window, day).

| | |
|---|---|
| Routes | 6 — DEL-BOM, DEL-BLR, BOM-BLR, DEL-CCU, BLR-HYD, MAA-DEL |
| Booking windows | 5 — T+1, T+7, T+14, T+21, T+45 days ahead |
| Cells per day | **30** |
| Fare specification | one adult · economy · one-way · cheapest available |
| Observation slot | a fixed daily time, so days are comparable |

**Why T+21 is in the list:** it is MoSPI's own documented domestic collection
window. Our T+21 series is therefore directly comparable to the official
airfare item index, and the other four windows show something no official
series anywhere publishes — how the fare moves with booking lead time.

---

## 2. Notation

| Symbol | Meaning |
|---|---|
| `r` | route |
| `w` | booking window, in days ahead |
| `t` | observation date |
| `W` | number of windows used for a route on day `t` |
| `ω_r` | expenditure weight of route `r`, `Σ ω_r = 1` |

---

## 3. Cell median

```
P(r,w,t) = median{ total_fare : status = OK }
```

The median of every quoted fare in that cell. Flagged rows are **included** —
see section 5. The flag is a label on a row, not a deletion of it.

> **Why the median and not the mean.**
>
> Fare distributions are lopsided in one direction. On DEL–BOM leaving
> 24 September we measured a cheapest fare of ₹6,090 and a dearest of ₹24,056
> on the same route, the same date, in the same search — a four-fold spread.
> The mean of that cell is about ₹8,900, which is a price almost nobody in it
> actually paid; the median is ₹7,675, which is roughly what a traveller
> booking that seat would have seen. A mean would let a handful of last-minute
> seats report a price rise that most travellers never faced.
>
> The important part is that those dear fares are **real**. They are not
> errors, and we do not remove them — that would be editing the market. We
> flag them, keep them, and publish a statistic that is not moved by them.

**If a cell has no OK rows**, `P(r,w,t)` is undefined. The cell is skipped and
the reason is recorded — it is never treated as zero, and never interpolated.

---

## 4. Price relative and the base period

```
R(r,w,t) = P(r,w,t) / P(r,w,0)
```

`P(r,w,0)` is the **base**: the cell median on the base date, with the base
index set to 100.

**Base date for the real series: 3 September 2026.** Our first real collection
day. The real index therefore starts at 100 today.

**The simulated 91-day history is based separately and drawn as a separate
line.** It never anchors the real series. Nothing real is ever computed from a
simulated number.

> **Why a 1-day base, and what changes later.**
>
> A price index should be based on an *average* over a base period, not on a
> single day. One day carries whatever was peculiar to it — a strike, a long
> weekend, a fare sale — and a single-day base silently writes that peculiarity
> into every later value as though it were normal. Our base period is specified
> as **7 days**.
>
> We do not have 7 days. Version 0.1 therefore uses a single-day base,
> 3 September 2026, and states it here rather than hiding it. Every value the
> system publishes is stamped `method_version` so it is always clear which rule
> produced it.
>
> When 7 real collection days exist, the base becomes the mean of the cell
> medians over those days, the whole series is recomputed from Bronze, and the
> results are published as `method_version` 0.2. Nothing is patched in place;
> the old series remains reproducible from the same raw archive. A single-day
> base that is declared and dated is a stated limitation. An averaged base that
> is claimed but not held would be a false one.

---

## 5. Outlier flagging

Computed **within** each (route, window, day) cell, on the OK rows.

```
median         = median(fares)
MAD            = median( |fare - median| )
modified_Z(i)  = 0.6745 × (fare_i - median) / MAD
flag if |modified_Z(i)| > 3.5
```

If `MAD = 0` (every fare identical) no row is flagged.

- Method: **modified Z-score on the median absolute deviation**, Iglewicz &
  Hoaglin. Threshold 3.5 is their standard cut.
- `0.6745` rescales MAD so the threshold is comparable to a standard-deviation
  cut on normally distributed data.
- **Rows are flagged, never deleted.** The flag is stored; the row stays.

> **Why MAD and not mean ± 3σ.**
>
> A 3σ rule detects outliers using the standard deviation — a quantity the
> outlier itself inflates. One ₹24,056 fare in a cell of ₹6,000 quotes widens σ
> enough to bring itself back inside the fence. Statisticians call this
> masking, and it gets worse the more extreme the value: the rule fails hardest
> exactly where it is needed.
>
> The median absolute deviation has no such feedback. The median does not move
> when a tail value moves further out, so the yardstick stays fixed while the
> thing being measured does not. On right-skewed data — and every fare
> distribution we have collected is right-skewed — a 3σ rule typically flags
> nothing at all, because σ is already large enough to swallow the tail it was
> meant to catch.
>
> The distinction that matters operationally: **a real market move is not an
> outlier.** When a festival or a long weekend lifts a route, the whole cell
> rises together — the median rises with it, every deviation from that new
> median stays small, and nothing is flagged. That is correct. The flag exists
> to catch one bad quote sitting among thirty sane ones, not to argue with the
> market about its own prices. On 3 September, 3.5% of rows were flagged; none
> of them were removed.

---

## 6. Route index — geometric mean across windows

```
I(r,t) = 100 × ( Π_w R(r,w,t) )^(1/W)
```

The geometric mean of the five window price relatives.

This is a **Jevons index** — the same elementary aggregation form used in CPI
construction.

> **Why geometric across windows.**
>
> By the time the five windows are combined they are no longer prices, they
> are ratios — each window divided by its own base — and ratios combine by
> multiplying, not by adding. The practical consequence is symmetry: a window
> that doubles and a window that halves cancel exactly under a geometric mean,
> giving 100. Under a plain average the same pair gives 125, so the index
> would report a 25% rise on a route where nothing had happened.
>
> It also stops one window running the route. T+1 is both the dearest window
> and by far the jumpiest; on DEL–BOM its median sits 2.7× above T+45. Because
> we aggregate relatives rather than levels that gap largely cancels, and the
> geometric mean keeps what remains of it from dominating.
>
> This form has a name — a **Jevons index** — and it is the same elementary
> aggregation CPI construction uses below the weighted level.

---

## 7. National index — weighted arithmetic mean across routes

```
APIx(t) = Σ_r  ω_r · I(r,t)          with  Σ ω_r = 1
```

Fixed weights, revised annually — **not** daily. This is a **Laspeyres-type**
fixed-weight index.

**Weights are currently PROVISIONAL.** We do not yet have DGCA city-pair
passenger data, so all six routes carry equal weight (1/6) and every index
value computed this way is stamped `weights_provisional = true`.

Do not hand-type weights to make that flag go away.

> **Why arithmetic across routes but geometric across windows.**
>
> The two levels are aggregating different kinds of thing, so they take
> different forms. A route carries an **expenditure weight**: DEL–BOM
> represents a real share of what Indian travellers spend on flying, and
> shares of a budget add up. That is why routes combine as a weighted sum,
> and why the weights have to total 1.
>
> The five windows carry no expenditure weight of their own. They are five
> repeated readings of the same route's price at different booking lead times,
> not five different things people buy. There is no budget share to attach to
> T+7, so there is nothing to add up — which is what leaves the geometric mean
> as the right form one level down.
>
> Strictly this makes APIx a **Laspeyres-type** index, and once the weights
> come from a period other than the price base — they are revised annually —
> it is a **Lowe index**. Both are fixed-weight forms; the distinction is
> which period the weights are drawn from."

---

## 8. Coverage

```
n_expected(t) = 30  −  (cells with status NO_SERVICE)
n_observed(t) = cells with at least one row of status OK or SOLD_OUT
coverage(t)   = n_observed(t) / n_expected(t)
```

`SOLD_OUT` **counts as observed**: the market was successfully checked and it
said there is no inventory. That is information, not a failure.

`NO_SERVICE` **leaves the denominator**: no flight operates that pair on that
date, so there was never anything to observe.

`FETCH_FAIL`, `BLOCKED`, `PARSE_FAIL` and `SOURCE_DISALLOWED` are gaps and
**lower coverage**.

> **Why a sold-out flight and a broken scraper are different.**
>
> On the screen they look identical: a cell with no price in it. In a table of
> NULLs they are indistinguishable. They are not remotely the same thing.
>
> A sold-out flight is **a fact about the market**. We asked, the market
> answered, and the answer was that nothing is left at any price. That is a
> successful measurement, and one of the more interesting ones — inventory
> exhaustion is itself a price signal. A failed fetch is **a fact about us**.
> The market may have had a perfectly ordinary fare on offer; we simply did not
> manage to read it.
>
> Collapse the two into NULL and the system loses the ability to describe its
> own reliability. Coverage becomes uncomputable, because a gap can no longer
> be attributed. Worse, the incentive inverts: every silent failure now looks
> like a quiet market, and the index reports most confidently on exactly the
> days it measured worst.
>
> This is why every observation APIx records carries one of seven statuses
> across three classes — MARKET, POLICY, SYSTEM — and why there is no NULL in
> the vocabulary at all. A statistical office needs to know what it failed to
> measure more than it needs a table with no holes in it. A complete-looking
> table that cannot say why it is complete is not a measurement; it is a
> presentation.
>
> The rule was tested on 8 September 2026 by our own bug: the compliance gate
> refused all 30 cells, the refusal was recorded as `SOURCE_DISALLOWED`, and
> because that status is POLICY and not MARKET, the day was visibly unmeasured
> rather than quietly empty — which is how it was caught and recollected the
> same night.

---

## 9. Confidence grade

Published on every value.

| Grade | Condition |
|---|---|
| **A** | coverage ≥ 0.90 **and** ≥ 2 source classes contributing |
| **B** | coverage ≥ 0.70 |
| **C** | coverage < 0.70 — still published, marked provisional |

An index value built from 30 of 30 expected observations and one built from
11 of 30 are not the same fact. Official series rarely tell you which one you
are looking at. APIx always does.

---

## 10. Provenance

Every published APIx value traces back to raw bytes:

```
gold_apix_daily → gold_route_index_daily → gold_cell_median
                → silver_fare_observation → bronze_observation_raw
                → the raw payload and its SHA-256
```

Bronze is append-only and immutable. When a parser breaks, the raw archive lets
the entire history be re-parsed. Airfare data cannot be collected
retrospectively, so a discarded payload is a permanently lost day.

---

## 11. Stated limitations

Say these before a judge finds them.

1. **Two days of real collection** (3 and 4 September 2026). The 91-day history
   is simulated from the model in §12, labelled `SIMULATED` in the database,
   and drawn differently on every chart.
2. **Weights are provisional** — equal weighting pending DGCA city-pair data.
3. **Single-day base** in v0.1; becomes a 7-day mean at v0.2.
4. **Six routes of roughly 1,100 city pairs.** Defend per route, not in
   aggregate: five observations a day is ~150 a month against the official one.
5. **Five of eleven named sources could not be checked** — read timeouts, which
   is *not* proof of a bot wall. Recorded as such, not overstated.
6. **The daily series carries a day-of-week cycle, and we have not removed it.**
   Every booking window shifts its departure date forward by one day on each
   observation day, so all 30 cells rotate through the weekly fare cycle
   together. Measured over the simulated history, mean APIx by observation
   weekday spans 13.3 index points — Monday 92.7 against Thursday 106.0 — and
   the mean absolute day-on-day move is 4.9%. For scale, the largest monthly
   move in MoSPI's own airfare item is 4.4%.

   Most of that daily movement is therefore composition, not price change:
   the index is partly reporting which weekday it is looking at. This is a
   known property of high-frequency price indices and the standard treatment
   is a 7-day moving average published alongside the raw daily series
   (Cavallo & Rigobon 2016 do exactly this). **v0.1 does not do it, and no
   APIx daily value should be read as a pure price movement until it does.**
   Scheduled for 0.2 with the 7-day base.

---

## 12. The simulation model — for the labelled history only

```
fare = base_route_fare
     × window_multiplier(w)     advance-purchase curve
     × weekday_factor(dow)      Friday/Sunday peaks
     × seasonality(t)           interpolated from the REAL MoSPI airfare index
     × lognormal_noise(0, 0.16) within-cell dispersion
     × festival_surge(t)        one deliberate 3-day shock
```

Seasonality is **not invented** — it interpolates MoSPI's published
"Air fare [normal]: economy class [adult]" index (Base 2012=100, Annex-V),
extracted by `scripts/extract_mospi_airfare.py`.

Base route fares are **order-of-magnitude placeholders**. They are plausible
for Indian domestic economy one-way fares. They are not measurements and must
never be presented as such.

Deterministic per cell — the same seed reproduces the identical history.

---

## Version history

| Version | Date | Change |
|---|---|---|
| 0.1 | 3 Sep 2026 | First specification. Single-day base, provisional weights. |
