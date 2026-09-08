# Jury prep — APIx, 8 September 2026, 15:00

Jury: **Om sir** and **Nikita ma'am**. Reported style: not aggressive, but
**heavy weighting on technical questions**. At least four people must speak.

Live site: **https://apix-fz3l.onrender.com**

---

## The three sentences everything else hangs off

Learn these. If you only remember one thing, remember the first.

> **India already measures airfares. It publishes one number, for the whole
> country, once a month, at weight 0.08 in the consumer basket. We publish
> thirty numbers a day, per route, per booking window.**

> **This is a measuring instrument that happens to use the web. It is not a
> scraper that happens to compute an average.**

> **Every number we publish carries how complete it was, how confident we are,
> and a path back to the raw bytes it came from.**

---

## Who answers what

Never let one person answer everything. If a question lands on the wrong
person, hand it over out loud: *"That's Bharat's layer, he'll take it."* That
looks like a team, not a rehearsal.

| Area | Owner | Backup |
|---|---|---|
| Collection, compliance, the browser, the API | **Mayank** | Bharat |
| Database, loader, index engine, dashboard | **Bharat** | Mayank |
| Why this matters, CPI context, MoSPI framing | **3rd speaker** | Mayank |
| What exists already, why ours differs, what's next | **4th speaker** | Bharat |

The third and fourth speakers do not need to know any code. Their sections are
written out in full at the end of this document and can be learned in an hour.

---

## THE HARD ONES

### "Did you use AI to build this?"

**Answer yes. Immediately, without flinching.** Then take control of what the
answer means.

> "Yes. We used Claude as a coding assistant throughout, the same way you'd use
> an IDE or Stack Overflow, and we're happy to talk about exactly where.
>
> What it didn't do is make the decisions. Three examples.
>
> One: we chose to obey robots.txt even though the problem statement asks for
> bot-evasion techniques. Those two things contradict each other. We decided
> that a government statistical product cannot be built on access we don't
> have permission for, so we collect from six sources and we publish the five
> we couldn't clear as a visible gap. That's a judgment call, and it cost us
> coverage.
>
> Two: we found a contradiction between our own methodology document and our
> own code, about whether outlier fares stay in the median. We had to decide
> which one was right, and defend it. We kept them in, and the document now
> records that the number would have been 102.669 instead of 102.240 under the
> other rule.
>
> Three: there's no machine learning in this project at all, on purpose. That
> was the most debated decision we made.
>
> The code was written fast with assistance. The reason it's built this way
> is ours."

**Do not say:** "we only used it a little", "just for boilerplate", "we wrote
it all ourselves". If they ask to see the repo, the commit history is right
there. Getting caught understating it is far worse than admitting it.

**If they push: "so what did YOU actually do?"**

> "We decided what to measure, and what counts as having measured it. Six
> routes, five booking windows, one adult, economy, one-way, cheapest available,
> at a fixed time every day. We decided that a sold-out flight and a crashed
> collector are different facts and must never be recorded the same way. We
> decided the base date, the aggregation formula, and that outliers get flagged
> and kept rather than deleted. And we wrote down every limitation we know
> about, including the ones that make us look worse."

---

### "How did you build something this complex without a mentor?"

Don't be defensive. This is a compliment shaped like a question.

> "We split it clean. I own collection, compliance and the API; Bharat owns the
> database, the loader and the index engine. We agreed the contract between the
> two layers first, in writing, before either of us wrote code: seven status
> values, a fixed record format with fourteen fields, and a rule that raw data
> is never edited. After that we could work in parallel without blocking each
> other.
>
> For the statistics we didn't invent anything. We used the same methods
> official indices use, and we can name the sources: the geometric mean across
> booking windows is a Jevons index, which is how CPI builds its elementary
> aggregates. The outlier rule is Iglewicz and Hoaglin's modified Z-score. We
> checked our approach against how the US Bureau of Labor Statistics and
> Eurostat publish their airfare series.
>
> And we checked ourselves. There's a test that recomputes the published index
> from the raw rows without using our own engine, because otherwise the engine
> would just be proving it agrees with itself. The two match to four decimal
> places."

---

### "What transformer / model / algorithm did you use?"

