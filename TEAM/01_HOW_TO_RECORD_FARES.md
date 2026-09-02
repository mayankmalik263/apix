# How to record fares — Kritika, Riya, Vidushi

**Read this once. It takes about 20 minutes a day. Do it on 2, 3 and 4 September.**

You are not helping with the project. You are producing the only genuinely
human-verified data we have, and it is the thing that lets us say our program
tells the truth. If the scraper breaks, your sheet *is* the dataset.

---

## Your file

Open the sheet with your name on it:

| Person | Routes | File |
|---|---|---|
| **Kritika** | DEL–BOM, DEL–BLR | `data/ground_truth_2026-09-02_kritika.csv` |
| **Riya** | BOM–BLR, DEL–CCU | `data/ground_truth_2026-09-02_riya.csv` |
| **Vidushi** | BLR–HYD, MAA–DEL | `data/ground_truth_2026-09-02_vidushi.csv` |

Open it in Excel or Google Sheets. There are **10 rows** already filled in with
the route and the exact date to search for. You only fill the empty columns.

There is a separate file for the 3rd and the 4th. Use the right day's file.

**Airport codes:** DEL = Delhi · BOM = Mumbai · BLR = Bengaluru ·
CCU = Kolkata · HYD = Hyderabad · MAA = Chennai

---

## What to do, per row

1. Open a flight search site. **Use the same site every time** — write which one
   in the `website` column. Any of these is fine:
   *EaseMyTrip · Cleartrip · Ixigo · SpiceJet · Akasa Air · Air India Express*

2. Search exactly this:

   | Setting | Value |
   |---|---|
   | From → To | the `route_code` in your row, e.g. DEL → BOM |
   | Departure date | the `departure_date` in your row — **already worked out for you** |
   | Trip type | **One way** |
   | Passengers | **1 adult** |
   | Class | **Economy** |
   | Return date | leave empty |

3. Look at the results. Find the **cheapest** one. Prefer a **non-stop** flight
   if there is one; if every flight has a stop, take the cheapest anyway and
   write `had to take 1 stop` in notes.

4. Fill in your row:

   | Column | What to type | Example |
   |---|---|---|
   | `time_checked` | the time now, 24-hour | `09:15` |
   | `website` | which site you used | `EaseMyTrip` |
   | `airline` | airline name or code | `IndiGo` or `6E` |
   | `flight_no` | flight number | `6E 2134` |
   | `fare_shown` | **number only** | `5432` |
   | `status` | see below | `OK` |
   | `notes` | anything odd | usually blank |

---

## The fare number — get this right

Write the **total price you would actually pay for one adult**, the number
shown before you enter passenger details.

- **Digits only.** `5432`
- **No ₹ sign.** Not `₹5432`
- **No commas.** Not `5,432`
- **No decimals.** Round to the nearest rupee.

If the site shows a price and then adds fees at checkout, use the **first total
price shown on the results page**. Be consistent — the same choice every time
matters more than which choice you make.

---

## The status column — the important bit

**Never leave a row blank.** A blank row tells us nothing. A status tells us
something. Type exactly one of these three words:

| Type this | When |
|---|---|
| `OK` | You found a fare. Write it in `fare_shown`. |
| `SOLD_OUT` | Flights exist on that route and date, but everything is sold out or shows no price. Leave `fare_shown` empty. |
| `NO_SERVICE` | There is genuinely no flight on that route for that date. Leave `fare_shown` empty. |

**Why this matters, in one sentence:** a sold-out flight is a fact about the
market, and our program failing is a fact about us — if you write both as
"blank" we can never tell those apart again.

If the website itself is broken or won't load, write `OK` in nothing — leave
status empty and put `site would not load` in notes. Tell Mayank.

---

## Rules that make the data usable

1. **Check at roughly the same time each day.** Aim for **09:00–10:00**. Fares
   change through the day, so a 9am number and a 9pm number are not comparable.
   Same hour every day is what makes the three days comparable.

2. **Do all 10 rows in one sitting.** Ten searches, about 20 minutes.

3. **Don't skip the expensive ones.** The T+1 row (tomorrow's flight) will look
   absurdly expensive — ₹12,000, ₹15,000. **That is real and it is exactly what
   we are trying to measure.** Write it down. Do not assume it is a mistake.

4. **Don't tidy the numbers.** No rounding to the nearest hundred, no "that
   looks wrong so I'll check another site". Write what the screen says.

5. **If a row takes more than 3 minutes, mark it and move on.** Come back at
   the end. Do not lose 20 minutes to one stubborn row.

---

## When you are done

Send your filled file to Mayank the same morning. **Do not wait until all three
days are done** — send day one on day one. If the sheet arrives on the 5th it
is worth nothing to us.

---

## Common questions

**The price changed while I was looking at it.**
Normal. Write the first one you saw and note the time.

**There are two flights at the same cheapest price.**
Take whichever appears first. Don't agonise.

**The site is asking me to log in.**
Don't log in. Use a different site and write which one you used.

**I can only find a fare with a stop, but the row says nothing about stops.**
Take it. Write `1 stop` in notes.

**I missed the 9am window.**
Do it as soon as you can and write the real time in `time_checked`. Late data
with an honest timestamp is far better than no data, and much better than a
guessed time.

**Do I need to install anything?**
No. A browser and Excel or Google Sheets. Nothing else.
