"""Unit tests for :class:`catalog.wp_import.sources.SqlDumpSource` mapping.

These build small in-memory ``mysqldump``-shaped SQL fixtures (written to a
temp file) rather than using the full ``db/dump.sql``, and assert the source
layer's postmeta strategy (Requirement 3):

* ACF postmeta pairs are collapsed - the shadow ``_key`` rows are dropped.
* The ACF value rows map to first-class ``SourceBrand``/``SourceReview`` fields.
* The ``brand`` post-object reference maps to the review-to-brand FK id.
* The two Yoast keys (``_yoast_wpseo_title``/``_yoast_wpseo_metadesc``) are retained.
* Every other (non-mapped) postmeta key is dropped.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from catalog.wp_import.sources import SqlDumpSource


# --------------------------------------------------------------------------- #
# Fixture builders - emit faithful mysqldump INSERT lines
# --------------------------------------------------------------------------- #

def _sql_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _row(*values) -> str:
    return "(" + ",".join(_sql_value(v) for v in values) + ")"


def _post_row(
    *,
    post_id: int,
    post_type: str,
    title: str = "",
    name: str = "",
    content: str = "",
    author: int = 1,
    post_date: str = "2026-05-19 20:28:55",
) -> str:
    """A 23-column wp_posts row matching the real dump layout."""
    cols = [
        post_id,            # 0  ID
        author,             # 1  post_author
        post_date,          # 2  post_date
        post_date,          # 3  post_date_gmt
        content,            # 4  post_content
        title,              # 5  post_title
        "",                 # 6  post_excerpt
        "publish",          # 7  post_status
        "open",             # 8  comment_status
        "open",             # 9  ping_status
        "",                 # 10 post_password
        name,               # 11 post_name
        "",                 # 12 to_ping
        "",                 # 13 pinged
        post_date,          # 14 post_modified
        post_date,          # 15 post_modified_gmt
        "",                 # 16 post_content_filtered
        0,                  # 17 post_parent
        f"http://x/?p={post_id}",  # 18 guid
        0,                  # 19 menu_order
        post_type,          # 20 post_type
        "",                 # 21 post_mime_type
        0,                  # 22 comment_count
    ]
    return _row(*cols)


def _meta_row(meta_id: int, post_id: int, key: str, value) -> str:
    return _row(meta_id, post_id, key, value)


def _user_row(user_id: int, login: str, display_name: str, email: str = "a@b.c") -> str:
    # 10-column wp_users: display_name is at index 9.
    return _row(
        user_id, login, "hash", login, email, "", "", "2026-05-19 20:28:55", 0, display_name
    )


def _insert(table: str, *rows: str) -> str:
    return f"INSERT INTO `{table}` VALUES " + ",".join(rows) + ";\n"


def _write_dump(tmp_path, text: str) -> SqlDumpSource:
    path = tmp_path / "dump.sql"
    path.write_text(text, encoding="utf-8")
    return SqlDumpSource(str(path))


# --------------------------------------------------------------------------- #
# Brand postmeta mapping
# --------------------------------------------------------------------------- #

def _brand_dump() -> str:
    """A single brand with ACF value+shadow pairs, Yoast keys, and junk meta."""
    posts = _insert(
        "wp_posts",
        _post_row(post_id=10, post_type="brand", title="Acme", name="acme",
                  content="Acme body"),
    )
    postmeta = _insert(
        "wp_postmeta",
        # ACF value rows (kept -> first-class fields)
        _meta_row(1, 10, "website_url", "https://acme.example"),
        _meta_row(3, 10, "founded_year", "1998"),
        _meta_row(5, 10, "headquarters", "Austin, TX"),
        _meta_row(7, 10, "average_rating", "4.25"),
        # ACF shadow _key rows (must be dropped)
        _meta_row(2, 10, "_website_url", "field_abc123"),
        _meta_row(4, 10, "_founded_year", "field_def456"),
        _meta_row(6, 10, "_headquarters", "field_ghi789"),
        _meta_row(8, 10, "_average_rating", "field_jkl000"),
        # Yoast keys (retained)
        _meta_row(9, 10, "_yoast_wpseo_title", "Acme | Best"),
        _meta_row(10, 10, "_yoast_wpseo_metadesc", "Acme meta description"),
        # Non-mapped junk meta (dropped)
        _meta_row(11, 10, "_edit_last", "1"),
        _meta_row(12, 10, "_edit_lock", "1600000000:1"),
        _meta_row(13, 10, "_thumbnail_id", "42"),
    )
    return posts + postmeta


def test_brand_acf_values_map_to_first_class_fields(tmp_path):
    source = _write_dump(tmp_path, _brand_dump())
    brand = next(iter(source.brands()))

    assert brand.wp_post_id == 10
    assert brand.name == "Acme"
    assert brand.slug == "acme"
    assert brand.body == "Acme body"
    assert brand.website_url == "https://acme.example"
    assert brand.founded_year == 1998
    assert brand.headquarters == "Austin, TX"
    assert brand.average_rating == Decimal("4.25")


def test_brand_yoast_keys_are_retained(tmp_path):
    source = _write_dump(tmp_path, _brand_dump())
    brand = next(iter(source.brands()))

    assert brand.seo_title == "Acme | Best"
    assert brand.seo_metadesc == "Acme meta description"


def test_brand_shadow_keys_do_not_leak_into_values(tmp_path):
    # The shadow _key rows carry 'field_*' ACF references; if collapsing failed
    # those values could overwrite the real ones. Assert real values survived.
    source = _write_dump(tmp_path, _brand_dump())
    brand = next(iter(source.brands()))

    assert not brand.website_url.startswith("field_")
    assert brand.website_url == "https://acme.example"


def test_brand_non_mapped_postmeta_is_dropped(tmp_path):
    # _edit_last/_edit_lock/_thumbnail_id have no destination and must not appear
    # anywhere on the mapped dataclass.
    source = _write_dump(tmp_path, _brand_dump())
    brand = next(iter(source.brands()))

    values = [
        brand.website_url,
        brand.headquarters,
        brand.seo_title,
        brand.seo_metadesc,
        str(brand.founded_year),
    ]
    for junk in ("1600000000:1", "42"):
        assert junk not in values


# --------------------------------------------------------------------------- #
# Review postmeta mapping
# --------------------------------------------------------------------------- #

def _review_dump() -> str:
    posts = _insert(
        "wp_posts",
        _post_row(post_id=20, post_type="review", title="Great!", name="great",
                  content="Loved it", author=7),
    )
    postmeta = _insert(
        "wp_postmeta",
        # ACF value rows
        _meta_row(1, 20, "rating", "5"),
        _meta_row(3, 20, "reviewer_name", "Jane Doe"),
        _meta_row(5, 20, "reviewer_location", "Denver, CO"),
        _meta_row(7, 20, "brand", "10"),  # post-object reference -> brand id
        # ACF shadow _key rows (dropped)
        _meta_row(2, 20, "_rating", "field_r1"),
        _meta_row(4, 20, "_reviewer_name", "field_r2"),
        _meta_row(6, 20, "_reviewer_location", "field_r3"),
        _meta_row(8, 20, "_brand", "field_r4"),
        # Non-mapped junk (dropped)
        _meta_row(9, 20, "_edit_lock", "1600000000:7"),
    )
    return posts + postmeta


def test_review_acf_values_map_to_first_class_fields(tmp_path):
    source = _write_dump(tmp_path, _review_dump())
    review = next(iter(source.reviews()))

    assert review.wp_post_id == 20
    assert review.title == "Great!"
    assert review.slug == "great"
    assert review.body == "Loved it"
    assert review.rating == 5
    assert review.reviewer_name == "Jane Doe"
    assert review.reviewer_location == "Denver, CO"


def test_review_brand_reference_maps_to_fk_id(tmp_path):
    source = _write_dump(tmp_path, _review_dump())
    review = next(iter(source.reviews()))

    assert review.brand_wp_post_id == 10


def test_review_post_author_maps_to_reviewer_id(tmp_path):
    source = _write_dump(tmp_path, _review_dump())
    review = next(iter(source.reviews()))

    assert review.wp_user_id == 7


def test_review_shadow_and_junk_keys_are_dropped(tmp_path):
    source = _write_dump(tmp_path, _review_dump())
    review = next(iter(source.reviews()))

    assert review.reviewer_name == "Jane Doe"
    assert not review.reviewer_name.startswith("field_")
    # brand ref resolved to the numeric id, not the shadow 'field_r4'.
    assert review.brand_wp_post_id == 10


# --------------------------------------------------------------------------- #
# Post-type filtering and taxonomy mapping
# --------------------------------------------------------------------------- #

def test_only_brand_posts_yielded_by_brands(tmp_path):
    dump = _insert(
        "wp_posts",
        _post_row(post_id=1, post_type="post", title="Hello", name="hello"),
        _post_row(post_id=10, post_type="brand", title="Acme", name="acme"),
        _post_row(post_id=20, post_type="review", title="Great", name="great"),
    )
    source = _write_dump(tmp_path, dump)
    brands = list(source.brands())
    reviews = list(source.reviews())

    assert [b.wp_post_id for b in brands] == [10]
    assert [r.wp_post_id for r in reviews] == [20]


def test_industries_only_returns_industry_taxonomy_terms(tmp_path):
    dump = (
        _insert(
            "wp_terms",
            _row(1, "Finance", "finance"),
            _row(2, "Uncategorized", "uncategorized"),
        )
        + _insert(
            "wp_term_taxonomy",
            _row(100, 1, "industry", "", 0, 0),
            _row(101, 2, "category", "", 0, 0),
        )
    )
    source = _write_dump(tmp_path, dump)
    industries = list(source.industries())

    assert [(i.wp_term_id, i.name, i.slug) for i in industries] == [
        (1, "Finance", "finance"),
    ]


def test_brand_industry_resolved_via_term_relationships(tmp_path):
    dump = (
        _insert("wp_posts", _post_row(post_id=10, post_type="brand", title="Acme", name="acme"))
        + _insert("wp_terms", _row(1, "Finance", "finance"))
        + _insert("wp_term_taxonomy", _row(100, 1, "industry", "", 0, 0))
        + _insert("wp_term_relationships", _row(10, 100, 0))
    )
    source = _write_dump(tmp_path, dump)
    brand = next(iter(source.brands()))

    assert brand.industry_wp_term_id == 1


def test_users_map_to_source_users(tmp_path):
    dump = _insert("wp_users", _user_row(7, "jane", "Jane Doe", "jane@example.com"))
    source = _write_dump(tmp_path, dump)
    users = list(source.users())

    assert len(users) == 1
    assert users[0].wp_user_id == 7
    assert users[0].user_login == "jane"
    assert users[0].display_name == "Jane Doe"
    assert users[0].email == "jane@example.com"


def test_missing_optional_meta_yields_empty_defaults(tmp_path):
    # A brand with no postmeta at all should still map, with empty/None defaults.
    dump = _insert("wp_posts", _post_row(post_id=10, post_type="brand", title="Acme", name="acme"))
    source = _write_dump(tmp_path, dump)
    brand = next(iter(source.brands()))

    assert brand.website_url == ""
    assert brand.founded_year is None
    assert brand.average_rating is None
    assert brand.seo_title == ""
    assert brand.industry_wp_term_id is None
