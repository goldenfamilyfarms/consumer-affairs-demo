"""Unit tests for the streaming mysqldump ``INSERT`` tokenizer.

These exercise :mod:`catalog.wp_import.dump_parser` directly: the value-tuple
tokenizer (quoted strings, backslash escapes, doubled ``''`` quotes, commas and
parentheses inside literals, unquoted numerics, and ``NULL``) and the
line-oriented ``stream_insert_rows`` reader.
"""

from __future__ import annotations

import pytest

from catalog.wp_import.dump_parser import (
    iter_value_tuples,
    parse_insert_values,
    stream_insert_rows,
)


# --------------------------------------------------------------------------- #
# iter_value_tuples / parse_insert_values
# --------------------------------------------------------------------------- #

def test_parses_simple_numeric_and_string_row():
    rows = list(iter_value_tuples("(1,'hello',2)"))
    assert rows == [["1", "hello", "2"]]


def test_null_becomes_none_case_insensitive():
    rows = list(iter_value_tuples("(NULL,'x',null,NuLl)"))
    assert rows == [[None, "x", None, None]]


def test_multiple_tuples_in_one_clause():
    rows = list(iter_value_tuples("(1,'a'),(2,'b'),(3,'c')"))
    assert rows == [["1", "a"], ["2", "b"], ["3", "c"]]


def test_comma_inside_string_literal_is_not_a_separator():
    rows = list(iter_value_tuples("(1,'a,b,c',2)"))
    assert rows == [["1", "a,b,c", "2"]]


def test_parens_inside_string_literal_are_not_tuple_boundaries():
    # A body containing ')' and '(' must not terminate the tuple early.
    rows = list(iter_value_tuples("(1,'foo (bar) baz)',2)"))
    assert rows == [["1", "foo (bar) baz)", "2"]]


def test_doubled_single_quote_is_an_escaped_quote():
    # MySQL's '' inside a string literal represents a single quote.
    rows = list(iter_value_tuples("(1,'it''s fine')"))
    assert rows == [["1", "it's fine"]]


def test_backslash_escaped_quote_within_string():
    rows = list(iter_value_tuples(r"(1,'it\'s ok')"))
    assert rows == [["1", "it's ok"]]


def test_backslash_escape_sequences_are_resolved():
    # \n -> newline, \t -> tab, \\ -> single backslash.
    rows = list(iter_value_tuples(r"(1,'line1\nline2\tcol\\end')"))
    assert rows == [["1", "line1\nline2\tcol\\end"]]


def test_escaped_backslash_before_quote_does_not_terminate_early():
    # 'a\\' is the two-char value a + backslash; the closing quote follows.
    rows = list(iter_value_tuples(r"(1,'a\\',2)"))
    assert rows == [["1", "a\\", "2"]]


def test_empty_string_literal():
    rows = list(iter_value_tuples("(1,'',2)"))
    assert rows == [["1", "", "2"]]


def test_whitespace_between_fields_is_ignored():
    rows = list(iter_value_tuples("( 1 , 'a' , 2 )"))
    assert rows == [["1", "a", "2"]]


def test_negative_and_decimal_numerics_kept_as_raw_tokens():
    rows = list(iter_value_tuples("(-5,'x',3.14)"))
    assert rows == [["-5", "x", "3.14"]]


def test_parse_insert_values_splits_on_values_marker():
    stmt = "INSERT INTO `wp_terms` VALUES (1,'Finance','finance'),(2,'Health','health');"
    rows = parse_insert_values(stmt)
    assert rows == [["1", "Finance", "finance"], ["2", "Health", "health"]]


def test_parse_insert_values_without_marker_returns_empty():
    assert parse_insert_values("SELECT 1;") == []


# --------------------------------------------------------------------------- #
# stream_insert_rows
# --------------------------------------------------------------------------- #

def _write(tmp_path, text: str) -> str:
    path = tmp_path / "dump.sql"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_stream_insert_rows_yields_only_matching_table(tmp_path):
    dump = (
        "INSERT INTO `wp_terms` VALUES (1,'Finance','finance');\n"
        "INSERT INTO `wp_users` VALUES (7,'alice');\n"
        "INSERT INTO `wp_terms` VALUES (2,'Health','health');\n"
    )
    rows = list(stream_insert_rows(_write(tmp_path, dump), "wp_terms"))
    assert rows == [["1", "Finance", "finance"], ["2", "Health", "health"]]


def test_stream_insert_rows_ignores_non_insert_lines(tmp_path):
    dump = (
        "-- a comment line\n"
        "DROP TABLE IF EXISTS `wp_terms`;\n"
        "INSERT INTO `wp_terms` VALUES (1,'Finance','finance');\n"
    )
    rows = list(stream_insert_rows(_write(tmp_path, dump), "wp_terms"))
    assert rows == [["1", "Finance", "finance"]]


def test_stream_insert_rows_missing_table_yields_nothing(tmp_path):
    dump = "INSERT INTO `wp_users` VALUES (7,'alice');\n"
    assert list(stream_insert_rows(_write(tmp_path, dump), "wp_posts")) == []
