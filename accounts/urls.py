"""
Authentication template routes for the Accounts app.

This module defines the endpoints for user registration, login,
profile display, and logout. These routes are included in the
project’s main urls.py under the prefix "accounts/", which means
the final URLs are:

    /accounts/register/   → Render the registration form and create a new user
    /accounts/login/      → Render the login form and authenticate a user
    /accounts/profile/    → Display the authenticated user's profile page
    /accounts/logout/     → Log out the current user and redirect accordingly

Each path is mapped to a function-based view defined in accounts/views.py.
"""

from django.urls import path
from .views import register_view, login_view, profile_view, logout_view

urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('profile/', profile_view, name='profile'),
    path('logout/', logout_view, name='logout'),
]
