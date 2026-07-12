# Walkthrough: `catalog/wp_import/` — the migration engine

This is the folder that pulls WordPress content into the Django database. If you
strip away the framework stuff, the whole job is: *read messy WordPress data
from somewhere, and write it cleanly into our tables — without making duplicates
or bringing back rows someone deleted on purpose.*

There are three files doing the work, and they're stacked in layers:

```
dump_parser.py   →  low-level: turn a mysqldump file into rows of Python values
sources.py       →  middle:    turn rows (or DB/REST data) into clean dataclasses
importer.py      →  top:       take those dataclasses and upsert them into Django
```

The nice thing about this split is that each layer only knows about the one
below it. The importer has *no idea* where the data came from — dump file, live
MySQL, or the REST API. That's the whole design, and it's why adding a new data
source never touches the import logic.

Let me go file by file.

---

## `__init__.py`

Empty. It just makes the folder a Python package so you can do
`from catalog.wp_import.importer import run_import`. Nothing to see here.

---

## `dump_parser.py` — reading the SQL dump without losing your mind

WordPress ships us a `db/dump.sql` file. It's the output of `mysqldump`, so it's
full of lines like:

```sql
INSERT INTO `wp_posts` VALUES (1,2,'2026-01-01 00:00:00','...','<p>body</p>',...);
```

We need to pull the actual values out of those lines. You might think "just
split on commas" — but nope, because the post body itself can contain commas,
parentheses, quotes, and escaped newlines. So we need a tiny, careful parser.

**The key trick (and the reason this scales):** `mysqldump` writes each `INSERT`
on a *single physical line*, with real newlines inside text escaped as `\n`. So
we can read the file **one line at a time** and never load the whole thing into
memory. That's what `stream_insert_rows` does:

```python
def stream_insert_rows(path, table, encoding="utf-8"):
    prefix = f"INSERT INTO `{table}` VALUES "
    with open(path, "r", encoding=encoding, newline="") as handle:
        for line in handle:
            if line.startswith(prefix):
                yield from iter_value_tuples(line[len(prefix):])
```

It opens the file, walks it line by line, and whenever a line is an `INSERT` for
the table we care about, it hands the `VALUES (...)` part off to be parsed. It
`yield`s rows, so nothing piles up — memory stays flat whether the dump is 60
rows or 6 million.

**`iter_value_tuples`** is the actual hand-rolled tokenizer. It walks the string
character by character and pulls out each `(...)` group as a list of fields. The
fiddly bits it handles correctly:

- **Quoted strings** — everything between `'...'` is one value, even if it has
  commas or parens inside.
- **Doubled quotes** — in SQL, `''` inside a string means a literal single quote,
  not the end of the string.
