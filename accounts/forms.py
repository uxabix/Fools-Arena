"""
Forms for the Accounts app.

This module defines form classes used for user registration and login.
They extend Django's built-in authentication forms to include additional
fields or custom behavior where necessary.

Available forms:
    - RegistrationForm: extends UserCreationForm to include an email field.
    - LoginForm: extends AuthenticationForm for user login.
"""

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()

# Raw passwords are hashed before storage, so this cap is a product limit
# (passphrases stay usable; multi-megabyte values are rejected) rather than
# the width of the password hash column.
PASSWORD_MAX_LENGTH = 128

# Same wording for a missing account, a wrong password, and an inactive
# account. Naming which of those failed would let callers test whether a
# username is registered.
GENERIC_LOGIN_ERROR = "Incorrect username or password."


def password_min_length():
    """Return the configured minimum password length.

    Reads ``MinimumLengthValidator`` from ``AUTH_PASSWORD_VALIDATORS``.
    Falls back to 8, Django's default, when that validator is not installed.

    Returns:
        int: Minimum number of characters a new password must contain.
    """
    validators = password_validation.get_password_validators(
        settings.AUTH_PASSWORD_VALIDATORS
    )
    for validator in validators:
        min_length = getattr(validator, "min_length", None)
        if isinstance(min_length, int):
            return min_length
    return 8


class InvalidFieldMixin:
    """Expose invalid fields to assistive technology after validation."""

    def full_clean(self):
        """Validate, then mark each field that has an error.

        Sets ``aria-invalid="true"`` on widgets whose field failed.
        Screen readers use that flag in addition to the visible message.
        """
        super().full_clean()
        for name in self.errors:
            field = self.fields.get(name)
            if field is None:
                continue
            field.widget.attrs["aria-invalid"] = "true"


def _password_widget(autocomplete, placeholder, described_by):
    """Build a password input that keeps its value across a failed submit.

    ``render_value=True`` redisplays what the person typed when another
    field is invalid. Paste from a password manager stays allowed: there
    is no ``maxlength`` and no paste handler.

    Args:
        autocomplete (str): Autocomplete token, such as ``new-password``.
        placeholder (str): Example text shown until the person types.
        described_by (str): Space-separated ids of the hint and error nodes.

    Returns:
        forms.PasswordInput: Configured password widget.
    """
    return forms.PasswordInput(
        render_value=True,
        attrs={
            "class": "fools-input",
            "autocomplete": autocomplete,
            "placeholder": placeholder,
            "autocapitalize": "none",
            "autocorrect": "off",
            "spellcheck": "false",
            "aria-describedby": described_by,
        },
    )


class RegistrationForm(InvalidFieldMixin, UserCreationForm):
    """
    Form for user registration.

    Collects only the fields needed to create an account: username, email,
    password, and password confirmation. Password rules are the project's
    ``AUTH_PASSWORD_VALIDATORS`` plus an upper length of
    ``PASSWORD_MAX_LENGTH``. Policy failures are attached to the password
    field (Django otherwise reports them on the confirmation field).
    """

    error_messages = {
        "password_mismatch": "Passwords do not match.",
    }

    email = forms.EmailField(
        required=True,
        label="Email",
        error_messages={
            "required": "Enter your email.",
            "invalid": "Enter a valid email address, such as name@example.com.",
        },
    )

    field_order = ["username", "email", "password1", "password2"]

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        username = self.fields["username"]
        username.label = "Username"
        username.help_text = (
            "Letters, digits, and @ . + - _ only. Up to 150 characters."
        )
        username.error_messages["required"] = "Enter a username."
        username.widget.attrs.update(
            {
                "class": "fools-input",
                "placeholder": "player_one",
                "autocomplete": "username",
                "autocapitalize": "none",
                "spellcheck": "false",
                "aria-describedby": "id_username-hint id_username-feedback",
            }
        )

        self.fields["email"].widget.attrs.update(
            {
                "class": "fools-input",
                "placeholder": "name@example.com",
                "autocomplete": "email",
                "autocapitalize": "none",
                "spellcheck": "false",
                "inputmode": "email",
                "aria-describedby": "id_email-feedback",
            }
        )

        password1 = self.fields["password1"]
        password1.label = "Password"
        password1.help_text = ""
        password1.error_messages["required"] = "Enter a password."
        password1.widget = _password_widget(
            "new-password",
            "Enter a password",
            "password-rules id_password1-feedback",
        )

        password2 = self.fields["password2"]
        password2.label = "Confirm password"
        password2.help_text = ""
        password2.error_messages["required"] = "Confirm your password."
        password2.widget = _password_widget(
            "new-password",
            "Re-enter your password",
            "id_password2-feedback",
        )

    def validate_password_for_user(self, user, password_field_name="password1"):
        """Apply length and policy checks to the password field.

        Django's mixin reports validator failures on the confirmation
        field. This override reports them on ``password1``, next to the
        requirements list, and rejects values longer than
        ``PASSWORD_MAX_LENGTH`` before the other validators run.

        Args:
            user: Unsaved user instance carrying username and email.
            password_field_name (str): Ignored. Errors always use ``password1``.
        """
        password = self.cleaned_data.get("password1")
        if password and len(password) > PASSWORD_MAX_LENGTH:
            self.add_error(
                "password1",
                "Use %d characters or fewer." % PASSWORD_MAX_LENGTH,
            )
            return
        super().validate_password_for_user(user, password_field_name="password1")


class LoginForm(InvalidFieldMixin, AuthenticationForm):
    """
    Form for user login.

    Authenticates with username and password. Every credential failure uses
    ``GENERIC_LOGIN_ERROR``, including an inactive account, and the message
    is attached to the password field.
    """

    error_messages = {
        "invalid_login": GENERIC_LOGIN_ERROR,
        "inactive": GENERIC_LOGIN_ERROR,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        username = self.fields["username"]
        username.label = "Username"
        username.error_messages["required"] = "Enter your username."
        username.widget.attrs.update(
            {
                "class": "fools-input",
                "placeholder": "player_one",
                "autocomplete": "username",
                "autocapitalize": "none",
                "spellcheck": "false",
                "aria-describedby": "id_username-feedback",
            }
        )

        password = self.fields["password"]
        password.label = "Password"
        password.error_messages["required"] = "Enter your password."
        password.widget = _password_widget(
            "current-password",
            "Enter your password",
            "id_password-feedback",
        )

    def clean(self):
        """Authenticate and keep credential errors on the password field.

        Returns:
            dict: Cleaned form data. On failure the password value is
            dropped from this dict, but the posted value is still
            redisplayed by the widget.
        """
        try:
            return super().clean()
        except forms.ValidationError as exc:
            self.add_error("password", exc)
            return self.cleaned_data
