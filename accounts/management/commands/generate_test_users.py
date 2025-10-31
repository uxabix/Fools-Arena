"""
Create test users for development/testing and optionally delete all users
belonging to the marker group (default: Test_Users).

This command has two modes:

* Creation (default): create users with --count, --prefix, --password, etc.
  Created users are added to the marker group so they can be deleted safely later.

* Deletion: pass --delete to delete all users who are members of the marker group.
  Deletion excludes staff and superusers by default to avoid accidental removal.

Examples:
    # Create 5 users:
    python manage.py generate_test_users --count 5 --prefix dev_ --password secret

    # Dry-run create:
    python manage.py generate_test_users --count 3 --prefix demo --dry-run

    # Delete all users in Test_Users group (interactive confirmation)
    python manage.py generate_test_users --delete

    # Delete without prompt (careful!)
    python manage.py generate_test_users --delete --noinput

    # Preview deletions without performing them
    python manage.py generate_test_users --delete --dry-run
"""
from __future__ import annotations

import random
import string
from typing import List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

User = get_user_model()


def _random_suffix(length: int = 4) -> str:
    """Generate a short random alphanumeric suffix.

    Args:
        length: Length of the suffix (default: 4).

    Returns:
        A random string composed of lowercase letters and digits.
    """
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


class Command(BaseCommand):
    """Management command to create test users and delete marker-group users.

    Creation mode (default) creates test users and adds them to a marker group
    (default group name: "Test_Users") so they can be deleted later.

    Deletion mode (pass --delete) deletes all users who are members of the
    marker group. Staff and superusers are excluded from deletion by default.
    """

    help = "Create test users or delete all users in the marker group (use --delete)."

    def add_arguments(self, parser):
        """Define command-line arguments."""
        # Creation args
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
            help='Prefix for usernames (default: "testuser").',
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
            help="Email domain for generated users (default: example.com).",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="test_password",
            help='Password to set for created users (default: "test_password").',
        )
        parser.add_argument(
            "--staff",
            action="store_true",
            help="Mark created users as staff (is_staff=True).",
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
            help="If username exists, append short random suffix and create anyway.",
        )

        # Marker group (default Test_Users)
        parser.add_argument(
            "--marker-group",
            type=str,
            default="Test_Users",
            help='Group name used to mark generated users (default: "Test_Users").',
        )

        # Deletion mode - simplified: one flag to delete all marker-group members
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete ALL users who are members of the marker group (default: Test_Users).",
        )

        # Shared safety args
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview actions (no DB changes).",
        )
        parser.add_argument(
            "--noinput",
            action="store_true",
            help="Do not prompt for confirmation when deleting (use with care).",
        )

    def _make_username(self, prefix: str, idx: int) -> str:
        """Construct username from prefix and index."""
        return f"{prefix}{idx}"

    def _email_for_username(self, username: str, domain: str) -> str:
        """Construct a simple email for a username."""
        return f"{username}@{domain}"

    def handle(self, *args, **options):
        """Main entry: create users or delete marker-group users."""
        dry_run: bool = options.get("dry_run", False)
        marker_group_name: str = options.get("marker_group") or "Test_Users"

        # Deletion mode: delete all users in marker group (excluding staff/superuser)
        if options.get("delete"):
            # Ensure the group exists
            try:
                group = Group.objects.get(name=marker_group_name)
            except Group.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f"Marker group '{marker_group_name}' does not exist. Nothing to delete."
                ))
                return

            # Query users in the group
            qs = User.objects.filter(groups__name=marker_group_name)

            # Exclude staff and superuser accounts for safety if model has those flags
            if hasattr(User, "is_staff"):
                qs = qs.exclude(is_staff=True)
            if hasattr(User, "is_superuser"):
                qs = qs.exclude(is_superuser=True)

            total = qs.count()
            if total == 0:
                self.stdout.write(self.style.WARNING("No non-staff/non-superuser users found in marker group."))
                return

            # List matched users
            self.stdout.write(self.style.WARNING(f"Matched users for deletion (group='{marker_group_name}'): {total}"))
            for u in qs:
                parts = [f"username='{getattr(u, 'username', '<no-username>')}'"]
                if getattr(u, "email", None):
                    parts.append(f"email='{u.email}'")
                self.stdout.write("  - " + " ".join(parts))

            if dry_run:
                self.stdout.write(self.style.WARNING("Dry run: no users were deleted."))
                return

            # Confirm unless noinput
            if not options.get("noinput"):
                answer = input("Delete all listed users? This is irreversible. [y/N]: ")
                if answer.lower() not in ("y", "yes"):
                    self.stdout.write(self.style.WARNING("Aborted by user."))
                    return

            # Perform deletions
            deleted = 0
            failed = []
            try:
                with transaction.atomic():
                    for u in qs:
                        try:
                            u.delete()  # call delete() to respect signals/cascades
                            deleted += 1
                        except Exception as exc:
                            failed.append((u, exc))
                            # continue deleting others
                self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} users from group '{marker_group_name}'."))
                if failed:
                    self.stdout.write(self.style.ERROR(f"{len(failed)} deletions failed:"))
                    for u, exc in failed:
                        self.stdout.write(f"  - {getattr(u, 'username', '<no-username>')}: {exc}")
            except Exception as exc_outer:
                raise CommandError(f"Deletion transaction failed: {exc_outer}")

            return  # done

        # Creation mode: create users and add to marker group
        count: int = int(options.get("count", 1))
        prefix: str = options.get("prefix") or "testuser"
        start: int = int(options.get("start", 1))
        email_domain: str = options.get("email_domain") or "example.com"
        password: str = options.get("password") or "test_password"
        make_staff: bool = bool(options.get("staff"))
        make_superuser: bool = bool(options.get("superuser"))
        inactive: bool = bool(options.get("inactive"))
        force: bool = bool(options.get("force"))

        created: List[User] = []

        # Ensure marker group exists (get_or_create is safe; use admin-created group if present)
        group_obj: Optional[Group] = None
        try:
            group_obj, _ = Group.objects.get_or_create(name=marker_group_name)
        except Exception:
            group_obj = None

        for i in range(start, start + count):
            username = self._make_username(prefix, i)
            email = self._email_for_username(username, email_domain)

            # Handle existing username
            if User.objects.filter(username=username).exists():
                if not force:
                    self.stdout.write(self.style.WARNING(f"Skipping existing username: {username}"))
                    continue
                username = f"{username}_{_random_suffix()}"
                email = self._email_for_username(username, email_domain)
                self.stdout.write(self.style.NOTICE(f"Username existed; using fallback username: {username}"))

            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] Would create username='{username}', email='{email}', staff={make_staff}, superuser={make_superuser}, active={not inactive}"
                )
                continue

            # Create user
            if make_superuser:
                user = User.objects.create_superuser(username=username, email=email,
                                                     password=password)  # type: ignore[attr-defined]
                try:
                    user.is_staff = True
                    user.is_superuser = True
                except Exception:
                    pass
            else:
                user = User.objects.create_user(username=username, email=email,
                                                password=password)  # type: ignore[attr-defined]
                try:
                    user.is_staff = bool(make_staff)
                    user.is_superuser = False
                except Exception:
                    pass

            try:
                user.is_active = not bool(inactive)
            except Exception:
                pass

            # Add to marker group if possible
            try:
                if group_obj is not None and hasattr(user, "groups"):
                    user.groups.add(group_obj)
            except Exception:
                self.stdout.write(
                    self.style.WARNING(f"Warning: couldn't add user '{username}' to group '{marker_group_name}'"))

            user.save()
            created.append(user)
            self.stdout.write(self.style.SUCCESS(f"Created user: username='{username}' email='{email}'"))

        self.stdout.write(self.style.SQL_TABLE(f"Total users created: {len(created)}"))
