"""``import_wordpress`` management command (the Migration_Command).

Imports WordPress content (Industries, Reviewers, Brands, Reviews) into the
Django database through a pluggable :class:`WordPressSource`. The default source
parses the committed ``db/dump.sql`` file; a ``mariadb`` source streams from a
live MariaDB/MySQL connection; a ``rest`` source reads the live WordPress REST
API under ``/wp-json/wp/v2/``.

Usage::

    python manage.py import_wordpress [--source=dump|mariadb|rest] [--dump-path=...]

Behavior (Requirement 5):

- Default source is :class:`SqlDumpSource` over ``<REPO_ROOT>/db/dump.sql``
  (Req 5.1).
- If the source is unreachable/unreadable (missing dump file, connection or
  driver error), the command raises :class:`CommandError`: Django exits with a
  non-zero status, the reason is written to stderr, and no summary is printed
  (Req 5.8).
- On a successful run the command prints a per-model created/updated summary to
  stdout (Req 5.9).
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.wp_import.importer import run_import
from catalog.wp_import.sources import MariaDbSource, RestApiSource, SqlDumpSource


class Command(BaseCommand):
    help = (
        "Import WordPress content (Industries, Reviewers, Brands, Reviews) into "
        "the Django database. Re-runnable and idempotent."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--source",
            choices=["dump", "mariadb", "rest"],
            default="dump",
            help=(
                "Where to read WordPress content from: 'dump' (default, parses "
                "the SQL dump), 'mariadb' (live DB connection), or 'rest' (the "
                "live WordPress REST API under /wp-json/wp/v2/)."
            ),
        )
        parser.add_argument(
            "--rest-base",
            default=None,
            help=(
                "Base URL of the WordPress site for --source=rest "
                "(default: $WORDPRESS_REST_BASE or http://localhost:8080)."
            ),
        )
        parser.add_argument(
            "--dump-path",
            default=str(Path(settings.REPO_ROOT) / "db" / "dump.sql"),
            help=(
                "Path to the mysqldump SQL file (only used with --source=dump). "
                "Defaults to <REPO_ROOT>/db/dump.sql."
            ),
        )

    def handle(self, *args, **options) -> None:
        source_kind = options["source"]

        # Build the chosen source. Any failure to construct or reach the source
        # surfaces as a CommandError (non-zero exit, reason to stderr, no
        # summary) per Requirement 5.8.
        source = self._build_source(source_kind, options)

        # Run the import. A source that becomes unreadable mid-stream (e.g. a
        # connection drop or a parse error) also fails the run with a
        # CommandError so no partial summary is printed.
        try:
            summary = run_import(source)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface any read failure cleanly
            raise CommandError(
                f"Import failed while reading the source: {exc}"
            ) from exc

        self._print_summary(summary)

    # -- source construction ---------------------------------------------- #

    def _build_source(self, source_kind: str, options: dict):
        if source_kind == "dump":
            dump_path = Path(options["dump_path"])
            # Validate the dump exists and is readable before running so an
            # unreadable source fails fast with a clear reason (Req 5.8).
            if not dump_path.exists():
                raise CommandError(
                    f"SQL dump not found at '{dump_path}'. "
                    "Pass --dump-path to point at the WordPress dump file."
                )
            if not dump_path.is_file():
                raise CommandError(
                    f"SQL dump path '{dump_path}' is not a file."
                )
            try:
                # A minimal readability probe; the parser streams the file later.
                with dump_path.open("r", encoding="utf-8", errors="replace") as fh:
                    fh.read(1)
            except OSError as exc:
                raise CommandError(
                    f"SQL dump at '{dump_path}' could not be read: {exc}"
                ) from exc
            return SqlDumpSource(str(dump_path))

        if source_kind == "mariadb":
            # Connection settings come from environment variables (see
            # MariaDbSource). Construction is cheap; connection/driver errors
            # surface when the importer consumes a generator and are turned into
            # a CommandError in handle().
            try:
                return MariaDbSource()
            except Exception as exc:  # noqa: BLE001
                raise CommandError(
                    f"Could not configure the MariaDB source: {exc}"
                ) from exc

        if source_kind == "rest":
            # Construction is cheap; unreachable-host/HTTP errors surface when
            # the importer consumes a generator and become a CommandError in
            # handle(). Needs the WordPress stack running.
            try:
                return RestApiSource(base_url=options.get("rest_base"))
            except Exception as exc:  # noqa: BLE001
                raise CommandError(
                    f"Could not configure the REST source: {exc}"
                ) from exc

        # argparse choices guard this, but keep an explicit fallback.
        raise CommandError(f"Unknown source: {source_kind!r}")

    # -- summary output ---------------------------------------------------- #

    def _print_summary(self, summary) -> None:
        data = summary.as_dict()
        self.stdout.write(self.style.SUCCESS("WordPress import complete."))
        self.stdout.write("Per-model created / updated:")
        for model_label, counts in data.items():
            self.stdout.write(
                "  {label:<12} created={created:<6} updated={updated}".format(
                    label=model_label,
                    created=counts["created"],
                    updated=counts["updated"],
                )
            )
