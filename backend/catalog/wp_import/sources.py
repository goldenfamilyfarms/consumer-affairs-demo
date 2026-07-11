"""WordPress content sources for the import command.

The import command depends on the :class:`WordPressSource` protocol rather than
on any concrete reader. This isolates *where* WordPress content comes from (the
``db/dump.sql`` file, a live MariaDB connection, or the REST API) from *how* the
importer upserts it idempotently.

Every source yields plain, source-shaped dataclasses (:class:`SourceIndustry`,
:class:`SourceUser`, :class:`SourceBrand`, :class:`SourceReview`) so the upsert
logic stays source-agnostic and unit-testable with in-memory fixtures. These
dataclasses are deliberately *not* Django models; they carry the raw
WordPress-derived values plus the natural keys used for FK resolution.

:class:`SqlDumpSource` (the default) parses ``db/dump.sql``. It reads
``wp_posts`` (filtered by ``post_type``), ``wp_postmeta``, ``wp_users``, and the
``wp_terms`` / ``wp_term_taxonomy`` / ``wp_term_relationships`` trio. It collapses
ACF postmeta pairs by dropping the shadow ``_key`` rows, retains the two Yoast
keys, and drops every other postmeta key (Requirement 3).

:class:`MariaDbSource` (the "scale" source) yields the *same* four generators
against a live MariaDB/MySQL connection. Instead of pivoting postmeta in Python,
it collapses ACF pairs, retains Yoast keys, and resolves the industry term inside
the SQL (``MAX(CASE WHEN meta_key = ... )`` pivots + a join on the industry
taxonomy). Every generator streams rows through an *unbuffered* server-side
cursor so the Python process's memory stays flat regardless of dump size - the
mechanism behind the "scale to 100x" story (Requirement 5.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, Iterator, List, Optional, Protocol, Tuple, runtime_checkable

from .dump_parser import stream_insert_rows

__all__ = [
    "SourceIndustry",
    "SourceUser",
    "SourceBrand",
    "SourceReview",
    "WordPressSource",
    "SqlDumpSource",
    "MariaDbSource",
    "RestApiSource",
]


# --------------------------------------------------------------------------- #
# Source dataclasses (plain data, not Django models)
# --------------------------------------------------------------------------- #

@dataclass
class SourceIndustry:
    """An ``industry`` taxonomy term."""

    wp_term_id: int
    name: str
    slug: str


@dataclass
class SourceUser:
    """A ``wp_users`` record (a candidate reviewer)."""

    wp_user_id: int
    user_login: str
    display_name: str
    email: str = ""


@dataclass
class SourceBrand:
    """A ``brand`` post with its collapsed ACF fields and Yoast metadata."""

    wp_post_id: int
    name: str
    slug: str
    body: str = ""
    wp_post_date: Optional[datetime] = None
    industry_wp_term_id: Optional[int] = None
    website_url: str = ""
    founded_year: Optional[int] = None
    headquarters: str = ""
    average_rating: Optional[Decimal] = None
    seo_title: str = ""
    seo_metadesc: str = ""


@dataclass
class SourceReview:
    """A ``review`` post with its collapsed ACF fields."""

    wp_post_id: int
    title: str
    slug: str
    body: str = ""
    wp_post_date: Optional[datetime] = None
    rating: Optional[int] = None
    reviewer_name: str = ""
    reviewer_location: str = ""
    brand_wp_post_id: Optional[int] = None
    wp_user_id: Optional[int] = None


# --------------------------------------------------------------------------- #
# Source protocol
# --------------------------------------------------------------------------- #

@runtime_checkable
class WordPressSource(Protocol):
    """The interface the import command depends on."""

    def industries(self) -> Iterable[SourceIndustry]: ...
    def users(self) -> Iterable[SourceUser]: ...
    def brands(self) -> Iterable[SourceBrand]: ...
    def reviews(self) -> Iterable[SourceReview]: ...


# --------------------------------------------------------------------------- #
# Value coercion helpers
# --------------------------------------------------------------------------- #

def _to_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value: Optional[str]) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except (TypeError, InvalidOperation):
        return None


def _make_aware_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return ``value`` as a timezone-aware UTC datetime when ``USE_TZ`` is set.

    WordPress dump timestamps are naive (they carry no tzinfo). Django stores
    and reads ``DateTimeField`` values as timezone-aware when ``settings.USE_TZ``
    is ``True`` (the project default). If the importer produced naive datetimes,
    every re-run would treat ``live_row.wp_post_date != src.wp_post_date`` as a
    change (naive vs aware never compare equal) and mark rows "updated" forever,
    breaking idempotency (Property 3). Interpreting the naive dump timestamps as
    UTC keeps them equal across runs and silences naive-datetime warnings.
    """
    if value is None:
        return None

    # Import lazily so this module can be used without Django settings loaded.
    from datetime import timezone as _dt_timezone

    from django.conf import settings
    from django.utils import timezone

    if getattr(settings, "USE_TZ", False) and timezone.is_naive(value):
        return timezone.make_aware(value, _dt_timezone.utc)
    return value


