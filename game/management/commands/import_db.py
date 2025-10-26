import os
import gzip
from typing import Optional, Set, List
from django.core.management.base import BaseCommand, CommandError
from django.core import serializers
from django.db import transaction, IntegrityError, connection
from django.core.management import call_command
from django.conf import settings
from django.apps import apps
from django.core.management.color import no_style


def resolve_input_path(path: str) -> str:
    """Resolve a possibly-relative input path against BASE_DIR.

    Args:
        path: Input file path (absolute or relative).

    Returns:
        Absolute path inside BASE_DIR if a relative path was provided.
    """
    base = getattr(settings, "BASE_DIR", os.getcwd())
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    return path


class Command(BaseCommand):
    """Import JSON exported by export_db (Django serialization) with optional app filter.

    The command accepts a Django-serialized JSON array (optionally gzipped) and
    deserializes objects into the database. Use `--apps` to restrict import to
    objects belonging to a set of app labels (comma-separated). When PostgreSQL
    is detected (or `--reset-sequences` is passed) the command will attempt to
    reset DB sequences — by default for all models, or only for the selected apps
    when `--apps` is used.

    Example usages:
        # Import everything
        python manage.py import_db db_backups/backup.json

        # Import gzipped file and continue past errors
        python manage.py import_db db_backups/backup.json.gz --ignore-errors

        # Import only objects for 'game' and 'auth' apps
        python manage.py import_db db_backups/backup.json --apps game,auth

        # Clear DB first (dangerous)
        python manage.py import_db db_backups/backup.json --clear
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

    def _parse_apps_arg(self, apps_arg: Optional[str]) -> Optional[Set[str]]:
        """Parse the --apps argument into a set of app labels.

        Args:
            apps_arg: Comma-separated app labels or None.

        Returns:
            A set of app labels if apps_arg provided, otherwise None.
        """
        if not apps_arg:
            return None
        # strip whitespace and ignore empty pieces
        return {p.strip() for p in apps_arg.split(",") if p.strip()}

    def handle(self, *args, **options):
        """Main command entry point.

        Steps:
        1. Resolve input path (or read stdin).
        2. Optionally flush DB (--clear).
        3. Read and deserialize JSON (supports .gz).
        4. Iterate deserialized objects, optionally filtering by --apps, saving each.
        5. Optionally reset sequences for Postgres (either all models or filtered models).
        """
        input_path = options["input"]
        do_clear = options["clear"]
        ignore_errors = options["ignore_errors"]
        reset_sequences_flag = options["reset_sequences"]
        apps_arg = options["apps"]

        apps_filter = self._parse_apps_arg(apps_arg)

        # Resolve path if not stdin
        read_from_stdin = (input_path == "-")
        if not read_from_stdin:
            input_path = resolve_input_path(input_path)
            if not os.path.exists(input_path):
                raise CommandError(f"Input file not found: {input_path}")

        # Optionally clear the DB (flush clears all data)
        if do_clear:
            self.stdout.write(self.style.WARNING("Flushing the database (this will remove ALL data)..."))
            call_command("flush", "--noinput")

        # Read input file / stdin
        if read_from_stdin:
            raw = self.stdin.read()
        else:
            if input_path.endswith(".gz"):
                with gzip.open(input_path, "rt", encoding="utf-8") as fh:
                    raw = fh.read()
            else:
                with open(input_path, "r", encoding="utf-8") as fh:
                    raw = fh.read()

        if not raw.strip():
            raise CommandError("Input file is empty.")

        # Create a generator of deserialized objects. This does not eagerly load into a list.
        try:
            deserialized_iter = serializers.deserialize("json", raw)
        except Exception as e:
            raise CommandError(f"Failed to deserialize input JSON: {e}")

        saved = 0
        skipped = 0
        errors: List[str] = []

        # Save objects inside a single atomic transaction. If --ignore-errors, continue past failing objects.
        with transaction.atomic():
            for dobj in deserialized_iter:
                # Determine the app label of the object's model
                try:
                    obj_app_label = dobj.object._meta.app_label
                except Exception:
                    # Defensive: if object lacks expected attributes, skip it
                    skipped += 1
                    continue

                # If --apps filter is provided, skip objects not in that set
                if apps_filter is not None and obj_app_label not in apps_filter:
                    skipped += 1
                    continue

                try:
                    # dobj.save() persists the object and handles m2m relationships
                    dobj.save()
                    saved += 1
                except IntegrityError as e:
                    msg = f"IntegrityError saving {dobj}: {e}"
                    errors.append(msg)
                    self.stderr.write(self.style.ERROR(msg))
                    if not ignore_errors:
                        # Re-raise to abort the transaction
                        raise
                except Exception as e:
                    msg = f"Error saving {dobj}: {e}"
                    errors.append(msg)
                    self.stderr.write(self.style.ERROR(msg))
                    if not ignore_errors:
                        raise

        # Decide whether to reset sequences:
        engine = connection.settings_dict.get("ENGINE", "")
        is_postgres = "postgresql" in engine or connection.vendor == "postgresql"
        do_reset = reset_sequences_flag or is_postgres

        if do_reset and is_postgres:
            # Build model list: either all models or only models in selected apps
            if apps_filter is None:
                models_to_reset = list(apps.get_models())
            else:
                models_to_reset = [m for m in apps.get_models() if m._meta.app_label in apps_filter]

            style = no_style()
            try:
                sql_list = connection.ops.sequence_reset_sql(style, models_to_reset)
                with connection.cursor() as cursor:
                    for sql in sql_list:
                        if sql.strip():
                            cursor.execute(sql)
                self.stdout.write(self.style.SUCCESS("Postgres sequences reset successfully."))
            except Exception as e:
                err_msg = f"Failed to reset sequences: {e}"
                self.stderr.write(self.style.ERROR(err_msg))
                errors.append(err_msg)

        # Summary output
        self.stdout.write(self.style.SUCCESS(f"Imported {saved} objects."))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped {skipped} objects (outside --apps or invalid)."))
        if errors:
            self.stdout.write(self.style.WARNING(f"{len(errors)} errors occurred during import. See stderr for details."))
