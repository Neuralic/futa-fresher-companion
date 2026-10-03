# AGENTS.md — rules for every AI tool working in this repo

Read this fully before writing any code. These rules exist so six people (and their AIs) can
build in parallel without breaking each other. If a task conflicts with a rule, STOP and tell
the human; do not work around it.

## Project
FUTA Fresher Companion: a PWA that helps new FUTA students navigate campus, find people and
information, and stay informed. Priorities: **fast on cheap Android/iOS phones, low data use,
works offline, information is verified and dated.**

## Stack
- `web/`: React + TypeScript + Vite PWA (vite-plugin-pwa/Workbox, Dexie for offline data)
- `api/`: FastAPI (Python 3.12), psycopg 3, one router module per backend service
- `db/`: PostgreSQL 16 + PostGIS, plain SQL migrations (`db/migrations`), run by `db/migrate.py`
- `docs/openapi.yaml`: the API contract (source of truth)

Architecture note: the diagram's "microservices" are separate **modules inside one FastAPI app**
(`api/app/routers/*`), not separate deployables. Keep module boundaries clean; do not import one
router from another.

## Ownership: stay in your own folder
| Area | Folder | Owner role |
|---|---|---|
| Backend / DB | `api/`, `db/` | Backend |
| Frontend | `web/` (except below) | Frontend |
| Maps | `web/src/pages/MapPage.tsx`, `web/src/components/map/`, `db` path/building data | Maps/GIS |
| Data & verification | `data/` | Admin/Data |
| Design | `docs/design/` | UI/UX |
| Contract, CI, rules | `docs/openapi.yaml`, `.github/`, `AGENTS.md` | Lead |

Only edit files in the area your human owns. If you need a change elsewhere, say so and let the
human raise it with the owner.

## Hard rules (never break)
1. **The contract is frozen.** Never change `docs/openapi.yaml` or add/remove/rename an endpoint
   unless the human says the lead approved it. `api/tests/test_contract.py` enforces this.
2. **Database changes = a new numbered file in `db/migrations/`.** Never edit a merged
   migration, never alter the DB by hand, never use ORM auto-create.
3. **Types come from the contract.** In `web/`, run `npm run gen:api`; never hand-write API types.
4. **No new dependencies** (npm or pip) without lead approval. Pre-approved: what is already in
   `package.json` / `requirements.txt`.
5. **No secrets in git.** Config goes in `.env` (ignored); update `.env.example` with names only.
6. **Never push to `main`.** Work on a branch (`feat/<area>-<thing>`), open a PR.
7. **Personal data (NDPR):** never log passwords, tokens, phone numbers, or emails. Hash
   passwords with argon2. Class-rep `contact` is returned only when `consent_given` is true.
   Lecturer `email` is the official school email only.

## Performance rules (low-data is a feature)
- First-load JS+CSS must stay under **150 KB gzipped** (`npm run check:bundle` fails otherwise).
- Lazy-load heavy screens (map, admin) with `React.lazy`. Never import a map library at top level.
- No web fonts (system fonts only). Images: WebP/AVIF, lazy, sized. Video: opt-in, never autoplay.
- List endpoints must paginate (`limit`/`offset`). Responses are gzip-compressed already.
- Read data through the offline layer (`web/src/lib/offline.ts`, Dexie) so screens work offline.
- Every screen must handle: loading, empty, error, and offline states.
- Show `verification.status`, `source` and `updated_at` wherever information is displayed.

## Backend conventions
- Replace `not_implemented()` stubs in the matching router; keep the route path and method.
- Use `Depends(get_conn)` from `app/db.py`; parameterised SQL only (never f-string SQL).
- Soft-delete: set `deleted_at`; every read query filters `deleted_at IS NULL`.
- `/sync` must return rows with `updated_at > since` plus ids deleted since then.
- Authorisation by role: `student`, `class_rep`, `department_admin`, `faculty_admin`, `sug`,
  `super_admin`. Admin roles can only manage their own faculty/department scope.

## Before you say "done"
- API: `cd api && pytest -q` and `ruff check api db` (from repo root)
- Web: `cd web && npm run build && npm run check:bundle`
- Run the app and try the feature yourself. Tests passing is not the same as it working.
- Keep PRs small (one task), and describe what you changed and how you verified it.

## When unsure
Ask the human. Prefer a small, boring, readable solution over a clever one. A student teammate
must be able to understand and fix your code at 11pm before a deadline.
