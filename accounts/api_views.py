"""
API views for the Accounts app.

This module defines class-based views for handling user authentication
via RESTful endpoints. It includes registration, login, profile retrieval,
and logout functionality. These views are connected to the routes defined
in accounts/api_urls.py and use serializers from accounts/serializers.py.

Available API views:
    - RegistrationAPI: create a new user and log them in automatically.
    - LoginAPI: authenticate user credentials and start a session.
    - ProfileAPI: return profile data for the authenticated user.
    - LogoutAPI: end the current user session.
"""

from django.contrib.auth import login as auth_login, logout as auth_logout
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import RegistrationSerializer, LoginSerializer, ProfileSerializer

class RegistrationAPI(generics.CreateAPIView):
    """
    API endpoint for user registration.

    Handles the creation of a new user account using validated input.
    Automatically logs in the newly created user to establish a session.
    """
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        """
        Save the new user instance and log them in.

        Overrides the default CreateAPIView behavior to attach the user
        to the current session immediately after registration.
        """
        user = serializer.save()
        auth_login(self.request, user)

class LoginAPI(APIView):
    """
    API endpoint for user login.

    Accepts username and password, authenticates the user,
    and returns their profile data upon successful login.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """
        Authenticate user credentials and start a session.

        If credentials are valid, the user is logged in and their
        profile data is returned in the response.
        """
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        auth_login(request, user)
        return Response(ProfileSerializer(user).data)

class ProfileAPI(generics.RetrieveAPIView):
    """
    API endpoint for retrieving the authenticated user's profile.

    Requires the user to be logged in. Returns basic profile information.
    """
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """
        Return the current authenticated user.

        Used by RetrieveAPIView to serialize and return profile data.
        """
        return self.request.user

class LogoutAPI(APIView):
    """
    API endpoint for logging out the current user.

    Requires authentication. Ends the session and returns a confirmation message.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        End the current user session.

        Logs out the user and returns a success response.
        """
        auth_logout(request)
        return Response({'detail': 'You are out of the system'}, status=status.HTTP_200_OK)
