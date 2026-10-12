"""
Authentication template routes for the Accounts app.

This module defines the endpoints for user registration, login,
profile display, logout, email confirmation, and password reset.
These routes are included in the project's main urls.py under the
prefix "accounts/".
"""

from django.urls import path

from .views import (
    PasswordResetChangeView,
    PasswordResetFinishedView,
    PasswordResetRequestView,
    PasswordResetSentView,
    confirm_email_view,
    login_view,
    logout_view,
    profile_view,
    register_done_view,
    register_view,
    resend_confirmation_view,
)

urlpatterns = [
    path('register/', register_view, name='register'),
    path('register/done/', register_done_view, name='register-done'),
    path('register/resend/', resend_confirmation_view, name='resend-confirmation'),
    path(
        'confirm-email/<uidb64>/<token>/',
        confirm_email_view,
        name='confirm-email',
    ),
    path('login/', login_view, name='login'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path(
        'password-reset/done/',
        PasswordResetSentView.as_view(),
        name='password-reset-done',
    ),
    path(
        'password-reset/<uidb64>/<token>/',
        PasswordResetChangeView.as_view(),
        name='password-reset-confirm',
    ),
    path(
        'password-reset/complete/',
        PasswordResetFinishedView.as_view(),
        name='password-reset-complete',
    ),
    path('profile/', profile_view, name='profile'),
    path('logout/', logout_view, name='logout'),
]
