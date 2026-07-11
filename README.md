# Brand Reviews WordPress (Interview Challenge Source)

Self-contained, reproducible WordPress site used as the source for a WP → Django migration challenge.

The site is a small consumer-reviews directory: **brands** with profile pages plus user-submitted **reviews** linked to each brand. Two custom post types, one taxonomy, ACF fields, Yoast SEO metadata.

---

# Django Migration — Submission

The Django replacement lives in `backend/` (Django + DRF) and `frontend/` (Vite + React 18, plus the SCSS source tree). It models the WordPress domain relationally, imports the WP content through a re-runnable command, serves the public pages under permalink-matching URLs, exposes `GET /api/brands/`, and ships a `<BrandList />` React component.

## Running the Django app locally

The migration reads the committed `db/dump.sql`, so you do **not** need the WordPress/Docker stack running to use the Django app.

```bash
# From the repo root — create a virtualenv and install backend deps.
python -m venv .venv
# Windows:  .venv\Scripts\activate       macOS/Linux:  source .venv/bin/activate
pip install -r backend/requirements.txt

cd backend
python manage.py migrate            # create the schema
python manage.py import_wordpress   # import WP content from db/dump.sql (see below)
python manage.py runserver          # http://127.0.0.1:8000/
```

Pages:
- Homepage (hero + recent reviews + featured brands): <http://127.0.0.1:8000/>
- Brand detail: `/brand/<slug>/`  ·  Review detail: `/review/<slug>/` (slugs match the WP permalinks)
- Brand listing API: `/api/brands/`

## API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/brands/` | Paginated brand cards. Params: `industry` (slug), `sort` (`avg_rating`\|`review_count`), `dir` (`asc`\|`desc`), `page`, `page_size`. |
| `GET /api/industries/` | Unpaginated list of industries (`name`, `slug`, `brand_count`) for the filter control — so the React dropdown is complete on a cold `?industry=…` load. |

**Pagination:** page-number style (`count`/`next`/`previous`/`results`). Default
page size is **12**; `page_size` is client-controllable up to a **max of 100**
(`BrandPagination.max_page_size`). An out-of-range `page` returns **404**; an
unknown `industry`, `sort`, or `dir` returns **400** with a `detail` message.

## Running the migration (and re-running it safely)

```bash
cd backend
python manage.py import_wordpress                 # default: parse ../db/dump.sql
python manage.py import_wordpress --dump-path=/path/to/dump.sql
python manage.py import_wordpress --source=mariadb # stream from a live DB (needs PyMySQL + WORDPRESS_DB_* env)
```

The import is **idempotent**. It upserts by the stable WordPress natural key (`wp_post_id` / `wp_user_id` / `wp_term_id`) and records every key it has ever created in an `ImportLedger`. On re-run: unchanged rows are left alone, changed source fields are updated in place, and rows you deleted between runs are **not** resurrected (the ledger distinguishes "never imported" from "imported then deleted"). A first run against the seeded dump reports 5 industries, 8 reviewers, 5 brands, 60 reviews; a second run reports zero created and zero updated. An unreadable source exits non-zero with the reason on stderr and prints no summary.

