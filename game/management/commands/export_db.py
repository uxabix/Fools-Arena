"""
Export database rows to a JSON file (Django serialization) with optional apps filter.

This management command streams model instances into a JSON array in chunks to
avoid building one huge list in memory. It supports filtering exported models
by app label (--apps), excluding particular models (--exclude), pretty JSON
(--indent), natural key serialization, gzipped output and configurable
chunk sizes.

Design notes
- The `handle` entry point is small and delegates to helper methods for I/O
  and per-model streaming to follow single-responsibility and make unit
  testing easier.
- The command avoids loading entire querysets into memory by iterating and
  flushing chunks.

Examples
    python manage.py export_db
    python manage.py export_db --apps game,auth --indent 2 -o backups/backup.json.gz
"""

import os
import gzip
from typing import Optional, Set, List, Callable, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.conf import settings
from django.core import serializers


EXCLUDE_MODEL_NAMES = {
    "ContentType",
    "Session",
}


class Command(BaseCommand):
    """Export database rows to JSON using Django serializers.

    The implementation keeps `handle()` concise by delegating tasks to
    small helpers like `_resolve_output_path`, `_open_output_stream`, and
    `_serialize_chunk_and_write`.
    """

    help = "Export database rows to a JSON file (Django serialization). Supports --apps filter."

    def add_arguments(self, parser):
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

    # -------------------------
    # Small helpers
    # -------------------------
    def _parse_apps_arg(self, apps_arg: Optional[str]) -> Optional[Set[str]]:
        if not apps_arg:
            return None
        return {p.strip() for p in apps_arg.split(",") if p.strip()}

    def _resolve_output_path(self, path: str) -> str:
        base = getattr(settings, "BASE_DIR", os.getcwd())
        if not os.path.isabs(path):
            path = os.path.join(base, path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        return path

    def models_to_export(self, apps_filter: Optional[Set[str]], exclude_set: Set[str]) -> List[type]:
        all_models = list(apps.get_models())
        models_to_export: List[type] = []
        for m in all_models:
            full_name = f"{m._meta.app_label}.{m.__name__}"
            if m.__name__ in EXCLUDE_MODEL_NAMES or full_name in exclude_set or m.__name__ in exclude_set:
                continue
            if apps_filter is not None and m._meta.app_label not in apps_filter:
                continue
            models_to_export.append(m)
        return models_to_export

    def _open_output_stream(self, output: str) -> Tuple[Callable[[str], None], Callable[[], None], str]:
        """Return (write_chunk, close_fn, output_display_name).

        write_chunk is a callable that accepts a string and writes to the
        destination. close_fn closes the underlying file object when used.
        output_display_name is used in the final status message.
        """
        write_to_stdout = (output == "-")
        if write_to_stdout:
            write_chunk = lambda s: self.stdout.write(s)
            close_fn = lambda: None
            return write_chunk, close_fn, "stdout"

        # Ensure path exists and open the file handle
        output_path = self._resolve_output_path(output)
        if output_path.endswith(".gz"):
            fh = gzip.open(output_path, "wt", encoding="utf-8")
        else:
            fh = open(output_path, "w", encoding="utf-8")

        def _write(s: str):
            fh.write(s)

        def _close():
            try:
                fh.close()
            except Exception:
                pass

        return _write, _close, output_path

    def _serialize_chunk_and_write(
        self,
        chunk: List[object],
        indent: Optional[int],
        use_nat_foreign: bool,
        use_nat_primary: bool,
        write_chunk: Callable[[str], None],
        separator: str,
        first_piece: bool,
        compact: bool,
    ) -> bool:
        """Serialize a chunk and write its inner JSON array items to the stream.

        Returns True if any items were written (so caller can update first_piece).
        """
        if not chunk:
            return False

        serialized = serializers.serialize(
            "json",
            chunk,
            indent=indent,
            use_natural_foreign_keys=use_nat_foreign,
            use_natural_primary_keys=use_nat_primary,
        )
        start = serialized.find('[')
        end = serialized.rfind(']')
        if start == -1 or end == -1:
            # Fallback: write whole serialization
            inner = serialized
        else:
            inner = serialized[start + 1 : end]

        if indent is not None:
            inner = inner.lstrip('\n').rstrip('\n')
            if inner:
                if not first_piece:
                    write_chunk(separator)
                write_chunk(inner)
                return True
            return False
        else:
            inner = inner.strip()
            if inner:
                if not first_piece:
                    write_chunk(separator)
                write_chunk(inner)
                return True
            return False

    # -------------------------
    # Main handler (delegates heavily)
    # -------------------------
    def handle(self, *args, **options):
        """Main command entry: collect models and stream them to JSON output."""
        output = options["output"]
        apps_arg = options["apps"]
        exclude_arg = options["exclude"]
        indent = options["indent"]
        use_nat_foreign = options["natural_foreign"]
        use_nat_primary = options["natural_primary"]
        chunk_size = options["chunk_size"]

        apps_filter = self._parse_apps_arg(apps_arg)
        exclude_set = {x.strip() for x in exclude_arg.split(",") if x.strip()} if exclude_arg else set()

        models_to_export = self.models_to_export(apps_filter, exclude_set)
        if not models_to_export:
            raise CommandError("No models found to export (check --apps and --exclude).")

        write_chunk, close_fh, output_display = self._open_output_stream(output)

        total_objects = 0
        first_piece = True

        try:
            # Prepare JSON array delimiters
            if indent is not None:
                write_chunk("[\n")
                separator = ",\n"
                closing = "\n]\n"
            else:
                write_chunk("[")
                separator = ","
                closing = "]"

            # Stream objects model-by-model in chunks
            for model in models_to_export:
                qs = model._default_manager.all().iterator()
                chunk: List[object] = []
                for obj in qs:
                    chunk.append(obj)
                    if len(chunk) >= chunk_size:
                        wrote = self._serialize_chunk_and_write(
                            chunk,
                            indent,
                            use_nat_foreign,
                            use_nat_primary,
                            write_chunk,
                            separator,
                            first_piece,
                            compact=(indent is None),
                        )
                        if wrote:
                            first_piece = False
                        total_objects += len(chunk)
                        chunk = []

                # flush remaining
                if chunk:
                    wrote = self._serialize_chunk_and_write(
                        chunk,
                        indent,
                        use_nat_foreign,
                        use_nat_primary,
                        write_chunk,
                        separator,
                        first_piece,
                        compact=(indent is None),
                    )
                    if wrote:
                        first_piece = False
                    total_objects += len(chunk)

            # Finish JSON
            write_chunk(closing)
        finally:
            close_fh()

        self.stdout.write(self.style.SUCCESS(f"Exported {total_objects} objects to {output_display}"))
