from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0009_message_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatparticipant",
            name="last_read_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Newest moment this member has caught up to. Empty means nothing is read.",
                null=True,
            ),
        ),
    ]
