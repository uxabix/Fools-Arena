"""Signed links for account email confirmation."""

from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailConfirmTokenGenerator(PasswordResetTokenGenerator):
    """Token that stops working once the account is activated.

    The hash includes ``is_active`` and the email, so confirming the
    account or changing the address invalidates older links.
    """

    def _make_hash_value(self, user, timestamp):
        """Build the value hashed into the confirmation token.

        Args:
            user: Account the link belongs to.
            timestamp: Token creation time, as produced by the base class.

        Returns:
            str: Material that changes when the account is confirmed.
        """
        email = user.email or ""
        return f"{user.pk}{user.password}{user.is_active}{timestamp}{email}"


email_confirm_token = EmailConfirmTokenGenerator()
