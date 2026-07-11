"""Streaming tokenizer for mysqldump ``INSERT`` statements.

WordPress dumps produced by ``mysqldump`` write one ``INSERT INTO`` statement
per table row (or per batched row group) on a single physical line, with real
newlines inside string values escaped as ``\\n``. That property lets us read the
dump line by line and keep memory flat regardless of dump size, which is the
mechanism behind the "scale to 100x" story for the SQL-dump source.

The public helpers are:

* :func:`stream_insert_rows` - yield each row (a ``list`` of field values) for a
  given table, reading the file lazily one line at a time.
* :func:`parse_insert_values` - parse the ``VALUES (...), (...)`` clause of a
  single ``INSERT`` statement into a list of rows.

Field values come back as Python ``str`` for quoted values (fully unescaped),
``None`` for SQL ``NULL``, and the raw token text for unquoted numerics.
"""

from __future__ import annotations

from typing import Iterator, List, Optional

__all__ = ["stream_insert_rows", "parse_insert_values", "iter_value_tuples"]

Row = List[Optional[str]]

# MySQL single-character backslash escape sequences.
_ESCAPES = {
    "0": "\0",
    "b": "\b",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "Z": "\x1a",
    "\\": "\\",
    "'": "'",
    '"': '"',
}


def _unescape(body: str) -> str:
    """Resolve MySQL escape sequences in the body of a quoted string literal."""
    out: List[str] = []
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == "\\" and i + 1 < n:
            nxt = body[i + 1]
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def iter_value_tuples(clause: str) -> Iterator[Row]:
    """Yield each ``(...)`` tuple from a ``VALUES`` clause as a list of fields.

    Handles quoted strings with backslash escapes and doubled ``''`` quotes,
    unquoted numerics, and ``NULL``. Commas and parentheses inside string
    literals are ignored, so post bodies containing ``)`` or ``,`` parse
    correctly.
    """
    i = 0
    n = len(clause)
    while i < n:
        # Advance to the start of the next tuple.
        while i < n and clause[i] != "(":
            i += 1
        if i >= n:
            return
        i += 1  # consume '('
        row: Row = []
        while i < n:
            ch = clause[i]
            if ch == "'":
                # Quoted string literal.
                i += 1
                buf: List[str] = []
                while i < n:
                    c = clause[i]
                    if c == "\\" and i + 1 < n:
                        buf.append(c)
                        buf.append(clause[i + 1])
                        i += 2
                        continue
                    if c == "'":
                        # Doubled '' is an escaped quote, not a terminator.
                        if i + 1 < n and clause[i + 1] == "'":
                            buf.append("'")
                            i += 2
                            continue
                        i += 1  # consume closing quote
                        break
                    buf.append(c)
                    i += 1
                row.append(_unescape("".join(buf)))
            elif ch == ",":
                i += 1
            elif ch == ")":
                i += 1
                break
            elif ch.isspace():
                i += 1
            else:
                # Unquoted token: number or NULL, terminated by ',' or ')'.
                start = i
                while i < n and clause[i] not in ",)":
                    i += 1
                token = clause[start:i].strip()
                row.append(None if token.upper() == "NULL" else token)
        yield row


def parse_insert_values(statement: str) -> List[Row]:
    """Parse a full ``INSERT INTO ... VALUES ...;`` statement into rows."""
    marker = " VALUES "
    idx = statement.find(marker)
    if idx == -1:
        return []
    return list(iter_value_tuples(statement[idx + len(marker):]))


def stream_insert_rows(path: str, table: str, encoding: str = "utf-8") -> Iterator[Row]:
    """Stream every inserted row for ``table`` from the dump at ``path``.

    Reads the file one line at a time so memory stays flat for arbitrarily
    large dumps.
    """
    prefix = f"INSERT INTO `{table}` VALUES "
    with open(path, "r", encoding=encoding, newline="") as handle:
        for line in handle:
            if line.startswith(prefix):
                yield from iter_value_tuples(line[len(prefix):])