This one has caught teams out. **The answer is: none, and that's the point.**

> "None. There's no machine learning in this project, and that's deliberate,
> not a gap.
>
> A model would make the number harder to defend. If MoSPI publishes a figure
> and someone asks 'why is it 94.26 today', the answer has to be a chain of
> arithmetic anyone can redo by hand. Ours is: take the median of the fares in
> each cell, divide by the same cell on the base day, take a geometric mean
> across the five booking windows, then a weighted average across the six
> routes. You can check that in a spreadsheet. We did, and it matches our code
> to four decimal places.
>
> A neural network cannot be audited that way. A statistical office has to
> defend every figure it publishes, sometimes in Parliament.
>
> This measures. It doesn't predict. If you asked us to forecast next month's
> fares, that's when you'd want a model, and that's a different product."

**If they say "so where's the innovation?"**

> "In the measurement design, not the algorithm. Nobody publishes airfares
> daily at route level anywhere in the world. The reason isn't that it's
> computationally hard, it's that nobody built the collection discipline to do
> it honestly. That's what we built."

---

### "Is there anything like this already? Why is yours better?"

Don't say "there's nothing like it". There is, and they may know it.

> "Four things exist, and each does part of it.
>
> **India's own CPI** has an air fare item, monthly, national, weight 0.08. It's
> real and it works, it just can't answer route-level questions.
>
> **DGCA** publishes monthly average fares. Also monthly, limited route detail,
> no API.
>
> **US BLS and Eurostat** both publish airfare indices. Monthly, national, not
> route-level. Their methods are public, and we followed them.
>
> **Skyscanner, MakeMyTrip and so on** have live route-level prices. But they
> are not statistical products: no published methodology, no fixed basket, no
> weights, no continuous series, and the number changes if you refresh.
>
> So the gap is real: daily, route level, with a published method and an
> auditable trail. We're not better than CPI, we're an input to it. The framing
> in the problem statement is 'augment', and that's exactly right."

---

### "How do we know your data is real?"

This is your strongest moment. **Do it live rather than answering.**

Open the dashboard → **The basket** tab → click any cell in the heatmap.

> "This is the median for Delhi–Mumbai at 21 days out. Click it and you get the
> fares behind it, the parse that produced them, and the SHA-256 hash of the
> raw page we stored at collection time. The raw file is in our repository. You
> can download it and hash it yourself."

Then: **What we missed** tab.

> "And this is what we didn't manage to collect, and whose fault each gap was."

---

## THE TECHNICAL ONES

### "Why the median and not the average?"

Plain language, with the real number:

> "On 3 September, one Delhi–Mumbai search returned 221 fares. The cheapest was
> ₹6,090, the dearest ₹24,056. Same route, same day, same seat type.
>
> The average of those is about ₹8,900, which is a price almost nobody in that
> search actually paid, because a handful of very expensive last-minute seats
> drags it upward. The median is ₹7,675, which is roughly what a normal person
> booking that flight would see.
>
> Fare distributions are lopsided in one direction. The median doesn't care."

### "Why a geometric mean across windows, but a normal average across routes?"

This is the question that separates "built a scraper" from "built an index".
Mayank or Bharat only.

> "Different things are being combined.
>
> Across booking windows, we're combining **ratios**. Each window is measured
> against its own starting point, so they're multiples, and multiples combine by
> multiplying. If one window doubles and another halves, the honest answer is
> 'no change' — a geometric mean gives exactly 100. A normal average would say
> 125, which is wrong. This form is called a Jevons index and it's what CPI uses
> for its elementary aggregates.
>
> Across routes, we're combining **shares of spending**, like a household
> budget. Budget shares add up. So that one is a weighted arithmetic mean,
> Laspeyres-type.
>
> Windows multiply, routes add."

### "What are your weights?"

**Tell the truth. This is a weakness, and owning it scores better than hiding it.**

> "Equal, one-sixth each, and every value we publish is flagged
> 'weights provisional' in the database and on the page.
>
> Proper weights need passenger volume per city pair. The brief points at DGCA
> for that. We downloaded twelve DGCA reports and none of them contain fare or
> per-route passenger data — they have traffic totals, load factors,
> cancellations and on-time performance. So rather than invent plausible-looking
> weights, we left them equal and marked them provisional. The moment we get
> that dataset, it's one configuration change and the whole series recomputes."