def _to_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value or value.startswith("0000-00-00"):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    return _make_aware_utc(parsed)


# --------------------------------------------------------------------------- #
# DB-driver value coercion
# --------------------------------------------------------------------------- #
# The SQL-dump parser hands every field back as ``str`` / ``None``. A DB driver
# is richer: it can return ``int``/``Decimal``/``datetime`` for typed columns and
# ``bytes`` for text under some driver configs. These helpers normalise driver
# values into the same shapes the dataclasses expect, then reuse the ``_to_*``
# coercions above so both sources share one definition of "how a field is read".

def _coerce_text(value: object) -> str:
    """Normalise a driver value into ``str`` (``None`` -> empty string)."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _coerce_optional_text(value: object) -> Optional[str]:
    """Like :func:`_coerce_text` but keep ``None`` as ``None`` for ``_to_*``."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _coerce_datetime(value: object) -> Optional[datetime]:
    """Accept a driver ``datetime``/``date`` or a dump ``str`` timestamp.

    Naive results are made timezone-aware (UTC) when ``settings.USE_TZ`` is set,
    matching :func:`_to_datetime`, so both sources feed the importer aware
    datetimes and idempotency holds (see :func:`_make_aware_utc`).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return _make_aware_utc(value)
    if isinstance(value, date):
        return _make_aware_utc(datetime(value.year, value.month, value.day))
    if isinstance(value, str):
        return _to_datetime(value)
    return None


# --------------------------------------------------------------------------- #
# wp_posts / wp_postmeta / wp_users / wp_terms column indices
# --------------------------------------------------------------------------- #

# wp_posts
_POST_ID = 0
_POST_AUTHOR = 1
_POST_DATE = 2
_POST_CONTENT = 4
_POST_TITLE = 5
_POST_STATUS = 7
_POST_NAME = 11
_POST_TYPE = 20

# wp_postmeta
_META_POST_ID = 1
_META_KEY = 2
_META_VALUE = 3

# wp_users
_USER_ID = 0
_USER_LOGIN = 1
_USER_EMAIL = 4
_USER_DISPLAY_NAME = 9

# wp_terms
_TERM_ID = 0
_TERM_NAME = 1
_TERM_SLUG = 2

# wp_term_taxonomy
_TT_ID = 0
_TT_TERM_ID = 1
_TT_TAXONOMY = 2

# wp_term_relationships
_REL_OBJECT_ID = 0
_REL_TT_ID = 1

_INDUSTRY_TAXONOMY = "industry"

# Postmeta keys retained per post type. Everything else - including ACF shadow
# ``_key`` rows and unrelated WordPress meta - is dropped (Requirement 3.5).
_BRAND_META_KEYS = frozenset(
    {
        "website_url",
        "founded_year",
        "headquarters",
        "average_rating",
        "_yoast_wpseo_title",
        "_yoast_wpseo_metadesc",
    }
)
_REVIEW_META_KEYS = frozenset(
    {
        "rating",
        "reviewer_name",
        "reviewer_location",
        "brand",
    }
)


# --------------------------------------------------------------------------- #
# SqlDumpSource
# --------------------------------------------------------------------------- #

class SqlDumpSource:
    """Read WordPress content from a ``mysqldump`` SQL file (default source)."""

    def __init__(self, dump_path: str) -> None:
        self.dump_path = str(dump_path)

    # -- taxonomy ---------------------------------------------------------- #

    def _industry_term_ids(self) -> set[int]:
        """term_ids whose taxonomy is ``industry``."""
        ids: set[int] = set()
        for row in stream_insert_rows(self.dump_path, "wp_term_taxonomy"):
            if len(row) <= _TT_TAXONOMY:
                continue
            if row[_TT_TAXONOMY] == _INDUSTRY_TAXONOMY:
                term_id = _to_int(row[_TT_TERM_ID])
                if term_id is not None:
                    ids.add(term_id)
        return ids

    def _industry_tt_to_term(self) -> Dict[int, int]:
        """Map ``term_taxonomy_id`` -> ``term_id`` for industry terms only."""
        mapping: Dict[int, int] = {}
        for row in stream_insert_rows(self.dump_path, "wp_term_taxonomy"):
            if len(row) <= _TT_TAXONOMY:
                continue
            if row[_TT_TAXONOMY] != _INDUSTRY_TAXONOMY:
                continue
            tt_id = _to_int(row[_TT_ID])
            term_id = _to_int(row[_TT_TERM_ID])
            if tt_id is not None and term_id is not None:
                mapping[tt_id] = term_id
        return mapping

    def _brand_industry_terms(self) -> Dict[int, int]:
        """Map brand ``post_id`` -> industry ``term_id`` via term relationships."""
        tt_to_term = self._industry_tt_to_term()
        result: Dict[int, int] = {}
        for row in stream_insert_rows(self.dump_path, "wp_term_relationships"):
            if len(row) <= _REL_TT_ID:
                continue
            object_id = _to_int(row[_REL_OBJECT_ID])
            tt_id = _to_int(row[_REL_TT_ID])
            if object_id is None or tt_id is None:
                continue
            term_id = tt_to_term.get(tt_id)
            if term_id is not None and object_id not in result:
                result[object_id] = term_id
        return result

    # -- postmeta ---------------------------------------------------------- #

    def _collect_postmeta(self, allowed_keys: frozenset) -> Dict[int, Dict[str, str]]:
        """Build ``{post_id: {meta_key: meta_value}}`` for retained keys only.

        Dropping every key not in ``allowed_keys`` collapses ACF pairs (the
        shadow ``_key`` rows are excluded) and discards all non-mapped postmeta.
        """
        meta: Dict[int, Dict[str, str]] = {}
        for row in stream_insert_rows(self.dump_path, "wp_postmeta"):
            if len(row) <= _META_VALUE:
                continue
            key = row[_META_KEY]
            if key not in allowed_keys:
                continue
            post_id = _to_int(row[_META_POST_ID])
            if post_id is None:
                continue
            meta.setdefault(post_id, {})[key] = row[_META_VALUE]
        return meta

    # -- generators -------------------------------------------------------- #

    def industries(self) -> Iterable[SourceIndustry]:
        industry_ids = self._industry_term_ids()
        for row in stream_insert_rows(self.dump_path, "wp_terms"):
            if len(row) <= _TERM_SLUG:
                continue
            term_id = _to_int(row[_TERM_ID])
            if term_id is None or term_id not in industry_ids:
                continue
            yield SourceIndustry(
                wp_term_id=term_id,
                name=row[_TERM_NAME] or "",
                slug=row[_TERM_SLUG] or "",
            )

    def users(self) -> Iterable[SourceUser]:
        for row in stream_insert_rows(self.dump_path, "wp_users"):
            if len(row) <= _USER_DISPLAY_NAME:
                continue
            user_id = _to_int(row[_USER_ID])
            if user_id is None:
                continue
            yield SourceUser(
                wp_user_id=user_id,
                user_login=row[_USER_LOGIN] or "",
                display_name=row[_USER_DISPLAY_NAME] or "",
                email=row[_USER_EMAIL] or "",
            )

    def brands(self) -> Iterable[SourceBrand]:
        meta = self._collect_postmeta(_BRAND_META_KEYS)
        industry_terms = self._brand_industry_terms()
        for row in stream_insert_rows(self.dump_path, "wp_posts"):
            if len(row) <= _POST_TYPE:
                continue
            if row[_POST_TYPE] != "brand":
                continue
            post_id = _to_int(row[_POST_ID])
            if post_id is None:
                continue
            fields = meta.get(post_id, {})
            yield SourceBrand(
                wp_post_id=post_id,
                name=row[_POST_TITLE] or "",
                slug=row[_POST_NAME] or "",
                body=row[_POST_CONTENT] or "",
                wp_post_date=_to_datetime(row[_POST_DATE]),
                industry_wp_term_id=industry_terms.get(post_id),
                website_url=fields.get("website_url", "") or "",
                founded_year=_to_int(fields.get("founded_year")),
                headquarters=fields.get("headquarters", "") or "",
                average_rating=_to_decimal(fields.get("average_rating")),
                seo_title=fields.get("_yoast_wpseo_title", "") or "",
                seo_metadesc=fields.get("_yoast_wpseo_metadesc", "") or "",
            )

    def reviews(self) -> Iterable[SourceReview]:
        meta = self._collect_postmeta(_REVIEW_META_KEYS)
        for row in stream_insert_rows(self.dump_path, "wp_posts"):
            if len(row) <= _POST_TYPE:
                continue
            if row[_POST_TYPE] != "review":
                continue
            post_id = _to_int(row[_POST_ID])
            if post_id is None:
                continue
            fields = meta.get(post_id, {})
            yield SourceReview(
                wp_post_id=post_id,
                title=row[_POST_TITLE] or "",
                slug=row[_POST_NAME] or "",
                body=row[_POST_CONTENT] or "",
                wp_post_date=_to_datetime(row[_POST_DATE]),
                rating=_to_int(fields.get("rating")),
                reviewer_name=fields.get("reviewer_name", "") or "",
                reviewer_location=fields.get("reviewer_location", "") or "",
                brand_wp_post_id=_to_int(fields.get("brand")),
                wp_user_id=_to_int(row[_POST_AUTHOR]),
            )


# --------------------------------------------------------------------------- #
# MariaDbSource (scale)
# --------------------------------------------------------------------------- #

# A table/identifier prefix we are willing to splice into SQL. Table names cannot
# be passed as bound parameters, so the prefix is validated against this pattern
# before interpolation to keep the queries injection-safe.
_SAFE_PREFIX = re.compile(r"^[A-Za-z0-9_]*$")

# Postmeta pivot expressions shared by the brand/review SELECTs. Collapsing ACF
# pairs happens for free: only the mapped keys are pivoted, so shadow ``_key``
# rows and every other postmeta key are dropped (Requirement 3.5).
_BRAND_META_PIVOTS: Tuple[Tuple[str, str], ...] = (
    ("website_url", "website_url"),
    ("founded_year", "founded_year"),
    ("headquarters", "headquarters"),
    ("average_rating", "average_rating"),
    ("_yoast_wpseo_title", "seo_title"),
    ("_yoast_wpseo_metadesc", "seo_metadesc"),
)
_REVIEW_META_PIVOTS: Tuple[Tuple[str, str], ...] = (
    ("rating", "rating"),
    ("reviewer_name", "reviewer_name"),
    ("reviewer_location", "reviewer_location"),
    ("brand", "brand"),
)


class MariaDbSource:
    """Read WordPress content from a live MariaDB/MySQL connection (scale source).

    This yields the same four generators as :class:`SqlDumpSource`, but instead
    of loading ``wp_postmeta`` into a dict and pivoting in Python, it pivots the
    mapped ACF/Yoast keys inside SQL (``MAX(CASE WHEN meta_key = ...)``) and
    resolves the industry term with a correlated sub-select. Every generator
    streams its result set through an *unbuffered* server-side cursor
    (``SSDictCursor``) and yields one dataclass per fetched row, so the Python
    process never materialises the whole table - memory stays flat at 100x
    volume (Requirement 5.2).

    The MariaDB driver (``PyMySQL``) is imported lazily inside :meth:`_connect`
    so this module still imports cleanly when the driver is not installed; the
    default ``SqlDumpSource`` path has no such dependency.

    Connection config
    -----------------
    Pass connection settings explicitly to the constructor, or leave them unset
    to fall back to environment variables (defaults in parentheses):

    ==========  ============================  ==========================
    Argument    Environment variable          Default
    ==========  ============================  ==========================
    ``host``      ``WORDPRESS_DB_HOST``         ``127.0.0.1``
    ``port``      ``WORDPRESS_DB_PORT``         ``3306``
    ``user``      ``WORDPRESS_DB_USER``         ``wp``
    ``password``  ``WORDPRESS_DB_PASSWORD``     ``wp``
    ``database``  ``WORDPRESS_DB_NAME``         ``wp``
    ``table_prefix`` ``WORDPRESS_TABLE_PREFIX`` ``wp_``
    ==========  ============================  ==========================

    ``charset`` defaults to ``utf8mb4``. ``connect_kwargs`` is passed straight
    through to ``pymysql.connect`` for anything else (SSL, socket, timeouts).
    The ``table_prefix`` is validated against ``[A-Za-z0-9_]*`` before being
    spliced into SQL (table names cannot be bound parameters), so it is safe
    from injection. Example::

        source = MariaDbSource(
            host="db.internal", port=3306, user="reader",
            password="…", database="wordpress", table_prefix="wp_",
        )
        for brand in source.brands():
            ...

    Requires ``PyMySQL`` (``pip install PyMySQL``); it is only imported when a
    generator is actually consumed.
    """

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        table_prefix: str = "wp_",
        charset: str = "utf8mb4",
        connect_kwargs: Optional[dict] = None,
    ) -> None:
        import os

        self.host = host or os.environ.get("WORDPRESS_DB_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("WORDPRESS_DB_PORT", 3306))
        self.user = user or os.environ.get("WORDPRESS_DB_USER", "wp")
        self.password = (
            password
            if password is not None
            else os.environ.get("WORDPRESS_DB_PASSWORD", "wp")
        )
        self.database = database or os.environ.get("WORDPRESS_DB_NAME", "wp")
        prefix = table_prefix or os.environ.get("WORDPRESS_TABLE_PREFIX", "wp_")
        if not _SAFE_PREFIX.match(prefix):
            raise ValueError(f"Unsafe table prefix: {prefix!r}")
        self.table_prefix = prefix
        self.charset = charset
        self.connect_kwargs = dict(connect_kwargs or {})

    # -- connection / streaming ------------------------------------------- #

    def _connect(self):
        """Open a PyMySQL connection, importing the driver lazily.

        Kept optional so importing this module never requires the driver. Any
        failure to import or connect surfaces to the caller (the import command
        turns it into a ``CommandError`` per Requirement 5.8).
        """
        pymysql = self._import_pymysql()
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset=self.charset,
            **self.connect_kwargs,
        )

    @staticmethod
    def _import_pymysql():
        """Import PyMySQL (with its ``cursors`` submodule) lazily.

        Kept out of module import so ``sources.py`` imports cleanly without the
        driver installed - the default ``SqlDumpSource`` path needs none. A
        missing driver raises an actionable ``ImportError`` that the import
        command turns into a ``CommandError`` (Requirement 5.8).
        """
        try:
            import pymysql  # noqa: WPS433 (intentional lazy/optional import)
            import pymysql.cursors  # noqa: F401  (SSDictCursor lives here)
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ImportError(
                "MariaDbSource requires the 'PyMySQL' driver. "
                "Install it with `pip install PyMySQL`."
            ) from exc
        return pymysql

    def _stream(self, sql: str) -> Iterator[dict]:
        """Yield dict rows for ``sql`` through an unbuffered server-side cursor.

        ``SSDictCursor`` fetches rows from the server on demand rather than
        buffering the whole result set client-side, which is what keeps memory
        flat for arbitrarily large tables.
        """
        pymysql = self._import_pymysql()
        conn = self._connect()
        try:
            with conn.cursor(pymysql.cursors.SSDictCursor) as cursor:
                cursor.execute(sql)
                for row in cursor:
                    yield row
        finally:
            conn.close()

    def _t(self, name: str) -> str:
        """Return a prefixed table name (e.g. ``wp_posts``)."""
        return f"{self.table_prefix}{name}"

    @staticmethod
    def _meta_pivot_sql(pivots: Tuple[Tuple[str, str], ...]) -> str:
        """Build the ``MAX(CASE WHEN meta_key = 'x' ...)`` pivot column list."""
        return ",\n".join(
            "  MAX(CASE WHEN pm.meta_key = '{key}' THEN pm.meta_value END) AS {alias}".format(
                key=key, alias=alias
            )
            for key, alias in pivots
        )

    @staticmethod
    def _meta_key_list(pivots: Tuple[Tuple[str, str], ...]) -> str:
        """Build the quoted ``IN (...)`` key list restricting the postmeta join."""
        return ", ".join("'{}'".format(key) for key, _ in pivots)

    # -- generators -------------------------------------------------------- #

    def industries(self) -> Iterable[SourceIndustry]:
        sql = (
            "SELECT t.term_id AS term_id, t.name AS name, t.slug AS slug "
            f"FROM {self._t('terms')} t "
            f"JOIN {self._t('term_taxonomy')} tt ON tt.term_id = t.term_id "
            f"WHERE tt.taxonomy = '{_INDUSTRY_TAXONOMY}'"
        )
        for row in self._stream(sql):
            term_id = _to_int(_coerce_optional_text(row.get("term_id")))
            if term_id is None:
                continue
            yield SourceIndustry(
                wp_term_id=term_id,
                name=_coerce_text(row.get("name")),
                slug=_coerce_text(row.get("slug")),
            )

    def users(self) -> Iterable[SourceUser]:
        sql = (
            "SELECT ID AS id, user_login AS user_login, "
            "display_name AS display_name, user_email AS user_email "
            f"FROM {self._t('users')}"
        )
        for row in self._stream(sql):
            user_id = _to_int(_coerce_optional_text(row.get("id")))
            if user_id is None:
                continue
            yield SourceUser(
                wp_user_id=user_id,
                user_login=_coerce_text(row.get("user_login")),
                display_name=_coerce_text(row.get("display_name")),
                email=_coerce_text(row.get("user_email")),
            )

    def brands(self) -> Iterable[SourceBrand]:
        sql = (
            "SELECT\n"
            "  p.ID AS id,\n"
            "  p.post_title AS post_title,\n"
            "  p.post_name AS post_name,\n"
            "  p.post_content AS post_content,\n"
            "  p.post_date AS post_date,\n"
            "  (SELECT tt.term_id\n"
            f"     FROM {self._t('term_relationships')} tr\n"
            f"     JOIN {self._t('term_taxonomy')} tt "
            "ON tt.term_taxonomy_id = tr.term_taxonomy_id\n"
            "    WHERE tr.object_id = p.ID "
            f"AND tt.taxonomy = '{_INDUSTRY_TAXONOMY}'\n"
            "    LIMIT 1) AS industry_term_id,\n"
            f"{self._meta_pivot_sql(_BRAND_META_PIVOTS)}\n"
            f"FROM {self._t('posts')} p\n"
            f"LEFT JOIN {self._t('postmeta')} pm "
            "ON pm.post_id = p.ID "
            f"AND pm.meta_key IN ({self._meta_key_list(_BRAND_META_PIVOTS)})\n"
            "WHERE p.post_type = 'brand'\n"
            "GROUP BY p.ID, p.post_title, p.post_name, p.post_content, p.post_date"
        )
        for row in self._stream(sql):
            post_id = _to_int(_coerce_optional_text(row.get("id")))
            if post_id is None:
                continue
            yield SourceBrand(
                wp_post_id=post_id,
                name=_coerce_text(row.get("post_title")),
                slug=_coerce_text(row.get("post_name")),
                body=_coerce_text(row.get("post_content")),
                wp_post_date=_coerce_datetime(row.get("post_date")),
                industry_wp_term_id=_to_int(
                    _coerce_optional_text(row.get("industry_term_id"))
                ),
                website_url=_coerce_text(row.get("website_url")),
                founded_year=_to_int(_coerce_optional_text(row.get("founded_year"))),
                headquarters=_coerce_text(row.get("headquarters")),
                average_rating=_to_decimal(
                    _coerce_optional_text(row.get("average_rating"))
                ),
                seo_title=_coerce_text(row.get("seo_title")),
                seo_metadesc=_coerce_text(row.get("seo_metadesc")),
            )

    def reviews(self) -> Iterable[SourceReview]:
        sql = (
            "SELECT\n"
            "  p.ID AS id,\n"
            "  p.post_title AS post_title,\n"
            "  p.post_name AS post_name,\n"
            "  p.post_content AS post_content,\n"
            "  p.post_date AS post_date,\n"
            "  p.post_author AS post_author,\n"
            f"{self._meta_pivot_sql(_REVIEW_META_PIVOTS)}\n"
            f"FROM {self._t('posts')} p\n"
            f"LEFT JOIN {self._t('postmeta')} pm "
            "ON pm.post_id = p.ID "
            f"AND pm.meta_key IN ({self._meta_key_list(_REVIEW_META_PIVOTS)})\n"
            "WHERE p.post_type = 'review'\n"
            "GROUP BY p.ID, p.post_title, p.post_name, p.post_content, "
            "p.post_date, p.post_author"
        )
        for row in self._stream(sql):
            post_id = _to_int(_coerce_optional_text(row.get("id")))
            if post_id is None:
                continue
            yield SourceReview(
                wp_post_id=post_id,
                title=_coerce_text(row.get("post_title")),
                slug=_coerce_text(row.get("post_name")),
                body=_coerce_text(row.get("post_content")),
                wp_post_date=_coerce_datetime(row.get("post_date")),
                rating=_to_int(_coerce_optional_text(row.get("rating"))),
                reviewer_name=_coerce_text(row.get("reviewer_name")),
                reviewer_location=_coerce_text(row.get("reviewer_location")),
                brand_wp_post_id=_to_int(_coerce_optional_text(row.get("brand"))),
                wp_user_id=_to_int(_coerce_optional_text(row.get("post_author"))),
            )


# --------------------------------------------------------------------------- #
# RestApiSource (alternative: read from the live WordPress REST API)
# --------------------------------------------------------------------------- #

def _iso_to_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a WP REST ISO-8601 timestamp (e.g. ``2026-05-19T20:28:55``)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return _make_aware_utc(parsed)


def _rendered(field) -> str:
    """Extract the ``.rendered`` string from a WP REST title/content field."""
    if isinstance(field, dict):
        return field.get("rendered", "") or ""
    return field or ""


def _brand_ref_id(acf_brand) -> Optional[int]:
    """Normalize the ACF ``brand`` post-object reference to a post id.

    Depending on the ACF return-format the REST payload may carry a bare id, a
    numeric string, or an embedded object (`{"ID": …}` / `{"id": …}`).
    """
    if isinstance(acf_brand, dict):
        return _to_int(acf_brand.get("ID") or acf_brand.get("id"))
    if isinstance(acf_brand, bool):  # guard: bool is an int subclass
        return None
    if isinstance(acf_brand, int):
        return acf_brand
    return _to_int(acf_brand)


def _urllib_get_json(url: str):
    """Default HTTP getter: GET ``url`` and parse JSON, using only the stdlib.

    Kept dependency-free (no ``requests``) and injectable so ``RestApiSource``
    is unit-testable with canned payloads. Any transport/HTTP error propagates
    to the caller (the import command turns it into a ``CommandError``).
    """
    import json
    import urllib.request

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (trusted base URL)
        return json.loads(resp.read().decode("utf-8"))


class RestApiSource:
    """Read WordPress content from the live REST API under ``/wp-json/wp/v2/``.

    Yields the *same* four generators as the other sources, so the importer is
    unchanged — this is the payoff of the :class:`WordPressSource` protocol:
    adding a third origin is a new class, not an importer rewrite.

    It reads the CPT ``rest_base`` collections (``brands``/``reviews``), the
    ``industry`` taxonomy, and ``users``, following simple ``per_page``/``page``
    pagination. ACF fields arrive inline under the ``acf`` key (the mu-plugin
    sets ``show_in_rest``); Yoast title/description are read from
    ``yoast_head_json`` when present.

    Config: ``base_url`` (default ``$WORDPRESS_REST_BASE`` or
    ``http://localhost:8080``). ``fetch_json`` is injectable for tests; the
    default uses ``urllib`` (no third-party dependency). This source needs the
    WordPress stack running — hence it is an *alternative*, not the default.
    """

    def __init__(self, base_url: Optional[str] = None, per_page: int = 100, fetch_json=None):
        import os

        base = base_url or os.environ.get("WORDPRESS_REST_BASE", "http://localhost:8080")
        self.base_url = base.rstrip("/")
        self.per_page = per_page
        self._fetch_json = fetch_json or _urllib_get_json

    # -- paging ------------------------------------------------------------ #

    def _paged(self, resource: str) -> Iterator[dict]:
        """Yield every item of a REST collection, following page-number paging."""
        page = 1
        while True:
            url = (
                f"{self.base_url}/wp-json/wp/v2/{resource}"
                f"?per_page={self.per_page}&page={page}"
            )
            batch = self._fetch_json(url)
            # WP returns an error object (dict) once the page number exceeds the
            # range; anything that isn't a non-empty list ends the walk.
            if not isinstance(batch, list) or not batch:
                return
            for item in batch:
                yield item
            if len(batch) < self.per_page:
                return
            page += 1

    # -- generators -------------------------------------------------------- #

    def industries(self) -> Iterable[SourceIndustry]:
        for term in self._paged("industry"):
            term_id = _to_int(term.get("id"))
            if term_id is None:
                continue
            yield SourceIndustry(
                wp_term_id=term_id,
                name=term.get("name", "") or "",
                slug=term.get("slug", "") or "",
            )

    def users(self) -> Iterable[SourceUser]:
        for user in self._paged("users"):
            user_id = _to_int(user.get("id"))
            if user_id is None:
                continue
            yield SourceUser(
                wp_user_id=user_id,
                # REST rarely exposes user_login/email (privacy); fall back to
                # the public slug/name. `email` stays blank when absent.
                user_login=user.get("slug", "") or "",
                display_name=user.get("name", "") or "",
                email=user.get("email", "") or "",
            )

    def brands(self) -> Iterable[SourceBrand]:
        for post in self._paged("brands"):
            post_id = _to_int(post.get("id"))
            if post_id is None:
                continue
            acf = post.get("acf") or {}
            yoast = post.get("yoast_head_json") or {}
            industry_ids = post.get("industry") or []  # taxonomy term ids
            industry_term_id = _to_int(industry_ids[0]) if industry_ids else None
            yield SourceBrand(
                wp_post_id=post_id,
                name=_rendered(post.get("title")),
                slug=post.get("slug", "") or "",
                body=_rendered(post.get("content")),
                wp_post_date=_iso_to_datetime(post.get("date")),
                industry_wp_term_id=industry_term_id,
                website_url=acf.get("website_url", "") or "",
                founded_year=_to_int(acf.get("founded_year")),
                headquarters=acf.get("headquarters", "") or "",
                average_rating=_to_decimal(acf.get("average_rating")),
                seo_title=yoast.get("title", "") or "",
                seo_metadesc=yoast.get("description", "") or "",
            )

    def reviews(self) -> Iterable[SourceReview]:
        for post in self._paged("reviews"):
            post_id = _to_int(post.get("id"))
            if post_id is None:
                continue
            acf = post.get("acf") or {}
            yield SourceReview(
                wp_post_id=post_id,
                title=_rendered(post.get("title")),
                slug=post.get("slug", "") or "",
                body=_rendered(post.get("content")),
                wp_post_date=_iso_to_datetime(post.get("date")),
                rating=_to_int(acf.get("rating")),
                reviewer_name=acf.get("reviewer_name", "") or "",
                reviewer_location=acf.get("reviewer_location", "") or "",
                brand_wp_post_id=_brand_ref_id(acf.get("brand")),
                wp_user_id=_to_int(post.get("author")),
            )
