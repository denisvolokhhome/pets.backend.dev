# Load testing (Locust)

Never point this at production — it creates accounts, favorites and messages.

## Setup

```bash
pip install locust
# A production-like server (no --reload, several workers, DEBUG=false)
DEBUG=false uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 4 --no-access-log
# Accounts (40 pet seekers, 10 breeders) -> loadtest/accounts.json
python loadtest/seed_users.py --host http://localhost:8001
```

## Run

```bash
locust -f loadtest/locustfile.py --host http://localhost:8001 \
       --headless -u 200 -r 10 -t 3m --csv loadtest/results/run200
```

The traffic mix is 70% anonymous visitors (search, breeder profiles, offspring pages, pricing),
20% signed-in pet seekers (polling, favorites, messages) and 10% breeders (management views).
Every simulated user sends its own `X-Forwarded-For` so per-IP rate limits behave like distinct clients.

### Cleanup after a run

```sql
DELETE FROM notifications WHERE related_id IN (SELECT id FROM messages WHERE content LIKE 'Load-test inquiry%');
DELETE FROM messages WHERE content LIKE 'Load-test inquiry%';
```

## Results — 2026-10-04 (local, single MacBook, 4 uvicorn workers, dev dataset)

| Users | Requests | Failures | RPS | p50 | p95 | p99 | max |
|------:|---------:|---------:|----:|----:|----:|----:|----:|
| 50  | 2,139  | 1 (connection reset) | 18 | 11 ms | 260 ms | 460 ms | 1.3 s |
| 200 | 11,990 | 0 | 68 | 30 ms | 1.4 s | 2.7 s | 5.3 s |

No server errors were logged. Locust, Postgres, Redis and the API all shared one laptop, so
absolute numbers are pessimistic; the **relative** hot spots are what matter.

Slowest endpoints at 200 users (p50 / p95):

| Endpoint | p50 | p95 |
|---|---:|---:|
| `POST /api/favorites/offsprings/{id}` | 1.7 s | 5.1 s |
| `DELETE /api/favorites/offsprings/{id}` | 1.1 s | 2.9 s |
| `POST /api/messages/offspring/{id}` | 970 ms | 2.5 s |
| `GET /api/breeds` | 780 ms | 2.9 s |
| `GET /api/offsprings/public/{id}` | 730 ms | 2.5 s |
| `GET /api/users/breeder/{id}/public` | 490 ms | 2.6 s |

## Findings / recommendations

1. **Eager loading on `User`** — `app/models/user.py` declares 11 relationships with
   `lazy="selectin"` (pets, breedings, messages sent/received, notifications, favorites…).
   Every `User` load — including the auth lookup on *every* signed-in request — pulls all of
   them, and `Pet`/`Breeding`/`Offspring` cascade further. Cost grows with each account's
   history. Switch these to `lazy="select"`/`"raise"` and load explicitly with
   `selectinload()` where needed (needs a careful pass for async `MissingGreenlet` errors).
2. **`/api/breeds`** — ~0.5 s for a static 64 KB list even when idle. Cache it (Redis or
   in-process) and add `Cache-Control`. The app also calls it without a trailing slash, which
   costs an extra 307 redirect round-trip.
3. **Writes that notify** (favorite, message) are the slowest calls — they create a
   notification and queue an email in the request. Fine at current scale; move to a background
   worker if they become hot.
4. **Rate limits trust `X-Forwarded-For`** — the reverse proxy must overwrite (not append) it,
   otherwise clients can bypass per-IP limits. The login endpoint has no rate limit at all.
5. Re-run against staging hardware (separate DB host, production worker count) before launch
   to get absolute capacity numbers.