### "How does the scraping actually work?"

Mayank.

> "We drive a real Chromium browser with Playwright, but we don't read the
> screen. We listen to the network underneath it. When the page loads its
> results, it fetches its own fare data as JSON, and we capture that response
> before it's rendered.
>
> That matters for two reasons. It's already structured, so base fare, taxes and
> total come separated instead of being scraped out of text. And it survives a
> redesign: if they move the buttons around tomorrow, our parser doesn't break,
> because we were never reading the layout.
>
> We also store the raw response, unedited, before we parse anything. If our
> parser turns out to be wrong in three weeks, we can re-parse three weeks of
> history."

### "What happens when a website blocks you?"

> "We record it and publish it. `BLOCKED` is one of our seven status values.
>
> What we don't do is get around it. No CAPTCHA solving, no IP rotation, no
> pretending to be a different browser. The problem statement asks for
> bot-evasion techniques and also for robots.txt compliance, and those two
> can't both be satisfied. We chose compliance, and we report the cost of that
> choice on the dashboard: six of eleven sources cleared."

### "Why SQLite and not a real database?"

Bharat.

> "Because Docker, WSL2 and Postgres weren't installed on the build machine, and
> installing them meant two reboots the day before a demo.
>
> The production schema is written and it's in the repository as
> `db/schema.postgres.sql`. The same code runs against either, switched with one
> environment variable. SQLite is the demo choice, not the architecture."

### "What's the difference between your seven statuses?"

Anyone. This is the most quotable idea you have.

> "A sold-out flight and a crashed scraper both leave an empty cell. They are
> completely different facts. One is the market telling us something. The other
> is us failing.
>
> If you record both as blank, your table looks complete and your index can no
> longer tell you how well it measured anything. Worse, every silent failure
> starts to look like a quiet market.
>
> So there are seven statuses in three groups: what the market said, what we
> chose not to collect, and what we broke. There is no 'null' option. The
> database physically rejects an eighth value."

**True story worth telling if it fits:** *"This caught a real bug. On 8
September our compliance gate refused all thirty cells because the day's check
hadn't run yet. Because that refusal was recorded as a policy decision rather
than an empty cell, we could see the day was unmeasured and re-collect it the
same night. If it had been stored as blank, we'd have lost the day."*

### "Where does your historical data come from?"

**Say this before they ask. Never let them discover it.**

> "Two sources, and they're never mixed. We have three days of real collection,
> 3, 4 and 8 September. Behind that there are 91 days of history generated from
> a documented model, and every one of those rows is labelled SIMULATED in the
> database, drawn as a dashed line on the chart, and computed separately. No
> real number is ever derived from a generated one.
>
> The seasonal shape in that generated history isn't invented either, it's
> interpolated from MoSPI's own published airfare index."

### "Why only three days? Why only six routes?"

> "Three days because airfares can't be collected retrospectively. There's no
> archive to go back for. We started on 3 September, and we lost 5, 6 and 7 to
> a bug we've since fixed, which is recorded rather than hidden.
>
> Six routes because six routes collected properly is worth more than sixty
> collected badly. Adding a route is one line in a config file. The hard part
> was never the number of routes, it was the discipline around each observation."

### "How do we know your index is calculated correctly?"

> "There's a test that recomputes the published index from the raw database
> rows using only the formulas in our methodology document, without importing
> our index engine at all. If we imported the engine, we'd only be proving the
> engine agrees with itself. All three days match to better than 0.0001 index
> points."

---

## PLAIN-LANGUAGE CHEAT SHEET

Use these if a jury member isn't technical, or if you get stuck.