## Running the React component locally

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173/  (proxies /api → http://localhost:8000)
```

Run the Django server (above) alongside it so the component has an API to consume.

## Running the tests

```bash
# Backend: unit, integration, and 11 Hypothesis property tests
cd backend && python -m pytest

# Frontend: Vitest + React Testing Library + axe, and the SCSS structure test
cd frontend && npm test

# Frontend: lint the SCSS for structural selector collisions
cd frontend && npm run lint:css
```

## Modeling decisions (half-page)

- **Average rating — stored *and* derived.** The WP ACF value is kept on `Brand.migrated_average_rating` for audit, but the authoritative value is *computed* from live reviews (`with_stats()` annotation + a matching model property). Reviews are the source of truth; a stored aggregate drifts. Ratings `< 1` are excluded; no qualifying reviews → `null`.
- **Reviewers — a dedicated `Reviewer` model**, not `auth.User` (which would conflate authentication with attribution). One reviewer per WP author; the per-review `reviewer_name`/`reviewer_location` strings also live on `Review` so they survive an unresolved author.
- **Postmeta.** Queried ACF fields → first-class columns; the two Yoast keys → retained SEO fields; ACF shadow `_key` rows and everything else → dropped.
- **Migration.** A `manage.py` command over a pluggable `WordPressSource` (SQL-dump default, MariaDB for scale). Idempotent upsert by WP natural key + an `ImportLedger` so a re-run never resurrects a deleted row. Each phase is atomic and writes with chunked `bulk_create`/`bulk_update`.
- **API.** DRF page-number pagination; filter by industry **slug**; allow-listed `sort`+`dir` on DB annotations with nulls-last; clean `400`/`404`s.
- **Component & state.** The URL query string is the single source of truth for filter/sort/page; `useBrands` is an explicit `loading|success|empty|error` machine with abortable fetches; native labelled controls; responsive `.grid`.
- **SCSS.** Tokens partial mirroring the reference `:root`, 7-1 partitioning with `@use` — a new component is an isolated partial.

**What I'd do differently with more time:** cursor pagination as an additive option for mobile infinite-scroll; cache/precompute the rating + top-review if read volume grew; a chunked-flush importer (stream the source in batches) for a true 100× dataset.

**Where I took AI's default:** DRF's `PageNumberPagination` shape and SQLite for local dev — both appropriate here and trivially swappable (Postgres in prod).

---

## Quick start

```bash
cp .env.example .env
make up
```

After ~20 seconds:

- Public site: <http://localhost:8080>
- WP admin:    <http://localhost:8080/wp-admin> (`admin` / `admin`)
- phpMyAdmin:  <http://localhost:8081>
- REST root:   <http://localhost:8080/wp-json/wp/v2/>

The DB is auto-imported from `db/dump.sql` on first boot. No manual setup required for candidates.

## Stack

| Service     | Image                            | Port  | Purpose                                |
|-------------|----------------------------------|-------|----------------------------------------|
| `db`        | `mariadb:11`                     | -     | Database; auto-imports `db/dump.sql`   |
| `wordpress` | `wordpress:6.9-php8.3-apache`    | 8080  | WP + Apache + PHP                      |
| `wpcli`     | `wordpress:cli-php8.3`           | -     | Helper for re-seeding / dumping        |
| `phpmyadmin`| `phpmyadmin:5`                   | 8081  | Optional DB browser                    |

## What's committed

```
docker-compose.yml          # the stack
.env.example                # config defaults
Makefile                    # make targets
db/dump.sql                 # seeded database snapshot
scripts/seed.sh             # bootstrap script (install + plugins + seed)
wp-content/plugins/         # WP default plugins + ACF + Yoast (committed for offline reproducibility)
wp-content/mu-plugins/
  cpt.php                   # registers `brand` and `review` CPTs and `industry` taxonomy
  acf-fields.php            # registers ACF field groups in code
wp-content/themes/
  consumer-reviews/         # custom theme used by the site
```

WP core files and the default themes (e.g. twentytwentyfour) live inside the `wp_files` named volume and are recreated from the image on first boot. Only the custom `consumer-reviews` theme is committed to the repo.

## Make targets

```
make up         # start db + wordpress + phpmyadmin
make down       # stop containers (keeps volumes)
make reset      # stop AND wipe volumes (next 'up' re-imports dump.sql)
make logs       # tail wordpress + db
make wp ARGS="plugin list"   # run wp-cli inside the stack
make bootstrap  # full re-seed: WP core install + plugin install + content seed
make dump       # export the current DB to db/dump.sql
make status     # show running services
```

## Rebuilding the dump from scratch

If you change the schema or seed data:

```bash
make reset
make up
make bootstrap
make dump
git add db/dump.sql wp-content/plugins
git commit -m "Refresh seed data"
```

`make bootstrap` is idempotent enough to re-run, but the cleanest path is reset → up → bootstrap → dump.

## Content model

**`brand` CPT** at `/brand/<slug>/`
- Standard fields: title, content (body), featured image (optional)
- ACF fields: `website_url`, `founded_year`, `headquarters`, `average_rating`
- Taxonomy: `industry`
- Yoast: `_yoast_wpseo_title`, `_yoast_wpseo_metadesc` in postmeta

**`review` CPT** at `/review/<slug>/`
- Standard fields: title, content (review body), post_author (mapped to a real WP user)
- ACF fields: `rating` (1-5), `reviewer_name`, `reviewer_location`, `brand` (post object → brand id)

Seeded volume: 5 brands (one per industry), 60 reviews (12 per brand) authored by 8 reviewer users, 3 static pages (Home/About/Contact), 1 admin user.

## Theme

The active theme is a custom one at `wp-content/themes/consumer-reviews/` (committed to the repo). It renders:

- Homepage with featured brands and recent reviews
- Brand archive (`/brand/`) — card grid
- Single brand page (`/brand/<slug>/`) — hero with industry badge, star rating, website / founded / HQ metadata, body content, and full list of customer reviews
- Review archive (`/review/`) — paginated list
- Single review (`/review/<slug>/`) — back-link to brand, star rating, reviewer name/location, body
- Page template for About / Contact / Home pages

The theme is intentionally small (~10 PHP files + one stylesheet) and is meant to show candidates what the data renders as. They are not expected to clone the theme — just to migrate the underlying data.

## Endpoints worth knowing

- `/wp-json/wp/v2/brands` — list brands (note: `rest_base` is `brands` even though post type is `brand`)
- `/wp-json/wp/v2/brands/<id>` — single brand with ACF fields under `acf`
- `/wp-json/wp/v2/reviews` — list reviews
- `/wp-json/wp/v2/industry` — taxonomy terms
- `/wp-json/wp/v2/users` — reviewer users
- `/wp-json/wp/v2/pages` — static pages

ACF fields are exposed natively via `show_in_rest: true` set in `wp-content/mu-plugins/acf-fields.php`.

## Styling (SCSS)

The Django frontend styles live as an organized SCSS source tree under `frontend/scss/`, split into partials by concern:

```
frontend/scss/
  main.scss                 # entry point — forwards all partials
  abstracts/_tokens.scss    # design tokens (colors, radius, shadows, max width, font)
  base/                     # reset + typography
  layout/                   # container, header, footer, sections
  components/               # cards, stars, badge, reviews, pagination, page
```

The tree compiles to `frontend/static/css/theme.css`, which is structurally equivalent to `reference/theme.css`.

Compile it with [Dart Sass](https://sass-lang.com/dart-sass/):

```bash
sass frontend/scss/main.scss frontend/static/css/theme.css
```

If Dart Sass isn't installed globally, run it through npm without a global install:

```bash
npx sass frontend/scss/main.scss frontend/static/css/theme.css
```

To recompile automatically while editing, add `--watch`:

```bash
sass --watch frontend/scss/main.scss frontend/static/css/theme.css
```

## Notes for the maintainer

- The `wp-content/plugins/advanced-custom-fields/` and `wp-content/plugins/wordpress-seo/` plugin code is GPL and committed to the repo so candidates don't need internet on first boot.
- `wp-content/plugins/akismet/` and `hello.php` are WP defaults — left in place but inactive.
- The site URL is hardcoded as `http://localhost:8080` in the dump (in `wp_options.siteurl` and `home`). Changing the port requires a search/replace in `db/dump.sql` before commit, or just override via `WP_HOME` / `WP_SITEURL` constants.
- `_yoast_wpseo_*` postmeta is seeded for brand posts only.
