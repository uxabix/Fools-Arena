"""Outbound account email."""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import email_confirm_token

logger = logging.getLogger(__name__)


def send_account_confirmation(request, user):
    """Email a one-time link that activates ``user``.

    Args:
        request: Current HTTP request, used to build an absolute URL.
        user: Inactive account whose ``email`` should receive the link.

    Returns:
        int: Number of messages handed to the email backend.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_confirm_token.make_token(user)
    url = request.build_absolute_uri(
        reverse("confirm-email", kwargs={"uidb64": uid, "token": token})
    )
    logger.info("Sending account confirmation: id=%s", user.pk)
    return send_mail(
        subject="Confirm your Fools Arena account",
        message=(
            "Confirm your Fools Arena account by opening this link:\n\n"
            f"{url}\n\n"
            "You can sign in after the link is opened. "
            "If you did not create an account, you can ignore this email.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
