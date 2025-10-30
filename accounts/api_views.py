from django.contrib.auth import login as auth_login, logout as auth_logout
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import RegistrationSerializer, LoginSerializer, ProfileSerializer

class RegistrationAPI(generics.CreateAPIView):
    """
    API endpoint for user registration.

    This view handles the creation of a new user account.
    It uses the RegistrationSerializer to validate and save
    the incoming data. Once the user is successfully created,
    they are automatically logged in so that the client
    immediately receives an authenticated session.
    """
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        """
        Save the new user instance and log them in.

        This method overrides the default behavior of CreateAPIView.
        After the serializer successfully saves the user, we call
        Django's built-in auth_login to attach the user to the current
        session. This ensures that the client does not need to perform
        a separate login request right after registration.
        """
        user = serializer.save()
        auth_login(self.request, user)

class LoginAPI(APIView):
    """API endpoint for user login."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """Authenticate user credentials and start a session."""
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        auth_login(request, user)
        return Response(ProfileSerializer(user).data)

class ProfileAPI(generics.RetrieveAPIView):
    """API endpoint for retrieving the authenticated user's profile."""
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """Return the current authenticated user."""
        return self.request.user

class LogoutAPI(APIView):
    """API endpoint for logging out the current user."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """End the current user session."""
        auth_logout(request)
        return Response({'detail': 'You are out of the system'}, status=status.HTTP_200_OK)
