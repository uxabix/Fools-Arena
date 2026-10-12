"""
Serializers for the Accounts app.

This module defines serializers used for user authentication and profile
management. They handle validation and transformation of input/output data
between Django models and API views.

Available serializers:
    - RegistrationSerializer: validates and creates new user accounts.
    - LoginSerializer: authenticates existing users with username/password.
    - ProfileSerializer: returns basic profile information for authenticated users.
"""

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .forms import PASSWORD_MAX_LENGTH
from .validators import USERNAME_MAX_LENGTH, is_reserved_username

User = get_user_model()

class RegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration.

    Uses the same password rules as the registration form, requires an
    email, and creates an inactive account until the address is confirmed.
    """
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password')
        extra_kwargs = {
            "username": {
                "trim_whitespace": False,
                "error_messages": {
                    "max_length": "Use %d characters or fewer." % USERNAME_MAX_LENGTH,
                },
            },
            "email": {"required": True, "allow_blank": False},
        }

    def validate_username(self, value):
        """Reject reserved names and names that differ only by case.

        Shape rules run from the model field validators. This adds the
        checks that need the database.

        Args:
            value (str): Username submitted by the client.

        Returns:
            str: The same username when it can be registered.
        """
        if is_reserved_username(value):
            raise serializers.ValidationError("This username is reserved.")
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with that username already exists."
            )
        return value

    def validate_email(self, value):
        """Normalize the address and reject one that is already registered.

        Args:
            value (str): Email submitted by the client.

        Returns:
            str: Lowercased email.

        Raises:
            serializers.ValidationError: If the address is already in use.
        """
        email = (value or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return email

    def validate_password(self, value):
        """Reject passwords above the product length cap.

        The other password rules run in ``validate`` so they can see the
        username and email.

        Args:
            value (str): Candidate password.

        Returns:
            str: The same password when it is not too long.
        """
        if len(value) > PASSWORD_MAX_LENGTH:
            raise serializers.ValidationError(
                "Use %d characters or fewer." % PASSWORD_MAX_LENGTH
            )
        return value

    def validate(self, attrs):
        """Run Django's password validators against the submitted identity.

        Args:
            attrs (dict): Field values that passed individual checks.

        Returns:
            dict: The same values when the password is acceptable.
        """
        candidate = User(
            username=attrs.get("username") or "",
            email=attrs.get("email") or "",
        )
        try:
            validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        """Create an inactive user with a hashed password.

        The account stays inactive until the confirmation link is opened.

        Args:
            validated_data (dict): Username, email, and password.

        Returns:
            User: The stored, inactive account.
        """
        return User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            is_active=not settings.ACCOUNT_EMAIL_CONFIRMATION_REQUIRED,
        )

class LoginSerializer(serializers.Serializer):
    """
    Serializer for user login.

    Accepts username and password, and authenticates the user
    using Django's built-in authentication system.
    """
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """
        Validate the provided credentials.

        If authentication fails, raise a ValidationError.
        On success, attach the authenticated user to attrs.
        """
        user = authenticate(username=attrs['username'], password=attrs['password'])
        if not user:
            # One message for an unknown user, a wrong password, and an
            # inactive account. authenticate() already returns None for
            # inactive users, so this does not reveal which case failed.
            raise serializers.ValidationError('Incorrect username or password.')
        attrs['user'] = user
        return attrs

class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying user profile data.

    Returns basic information about the authenticated user.
    """
    class Meta:
        model = User
        fields = ('id', 'username', 'email')