- **Backslash escapes** — `\n`, `\t`, `\'`, `\\` etc. get turned back into the
  real characters (that's the `_ESCAPES` table + `_unescape`).
- **`NULL`** — becomes Python `None`.
- **Bare numbers** — kept as their raw text (the layer above decides if it's an
  int or a decimal).

So the output of this file is dumb and simple: **lists of strings (or `None`)**,
one per database row. It doesn't know what a "brand" is. It's just "here are the
raw cells from this table."

> Interview one-liner: *"It's a streaming, line-by-line tokenizer for mysqldump
> INSERTs — so memory stays flat regardless of dump size, and it correctly
> handles quotes, escapes, and commas inside post bodies."*

---

## `sources.py` — turning raw data into clean, typed objects

This is the translation layer, and honestly it's the most important design idea
in the whole project. It answers: *"where does WordPress content come from, and
what shape do we hand it to the importer?"*

### The dataclasses

First it defines four little plain-data classes — `SourceIndustry`,
`SourceUser`, `SourceBrand`, `SourceReview`. These are **not** Django models.
They're just tidy bags of the fields we care about, already typed:

```python
@dataclass
class SourceBrand:
    wp_post_id: int
    name: str
    slug: str
    body: str = ""
    website_url: str = ""
    founded_year: int | None = None
    ...
    average_rating: Decimal | None = None
```

Why bother with these instead of passing dicts around? Because it gives the
importer a stable, predictable contract. No matter which source produced it, a
`SourceBrand` always looks the same.

### The protocol (the real MVP)

```python
@runtime_checkable
class WordPressSource(Protocol):
    def industries(self): ...
    def users(self): ...
    def brands(self): ...
    def reviews(self): ...
```

This is just a promise: "a source is anything with these four methods." The
importer depends on *this*, not on any specific class. Swap the source, the
importer doesn't care.

### The three concrete sources

- **`SqlDumpSource`** (the default) — uses `dump_parser` to read the committed
  `db/dump.sql`. It's offline, deterministic, and needs nothing running, which
  makes it perfect for tests/CI. It reads `wp_posts`, `wp_postmeta`, `wp_users`,
  and the taxonomy tables, then does the annoying WordPress-specific work:
  - **Collapsing ACF pairs.** ACF stores each custom field as two rows — the
    value, and a "shadow" `_key` row pointing at the field definition. We keep
    an allow-list of the meta keys we actually want and drop everything else, so
    the shadow rows and all the WordPress bookkeeping meta just fall away.
  - **Keeping the two Yoast SEO keys**, dropping the rest.
  - **Resolving the industry** by walking the `wp_terms` /
    `wp_term_taxonomy` / `wp_term_relationships` trio back to each brand.

- **`MariaDbSource`** (the "scale" story) — same four methods, but instead of a
  file it reads a live MySQL/MariaDB connection with an *unbuffered server-side
  cursor*, so rows stream in instead of being loaded all at once. It even does
  the ACF-pair collapsing inside SQL with `MAX(CASE WHEN meta_key = ...)`
  pivots. The driver (`PyMySQL`) is imported lazily, so this file still imports
  fine even if the driver isn't installed.

- **`RestApiSource`** (on the `approach/rest-source` branch) — same four
  methods again, but reads the live WP REST API under `/wp-json/wp/v2/`.

### The one sneaky-but-important helper: `_make_aware_utc`

WordPress timestamps are "naive" (no timezone). Django, with `USE_TZ=True`,
reads dates back as timezone-*aware*. If we stored naive dates, then every time
we re-ran the import, the check "did this date change?" would compare a naive
date against an aware one — and those are *never* equal — so every row would look
"changed" on every run. That quietly breaks idempotency. This helper stamps the
parsed dates as UTC so they compare equal across runs.

> This is the bug I actually caught with a property test ("a re-run should change
> nothing"). Good story for the interview — it's the difference between AI
> writing code and me owning it.

> Interview one-liner: *"The importer depends on a `WordPressSource` protocol,
> not a concrete reader. That's the seam — SQL dump by default, MariaDB for
> scale, REST as an alternative, all behind the same four methods."*

---

## `importer.py` — writing it in, safely and idempotently

Now we've got clean `Source*` objects. This file's job is to get them into the
database *correctly* — and "correctly" here has a specific, tricky meaning:
running the import twice should not create duplicates, and should not undo a
deletion someone made on purpose.

### The three-way rule (the heart of it)

For every incoming record, keyed by its stable WordPress id, we do one of three
things:

1. **A live row with that key already exists?** → update its fields if anything
   changed.
2. **No live row, but we've imported this key before?** → *skip it.* This means
   someone deleted it after a previous import, and we respect that.
3. **Never seen it at all?** → create it, and record its key.

That "have we seen it before" memory is the **`ImportLedger`** — a tiny table
that just remembers every key we've ever created. It's what lets us tell
"brand new" apart from "deleted on purpose." A naive `update_or_create` can't do
this — it would happily resurrect a deleted row on the next run.

You can see the rule literally in the code (this is `_upsert_industries`, but all
four phases follow the same shape):

```python
if live is not None:
    # ... update changed fields, add to `to_update`
elif wp_id in ledger_keys:
    pass                      # ← the "deleted on purpose" branch
else:
    to_create.append(Industry(...))   # brand new → create + ledger it
```

### Why it's fast (bulk, not row-by-row)

Instead of hitting the database once per record, each phase sorts everything
into two buckets — `to_create` and `to_update` — and then does **one**
`bulk_create` and **one** `bulk_update` (chunked at 1000). So importing N rows is
a handful of queries, not N queries. The "does this already exist?" lookups are
also cheap: we load all existing rows into a `{wp_id: object}` dict once per
phase (one `SELECT`), and the ledger check is just set membership.

### The order matters (foreign keys)

`run_import` runs the phases in dependency order:

```
Industries → Reviewers → Brands → Reviews
```

You have to create industries before brands (a brand points at an industry), and
brands + reviewers before reviews (a review points at both). After each phase
commits, we build a `{wp_id: primary_key}` map so the next phase can wire up
foreign keys **without** doing a query per row:

```python
industry_map = dict(Industry.objects.values_list("wp_term_id", "pk"))
# ... later, when creating a brand:
Brand(..., industry_id=industry_map[src.industry_wp_term_id])
```

### A couple of nice touches

- **Each phase is wrapped in `transaction.atomic()`**, so if something blows up
  mid-phase, that phase rolls back cleanly instead of leaving half-written data.
- **Reviewers are filtered.** We only create a `Reviewer` for WordPress users who
  actually authored a review (`_referenced_author_ids`), not every single
  `wp_users` row — so the admin account and other noise don't become reviewers.
- **Unresolvable references are handled, not crashed on.** A review pointing at a
  brand that doesn't exist gets skipped with a logged warning (we can't satisfy
  a non-null foreign key). A review whose author we can't resolve still imports —
  its `reviewer` is just left null, and we keep the display name.
- **It returns an `ImportSummary`** — the per-model created/updated counts that
  the `import_wordpress` command prints out. On a second run against unchanged
  data, every number is zero. That's the proof it's idempotent.

> Interview one-liner: *"The `ImportLedger` is the whole trick — it distinguishes
> 'never imported' from 'imported then deleted,' so a re-run never resurrects a
> deletion. Each phase classifies rows into create/update/skip and writes them in
> bulk, in FK order, inside a transaction."*

---

## `tests/`

Right next door there's a `tests/` folder that backs all this up:

- **`test_dump_parser.py`** — feeds the tokenizer nasty strings (commas in
  bodies, doubled quotes, escapes) and checks it parses them right.
- **`test_sql_dump_source.py`** — checks the ACF-pair collapsing, Yoast
  retention, and field mapping with small in-memory dump fixtures.
- **`test_rest_source.py`** (rest-source branch) — same idea for the REST source,
  with an injected fake fetcher so it runs offline.
- The idempotency/deletion property tests live one level up in
  `catalog/tests/` (`test_importer_properties.py`, `test_importer_ledger.py`,
  `test_import_integration.py`) — those are the ones that hammer `run_import`
  with generated data and prove the "re-run changes nothing / deletions stay
  deleted" guarantees.

---

## TL;DR

- `dump_parser.py` = streaming SQL-dump reader → raw rows.
- `sources.py` = adapters (dump / MariaDB / REST) behind one `WordPressSource`
  protocol → clean typed `Source*` objects.
- `importer.py` = idempotent, ledger-backed, bulk upsert in FK order → the Django
  DB, returning a created/updated summary.

The one sentence that ties it together: **the importer never knows where the data
came from, and re-running it is always safe.**
