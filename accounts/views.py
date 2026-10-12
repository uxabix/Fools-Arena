"""
Views for the Accounts app.

This module defines function-based views for handling user authentication
through HTML templates. It includes registration, login, profile display,
and logout functionality. These views are connected to the routes defined
in accounts/urls.py and render templates located in accounts/templates/accounts/.

Available views:
    - register_view: render and process the registration form.
    - login_view: render and process the login form.
    - profile_view: display the authenticated user's profile page.
    - logout_view: log out the current user and redirect accordingly.
"""

import logging

from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_protect

from .forms import (
    PASSWORD_MAX_LENGTH,
    LoginForm,
    RegistrationForm,
    password_min_length,
)

logger = logging.getLogger(__name__)


def _auth_context(form):
    """Build template context shared by the login and registration pages.

    Args:
        form: Bound or unbound authentication form.

    Returns:
        dict: Form plus the password length limits shown in the UI.
    """
    return {
        'form': form,
        'password_min_length': password_min_length(),
        'password_max_length': PASSWORD_MAX_LENGTH,
    }

@csrf_protect
def register_view(request):
    """Render and process the registration form.

    On success the new user is signed in and sent to the lobby list with
    a confirmation message. There is no email verification step.
    """
    if request.user.is_authenticated:
        return redirect("fools-lobby-list-page")
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            logger.info("User registered: id=%s", user.pk)
            messages.success(request, "Account created. You are signed in.")
            return redirect('fools-lobby-list-page')
        logger.info(
            "Registration failed: fields=%s",
            ",".join(form.errors.keys()),
        )
    else:
        form = RegistrationForm()
    return render(request, 'accounts/registration.html', _auth_context(form))

@csrf_protect
def login_view(request):
    """Render and process the login form.

    Failed attempts are logged with the attempted username only.
    The password is never written to the log.
    """
    if request.user.is_authenticated:
        return redirect("fools-lobby-list-page")
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            logger.info("User signed in: id=%s", user.pk)
            return redirect('fools-lobby-list-page')
        attempted = (request.POST.get('username') or '')[:150]
        logger.info("Sign-in failed for username=%s", attempted)
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', _auth_context(form))

@login_required
def profile_view(request):
    """
    Display the authenticated user's profile page.

    Requires the user to be logged in. If the user is not authenticated,
    they will be redirected to the login page.
    """
    return render(request, 'accounts/profile.html')

@csrf_protect
def logout_view(request):
    """
    Log out the current user.

    If the request method is POST, the user is logged out and redirected
    to the login page. For non-POST requests, the user is redirected
    back to the profile page.
    """
    if request.method == 'POST':
        auth_logout(request)
        return redirect('login')
    return redirect('profile')
