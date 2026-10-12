"""Make account email unique and allow legacy rows to keep a missing address."""

from django.db import migrations, models


def empty_emails_to_null(apps, schema_editor):
    """Turn blank emails into NULL so a unique column can be added.

    PostgreSQL treats each NULL as distinct. Several empty strings would
    violate the unique constraint.
    """
    User = apps.get_model("accounts", "User")
    User.objects.filter(email="").update(email=None)
    for user in User.objects.exclude(email__isnull=True):
        normalized = (user.email or "").strip().lower()
        if normalized != user.email:
            user.email = normalized or None
            user.save(update_fields=["email"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_block"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(
                blank=True,
                max_length=254,
                null=True,
                verbose_name="email address",
            ),
        ),
        migrations.RunPython(empty_emails_to_null, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(
                blank=True,
                max_length=254,
                null=True,
                unique=True,
                verbose_name="email address",
            ),
        ),
    ]
