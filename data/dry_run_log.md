# APIx dry-run log

_Monday 07 September 2026, 12:24_

**10 of 10 runs passed.** Average cold start 2.6s.

Each run deletes the database, reapplies both schemas, reparses the whole
raw archive, recomputes the index, boots the API, serves every page, calls
every open endpoint, walks the lineage back to a real SHA-256, and checks
that the keyed API and the admin console refuse an anonymous caller.

| Run | Result | Seconds | What broke |
|---|---|---|---|
| 1 | PASS | 2.6 | — |
| 2 | PASS | 2.6 | — |
| 3 | PASS | 2.5 | — |
| 4 | PASS | 2.5 | — |
| 5 | PASS | 2.6 | — |
| 6 | PASS | 2.6 | — |
| 7 | PASS | 2.5 | — |
| 8 | PASS | 2.5 | — |
| 9 | PASS | 2.7 | — |
| 10 | PASS | 2.5 | — |
