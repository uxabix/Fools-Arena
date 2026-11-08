"""Forms for server-rendered chat flows (mirroring REST validation rules)."""

from django import forms


class StartDirectChatForm(forms.Form):
    """Identify another user to open or reuse a 1-on-1 chat."""

    other_username = forms.CharField(
        max_length=150,
        label="Other user's username",
        help_text="Case-insensitive match to an existing account.",
    )

    def clean_other_username(self):
        """Return stripped username for lookup."""
        return (self.cleaned_data.get("other_username") or "").strip()


class ChatMessageForm(forms.Form):
    """Post a new message in a chat room (HTTP form, same limits as the API)."""

    content = forms.CharField(
        max_length=10000,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Type a message…", "class": "chat-input"}
        ),
    )

    def clean_content(self):
        """Strip whitespace; reject empty after strip."""
        value = (self.cleaned_data.get("content") or "").strip()
        if not value:
            raise forms.ValidationError("Message cannot be empty.")
        return value
