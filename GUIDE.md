# APIx — how everything works

Written so that someone who has never seen the project can read it top to
bottom and then answer questions about it.

---

## 1. What the problem is

Inflation is measured by checking prices on a regular schedule. For air travel,
India uses **one figure for the whole country, published once a month**, with a
weight of 0.08 in the consumer price basket.

An airline seat does not behave like a bag of rice. The same seat can cost
₹6,000 one day and ₹24,000 the next. Price depends on the route, the day of the
week, and above all on how far ahead you book. Over 90% of domestic tickets are
now sold online, where prices change hourly, and none of that movement reaches a
monthly national average.

**APIx measures 30 prices a day instead of one a month**, at route level, and
turns them into an index number the same way the CPI turns grocery prices into
one figure.

---

## 2. What the index actually is

The unit of observation is a **cell**: one route, one booking window, one day.

> `DEL-BOM, T+21, 7 September` is one cell.

| | |
|---|---|
| **Routes** (6) | DEL–BOM, DEL–BLR, BOM–BLR, DEL–CCU, BLR–HYD, MAA–DEL |
| **Booking windows** (5) | T+1, T+7, T+14, T+21, T+45 days ahead |
| **Cells per day** | 6 × 5 = **30** |
| **Fare priced** | one adult, economy, one way, cheapest available |

**T+21 is in the list on purpose.** It is the official documented domestic
collection window, so our T+21 series is directly comparable to the published
item index. The other four windows show something no official series anywhere
publishes: how a fare moves with booking lead time.

**Reading the number.** The index starts at 100 on its first day. A value of 104
means fares across the basket are 4% above where they started. It measures
*change*, not price — 104 does not mean ₹104.

---

## 3. Using the website

Six screens. The top bar carries a live IST clock and a countdown to the next
collection on every one of them.

### Index
The headline readout and the comparison that carries the argument.

- **APIx** — the index value, with the date its base is set from.
- **Coverage** — how many of the thirty cells were actually observed.
- **Confidence** — A, B or C, explained in section 5.
- **Fares priced / Median fare** — the raw volume behind the number.
- **Against the official series** — our line over the official monthly steps,
  both rebased to 100 at their own first observation. Daily, weekly and monthly
  are a toggle; drag the slider under the chart to change the span.
- **Route indices** — each route's deviation from its own base.
- **Coverage over time** — green ≥ 90%, amber ≥ 70%, red below.

### Lead time
Median fare against how far ahead the seat is booked, overall and per route,
with the change between adjacent windows and per day of extra lead time. This
is the output the brief calls a lead-time elasticity curve. On the day shown
the floor is T+14 and the curve turns back up, so booking earliest is not
booking cheapest.

### Basket
All thirty cells as a heatmap and a table, plus the base fare separated from
taxes and fees. **Click any cell** to open its provenance: the published
median, the fares behind it with their outlier scores, and the stored payload
with its SHA-256.

### Quality
The fare distribution, the status vocabulary in use, the fares flagged inside
their own cell, and the compliance verdict for all eleven registered sources.

### API
The two access tiers, authentication, and every endpoint.

### About
The problem, the four calculation steps, how APIx compares to what already
exists, and the stated limitations.

### Operator console
Separate, at `/console`, behind a sign-in. Issues API keys, triggers a
collection, and shows the access log.

---

## 4. How the number is built

Four steps. Each feeds the next.

**Step 1 — cell median.** Within each cell, take the median of the fares that
came back.

```
P(r,w,t) = median of the OK fares in that cell
```

Median rather than average because fare distributions are lopsided. In one real
search we measured fares from ₹4,074 to ₹52,225. The average of that is around
₹12,700 — a price almost nobody paid. The median describes the ticket a normal
traveller sees.

**Step 2 — price relative.** Compare each cell against the same cell on the base
day.

```
R(r,w,t) = P(r,w,t) / P(r,w,base)
```

A T+1 fare is naturally dearer than a T+45 fare. Comparing each window against
its own history stops expensive windows dominating just because their rupee
level is higher. On DEL–BOM the raw medians span 2.67× across windows; the
relatives span 1.17×.

**Step 3 — route index, geometric mean.**

```
I(r,t) = 100 × (R₁ × R₂ × … × R_W)^(1/W)
```

Geometric because by this point the windows are ratios, and ratios multiply. A
window that doubles and one that halves cancel to exactly 100; a plain average
gives 125, so the index would report a rise where nothing happened. This form is
a **Jevons index** — the standard elementary aggregation in CPI construction.

**Step 4 — APIx, weighted arithmetic mean.**

