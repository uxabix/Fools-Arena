from django.contrib.auth import authenticate
from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class RegistrationSerializer(serializers.ModelSerializer):
    # Serializer for user registration
    # Validates and creates a new user instance
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ('username', 'email', 'password')

    def create(self, validated_data):
        # Creates a new user with encrypted password
        return User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
        )

class LoginSerializer(serializers.Serializer):
    # Serializer for user login
    # Authenticates user credentials
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        # Validates the provided username and password
        user = authenticate(username=attrs['username'], password=attrs['password'])
        if not user:
            raise serializers.ValidationError('Incorrect login details')
        attrs['user'] = user
        return attrs

class ProfileSerializer(serializers.ModelSerializer):
    # Serializer for displaying user profile data
    class Meta:
        model = User
        fields = ('id', 'username', 'email')
