import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fools", "0007_lobbysettings_share_hand_signals"),
    ]

    operations = [
        migrations.AddField(
            model_name="lobbyplayer",
            name="joined_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