```
APIx(t) = Σ ω_r × I(r,t),   Σ ω_r = 1
```

Arithmetic because each route carries a real share of what travellers spend,
like items in a household budget, and budget shares add. Windows carry no
spending weight of their own — they are repeated readings of one route's price.

Weights are currently equal and every affected value is stamped
`weights_provisional`, pending DGCA city-pair passenger data.

---

## 5. Coverage and confidence

Published on every value, because an index built from 30 of 30 observations and
one built from 11 of 30 are not the same fact.

```
n_expected = 30 − cells where no flight operates
n_observed = cells with at least one OK or SOLD_OUT result
coverage   = n_observed / n_expected
```

| Grade | Condition |
|---|---|
| **A** | coverage ≥ 0.90 **and** two independent portals agreeing |
| **B** | coverage ≥ 0.70 |
| **C** | below 0.70 — still published, marked provisional |

We currently publish **B**: coverage is complete, but from a single permitted
source. Reaching A needs a second portal corroborating, which is honest and is a
stronger claim than the alternative.

---

## 6. A missing price is never just missing

This is the idea the project is built on.

| Status | Class | Meaning | Counts as observed? |
|---|---|---|---|
| `OK` | Market | Fare captured and parsed | Yes |
| `SOLD_OUT` | Market | Checked, nothing for sale | **Yes** |
| `NO_SERVICE` | Market | No flight operates that pair | Removed from denominator |
| `SOURCE_DISALLOWED` | Policy | We chose not to collect | No — a gap we chose |
| `FETCH_FAIL` | System | Timeout or network failure | No — counted against us |
| `BLOCKED` | System | A bot wall, never bypassed | No — counted against us |
| `PARSE_FAIL` | System | Fetched, page shape changed | No — counted against us |

A sold-out flight and a crashed scraper both look like a blank cell. One is a
fact about the market, the other is a fact about us. Record both as empty and
you can never tell them apart again, and you lose the ability to report honestly
on your own coverage.

The database enforces this — an eighth status is rejected at insert.

---

## 7. Where the data comes from

Eleven airline and aggregator sites are registered. Before any collection, the
system fetches each site's `robots.txt`, saves it verbatim with a SHA-256 hash,
and records a dated verdict. **A source that has not been cleared today cannot
be reached**, and the check happens before the browser is even launched.

Six of eleven currently permit collection. The other five could not be verified —
read timeouts, which is *not* proof of a bot wall and is recorded as exactly
that rather than overstated.

There is **no CAPTCHA handling and no IP rotation** anywhere in the codebase.
`compliance/registry.yml` carries `bypass_captcha: false` and `rotate_ip: false`
as settings that exist so a reader can see they are never flipped.

### The three storage layers

```
bronze  →  the raw response, verbatim, with its SHA-256. Append-only.
silver  →  one row per fare quote, each carrying a status.
gold    →  cell medians, route indices, the published number.
```

Any published value walks back down that chain to the bytes it came from:

```
GET /v1/lineage/2026-09-07/DEL-BOM/21
```

Bronze is files rather than database rows on purpose: an airfare cannot be
collected retrospectively, so the archive has to survive the database being
dropped and rebuilt.

---

## 8. Running it

```bash
pip install -r requirements.txt
python -m playwright install chromium

python -m apix.cli useradd --generate-password
python -m webapp.run
```

Open `localhost:8000`. That one process is the dashboard, the API, the operator
console and the scheduler.

| Command | What it does |
|---|---|
| `apix compliance --check` | Fetch every robots.txt, write today's verdicts |
| `apix collect --today --live` | Collect the 30 cells |
| `apix load` | Raw files into the clean table |
| `apix index` | Build the index |
| `apix demo` | All of the above, then serve |
| `apix serve` | Web app and scheduler |
| `apix useradd` | Create an operator account |
| `pytest tests/` | 53 tests |
| `python scripts/dry_run.py` | 10 counted cold starts |

Collection runs daily at **20:00 IST**. The slot is fixed because fares move
through the day — a series collected at 09:00 one day and 21:00 the next
measures the clock as much as the price. If the machine was asleep at the slot,
a catch-up run covers it.

---

## 9. The API

Two tiers. `/public/*` is open and rate limited, because a published statistical
series is public information — it is what the dashboard reads. `/v1/*` is the
documented integration surface and needs a key.

The key is not there to keep anyone out. It makes bulk access attributable,
rate-limitable and revocable, and lets us answer "who read what, when".

