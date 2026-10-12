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

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .forms import (
    PASSWORD_MAX_LENGTH,
    LoginForm,
    NewPasswordForm,
    PasswordResetRequestForm,
    RegistrationForm,
    password_min_length,
)
from .validators import RESERVED_USERNAMES, USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH
from .mail import send_account_confirmation
from .ratelimit import TOO_MANY_EMAIL_REQUESTS, email_request_blocked
from .tokens import email_confirm_token

logger = logging.getLogger(__name__)
User = get_user_model()


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
        'username_min_length': USERNAME_MIN_LENGTH,
        'username_max_length': USERNAME_MAX_LENGTH,
        'reserved_usernames': ",".join(sorted(RESERVED_USERNAMES)),
    }

@csrf_protect
def register_view(request):
    """Render and process the registration form.

    On success the account is inactive until the confirmation link is
    opened, unless ``ACCOUNT_EMAIL_CONFIRMATION_REQUIRED`` is false.
    That switch is refused when ``DEBUG`` is false.
    """
    if request.user.is_authenticated:
        return redirect("fools-lobby-list-page")
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            if email_request_blocked(request, form.cleaned_data.get("email") or ""):
                form.add_error(None, TOO_MANY_EMAIL_REQUESTS)
            elif settings.ACCOUNT_EMAIL_CONFIRMATION_REQUIRED:
                user = form.save(commit=False)
                user.is_active = False
                user.save()
                send_account_confirmation(request, user)
                logger.info(
                    "User registered, awaiting email confirmation: id=%s",
                    user.pk,
                )
                return redirect('register-done')
            else:
                user = form.save(commit=False)
                user.is_active = True
                user.save()
                auth_login(
                    request,
                    user,
                    backend="django.contrib.auth.backends.ModelBackend",
                )
                logger.info(
                    "User registered without email confirmation: id=%s",
                    user.pk,
                )
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


def register_done_view(request):
    """Tell the person to open the confirmation link.

    The page does not repeat the address and does not say whether a
    resend matched an account.
    """
    return render(request, "accounts/register_done.html")


@require_POST
@csrf_protect
def resend_confirmation_view(request):
    """Send another confirmation link when the account is still inactive.

    The response is the same whether or not the address matches an
    account, so the form cannot be used to look up registrations.
    """
    email = (request.POST.get("email") or "").strip().lower()
    if email_request_blocked(request, email):
        messages.error(request, TOO_MANY_EMAIL_REQUESTS)
        return redirect("register-done")
    user = None
    if email:
        user = User.objects.filter(email__iexact=email, is_active=False).first()
    if user:
        send_account_confirmation(request, user)
        logger.info("Confirmation resent: id=%s", user.pk)
    else:
        logger.info("Confirmation resend skipped")
    messages.success(
        request,
        "If an account is waiting for confirmation, we sent another link.",
    )
    return redirect("register-done")


def confirm_email_view(request, uidb64, token):
    """Activate the account when the emailed token is still valid.

    A valid link signs the person in. An already-active account is sent
    to sign-in. A bad or expired link is told to request another email.
    """
    user = None
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is not None and user.is_active:
        messages.info(request, "This account is already confirmed. Sign in to play.")
        return redirect("login")
    if user is not None and email_confirm_token.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        auth_login(
            request,
            user,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        logger.info("Email confirmed: id=%s", user.pk)
        messages.success(request, "Email confirmed. You are signed in.")
        return redirect("fools-lobby-list-page")
    logger.info("Email confirmation link rejected")
    return render(request, "accounts/confirm_email_invalid.html")


class PasswordResetRequestView(auth_views.PasswordResetView):
    """Email a reset link without revealing whether the address is registered."""

    form_class = PasswordResetRequestForm
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("password-reset-done")

    def form_valid(self, form):
        """Send the reset mail unless this IP or address is over the limit.

        A blocked request is shown on the same form. It does not say
        whether an account exists, and it does not claim a mail was sent.
        """
        email = (form.cleaned_data.get("email") or "").strip().lower()
        if email_request_blocked(self.request, email):
            form.add_error(None, TOO_MANY_EMAIL_REQUESTS)
            return self.form_invalid(form)
        return super().form_valid(form)


class PasswordResetSentView(auth_views.PasswordResetDoneView):
    """Shown after a reset request, for both known and unknown addresses."""

    template_name = "accounts/password_reset_done.html"


class PasswordResetChangeView(auth_views.PasswordResetConfirmView):
    """Let the person choose a new password from the emailed link."""

    form_class = NewPasswordForm
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("password-reset-complete")

    def get_context_data(self, **kwargs):
        """Add the password length limits used by the requirements list."""
        context = super().get_context_data(**kwargs)
        context["password_min_length"] = password_min_length()
        context["password_max_length"] = PASSWORD_MAX_LENGTH
        return context


class PasswordResetFinishedView(auth_views.PasswordResetCompleteView):
    """Shown after the password has been changed."""

    template_name = "accounts/password_reset_complete.html"


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