| Term | Say it like this |
|---|---|
| **Price index** | "A number that shows how prices moved, not what they are. We set the first day to 100. Today is 94.26, so fares are about 6% below where we started." |
| **Basket** | "The fixed shopping list. Ours is six routes at five booking distances. It never changes, so any movement is the price moving, not the list." |
| **Booking window** | "How far ahead you're buying. T+21 means a flight leaving in 21 days." |
| **Median** | "The middle price. Half cost more, half cost less. It ignores the few crazy ones." |
| **Coverage** | "Out of the thirty prices we were supposed to collect today, how many we actually got. Today, all thirty." |
| **Confidence grade** | "A school grade on the number. A needs 90% coverage and two independent sources. We're at B: complete, but one source." |
| **Outlier** | "A price far away from the others in the same search. We mark them and keep them, because they're usually real." |
| **Bronze / Silver / Gold** | "Raw, cleaned, published. The raw layer is never edited, so we can always go back." |
| **robots.txt** | "A file every website publishes saying which parts automated visitors may read. We check it every day and store a copy." |
| **API** | "A URL that returns the data instead of a webpage, so another system can consume our numbers directly." |
| **Jevons index** | "Multiplying instead of averaging, used when you're combining ratios. CPI does the same thing." |

---

## THE TWO NON-TECHNICAL SPEAKERS

Learn one of these. You do not need to understand the code.

### Speaker 3 — why this matters

> "Air travel sits inside India's Consumer Price Index as one number, published
> once a month, at a weight of 0.08. That number is real and it moves: between
> June and July last year it fell 4.4% in a single month.
>
> But it's one number for the whole country. It can't tell you whether Delhi to
> Mumbai moved or Bangalore to Hyderabad. It can't tell you whether it hit
> people who book early or people who book late. And it arrives weeks after the
> month it describes.
>
> Meanwhile over 90% of domestic tickets are sold online, where prices change
> several times a day. We're measuring where the prices actually live, at the
> frequency they actually move."

**If asked anything technical:** *"That's Mayank's area, he'll take it."*

### Speaker 4 — what we found, and what's next

> "One thing surprised us. Everyone assumes booking earlier is cheaper. Across
> our six routes the cheapest point isn't the earliest, it's 21 days out. The
> median there is ₹9,043, and at one day out it's ₹14,781, a spread of 63%. And
> it goes back up at 45 days.
>
> We want to be careful here: that's three days of data on six routes, so it's
> what we observed, not a law of nature. But no official index anywhere
> publishes booking-window curves, which means nobody had checked.
>
> Next is more days, more routes, and proper route weights once we have
> passenger volume data. The architecture doesn't change for any of that."

---

## RULES FOR THE ROOM

1. **Never bluff.** "I don't know, that's Bharat's layer" is a complete answer.
   A wrong confident answer about your own system is the only thing that
   actually loses marks here.
2. **Hand questions over out loud.** It makes you look like a team.
3. **Say the limitation before they find it.** Three days of data, six routes,
   provisional weights, simulated history, five sources uncleared. Every one of
   those sounds like honesty when you say it and like a cover-up when they do.
4. **Use the live site.** Don't describe the lineage feature, click it.
5. **Numbers, not adjectives.** Not "a lot of fares", but "5,323 fares priced
   today". Not "very compliant", but "six of eleven sources cleared, verdicts
   stored with SHA-256".
6. **If a question is out of scope, say so and say why.** "We deliberately
   didn't build forecasting. It measures, it doesn't predict."

---

## NUMBERS TO KNOW COLD

| | |
|---|---|
| Today's index | **94.26**, down 7.80% |
| Coverage | **30 of 30 cells**, 100% |
| Confidence | **B** (complete, single source) |
| Fares priced today | **5,323** across 7 carriers |
| Median fare today | **₹12,399**, range ₹4,074 to ₹54,641 |
| Sources cleared | **6 of 11** |
| Real collection days | **3** (3, 4 and 8 September) |
| Generated history | **91 days**, labelled, dashed, never mixed |
| Basket | **6 routes × 5 windows = 30 observations/day** |
| Observation slot | **20:00 IST**, fixed |
| CPI air fare weight | **0.08**, monthly, national |
| CPI air fare move | **−4.4%** June to July 2025 |
| Cheapest booking window | **T+21**, ₹9,043 vs ₹14,781 at T+1 (63% spread) |
| The spread example | DEL–BOM, 3 Sep: ₹6,090 to ₹24,056, 221 quotes |
| Automated tests | **57 passing** |
| Hand-check agreement | **0.0001** index points |
