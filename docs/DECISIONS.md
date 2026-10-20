# Decisions (append new ones at the bottom)

| # | Decision | Why |
|---|---|---|
| 1 | Architecture diagram is the agreed plan | Team decision |
| 2 | Website first, mobile app later | Faster to ship; one codebase |
| 3 | Web is an installable **PWA** with offline + low-data support | Fast on Android/iOS, tiny download vs. app stores |
| 4 | Backend "services" are modules inside **one FastAPI app** | Same boundaries as the diagram, one thing to deploy and debug. Split into separate services only if there is a real need. |
| 5 | API contract (`docs/openapi.yaml`) and DB migrations are frozen; changes via lead-approved PR | Lets frontend/backend/data work in parallel without breaking each other |
| 6 | Plain-SQL migrations (`db/migrate.py`), PostGIS from day one | Simple to read and review; map/geo data needs it |
| 7 | `/sync` endpoint feeds an IndexedDB (Dexie) cache | One small request keeps the offline cache fresh |

## Deferred (not forgotten)
- Student verification method (matric number? school email?)
- Data privacy (NDPR) review and privacy policy
- Hostels/accommodation, AI assistant (RAG), notifications: phase 2/3
- Hosting, domain, monitoring

## 8. `/sync` is paged, with an overlap window on `server_time`

- **Decision:** `GET /sync` returns pages. It takes `cursor` (opaque, takes precedence over
  `since`) and `limit` (1–1000, default 500, counted across all collections). Every response
  has `next_cursor`, which is null on the last page. Clients must loop until it is null.
- **Why paging:** a first sync of all reference data and announcements can be large. One
  unbounded response must stay under Vercel's 4.5 MB response limit, and it is slow and
  costly on low-data phones. Row caps keep each response small and predictable.
- **Why an overlap window:** PostgreSQL `now()` returns the transaction start time, so a slow
  transaction can commit a row with an `updated_at` older than a `server_time` a client already
  holds. The client would never receive that row. Subtracting 60 seconds from the stored
  `server_time` makes the next sync re-fetch recent changes. Re-received rows are idempotent,
  since saving by id is safe to repeat.
- **Limits of the overlap:** it covers transactions shorter than 60 seconds. A longer transaction
  still needs `clock_timestamp()` in `set_updated_at()`, planned as a separate migration.
- **Rules that follow:**
  - Store `server_time` only from the last page. Storing it earlier can skip rows that later
    pages would have sent.
  - `full: true` only on the first page of a full sync, so clients clear their cache once.
  - Cursors expire after 24 hours and return 422, so the client restarts from its stored `since`.
  - The web client (`offline.ts`) must loop on `next_cursor` before the API ships with paging.
    Until then, large syncs silently lose rows.
- **Open:** publishing and expiry happen with time, and `updated_at` does not change, so a
  scheduled announcement is not sent when it is published. Expired announcements are never
  tombstoned. Needs a decision (for example, sort announcements by `greatest(updated_at,
  published_at)`).
