# Jury prep — 8 September, 15:00, Group G13

Jury: **Om sir** and **Nikita ma'am**. Reported style: not aggressive, but
**technical questions carry higher weight**. At least four people must speak.
One person answering everything counts against you.

---

## The one-sentence version

Learn this. Everything else hangs off it.

> India measures every airfare in the country with **one number, once a month,
> at weight 0.08 in the consumer basket**. Last year it moved 4.4% between June
> and July, and nobody could say which route, which week, or whether it hit
> people who book early or late. **We publish thirty prices a day** and every
> one of them can be traced back to the page it came from.

Never say "India has no airfare index." It does, and a MoSPI jury knows it.
Saying that loses you the room in one sentence.

---

## Who answers what

Do not let one person take everything. Agreed split:

| Topic | Who |
|---|---|
| Problem, why it matters, the MoSPI number | **Mayank** |
| Collection, compliance, robots.txt, the seven statuses | **Mayank** |
| Database, loader, index maths, the engine | **Bharat** |
| Dashboard, API, deployment, live demo | **Mayank / Bharat** |
| Anything about scope, timeline, division of work | **anyone** |

If a question lands on you and you don't know: *"That's Bharat's layer, he
built it"* and hand over. That looks like a team. Guessing looks worse than
handing over.

**Get the third and fourth voices in early.** Even a short factual answer
("we chose those six routes because they're the highest-traffic domestic
sectors") counts as participation. Brief them on two facts each so they can
speak once with confidence.

---

## The questions they actually asked other teams

### "What transformer did you use?"

**This is the trap, and our answer is the strongest thing we have. Do not
apologise for it.**

> None. There's no machine learning in this at all, and that's a deliberate
> design decision, not a gap.
>
> This is a **measurement** system, not a prediction system. MoSPI has to
> defend every published figure — potentially in Parliament. The moment a
> number comes out of a model, you can't explain why it is what it is. You can
> only say the model produced it.
>
> So we use the same maths the CPI itself uses: a median inside each cell, a
> Jevons geometric mean across booking windows, a weighted arithmetic mean
> across routes. Anyone can recompute our number by hand from the raw data,
> and we ship a test that does exactly that — it agrees with the engine to four
> decimal places.

If they push, *"so where is the innovation?"*:

> The innovation is in **frequency and granularity**, not in the model. Nobody
> in the world publishes a daily, route-level airfare index. Not MoSPI, not the
> US Bureau of Labor Statistics, not Eurostat. Getting a number that a
> statistical office would actually accept is the hard part, and that's a data
> engineering and methodology problem, not a modelling one.

### "Have you used AI?"

**Say yes immediately. Be straightforward. Do not let them catch you hedging.**

> Yes, we used AI as a coding tool, the same way you'd use an IDE or Stack
> Overflow. It wrote code faster than we could type it.
>
> Two things it did not do. It did not make the decisions — which routes, which
> booking windows, median instead of mean, geometric across windows and
> arithmetic across routes, what counts as a failed observation. Those are
> defended in our methodology document with reasons.
>
> And there is **no AI inside the product**. Not one line. Ask me about any part
> of this system and I'll explain what it does and why.

Then *invite the follow-up*: **"Which part would you like me to walk through?"**
That single sentence flips it. It reads as confidence, and it moves the
conversation onto the code you know.

Bharat is right that transparency is the play here. Someone who says "no AI"
and then can't explain their own code gets destroyed. Someone who says "yes,
and here's exactly what I decided myself" doesn't.

### "How did you build something this complex without a mentor?"

> We split it by ownership rather than trying to all work on everything. I own
> collection, compliance and the API. Bharat owns the database, the loader and
> the index engine. We agreed the interface between our two halves first — a
> fixed seven-value status vocabulary and a frozen raw record format — so we
> could work in parallel without blocking each other.
>
> And we didn't invent the methodology. We followed what statistical offices
> already publish: the CPI manual for elementary aggregation, the US BLS and
> Eurostat for how airfares are treated elsewhere, and a standard published
> method for outlier detection. Our job was to apply existing methodology to a
> daily data source, not to invent statistics.

### "Why this problem? How does it solve anything?"

> Air travel is the most volatile thing in the consumer basket and the worst
> measured. The same Delhi–Mumbai seat cost between ₹6,090 and ₹24,056 on the
> same day when we measured it — a four-fold spread. A monthly national average
> cannot see any of that.
>
> A daily route-level index gives MoSPI an early signal on one of the fastest
> moving items in the CPI, months before the monthly figure would show it.

### "How did you arrive at your outcome?"

Lead with the finding. This is your best moment.

> We found something we didn't expect. **The cheapest time to book is not as
> early as possible.** Across all six routes the median fare bottoms out at 21
> days ahead and rises again at 45 days — the curve is U-shaped, not a straight
> line down. The spread between the cheapest and dearest booking window is
> 63.4% for the identical seat.
>
> No official index publishes booking-window curves, so nobody had checked.

**Say "we observed", never "airfares are".** It's three days of data on six
routes. If they ask how confident you are, say exactly that — it's a strength,
not a weakness, that you know the limits of your own data.

### "Is there nothing else in the market? Why is yours better?"

> There are two different things and neither is what we built.
>
> **Statistical indices** — MoSPI's monthly airfare item, DGCA's monthly average
> fare, US BLS airline fares, Eurostat's HICP. All monthly. None route-level.
>
> **Fare comparison tools** — Skyscanner, Google Flights, Ixigo. Real time and
> route level, but they're not indices. No published methodology, no weights,
> no continuous series, no statement of how complete their data was.
>
> APIx is the only one that's daily, route-level, and auditable. Every value we
> publish carries its coverage, a confidence grade, and a link back to the
> stored bytes it came from.

### "What references did you use?"

Have these ready by name:

- **MoSPI CPI press release, Annex-V** — the "Air fare [normal]: economy class
  [adult]" item, weight 0.08, base 2012=100. We extracted the series and
  reproduced MoSPI's own published inflation rates to the decimal.
- **US Bureau of Labor Statistics** — CPI airline fares, series `CUUR0000SETG01`
- **Eurostat** — HICP `CP0733`, passenger transport by air
- **Iglewicz & Hoaglin** — the modified Z-score on median absolute deviation,
  which is our outlier rule
- **Jevons index** — the geometric mean form used for CPI elementary aggregates

---

## Questions they will probably ask, and short answers

**"Is scraping legal? Isn't this a grey area?"**
> We check each source's robots.txt before every run, store the file itself
> with its SHA-256, and refuse anything not cleared that day. Six of eleven
> sources permit us. The other five we could not verify, and we record that as
> a gap rather than pretending we have full coverage. There is no CAPTCHA
> handling and no IP rotation anywhere in the code. If a source says no, we
> don't collect it and we publish that we didn't.

**"You only have three days of data."**
> Correct, and we say so on the dashboard. Three real days plus 91 days of
> generated history that is labelled as generated at every layer, drawn dashed,
> and never used to compute anything real. The system collects thirty more
> observations tonight at 20:00, automatically.

**"Why only six routes?"**
> They're high-traffic domestic sectors covering metro and non-metro pairs.
> Adding a route is one line of configuration — the constraint is politeness
> to the sources, not the code.

**"Why are all the route weights equal?"**
> Because we don't have the data to set them properly. Proper weights need
> city-pair passenger volumes from DGCA, and the reports we could access
> contain traffic and load factors but not fares or pair-level volumes. So
> every published value is stamped `weights_provisional`. We'd rather flag it
> than invent a number.

**"What happens when the airline site changes its layout?"**
> The parser breaks, and the system says so. That cell records `PARSE_FAIL`,
> coverage drops, and the confidence grade falls. It does not silently publish
> a wrong number. And because we store the raw response before parsing
> anything, we can fix the parser and re-derive the whole history from the
> bytes we already have.

**"How do we know your numbers are correct?"**
> Two ways. There's a test that recomputes the published index from the raw
> rows using only the formulas in our methodology document, without touching
> the engine — they agree to four decimal places. And on the dashboard you can
> click any cell and walk it back through the fares it was built from to the
> stored page and its hash. *(Then do it live. It's thirty seconds and it's the
> most convincing thing on the site.)*

**"What's the difference between a sold-out flight and a failed scrape?"**
This is the best idea in the project. Make sure it gets said.
> On screen they look identical — an empty cell. But one is a fact about the
> market and the other is a fact about us. If you record both as blank, your
> index can no longer report honestly on its own reliability, and every silent
> failure starts looking like a quiet market. So every observation carries one
> of seven statuses across three classes: what the market said, what we chose
> not to collect, and what we broke. There is no NULL in the vocabulary.

---

## The live demo — five minutes, in this order

Have these open in tabs **before you start**. Open the site by 14:50 so the
server is awake.

1. **https://apix-fz3l.onrender.com** — the index. 94.26, −7.80%, coverage 30
   of 30, grade B. Say: *"this is live, collected last night."*
2. **When you book** — the U-curve. Your finding.
3. **The basket** → click any cell → the lineage drawer. Show the raw payload
   and the hash. *"This median came from those exact bytes."*
4. **What we missed** — the seven statuses and the compliance table. Answers
   the ethics question before it's asked.
5. **/docs** — the API. *"A statistical office could pull this into their own
   systems tomorrow."*

If the internet fails: everything runs locally with `python -m webapp.run`. Say
plainly that it's running locally and hosting is a detail. Don't fight it.

---

## Three things not to say

1. **"India has no airfare index."** It does. Weight 0.08, monthly.
2. **"The sources blocked us."** Five sources *timed out*. That is not proof of
   a bot wall. Say "we could not verify them."
3. **"Airfares are U-shaped."** *We observed* a U-shape, on six routes, over
   three days.

---

## If you only remember four things

1. No AI in the product, on purpose — a statistical office must defend every
   figure.
2. Thirty prices a day against India's one a month.
3. A sold-out flight and a broken scraper are different facts.
4. Click a cell, see the raw bytes it came from.
