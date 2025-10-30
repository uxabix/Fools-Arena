from django.urls import path
from .api_views import RegistrationAPI, LoginAPI, ProfileAPI, LogoutAPI

"""
Authentication API routes for the Accounts app.

This module defines the endpoints for user registration, login,
profile retrieval, and logout. These routes are included in the
project’s main urls.py under the prefix "api/accounts/", which means
the final URLs are:

    /api/accounts/auth/register/   → Register a new user
    /api/accounts/auth/login/      → Log in an existing user
    /api/accounts/auth/profile/    → Retrieve the authenticated user's profile
    /api/accounts/auth/logout/     → Log out the current user
    
Each path is mapped to a class-based API view defined in accounts/api_views.py.
"""
urlpatterns = [
    path('auth/register/', RegistrationAPI.as_view(), name='api_register'),
    path('auth/login/', LoginAPI.as_view(), name='api_login'),
    path('auth/profile/', ProfileAPI.as_view(), name='api_profile'),
    path('auth/logout/', LogoutAPI.as_view(), name='api_logout'),
]
