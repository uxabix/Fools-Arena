"""
Management command: create test users for development and delete users in a marker group.

This command has two main modes:

1. Creation mode (default)
   - Creates test users with configurable parameters: --count, --prefix, --start,
     --email-domain, --password, and flags --staff / --superuser / --inactive.
   - Adds created users to a marker group (default: "Test_Users") so they can be
     identified and removed later.
   - Supports --force to create users even when the plain username exists
     (a short random suffix is appended in that case).
   - Supports --dry-run to preview actions without mutating the database.

2. Deletion mode (--delete)
   - Deletes users who are members of the configured marker group (default: "Test_Users").
   - Excludes staff and superusers from deletion if the user model supports those flags.
   - Shows matched users, supports --dry-run, and requires interactive confirmation
     by default (use --noinput to skip confirmation).

Examples:
    # Create 3 users testuser1..testuser3
    python manage.py generate_test_users --count 3 --prefix testuser

    # Delete all users in Test_Users group without prompt
    python manage.py generate_test_users --delete --noinput
"""
import argparse
from typing import List, Optional
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    """CLI wrapper for creating test users and deleting users in a marker group.

    Responsibilities:
    - Parse command-line options and delegate to helper methods.
    - Keep interactive I/O (prompts and formatted output) centralized.

    The heavy lifting is done in the private helpers `_handle_create` and
    `_handle_delete` which are easier to test in isolation.
    """

    help = "Create test users or delete all users in the marker group (use --delete)."

    def add_arguments(self, parser):
        """Register the command-line arguments."""
        parser.add_argument(
            "--count",
            "-c",
            type=int,
            default=1,
            help="Number of users to create (default: 1).",
        )
        parser.add_argument(
            "--prefix",
            "-p",
            type=str,
            default="testuser",
            help='Username prefix (default: "testuser").',
        )
        parser.add_argument(
            "--start",
            type=int,
            default=1,
            help="Starting index appended to username (default: 1).",
        )
        parser.add_argument(
            "--email-domain",
            type=str,
            default="example.com",
            help="Email domain for generated users.",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="test_password",
            help="Password for created users.",
        )
        parser.add_argument(
            "--staff",
            action="store_true",
            help="Mark created users as staff.",
        )
        parser.add_argument(
            "--superuser",
            action="store_true",
            help="Create superuser(s).",
        )
        parser.add_argument(
            "--inactive",
            action="store_true",
            help="Create users with is_active=False.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Append random suffix if username exists.",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete users in marker group instead of creating.",
        )
        parser.add_argument(
            "--marker-group",
            type=str,
            default="Test_Users",
            help='Group name used to mark generated users.',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview actions without making DB changes.",
        )
        parser.add_argument(
            "--noinput",
            action="store_true",
            help="Do not prompt for confirmation when deleting.",
        )

    # ---- helpers ----
    def _make_username(self, prefix: str, idx: int) -> str:
        """Return a username built from prefix and index (e.g. 'testuser3')."""
        return f"{prefix}{idx}"

    def _email_for_username(self, username: str, domain: str) -> str:
        """Return a simple email address for the given username and domain."""
        return f"{username}@{domain}"

    @staticmethod
    def _random_suffix(length: int = 4) -> str:
        """Return a short random alphanumeric suffix for collision avoidance."""
        import random, string
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choice(chars) for _ in range(length))

    def _handle_delete(self, marker_group_name: str, dry_run: bool, noinput: bool) -> None:
        """Delete non-staff/non-superuser users who belong to the marker group.

        Behavior:
        - Prints matched users and total count.
        - If dry_run is True, only prints what would be deleted.
        - If noinput is False, prompts interactively before deletion.
        - Uses a single transaction to perform deletions atomically.
        - Collects and reports failures without hiding them.
        """
        try:
            group = Group.objects.get(name=marker_group_name)
        except Group.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                f"Marker group '{marker_group_name}' does not exist. Nothing to delete."
            ))
            return

        qs = User.objects.filter(groups__name=marker_group_name)

        # Exclude privileged accounts if those attributes exist
        if hasattr(User, "is_staff"):
            qs = qs.exclude(is_staff=True)
        if hasattr(User, "is_superuser"):
            qs = qs.exclude(is_superuser=True)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("No non-staff/non-superuser users found in marker group."))
            return

        self.stdout.write(self.style.WARNING(f"Matched users for deletion (group='{marker_group_name}'): {total}"))
        for u in qs:
            parts = [f"username='{getattr(u, 'username', '<no-username>')}'"]
            if getattr(u, "email", None):
                parts.append(f"email='{u.email}'")
            self.stdout.write("  - " + " ".join(parts))

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: no users were deleted."))
            return

        if not noinput:
            answer = input("Delete all listed users? This is irreversible. [y/N]: ")
            if answer.lower() not in ("y", "yes"):
                self.stdout.write(self.style.WARNING("Aborted by user."))
                return

        deleted = 0
        failed = []
        try:
            with transaction.atomic():
                for u in qs:
                    try:
                        u.delete()
                        deleted += 1
                    except Exception as exc:
                        failed.append((u, exc))
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} users from group '{marker_group_name}'."))

            if failed:
                self.stdout.write(self.style.ERROR(f"{len(failed)} deletions failed:"))
                for u, exc in failed:
                    self.stdout.write(f"  - {getattr(u, 'username', '<no-username>')}: {exc}")
        except Exception as exc_outer:
            raise CommandError(f"Deletion transaction failed: {exc_outer}")

    def _handle_create(
        self,
        options,
        dry_run: bool,
        marker_group_name: str,
    ) -> None:
        """Create multiple users and add them to the marker group.

        Behavior:
        - Respects `force` to append a random suffix when a plain username exists.
        - Uses get_or_create semantics for the marker group (created if absent).
        - Adds users to the marker group when possible; reports warnings on failure.
        - Prints a success message per created user and a final summary.
        """
        created: List[User] = []

        count: int = int(options.get("count", 1))
        prefix: str = options.get("prefix") or "testuser"
        start: int = int(options.get("start", 1))
        email_domain: str = options.get("email_domain") or "example.com"
        password: str = options.get("password") or "test_password"
        make_staff: bool = bool(options.get("staff"))
        make_superuser: bool = bool(options.get("superuser"))
        inactive: bool = bool(options.get("inactive"))
        force: bool = bool(options.get("force"))

        group_obj: Optional[Group] = None
        try:
            group_obj, _ = Group.objects.get_or_create(name=marker_group_name)
        except Exception:
            group_obj = None

        for i in range(start, start + count):
            username = self._make_username(prefix, i)
            email = self._email_for_username(username, email_domain)

            if User.objects.filter(username=username).exists():
                if not force:
                    self.stdout.write(self.style.WARNING(f"Skipping existing username: {username}"))
                    continue
                username = f"{username}_{self._random_suffix()}"
                email = self._email_for_username(username, email_domain)
                try:
                    self.stdout.write(self.style.NOTICE(f"Username existed; using fallback username: {username}"))
                except Exception:
                    # Some Django versions may not provide NOTICE style
                    self.stdout.write(f"NOTICE: Username existed; using fallback username: {username}")

            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] Would create username='{username}', email='{email}', staff={make_staff}, superuser={make_superuser}, active={not inactive}"
                )
                continue

            if make_superuser:
                user = User.objects.create_superuser(username=username, email=email, password=password)  # type: ignore[attr-defined]
                try:
                    user.is_staff = True
                    user.is_superuser = True
                except Exception:
                    pass
            else:
                user = User.objects.create_user(username=username, email=email, password=password)  # type: ignore[attr-defined]
                try:
                    user.is_staff = bool(make_staff)
                    user.is_superuser = False
                except Exception:
                    pass

            try:
                user.is_active = not bool(inactive)
            except Exception:
                pass

            try:
                if group_obj is not None and hasattr(user, "groups"):
                    user.groups.add(group_obj)
            except Exception:
                self.stdout.write(self.style.WARNING(f"Warning: couldn't add user '{username}' to group '{marker_group_name}'"))

            user.save()
            created.append(user)
            self.stdout.write(self.style.SUCCESS(f"Created user: username='{username}' email='{email}'"))

        # final summary (SQL_TABLE may not exist in all versions, fall back if needed)
        try:
            self.stdout.write(self.style.SQL_TABLE(f"Total users created: {len(created)}"))
        except Exception:
            self.stdout.write(f"Total users created: {len(created)}")

    # ---- entry point ----
    def handle(self, *args, **options):
        """Parse CLI options and dispatch to the create or delete handler.

        This method is intentionally short: it validates and extracts options
        and then delegates functionality to `_handle_delete` or `_handle_create`.
        """
        dry_run: bool = options.get("dry_run", False)
        marker_group_name: str = options.get("marker_group") or "Test_Users"

        # Deletion mode
        if options.get("delete"):
            self._handle_delete(marker_group_name=marker_group_name, dry_run=dry_run, noinput=options.get("noinput", False))
            return

        # Creation mode: collect options and delegate


        self._handle_create(
            options=options,
            dry_run=dry_run,
            marker_group_name=marker_group_name,
        )
