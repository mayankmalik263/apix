# APIx Methodology

**Version 0.1 — DRAFT** · 3 September 2026
Owner: **Ayush**. Implemented by Bharat in `apix/index/engine.py`.

> **AYUSH — READ THIS FIRST.**
> This is a draft written to save you a blank page at 3am. It is not finished
> and it is not yours until you have checked it. Your job is three things:
>
> 1. **Verify** every formula below. If one is wrong, change it and tell Bharat.
> 2. **Write the justification paragraphs** — the boxes marked `[AYUSH: WHY]`.
>    Those are yours alone. They are the jury answers, and they need judgement,
>    not maths. Nobody can write them for you.
> 3. **Recompute one day's APIx by hand** from the Silver rows and check it
>    matches the engine. If those two numbers differ, that is the most
>    important bug in the project.
>
> Delete this box when you have done all three. Then it's version 0.1 proper.

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
P(r,w,t) = median{ total_fare : status = OK and is_outlier = false }
```

The median of every quoted fare in that cell, after outlier flagging.

> `[AYUSH: WHY]` **Why the median and not the mean.**
> Write 3–4 sentences. Points to hit: fare distributions are right-skewed;
> a handful of genuine last-minute fares run 4–5× the typical one; a mean is
> dragged upward by them and would report a price increase that most travellers
> never faced; the median describes the fare a typical buyer sees. Say clearly
> that the outliers are *real*, which is why we flag rather than delete them.

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

> `[AYUSH: WHY]` **Why a 1-day base, and what changes later.**
> Write 3–4 sentences. Points to hit: a proper index base is an *average* over
> a base period (we specify 7 days) to avoid anchoring the whole series to one
> unusual day; we have one real day, so v0.1 uses a single-day base and says so;
> once 7 days of collection exist the base becomes the 7-day mean and the whole
> series is recomputed under `method_version` 0.2. Being explicit about this is
> the honest version and it is what a statistical office would expect.

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

> `[AYUSH: WHY]` **Why MAD and not mean ± 3σ.**
> Write 3–4 sentences. Points to hit: the standard deviation is itself dragged
> by the outlier it is meant to detect (masking); MAD is robust because the
> median is not moved by extreme values; on right-skewed fare data a 3σ rule
> flags almost nothing, or flags an entire surge day as errors. Mention that a
> festival surge moves the *whole* cell together, so it is correctly NOT
> flagged — the flag catches a single bad quote, not a real market move.

---

## 6. Route index — geometric mean across windows

```
I(r,t) = 100 × ( Π_w R(r,w,t) )^(1/W)
```

The geometric mean of the five window price relatives.

This is a **Jevons index** — the same elementary aggregation form used in CPI
construction.

> `[AYUSH: WHY]` **Why geometric across windows.**
> Write 3–4 sentences. Points to hit: the windows are *ratios* against their own
> bases, and ratios combine multiplicatively; an arithmetic mean would let the
> T+1 window — both the most expensive and by far the most volatile — dominate
> the route index; the geometric mean treats a doubling and a halving
> symmetrically. Name it as Jevons and say CPI elementary aggregation uses it.

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

> `[AYUSH: WHY]` **Why arithmetic across routes but geometric across windows.**
> Write 3–4 sentences. Points to hit: routes carry *expenditure weights* — they
> represent different volumes of actual spending, so they aggregate additively
> like a budget share; windows are repeated measures of the same route's price
> and carry no expenditure weight of their own. Getting this distinction right
> is the difference between "a student built a scraper" and "a student built an
> index."

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

> `[AYUSH: WHY]` **Why a sold-out flight and a broken scraper are different.**
> Write 3–4 sentences. This is the single most quotable idea in the project —
> spend care on it. Points to hit: both look like a missing price; one is a fact
> about the market and the other is a fact about us; collapsing both into NULL
> destroys the ability to report honestly on our own coverage; a statistical
> office cares more about knowing what it failed to measure than about a
> complete-looking table.

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
