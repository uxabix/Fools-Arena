"""
API views for the Accounts app.

Registration creates an inactive user and emails a confirmation link.
Login starts a session only after that link has been opened.
"""

import logging

from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .mail import send_account_confirmation
from .ratelimit import TOO_MANY_EMAIL_REQUESTS, email_request_blocked
from .serializers import RegistrationSerializer, LoginSerializer, ProfileSerializer

logger = logging.getLogger(__name__)

class RegistrationAPI(generics.CreateAPIView):
    """
    API endpoint for user registration.

    Creates an inactive account and emails a confirmation link.
    The response does not start a session.
    """
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        """Validate, store the inactive user, and send the confirmation email.

        Args:
            request: DRF request with username, email, and password.

        Returns:
            Response: 201 with a confirmation notice, or 400 when invalid.
        """
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.info(
                "API registration failed: fields=%s",
                ",".join(serializer.errors.keys()),
            )
            raise ValidationError(serializer.errors)
        if email_request_blocked(request, serializer.validated_data.get("email") or ""):
            return Response(
                {"detail": TOO_MANY_EMAIL_REQUESTS},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        self.perform_create(serializer)
        if settings.ACCOUNT_EMAIL_CONFIRMATION_REQUIRED:
            detail = "Account created. A confirmation link was sent to your email."
        else:
            detail = "Account created. You are signed in."
        return Response({"detail": detail}, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        """Save the inactive user and email the confirmation link.

        Args:
            serializer: Validated registration serializer.
        """
        user = serializer.save()
        if not settings.ACCOUNT_EMAIL_CONFIRMATION_REQUIRED:
            auth_login(
                self.request,
                user,
                backend="django.contrib.auth.backends.ModelBackend",
            )
            logger.info("API registration without email confirmation: id=%s", user.pk)
            return
        send_account_confirmation(self.request, user)
        logger.info("API registration awaiting confirmation: id=%s", user.pk)

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

        Failed attempts are logged with the username only.
        An unconfirmed account gets the same error as a wrong password.
        """
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            attempted = str(request.data.get("username") or "")[:150]
            logger.info("API sign-in failed for username=%s", attempted)
            raise ValidationError(serializer.errors)
        user = serializer.validated_data['user']
        auth_login(request, user)
        logger.info("API sign-in: id=%s", user.pk)
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
