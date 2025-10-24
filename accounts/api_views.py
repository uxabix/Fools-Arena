from django.contrib.auth import login as auth_login, logout as auth_logout
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import RegistrationSerializer, LoginSerializer, ProfileSerializer

class RegistrationAPI(generics.CreateAPIView):
    """API endpoint for user registration."""
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        """Create a new user and log them in automatically."""
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
