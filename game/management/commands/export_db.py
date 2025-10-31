import os
import gzip
from typing import Optional, Set, List

from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.conf import settings
from django.core import serializers


EXCLUDE_MODEL_NAMES = {
    "ContentType",
    "Session",
}


def resolve_output_path(path: str) -> str:
    """Resolve a possibly-relative output path against BASE_DIR.

    Args:
        path: Output file path (absolute or relative).

    Returns:
        Absolute path inside BASE_DIR if a relative path was provided.
    """
    base = getattr(settings, "BASE_DIR", os.getcwd())
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return path


class Command(BaseCommand):
    """Export database rows to a JSON file (Django serialization) with optional apps filter.

    This command streams model instances to a JSON array in chunks (to avoid
    building one huge list in memory). Use ``--apps`` to limit exported objects
    to models that belong to a set of app labels (comma-separated). Use
    ``--indent N`` to pretty-print multi-line JSON.

    Example usage:
        # Default: writes db_backups/backup.json under BASE_DIR
        python manage.py export_db

        # Pretty-printed, only export 'game' and 'auth' apps
        python manage.py export_db --apps game,auth --indent 2

        # Gzipped output inside project
        python manage.py export_db -o db_backups/backup.json.gz --indent 2
    """

    help = "Export database rows to a JSON file (Django serialization). Supports --apps filter."

    def add_arguments(self, parser):
        """Define command-line arguments."""
        parser.add_argument(
            "--output",
            "-o",
            help=(
                "Output file path (relative paths are created inside BASE_DIR). "
                "Use '-' for stdout. Use .gz to gzip."
            ),
            default="db_backups/backup.json",
        )
        parser.add_argument(
            "--apps",
            help="Comma-separated app labels to export (e.g. 'auth,game'). If omitted exports all apps.",
            default=None,
        )
        parser.add_argument(
            "--exclude",
            help="Comma-separated model names to exclude (ModelName or app_label.ModelName).",
            default="",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=None,
            help="JSON indent level (pass an integer). If omitted output is compact (single line).",
        )
        parser.add_argument(
            "--natural-foreign",
            action="store_true",
            help="Use natural foreign keys when serializing (if supported by models).",
        )
        parser.add_argument(
            "--natural-primary",
            action="store_true",
            help="Use natural primary keys when serializing (if supported).",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=1000,
            help="Number of objects to serialize per chunk (memory / performance tuning).",
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
        return {p.strip() for p in apps_arg.split(",") if p.strip()}

    def handle(self, *args, **options):
        """Main command entry point.

        Steps:
        1. Collect models to export (apply --apps and --exclude filters).
        2. Stream objects per-model and per-chunk, serializing each chunk and
           writing the inner JSON to the output file/stream.
        3. Produce pretty JSON when --indent is provided.
        """
        output = options["output"]
        apps_arg = options["apps"]
        exclude_arg = options["exclude"]
        indent = options["indent"]
        use_nat_foreign = options["natural_foreign"]
        use_nat_primary = options["natural_primary"]
        chunk_size = options["chunk_size"]

        apps_filter = self._parse_apps_arg(apps_arg)
        exclude_set = set(x.strip() for x in exclude_arg.split(",") if x.strip())

        # Collect models, applying app & exclude filters.
        all_models = list(apps.get_models())
        models_to_export: List[type] = []
        for m in all_models:
            full_name = f"{m._meta.app_label}.{m.__name__}"
            if m.__name__ in EXCLUDE_MODEL_NAMES or full_name in exclude_set or m.__name__ in exclude_set:
                # skip common internal models or anything explicitly excluded
                continue
            if apps_filter is not None and m._meta.app_label not in apps_filter:
                # skip models that are not in the requested apps
                continue
            models_to_export.append(m)

        if not models_to_export:
            raise CommandError("No models found to export (check --apps and --exclude).")

        # Determine output destination
        write_to_stdout = (output == "-")
        if not write_to_stdout:
            output = resolve_output_path(output)

        # Open output (gz or plain file) or use stdout
        if write_to_stdout:
            write_chunk = lambda s: self.stdout.write(s)
            close_fh = lambda: None
        else:
            if output.endswith(".gz"):
                fh = gzip.open(output, "wt", encoding="utf-8")
            else:
                fh = open(output, "w", encoding="utf-8")
            write_chunk = fh.write
            close_fh = fh.close

        total_objects = 0
        first_piece = True

        try:
            # Prepare array formatting depending on pretty vs compact
            if indent is not None:
                write_chunk("[\n")
                separator = ",\n"
                closing = "\n]\n"
            else:
                write_chunk("[")
                separator = ","
                closing = "]"

            # Stream per model to limit memory usage
            for model in models_to_export:
                qs = model._default_manager.all().iterator()
                chunk: List[object] = []
                for obj in qs:
                    chunk.append(obj)
                    if len(chunk) >= chunk_size:
                        serialized = serializers.serialize(
                            "json",
                            chunk,
                            indent=indent,
                            use_natural_foreign_keys=use_nat_foreign,
                            use_natural_primary_keys=use_nat_primary,
                        )
                        # Extract the JSON inner array content (strip leading/trailing [ ])
                        start = serialized.find('[')
                        end = serialized.rfind(']')
                        inner = serialized[start+1:end]

                        if indent is not None:
                            # Trim surrounding newlines for nicer concatenation
                            inner = inner.lstrip('\n').rstrip('\n')
                            if inner:
                                if not first_piece:
                                    write_chunk(separator)
                                write_chunk(inner)
                                first_piece = False
                        else:
                            inner = inner.strip()
                            if inner:
                                if not first_piece:
                                    write_chunk(separator)
                                write_chunk(inner)
                                first_piece = False

                        total_objects += len(chunk)
                        chunk = []

                # Flush any remaining objects for this model
                if chunk:
                    serialized = serializers.serialize(
                        "json",
                        chunk,
                        indent=indent,
                        use_natural_foreign_keys=use_nat_foreign,
                        use_natural_primary_keys=use_nat_primary,
                    )
                    start = serialized.find('[')
                    end = serialized.rfind(']')
                    inner = serialized[start+1:end]

                    if indent is not None:
                        inner = inner.lstrip('\n').rstrip('\n')
                        if inner:
                            if not first_piece:
                                write_chunk(separator)
                            write_chunk(inner)
                            first_piece = False
                    else:
                        inner = inner.strip()
                        if inner:
                            if not first_piece:
                                write_chunk(separator)
                            write_chunk(inner)
                            first_piece = False

                    total_objects += len(chunk)

            # Close JSON array
            write_chunk(closing)
        finally:
            close_fh()

        self.stdout.write(self.style.SUCCESS(f"Exported {total_objects} objects to {output}"))
