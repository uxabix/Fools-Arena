"""
generate_test_users management command.

Creates one or more test users for development/testing.

Example:
    # create 5 regular test users with default password
    python manage.py generate_test_users --count 5 --prefix testuser

    # create 3 staff users with a custom email domain and password
    python manage.py generate_test_users -c 3 --prefix staff_ --email-domain example.org --password secret123 --staff

    # create 1 superuser
    python manage.py generate_test_users --count 1 --prefix admin --superuser --password adminpass
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import random
import string
from typing import List

User = get_user_model()


def _random_suffix(length: int = 4) -> str:
    """Return a short random alphanumeric suffix.

    Args:
        length: Length of the suffix.

    Returns:
        A random string composed of lowercase letters and digits.
    """
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


class Command(BaseCommand):
    """Django command to generate test users.

    The command creates users using `User.objects.create_user()` (or
    `create_superuser()` when the `--superuser` flag is used). It will skip
    usernames that already exist unless `--force` is provided, in which case
    a short random suffix is appended to the username.

    Methods
    -------
    add_arguments(parser):
        Add command-line arguments.
    handle(*args, **options):
        Main entry point that creates users according to parsed options.
    """

    help = "Generate test users (regular, staff, or superuser) for development."

    def add_arguments(self, parser):
        """Add command-line arguments.

        Args:
            parser: The argparse parser to configure.
        """
        parser.add_argument(
            '--count', '-c',
            type=int,
            default=1,
            help='Number of users to create (default: 1)'
        )
        parser.add_argument(
            '--prefix', '-p',
            type=str,
            default='testuser',
            help='Prefix for usernames (default: "testuser")'
        )
        parser.add_argument(
            '--start',
            type=int,
            default=1,
            help='Starting index appended to username (default: 1)'
        )
        parser.add_argument(
            '--email-domain',
            type=str,
            default='example.com',
            help='Email domain to use for generated users (default: example.com)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default='test_password',
            help='Password to set for all created users (default: "test_password")'
        )
        parser.add_argument(
            '--staff',
            action='store_true',
            help='Mark created users as staff (is_staff=True)'
        )
        parser.add_argument(
            '--superuser',
            action='store_true',
            help='Create superuser(s) (uses create_superuser)'
        )
        parser.add_argument(
            '--inactive',
            action='store_true',
            help='Create users with is_active=False'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='If username exists, append random suffix and create anyway'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be created without saving to the database'
        )

    def _make_username(self, prefix: str, idx: int) -> str:
        """Construct a username from prefix and index.

        Args:
            prefix: Username prefix.
            idx: Index to append.

        Returns:
            The composed username (e.g. "prefix1").
        """
        return f"{prefix}{idx}"

    def _email_for_username(self, username: str, domain: str) -> str:
        """Construct an email address for a username.

        Args:
            username: The username to use before the @.
            domain: The domain to use after the @.

        Returns:
            A complete email address string.
        """
        return f"{username}@{domain}"

    def handle(self, *args, **options):
        """Create the requested number of test users.

        Args:
            *args: positional args (unused).
            **options: Parsed command-line options.

        Returns:
            None
        """
        count: int = options['count']
        prefix: str = options['prefix']
        start: int = options['start']
        email_domain: str = options['email_domain']
        password: str = options['password']
        make_staff: bool = options['staff']
        make_superuser: bool = options['superuser']
        inactive: bool = options['inactive']
        force: bool = options['force']
        dry_run: bool = options['dry_run']

        created: List[User] = []

        # loop to create the requested number of users
        for i in range(start, start + count):
            username = self._make_username(prefix, i)
            email = self._email_for_username(username, email_domain)

            # If the username already exists and --force is not used, skip it.
            if User.objects.filter(username=username).exists():
                if not force:
                    self.stdout.write(self.style.WARNING(
                        f"Skipping existing username: {username}"
                    ))
                    continue

                # If force mode, append a short random suffix to make it unique.
                username = f"{username}_{_random_suffix()}"
                email = self._email_for_username(username, email_domain)
                self.stdout.write(self.style.NOTICE(
                    f"Username existed; using fallback username: {username}"
                ))

            # Dry-run prints and does not save to DB.
            if dry_run:
                self.stdout.write(f"[DRY RUN] Would create: username='{username}', email='{email}', "
                                  f"is_staff={make_staff}, is_superuser={make_superuser}, is_active={not inactive}")
                continue

            # Create a superuser if requested (this calls create_superuser which
            # typically sets is_staff/is_superuser automatically).
            if make_superuser:
                # create_superuser signature: (username, email=None, password=None, **extra_fields)
                user = User.objects.create_superuser(username=username, email=email, password=password) # type: ignore[attr-defined]
                # Ensure flags align with requested options (some custom user models
                # might require setting them explicitly).
                user.is_staff = True
                user.is_superuser = True
            else:
                # Regular user creation (hashes the password)
                user = User.objects.create_user(username=username, email=email, password=password) # type: ignore[attr-defined]
                user.is_staff = bool(make_staff)
                user.is_superuser = False

            # Set active state based on --inactive
            user.is_active = not bool(inactive)

            # Save changes (if any) and collect result.
            user.save()
            created.append(user)

            # Informational output for each created user.
            self.stdout.write(self.style.SUCCESS(
                f"Created user: username='{username}' email='{email}' "
                f"{'(staff)' if user.is_staff else ''} {'(superuser)' if user.is_superuser else ''}"
            ))

        # Summary output
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete. No users were created."))
        else:
            self.stdout.write(self.style.SQL_TABLE(f"Total users created: {len(created)}"))
