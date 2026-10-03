# FUTA Fresher Companion

A PWA that helps new FUTA students navigate campus, find the right people and places, and get
verified information, on any phone, with little data, even offline.

```
web/   React + TypeScript PWA        api/   FastAPI backend
db/    PostgreSQL+PostGIS migrations  data/  CSV templates for campus data
docs/  OpenAPI contract, tasks, decisions
```

**Read first:** [`AGENTS.md`](AGENTS.md) (rules for people and AI tools) and [`docs/TASKS.md`](docs/TASKS.md).

## Setup (once)

Needs: Git, Docker, Python 3.12, Node 20+.

```bash
cp .env.example .env
docker compose up -d db                 # PostgreSQL + PostGIS

# API
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r api/requirements.txt
python db/migrate.py                    # create tables
cd api && uvicorn app.main:app --reload # http://localhost:8000/api/v1/docs

# Web (new terminal)
cd web
cp .env.example .env.local              # VITE_USE_MOCKS=true works without the backend
npm install
npm run dev                             # http://localhost:5173
```

## Everyday workflow

1. `git checkout main && git pull`
2. `git checkout -b feat/<area>-<thing>`  (e.g. `feat/api-auth`)
3. Work only in your own folder. Give your AI tool `AGENTS.md`, `docs/openapi.yaml` and the files it needs.
4. Run the checks (below), commit, push, open a Pull Request.
5. CI must be green and the lead (or the code owner) approves. Then merge.

**Checks**
- API: `ruff check api db` (repo root) and `cd api && pytest -q`
- Web: `cd web && npm run build && npm run check:bundle`

## The contract

`docs/openapi.yaml` defines every endpoint. It is frozen: changes need lead approval.
- Backend: implement exactly what it says (a test fails if routes drift).
- Frontend: `cd web && npm run gen:api` regenerates TypeScript types from it.
- Need something new? Open an issue, the lead updates the contract first, then you build it.

## Database changes

Add `db/migrations/00N_description.sql`, run `python db/migrate.py`. Never edit a merged migration.

## One-time lead setup

1. Create the GitHub repo, push, invite teammates.
2. Replace the `@PLACEHOLDERS` in `.github/CODEOWNERS` with real usernames.
3. `./scripts/protect-main.sh OWNER/REPO` (needs GitHub CLI; private repos need a paid plan,
   or set the same rules manually under Settings → Branches).
4. Replace the placeholder icons in `web/public/icons/` with the real logo.
