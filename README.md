# GeM Intelligence Dashboard

An independent, read-only dashboard of Government e-Marketplace (GeM) procurement listings:
a Python collector/importer writes to Supabase Postgres, a React site displays the data, GitHub
Actions runs the collector daily and Netlify hosts the site.

> **Status (verified 2026-10-17).** Live GeM collection does **not** work. GeM's security
> gateway blocks automated clients that identify themselves honestly, and this project will not
> impersonate a browser to get past it. The GeM adapter is built and tested on synthetic fixtures,
> but it stays **disabled** behind `GEM_LIVE_ACCESS_APPROVED`. No other public feed of GeM bid
> listings was found (see [docs/SOURCE_FEASIBILITY.md](docs/SOURCE_FEASIBILITY.md)).
> Everything else works today with **CSV/JSON imports** and **clearly labelled synthetic data**.

## Contents

1. [Architecture](#architecture)
2. [Data origins](#data-origins)
3. [Local setup](#local-setup)
4. [Tests, linting, type checks and builds](#tests-linting-type-checks-and-builds)
5. [Importing data](#importing-data)
6. [Supabase setup](#supabase-setup)
7. [GitHub Actions (daily run)](#github-actions-daily-run)
8. [Netlify deployment](#netlify-deployment)
9. [Configuring a live source later](#configuring-a-live-source-later)
10. [Security model](#security-model)
11. [Checklist: what you must provide](#checklist-what-you-must-provide)

## Architecture

```
 GitHub Actions (01:00 UTC daily / manual)          Netlify (static React SPA)
   python -m scraper                                  frontend/dist
     ├─ live adapters  (scraper/sources/gem_*)  ──┐      │  anon key, read-only
     └─ file import    (--import-file)          ──┤      ▼
                                                  ▼   Supabase PostgREST ──► Postgres
                    DATABASE_URL (owner) ──► Postgres  (RLS: public read of display
                                                        columns; admins read run logs)
```

| Path | What it is |
|---|---|
| `scraper/` | Python 3.12 package: `config.py`, `http.py` (paced client, bounded retries), `sources/` (adapters), `normalizers/` (text, dates, URLs), `models.py` (pydantic schema), `changes.py`, `database.py` (idempotent upserts, history), `pipeline.py`, `__main__.py` (CLI), `synthetic.py` |
| `scraper/tests/` | pytest suite. Fixtures are synthetic. DB/RLS tests run against a disposable Postgres |
| `supabase/migrations/` | Schema, RLS/privileges, public read-only functions, data-origin column |
| `supabase/tests/local_supabase_shim.sql` | Minimal Supabase roles/`auth.uid()` emulation for **local/CI test databases only** |
| `frontend/` | React 19 + TypeScript + Vite + Tailwind 4 |
| `data/samples/` | Import templates (placeholder rows only) |
| `.github/workflows/` | `daily-collection.yml` (scheduler), `ci.yml` (tests on push/PR) |
| `netlify.toml` | Build, SPA routing, security headers |
| `docs/SOURCE_FEASIBILITY.md` | What was inspected, what is blocked and why |

**Database tables.** `listings` holds the latest state, deduplicated on `(source_name, dedup_key)`
where `dedup_key` is `id:<source id>` or, failing that, `url:<canonical url>`. `listing_history`
stores field-level changes. `scrape_runs` stores one row per run with per-source results. `admins`
lists the Supabase Auth users allowed to see run logs. Listings are never deleted because they were
missing from a scan. A field that is missing from a new observation keeps its stored value. The only
delete path is `--purge-synthetic`.

## Data origins

Every listing has `data_origin`, and the UI shows it as a badge on every row and on the detail page:

| Origin | Meaning | Source link |
|---|---|---|
| `live` (Live-collected) | Fetched by a live adapter from the original publisher | Official GeM URL |
| `imported` (Imported) | Loaded by the operator from a CSV/JSON file; not verified by this site | Kept only if it is an `https://` URL on `gem.gov.in` or a subdomain |
| `synthetic` (Synthetic demo) | Invented test data; titles always start with `[SYNTHETIC]` | Never; any URL is removed |

The dashboard's freshness indicator counts **live** successes only ("No live collection" until one
happens), shows file imports separately, warns after 36 h without a live success, shows a magenta
banner whenever synthetic records exist, and marks live listings that have not been re-observed recently.
If Supabase is not configured at all, every page shows an explicit "no database connected" notice and no data.

## Local setup

Requirements: Python 3.12, Node.js ≥ 22.12 (CI uses 24), and optionally PostgreSQL 15+ for the database tests.

```bash
git clone <your-repo-url> gem-intelligence
```

```bash
cd gem-intelligence
```

```bash
python3.12 -m venv .venv
```

```bash
.venv/bin/pip install -r scraper/requirements-dev.txt
```

```bash
npm --prefix frontend ci
```

```bash
cp .env.example .env
```

Edit `.env` (never commit it). For the frontend, put `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`
in `frontend/.env.local` (Vite reads env files from `frontend/`):

```bash
printf 'VITE_SUPABASE_URL=https://YOUR-REF.supabase.co\nVITE_SUPABASE_ANON_KEY=YOUR-ANON-KEY\n' > frontend/.env.local
```

Run the site locally (http://localhost:5173):

```bash
npm --prefix frontend run dev
```

Run the collector. It reads env vars, so export them from `.env` first:

```bash
set -a; source .env; set +a; .venv/bin/python -m scraper --summary-file summary.md
```

With no `ENABLED_SOURCES` this records a `skipped` run and exits 0. Exit codes: `0` success/skipped,
`1` failed, `2` partial (some sources failed), `3` configuration error.

## Tests, linting, type checks and builds

Collector (the DB and RLS tests are skipped unless `TEST_DATABASE_URL` points at a **disposable**
Postgres server. They create and drop their own databases):

```bash
.venv/bin/ruff check scraper && .venv/bin/ruff format --check scraper && .venv/bin/mypy
```

```bash
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres .venv/bin/pytest
```

Frontend:

```bash
npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend test && npm --prefix frontend run build
```

CI (`.github/workflows/ci.yml`) runs all of the above, using a Postgres 17 service container.

## Importing data

### Synthetic demo data

```bash
.venv/bin/python -m scraper.synthetic --out /tmp/synthetic_demo.json
```

```bash
.venv/bin/python -m scraper --import-file /tmp/synthetic_demo.json --origin synthetic
```

To see change detection, generate revision 1 (some deadlines extended, some titles amended) and import it:

```bash
.venv/bin/python -m scraper.synthetic --out /tmp/synthetic_r1.json --revision 1 && .venv/bin/python -m scraper --import-file /tmp/synthetic_r1.json --origin synthetic
```

Remove all synthetic records before going live (history rows cascade; other origins are untouched):

```bash
.venv/bin/python -m scraper --purge-synthetic --yes
```

From GitHub instead: **Actions → Daily collection → Run workflow → mode `import-synthetic`** (or `purge-synthetic`).

### Your own CSV/JSON files

Templates: [data/samples/import_template.csv](data/samples/import_template.csv) and
[data/samples/import_template.json](data/samples/import_template.json) (a JSON array, or
`{"records": [...]}`).

| Column | Required | Notes |
|---|---|---|
| `title` | yes | Free text, whitespace-normalized, max 2000 chars |
| `source_id` (or `id`) | one of these two | Stable id. This is the preferred dedup key |
| `url` | one of these two | Kept only if it is `https://` on `gem.gov.in` / `*.gem.gov.in` (canonicalized). Otherwise it is dropped |
| `bid_number`, `organisation`, `ministry`, `department`, `category`, `listing_type` | no | If `organisation` is empty, it is built as "ministry / department" |
| `quantity` | no | Non-negative number, otherwise null |
| `published_at`, `deadline` | no | ISO 8601 or `DD-MM-YYYY hh:mm AM`. Values without an offset are read as IST. A date without a time becomes null (deadlines are never guessed) |

```bash
.venv/bin/python -m scraper --import-file path/to/listings.csv --source-name my_export --dry-run
```

```bash
.venv/bin/python -m scraper --import-file path/to/listings.csv --source-name my_export
```

Re-importing the same file is idempotent. Changed values create `listing_history` rows. Rows that
fail validation are counted as `rejected`. If more than half the rows are rejected, the import is
marked `failed`. Only import data you have the right to republish.

## Supabase setup

1. Create a project at https://supabase.com (any region; Mumbai is closest to GeM users).
2. Apply the migrations **in filename order**, using one of these:
   * **SQL editor:** paste and run each file from `supabase/migrations/`, in order. Do **not** run
     `supabase/tests/local_supabase_shim.sql` on Supabase.
   * **Supabase CLI:**

     ```bash
     supabase link --project-ref YOUR-REF
     ```

     ```bash
     supabase db push
     ```
3. **Auth → Providers → Email:** keep email sign-in enabled and **disable "Allow new users to sign up"**,
   so nobody can self-register.
4. **Auth → Users → Add user:** create the operator account (email + strong password).
5. Make that user an admin in the SQL editor:

   ```sql
   insert into public.admins (user_id)
   select id from auth.users where email = 'operator@example.com';
   ```
6. Collect credentials:
   * **Project URL** and **anon (publishable) key** (Project Settings → API) → frontend / Netlify.
   * **Connection string** (Connect → *Session pooler*, port 5432; it works over IPv4 from GitHub
     runners) → `DATABASE_URL` GitHub secret only.
   * The **service-role key is not used** by this project. Never put it in the frontend or Netlify.

## GitHub Actions (daily run)

`.github/workflows/daily-collection.yml` runs at **01:00 UTC (06:30 IST)** and on demand. GitHub can
delay or skip scheduled runs, so the website shows the time of the last *actual* successful live
run, not the schedule.

**Settings → Secrets and variables → Actions:**

| Type | Name | Value |
|---|---|---|
| Secret | `DATABASE_URL` | Supabase session-pooler connection string |
| Variable | `ENABLED_SOURCES` | Empty for now. Later a comma-separated adapter list |
| Variable | `GEM_LIVE_ACCESS_APPROVED` | `false` until GeM approves automated access |
| Variable | `GEM_REPRODUCTION_PERMISSION_CONFIRMED` | `false` until written permission is obtained |
| Variable | `COLLECTOR_USER_AGENT` | e.g. `GeMIntelligenceCollector/1.0 (+mailto:you@example.com)` |
| Variable (optional) | `REQUEST_DELAY_SECONDS`, `MAX_PAGES_PER_SOURCE`, `REFRESH_WINDOW_DAYS`, `REFRESH_MAX_PAGES` | Pacing/limits (bounded in code) |

What the workflow does: check out the repo, set up Python 3.12, install the pinned
`scraper/requirements.txt`, check that `DATABASE_URL` exists, run the selected mode, write a Markdown
summary to the job page, and upload the JSON-lines log as an artifact (kept 30 days). Credentials are
passed only as masked secrets and the collector never prints them.

* **No live source enabled (current state):** the run is recorded as `skipped`. The job summary and
  an annotation say "No live data source is enabled, so no GeM data was collected." The job does not
  claim a successful collection.
* **A source fails:** the job exits non-zero (`partial` = 2, `failed` = 1), shows as **failed** in
  GitHub, and the error is stored in `scrape_runs` and shown in the admin view.
* **Concurrency:** runs never overlap (`concurrency: daily-collection`).
* Manual modes: `collect` (optional `max_pages`, `dry_run`), `import-synthetic`, `purge-synthetic`.

## Netlify deployment

1. Push this repository to GitHub.
2. In Netlify: **Add new site → Import an existing project → GitHub →** pick the repo. `netlify.toml`
   already sets base `frontend`, command `npm run build`, publish `dist`, Node 24, SPA redirect and
   security headers (CSP allows only Supabase and Google Fonts).
3. **Site configuration → Environment variables:** add `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`
   (scope: Builds). These are public by design and protected by RLS. `netlify.toml` excludes exactly
   these two from Netlify's secret scanning. **Do not add `DATABASE_URL` or any service-role key to Netlify.**
4. Deploy. Without the two variables the site still deploys and shows the "no database connected" notice.
5. If you use a custom Supabase domain, add it to `connect-src` in `netlify.toml`.

Netlify only hosts the static site. The collector never runs in Netlify Functions.

## Configuring a live source later

No frontend or schema change is needed:

1. Add `scraper/sources/<name>.py` that subclasses `SourceAdapter` (`scraper/sources/base.py`):
   * `iter_pages(ctx)` yields bounded pages of raw dicts. Use `PacedHttpClient` for network access and
     `ctx.watermark` for incremental runs.
   * `normalize(raw)` returns a `ListingRecord` (with `data_origin="live"`) or raises `RejectedRecord`.
   * Set `origin = "live"`, an `access_group` (the host), and `requires_permission = True` if the data
     needs the GeM gates.
   * Raise `SourceAccessBlocked` on block pages. Never work around them.
2. Register it in `REGISTRY` in `scraper/sources/__init__.py` and add tests with synthetic fixtures.
3. Add its name to the `ENABLED_SOURCES` repository variable, then run the workflow manually once with `dry_run`.

To enable the **existing GeM adapters** (`gem_bids_products`, `gem_bids_services`), GeM must first
approve automated access and reproduction (feasibility report §3a/§4). Then set
`GEM_LIVE_ACCESS_APPROVED=true`, `GEM_REPRODUCTION_PERMISSION_CONFIRMED=true`, a `COLLECTOR_USER_AGENT`
that matches what GeM approved, and `ENABLED_SOURCES=gem_bids_products,gem_bids_services`. Until then
the CLI refuses to start them, including in dry-run mode.

## Security model

* **Anonymous visitors** (anon key) can `select` only the display columns of `listings`
  (not `content_hash`/`dedup_key`) and of `listing_history`, and can call `dashboard_stats()`,
  `collection_status()` and `listing_categories()`, which return aggregates and timestamps only.
  They cannot write anything, read `scrape_runs` or `admins`, or call `is_admin()`. These rules are
  tested against a real Postgres (`scraper/tests/test_access_controls.py`), and were also checked
  through PostgREST.
* **Admins** sign in with Supabase Auth on `/admin`. RLS returns `scrape_runs` rows only to users in
  `public.admins`. The admin page is part of the public bundle, but the data is enforced in the database.
* **The collector** connects with `DATABASE_URL` as the table owner, from GitHub Actions secrets only.
* The frontend lint config fails the build if code references `SERVICE_ROLE` or `DATABASE_URL`.
  Source links render only for `https://` URLs on GeM domains and open in a new tab
  (`noopener noreferrer`), because GeM forbids framing.
* `.env`, `.env.*` (except `.env.example`) and key files are git-ignored.

## Checklist: what you must provide

- [ ] Supabase project. Apply the 4 migrations, disable sign-ups, create the operator user and add it to `public.admins`.
- [ ] GitHub repository with the `DATABASE_URL` secret and the variables listed above.
- [ ] Netlify site connected to the repo, with `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`.
- [ ] Data: import synthetic demo data (clearly labelled), or import files you have the right to publish.
- [ ] **Live GeM data:** not available. It needs GeM's approval for automated access and written
      reproduction permission (feasibility report §3a/§4), or another approved source adapter.
- [ ] Optional: a custom domain on Netlify, and the Supabase custom domain in the CSP.
- [ ] Before using real data: `python -m scraper --purge-synthetic --yes`.

Not verified from this workstation: deployment to a real Supabase project, a GitHub Actions run, and
a Netlify deploy, because no credentials for those services were available. They are configured and
documented, and their local equivalents were tested (see the feasibility report and the test suites).
