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

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

User = get_user_model()

class RegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration.

    Validates the provided username, email, and password.
    Creates a new user instance with an encrypted password.
    """
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ('username', 'email', 'password')

    def create(self, validated_data):
        """
            Create a new user with the given validated data.

            Uses Django's built-in create_user method to ensure
            the password is properly hashed before saving.
        """
        return User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
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
            raise serializers.ValidationError('Incorrect login details')
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