```bash
curl -H "Authorization: Bearer apix_live_..." localhost:8000/v1/apix/latest
curl -H "X-API-Key: apix_live_..."            localhost:8000/v1/apix/series
```

Keys are 256 bits of randomness, shown once at creation, stored only as a
SHA-256 hash. A lost key is rotated, not recovered. Scopes (`read:index`,
`read:lineage`, `read:compliance`) are enforced server-side.

Interactive schema at `/docs`.

---

## 10. Questions you will be asked

**Which index formula is this, and does it have a name?**
Two, at two levels. Booking windows combine by geometric mean — a Jevons index,
the standard elementary aggregation in CPI construction. Routes combine by
weighted arithmetic mean with fixed weights, which makes the overall form
Laspeyres-type; strictly a **Lowe index**, since the weights come from a
different period than the price base.

**Why the median instead of the average?**
Fare distributions are lopsided. On one route on one date we measured ₹6,090 up
to ₹24,056. The average is around ₹8,900 — a price almost nobody paid. The
expensive fares are real, which is why they are flagged and kept rather than
deleted. Deleting them would be editing the market.

**Why do windows multiply but routes add up?**
By the time windows are combined they are ratios, and ratios multiply. Routes
carry expenditure weights — a real share of what travellers spend — and budget
shares add. Getting that distinction right is the difference between a scraper
and an index.

**Where is the machine learning?**
There is none, deliberately. This measures, it does not predict. A model makes
the number harder to audit, and a statistical office has to defend every figure
it publishes.

**The problem statement asks for CAPTCHA handling and IP rotation.**
The same statement also requires robots.txt and terms-of-service compliance.
Both cannot hold at once. We built the permission-tiered version and report the
sources that refuse as a finding about which parts of the market can be observed
at all.

**What happens if a site blocks you for two days?**
Those cells are recorded as `BLOCKED`. Coverage falls, the grade drops, and the
series says so rather than quietly inventing a number. Because the raw responses
are kept immutably, fixing the collector afterwards recovers the history.

**What if a site redesigns its page?**
Rows become `PARSE_FAIL` and coverage falls. The parser also re-finds fare
elements by shape rather than by class name, so a redesign degrades instead of
breaking — and it reports which strategy it used, so a fallback never passes
silently as a healthy parse. There is a test that renames every class on the
page and checks we still recover the fares.

**Six routes out of about 1,100 city pairs — is that enough?**
Answer per route, not in total. Five observations a day on one route is roughly
150 a month, against one national monthly figure. Adding a route is one line of
configuration.

**How much of this is real?**
The compliance checks are real and dated. The collection is real — 30 cells a
day from a permitted source, 5,518 individual fares on the day shown. The
official comparison series is real published data. The longer history behind the
recent days is generated from a documented model, labelled at every layer, and
drawn dashed so it cannot be mistaken for measurement.

**Why does the daily index move more than the official monthly one?**
Partly because it should — a daily series picks up movement a monthly average
smooths away. But partly because every booking window shifts its departure date
forward by a day each morning, so the whole basket rotates through the weekly
fare cycle. Measured over the generated history that is worth 13.3 index points
between the cheapest and dearest weekday. It is recorded as a stated limitation;
the standard treatment is a seven-day moving average published alongside the raw
series.

**Why SQLite?**
It is the demo profile — it installs nowhere and cannot fail on stage.
PostgreSQL is the production target and `db/schema.postgres.sql` is what that
costs: JSONB with a GIN index for the raw archive, `NUMERIC(10,2)` for money
instead of a float that loses paise, `TIMESTAMPTZ`, the status vocabulary as a
declared ENUM instead of a CHECK list copied into four tables, monthly range
partitions on Bronze, and real schemas so a read-only consumer can be granted
the published index without the raw archive. The application code does not
change; it goes through SQLAlchemy.

---

## 11. Known limitations

Stated here so nobody has to find them.

1. One real collection day so far. Everything before it is generated history,
   labelled at every layer.
2. Route weights are equal and flagged provisional, pending DGCA city-pair data.
3. Single-day base in v0.1; becomes a 7-day mean at v0.2.
4. Six routes of roughly 1,100 city pairs.
5. Five of eleven registered sources could not be verified.
6. The daily series carries an unremoved day-of-week cycle (see above).
7. The live source returns multiple fare products per itinerary. v0.1 keeps
   every quote as a distinct observation and does not yet separate fare
   families; a deduplication policy needs to be agreed rather than invented.
8. The brief asks for a 30-day backtest against DGCA monthly average fares. We
   do not hold that dataset. The hand-checked panel is the substitute, and it
   is a substitute.
