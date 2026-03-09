"""
Import JSON (Django serialization) into the database with optional filtering.

This management command imports JSON previously exported by `export_db` (Django
serialized objects). It supports gzipped input, an app-label filter (--apps),
an optional full DB flush (--clear), and resetting database sequences for
PostgreSQL-driven backends.

Behavior summary
---------------
- Input: path to JSON or '-' for stdin. '.gz' files are supported.
- --apps: comma-separated list of app labels to import (if omitted, import all).
- --ignore-errors: attempt to continue past individual object save errors.
- --clear: run `manage.py flush --noinput` before importing (DANGEROUS).
- Sequence reset: automatically attempted for Postgres or when --reset-sequences is given.
"""

import os
import gzip
from typing import Optional, Set, List, Iterable, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.core import serializers
from django.db import transaction, IntegrityError, connection
from django.core.management import call_command
from django.conf import settings
from django.apps import apps
from django.core.management.color import no_style


class Command(BaseCommand):
    """
    Import JSON exported by export_db (Django serialization) with optional app filter.

    The command accepts a Django-serialized JSON array (optionally gzipped) and
    deserializes objects into the database. Use `--apps` to restrict import to
    objects belonging to a set of app labels (comma-separated). When PostgreSQL
    is detected (or `--reset-sequences` is passed) the command will attempt to
    reset DB sequences — by default for all models, or only for the selected apps
    when `--apps` is used.
    """

    help = "Import JSON exported by export_db (Django serialization). Supports --apps filter."

    def add_arguments(self, parser):
        """Define command-line arguments."""
        parser.add_argument(
            "input",
            help="Input JSON file path (relative paths searched in BASE_DIR). Use '-' for stdin. Supports .gz.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear the database via `flush --noinput` before importing. USE WITH CARE.",
        )
        parser.add_argument(
            "--ignore-errors",
            action="store_true",
            help="Try to continue past individual object errors (logs them).",
        )
        parser.add_argument(
            "--reset-sequences",
            action="store_true",
            help="Attempt to reset DB sequences after import (Postgres only). Default: on for Postgres.",
        )
        parser.add_argument(
            "--apps",
            help="Comma-separated app labels to import (e.g. 'auth,game'). If omitted imports all apps.",
            default=None,
        )

    # -------------------------
    # Helper utilities
    # -------------------------
    def _parse_apps_arg(self, apps_arg: Optional[str]) -> Optional[Set[str]]:
        """
        Parse the --apps argument into a set of app labels.

        Returns a set of app labels, or None if apps_arg is falsy.
        """
        if not apps_arg:
            return None
        return {p.strip() for p in apps_arg.split(",") if p.strip()}

    def _resolve_input_path(self, path: str) -> str:
        """
        Resolve a possibly-relative input path against BASE_DIR.

        If path is absolute, return as-is. If relative, join with BASE_DIR (or cwd).
        """
        base = getattr(settings, "BASE_DIR", os.getcwd())
        if not os.path.isabs(path):
            path = os.path.join(base, path)
        return path

    def _read_raw_input(self, input_path: str, from_stdin: bool) -> str:
        """
        Read input JSON text from a file (supports .gz) or from stdin.

        Raises CommandError if file missing or unreadable.
        """
        if from_stdin:
            return self.stdin.read()

        if not os.path.exists(input_path):
            raise CommandError(f"Input file not found: {input_path}")

        try:
            if input_path.endswith(".gz"):
                with gzip.open(input_path, "rt", encoding="utf-8") as fh:
                    return fh.read()
            else:
                with open(input_path, "r", encoding="utf-8") as fh:
                    return fh.read()
        except OSError as e:
            raise CommandError(f"Failed reading input file '{input_path}': {e}")

    def _deserialized_iter(self, raw: str) -> Iterable:
        """
        Return an iterator of deserialized objects from a JSON string.

        Raises CommandError if deserialization fails.
        """
        try:
            return serializers.deserialize("json", raw)
        except Exception as e:
            raise CommandError(f"Failed to deserialize input JSON: {e}")

    def _maybe_flush(self):
        """Perform database flush (via manage.py flush) if requested."""
        try:
            call_command("flush", "--noinput")
        except Exception as e:
            raise CommandError(f"Failed to flush database: {e}")

    # -------------------------
    # Import core
    # -------------------------
    def _import_objects(
        self,
        deserialized_iter: Iterable,
        apps_filter: Optional[Set[str]],
        ignore_errors: bool
    ) -> Tuple[int, int, List[str]]:
        """
        Iterate the deserialized objects and save them to the DB.

        Returns (saved_count, skipped_count, errors_list).

        Behavior:
        - If apps_filter is provided, objects whose model's app_label are not in
          the set will be skipped (counted in skipped_count).
        - If ignore_errors is True, exceptions for individual objects are logged
          and the loop continues; objects are saved in per-object transactions
          to avoid leaving partial state locked in a big transaction.
        - If ignore_errors is False, the entire import runs in one transaction
          and any error aborts the import (exception propagates).
        """
        saved = 0
        skipped = 0
        errors: List[str] = []

        if ignore_errors:
            # Save each object in its own small transaction so we can continue on error.
            for des_obj in deserialized_iter:
                try:
                    obj_app_label = des_obj.object._meta.app_label
                except Exception:
                    skipped += 1
                    continue

                if apps_filter is not None and obj_app_label not in apps_filter:
                    skipped += 1
                    continue

                try:
                    with transaction.atomic():
                        des_obj.save()
                    saved += 1
                except IntegrityError as e:
                    msg = f"IntegrityError saving {des_obj}: {e}"
                    errors.append(msg)
                    self.stderr.write(self.style.ERROR(msg))
                    # continue to next object
                except Exception as e:
                    msg = f"Error saving {des_obj}: {e}"
                    errors.append(msg)
                    self.stderr.write(self.style.ERROR(msg))
                    # continue to next object
        else:
            # Perform the import inside a single transaction — consistent commit or rollback.
            try:
                with transaction.atomic():
                    for des_obj in deserialized_iter:
                        try:
                            obj_app_label = des_obj.object._meta.app_label
                        except Exception:
                            skipped += 1
                            continue

                        if apps_filter is not None and obj_app_label not in apps_filter:
                            skipped += 1
                            continue

                        des_obj.save()
                        saved += 1
            except IntegrityError:
                # Let the IntegrityError propagate after reporting (so caller sees it),
                # the transaction will rollback automatically.
                raise
            except Exception:
                # Any other exception also should propagate out and rollback.
                raise

        return saved, skipped, errors

    # -------------------------
    # Sequence reset
    # -------------------------
    def _reset_postgres_sequences(self, apps_filter: Optional[Set[str]]) -> Optional[str]:
        """
        Reset Postgres sequences for models (all models or filtered by apps_filter).

        Returns None on success, or an error message string on failure.
        """
        style = no_style()
        try:
            if apps_filter is None:
                models_to_reset = list(apps.get_models())
            else:
                models_to_reset = [m for m in apps.get_models() if m._meta.app_label in apps_filter]

            sql_list = connection.ops.sequence_reset_sql(style, models_to_reset)
            with connection.cursor() as cursor:
                for sql in sql_list:
                    if sql.strip():
                        cursor.execute(sql)
            return None
        except Exception as e:
            return f"Failed to reset sequences: {e}"

    # -------------------------
    # Main handle
    # -------------------------
    def handle(self, *args, **options):
        """
        Main command entry.

        Steps:
        1. Resolve input (path/stdin) and read raw JSON text.
        2. Optionally flush DB (--clear).
        3. Deserialize objects and import them (respecting --apps and --ignore-errors).
        4. Optionally reset Postgres sequences (automatic on Postgres or via --reset-sequences).
        5. Print a summary and raise CommandError on fatal problems.
        """
        input_path = options["input"]
        do_clear = options["clear"]
        ignore_errors = options["ignore_errors"]
        reset_sequences_flag = options["reset_sequences"]
        apps_arg = options["apps"]

        apps_filter = self._parse_apps_arg(apps_arg)

        read_from_stdin = (input_path == "-")
        if not read_from_stdin:
            input_path = self._resolve_input_path(input_path)

        # Optional DB flush
        if do_clear:
            self.stdout.write(self.style.WARNING("Flushing the database (this will remove ALL data)..."))
            self._maybe_flush()

        # Read raw input
        raw = self._read_raw_input(input_path, read_from_stdin) if not read_from_stdin else self._read_raw_input(input_path, True)
        if not raw or not raw.strip():
            raise CommandError("Input file is empty.")

        # Prepare deserialized iterator
        deserialized_iter = self._deserialized_iter(raw)

        # Import objects
        saved, skipped, errors = self._import_objects(deserialized_iter, apps_filter, ignore_errors)

        # Decide whether to reset sequences:
        engine = connection.settings_dict.get("ENGINE", "")
        is_postgres = "postgresql" in engine or connection.vendor == "postgresql"
        do_reset = reset_sequences_flag or is_postgres

        if do_reset and is_postgres:
            reset_err = self._reset_postgres_sequences(apps_filter)
            if reset_err:
                self.stderr.write(self.style.ERROR(reset_err))
                errors.append(reset_err)
            else:
                self.stdout.write(self.style.SUCCESS("Postgres sequences reset successfully."))

        # Summary
        self.stdout.write(self.style.SUCCESS(f"Imported {saved} objects."))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped {skipped} objects (outside --apps or invalid)."))
        if errors:
            self.stdout.write(self.style.WARNING(f"{len(errors)} errors occurred during import. See stderr for details."))
