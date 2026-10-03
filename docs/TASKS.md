# Day-1 tasks

Put names next to roles. Everyone works only in their own folder and opens PRs (see README).

## Start right now (no repo needed)

| Role | Name | Task | Done when |
|---|---|---|---|
| UI/UX | | Mobile-first wireframes: login, home, map, departments/lecturers, announcements, admin panel. Light on images, big tap targets. Save to Figma + export PNGs to `docs/design/`. | Lead has approved the wireframes |
| Maps/GIS | | Walk the campus. Record GPS for gates, faculties, lecture halls, library, hostels, food, health centre. Fill `data/templates/buildings.csv` (use "Share location" or Google Maps long-press for lat/lng). | 30+ key places logged |
| Admin/Data | | Fill the CSV templates in `data/templates/` for ONE faculty first (faculty, departments, lecturers, courses, class reps). Read `data/README.md`. | One faculty complete, every row has a `source` |

## After the lead pushes this repo and sets up branch protection

| Role | Name | Task | Done when |
|---|---|---|---|
| Backend | | Run the setup in README. Implement `/auth/register`, `/auth/login`, `/auth/me` in `api/app/routers/auth.py` (argon2 + JWT). Then `/faculties`, `/departments`, `/announcements` (GET). | Endpoints match `docs/openapi.yaml`, tests added, CI green |
| Frontend | | Run `web/` with `VITE_USE_MOCKS=true`. Build app shell, nav, Login/Register screens, Academics list, Announcements list against the mocks. Add the install-to-home-screen banner for iOS. | Works on a real phone, offline banner shows, bundle under budget |
| Lead | | Branch protection (`scripts/protect-main.sh`), fill `CODEOWNERS`, review PRs, own the contract and migrations. | All teammates can push a PR and see CI run |

## Next
- Data import script (`data/` CSV -> database) with validation
- `/sync` endpoint, then wire the Dexie offline cache to real data
- Map page: MapLibre (lazy-loaded) + campus tiles, then routing
- Admin panel + verification workflow
